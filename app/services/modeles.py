"""UC07 · Paramétrer les modèles — UC08 · Entraîner les modèles RL et RN (inclut UC09,
l'évaluation) — UC10 · Changer le modèle actif.

Au moins 90 jours d'historique sont nécessaires par site et zone (UC08) ; une zone qui n'en
a pas assez est simplement signalée dans le résumé, sans bloquer les autres zones. Un nouvel
entraînement ne change jamais automatiquement le modèle actif (UC10 seul le fait).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import joblib

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.bd.depots.modeles import DepotModeles
from app.bd.depots.parametres_modele import DepotParametresModele
from app.bd.depots.referentiels import DepotReferentiels
from app.config import DOSSIER_MODELES
from app.contexte import Contexte
from app.erreurs import DonneesInvalides, OperationImpossible
from app.journal import journal
from app.ml import entrainement, preparation
from app.ml.entrainement import LIBELLES_METHODES, METHODES
from app.services.droits import verifier_droit, verifier_site
from app.utils import validation
from app.utils.noms_fichiers import nom_fichier
from app.utils.progression import Progression, signaler

_log = journal(__name__)

NB_JOURS_MINIMUM = 90
CIBLES = ("heures", "equipements")
ACTIVATIONS_VALIDES = ("relu", "tanh", "logistic", "identity")
JOURS_SEMAINE_VALIDES = preparation.JOURS_SEMAINE

DEFAUT_PARAMETRES: dict = {
    "variables_actives": list(preparation.VARIABLES_PAR_DEFAUT),
    "hyperparametres_rn": dict(entrainement.HYPERPARAMETRES_RN_PAR_DEFAUT),
    "part_test": 0.2,
    "niveau_confiance": 0.8,
    "seuil_derive_mape": 10.0,
    "jour_reentrainement": "lundi",
    "heure_reentrainement": "03:00",
}


# =====================================================================
# UC07 · Paramètres
# =====================================================================
def recuperer_parametres(ctx: Contexte) -> dict:
    """Configuration en vigueur (la plus récente), complétée par les valeurs par défaut."""
    verifier_droit(ctx, "UC07")
    with transaction() as cur:
        dernier = DepotParametresModele(cur).dernier()
    if dernier is None:
        return dict(DEFAUT_PARAMETRES)
    return {**DEFAUT_PARAMETRES, **dernier["configuration"]}


def parametrer_modeles(ctx: Contexte, configuration: dict) -> dict:
    """UC07 : valide puis enregistre une nouvelle configuration."""
    verifier_droit(ctx, "UC07")
    validee = _valider_configuration(configuration)
    with transaction() as cur:
        DepotParametresModele(cur).enregistrer(validee, ctx.utilisateur_id)
    _log.info("Paramètres des modèles enregistrés par %s.", ctx.identifiant)
    return validee


def retablir_defaut(ctx: Contexte) -> dict:
    """UC07 : rétablit les valeurs par défaut (nouvel enregistrement, l'historique est conservé)."""
    verifier_droit(ctx, "UC07")
    with transaction() as cur:
        DepotParametresModele(cur).enregistrer(DEFAUT_PARAMETRES, ctx.utilisateur_id)
    _log.info("Paramètres des modèles rétablis aux valeurs par défaut par %s.", ctx.identifiant)
    return dict(DEFAUT_PARAMETRES)


def _valider_configuration(configuration: dict) -> dict:
    erreurs: dict[str, str] = {}
    resultat: dict = {}

    variables = configuration.get("variables_actives") or []
    if not isinstance(variables, list) or not set(variables) <= set(
        preparation.VARIABLES_PAR_DEFAUT
    ):
        erreurs["variables_actives"] = "Variables d'entrée invalides."
    elif "volume" not in variables:
        erreurs["variables_actives"] = "Le volume doit toujours faire partie des variables actives."
    else:
        resultat["variables_actives"] = variables

    hyper = configuration.get("hyperparametres_rn") or {}
    try:
        couches = [
            int(validation.nombre(c, "Neurones par couche", 1, 1000, entier=True))
            for c in hyper.get("hidden_layer_sizes", [])
        ]
        if not couches:
            raise ValueError("Au moins une couche cachée est requise.")
        activation = hyper.get("activation", "relu")
        if activation not in ACTIVATIONS_VALIDES:
            raise ValueError("Fonction d'activation inconnue.")
        max_iter = int(
            validation.nombre(
                hyper.get("max_iter", 2000), "Itérations maximum", 10, 20000, entier=True
            )
        )
        resultat["hyperparametres_rn"] = {
            "hidden_layer_sizes": couches,
            "activation": activation,
            "max_iter": max_iter,
        }
    except ValueError as exc:
        erreurs["hyperparametres_rn"] = str(exc)

    try:
        resultat["part_test"] = validation.nombre(
            configuration.get("part_test"), "Part du jeu de test", 0.05, 0.5
        )
    except ValueError as exc:
        erreurs["part_test"] = str(exc)

    try:
        resultat["niveau_confiance"] = validation.nombre(
            configuration.get("niveau_confiance"), "Niveau de l'intervalle de confiance", 0.5, 0.99
        )
    except ValueError as exc:
        erreurs["niveau_confiance"] = str(exc)

    try:
        resultat["seuil_derive_mape"] = validation.nombre(
            configuration.get("seuil_derive_mape"), "Seuil de dérive (MAPE %)", 0.1, 100
        )
    except ValueError as exc:
        erreurs["seuil_derive_mape"] = str(exc)

    jour = configuration.get("jour_reentrainement")
    if jour not in JOURS_SEMAINE_VALIDES:
        erreurs["jour_reentrainement"] = "Choisissez un jour de la semaine valide."
    else:
        resultat["jour_reentrainement"] = jour

    heure = str(configuration.get("heure_reentrainement", ""))
    if not _heure_valide(heure):
        erreurs["heure_reentrainement"] = "L'heure doit être au format HH:MM (ex. 03:00)."
    else:
        resultat["heure_reentrainement"] = heure

    if erreurs:
        raise DonneesInvalides("Certains paramètres sont invalides.", erreurs)
    return resultat


def _heure_valide(heure: str) -> bool:
    if len(heure) != 5 or heure[2] != ":":
        return False
    heures, _, minutes = heure.partition(":")
    return (
        heures.isdigit() and minutes.isdigit() and 0 <= int(heures) < 24 and 0 <= int(minutes) < 60
    )


# =====================================================================
# UC08 · Entraînement (inclut UC09, l'évaluation)
# =====================================================================
@dataclass
class VersionEntrainee:
    """Une ligne du résumé d'entraînement (une zone, une cible, une méthode)."""

    zone_id: int
    zone: str
    cible: str
    methode: str
    version_id: int
    metriques: dict[str, float]
    convergence_ok: bool


@dataclass
class ResumeEntrainement:
    """Résultat de :func:`entrainer_modeles`."""

    versions: list[VersionEntrainee] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


def entrainer_modeles(
    ctx: Contexte, site_id: int, zone_id: int | None = None, progression: Progression | None = None
) -> ResumeEntrainement:
    """UC08 : entraîne RL et RN pour les heures et les équipements, zone par zone.

    ``zone_id=None`` entraîne toutes les zones actives du site. Une zone dont l'historique
    est insuffisant (moins de 90 jours) est signalée dans ``avertissements`` et ignorée ;
    les autres zones continuent d'être traitées.
    """
    verifier_droit(ctx, "UC08")
    verifier_site(ctx, site_id)
    resume = ResumeEntrainement()
    with transaction() as cur:
        ref = DepotReferentiels(cur)
        site = ref.site(site_id)
        if site is None:
            raise OperationImpossible("Site introuvable.")
        zones = [ref.zone(zone_id)] if zone_id is not None else ref.lister_zones(site_id)
        zones = [z for z in zones if z is not None]
        dernier = DepotParametresModele(cur).dernier()
        config = {**DEFAUT_PARAMETRES, **dernier["configuration"]} if dernier else DEFAUT_PARAMETRES
        depot_historique = DepotHistorique(cur)
        depot_modeles = DepotModeles(cur)

        etapes_totales = max(len(zones) * len(CIBLES) * len(METHODES), 1)
        etape = 0
        DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
        for zone in zones:
            signaler(
                progression,
                etape / etapes_totales,
                f"Zone « {zone['nom']} » : lecture de l'historique…",
            )
            lignes = depot_historique.historique_complet(site_id, zone["id"])
            if len(lignes) < NB_JOURS_MINIMUM:
                resume.avertissements.append(
                    f"Zone « {zone['nom']} » : historique insuffisant ({len(lignes)} jour(s), "
                    f"{NB_JOURS_MINIMUM} requis). Zone ignorée."
                )
                etape += len(CIBLES) * len(METHODES)
                continue
            dates = [ligne["date_jour"] for ligne in lignes]
            volumes = [ligne["volume_traite"] for ligne in lignes]
            pics = [ligne["indicateur_pic"] for ligne in lignes]
            x = preparation.construire_variables(dates, volumes, pics, config["variables_actives"])
            masque = preparation.lignes_utilisables(x).to_numpy()
            x_utilisable = x[masque].reset_index(drop=True)
            dates_utilisables = [d for d, garder in zip(dates, masque, strict=True) if garder]

            cibles_valeurs = {
                "heures": preparation.cible_heures(
                    [ligne["heures_travaillees"] for ligne in lignes],
                    [ligne["heures_inactives"] for ligne in lignes],
                )[masque].reset_index(drop=True),
                "equipements": preparation.cible_equipements(
                    [ligne["equipements_mobilises"] for ligne in lignes]
                )[masque].reset_index(drop=True),
            }
            for cible in CIBLES:
                for methode in METHODES:
                    etape += 1
                    signaler(
                        progression,
                        etape / etapes_totales,
                        f"Zone « {zone['nom']} » — {LIBELLES_METHODES[methode]} ({cible})…",
                    )
                    resultat = entrainement.entrainer_et_evaluer(
                        x_utilisable,
                        cibles_valeurs[cible],
                        methode,
                        config["part_test"],
                        config["niveau_confiance"],
                        config["hyperparametres_rn"],
                    )
                    statut = "retenue" if resultat.convergence_ok else "non_retenue"
                    if not resultat.convergence_ok:
                        _log.warning(
                            "Le réseau de neurones n'a pas convergé pour %s / %s / %s (%s) : "
                            "version non retenue.",
                            site["nom"],
                            zone["nom"],
                            methode,
                            cible,
                        )
                    nom = nom_fichier(site["nom"], zone["nom"], methode, cible)
                    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                    chemin_relatif = f"{nom}_{horodatage}.joblib"
                    joblib.dump(resultat.pipeline, DOSSIER_MODELES / chemin_relatif)
                    # Les résidus et prédictions du jeu de test sont conservés (dans les
                    # métriques) pour le graphique des résidus de l'écran Modèles.
                    metriques_stockees = {
                        **resultat.metriques,
                        "residus_test": resultat.residus_test,
                        "predictions_test": resultat.predictions_test,
                    }
                    version_id = depot_modeles.creer(
                        site_id,
                        zone["id"],
                        methode,
                        cible,
                        chemin_relatif,
                        metriques_stockees,
                        resultat.coefficients,
                        config,
                        resultat.nb_lignes_apprentissage,
                        resultat.nb_lignes_test,
                        dates_utilisables[0] if dates_utilisables else None,
                        dates_utilisables[-1] if dates_utilisables else None,
                        statut,
                        ctx.utilisateur_id,
                    )
                    resume.versions.append(
                        VersionEntrainee(
                            zone["id"],
                            zone["nom"],
                            cible,
                            methode,
                            version_id,
                            resultat.metriques,
                            resultat.convergence_ok,
                        )
                    )
                    if not resultat.convergence_ok:
                        resume.avertissements.append(
                            f"Zone « {zone['nom']} », {LIBELLES_METHODES[methode]} ({cible}) : "
                            "le réseau de neurones n'a pas convergé ; version non retenue."
                        )
        signaler(progression, 1.0, "Entraînement terminé.")
    _log.info(
        "Entraînement UC08 par %s : %d version(s) créée(s), %d avertissement(s).",
        ctx.identifiant,
        len(resume.versions),
        len(resume.avertissements),
    )
    return resume


def lister_versions(ctx: Contexte, site_id: int, zone_id: int | None = None) -> list[dict]:
    """Tableau des versions (écran Modèles, onglet Entraînement)."""
    verifier_droit(ctx, "lecture_modeles")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        return DepotModeles(cur).lister(site_id, zone_id)


def charger_pipeline(chemin_fichier: str):
    """Charge un pipeline scikit-learn sauvegardé (``joblib``)."""
    return joblib.load(DOSSIER_MODELES / chemin_fichier)


# =====================================================================
# UC10 · Changer le modèle actif
# =====================================================================
def comparer_avant_activation(ctx: Contexte, version_id: int) -> dict:
    """Métriques de la version candidate et de la version actuellement active, côte à côte."""
    verifier_droit(ctx, "UC10")
    with transaction() as cur:
        depot = DepotModeles(cur)
        candidate = depot.version(version_id)
        if candidate is None:
            raise OperationImpossible("Version de modèle introuvable.")
        actif_actuel = depot.version_active(
            candidate["site_id"], candidate["zone_id"], candidate["methode"], candidate["cible"]
        )
    return {"candidate": candidate, "actif_actuel": actif_actuel}


def activer_version(ctx: Contexte, version_id: int) -> None:
    """UC10 : active la version sélectionnée ; si elle porte sur les heures, retient aussi sa
    méthode pour le plan de charge (UC12) et la détection de dérive (UC21)."""
    verifier_droit(ctx, "UC10")
    with transaction() as cur:
        depot = DepotModeles(cur)
        version = depot.version(version_id)
        if version is None:
            raise OperationImpossible("Version de modèle introuvable.")
        if version["statut"] != "retenue":
            raise OperationImpossible(
                "Cette version n'a pas été retenue à l'entraînement (le réseau de neurones "
                "n'a pas convergé) et ne peut pas être activée."
            )
        depot.activer(version_id)
        if version["cible"] == "heures":
            depot.definir_retenue_pour_plan(version_id)
    _log.info("Version de modèle n° %s activée par %s.", version_id, ctx.identifiant)
