"""Test de fumée de l'écran de connexion (UC01) : icône « œil » du champ mot de passe."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def test_icone_oeil_bascule_l_affichage_du_mot_de_passe(application):
    ecran = application._cadre
    champ = ecran.mot_de_passe

    assert champ.saisie.cget("show") == "•"
    assert champ._infobulle_oeil.texte == "Afficher le mot de passe"

    champ._basculer_affichage()
    application.racine.update()

    assert champ.saisie.cget("show") == ""
    assert champ._infobulle_oeil.texte == "Masquer le mot de passe"

    champ._basculer_affichage()
    application.racine.update()

    assert champ.saisie.cget("show") == "•"
    assert champ._infobulle_oeil.texte == "Afficher le mot de passe"
