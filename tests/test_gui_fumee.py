"""Test de fumée de l'interface : chaque écran s'ouvre pour chaque rôle, sans exception.

Sous Linux sans affichage : ``xvfb-run -a python -m pytest -m gui``.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = [pytest.mark.gui, pytest.mark.integration]

COMPTES = {
    "admin": "Admin2026!",
    "planif": "Planif2026!",
    "resp": "Resp2026!",
    "direction": "Direction2026!",
}


@pytest.fixture
def application(demo_referentiels, monkeypatch):
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("Aucun affichage disponible : lancez les tests avec xvfb-run.")
    tk = pytest.importorskip("tkinter")
    try:
        racine = tk.Tk()
    except tk.TclError:
        pytest.skip("Impossible d'ouvrir une fenêtre Tk.")
    erreurs: list[str] = []

    def erreur_bloquante(_parent, message, *_args, **_kwargs):
        erreurs.append(message)

    import app.gui.fenetre_principale as fp
    import app.gui.widgets.dialogues as dialogues

    monkeypatch.setattr(dialogues, "afficher_erreur", erreur_bloquante)
    monkeypatch.setattr(fp, "afficher_erreur", erreur_bloquante)
    application = fp.Application(racine)
    application.erreurs = erreurs
    yield application
    application.quitter()


def _connecter(application, identifiant):
    ecran = application._cadre
    ecran.identifiant.definir(identifiant)
    ecran.mot_de_passe.definir(COMPTES[identifiant])
    ecran.se_connecter()
    assert application.contexte is not None, application._cadre.message.cget("text")


@pytest.mark.parametrize("identifiant", list(COMPTES))
def test_chaque_ecran_s_ouvre(application, identifiant):
    from app.gui.vues import ACCUEIL, ecrans_autorises

    _connecter(application, identifiant)
    role = application.contexte.role
    assert application.vue_courante == ACCUEIL[role]
    menu = set(application.navigation.get_children())
    assert menu == {e.cle for e in ecrans_autorises(role)}
    for definition in ecrans_autorises(role):
        application.naviguer(definition.cle)
        application.racine.update()
        vue = application.vues[definition.cle]
        if hasattr(vue, "onglets"):
            for index in range(len(vue.onglets.tabs())):
                vue.onglets.select(index)
                application.racine.update()
    assert application.erreurs == []
    application.se_deconnecter()
    assert application.contexte is None


def test_menu_selon_role(application):
    _connecter(application, "direction")
    assert set(application.navigation.get_children()) == {"tableau_bord"}


def test_a_propos(application, monkeypatch):
    from app.gui.vues import a_propos

    _connecter(application, "planif")
    fenetre = a_propos.FenetreAPropos(application.racine)
    application.racine.update()
    boutons = [w.cget("text") for w in fenetre.barre_boutons.winfo_children()]
    assert boutons == ["Fermer"]
    fenetre.fermer()


def test_connexion_refusee_affiche_message_francais(application):
    ecran = application._cadre
    ecran.identifiant.definir("planif")
    ecran.mot_de_passe.definir("faux")
    ecran.se_connecter()
    assert application.contexte is None
    assert "Identifiant ou mot de passe incorrect" in ecran.message.cget("text")
