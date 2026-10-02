"""Bottom line — ce que Workly apporte (et ce qu'il n'apporte pas) sur une période.

Le calcul compare deux règles de planification face au **même besoin réel** (heures travaillées
moins heures inactives, comme dans le catalogue des KPI) :

* « sans Workly » : le planning de la semaine précédente est reconduit (le réel du même jour de
  la semaine passée) ;
* « avec Workly » : le plan suit la prévision d'heures de la méthode retenue pour le plan.

Pour chaque jour et chaque zone, un plan trop court oblige à couvrir le déficit en heures
supplémentaires ; un plan trop large laisse des heures payées mais inutilisées. Les coûts viennent
des taux horaires (UC03) et des paramètres du bottom line, modifiables par l'administrateur.
Les gains sont donc **simulés**, jamais mesurés : le texte de limites le dit explicitement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.bd.connexion import transaction
from app.bd.depots.bottom_line import DepotBottomLine
from app.bd.depots.parametres import DepotParametres
from app.bd.depots.referentiels import DepotReferentiels
from app.config import configuration
from app.contexte import Contexte
from app.erreurs import DonneesInvalides
from app.journal import journal
from app.services.droits import verifier_droit, verifier_site
from app.utils import validation
from app.utils.format_fr import formater_nombre

_log = journal(__name__)

#: En dessous de ce nombre, une moyenne de délais n'est qu'indicative.
MIN_ECHANTILLON = 5


@dataclass(frozen=True)
class Parametre:
    cle: str
    libelle: str
    unite: str
    defaut: float
    maximum: float
    aide: str


PARAMETRES: tuple[Parametre, ...] = (
    Parametre(
        "bl_penalite_retard",
        "Pénalité par commande en retard",
        "devise",
        20.0,
        1_000_000,
        "Coût d'une commande livrée hors délai (pénalité, geste commercial).",
    ),
    Parametre(
        "bl_sensibilite_retard",
        "Commandes retardées par heure manquante",
        "0 à 1",
        0.5,
        1.0,
        "Part des commandes d'un jour touchée quand tout le besoin manque (0,5 = la moitié).",
    ),
    Parametre(
        "bl_cout_penurie_jour",
        "Coût d'un jour de pénurie d'équipement",
        "devise",
        1500.0,
        10_000_000,
        "Perte estimée quand un équipement manque une journée dans une zone.",
    ),
    Parametre(
        "bl_cout_mise_en_place",
        "Coût de mise en place de Workly",
        "devise",
        0.0,
        1_000_000_000,
        "Investissement initial, pour le retour sur investissement (0 = non renseigné).",
    ),
    Parametre(
        "bl_minutes_manuelles_par_tache",
        "Temps manuel évité par tâche automatique",
        "minutes",
        20.0,
        1440,
        "Temps qu'une personne passerait à faire la tâche à la main.",
    ),
)
_PAR_CLE = {p.cle: p for p in PARAMETRES}


# =====================================================================
# Paramètres
# =====================================================================
def lire_parametres(ctx: Contexte) -> dict[str, float]:
    """Paramètres du bottom line (défauts pour ceux qui n'ont jamais été saisis)."""
    verifier_droit(ctx, "lecture_bottom_line")
    with transaction() as cur:
        return _parametres(DepotParametres(cur))


def _parametres(depot: DepotParametres) -> dict[str, float]:
    valeurs = {}
    for p in PARAMETRES:
        brut = depot.lire(p.cle)
        try:
            valeurs[p.cle] = float(brut) if brut is not None else p.defaut
        except ValueError:
            valeurs[p.cle] = p.defaut
    return valeurs


def enregistrer_parametres(ctx: Contexte, valeurs: dict[str, float | str]) -> int:
    """UC03 · Enregistre les paramètres fournis ; renvoie le nombre de paramètres écrits."""
    verifier_droit(ctx, "UC03")
    retenues, erreurs = {}, {}
    for cle, brut in valeurs.items():
        p = _PAR_CLE.get(cle)
        if p is None:
            continue
        try:
            retenues[cle] = validation.nombre(brut, p.libelle, 0, p.maximum)
        except ValueError as exc:
            erreurs[cle] = str(exc)
    if erreurs:
        raise DonneesInvalides(
            "Certains paramètres sont invalides. Corrigez les champs signalés.", erreurs
        )
    with transaction() as cur:
        depot = DepotParametres(cur)
        for cle, valeur in retenues.items():
            depot.ecrire(cle, repr(float(valeur)))
    _log.info("Paramètres du bottom line enregistrés par %s : %s", ctx.identifiant, retenues)
    return len(retenues)


# =====================================================================
# Simulation « sans / avec Workly » (fonctions pures, testables sans base)
# =====================================================================
def _scenario(jours: list[dict], cle_plan: str, taux: dict[str, float], p: dict) -> dict:
    interne = taux.get("interne", 0.0)
    heures_sup = taux.get("heures_sup", interne)
    manque = surplus = postes = cout_rh = en_retard = commandes = 0.0
    for j in jours:
        besoin, plan = j["besoin"], j[cle_plan]
        deficit, exces = max(0.0, besoin - plan), max(0.0, plan - besoin)
        manque += deficit
        surplus += exces
        postes += (deficit + exces) / (j["duree_poste"] or 1)
        cout_rh += plan * interne + deficit * heures_sup
        commandes += j["commandes_totales"]
        if besoin > 0:
            en_retard += (
                j["commandes_totales"] * min(1.0, deficit / besoin) * p["bl_sensibilite_retard"]
            )
    penalites = en_retard * p["bl_penalite_retard"]
    return {
        "cout_rh": cout_rh,
        "cout_deficit": manque * heures_sup,
        "cout_inactif": surplus * interne,
        "penalites": penalites,
        "cout_total": cout_rh + penalites,
        "heures_sup": manque,
        "heures_inactives": surplus,
        "heures_mal_allouees": manque + surplus,
        "postes_mal_alloues": postes,
        "commandes_en_retard": en_retard,
        "taux_service": (1 - en_retard / commandes) * 100 if commandes else None,
    }


def simuler(jours: list[dict], taux: dict[str, float], parametres: dict[str, float]) -> dict:
    """Scénarios « sans » (planning reconduit) et « avec » (prévision) sur les mêmes jours, et
    gains (positifs = Workly fait mieux)."""
    sans = _scenario(jours, "plan_reconduit", taux, parametres)
    avec = _scenario(jours, "plan_workly", taux, parametres)
    gains = {
        "cout_rh": sans["cout_rh"] - avec["cout_rh"],
        "cout_deficit": sans["cout_deficit"] - avec["cout_deficit"],
        "cout_inactif": sans["cout_inactif"] - avec["cout_inactif"],
        "penalites": sans["penalites"] - avec["penalites"],
        "cout_total": sans["cout_total"] - avec["cout_total"],
        "heures_sup": sans["heures_sup"] - avec["heures_sup"],
        "heures_inactives": sans["heures_inactives"] - avec["heures_inactives"],
        "heures_mal_allouees": sans["heures_mal_allouees"] - avec["heures_mal_allouees"],
        "postes_mal_alloues": sans["postes_mal_alloues"] - avec["postes_mal_alloues"],
        "commandes_en_retard": sans["commandes_en_retard"] - avec["commandes_en_retard"],
        "points_service": (
            avec["taux_service"] - sans["taux_service"]
            if avec["taux_service"] is not None
            else None
        ),
    }
    return {"sans": sans, "avec": avec, "gains": gains, "nb_jours": len(jours)}


def _moyenne(valeurs: list[float]) -> float | None:
    return sum(valeurs) / len(valeurs) if valeurs else None


def analyser_alertes(lignes: list[dict], parametres: dict[str, float]) -> dict:
    """Apport du système d'alertes : volume, réactivité, anticipation, pénuries traitées."""
    prises, resolutions, avances = [], [], []
    penuries: set[tuple] = set()
    for a in lignes:
        creation = a["date_creation"]
        if a["date_prise_en_charge"]:
            prises.append((a["date_prise_en_charge"] - creation).total_seconds() / 3600)
        if a["date_resolution"]:
            resolutions.append((a["date_resolution"] - creation).total_seconds() / 3600)
        avance = (a["date_concernee"] - creation.date()).days
        if avance > 0:
            avances.append(avance)
            if a["type"] == "penurie_equipement" and a["statut"] != "ouverte":
                penuries.add((a["zone_id"], a["date_concernee"]))
    n = len(lignes)
    traitees = sum(1 for a in lignes if a["statut"] != "ouverte")
    return {
        "nb": n,
        "nb_critiques": sum(1 for a in lignes if a["niveau"] == "rouge"),
        "nb_traitees": traitees,
        "taux_traitement": traitees / n * 100 if n else None,
        "delai_prise_en_charge_h": _moyenne(prises),
        "delai_resolution_h": _moyenne(resolutions),
        "nb_anticipees": len(avances),
        "taux_anticipation": len(avances) / n * 100 if n else None,
        "avance_moyenne_j": _moyenne(avances),
        "penuries_traitees": len(penuries),
        "valeur_penuries": len(penuries) * parametres["bl_cout_penurie_jour"],
    }


def analyser_taches(lignes: list[dict], taux: dict[str, float], parametres: dict) -> dict:
    """Apport de l'automatisation : exécutions, fiabilité, temps manuel évité."""
    succes = sum(1 for t in lignes if t["statut"] == "succes")
    echecs = sum(1 for t in lignes if t["statut"] == "echec")
    termine = succes + echecs
    heures = succes * parametres["bl_minutes_manuelles_par_tache"] / 60
    return {
        "nb": len(lignes),
        "nb_succes": succes,
        "nb_echecs": echecs,
        "taux_reussite": succes / termine * 100 if termine else None,
        "duree_machine_h": sum(t["duree_s"] or 0 for t in lignes) / 3600,
        "heures_evitees": heures,
        "valeur_heures_evitees": heures * taux.get("interne", 0.0),
    }


def calculer_roi(gain_periode: float, nb_jours: int, cout_mise_en_place: float) -> dict:
    """Gain annualisé, retour sur investissement et délai de rentabilisation."""
    annuel = gain_periode * 365 / nb_jours if nb_jours > 0 else 0.0
    renseigne = cout_mise_en_place > 0
    return {
        "gain_periode": gain_periode,
        "gain_annuel": annuel,
        "cout_mise_en_place": cout_mise_en_place,
        "roi_pct": (annuel - cout_mise_en_place) / cout_mise_en_place * 100 if renseigne else None,
        "retour_mois": (cout_mise_en_place / (annuel / 12) if renseigne and annuel > 0 else None),
    }


def _limites(
    simulation: dict,
    n_historique: int,
    alertes: dict,
    parametres: dict,
    personnalises: set[str],
    taux: dict[str, float],
) -> list[str]:
    limites = [
        "Les gains sont simulés, pas mesurés : on compare le planning de la semaine précédente "
        "reconduit à la prévision de Workly, face au même besoin réel.",
        "Le retard de commandes est une estimation (sensibilité "
        f"{formater_nombre(parametres['bl_sensibilite_retard'], 2)}) : il ne remplace pas le suivi "
        "des livraisons.",
        "Les heures manquantes sont valorisées au taux d'heures supplémentaires ; l'intérim, les "
        "compétences et les contraintes de planning ne sont pas modélisés.",
        "Workly propose, il ne décide pas : le gain suppose que le plan est suivi et que les "
        "alertes sont traitées.",
    ]
    if n_historique and simulation["nb_jours"] < n_historique:
        limites.append(
            f"Seuls {simulation['nb_jours']} jours de zone sur {n_historique} sont comparables "
            "(prévision et historique de la semaine précédente nécessaires)."
        )
    if not simulation["nb_jours"]:
        limites.append("Aucun jour comparable : les gains simulés ne peuvent pas être chiffrés.")
    if "interne" not in taux:
        limites.append("Aucun coût horaire interne enregistré : les coûts RH valent zéro.")
    non_saisis = [p.libelle for p in PARAMETRES if p.cle not in personnalises]
    if non_saisis:
        limites.append(
            "Valeurs par défaut non calibrées (Administration) : " + " ; ".join(non_saisis) + "."
        )
    if alertes["nb"] and alertes["nb"] < MIN_ECHANTILLON:
        limites.append(
            f"Seulement {alertes['nb']} alerte(s) sur la période : les délais moyens sont "
            "indicatifs."
        )
    return limites


# =====================================================================
# Calcul complet
# =====================================================================
def calculer_bottom_line(
    ctx: Contexte, site_id: int, zone_id: int | None, debut: date, fin: date
) -> dict:
    """Bottom line d'un site (ou d'une zone) sur la période ``debut`` → ``fin`` incluse."""
    verifier_droit(ctx, "lecture_bottom_line")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        depot = DepotBottomLine(cur)
        referentiels = DepotReferentiels(cur)
        parametres = _parametres(DepotParametres(cur))
        personnalises = {p.cle for p in PARAMETRES if DepotParametres(cur).lire(p.cle) is not None}
        taux = referentiels.couts_en_vigueur(fin)
        couts = referentiels.lister_couts()
        jours = depot.jours_comparables(site_id, zone_id, debut, fin)
        n_historique = depot.nb_jours_historique(site_id, zone_id, debut, fin)
        lignes_alertes = depot.alertes_periode(site_id, zone_id, debut, fin)
        lignes_taches = depot.taches_periode(debut, fin)

    simulation = simuler(jours, taux, parametres)
    alertes = analyser_alertes(lignes_alertes, parametres)
    automatisation = analyser_taches(lignes_taches, taux, parametres)
    gain = (
        simulation["gains"]["cout_total"]
        + alertes["valeur_penuries"]
        + automatisation["valeur_heures_evitees"]
    )
    # Pour une période en cours, seuls les jours écoulés comptent dans l'annualisation.
    nb_jours_periode = max(1, (min(fin, date.today()) - debut).days + 1)
    return {
        "debut": debut,
        "fin": fin,
        "devise": couts[0]["devise"] if couts else configuration().devise,
        "nb_jours_historique": n_historique,
        "simulation": simulation,
        "alertes": alertes,
        "automatisation": automatisation,
        "roi": calculer_roi(gain, nb_jours_periode, parametres["bl_cout_mise_en_place"]),
        "parametres": parametres,
        "limites": _limites(simulation, n_historique, alertes, parametres, personnalises, taux),
    }
