"""Matrice des droits par cas d'utilisation, vérifiée dans chaque service."""

from __future__ import annotations

from app.contexte import ROLE_SYSTEME, Contexte
from app.erreurs import AccesRefuse

P = "planificateur"
R = "responsable"
D = "direction"
A = "administrateur"
S = ROLE_SYSTEME

#: Rôles autorisés par cas d'utilisation (et par droit de lecture transverse).
DROITS: dict[str, frozenset[str]] = {
    "UC01": frozenset({P, R, D, A}),
    "UC02": frozenset({A}),
    "UC03": frozenset({A}),
    "UC04": frozenset({P, S}),
    "UC05": frozenset({P, S}),
    "UC06": frozenset({P, S}),
    "UC07": frozenset({A}),
    "UC08": frozenset({A, S}),
    "UC09": frozenset({A, S}),
    "UC10": frozenset({A}),
    "UC11": frozenset({P, S}),
    "UC12": frozenset({P}),
    "UC13": frozenset({P}),
    "UC14": frozenset({R}),
    "UC15": frozenset({R}),
    "UC16": frozenset({R, S}),
    "UC17": frozenset({R, S}),
    "UC18": frozenset({R, S}),
    "UC19": frozenset({P, R}),
    "UC20": frozenset({R, S}),
    "UC21": frozenset({R, S}),
    "UC22": frozenset({P, R, D}),
    "UC23": frozenset({R, S}),
    "UC24": frozenset({R, S}),
    # Droits de lecture hors cas d'utilisation
    "lecture_referentiels": frozenset({P, R, D, A, S}),
    "lecture_previsions": frozenset({P, R, S}),
    "lecture_plan": frozenset({P, R, S}),
    # L'administrateur voit les alertes de dérive de modèle depuis l'écran Modèles (UC21),
    # bien qu'il ne traite pas les alertes lui-même (UC19, réservé au planificateur/responsable).
    "lecture_alertes": frozenset({P, R, A, S}),
    "lecture_modeles": frozenset({A, R, S}),
    "taches": frozenset({A, S}),
}

LIBELLES_DROITS = {
    "UC02": "gérer les utilisateurs",
    "UC03": "gérer les référentiels",
    "UC04": "importer ou saisir l'historique d'activité",
    "UC05": "importer ou saisir les prévisions de volume",
    "UC06": "contrôler la qualité des données",
    "UC07": "paramétrer les modèles",
    "UC08": "entraîner les modèles",
    "UC09": "évaluer les modèles",
    "UC10": "changer le modèle actif",
    "UC11": "générer les prévisions de ressources",
    "UC12": "élaborer le plan de charge",
    "UC13": "simuler un scénario",
    "UC14": "valider le plan de charge",
    "UC15": "définir les cibles des KPI",
    "UC16": "calculer les KPI",
    "UC17": "comparer les KPI aux cibles",
    "UC18": "émettre des alertes",
    "UC19": "traiter les alertes",
    "UC20": "comparer le réalisé aux prévisions",
    "UC21": "détecter une dérive de modèle",
    "UC22": "consulter le tableau de bord",
    "UC23": "générer un rapport de performance",
    "UC24": "exporter un rapport",
    "taches": "piloter les tâches automatiques",
}


def a_le_droit(ctx: Contexte, droit: str) -> bool:
    """Vrai si le rôle du contexte possède le droit."""
    return ctx.role in DROITS.get(droit, frozenset())


def verifier_droit(ctx: Contexte, droit: str) -> None:
    """Lève :class:`AccesRefuse` si le rôle n'a pas le droit demandé."""
    if not a_le_droit(ctx, droit):
        action = LIBELLES_DROITS.get(droit, "effectuer cette action")
        raise AccesRefuse(f"Votre rôle ({ctx.libelle_role}) ne permet pas de {action}.")


def verifier_site(ctx: Contexte, site_id: int | None) -> None:
    """Lève :class:`AccesRefuse` si l'utilisateur n'est pas rattaché au site."""
    if not ctx.peut_voir_site(site_id):
        raise AccesRefuse("Vous n'êtes pas rattaché à ce site.")
