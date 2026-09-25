"""UC15 · Définir les cibles et seuils des KPI — UC16 · Calculer les KPI (inclus dans UC17) —
UC17 · Comparer les KPI aux cibles.

Les formules et les règles de statut suivent exactement le tableau du prompt (``<kpi>``) :
pour tous les taux, le rapport des sommes sur la période (pas la moyenne des rapports), le
MAPE exclut les jours où le réel vaut 0, et les heures nécessaires réelles valent les heures
travaillées moins les heures inactives.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date

from app.bd.connexion import transaction
from app.bd.depots.comparaisons import DepotComparaisons
from app.bd.depots.historique import DepotHistorique
from app.bd.depots.kpi import DepotKpi
from app.bd.depots.modeles import DepotModeles
from app.bd.depots.plans import DepotPlansCharge
from app.bd.depots.previsions_ressources import DepotPrevisionsRessources
from app.bd.depots.referentiels import DepotReferentiels
from app.contexte import Contexte
from app.erreurs import DonneesInvalides, OperationImpossible
from app.journal import journal
from app.ml.entrainement import METHODES
from app.services.droits import verifier_droit, verifier_site
from app.utils import validation
from app.utils.dates import bornes_periode

_log = journal(__name__)

NB_JOURS_CIBLE_RELATIVE = 90
CODES_CIBLE_RELATIVE = ("PRODUCTIVITE", "COUT_UNITE")


# =====================================================================
# Règles de statut
# =====================================================================
def statut_baisse(valeur: float, seuil_orange: float, seuil_rouge: float) -> str:
    if valeur <= seuil_orange:
        return "vert"
    if valeur <= seuil_rouge:
        return "orange"
    return "rouge"


def statut_hausse(valeur: float, seuil_orange: float, seuil_rouge: float) -> str:
    if valeur >= seuil_orange:
        return "vert"
    if valeur >= seuil_rouge:
        return "orange"
    return "rouge"


def statut_plage(valeur: float, valeur_min: float, valeur_max: float, marge: float) -> str:
    if valeur_min <= valeur <= valeur_max:
        return "vert"
    ecart = (valeur_min - valeur) if valeur < valeur_min else (valeur - valeur_max)
    return "orange" if ecart <= marge else "rouge"


def calculer_statut(sens: str, valeur: float | None, objectif: dict | None) -> str:
    """Statut d'une valeur de KPI : ``"gris"`` sans valeur, sans objectif ou pour un KPI
    d'information."""
    if valeur is None or objectif is None or sens == "information":
        return "gris"
    if sens == "baisse":
        return statut_baisse(valeur, objectif["seuil_orange"], objectif["seuil_rouge"])
    if sens == "hausse":
        return statut_hausse(valeur, objectif["seuil_orange"], objectif["seuil_rouge"])
    if sens == "plage":
        return statut_plage(
            valeur, objectif["valeur_min"], objectif["valeur_max"], objectif["seuil_orange"]
        )
    return "gris"


# =====================================================================
# Formules de précision (à partir des rapprochements réel / prévu, UC20)
# =====================================================================
def _comparables(rapprochements: list[dict]) -> list[dict]:
    return [r for r in rapprochements if r["comparable"] and r["heures_reelles"] is not None]


def calculer_mae(rapprochements: list[dict]) -> float | None:
    """Moyenne de |réel − prévu| (heures)."""
    paires = _comparables(rapprochements)
    if not paires:
        return None
    return statistics.mean(abs(r["heures_reelles"] - r["heures_prevues"]) for r in paires)


def calculer_rmse(rapprochements: list[dict]) -> float | None:
    """√moyenne((réel − prévu)²)."""
    paires = _comparables(rapprochements)
    if not paires:
        return None
    return math.sqrt(
        statistics.mean((r["heures_reelles"] - r["heures_prevues"]) ** 2 for r in paires)
    )


def calculer_mape(rapprochements: list[dict]) -> float | None:
    """Moyenne de |réel − prévu| / réel, en % (les jours à réel nul sont exclus)."""
    paires = [r for r in _comparables(rapprochements) if r["heures_reelles"]]
    if not paires:
        return None
    return (
        statistics.mean(
            abs(r["heures_reelles"] - r["heures_prevues"]) / r["heures_reelles"] for r in paires
        )
        * 100
    )


def calculer_biais(rapprochements: list[dict]) -> float | None:
    """Σ(prévu − réel) / Σréel, en %."""
    paires = _comparables(rapprochements)
    somme_reel = sum(r["heures_reelles"] for r in paires)
    if not paires or not somme_reel:
        return None
    return sum(r["heures_prevues"] - r["heures_reelles"] for r in paires) / somme_reel * 100


def calculer_couverture_ic(rapprochements: list[dict]) -> float | None:
    """Part des réels compris dans [ic_bas ; ic_haut], en %."""
    paires = _comparables(rapprochements)
    if not paires:
        return None
    dans = sum(1 for r in paires if r["ic_bas"] <= r["heures_reelles"] <= r["ic_haut"])
    return dans / len(paires) * 100


def calculer_ecart_equipements(rapprochements: list[dict]) -> float | None:
    """Moyenne de |équipements réels − prévus|."""
    paires = [r for r in _comparables(rapprochements) if r["equipements_reels"] is not None]
    if not paires:
        return None
    return statistics.mean(abs(r["equipements_reels"] - r["equipements_prevus"]) for r in paires)


def calculer_taux_victoire(
    rapprochements: list[dict], rapprochements_autre: list[dict]
) -> float | None:
    """Part des jours où cette méthode a l'erreur absolue la plus faible (égalité non comptée)."""
    autre_par_date = {r["date_jour"]: r for r in _comparables(rapprochements_autre)}
    communs = [r for r in _comparables(rapprochements) if r["date_jour"] in autre_par_date]
    if not communs:
        return None
    victoires = 0
    for r in communs:
        erreur = abs(r["heures_reelles"] - r["heures_prevues"])
        autre = autre_par_date[r["date_jour"]]
        erreur_autre = abs(autre["heures_reelles"] - autre["heures_prevues"])
        if erreur < erreur_autre:
            victoires += 1
    return victoires / len(communs) * 100


# =====================================================================
# Formules RH, équipements, coûts et service (à partir des sommes de l'historique)
# =====================================================================
def _ratio(numerateur: float, denominateur: float, pourcentage: bool = True) -> float | None:
    if not denominateur:
        return None
    return numerateur / denominateur * (100 if pourcentage else 1)


def calculer_productivite(sommes: dict) -> float | None:
    return _ratio(sommes["volume"], sommes["heures_travaillees"], pourcentage=False)


def calculer_adequation(sommes: dict, heures_planifiees: float) -> float | None:
    return _ratio(heures_planifiees, sommes["heures_necessaires"])


def calculer_taux_hs(sommes: dict) -> float | None:
    return _ratio(sommes["heures_sup"], sommes["heures_travaillees"])


def calculer_taux_interim(sommes: dict) -> float | None:
    return _ratio(sommes["heures_interim"], sommes["heures_travaillees"])


def calculer_taux_sous_charge(sommes: dict) -> float | None:
    return _ratio(sommes["heures_inactives"], sommes["heures_travaillees"])


def calculer_taux_absenteisme(sommes: dict) -> float | None:
    return _ratio(sommes["heures_absence"], sommes["heures_travaillees"] + sommes["heures_absence"])


def calculer_delai_anticipation(alertes_sous_effectif: list[dict]) -> float | None:
    """Moyenne de (date concernée − date de création) des alertes de sous-effectif, en jours."""
    if not alertes_sous_effectif:
        return None
    return statistics.mean(
        (a["date_concernee"] - a["date_creation"].date()).days for a in alertes_sous_effectif
    )


def calculer_taux_util_eqp(sommes: dict) -> float | None:
    return _ratio(sommes["heures_usage_equipement"], sommes["heures_disponibles_equipement"])


def calculer_taux_dispo_eqp(sommes: dict) -> float | None:
    total = sommes["heures_disponibles_equipement"] + sommes["heures_panne_equipement"]
    if not total:
        return None
    return (1 - sommes["heures_panne_equipement"] / total) * 100


def calculer_cout_unite(sommes: dict) -> float | None:
    return _ratio(sommes["cout_rh"], sommes["volume"], pourcentage=False)


def calculer_ecart_cout(sommes: dict, cout_planifie: float) -> float | None:
    if not cout_planifie:
        return None
    return _ratio(sommes["cout_rh"] - cout_planifie, cout_planifie)


def calculer_taux_a_temps(sommes: dict) -> float | None:
    return _ratio(sommes["commandes_a_temps"], sommes["commandes_totales"])


def _autre_methode(methode: str) -> str:
    return next(m for m in METHODES if m != methode)


# =====================================================================
# UC16 · Calculer les KPI (inclus dans UC17)
# =====================================================================
@dataclass
class ContexteCalculKpi:
    """Toutes les données déjà agrégées, pour ne calculer chaque somme qu'une seule fois."""

    sommes: dict
    rapprochements: dict[str, list[dict]]
    heures_planifiees: float
    cout_planifie: float
    jours_penurie: int
    alertes_sous_effectif: list[dict] = field(default_factory=list)


def _construire_contexte(
    cur, site_id: int, zone_id: int | None, debut: date, fin: date
) -> ContexteCalculKpi:
    depot_hist = DepotHistorique(cur)
    depot_comp = DepotComparaisons(cur)
    depot_plans = DepotPlansCharge(cur)
    ref = DepotReferentiels(cur)

    sommes = depot_hist.sommes_periode(site_id, zone_id, debut, fin)
    rapprochements = {
        methode: depot_comp.rapprochements(site_id, zone_id, debut, fin, methode)
        for methode in METHODES
    }
    heures_planifiees = depot_plans.heures_planifiees_periode(site_id, zone_id, debut, fin)
    couts = ref.couts_en_vigueur(fin)
    cout_planifie = depot_plans.cout_planifie_periode(
        site_id, zone_id, debut, fin, couts.get("interne", 0.0), couts.get("interim", 0.0)
    )
    jours_penurie = _calculer_jours_penurie(cur, site_id, zone_id, debut, fin)
    return ContexteCalculKpi(
        sommes, rapprochements, heures_planifiees, cout_planifie, jours_penurie
    )


def _calculer_jours_penurie(cur, site_id: int, zone_id: int | None, debut: date, fin: date) -> int:
    """Jours où les équipements nécessaires (méthode retenue) dépassent les disponibles."""
    ref = DepotReferentiels(cur)
    depot_modeles = DepotModeles(cur)
    depot_previsions = DepotPrevisionsRessources(cur)
    zones = [
        z
        for z in ref.lister_zones(site_id, inclure_inactives=True)
        if zone_id is None or z["id"] == zone_id
    ]
    disponibilites: dict[tuple, int] = {}
    for ligne in ref.equipements_disponibles(site_id, debut, fin):
        if ligne["type"] is not None:
            disponibilites[(ligne["zone_id"], ligne["date_jour"], ligne["type"])] = ligne[
                "disponibles"
            ]

    jours_en_penurie: set[tuple] = set()
    for zone in zones:
        retenue = depot_modeles.version_retenue_pour_plan(site_id, zone["id"], "heures")
        if retenue is None:
            continue
        previsions = depot_previsions.dernieres(site_id, zone["id"], debut, fin, retenue["methode"])
        for prevision in previsions:
            dispo = disponibilites.get(
                (zone["id"], prevision["date_jour"], zone["type_equipement_principal"]), 0
            )
            if prevision["equipements"] > dispo:
                jours_en_penurie.add((zone["id"], prevision["date_jour"]))
    return len(jours_en_penurie)


def _resoudre_objectif(
    objectif: dict | None, code: str, sommes_90j: tuple[float, float, float]
) -> dict | None:
    """Pour PRODUCTIVITE et COUT_UNITE (cibles relatives), transforme les seuils en % en
    valeurs absolues à partir de la cible calculée sur les 90 premiers jours d'historique."""
    if objectif is None or not objectif["seuils_relatifs"]:
        return objectif
    volume_90j, heures_90j, cout_90j = sommes_90j
    if code == "PRODUCTIVITE":
        cible = _ratio(volume_90j, heures_90j, pourcentage=False)
    elif code == "COUT_UNITE":
        cible = _ratio(cout_90j, volume_90j, pourcentage=False)
    else:  # pragma: no cover - aucun autre code n'est relatif aujourd'hui
        cible = None
    if cible is None:
        return None
    return {
        **objectif,
        "valeur_cible": cible,
        "seuil_orange": cible * objectif["seuil_orange"] / 100,
        "seuil_rouge": cible * objectif["seuil_rouge"] / 100,
    }


CALCULATEURS_SANS_METHODE = {
    "PRODUCTIVITE": lambda c: calculer_productivite(c.sommes),
    "ADEQUATION": lambda c: calculer_adequation(c.sommes, c.heures_planifiees),
    "TAUX_HS": lambda c: calculer_taux_hs(c.sommes),
    "TAUX_INTERIM": lambda c: calculer_taux_interim(c.sommes),
    "TAUX_SOUS_CHARGE": lambda c: calculer_taux_sous_charge(c.sommes),
    "TAUX_ABSENTEISME": lambda c: calculer_taux_absenteisme(c.sommes),
    "DELAI_ANTICIPATION": lambda c: calculer_delai_anticipation(c.alertes_sous_effectif),
    "TAUX_UTIL_EQP": lambda c: calculer_taux_util_eqp(c.sommes),
    "TAUX_DISPO_EQP": lambda c: calculer_taux_dispo_eqp(c.sommes),
    "JOURS_PENURIE": lambda c: float(c.jours_penurie),
    "COUT_UNITE": lambda c: calculer_cout_unite(c.sommes),
    "ECART_COUT": lambda c: calculer_ecart_cout(c.sommes, c.cout_planifie),
    "TAUX_A_TEMPS": lambda c: calculer_taux_a_temps(c.sommes),
}

CALCULATEURS_PAR_METHODE = {
    "MAE_H": lambda c, m: calculer_mae(c.rapprochements[m]),
    "RMSE_H": lambda c, m: calculer_rmse(c.rapprochements[m]),
    "MAPE_H": lambda c, m: calculer_mape(c.rapprochements[m]),
    "BIAIS_H": lambda c, m: calculer_biais(c.rapprochements[m]),
    "COUV_IC": lambda c, m: calculer_couverture_ic(c.rapprochements[m]),
    "ECART_EQP": lambda c, m: calculer_ecart_equipements(c.rapprochements[m]),
    "TAUX_VICTOIRE": lambda c, m: calculer_taux_victoire(
        c.rapprochements[m], c.rapprochements[_autre_methode(m)]
    ),
}


def _valeur_kpi(contexte: ContexteCalculKpi, kpi: dict, methode: str | None) -> float | None:
    if kpi["par_methode"]:
        return CALCULATEURS_PAR_METHODE[kpi["code"]](contexte, methode)
    return CALCULATEURS_SANS_METHODE[kpi["code"]](contexte)


def _calculer(
    cur,
    site_id: int,
    zone_id: int | None,
    periodicite: str,
    date_reference: date,
    avec_statut: bool,
) -> list[dict]:
    debut, _fin = bornes_periode(date_reference, periodicite)
    contexte = _construire_contexte(cur, site_id, zone_id, debut, _fin)
    depot_kpi = DepotKpi(cur)
    depot_hist = DepotHistorique(cur)
    sommes_90j = depot_hist.sommes_premiers_jours(site_id, zone_id, NB_JOURS_CIBLE_RELATIVE)

    resultats = []
    for kpi in depot_kpi.definitions():
        for methode in (METHODES if kpi["par_methode"] else (None,)):
            valeur = _valeur_kpi(contexte, kpi, methode)
            cible = statut = None
            if avec_statut:
                objectif = depot_kpi.objectif_applicable(
                    kpi["id"], site_id, zone_id, periodicite, debut
                )
                objectif = _resoudre_objectif(objectif, kpi["code"], sommes_90j)
                cible = objectif["valeur_cible"] if objectif else None
                statut = calculer_statut(kpi["sens"], valeur, objectif)
            depot_kpi.upsert_valeur(
                kpi["id"],
                site_id,
                zone_id,
                periodicite,
                debut,
                methode,
                valeur,
                cible,
                statut or "gris",
            )
            resultats.append(
                {
                    "kpi_code": kpi["code"],
                    "kpi_libelle": kpi["libelle"],
                    "famille": kpi["famille"],
                    "sens": kpi["sens"],
                    "unite": kpi["unite"],
                    "methode": methode,
                    "valeur": valeur,
                    "cible": cible,
                    "statut": statut or "gris",
                }
            )
    return resultats


def calculer_kpi(
    ctx: Contexte,
    site_id: int,
    zone_id: int | None,
    periodicite: str,
    date_reference: date | None = None,
) -> list[dict]:
    """UC16 : calcule et stocke la valeur de chaque KPI pour la période (sans statut)."""
    verifier_droit(ctx, "UC16")
    verifier_site(ctx, site_id)
    date_reference = date_reference or date.today()
    with transaction() as cur:
        resultats = _calculer(cur, site_id, zone_id, periodicite, date_reference, avec_statut=False)
    _log.info("KPI calculés par %s (site %s, %s).", ctx.identifiant, site_id, periodicite)
    return resultats


def comparer_kpi_cibles(
    ctx: Contexte,
    site_id: int,
    zone_id: int | None,
    periodicite: str,
    date_reference: date | None = None,
) -> list[dict]:
    """UC17 (inclut UC16) : calcule les KPI puis les compare à leurs objectifs (statut)."""
    verifier_droit(ctx, "UC17")
    verifier_site(ctx, site_id)
    date_reference = date_reference or date.today()
    with transaction() as cur:
        resultats = _calculer(cur, site_id, zone_id, periodicite, date_reference, avec_statut=True)
    _log.info(
        "KPI comparés aux cibles par %s (site %s, %s).", ctx.identifiant, site_id, periodicite
    )
    return resultats


def lister_kpi_valeurs(
    ctx: Contexte, site_id: int, zone_id: int | None, periodicite: str, date_reference: date
) -> list[dict]:
    """Dernières valeurs déjà calculées pour une période (écran KPI et cibles)."""
    verifier_droit(ctx, "lecture_referentiels")
    verifier_site(ctx, site_id)
    debut, _fin = bornes_periode(date_reference, periodicite)
    with transaction() as cur:
        depot = DepotKpi(cur)
        valeurs = depot.valeurs(site_id, zone_id, periodicite, debut)
        for valeur in valeurs:
            precedentes = depot.historique_valeur(
                valeur["kpi_id"], site_id, zone_id, periodicite, valeur["methode"], nb_periodes=2
            )
            valeur["tendance"] = _tendance(precedentes)
    return valeurs


def _tendance(precedentes: list[dict]) -> str:
    """↑ / ↓ / → par rapport à la période précédente (selon le sens du KPI)."""
    if len(precedentes) < 2 or precedentes[0]["valeur"] is None or precedentes[1]["valeur"] is None:
        return "→"
    actuelle, avant = precedentes[0]["valeur"], precedentes[1]["valeur"]
    if actuelle == avant:
        return "→"
    hausse = actuelle > avant
    if precedentes[0]["sens"] == "baisse":
        hausse = not hausse
    return "↑" if hausse else "↓"


# =====================================================================
# UC15 · Définir les cibles et seuils des KPI
# =====================================================================
def lister_definitions(ctx: Contexte) -> list[dict]:
    """Catalogue des 20 KPI (écran KPI et cibles : filtre par famille, sélecteur de cible)."""
    verifier_droit(ctx, "lecture_referentiels")
    with transaction() as cur:
        return DepotKpi(cur).definitions()


def lister_objectifs(ctx: Contexte, site_id: int | None = None) -> list[dict]:
    verifier_droit(ctx, "UC15")
    with transaction() as cur:
        return DepotKpi(cur).objectifs(site_id)


def _valider_objectif(sens: str, configuration: dict) -> dict:
    erreurs: dict[str, str] = {}
    resultat: dict = {"seuils_relatifs": bool(configuration.get("seuils_relatifs"))}
    champs_communs = {
        "valeur_cible": ("Valeur cible", False),
        "seuil_orange": ("Seuil orange", sens in ("baisse", "hausse", "plage")),
        "seuil_rouge": ("Seuil rouge", sens in ("baisse", "hausse")),
        "valeur_min": ("Valeur minimum", sens == "plage"),
        "valeur_max": ("Valeur maximum", sens == "plage"),
    }
    for champ, (libelle, obligatoire) in champs_communs.items():
        brut = configuration.get(champ)
        if brut in (None, "") and not obligatoire:
            resultat[champ] = None
            continue
        try:
            resultat[champ] = validation.nombre(brut, libelle, minimum=None)
        except ValueError as exc:
            erreurs[champ] = str(exc)
    if sens == "plage" and "valeur_min" not in erreurs and "valeur_max" not in erreurs:
        if (
            resultat["valeur_min"] is not None
            and resultat["valeur_max"] is not None
            and resultat["valeur_min"] > resultat["valeur_max"]
        ):
            erreurs["valeur_min"] = "Le minimum doit être inférieur ou égal au maximum."
    if erreurs:
        raise DonneesInvalides("Certains seuils sont invalides.", erreurs)
    return resultat


def definir_objectif(
    ctx: Contexte,
    kpi_id: int,
    site_id: int | None,
    zone_id: int | None,
    periodicite: str,
    configuration: dict,
    objectif_id: int | None = None,
) -> int:
    """UC15 : crée ou modifie un objectif (ajouter/modifier une cible)."""
    verifier_droit(ctx, "UC15")
    if site_id is not None:
        verifier_site(ctx, site_id)
    if zone_id is not None and site_id is None:
        raise DonneesInvalides(
            "Une cible par zone doit préciser le site.", {"zone_id": "Choisissez d'abord un site."}
        )
    with transaction() as cur:
        depot = DepotKpi(cur)
        kpi = depot.definition(kpi_id)
        if kpi is None:
            raise OperationImpossible("KPI introuvable.")
        if kpi["sens"] == "information":
            raise OperationImpossible(
                f"« {kpi['libelle']} » est un KPI d'information : il n'a pas d'objectif."
            )
        donnees = _valider_objectif(kpi["sens"], configuration)
        if objectif_id is None:
            objectif_id = depot.creer_objectif(
                kpi_id,
                site_id,
                zone_id,
                periodicite,
                kpi["sens"],
                donnees["valeur_cible"],
                donnees["seuil_orange"],
                donnees["seuil_rouge"],
                donnees["valeur_min"],
                donnees["valeur_max"],
                donnees["seuils_relatifs"],
                date.today(),
            )
        else:
            depot.modifier_objectif(
                objectif_id,
                donnees["valeur_cible"],
                donnees["seuil_orange"],
                donnees["seuil_rouge"],
                donnees["valeur_min"],
                donnees["valeur_max"],
            )
    _log.info("Objectif KPI n° %s enregistré par %s.", objectif_id, ctx.identifiant)
    return objectif_id


def supprimer_objectif(ctx: Contexte, objectif_id: int) -> None:
    """UC15 : supprime une cible."""
    verifier_droit(ctx, "UC15")
    with transaction() as cur:
        depot = DepotKpi(cur)
        if depot.objectif(objectif_id) is None:
            raise OperationImpossible("Objectif introuvable.")
        depot.supprimer_objectif(objectif_id)
    _log.info("Objectif KPI n° %s supprimé par %s.", objectif_id, ctx.identifiant)
