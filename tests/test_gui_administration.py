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

    # Le tableau de synthèse liste les neuf tâches automatiques, chacune sa fréquence, même
    # avant toute exécution.
    lignes = taches.tableau.lignes()
    assert len(lignes) == 9
    assert all(l["dernier_statut_libelle"] == "Jamais exécutée" for l in lignes)
    assert all(l["frequence"] for l in lignes)

    taches.tableau.selectionner("kpi_quotidiens")
    application.racine.update()
    taches._sur_selection()
    assert taches.b_executer.est_actif

    nb_infos_avant = len(application.infos)
    taches.executer()
    for _ in range(400):
        application.racine.update()
        if len(application.infos) > nb_infos_avant or application.erreurs:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    lignes = taches.tableau.lignes()
    assert len(lignes) == 9
    kpi_ligne = next(l for l in lignes if l["id"] == "kpi_quotidiens")
    assert kpi_ligne["dernier_statut_libelle"] == "Succès"
    assert kpi_ligne["derniere_duree"] != "—"

    from app.gui.vues.administration import FenetreJournalTaches

    fenetre = FenetreJournalTaches(taches, application.contexte)
    application.racine.update()
    assert fenetre.tableau.lignes()
    fenetre.destroy()


def test_parametres_du_bottom_line_enregistres_depuis_administration(application):
    from app.services import bottom_line

    connecter(application, "admin")
    application.naviguer("administration")
    application.racine.update()
    capacites = application.vues["administration"].pages[3]  # OngletCapacitesCouts
    capacites.actualiser()
    assert capacites.champs_bl["bl_penalite_retard"].valeur() == "20"

    capacites.champs_bl["bl_penalite_retard"].definir("42,5")
    capacites.champs_bl["bl_sensibilite_retard"].definir("3")  # hors bornes (0 à 1)
    capacites.enregistrer_parametres_bl()
    assert application.infos == []
    assert capacites.champs_bl["bl_sensibilite_retard"].message.cget("text")  # erreur affichée

    capacites.champs_bl["bl_sensibilite_retard"].definir("0,8")
    capacites.enregistrer_parametres_bl()
    assert application.erreurs == []
    assert application.infos  # confirmation
    lus = bottom_line.lire_parametres(application.contexte)
    assert lus["bl_penalite_retard"] == pytest.approx(42.5)
    assert lus["bl_sensibilite_retard"] == pytest.approx(0.8)
