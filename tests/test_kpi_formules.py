"""Formules et règles de statut des KPI (UC15, UC16, UC17) : données construites à la main,
résultats connus. Aucune base de données requise."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services import kpi


# ---------------------------------------------------------------------
# Règles de statut
# ---------------------------------------------------------------------
def test_statut_baisse():
    assert kpi.statut_baisse(3, seuil_orange=5, seuil_rouge=10) == "vert"
    assert kpi.statut_baisse(5, seuil_orange=5, seuil_rouge=10) == "vert"  # borne incluse
    assert kpi.statut_baisse(7, seuil_orange=5, seuil_rouge=10) == "orange"
    assert kpi.statut_baisse(10, seuil_orange=5, seuil_rouge=10) == "orange"
    assert kpi.statut_baisse(11, seuil_orange=5, seuil_rouge=10) == "rouge"


def test_statut_hausse():
    assert kpi.statut_hausse(98, seuil_orange=95, seuil_rouge=90) == "vert"
    assert kpi.statut_hausse(95, seuil_orange=95, seuil_rouge=90) == "vert"  # borne incluse
    assert kpi.statut_hausse(92, seuil_orange=95, seuil_rouge=90) == "orange"
    assert kpi.statut_hausse(90, seuil_orange=95, seuil_rouge=90) == "orange"
    assert kpi.statut_hausse(85, seuil_orange=95, seuil_rouge=90) == "rouge"


def test_statut_plage():
    assert kpi.statut_plage(10, valeur_min=8, valeur_max=12, marge=2) == "vert"
    assert kpi.statut_plage(8, valeur_min=8, valeur_max=12, marge=2) == "vert"  # borne incluse
    assert kpi.statut_plage(12, valeur_min=8, valeur_max=12, marge=2) == "vert"
    assert kpi.statut_plage(6, valeur_min=8, valeur_max=12, marge=2) == "orange"  # en dessous
    assert kpi.statut_plage(14, valeur_min=8, valeur_max=12, marge=2) == "orange"  # au-dessus
    assert kpi.statut_plage(5, valeur_min=8, valeur_max=12, marge=2) == "rouge"
    assert kpi.statut_plage(15, valeur_min=8, valeur_max=12, marge=2) == "rouge"


def test_calculer_statut_gris_sans_valeur_ni_objectif():
    objectif = {"seuil_orange": 5, "seuil_rouge": 10}
    assert kpi.calculer_statut("baisse", None, objectif) == "gris"
    assert kpi.calculer_statut("baisse", 3, None) == "gris"
    assert kpi.calculer_statut("information", 3, objectif) == "gris"


def test_calculer_statut_dispatch_selon_le_sens():
    assert kpi.calculer_statut("baisse", 3, {"seuil_orange": 5, "seuil_rouge": 10}) == "vert"
    assert kpi.calculer_statut("hausse", 98, {"seuil_orange": 95, "seuil_rouge": 90}) == "vert"
    plage = {"valeur_min": 8, "valeur_max": 12, "seuil_orange": 2}
    assert kpi.calculer_statut("plage", 10, plage) == "vert"
    assert kpi.calculer_statut("plage", 15, plage) == "rouge"


# ---------------------------------------------------------------------
# Formules de précision (rapprochements réel / prévu)
# ---------------------------------------------------------------------
def _rappro(
    date_jour,
    heures_reelles,
    heures_prevues,
    ic_bas=0.0,
    ic_haut=100.0,
    equipements_reels=None,
    equipements_prevus=None,
    comparable=True,
):
    return {
        "date_jour": date_jour,
        "heures_reelles": heures_reelles,
        "heures_prevues": heures_prevues,
        "ic_bas": ic_bas,
        "ic_haut": ic_haut,
        "equipements_reels": equipements_reels,
        "equipements_prevus": equipements_prevus,
        "comparable": comparable,
    }


def test_calculer_mae():
    r = [
        _rappro(date(2026, 1, 1), 100.0, 90.0),
        _rappro(date(2026, 1, 2), 80.0, 100.0),
    ]
    # |100-90| = 10, |80-100| = 20 -> moyenne 15
    assert kpi.calculer_mae(r) == 15.0


def test_calculer_mae_ignore_les_jours_non_comparables():
    r = [
        _rappro(date(2026, 1, 1), 100.0, 90.0),
        _rappro(date(2026, 1, 2), None, 100.0, comparable=False),
    ]
    assert kpi.calculer_mae(r) == 10.0


def test_calculer_mae_vide():
    assert kpi.calculer_mae([]) is None


def test_calculer_rmse():
    r = [
        _rappro(date(2026, 1, 1), 100.0, 90.0),  # écart 10
        _rappro(date(2026, 1, 2), 100.0, 110.0),  # écart 10
    ]
    assert kpi.calculer_rmse(r) == 10.0


def test_calculer_mape_exclut_les_reels_nuls():
    r = [
        _rappro(date(2026, 1, 1), 100.0, 110.0),  # 10 %
        _rappro(date(2026, 1, 2), 0.0, 50.0),  # exclu (réel nul)
    ]
    assert kpi.calculer_mape(r) == pytest.approx(10.0)


def test_calculer_mape_vide_si_tous_les_reels_nuls():
    r = [_rappro(date(2026, 1, 1), 0.0, 50.0)]
    assert kpi.calculer_mape(r) is None


def test_calculer_biais_positif_si_surestimation():
    r = [
        _rappro(date(2026, 1, 1), 100.0, 120.0),
        _rappro(date(2026, 1, 2), 100.0, 120.0),
    ]
    # Σ(prévu - réel) / Σréel = 40 / 200 = 20 %
    assert kpi.calculer_biais(r) == pytest.approx(20.0)


def test_calculer_biais_negatif_si_sous_estimation():
    r = [_rappro(date(2026, 1, 1), 100.0, 60.0)]
    assert kpi.calculer_biais(r) == pytest.approx(-40.0)


def test_calculer_couverture_ic():
    r = [
        _rappro(date(2026, 1, 1), 50.0, 50.0, ic_bas=40.0, ic_haut=60.0),  # dans l'IC
        _rappro(date(2026, 1, 2), 70.0, 50.0, ic_bas=40.0, ic_haut=60.0),  # hors IC
    ]
    assert kpi.calculer_couverture_ic(r) == pytest.approx(50.0)


def test_calculer_ecart_equipements():
    r = [
        _rappro(date(2026, 1, 1), 1, 1, equipements_reels=5, equipements_prevus=3),
        _rappro(date(2026, 1, 2), 1, 1, equipements_reels=4, equipements_prevus=4),
    ]
    assert kpi.calculer_ecart_equipements(r) == pytest.approx(1.0)


def test_calculer_taux_victoire():
    rl = [
        _rappro(date(2026, 1, 1), 100.0, 90.0),  # erreur 10
        _rappro(date(2026, 1, 2), 100.0, 100.0),  # erreur 0
    ]
    rn = [
        _rappro(date(2026, 1, 1), 100.0, 95.0),  # erreur 5 (RN gagne)
        _rappro(date(2026, 1, 2), 100.0, 110.0),  # erreur 10 (RL gagne)
    ]
    assert kpi.calculer_taux_victoire(rl, rn) == pytest.approx(50.0)


def test_calculer_taux_victoire_aucun_jour_commun():
    rl = [_rappro(date(2026, 1, 1), 100.0, 90.0)]
    rn = [_rappro(date(2026, 1, 2), 100.0, 90.0)]
    assert kpi.calculer_taux_victoire(rl, rn) is None


# ---------------------------------------------------------------------
# Formules RH, équipements, coûts et service
# ---------------------------------------------------------------------
def _sommes(**champs) -> dict:
    base = {
        "volume": 0.0,
        "heures_travaillees": 0.0,
        "heures_necessaires": 0.0,
        "heures_sup": 0.0,
        "heures_interim": 0.0,
        "heures_absence": 0.0,
        "heures_inactives": 0.0,
        "heures_usage_equipement": 0.0,
        "heures_disponibles_equipement": 0.0,
        "heures_panne_equipement": 0.0,
        "cout_rh": 0.0,
        "commandes_a_temps": 0,
        "commandes_totales": 0,
    }
    base.update(champs)
    return base


def test_calculer_productivite():
    sommes = _sommes(volume=1000.0, heures_travaillees=100.0)
    assert kpi.calculer_productivite(sommes) == pytest.approx(10.0)


def test_calculer_productivite_sans_heures():
    assert kpi.calculer_productivite(_sommes()) is None


def test_calculer_adequation():
    sommes = _sommes(heures_necessaires=80.0)
    assert kpi.calculer_adequation(sommes, heures_planifiees=100.0) == pytest.approx(125.0)


def test_calculer_taux_hs():
    sommes = _sommes(heures_sup=5.0, heures_travaillees=100.0)
    assert kpi.calculer_taux_hs(sommes) == pytest.approx(5.0)


def test_calculer_taux_interim():
    sommes = _sommes(heures_interim=20.0, heures_travaillees=100.0)
    assert kpi.calculer_taux_interim(sommes) == pytest.approx(20.0)


def test_calculer_taux_sous_charge():
    sommes = _sommes(heures_inactives=10.0, heures_travaillees=100.0)
    assert kpi.calculer_taux_sous_charge(sommes) == pytest.approx(10.0)


def test_calculer_taux_absenteisme():
    sommes = _sommes(heures_absence=10.0, heures_travaillees=90.0)
    # 10 / (90 + 10) = 10 %
    assert kpi.calculer_taux_absenteisme(sommes) == pytest.approx(10.0)


def test_calculer_delai_anticipation():
    alertes = [
        {"date_concernee": date(2026, 1, 10), "date_creation": datetime(2026, 1, 5)},
        {"date_concernee": date(2026, 1, 10), "date_creation": datetime(2026, 1, 8)},
    ]
    # (5 + 2) / 2 = 3.5 jours
    assert kpi.calculer_delai_anticipation(alertes) == pytest.approx(3.5)


def test_calculer_delai_anticipation_vide():
    assert kpi.calculer_delai_anticipation([]) is None


def test_calculer_taux_util_eqp():
    sommes = _sommes(heures_usage_equipement=75.0, heures_disponibles_equipement=100.0)
    assert kpi.calculer_taux_util_eqp(sommes) == pytest.approx(75.0)


def test_calculer_taux_dispo_eqp():
    sommes = _sommes(heures_disponibles_equipement=95.0, heures_panne_equipement=5.0)
    assert kpi.calculer_taux_dispo_eqp(sommes) == pytest.approx(95.0)


def test_calculer_taux_dispo_eqp_sans_donnees():
    assert kpi.calculer_taux_dispo_eqp(_sommes()) is None


def test_calculer_cout_unite():
    sommes = _sommes(cout_rh=500.0, volume=1000.0)
    assert kpi.calculer_cout_unite(sommes) == pytest.approx(0.5)


def test_calculer_ecart_cout():
    sommes = _sommes(cout_rh=1100.0)
    assert kpi.calculer_ecart_cout(sommes, cout_planifie=1000.0) == pytest.approx(10.0)


def test_calculer_ecart_cout_sans_plan():
    assert kpi.calculer_ecart_cout(_sommes(cout_rh=100.0), cout_planifie=0.0) is None


def test_calculer_taux_a_temps():
    sommes = _sommes(commandes_a_temps=95, commandes_totales=100)
    assert kpi.calculer_taux_a_temps(sommes) == pytest.approx(95.0)


# ---------------------------------------------------------------------
# Cibles relatives (PRODUCTIVITE, COUT_UNITE)
# ---------------------------------------------------------------------
def test_resoudre_objectif_productivite_relative():
    objectif = {
        "seuils_relatifs": True,
        "valeur_cible": None,
        "seuil_orange": 95.0,
        "seuil_rouge": 90.0,
    }
    # 90 premiers jours : 1000 unités traitées en 100 heures -> cible = 10 unités/heure
    resolu = kpi._resoudre_objectif(objectif, "PRODUCTIVITE", (1000.0, 100.0, 0.0))
    assert resolu["valeur_cible"] == pytest.approx(10.0)
    assert resolu["seuil_orange"] == pytest.approx(9.5)  # 95 % de la cible
    assert resolu["seuil_rouge"] == pytest.approx(9.0)  # 90 % de la cible


def test_resoudre_objectif_cout_unite_relatif():
    objectif = {
        "seuils_relatifs": True,
        "valeur_cible": None,
        "seuil_orange": 105.0,
        "seuil_rouge": 110.0,
    }
    # 90 premiers jours : coût 500 pour 1000 unités -> cible = 0.5 par unité
    resolu = kpi._resoudre_objectif(objectif, "COUT_UNITE", (1000.0, 0.0, 500.0))
    assert resolu["valeur_cible"] == pytest.approx(0.5)
    assert resolu["seuil_orange"] == pytest.approx(0.525)
    assert resolu["seuil_rouge"] == pytest.approx(0.55)


def test_resoudre_objectif_non_relatif_inchange():
    objectif = {"seuils_relatifs": False, "valeur_cible": 42.0}
    assert kpi._resoudre_objectif(objectif, "TAUX_HS", (0.0, 0.0, 0.0)) == objectif


def test_resoudre_objectif_absent():
    assert kpi._resoudre_objectif(None, "PRODUCTIVITE", (0.0, 0.0, 0.0)) is None


# ---------------------------------------------------------------------
# Tendance (écran KPI et cibles)
# ---------------------------------------------------------------------
def test_tendance_hausse_favorable_pour_un_kpi_hausse():
    precedentes = [{"valeur": 95.0, "sens": "hausse"}, {"valeur": 90.0, "sens": "hausse"}]
    assert kpi._tendance(precedentes) == "↑"


def test_tendance_hausse_defavorable_pour_un_kpi_baisse():
    precedentes = [{"valeur": 15.0, "sens": "baisse"}, {"valeur": 10.0, "sens": "baisse"}]
    assert kpi._tendance(precedentes) == "↓"


def test_tendance_stable():
    precedentes = [{"valeur": 10.0, "sens": "baisse"}, {"valeur": 10.0, "sens": "baisse"}]
    assert kpi._tendance(precedentes) == "→"


def test_tendance_insuffisamment_de_donnees():
    assert kpi._tendance([{"valeur": 10.0, "sens": "baisse"}]) == "→"
    assert kpi._tendance([]) == "→"
