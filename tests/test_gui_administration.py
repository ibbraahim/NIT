"""Test de fumée des onglets Utilisateurs et Tâches de l'écran Administration (UC02, tâches
automatiques)."""

from __future__ import annotations

import time

import pytest

from tests.conftest import connecter

pytestmark = [pytest.mark.gui, pytest.mark.integration]


@pytest.fixture
def onglets_admin(application):
    connecter(application, "admin")
    application.naviguer("administration")
    application.racine.update()
    vue = application.vues["administration"]
    return vue.pages[0], vue.pages[4]  # OngletUtilisateurs, OngletTaches


def test_ajouter_modifier_desactiver_reactiver_utilisateur(onglets_admin, application):
    utilisateurs, _taches = onglets_admin
    utilisateurs.actualiser()
    application.racine.update()
    avant = len(utilisateurs.tableau.lignes())

    dialogue = utilisateurs._construire_dialogue(None)
    dialogue.champs["identifiant"].definir("j.dupont")
    dialogue.champs["mot_de_passe"].definir("Motdepasse1")
    dialogue.champs["nom"].definir("Dupont")
    dialogue.champs["prenom"].definir("Jean")
    dialogue.champs["email"].definir("jean@example.com")
    dialogue.champs["role"].definir("planificateur")
    dialogue._valider()
    application.racine.update()
    assert application.erreurs == []
    dialogue.destroy()

    utilisateurs.actualiser()
    application.racine.update()
    lignes = utilisateurs.tableau.lignes()
    assert len(lignes) == avant + 1
    cree = next(l for l in lignes if l["identifiant"] == "j.dupont")
    assert cree["role_libelle"] == "Planificateur"
    assert cree["etat"] == "Actif"

    utilisateurs.tableau.selectionner(cree["id"])
    application.racine.update()
    utilisateurs.mettre_a_jour_boutons()

    modification = utilisateurs._construire_dialogue(cree)
    modification.champs["prenom"].definir("Jean-Marc")
    modification._valider()
    application.racine.update()
    assert application.erreurs == []
    modification.destroy()

    utilisateurs.actualiser()
    modifie = next(l for l in utilisateurs.tableau.lignes() if l["id"] == cree["id"])
    assert modifie["nom_complet"] == "Jean-Marc Dupont"

    utilisateurs.tableau.selectionner(cree["id"])
    application.racine.update()
    utilisateurs.activer_desactiver()
    application.racine.update()
    assert application.erreurs == []
    utilisateurs.actualiser()
    desactive = next(l for l in utilisateurs.tableau.lignes() if l["id"] == cree["id"])
    assert desactive["etat"] == "Inactif"

    utilisateurs.tableau.selectionner(cree["id"])
    application.racine.update()
    utilisateurs.activer_desactiver()
    application.racine.update()
    utilisateurs.actualiser()
    reactive = next(l for l in utilisateurs.tableau.lignes() if l["id"] == cree["id"])
    assert reactive["etat"] == "Actif"


def test_planificateur_demarrer_suspendre_et_journal(onglets_admin, application):
    _utilisateurs, taches = onglets_admin
    taches.actualiser()
    application.racine.update()
    assert not application.planificateur.est_actif

    taches.demarrer()
    application.racine.update()
    assert application.erreurs == []
    assert application.planificateur.est_actif
    assert "en marche" in taches.etat_planificateur.cget("text")

    taches.suspendre()
    application.racine.update()
    assert not application.planificateur.est_actif
    assert "arrêté" in taches.etat_planificateur.cget("text")

    taches.tache.definir("calculer_kpi")
    taches.executer()
    for _ in range(400):
        application.racine.update()
        if taches.tableau.lignes() or application.erreurs:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    lignes = taches.tableau.lignes()
    assert len(lignes) == 1
    assert lignes[0]["statut_libelle"] == "Succès"

    from app.gui.vues.administration import FenetreJournalTaches

    fenetre = FenetreJournalTaches(taches, application.contexte)
    application.racine.update()
    assert fenetre.tableau.lignes()
    fenetre.destroy()
