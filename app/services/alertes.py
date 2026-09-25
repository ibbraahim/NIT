"""UC18 · Émettre une alerte — UC19 · Traiter une alerte.

UC18 est déclenchée manuellement par le responsable (bouton « Détecter les alertes » de
l'écran Alertes) ou par la tâche planifiée (lot 8) ; elle compare le plan de charge **validé**
et les KPI déjà calculés à leurs seuils, et émet ou met à jour les alertes correspondantes
(déduplication par ``cle_deduplication``, comme la dérive de modèle de l'UC21).

Assignation (non détaillée par le prompt) : à l'émission, une alerte n'est assignée à
personne ; « Prendre en charge » (UC19) l'assigne à son auteur (``assigne_a`` et
``pris_en_charge_par``) et la passe « en cours » ; « Résoudre » exige un commentaire
d'action menée et la classe « résolue ».
"""

from __future__ import annotations

from datetime import date, timedelta

from app.bd.connexion import transaction
from app.bd.depots.alertes import DepotAlertes
from app.bd.depots.kpi import DepotKpi
from app.bd.depots.plans import DepotPlansCharge
from app.contexte import Contexte
from app.erreurs import DonneesInvalides, OperationImpossible
from app.journal import journal
from app.services.droits import a_le_droit, verifier_droit, verifier_site
from app.services.planification import adequation_ligne
from app.utils.dates import lundi_de
from app.utils.format_fr import formater_date, formater_pourcentage

_log = journal(__name__)

#: Sous-effectif et pénurie d'équipements : J+1/J+2 rouge, J+3 à J+7 orange (docs/plan.md, Q4).
HORIZON_SOUS_EFFECTIF = 7
#: Sureffectif : le prompt ne fixe pas d'horizon ; J+1 à J+14 (docs/plan.md, Q4), un seul
#: niveau (orange) — un excédent de personnel est un enjeu de coût, pas de service.
HORIZON_SUREFFECTIF = 14
SEUIL_ADEQUATION_BASSE = 95.0
SEUIL_ADEQUATION_HAUTE = 105.0


def compter_alertes_ouvertes(ctx: Contexte) -> int:
    """Nombre d'alertes non résolues visibles (compteur du menu « Alertes »)."""
    if not a_le_droit(ctx, "lecture_alertes"):
        return 0
    sites = None if ctx.voit_tous_les_sites else sorted(ctx.sites)
    with transaction() as cur:
        return DepotAlertes(cur).compter_ouvertes(sites)


def lister_alertes_ouvertes(
    ctx: Contexte, site_id: int, type_alerte: str | None = None
) -> list[dict]:
    """Alertes ouvertes ou en cours d'un site (bandeau de dérive de l'écran Modèles, UC21)."""
    if not a_le_droit(ctx, "lecture_alertes") or not ctx.peut_voir_site(site_id):
        return []
    with transaction() as cur:
        return DepotAlertes(cur).ouvertes(site_id, type_alerte)


def lister_alertes(
    ctx: Contexte, site_id: int, statut: str | None = None, type_alerte: str | None = None
) -> list[dict]:
    """Toutes les alertes d'un site, résolues comprises (écran Alertes)."""
    verifier_droit(ctx, "lecture_alertes")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        return DepotAlertes(cur).lister(site_id, statut, type_alerte)


# =====================================================================
# UC18 · Émettre une alerte
# =====================================================================
def _niveau_horizon_court(decalage_jours: int) -> str:
    """J+1/J+2 : rouge ; au-delà (jusqu'à ``HORIZON_SOUS_EFFECTIF``) : orange."""
    return "rouge" if decalage_jours <= 2 else "orange"


def _detecter_sous_effectif(
    depot_alertes: DepotAlertes, site_id: int, lignes: list[dict], aujourdhui: date
) -> list[dict]:
    alertes = []
    for ligne in lignes:
        decalage = (ligne["date_jour"] - aujourdhui).days
        if not (1 <= decalage <= HORIZON_SOUS_EFFECTIF):
            continue
        adequation = adequation_ligne(ligne)
        if adequation is None or adequation >= SEUIL_ADEQUATION_BASSE:
            continue
        niveau = _niveau_horizon_court(decalage)
        message = (
            f"Sous-effectif prévu en zone « {ligne['zone']} » le {formater_date(ligne['date_jour'])} "
            f"({formater_pourcentage(adequation, 0)} du besoin planifié)."
        )
        alerte_id = depot_alertes.emettre(
            "sous_effectif",
            niveau,
            None,
            site_id,
            ligne["zone_id"],
            ligne["date_jour"],
            f"sous_effectif_{site_id}_{ligne['zone_id']}_{ligne['date_jour'].isoformat()}",
            message,
        )
        alertes.append(_resume_alerte(alerte_id, "sous_effectif", niveau, ligne))
    return alertes


def _detecter_sureffectif(
    depot_alertes: DepotAlertes, site_id: int, lignes: list[dict], aujourdhui: date
) -> list[dict]:
    alertes = []
    for ligne in lignes:
        decalage = (ligne["date_jour"] - aujourdhui).days
        if not (1 <= decalage <= HORIZON_SUREFFECTIF):
            continue
        adequation = adequation_ligne(ligne)
        if adequation is None or adequation <= SEUIL_ADEQUATION_HAUTE:
            continue
        detail = (
            "aucun besoin n'est prévu, mais du personnel reste planifié"
            if ligne["besoin_effectif"] <= 0
            else f"{formater_pourcentage(adequation, 0)} du besoin planifié"
        )
        message = (
            f"Sureffectif prévu en zone « {ligne['zone']} » le {formater_date(ligne['date_jour'])} "
            f"({detail})."
        )
        alerte_id = depot_alertes.emettre(
            "sureffectif",
            "orange",
            None,
            site_id,
            ligne["zone_id"],
            ligne["date_jour"],
            f"sureffectif_{site_id}_{ligne['zone_id']}_{ligne['date_jour'].isoformat()}",
            message,
        )
        alertes.append(_resume_alerte(alerte_id, "sureffectif", "orange", ligne))
    return alertes


def _penurie_equipement(ligne: dict) -> bool:
    """Le besoin en équipements dépasse la capacité disponible du jour (KPI JOURS_PENURIE)."""
    return ligne["besoin_equipements"] > ligne["capacite_equipements"]


def _detecter_penurie_equipement(
    depot_alertes: DepotAlertes, site_id: int, lignes: list[dict], aujourdhui: date
) -> list[dict]:
    alertes = []
    for ligne in lignes:
        decalage = (ligne["date_jour"] - aujourdhui).days
        if not (1 <= decalage <= HORIZON_SOUS_EFFECTIF):
            continue
        if not _penurie_equipement(ligne):
            continue
        niveau = _niveau_horizon_court(decalage)
        message = (
            f"Pénurie d'équipements prévue en zone « {ligne['zone']} » le "
            f"{formater_date(ligne['date_jour'])} : {ligne['besoin_equipements']} nécessaire(s) "
            f"pour {ligne['capacite_equipements']} disponible(s)."
        )
        alerte_id = depot_alertes.emettre(
            "penurie_equipement",
            niveau,
            None,
            site_id,
            ligne["zone_id"],
            ligne["date_jour"],
            f"penurie_equipement_{site_id}_{ligne['zone_id']}_{ligne['date_jour'].isoformat()}",
            message,
        )
        alertes.append(_resume_alerte(alerte_id, "penurie_equipement", niveau, ligne))
    return alertes


def _resume_alerte(alerte_id: int, type_alerte: str, niveau: str, ligne: dict) -> dict:
    return {
        "alerte_id": alerte_id,
        "type": type_alerte,
        "niveau": niveau,
        "zone_id": ligne["zone_id"],
        "zone": ligne["zone"],
        "date_jour": ligne["date_jour"],
    }


def _detecter_seuil_kpi(
    depot_alertes: DepotAlertes, depot_kpi: DepotKpi, site_id: int, aujourdhui: date
) -> list[dict]:
    """KPI généraux (toutes zones) de la semaine en cours dont le statut est orange ou rouge."""
    debut_semaine = lundi_de(aujourdhui)
    valeurs = depot_kpi.valeurs(site_id, None, "semaine", debut_semaine)
    alertes = []
    for valeur in valeurs:
        if valeur["statut"] not in ("orange", "rouge"):
            continue
        message = (
            f"« {valeur['kpi_libelle']} » {valeur['statut']} cette semaine : "
            f"{valeur['valeur']:.2f} {valeur['unite']} (cible {valeur['cible']:.2f})."
            if valeur["valeur"] is not None and valeur["cible"] is not None
            else f"« {valeur['kpi_libelle']} » {valeur['statut']} cette semaine."
        )
        alerte_id = depot_alertes.emettre(
            "seuil_kpi",
            valeur["statut"],
            valeur["kpi_id"],
            site_id,
            None,
            debut_semaine,
            f"seuil_kpi_{site_id}_{valeur['kpi_id']}_{valeur['methode'] or ''}",
            message,
        )
        alertes.append(
            {
                "alerte_id": alerte_id,
                "type": "seuil_kpi",
                "niveau": valeur["statut"],
                "kpi_code": valeur["kpi_code"],
            }
        )
    return alertes


def emettre_alertes(ctx: Contexte, site_id: int, date_reference: date | None = None) -> list[dict]:
    """UC18 : détecte, sur le plan de charge validé et les KPI déjà calculés, les situations de
    sous-effectif, de sureffectif, de pénurie d'équipements et de dépassement de seuil de KPI,
    et émet ou met à jour les alertes correspondantes."""
    verifier_droit(ctx, "UC18")
    verifier_site(ctx, site_id)
    aujourdhui = date_reference or date.today()
    horizon_max = max(HORIZON_SOUS_EFFECTIF, HORIZON_SUREFFECTIF)

    with transaction() as cur:
        depot_plans = DepotPlansCharge(cur)
        depot_kpi = DepotKpi(cur)
        depot_alertes = DepotAlertes(cur)
        lignes = depot_plans.lignes_validees_periode(
            site_id, None, aujourdhui + timedelta(days=1), aujourdhui + timedelta(days=horizon_max)
        )
        alertes = [
            *_detecter_sous_effectif(depot_alertes, site_id, lignes, aujourdhui),
            *_detecter_sureffectif(depot_alertes, site_id, lignes, aujourdhui),
            *_detecter_penurie_equipement(depot_alertes, site_id, lignes, aujourdhui),
            *_detecter_seuil_kpi(depot_alertes, depot_kpi, site_id, aujourdhui),
        ]
    _log.info(
        "Alertes émises par %s (site %s) : %s alerte(s) créée(s) ou confirmée(s).",
        ctx.identifiant,
        site_id,
        len(alertes),
    )
    return alertes


# =====================================================================
# UC19 · Traiter une alerte
# =====================================================================
def prendre_en_charge(ctx: Contexte, alerte_id: int) -> None:
    """UC19 : assigne l'alerte à son auteur et la passe « en cours »."""
    verifier_droit(ctx, "UC19")
    with transaction() as cur:
        depot = DepotAlertes(cur)
        alerte = depot.alerte(alerte_id)
        if alerte is None:
            raise OperationImpossible("Alerte introuvable.")
        verifier_site(ctx, alerte["site_id"])
        if alerte["statut"] == "resolue":
            raise OperationImpossible("Cette alerte est déjà résolue.")
        depot.prendre_en_charge(alerte_id, ctx.utilisateur_id)
    _log.info("Alerte n° %s prise en charge par %s.", alerte_id, ctx.identifiant)


def resoudre_alerte(ctx: Contexte, alerte_id: int, action_menee: str) -> None:
    """UC19 : clôture l'alerte avec l'action menée (obligatoire)."""
    verifier_droit(ctx, "UC19")
    if not action_menee or not action_menee.strip():
        raise DonneesInvalides(
            "L'action menée est obligatoire pour résoudre une alerte.",
            {"action_menee": "Décrivez l'action menée."},
        )
    with transaction() as cur:
        depot = DepotAlertes(cur)
        alerte = depot.alerte(alerte_id)
        if alerte is None:
            raise OperationImpossible("Alerte introuvable.")
        verifier_site(ctx, alerte["site_id"])
        if alerte["statut"] == "resolue":
            raise OperationImpossible("Cette alerte est déjà résolue.")
        depot.resoudre(alerte_id, ctx.utilisateur_id, action_menee.strip())
    _log.info("Alerte n° %s résolue par %s.", alerte_id, ctx.identifiant)
