"""Recommandations : suggestions UC06, UC18/UC21 et interprétation des KPI (UC17). Données
construites à la main, aucune base de données requise."""

from __future__ import annotations

from app.bd.catalogue_kpi import CATALOGUE
from app.libelles import TYPES_ALERTE
from app.services import recommandations


# ---------------------------------------------------------------------
# UC06 · Suggestions de correction
# ---------------------------------------------------------------------
def test_suggestion_rejet_colonne_connue():
    texte = recommandations.suggestion_rejet("heures_travaillees", "peu importe")
    assert "effectif" in texte.lower()


def test_suggestion_rejet_champ_obligatoire():
    texte = recommandations.suggestion_rejet("cout_rh", "Le champ « Coût RH » est obligatoire.")
    assert "vide" in texte.lower()


def test_suggestion_rejet_doublon():
    # "indicateur_pic" n'a pas de suggestion dédiée : le texte vient de la détection du mot
    # « doublon » dans la raison.
    texte = recommandations.suggestion_rejet(
        "indicateur_pic", "Doublon : site, zone et date déjà présents dans ce fichier."
    )
    assert "doublon" in texte.lower() or "double" in texte.lower()


def test_suggestion_rejet_nombre_invalide():
    texte = recommandations.suggestion_rejet("cout_rh", "« Coût RH » doit être un nombre.")
    assert "nombre" in texte.lower()


def test_suggestion_rejet_defaut():
    texte = recommandations.suggestion_rejet("colonne_inconnue", "raison quelconque")
    assert texte == recommandations._SUGGESTION_DEFAUT_REJET


def test_suggestion_avertissement_non_vide():
    assert recommandations.suggestion_avertissement("volume_traite")


# ---------------------------------------------------------------------
# UC18, UC21 · Suggestions d'action face à une alerte
# ---------------------------------------------------------------------
def test_suggestion_alerte_couvre_tous_les_types():
    """Chaque type d'alerte du catalogue (app.libelles.TYPES_ALERTE) a une suggestion propre,
    pas seulement le texte par défaut."""
    for type_alerte in TYPES_ALERTE:
        texte = recommandations.suggestion_alerte(type_alerte)
        assert texte != recommandations._SUGGESTION_DEFAUT_ALERTE


def test_suggestion_alerte_type_inconnu_renvoie_le_defaut():
    assert (
        recommandations.suggestion_alerte("type_qui_n_existe_pas")
        == recommandations._SUGGESTION_DEFAUT_ALERTE
    )


# ---------------------------------------------------------------------
# UC17 · Interprétation des KPI hors cible
# ---------------------------------------------------------------------
def test_interpreter_kpi_sens_baisse():
    interpretation = recommandations.interpreter_kpi("TAUX_HS", "baisse", 20.0, 5.0)
    assert interpretation is not None
    assert "heures supplémentaires" in interpretation.explication.lower()
    assert interpretation.conseil


def test_interpreter_kpi_kpi_information_renvoie_none():
    """Un KPI d'information (MAE_H, RMSE_H, TAUX_VICTOIRE) n'a pas de cible ni de statut
    hors-cible possible : pas d'interprétation."""
    assert recommandations.interpreter_kpi("MAE_H", "information", 12.0, None) is None


def test_interpreter_kpi_plage_direction_basse():
    interpretation = recommandations.interpreter_kpi("ADEQUATION", "plage", 80.0, 100.0)
    assert interpretation is not None
    assert "sous-effectif" in interpretation.explication.lower()


def test_interpreter_kpi_plage_direction_haute():
    interpretation = recommandations.interpreter_kpi("ADEQUATION", "plage", 130.0, 100.0)
    assert interpretation is not None
    assert "sureffectif" in interpretation.explication.lower()


def test_interpreter_kpi_plage_sans_cible_renvoie_none():
    assert recommandations.interpreter_kpi("ADEQUATION", "plage", 80.0, None) is None


def test_interpreter_kpi_couvre_les_kpi_avec_objectif():
    """Tout KPI du catalogue dont le sens n'est pas « information » a une interprétation
    (une direction pour baisse/hausse, les deux pour plage)."""
    for definition in CATALOGUE:
        if definition.sens == "information":
            continue
        if definition.sens == "plage":
            assert definition.code in recommandations._INTERPRETATIONS_PLAGE, definition.code
        else:
            assert (
                definition.code in recommandations._INTERPRETATIONS_UNE_DIRECTION
            ), definition.code
