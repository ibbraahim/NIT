"""Prédictions avec intervalle de confiance et passage en ressources (UC11).

Le passage en ressources est appliqué ici et non dans ``entrainement.py`` : les mêmes
règles servent aussi bien à une prédiction fraîche qu'à un recalcul (simulation UC13).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def ramener_positif(valeur: float) -> float:
    """Une prédiction négative n'a pas de sens physique : ramenée à 0."""
    return max(valeur, 0.0)


def predire(
    pipeline, x_nouvelles: pd.DataFrame, quantile_bas: float, quantile_haut: float
) -> pd.DataFrame:
    """Prédiction ponctuelle et intervalle de confiance pour de nouvelles lignes.

    Les valeurs négatives (prédiction et bornes de l'intervalle) sont ramenées à 0.
    """
    predictions = pipeline.predict(x_nouvelles)
    return pd.DataFrame(
        {
            "prediction": [ramener_positif(v) for v in predictions],
            "ic_bas": [ramener_positif(v + quantile_bas) for v in predictions],
            "ic_haut": [ramener_positif(v + quantile_haut) for v in predictions],
        },
        index=x_nouvelles.index,
    )


def heures_vers_effectif(heures: float, duree_poste_heures: float) -> int:
    """Effectif nécessaire = ⌈heures ÷ durée de poste⌉, jamais négatif."""
    if duree_poste_heures <= 0:
        raise ValueError("La durée de poste doit être strictement positive.")
    return max(0, math.ceil(ramener_positif(heures) / duree_poste_heures - 1e-9))


def arrondi_entier_superieur(valeur: float) -> int:
    """Entier supérieur d'une prédiction (équipements nécessaires), jamais négatif."""
    return max(0, math.ceil(ramener_positif(valeur) - 1e-9))


def moyenne_mobile_avec_historique(
    volumes_historiques: list[float], volumes_horizon: list[float], fenetre: int = 7
) -> list[float]:
    """Moyenne mobile des ``fenetre`` jours précédents pour une série de prédiction.

    Pour chaque date de l'horizon, la moyenne porte sur les vrais volumes historiques
    disponibles et, une fois l'historique épuisé, sur les volumes déjà prédits de
    l'horizon lui-même (approche « en cascade », sans jamais utiliser une valeur future
    à la date considérée).
    """
    serie = list(volumes_historiques) + list(volumes_horizon)
    resultat = []
    for i in range(len(volumes_historiques), len(serie)):
        fenetre_valeurs = serie[max(0, i - fenetre) : i]
        resultat.append(float(np.mean(fenetre_valeurs)) if fenetre_valeurs else float("nan"))
    return resultat
