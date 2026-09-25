"""Construction des variables d'entrée des modèles de prévision.

Une seule fonction construit les variables, que ce soit pour l'apprentissage (à partir de
l'historique réel) ou pour la prédiction (à partir des prévisions de volume) : dans les deux
cas, l'appelant fournit une série chronologique de dates, de volumes et d'indicateurs de pic.

Variables disponibles (voir ``VARIABLES_PAR_DEFAUT``) :
- ``volume`` : le volume (traité pour l'apprentissage, prévu pour la prédiction) ;
- ``jour_semaine`` : encodage one-hot du jour de la semaine (7 colonnes) ;
- ``indicateur_pic`` : indicateur de pic (0/1) ;
- ``mois_cyclique`` : encodage cyclique du mois (sinus/cosinus) ;
- ``moyenne_mobile_7j`` : volume moyen des 7 valeurs précédentes de la série (jamais la
  valeur du jour même ni des jours suivants : aucune fuite de données futures).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
COLONNES_JOUR = [f"jour_{jour}" for jour in JOURS_SEMAINE]

VARIABLES_PAR_DEFAUT = [
    "volume",
    "jour_semaine",
    "indicateur_pic",
    "mois_cyclique",
    "moyenne_mobile_7j",
]

#: Libellés français des variables (paramétrage UC07) et des colonnes produites (coefficients).
LIBELLES_VARIABLES = {
    "volume": "Volume",
    "jour_semaine": "Jour de la semaine",
    "indicateur_pic": "Indicateur de pic",
    "mois_cyclique": "Mois (cyclique)",
    "moyenne_mobile_7j": "Volume moyen des 7 jours précédents",
}
LIBELLES_COLONNES = {
    "volume": "Volume",
    "indicateur_pic": "Indicateur de pic",
    "mois_sin": "Mois (composante sinus)",
    "mois_cos": "Mois (composante cosinus)",
    "moyenne_mobile_7j": "Volume moyen des 7 jours précédents",
    **{f"jour_{jour}": f"Jour : {jour.capitalize()}" for jour in JOURS_SEMAINE},
}

TAILLE_FENETRE_MOBILE = 7


def libelle_colonne(nom_colonne: str) -> str:
    """Libellé français d'une colonne de variable (pour l'affichage des coefficients)."""
    return LIBELLES_COLONNES.get(nom_colonne, nom_colonne)


def construire_variables(
    dates: Sequence[date],
    volumes: Sequence[float],
    indicateurs_pic: Sequence[bool],
    variables_actives: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Construit le tableau des variables d'entrée, aligné sur ``dates``.

    Les trois séries doivent être triées par date croissante et de même longueur. La
    moyenne mobile porte sur les valeurs précédentes de la série fournie elle-même (pas sur
    un calendrier reconstitué) : elle vaut ``NaN`` tant qu'il n'y a pas ``TAILLE_FENETRE_MOBILE``
    valeurs antérieures disponibles.
    """
    variables_actives = list(variables_actives or VARIABLES_PAR_DEFAUT)
    volumes = pd.Series([float(v) for v in volumes], dtype=float)
    dates = pd.Series(list(dates))
    colonnes: dict[str, pd.Series] = {}

    if "volume" in variables_actives:
        colonnes["volume"] = volumes

    if "jour_semaine" in variables_actives:
        indices_jour = dates.map(lambda jour: jour.weekday())
        for indice, nom_colonne in enumerate(COLONNES_JOUR):
            colonnes[nom_colonne] = (indices_jour == indice).astype(int)

    if "indicateur_pic" in variables_actives:
        colonnes["indicateur_pic"] = pd.Series([int(bool(v)) for v in indicateurs_pic], dtype=int)

    if "mois_cyclique" in variables_actives:
        mois = dates.map(lambda jour: jour.month)
        angle = 2 * np.pi * mois / 12
        colonnes["mois_sin"] = np.sin(angle)
        colonnes["mois_cos"] = np.cos(angle)

    if "moyenne_mobile_7j" in variables_actives:
        colonnes["moyenne_mobile_7j"] = (
            volumes.shift(1)
            .rolling(TAILLE_FENETRE_MOBILE, min_periods=TAILLE_FENETRE_MOBILE)
            .mean()
        )

    return pd.DataFrame(colonnes, index=dates.index)


def lignes_utilisables(x: pd.DataFrame) -> pd.Series:
    """Masque des lignes sans valeur manquante (à appliquer avant l'entraînement)."""
    return ~x.isna().any(axis=1)


def cible_heures(
    heures_travaillees: Sequence[float], heures_inactives: Sequence[float]
) -> pd.Series:
    """Heures nécessaires réelles = heures travaillées − heures inactives."""
    return pd.Series(heures_travaillees, dtype=float) - pd.Series(heures_inactives, dtype=float)


def cible_equipements(equipements_mobilises: Sequence[float]) -> pd.Series:
    """Cible « équipements » = équipements mobilisés."""
    return pd.Series(equipements_mobilises, dtype=float)
