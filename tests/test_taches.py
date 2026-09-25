"""Tâches automatiques : exécution journalisée et cycle de vie du planificateur."""

from __future__ import annotations

import pytest

from app.bd.connexion import transaction
from app.bd.depots.taches import DepotTaches
from app.taches.planificateur import TACHES, Planificateur, executer_tache

pytestmark = pytest.mark.integration


def test_executer_tache_inconnue_refuse(bd_vierge):
    with pytest.raises(ValueError):
        executer_tache("tache_qui_n_existe_pas")


def test_executer_tache_journalise_le_succes(bd_vierge):
    message = executer_tache("calculer_kpi")
    assert isinstance(message, str)
    with transaction() as cur:
        journal = DepotTaches(cur).journal()
    assert len(journal) == 1
    assert journal[0]["tache"] == "calculer_kpi"
    assert journal[0]["statut"] == "succes"
    assert journal[0]["message"] == message
    assert journal[0]["fin"] is not None


def test_executer_tache_journalise_l_echec(bd_vierge, monkeypatch):
    def _en_echec():
        raise RuntimeError("panne simulée")

    monkeypatch.setitem(TACHES, "calculer_kpi", _en_echec)
    with pytest.raises(RuntimeError):
        executer_tache("calculer_kpi")
    with transaction() as cur:
        journal = DepotTaches(cur).journal()
    assert journal[0]["statut"] == "echec"
    assert "panne simulée" in journal[0]["message"]


def test_toutes_les_taches_s_executent_sans_site(bd_vierge):
    """Aucun site en base : chaque tâche doit renvoyer un message, pas planter."""
    for nom in TACHES:
        message = executer_tache(nom)
        assert isinstance(message, str) and message


def test_toutes_les_taches_s_executent_avec_donnees(demo_referentiels):
    """Référentiels de démonstration (sans historique) : chaque tâche s'exécute encore."""
    for nom in TACHES:
        message = executer_tache(nom)
        assert isinstance(message, str) and message


def test_planificateur_cycle_de_vie(bd_vierge):
    planificateur = Planificateur()
    try:
        assert not planificateur.est_actif
        planificateur.demarrer()
        assert planificateur.est_actif
        planificateur.suspendre()
        assert not planificateur.est_actif
        planificateur.demarrer()
        assert planificateur.est_actif
        jobs = dict(planificateur.prochaines_executions())
        assert set(jobs) == set(TACHES)
        assert all(prochaine is not None for prochaine in jobs.values())
    finally:
        planificateur.arreter()
    assert not planificateur.est_actif


def test_planificateur_arreter_puis_redemarrer(bd_vierge):
    planificateur = Planificateur()
    try:
        planificateur.demarrer()
        planificateur.arreter()
        assert not planificateur.est_actif
        planificateur.demarrer()
        assert planificateur.est_actif
    finally:
        planificateur.arreter()
