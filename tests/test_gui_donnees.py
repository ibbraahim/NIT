"""Test de fumée de l'écran Données (UC04, UC05) : saisie, import, modèle de fichier."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.conftest import connecter

pytestmark = [pytest.mark.gui, pytest.mark.integration]


@pytest.fixture
def onglets_donnees(application):
    connecter(application, "planif")
    application.naviguer("donnees")
    application.racine.update()
    vue = application.vues["donnees"]
    assert vue.page_historique.sites  # les référentiels de démonstration sont chargés
    return vue


def test_saisie_historique(onglets_donnees, application):
    onglet = onglets_donnees.page_historique
    onglet.champ_date.definir(date.today() - timedelta(days=2))
    onglet.widgets_champs["volume_traite"].definir("1234,5")
    onglet.widgets_champs["effectif_present"].definir("9")
    onglet.widgets_champs["heures_travaillees"].definir("60")

    onglet.enregistrer()
    application.racine.update()

    assert application.erreurs == []
    assert len(onglet.tableau.lignes()) == 1
    assert application.infos == ["Ligne enregistrée."]


def test_saisie_historique_invalide_encadre_le_champ(onglets_donnees, application):
    onglet = onglets_donnees.page_historique
    onglet.widgets_champs["volume_traite"].definir("")  # champ obligatoire manquant

    onglet.enregistrer()
    application.racine.update()

    assert application.erreurs == []  # erreur affichée sous le champ, pas en boîte de dialogue
    assert application.infos == []
    assert onglet.widgets_champs["volume_traite"].message.cget("text") == (
        "Le champ « Volume traité » est obligatoire."
    )
    assert not onglet.tableau.lignes()


def test_effacer_formulaire(onglets_donnees):
    onglet = onglets_donnees.page_historique
    onglet.widgets_champs["volume_traite"].definir("999")
    onglet.effacer_formulaire()
    assert onglet.widgets_champs["volume_traite"].valeur() == ""


def test_telecharger_modele(onglets_donnees, tmp_path, monkeypatch):
    import app.gui.vues.donnees as vd

    onglet = onglets_donnees.page_historique
    destination = tmp_path / "modele.csv"
    monkeypatch.setattr(vd, "choisir_fichier_a_enregistrer", lambda *a, **k: destination)

    onglet.telecharger_modele()

    assert destination.is_file()
    assert "site" in destination.read_text(encoding="utf-8").splitlines()[0]


def test_import_fichier_valides_et_rejetes(onglets_donnees, application, tmp_path, monkeypatch):
    import app.gui.vues.donnees as vd

    onglet = onglets_donnees.page_historique
    d1 = (date.today() - timedelta(days=5)).strftime("%d/%m/%Y")
    d2 = (date.today() - timedelta(days=6)).strftime("%d/%m/%Y")
    chemin = tmp_path / "import.csv"
    chemin.write_text(
        "site;zone;date;volume_traite;effectif_present;heures_travaillees\n"
        f"Plateforme Casablanca;Réception;{d1};1500;10;70\n"
        f"Plateforme Casablanca;Zone inconnue;{d2};1000;8;60\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vd, "choisir_fichier_a_ouvrir", lambda *a, **k: chemin)

    resultats_captures = {}

    def espionner(parent, titre, resultat, colonnes, nom):
        resultats_captures["resultat"] = resultat
        return True  # simule le clic sur « Enregistrer les lignes valides »

    monkeypatch.setattr(vd, "ouvrir_resultat_import", espionner)

    onglet.importer()
    application.racine.update()

    resultat = resultats_captures["resultat"]
    assert len(resultat.valides) == 1
    assert len(resultat.rejets) == 1
    assert resultat.rejets[0].colonne == "zone"
    assert application.erreurs == []
    assert len(onglet.tableau.lignes()) == 1


def test_saisie_prevision_volume(onglets_donnees, application):
    onglet = onglets_donnees.page_previsions
    onglet.champ_date.definir(date.today() + timedelta(days=3))
    onglet.widgets_champs["volume_prevu"].definir("2100")
    onglet.widgets_champs["indicateur_pic"].definir(True)

    onglet.enregistrer()
    application.racine.update()

    assert application.erreurs == []
    lignes = onglet.tableau.lignes()
    assert len(lignes) == 1
    assert lignes[0]["volume_prevu"] == 2100.0
    assert lignes[0]["indicateur_pic"] is True


def test_saisie_prevision_date_passee_refusee(onglets_donnees, application):
    onglet = onglets_donnees.page_previsions
    onglet.champ_date.definir(date.today() - timedelta(days=1))
    onglet.widgets_champs["volume_prevu"].definir("1000")

    onglet.enregistrer()
    application.racine.update()

    assert application.erreurs == []
    assert "passée" in onglet.champ_date.message.cget("text")
    assert not onglet.tableau.lignes()
