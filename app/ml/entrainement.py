"""Entraînement et évaluation des modèles RL et RN (UC08, UC09).

Découpage chronologique (jamais aléatoire) : les lignes les plus anciennes servent à
l'apprentissage, les plus récentes au test. Graine aléatoire fixée à 42 partout, pour des
résultats reproductibles.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LinearRegression
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.preparation import libelle_colonne

GRAINE_ALEATOIRE = 42

HYPERPARAMETRES_RN_PAR_DEFAUT = {
    "hidden_layer_sizes": [32, 16],
    "activation": "relu",
    "max_iter": 2000,
}

METHODES = ("regression_lineaire", "reseau_neurones")
LIBELLES_METHODES = {
    "regression_lineaire": "Régression linéaire",
    "reseau_neurones": "Réseau de neurones",
}


@dataclass
class ResultatEntrainement:
    """Résultat de l'entraînement et de l'évaluation d'une méthode sur un jeu de données."""

    methode: str
    pipeline: Pipeline
    metriques: dict[str, float]
    quantile_bas: float
    quantile_haut: float
    nb_lignes_apprentissage: int
    nb_lignes_test: int
    convergence_ok: bool
    residus_test: list[float] = field(default_factory=list)
    predictions_test: list[float] = field(default_factory=list)
    coefficients: dict[str, float] | None = None


def decouper_chronologique(
    x: pd.DataFrame, y: pd.Series, part_test: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """80 % les plus anciennes lignes pour l'apprentissage, 20 % les plus récentes pour le test.

    ``x`` et ``y`` doivent déjà être triés par date croissante. Aucun mélange aléatoire :
    le découpage est purement chronologique, pour ne jamais laisser le test « voir » un
    exemple plus ancien que ceux de l'apprentissage.
    """
    n = len(x)
    n_test = max(1, round(n * part_test))
    n_train = n - n_test
    return x.iloc[:n_train], x.iloc[n_train:], y.iloc[:n_train], y.iloc[n_train:]


def _construire_pipeline_rl() -> Pipeline:
    return Pipeline([("normalisation", StandardScaler()), ("regression", LinearRegression())])


def _construire_pipeline_rn(hyperparametres: dict) -> Pipeline:
    parametres = {**HYPERPARAMETRES_RN_PAR_DEFAUT, **(hyperparametres or {})}
    return Pipeline(
        [
            ("normalisation", StandardScaler()),
            (
                "reseau",
                MLPRegressor(
                    hidden_layer_sizes=tuple(parametres["hidden_layer_sizes"]),
                    activation=parametres["activation"],
                    max_iter=parametres["max_iter"],
                    early_stopping=True,
                    random_state=GRAINE_ALEATOIRE,
                ),
            ),
        ]
    )


def calculer_metriques(y_reel: pd.Series, y_predit: np.ndarray) -> dict[str, float]:
    """MAE, RMSE, MAPE (jours à réel nul exclus) et biais (%)."""
    ecarts = y_reel.to_numpy() - y_predit
    mae = float(np.mean(np.abs(ecarts)))
    rmse = float(np.sqrt(np.mean(ecarts**2)))
    non_nuls = y_reel.to_numpy() != 0
    mape = (
        float(np.mean(np.abs(ecarts[non_nuls]) / y_reel.to_numpy()[non_nuls]) * 100)
        if non_nuls.any()
        else float("nan")
    )
    somme_reel = float(y_reel.sum())
    biais = float(-ecarts.sum() / somme_reel * 100) if somme_reel else float("nan")
    return {"mae": mae, "rmse": rmse, "mape": mape, "biais": biais}


def quantiles_residus(residus: np.ndarray, niveau_confiance: float) -> tuple[float, float]:
    """Quantiles des résidus du jeu de test pour l'intervalle de confiance (UC11)."""
    marge = (1 - niveau_confiance) / 2
    return float(np.quantile(residus, marge)), float(np.quantile(residus, 1 - marge))


def couverture_intervalle(
    y_reel: np.ndarray, y_predit: np.ndarray, bas: float, haut: float
) -> float:
    """Part des valeurs réelles comprises dans [prédiction + bas ; prédiction + haut], en %."""
    dans_intervalle = (y_reel >= y_predit + bas) & (y_reel <= y_predit + haut)
    return float(np.mean(dans_intervalle) * 100)


def coefficients_lisibles(pipeline: Pipeline, colonnes: list[str]) -> dict[str, float]:
    """Coefficients de la régression linéaire (espace centré-réduit), avec leurs libellés."""
    modele = pipeline.named_steps["regression"]
    coefficients = {"Constante (variables à leur moyenne)": float(modele.intercept_)}
    for nom, coef in zip(colonnes, modele.coef_, strict=True):
        coefficients[libelle_colonne(nom)] = float(coef)
    return coefficients


def entrainer_et_evaluer(
    x: pd.DataFrame,
    y: pd.Series,
    methode: str,
    part_test: float = 0.2,
    niveau_confiance: float = 0.8,
    hyperparametres_rn: dict | None = None,
) -> ResultatEntrainement:
    """Entraîne et évalue une méthode (UC08 + UC09) sur un jeu de données déjà trié par date."""
    x_train, x_test, y_train, y_test = decouper_chronologique(x, y, part_test)
    convergence_ok = True
    if methode == "regression_lineaire":
        pipeline = _construire_pipeline_rl()
        pipeline.fit(x_train, y_train)
        coefficients = coefficients_lisibles(pipeline, list(x.columns))
    elif methode == "reseau_neurones":
        pipeline = _construire_pipeline_rn(hyperparametres_rn or {})
        with warnings.catch_warnings(record=True) as capturees:
            warnings.simplefilter("always", ConvergenceWarning)
            pipeline.fit(x_train, y_train)
        convergence_ok = not any(issubclass(w.category, ConvergenceWarning) for w in capturees)
        coefficients = None
    else:
        raise ValueError(f"Méthode de prévision inconnue : « {methode} ».")

    predictions_test = pipeline.predict(x_test)
    metriques = calculer_metriques(y_test, predictions_test)
    residus_test = y_test.to_numpy() - predictions_test
    quantile_bas, quantile_haut = quantiles_residus(residus_test, niveau_confiance)
    metriques["couverture_ic"] = couverture_intervalle(
        y_test.to_numpy(), predictions_test, quantile_bas, quantile_haut
    )

    return ResultatEntrainement(
        methode=methode,
        pipeline=pipeline,
        metriques=metriques,
        quantile_bas=quantile_bas,
        quantile_haut=quantile_haut,
        nb_lignes_apprentissage=len(x_train),
        nb_lignes_test=len(x_test),
        convergence_ok=convergence_ok,
        residus_test=residus_test.tolist(),
        predictions_test=predictions_test.tolist(),
        coefficients=coefficients,
    )


def entrainer_methodes(
    x: pd.DataFrame,
    y: pd.Series,
    part_test: float = 0.2,
    niveau_confiance: float = 0.8,
    hyperparametres_rn: dict | None = None,
) -> dict[str, ResultatEntrainement]:
    """Entraîne et évalue les deux méthodes (RL et RN) sur le même jeu de données."""
    return {
        methode: entrainer_et_evaluer(
            x, y, methode, part_test, niveau_confiance, hyperparametres_rn
        )
        for methode in METHODES
    }
