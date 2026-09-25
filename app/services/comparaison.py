"""UC20 · Comparer le réalisé aux prévisions RL et RN — UC21 · Détecter une dérive de modèle."""

from __future__ import annotations

from datetime import date, timedelta

from app.bd.connexion import transaction
from app.bd.depots.alertes import DepotAlertes
from app.bd.depots.comparaisons import DepotComparaisons
from app.bd.depots.kpi import DepotKpi
from app.bd.depots.modeles import DepotModeles
from app.bd.depots.parametres_modele import DepotParametresModele
from app.bd.depots.referentiels import DepotReferentiels
from app.contexte import Contexte
from app.journal import journal
from app.ml.entrainement import LIBELLES_METHODES, METHODES
from app.services.droits import verifier_droit, verifier_site
from app.services.kpi import calculer_mape
from app.services.modeles import DEFAUT_PARAMETRES
from app.utils.dates import decaler_periode

_log = journal(__name__)


def _seuil_derive_mape(cur) -> float:
    """Seuil de MAPE hebdomadaire au-delà duquel un modèle est en dérive (UC07, 10 % par
    défaut — Q8 du plan). Lecture directe du dépôt : UC07 est réservé à l'administrateur,
    mais UC21 doit pouvoir lire la valeur en vigueur quel que soit le rôle appelant."""
    dernier = DepotParametresModele(cur).dernier()
    configuration = (
        {**DEFAUT_PARAMETRES, **dernier["configuration"]} if dernier else DEFAUT_PARAMETRES
    )
    return configuration["seuil_derive_mape"]


def _calculer_ecarts(r: dict) -> dict:
    """Écarts d'un rapprochement (UC20) : absolu et relatif en heures, écart d'équipements,
    appartenance à l'intervalle de confiance. ``None`` pour un jour non comparable (pas encore
    de réel connu)."""
    ecart_absolu = ecart_relatif = dans_ic = ecart_equipements = None
    if r["comparable"] and r["heures_reelles"] is not None:
        ecart_absolu = abs(r["heures_reelles"] - r["heures_prevues"])
        if r["heures_reelles"]:
            ecart_relatif = (r["heures_prevues"] - r["heures_reelles"]) / r["heures_reelles"] * 100
        dans_ic = r["ic_bas"] <= r["heures_reelles"] <= r["ic_haut"]
        if r["equipements_reels"] is not None:
            ecart_equipements = abs(r["equipements_reels"] - r["equipements_prevus"])
    return {
        "ecart_absolu": ecart_absolu,
        "ecart_relatif": ecart_relatif,
        "ecart_equipements": ecart_equipements,
        "dans_ic": dans_ic,
    }


# =====================================================================
# UC20 · Comparer le réalisé aux prévisions RL et RN
# =====================================================================
def comparer_realise(
    ctx: Contexte,
    site_id: int,
    zone_id: int | None = None,
    debut: date | None = None,
    fin: date | None = None,
) -> dict:
    """Rapproche les dernières prévisions de ressources (RL et RN) au réel sur une période
    (hier par défaut, sur 7 jours), et persiste les écarts dans ``comparaisons_realise`` :
    matière première des KPI de précision (MAE, RMSE, MAPE, biais, couverture d'IC, écart
    d'équipements, taux de victoire) et de la détection de dérive (UC21)."""
    verifier_droit(ctx, "UC20")
    verifier_site(ctx, site_id)
    fin = fin or date.today() - timedelta(days=1)
    debut = debut or fin - timedelta(days=6)

    nb_traites = 0
    nb_comparables = 0
    with transaction() as cur:
        depot = DepotComparaisons(cur)
        for methode in METHODES:
            for r in depot.rapprochements(site_id, zone_id, debut, fin, methode):
                ecarts = _calculer_ecarts(r)
                if r["comparable"] and r["heures_reelles"] is not None:
                    nb_comparables += 1
                depot.upsert(
                    r["prevision_id"],
                    r["heures_reelles"],
                    r["equipements_reels"],
                    ecarts["ecart_absolu"],
                    ecarts["ecart_relatif"],
                    ecarts["ecart_equipements"],
                    ecarts["dans_ic"],
                    r["comparable"],
                )
                nb_traites += 1
    _log.info(
        "Réalisé rapproché aux prévisions par %s (site %s, %s → %s) : %s ligne(s), "
        "%s comparable(s).",
        ctx.identifiant,
        site_id,
        debut,
        fin,
        nb_traites,
        nb_comparables,
    )
    return {"nb_traites": nb_traites, "nb_comparables": nb_comparables}


def lister_comparaisons(
    ctx: Contexte,
    site_id: int,
    zone_id: int | None = None,
    debut: date | None = None,
    fin: date | None = None,
    methode: str | None = None,
) -> list[dict]:
    """Rapprochements réel/prévu, RL et RN, avec leurs écarts (écran Comparaison réel/prévu)."""
    verifier_droit(ctx, "lecture_previsions")
    verifier_site(ctx, site_id)
    fin = fin or date.today() - timedelta(days=1)
    debut = debut or fin - timedelta(days=27)
    with transaction() as cur:
        rapprochements = DepotComparaisons(cur).rapprochements(
            site_id, zone_id, debut, fin, methode
        )
    for r in rapprochements:
        r.update(_calculer_ecarts(r))
    return rapprochements


# =====================================================================
# UC21 · Détecter une dérive de modèle
# =====================================================================
def detecter_derive(ctx: Contexte, site_id: int, date_reference: date | None = None) -> list[dict]:
    """Pour chaque zone du site, compare le MAPE hebdomadaire de la méthode retenue pour le
    plan de charge (RL ou RN, ``retenue_pour_plan``) au seuil de dérive : au-delà, une alerte
    « derive_modele » est émise (orange), et confirmée en rouge si la semaine précédente était
    déjà en dérive. Renvoie les alertes émises ou mises à jour."""
    verifier_droit(ctx, "UC21")
    verifier_site(ctx, site_id)
    date_reference = date_reference or date.today()
    semaine_courante = decaler_periode(date_reference, "semaine", -1)
    semaine_precedente = decaler_periode(date_reference, "semaine", -2)

    alertes_emises: list[dict] = []
    with transaction() as cur:
        ref = DepotReferentiels(cur)
        depot_modeles = DepotModeles(cur)
        depot_comp = DepotComparaisons(cur)
        depot_kpi = DepotKpi(cur)
        depot_alertes = DepotAlertes(cur)
        mape_kpi = depot_kpi.definition_par_code("MAPE_H")
        seuil = _seuil_derive_mape(cur)

        for zone in ref.lister_zones(site_id, inclure_inactives=True):
            retenue = depot_modeles.version_retenue_pour_plan(site_id, zone["id"], "heures")
            if retenue is None:
                continue
            methode = retenue["methode"]
            mape_courant = calculer_mape(
                depot_comp.rapprochements(
                    site_id,
                    zone["id"],
                    semaine_courante,
                    semaine_courante + timedelta(days=6),
                    methode,
                )
            )
            if mape_courant is None or mape_courant <= seuil:
                continue
            mape_precedent = calculer_mape(
                depot_comp.rapprochements(
                    site_id,
                    zone["id"],
                    semaine_precedente,
                    semaine_precedente + timedelta(days=6),
                    methode,
                )
            )
            niveau = "rouge" if mape_precedent is not None and mape_precedent > seuil else "orange"
            message = (
                f"Dérive du modèle « {LIBELLES_METHODES[methode]} » retenu pour le plan en zone "
                f"« {zone['nom']} » : MAPE hebdomadaire de {mape_courant:.1f} % "
                f"(seuil {seuil:.0f} %)."
            )
            alerte_id = depot_alertes.emettre(
                "derive_modele",
                niveau,
                mape_kpi["id"] if mape_kpi else None,
                site_id,
                zone["id"],
                semaine_courante,
                f"derive_modele_{site_id}_{zone['id']}_{methode}",
                message,
            )
            alertes_emises.append(
                {
                    "alerte_id": alerte_id,
                    "zone_id": zone["id"],
                    "zone": zone["nom"],
                    "methode": methode,
                    "mape": mape_courant,
                    "niveau": niveau,
                }
            )
    _log.info(
        "Détection de dérive par %s (site %s) : %s alerte(s) émise(s) ou confirmée(s).",
        ctx.identifiant,
        site_id,
        len(alertes_emises),
    )
    return alertes_emises
