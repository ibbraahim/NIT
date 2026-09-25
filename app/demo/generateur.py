"""Générateur du jeu de démonstration « Plateforme Casablanca » (graine 42).

- Référentiels (site, zones, équipements dont 2 chariots en maintenance la semaine de
  démonstration), comptes, capacités de personnel (même planning chaque semaine) et coûts
  horaires ;
- historique d'activité de 18 mois (saisonnalités hebdomadaire et annuelle, campagnes
  promotionnelles, bruit, effet de congestion non linéaire au-delà de 85 % de la capacité,
  heures supplémentaires et intérim qui montent avec la charge) ;
- prévisions de volume sur 28 jours, avec le pic de +40 % du jeudi de la semaine de
  démonstration et le creux du mardi suivant ;
- modèles entraînés pour chaque zone et régression linéaire retenue par défaut pour le plan
  de charge (voir docs/plan.md, Q3 et Q4, pour les choix documentés) ;
- rétro-prévisions et rapprochement réel/prévu sur la période de test des modèles (UC20),
  matière des KPI de précision et de la détection de dérive (UC21 — voir docs/plan.md, Q5) ;
- KPI hebdomadaires calculés et alertes détectées sur le plan validé (UC16-UC18) : sureffectif
  du mardi suivant, pénurie d'équipements de la zone Réception, seuils de KPI dépassés.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable
from datetime import date, datetime, timedelta

import numpy as np

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.bd.depots.modeles import DepotModeles
from app.bd.depots.parametres import DepotParametres
from app.bd.depots.previsions import DepotPrevisionsVolume
from app.bd.depots.previsions_ressources import DepotPrevisionsRessources
from app.bd.depots.referentiels import DepotReferentiels
from app.bd.depots.utilisateurs import DepotUtilisateurs
from app.config import DOSSIER_RESSOURCES
from app.contexte import Contexte
from app.journal import journal
from app.ml import prediction, preparation
from app.ml.entrainement import METHODES
from app.services import alertes, comparaison, kpi, modeles, planification
from app.services.auth import hacher_mot_de_passe
from app.services.donnees import HORIZON_PREVISION_JOURS
from app.services.planification import TAILLE_FENETRE_MOBILE
from app.utils.dates import lundi_de

_log = journal(__name__)

GRAINE = 42
NOM_SITE = "Plateforme Casablanca"
ADRESSE_SITE = "Zone logistique (adresse fictive de démonstration), Casablanca"
DUREE_POSTE = 7.5
MOIS_HISTORIQUE = 18
FICHIER_COMPTES = DOSSIER_RESSOURCES / "demo" / "comptes_demo.csv"

#: (nom, type d'équipement principal, préfixe de code, nombre d'équipements, effectif planifié)
ZONES_DEMO = [
    ("Réception", "chariot_elevateur", "CE", 4, 10),
    ("Stockage", "chariot_elevateur", "CE", 4, 8),
    ("Préparation", "transpalette_electrique", "TP", 5, 16),
    ("Expédition", "transpalette_electrique", "TP", 5, 8),
]
EFFECTIF_ZONES = {nom: effectif for nom, _t, _p, _n, effectif in ZONES_DEMO}
NB_EQUIPEMENTS_ZONES = {nom: nombre for nom, _t, _p, nombre, _e in ZONES_DEMO}
#: Volume quotidien de référence par zone (jour ouvré moyen, hors saisonnalité et promotions).
VOLUME_BASE_ZONES = {
    "Réception": 1200.0,
    "Stockage": 1000.0,
    "Préparation": 1400.0,
    "Expédition": 1300.0,
}
#: Chariots de Réception placés en maintenance la semaine de démonstration.
NB_CHARIOTS_MAINTENANCE_DEMO = 2

#: Coûts horaires de démonstration (MAD).
COUTS_DEMO = {"interne": 45.0, "heures_sup": 56.25, "interim": 58.0}

#: Jours ouvrés : lundi (0) à samedi (5) ; le dimanche la plateforme est fermée.
JOURS_OUVRES = {0, 1, 2, 3, 4, 5}

# ---------------------------------------------------------------------
# Paramètres du modèle de génération de l'historique
# ---------------------------------------------------------------------
#: Multiplicateur de charge par jour de la semaine (lundi et jeudi plus chargés, samedi faible).
MULTIPLICATEURS_JOUR = {0: 1.15, 1: 1.0, 2: 1.0, 3: 1.20, 4: 1.0, 5: 0.5, 6: 0.0}
AMPLITUDE_SAISON_ANNUELLE = 0.25  # pic en décembre, creux en juin/juillet
ECART_TYPE_BRUIT = 0.04
PROBABILITE_CAMPAGNE = 9 / (MOIS_HISTORIQUE * 30)  # ~9 campagnes sur 18 mois
DUREE_CAMPAGNE_MIN, DUREE_CAMPAGNE_MAX = 1, 3
BOOST_CAMPAGNE_MIN, BOOST_CAMPAGNE_MAX = 1.30, 1.50
SEUIL_CONGESTION = 0.85  # au-delà de 85 % de la capacité, la productivité se dégrade
PENALITE_CONGESTION = 1.6
PLAFOND_HEURES_SUP = 0.20  # heures sup. maximum : 20 % de la capacité de la zone
FACTEUR_UTILISATION_EQUIPEMENT = 0.9
BOOST_PIC_DEMO = 1.40  # +40 % le jeudi de la semaine de démonstration
BAISSE_MARDI_SUIVANT = 0.55  # volume nettement plus faible le mardi suivant


def date_debut_historique(date_reference: date) -> date:
    """Premier jour de l'historique : 18 mois avant la date de référence."""
    mois = date_reference.year * 12 + date_reference.month - 1 - MOIS_HISTORIQUE
    return date(mois // 12, mois % 12 + 1, 1)


def semaine_demonstration(date_reference: date) -> date:
    """Lundi de la semaine suivant la date de référence."""
    return lundi_de(date_reference) + timedelta(days=7)


def lire_comptes_demo() -> list[dict]:
    """Comptes de démonstration (un par rôle), lus dans ``ressources/demo``."""
    with FICHIER_COMPTES.open(encoding="utf-8") as fichier:
        return list(csv.DictReader(fichier, delimiter=";"))


def generer_demonstration(
    date_reference: date | None = None, afficher: Callable[[str], None] = print
) -> dict:
    """Génère l'ensemble du jeu de démonstration et retourne ses identifiants clés."""
    date_reference = date_reference or date.today()
    rng = np.random.default_rng(GRAINE)
    resultat = generer_referentiels(date_reference)
    afficher(f"Référentiels de démonstration créés ({NOM_SITE}).")
    generer_historique(date_reference, rng, resultat["site_id"], resultat["zones"])
    afficher(f"Historique d'activité généré ({MOIS_HISTORIQUE} mois).")
    generer_previsions_demo(date_reference, resultat["site_id"], resultat["zones"])
    afficher(
        "Prévisions de volume générées, dont le pic du jeudi de la semaine de " "démonstration."
    )
    entrainer_et_activer_demo(resultat["site_id"], resultat["zones"])
    afficher("Modèles entraînés pour chaque zone (régression linéaire retenue par défaut).")
    resultat_retro = generer_retro_donnees_comparaison_demo(
        resultat["site_id"], resultat["zones"], date_reference
    )
    afficher(
        f"Réalisé rapproché aux prévisions sur la période de test des modèles : "
        f"{resultat_retro['nb_comparaisons']} jour(s) comparé(s), "
        f"{resultat_retro['nb_alertes']} alerte(s) de dérive."
    )
    generer_previsions_et_plans_demo(resultat["site_id"], resultat["zones"], date_reference)
    afficher(
        "Prévisions de ressources générées et plan de charge validé pour la semaine de "
        "démonstration et la semaine suivante."
    )
    _log.info("Jeu de démonstration généré (date de référence %s).", date_reference)
    return resultat


def generer_referentiels(date_reference: date) -> dict:
    """Site, zones, équipements (2 chariots de Réception en maintenance la semaine de
    démonstration), comptes, capacités et coûts de démonstration."""
    with transaction() as cur:
        ref = DepotReferentiels(cur)
        site_id = ref.creer_site(NOM_SITE, ADRESSE_SITE)
        zones: dict[str, int] = {}
        compteurs = {"CE": 0, "TP": 0}
        chariots_reception: list[int] = []
        for nom, type_eqp, prefixe, nombre, _effectif in ZONES_DEMO:
            zone_id = ref.creer_zone(site_id, nom, type_eqp, DUREE_POSTE)
            zones[nom] = zone_id
            for _ in range(nombre):
                compteurs[prefixe] += 1
                equipement_id = ref.creer_equipement(
                    site_id, zone_id, type_eqp, f"{prefixe}-{compteurs[prefixe]:02d}", "disponible"
                )
                if nom == "Réception":
                    chariots_reception.append(equipement_id)

        # Deux chariots de Réception en maintenance du lundi au vendredi de la semaine de
        # démonstration : la plateforme manque déjà de chariots pour absorber le pic du jeudi.
        lundi_demo = semaine_demonstration(date_reference)
        for equipement_id in chariots_reception[:NB_CHARIOTS_MAINTENANCE_DEMO]:
            ref.ajouter_indisponibilite(
                equipement_id,
                lundi_demo,
                lundi_demo + timedelta(days=4),
                "Maintenance programmée (jeu de démonstration).",
            )

        # Capacité volontairement identique d'une semaine à l'autre.
        debut = date_debut_historique(date_reference)
        fin = semaine_demonstration(date_reference) + timedelta(days=27)
        jour = debut
        while jour <= fin:
            for nom, _type, _prefixe, _nombre, effectif in ZONES_DEMO:
                ouvert = jour.weekday() in JOURS_OUVRES
                ref.enregistrer_capacite(site_id, zones[nom], jour, effectif if ouvert else 0, 0)
            jour += timedelta(days=1)

        for categorie, taux in COUTS_DEMO.items():
            ref.enregistrer_cout(categorie, taux, "MAD", debut)

        utilisateurs = DepotUtilisateurs(cur)
        comptes = {}
        for compte in lire_comptes_demo():
            hash_mdp, sel = hacher_mot_de_passe(compte["mot_de_passe"])
            existant = utilisateurs.par_identifiant(compte["identifiant"])
            if existant:
                utilisateurs.definir_mot_de_passe(existant["id"], hash_mdp, sel)
                utilisateurs.modifier(
                    existant["id"], compte["nom"], compte["prenom"], compte["email"], compte["role"]
                )
                utilisateur_id = existant["id"]
            else:
                utilisateur_id = utilisateurs.creer(
                    compte["identifiant"],
                    compte["nom"],
                    compte["prenom"],
                    compte["email"],
                    hash_mdp,
                    sel,
                    compte["role"],
                )
            if compte["role"] != "administrateur":
                utilisateurs.definir_sites(utilisateur_id, [site_id])
            comptes[compte["identifiant"]] = utilisateur_id

        parametres = DepotParametres(cur)
        parametres.ecrire("donnees_demonstration", "oui")
        parametres.ecrire("date_reference_demonstration", date_reference.isoformat())
    return {"site_id": site_id, "zones": zones, "comptes": comptes}


# =====================================================================
# Historique d'activité (18 mois)
# =====================================================================
def _saison_annuelle(mois: int) -> float:
    """Multiplicateur saisonnier : pic en décembre, creux en juin/juillet."""
    return 1 + AMPLITUDE_SAISON_ANNUELLE * math.cos(2 * math.pi * (mois - 12) / 12)


def _campagnes_promotionnelles(
    rng: np.random.Generator, debut: date, fin: date
) -> dict[date, float]:
    """Fenêtres de campagnes promotionnelles ponctuelles (+30 à +50 %), 1 à 3 jours."""
    campagnes: dict[date, float] = {}
    jour = debut
    while jour <= fin:
        if rng.random() < PROBABILITE_CAMPAGNE:
            duree = int(rng.integers(DUREE_CAMPAGNE_MIN, DUREE_CAMPAGNE_MAX + 1))
            boost = float(rng.uniform(BOOST_CAMPAGNE_MIN, BOOST_CAMPAGNE_MAX))
            for i in range(duree):
                jour_campagne = jour + timedelta(days=i)
                if jour_campagne > fin:
                    break
                campagnes[jour_campagne] = boost
            jour += timedelta(days=duree)
        else:
            jour += timedelta(days=1)
    return campagnes


def _ligne_activite(
    site_id: int,
    zone_id: int,
    nom_zone: str,
    jour: date,
    volume_traite: float,
    indicateur_pic: bool,
    rng: np.random.Generator,
) -> dict:
    """Construit une ligne d'historique cohérente à partir d'un volume (effet de congestion,
    heures supplémentaires et intérim croissant avec la charge, équipements, coûts, service)."""
    effectif = EFFECTIF_ZONES[nom_zone]
    capacite_heures = effectif * DUREE_POSTE
    coefficient_heures = capacite_heures / VOLUME_BASE_ZONES[nom_zone]

    heures_lineaires = volume_traite * coefficient_heures
    taux_charge = heures_lineaires / capacite_heures
    if taux_charge > SEUIL_CONGESTION:
        exces = taux_charge - SEUIL_CONGESTION
        heures_necessaires = heures_lineaires * (1 + PENALITE_CONGESTION * exces)
    else:
        heures_necessaires = heures_lineaires

    if heures_necessaires <= capacite_heures:
        heures_travaillees = capacite_heures
        heures_inactives = capacite_heures - heures_necessaires
        heures_sup = 0.0
        heures_interim = 0.0
    else:
        excedent = heures_necessaires - capacite_heures
        heures_sup = min(excedent, PLAFOND_HEURES_SUP * capacite_heures)
        heures_interim = max(excedent - heures_sup, 0.0)
        heures_travaillees = heures_necessaires
        heures_inactives = 0.0

    effectif_present = effectif + math.ceil(heures_interim / DUREE_POSTE - 1e-9)

    nb_equipements = NB_EQUIPEMENTS_ZONES[nom_zone]
    heures_disponibles_equipement = nb_equipements * DUREE_POSTE
    equipements_mobilises = min(
        nb_equipements,
        math.ceil(heures_necessaires / (DUREE_POSTE * FACTEUR_UTILISATION_EQUIPEMENT) - 1e-9),
    )
    heures_usage_equipement = min(heures_necessaires, equipements_mobilises * DUREE_POSTE)
    heures_panne_equipement = float(rng.uniform(0, 2)) if rng.random() < 0.1 else 0.0

    cout_rh = (
        capacite_heures * COUTS_DEMO["interne"]
        + heures_sup * COUTS_DEMO["heures_sup"]
        + heures_interim * COUTS_DEMO["interim"]
    )

    commandes_totales = max(1, round(volume_traite / 10))
    taux_a_temps = min(max(0.98 - 0.35 * max(taux_charge - SEUIL_CONGESTION, 0), 0.5), 0.99)
    commandes_a_temps = round(commandes_totales * taux_a_temps)

    return {
        "site_id": site_id,
        "zone_id": zone_id,
        "date_jour": jour,
        "volume_traite": round(volume_traite, 1),
        "effectif_present": effectif_present,
        "heures_travaillees": round(heures_travaillees, 2),
        "heures_sup": round(heures_sup, 2),
        "heures_interim": round(heures_interim, 2),
        "heures_absence": 0.0,
        "heures_inactives": round(heures_inactives, 2),
        "equipements_mobilises": equipements_mobilises,
        "heures_usage_equipement": round(heures_usage_equipement, 2),
        "heures_disponibles_equipement": round(heures_disponibles_equipement, 2),
        "heures_panne_equipement": round(heures_panne_equipement, 2),
        "cout_rh": round(cout_rh, 2),
        "commandes_a_temps": commandes_a_temps,
        "commandes_totales": commandes_totales,
        "indicateur_pic": indicateur_pic,
        "source": "demonstration",
    }


def generer_historique(
    date_reference: date, rng: np.random.Generator, site_id: int, zones: dict[str, int]
) -> int:
    """Historique de ``MOIS_HISTORIQUE`` mois, jusqu'à hier, pour toutes les zones du site."""
    debut = date_debut_historique(date_reference)
    fin = date_reference - timedelta(days=1)
    campagnes = _campagnes_promotionnelles(rng, debut, fin)

    lignes = []
    jour = debut
    while jour <= fin:
        if jour.weekday() in JOURS_OUVRES:
            saison = _saison_annuelle(jour.month)
            boost_campagne = campagnes.get(jour, 1.0)
            for nom_zone, zone_id in zones.items():
                bruit = 1 + float(rng.normal(0, ECART_TYPE_BRUIT))
                volume = (
                    VOLUME_BASE_ZONES[nom_zone]
                    * MULTIPLICATEURS_JOUR[jour.weekday()]
                    * saison
                    * boost_campagne
                    * bruit
                )
                lignes.append(
                    _ligne_activite(
                        site_id,
                        zone_id,
                        nom_zone,
                        jour,
                        max(volume, 0.0),
                        jour in campagnes,
                        rng,
                    )
                )
        jour += timedelta(days=1)

    with transaction() as cur:
        return DepotHistorique(cur).upsert_plusieurs(lignes)


# =====================================================================
# Prévisions de volume (semaine de démonstration incluse)
# =====================================================================
def generer_previsions_demo(date_reference: date, site_id: int, zones: dict[str, int]) -> int:
    """Prévisions sur ``HORIZON_PREVISION_JOURS`` jours : pic de +40 % le jeudi de la semaine de
    démonstration, creux le mardi de la semaine suivante."""
    jeudi_pic = semaine_demonstration(date_reference) + timedelta(days=3)
    mardi_creux = semaine_demonstration(date_reference) + timedelta(days=8)

    lignes = []
    for i in range(1, HORIZON_PREVISION_JOURS + 1):
        jour = date_reference + timedelta(days=i)
        if jour.weekday() not in JOURS_OUVRES:
            continue
        saison = _saison_annuelle(jour.month)
        volume_normal = VOLUME_BASE_ZONES  # alias, un volume de base par zone
        for nom_zone, zone_id in zones.items():
            volume = volume_normal[nom_zone] * MULTIPLICATEURS_JOUR[jour.weekday()] * saison
            indicateur_pic = False
            if jour == jeudi_pic:
                volume *= BOOST_PIC_DEMO
                indicateur_pic = True
            elif jour == mardi_creux:
                volume *= BAISSE_MARDI_SUIVANT
            lignes.append(
                {
                    "site_id": site_id,
                    "zone_id": zone_id,
                    "date_jour": jour,
                    "volume_prevu": round(max(volume, 0.0), 1),
                    "indicateur_pic": indicateur_pic,
                    "source": "demonstration",
                }
            )

    with transaction() as cur:
        return DepotPrevisionsVolume(cur).upsert_plusieurs(lignes)


# =====================================================================
# Entraînement et activation des modèles (au nom du compte administrateur)
# =====================================================================
def _contexte_administrateur() -> Contexte:
    """Contexte du compte ``admin`` : l'activation des modèles de démonstration se fait en
    son nom (voir docs/plan.md, Q3)."""
    with transaction() as cur:
        utilisateur = DepotUtilisateurs(cur).par_identifiant("admin")
    return Contexte(
        utilisateur_id=utilisateur["id"],
        identifiant="admin",
        role="administrateur",
        nom_complet=f"{utilisateur['prenom']} {utilisateur['nom']}".strip(),
        sites=frozenset(),
    )


def entrainer_et_activer_demo(site_id: int, zones: dict[str, int]) -> None:
    """Entraîne RL et RN pour chaque zone et active les deux (UC11 en a besoin pour les
    comparer côte à côte) ; la régression linéaire est retenue par défaut pour le plan de
    charge (référence de départ — la comparaison réel/prévu, au lot 5, montrera si le
    réseau de neurones la surpasse sur les pics, invitant à en changer via UC10 au lot 8)."""
    ctx = _contexte_administrateur()
    for zone_id in zones.values():
        resume = modeles.entrainer_modeles(ctx, site_id, zone_id)
        for version in resume.versions:
            modeles.activer_version(
                ctx, version.version_id, retenir_pour_plan=version.methode == "regression_lineaire"
            )


# =====================================================================
# Rétro-prévisions et comparaison réel/prévu (UC20, UC21 ; matière des KPI de précision)
# =====================================================================
def generer_retro_donnees_comparaison_demo(
    site_id: int, zones: dict[str, int], date_reference: date
) -> dict:
    """Rétro-prévisions de volume et de ressources sur la période de test des modèles (docs/
    plan.md, Q5), puis rapprochement réel/prévu (UC20) et détection de dérive (UC21).

    Les prévisions de volume rétroactives reprennent le volume réellement traité (biais nul
    sur le volume : l'écart mesuré vient du modèle heures/équipements lui-même, comme un vrai
    test a posteriori). Les prévisions de ressources sont calculées avec les pipelines RL et
    RN déjà entraînés, sur exactement la période de test qui a servi à leur évaluation
    (UC08/UC09) : les KPI de précision (lot 5) retrouvent ainsi les mêmes erreurs.
    """
    ctx_resp = _contexte_compte("resp", "responsable", site_id)
    config = modeles.recuperer_parametres(_contexte_administrateur())
    part_test = config["part_test"]
    horodatage = datetime.now()

    bornes: list[date] = []
    with transaction() as cur:
        ref = DepotReferentiels(cur)
        depot_hist = DepotHistorique(cur)
        depot_modeles = DepotModeles(cur)
        depot_volume = DepotPrevisionsVolume(cur)
        depot_previsions = DepotPrevisionsRessources(cur)

        for zone_id in zones.values():
            zone = ref.zone(zone_id)
            historique = depot_hist.historique_complet(site_id, zone_id)
            n_test = max(1, round(len(historique) * part_test))
            if len(historique) <= n_test + TAILLE_FENETRE_MOBILE:
                continue
            historique_recent = historique[-(n_test + TAILLE_FENETRE_MOBILE) : -n_test]
            periode_test = historique[-n_test:]
            bornes += [periode_test[0]["date_jour"], periode_test[-1]["date_jour"]]

            depot_volume.upsert_plusieurs(
                [
                    {
                        "site_id": site_id,
                        "zone_id": zone_id,
                        "date_jour": h["date_jour"],
                        "volume_prevu": h["volume_traite"],
                        "indicateur_pic": h["indicateur_pic"],
                        "source": "demonstration_retro",
                    }
                    for h in periode_test
                ]
            )

            dates_test = [h["date_jour"] for h in periode_test]
            volumes_par_date = {h["date_jour"]: h["volume_traite"] for h in periode_test}
            dates_completes = [h["date_jour"] for h in historique_recent] + dates_test
            volumes_completes = [h["volume_traite"] for h in historique_recent] + [
                volumes_par_date[d] for d in dates_test
            ]
            pics_completes = [h["indicateur_pic"] for h in historique_recent] + [
                h["indicateur_pic"] for h in periode_test
            ]

            lignes_ressources = []
            for methode in METHODES:
                version_heures = depot_modeles.version_active(site_id, zone_id, methode, "heures")
                version_eqp = depot_modeles.version_active(site_id, zone_id, methode, "equipements")
                if version_heures is None or version_eqp is None:
                    continue
                variables_actives = version_heures["parametres"]["variables_actives"]
                x_complet = preparation.construire_variables(
                    dates_completes, volumes_completes, pics_completes, variables_actives
                )
                x_horizon = x_complet.iloc[len(historique_recent) :].reset_index(drop=True)
                masque = preparation.lignes_utilisables(x_horizon).to_numpy()
                dates_valides = [d for d, garder in zip(dates_test, masque, strict=True) if garder]
                if not dates_valides:
                    continue
                x_valide = x_horizon[masque].reset_index(drop=True)

                pipeline_heures = modeles.charger_pipeline(version_heures["chemin_fichier"])
                pipeline_eqp = modeles.charger_pipeline(version_eqp["chemin_fichier"])
                pred_heures = prediction.predire(
                    pipeline_heures,
                    x_valide,
                    version_heures["metriques"]["quantile_bas"],
                    version_heures["metriques"]["quantile_haut"],
                )
                pred_eqp = prediction.predire(
                    pipeline_eqp,
                    x_valide,
                    version_eqp["metriques"]["quantile_bas"],
                    version_eqp["metriques"]["quantile_haut"],
                )
                for i, jour in enumerate(dates_valides):
                    heures = float(pred_heures["prediction"].iloc[i])
                    lignes_ressources.append(
                        {
                            "site_id": site_id,
                            "zone_id": zone_id,
                            "date_jour": jour,
                            "modele_version_id": version_heures["id"],
                            "modele_version_equipements_id": version_eqp["id"],
                            "methode": methode,
                            "volume_prevu": volumes_par_date[jour],
                            "heures": heures,
                            "effectif": prediction.heures_vers_effectif(
                                heures, zone["duree_poste_heures"]
                            ),
                            "equipements": prediction.arrondi_entier_superieur(
                                pred_eqp["prediction"].iloc[i]
                            ),
                            "ic_bas": float(pred_heures["ic_bas"].iloc[i]),
                            "ic_haut": float(pred_heures["ic_haut"].iloc[i]),
                            "ic_bas_equipements": float(pred_eqp["ic_bas"].iloc[i]),
                            "ic_haut_equipements": float(pred_eqp["ic_haut"].iloc[i]),
                            "date_generation": horodatage,
                        }
                    )
            depot_previsions.inserer_plusieurs(lignes_ressources)

    if not bornes:
        return {"nb_comparaisons": 0, "nb_alertes": 0}
    resultat_comparaison = comparaison.comparer_realise(
        ctx_resp, site_id, debut=min(bornes), fin=max(bornes)
    )
    alertes = comparaison.detecter_derive(ctx_resp, site_id, date_reference=date_reference)
    return {"nb_comparaisons": resultat_comparaison["nb_comparables"], "nb_alertes": len(alertes)}


# =====================================================================
# Prévisions de ressources et plan de charge (au nom des comptes planif et resp)
# =====================================================================
def _commentaire_depassement(ligne: dict) -> str:
    """Commentaire honnête d'une case en dépassement : selon la dimension réellement en cause
    (effectif ou seulement équipements), pour ne pas toujours invoquer la campagne
    promotionnelle même quand ce n'est pas elle qui explique le dépassement."""
    if ligne["besoin_effectif"] > ligne["capacite_effectif"]:
        return (
            "Pic de volume lié à une campagne promotionnelle : renfort intérim et heures "
            "supplémentaires nécessaires."
        )
    return "Besoin en équipements supérieur au nombre d'équipements disponibles ce jour-là."


def _contexte_compte(identifiant: str, role: str, site_id: int) -> Contexte:
    with transaction() as cur:
        utilisateur = DepotUtilisateurs(cur).par_identifiant(identifiant)
    return Contexte(
        utilisateur_id=utilisateur["id"],
        identifiant=identifiant,
        role=role,
        nom_complet=f"{utilisateur['prenom']} {utilisateur['nom']}".strip(),
        sites=frozenset({site_id}),
    )


def generer_previsions_et_plans_demo(
    site_id: int, zones: dict[str, int], date_reference: date
) -> None:
    """UC11 pour toutes les zones (28 jours), puis UC12/UC14 : plan proposé, les cases en
    dépassement commentées, soumis et validé pour la semaine de démonstration et la semaine
    suivante — pour que le planificateur voie tout, sans autre action, en ouvrant l'écran
    Plan de charge."""
    ctx_planif = _contexte_compte("planif", "planificateur", site_id)
    ctx_resp = _contexte_compte("resp", "responsable", site_id)

    for zone_id in zones.values():
        planification.generer_previsions(ctx_planif, site_id, zone_id, 28)

    semaine_demo = semaine_demonstration(date_reference)
    semaine_suivante = semaine_demo + timedelta(days=7)
    for semaine in (semaine_demo, semaine_suivante):
        resultat = planification.proposer_plan_charge(ctx_planif, site_id, semaine)
        plan = planification.lire_plan_charge(ctx_planif, site_id, semaine)
        ajustements = []
        for ligne in plan["lignes"]:
            if planification.statut_couleur_ligne(ligne) == "rouge":
                ajustements.append({**ligne, "commentaire": _commentaire_depassement(ligne)})
            elif (
                semaine == semaine_suivante
                and ligne["besoin_effectif"] < ligne["capacite_effectif"]
            ):
                # « Le même planning que la semaine précédente » (voir <donnees_demo>) : le
                # planificateur n'a pas réduit l'effectif malgré le volume plus faible, d'où
                # le sureffectif du mardi suivant.
                ajustements.append(
                    {
                        **ligne,
                        "effectif_planifie": ligne["capacite_effectif"],
                        "interim_planifie": 0,
                        "equipements_planifies": ligne["capacite_equipements"],
                    }
                )
        if ajustements:
            planification.enregistrer_brouillon_plan(ctx_planif, resultat["plan_id"], ajustements)
        planification.soumettre_plan(ctx_planif, resultat["plan_id"])
        planification.valider_plan(ctx_resp, resultat["plan_id"])

    # UC16/17 puis UC18 : matière (statuts orange/rouge) pour les alertes de seuil de KPI, en
    # plus de celles déjà décelables sur le plan validé (sous-effectif, sureffectif, pénurie
    # d'équipements).
    kpi.comparer_kpi_cibles(ctx_resp, site_id, None, "semaine", date_reference)
    alertes.emettre_alertes(ctx_resp, site_id, date_reference)
