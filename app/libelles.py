"""Libellés français des valeurs énumérées stockées en base."""

from __future__ import annotations

from app.contexte import LIBELLES_ROLES

TYPES_EQUIPEMENT = {
    "chariot_elevateur": "Chariot élévateur",
    "transpalette_electrique": "Transpalette électrique",
    "gerbeur": "Gerbeur",
    "preparateur_commandes": "Préparateur de commandes",
    "autre": "Autre",
}

STATUTS_EQUIPEMENT = {
    "disponible": "Disponible",
    "maintenance": "En maintenance",
    "hors_service": "Hors service",
}

CATEGORIES_COUT = {
    "interne": "Personnel interne",
    "heures_sup": "Heures supplémentaires",
    "interim": "Intérim",
}

METHODES = {
    "regression_lineaire": "Régression linéaire (RL)",
    "reseau_neurones": "Réseau de neurones (RN)",
}
METHODES_COURTES = {"regression_lineaire": "RL", "reseau_neurones": "RN"}

CIBLES_MODELE = {"heures": "Heures nécessaires", "equipements": "Équipements mobilisés"}

STATUTS_PLAN = {
    "brouillon": "Brouillon",
    "soumis": "Soumis",
    "valide": "Validé",
    "rejete": "Rejeté",
}

PERIODICITES = {"jour": "Jour", "semaine": "Semaine", "mois": "Mois", "annee": "Année"}

SENS_KPI = {
    "hausse": "Plus haut, mieux c'est",
    "baisse": "Plus bas, mieux c'est",
    "plage": "Dans une plage",
    "information": "Information",
}

FAMILLES_KPI = {
    "precision": "Précision",
    "rh": "Ressources humaines",
    "equipements": "Équipements",
    "couts": "Coûts",
    "service": "Service",
}

STATUTS_KPI = {"vert": "Vert", "orange": "Orange", "rouge": "Rouge", "gris": "Sans objectif"}

TYPES_ALERTE = {
    "seuil_kpi": "Seuil de KPI",
    "sous_effectif": "Sous-effectif prévisionnel",
    "sureffectif": "Sureffectif prévisionnel",
    "penurie_equipement": "Pénurie d'équipements",
    "derive_modele": "Dérive de modèle",
}

NIVEAUX_ALERTE = {"orange": "Orange", "rouge": "Rouge"}

STATUTS_ALERTE = {"ouverte": "Ouverte", "en_cours": "En cours", "resolue": "Résolue"}

STATUTS_TACHE = {"en_cours": "En cours", "succes": "Succès", "echec": "Échec"}

ROLES = dict(LIBELLES_ROLES)


def libelle(table: dict[str, str], valeur: str | None) -> str:
    """Libellé d'une valeur, ou la valeur elle-même si elle est inconnue."""
    if valeur is None:
        return "—"
    return table.get(valeur, valeur)
