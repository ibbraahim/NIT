"""Thèmes sombre et clair : palettes, préférence mémorisée, bascule et rendu des écrans."""

from __future__ import annotations

import json

import pytest

from tests.conftest import connecter

pytestmark = [pytest.mark.gui, pytest.mark.integration]


@pytest.fixture
def theme_sombre_a_la_fin():
    """Rend le thème sombre (défaut) après le test : la palette est globale au processus."""
    yield
    from app.gui import style

    style.definir_theme("sombre")


def test_les_deux_palettes_definissent_les_memes_couleurs():
    from app.gui.style import THEMES

    assert set(THEMES) == {"sombre", "clair"}
    assert set(THEMES["sombre"]) == set(THEMES["clair"])
    for palette in THEMES.values():
        assert all(valeur.startswith("#") and len(valeur) == 7 for valeur in palette.values())


def test_preferences_lecture_ecriture_et_fichier_illisible(tmp_path, monkeypatch):
    from app.gui import preferences

    fichier = tmp_path / "prefs.json"
    monkeypatch.setenv("WORKLY_PREFERENCES", str(fichier))
    assert preferences.lire() == {}
    preferences.ecrire("theme", "clair")
    assert preferences.lire() == {"theme": "clair"}
    assert json.loads(fichier.read_text(encoding="utf-8")) == {"theme": "clair"}
    fichier.write_text("{ pas du json", encoding="utf-8")
    assert preferences.lire() == {}


def test_theme_inconnu_revient_au_defaut(theme_sombre_a_la_fin):
    from app.gui import style

    style.definir_theme("fluo")
    assert style.theme_courant() == "sombre"


def test_bascule_de_theme_garde_l_ecran_et_memorise_le_choix(application, theme_sombre_a_la_fin):
    from app.gui import preferences, style

    connecter(application, "resp")
    application.naviguer("previsions")
    application.racine.update()
    assert style.theme_courant() == "sombre"

    application.basculer_theme()
    application.racine.update()
    assert style.theme_courant() == "clair"
    assert preferences.lire()["theme"] == "clair"
    assert application.contexte is not None
    assert application.vue_courante == "previsions"
    assert style.COULEURS["fond"] == style.THEMES["clair"]["fond"]

    application.basculer_theme()
    application.racine.update()
    assert style.theme_courant() == "sombre"
    assert preferences.lire()["theme"] == "sombre"
    assert application.erreurs == []


def test_bascule_sur_l_ecran_de_connexion(application, theme_sombre_a_la_fin):
    from app.gui import style

    application.basculer_theme()
    application.racine.update()
    assert style.theme_courant() == "clair"
    assert application.contexte is None
    assert application._cadre.winfo_exists()


@pytest.mark.parametrize("identifiant", ["planif", "resp", "admin"])
def test_chaque_ecran_s_ouvre_en_theme_clair(application, identifiant, theme_sombre_a_la_fin):
    from app.gui import style
    from app.gui.vues import ecrans_autorises

    application.basculer_theme()
    assert style.theme_courant() == "clair"
    connecter(application, identifiant)
    for definition in ecrans_autorises(application.contexte.role):
        application.naviguer(definition.cle)
        application.racine.update()
        vue = application.vues[definition.cle]
        if hasattr(vue, "onglets"):
            for index in range(len(vue.onglets.tabs())):
                vue.onglets.select(index)
                application.racine.update()
    assert application.erreurs == []
