"""Modèles de prévision : construction des variables, découpage chronologique,
entraînement et passage heures → effectif/équipements. Aucune base de données requise."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ml import entrainement, prediction, preparation


# ---------------------------------------------------------------------
# preparation.py
# ---------------------------------------------------------------------
def _dates(n: int, depart: date = date(2026, 1, 5)) -> list[date]:  # 5 janvier 2026 = lundi
    return [depart + timedelta(days=i) for i in range(n)]


def test_construire_variables_volume_et_pic():
    dates = _dates(3)
    x = preparation.construire_variables(
        dates,
        [100.0, 200.0, 300.0],
        [False, True, False],
        variables_actives=["volume", "indicateur_pic"],
    )
    assert list(x.columns) == ["volume", "indicateur_pic"]
    assert x["volume"].tolist() == [100.0, 200.0, 300.0]
    assert x["indicateur_pic"].tolist() == [0, 1, 0]


def test_construire_variables_jour_semaine_one_hot():
    dates = _dates(7)  # lundi à dimanche
    x = preparation.construire_variables(
        dates, [0] * 7, [False] * 7, variables_actives=["jour_semaine"]
    )
    assert list(x.columns) == preparation.COLONNES_JOUR
    # Chaque ligne n'a qu'un seul jour actif, dans l'ordre lundi -> dimanche.
    assert (x.to_numpy() == np.eye(7, dtype=int)).all()


def test_construire_variables_mois_cyclique():
    dates = [date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1)]
    x = preparation.construire_variables(
        dates, [0, 0, 0], [False, False, False], variables_actives=["mois_cyclique"]
    )
    assert list(x.columns) == ["mois_sin", "mois_cos"]
    # Janvier (mois 1) et juillet (mois 7) sont à l'opposé sur le cercle.
    assert x["mois_cos"].iloc[0] == pytest.approx(-x["mois_cos"].iloc[2], abs=1e-9)
    assert x["mois_sin"].iloc[0] == pytest.approx(-x["mois_sin"].iloc[2], abs=1e-9)


def test_moyenne_mobile_aucune_fuite_future():
    dates = _dates(10)
    volumes = [float(i) for i in range(10)]  # 0, 1, 2, ..., 9
    x = preparation.construire_variables(
        dates, volumes, [False] * 10, variables_actives=["moyenne_mobile_7j"]
    )
    # Les 7 premières lignes n'ont pas assez d'historique : NaN.
    assert x["moyenne_mobile_7j"].iloc[:7].isna().all()
    # Ligne 7 (volume=7) : moyenne des volumes 0..6 (jamais le volume du jour même).
    assert x["moyenne_mobile_7j"].iloc[7] == pytest.approx(np.mean(range(0, 7)))
    # Ligne 8 (volume=8) : moyenne des volumes 1..7.
    assert x["moyenne_mobile_7j"].iloc[8] == pytest.approx(np.mean(range(1, 8)))


def test_lignes_utilisables_exclut_les_nan():
    x = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": [1.0, 2.0, np.nan]})
    assert preparation.lignes_utilisables(x).tolist() == [True, False, False]


def test_cibles():
    assert preparation.cible_heures([80, 90], [5, 10]).tolist() == [75.0, 80.0]
    assert preparation.cible_equipements([3, 4]).tolist() == [3.0, 4.0]


def test_libelle_colonne_connue_et_inconnue():
    assert preparation.libelle_colonne("volume") == "Volume"
    assert preparation.libelle_colonne("jour_lundi") == "Jour : Lundi"
    assert preparation.libelle_colonne("xyz") == "xyz"


# ---------------------------------------------------------------------
# entrainement.py
# ---------------------------------------------------------------------
def test_decoupage_chronologique_ordre_et_tailles():
    x = pd.DataFrame({"v": range(100)})
    y = pd.Series(range(100))
    x_train, x_test, y_train, y_test = entrainement.decouper_chronologique(x, y, part_test=0.2)
    assert len(x_train) == 80 and len(x_test) == 20
    # Aucun mélange : les indices de test suivent strictement ceux d'apprentissage.
    assert x_train["v"].max() < x_test["v"].min()
    assert y_train.tolist() == list(range(80))
    assert y_test.tolist() == list(range(80, 100))


def test_calculer_metriques_valeurs_connues():
    y_reel = pd.Series([100.0, 0.0, 50.0])
    y_predit = np.array([110.0, 5.0, 45.0])
    metriques = entrainement.calculer_metriques(y_reel, y_predit)
    assert metriques["mae"] == pytest.approx((10 + 5 + 5) / 3)
    assert metriques["rmse"] == pytest.approx(np.sqrt((100 + 25 + 25) / 3))
    # MAPE exclut la ligne où le réel vaut 0.
    assert metriques["mape"] == pytest.approx((10 / 100 + 5 / 50) / 2 * 100)
    # Biais = (prévu - réel) / réel, en % : (110-100)+(5-0)+(45-50) = 10, / somme réel 150.
    assert metriques["biais"] == pytest.approx(10 / 150 * 100)


def test_calculer_metriques_tous_reels_nuls():
    metriques = entrainement.calculer_metriques(pd.Series([0.0, 0.0]), np.array([1.0, 2.0]))
    assert np.isnan(metriques["mape"]) and np.isnan(metriques["biais"])


def test_quantiles_residus():
    residus = np.arange(-100, 101)  # -100..100, distribution uniforme connue
    bas, haut = entrainement.quantiles_residus(residus, niveau_confiance=0.8)
    assert bas == pytest.approx(-80, abs=1)
    assert haut == pytest.approx(80, abs=1)


def test_couverture_intervalle():
    y_reel = np.array([10.0, 20.0, 30.0, 100.0])
    y_predit = np.array([10.0, 20.0, 30.0, 30.0])
    # bornes [-2, +2] : les trois premières valeurs sont couvertes, la dernière non.
    assert entrainement.couverture_intervalle(y_reel, y_predit, -2, 2) == pytest.approx(75.0)


def _jeu_lineaire(n: int = 150) -> tuple[pd.DataFrame, pd.Series]:
    """Relation linéaire exacte (heures = 0,05 x volume + 10) : la RL doit être quasi parfaite."""
    dates = _dates(n)
    volumes = [800 + 50 * (i % 14) for i in range(n)]
    x = preparation.construire_variables(dates, volumes, [False] * n, variables_actives=["volume"])
    y = pd.Series([0.05 * v + 10 for v in volumes])
    return x, y


def test_entrainement_regression_lineaire_precise_sur_relation_lineaire():
    x, y = _jeu_lineaire()
    resultat = entrainement.entrainer_et_evaluer(x, y, "regression_lineaire")
    assert resultat.methode == "regression_lineaire"
    assert resultat.convergence_ok is True
    assert resultat.nb_lignes_apprentissage == 120 and resultat.nb_lignes_test == 30
    assert resultat.metriques["mae"] < 0.5  # relation exacte : erreur quasi nulle
    assert resultat.coefficients is not None
    assert "Volume" in resultat.coefficients
    assert "couverture_ic" in resultat.metriques
    assert len(resultat.residus_test) == 30


def test_entrainement_reseau_neurones_produit_des_metriques():
    x, y = _jeu_lineaire()
    resultat = entrainement.entrainer_et_evaluer(x, y, "reseau_neurones")
    assert resultat.methode == "reseau_neurones"
    assert resultat.coefficients is None
    assert isinstance(resultat.convergence_ok, bool)
    assert set(resultat.metriques) >= {"mae", "rmse", "mape", "biais", "couverture_ic"}


def test_entrainer_methodes_renvoie_les_deux():
    x, y = _jeu_lineaire()
    resultats = entrainement.entrainer_methodes(x, y)
    assert set(resultats) == {"regression_lineaire", "reseau_neurones"}


def test_methode_inconnue_refusee():
    x, y = _jeu_lineaire()
    with pytest.raises(ValueError, match="inconnue"):
        entrainement.entrainer_et_evaluer(x, y, "arbre_de_decision")


def test_graine_aleatoire_fixee_reproductible():
    x, y = _jeu_lineaire()
    r1 = entrainement.entrainer_et_evaluer(x, y, "reseau_neurones")
    r2 = entrainement.entrainer_et_evaluer(x, y, "reseau_neurones")
    assert r1.predictions_test == pytest.approx(r2.predictions_test)


# ---------------------------------------------------------------------
# prediction.py
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "heures,duree_poste,attendu",
    [(75, 7.5, 10), (76, 7.5, 11), (0, 7.5, 0), (-5, 7.5, 0), (112.5, 7.5, 15), (7.5, 7.5, 1)],
)
def test_heures_vers_effectif(heures, duree_poste, attendu):
    assert prediction.heures_vers_effectif(heures, duree_poste) == attendu


def test_heures_vers_effectif_duree_poste_invalide():
    with pytest.raises(ValueError, match="strictement positive"):
        prediction.heures_vers_effectif(10, 0)


@pytest.mark.parametrize("valeur,attendu", [(2.1, 3), (2.0, 2), (0, 0), (-3, 0), (2.999, 3)])
def test_arrondi_entier_superieur(valeur, attendu):
    assert prediction.arrondi_entier_superieur(valeur) == attendu


def test_ramener_positif():
    assert prediction.ramener_positif(-5) == 0.0
    assert prediction.ramener_positif(5) == 5


class _PipelineFactice:
    """Simule un pipeline scikit-learn pour tester ``predire`` sans entraînement réel."""

    def predict(self, x):
        return np.array(x["volume"])


def test_predire_intervalle_de_confiance_et_valeurs_negatives_ramenees():
    x = pd.DataFrame({"volume": [10.0, -5.0, 100.0]})
    resultat = prediction.predire(_PipelineFactice(), x, quantile_bas=-20, quantile_haut=20)
    assert resultat["prediction"].tolist() == [10.0, 0.0, 100.0]
    assert resultat["ic_bas"].tolist() == [0.0, 0.0, 80.0]  # 10-20=-10 -> 0 ; -5-20 -> 0
    assert resultat["ic_haut"].tolist() == [30.0, 15.0, 120.0]  # -5+20=15 : positif, pas ramené


def test_moyenne_mobile_avec_historique_bascule_sur_l_horizon():
    historique = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]  # 7 valeurs
    horizon = [80.0, 90.0]
    resultat = prediction.moyenne_mobile_avec_historique(historique, horizon, fenetre=7)
    # Jour 1 de l'horizon : moyenne des 7 derniers jours d'historique.
    assert resultat[0] == pytest.approx(np.mean(historique))
    # Jour 2 : la fenêtre glisse et inclut la première prédiction de l'horizon.
    assert resultat[1] == pytest.approx(np.mean(historique[1:] + [80.0]))
