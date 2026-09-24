"""Fixtures communes : base PostgreSQL de test ``<nom_base>_test`` créée puis supprimée."""

from __future__ import annotations

import os

import pytest

from app.bd import connexion as bd
from app.config import charger_configuration
from app.erreurs import ErreurApplication
from app.journal import configurer_journal

MOT_DE_PASSE_ADMIN = "Admin2026!"


def _config_test():
    config = charger_configuration().base_de_donnees
    return config.avec_base(f"{config.base}_test")


@pytest.fixture(scope="session")
def config_test():
    """Configuration pointant vers la base de test (tests ignorés si PostgreSQL est absent)."""
    configurer_journal()
    try:
        config = _config_test()
        connexion = bd.connexion_administration(config)
        connexion.close()
    except ErreurApplication as exc:
        pytest.skip(f"Base PostgreSQL de test indisponible : {exc}")
    return config


@pytest.fixture(scope="session")
def base_test(config_test):
    """Crée la base de test pour la session, puis la supprime."""
    from app.bd.init_bd import base_existe, creer_base, creer_schema, supprimer_base

    if base_existe(config_test):
        supprimer_base(config_test)
    creer_base(config_test)
    creer_schema(config_test)
    yield config_test
    bd.fermer_pool()
    if not os.environ.get("PLANIF_CONSERVER_BASE_TEST"):
        supprimer_base(config_test)


TABLES_DONNEES = [
    "journal_taches",
    "rapports",
    "alertes",
    "kpi_valeurs",
    "objectifs_kpi",
    "kpi_definitions",
    "scenarios",
    "plans_charge_lignes",
    "plans_charge",
    "comparaisons_realise",
    "previsions_ressources",
    "modeles_versions",
    "parametres_modele",
    "previsions_volume",
    "historique_activite",
    "couts_horaires",
    "capacites_personnel",
    "indisponibilites_equipements",
    "equipements",
    "journal_connexions",
    "utilisateurs_sites",
    "utilisateurs",
    "zones",
    "sites",
    "parametres_application",
]


@pytest.fixture
def bd_vierge(base_test):
    """Base vidée avant chaque test : catalogue des KPI et compte ``admin`` recréés."""
    from app.bd.depots.parametres import DepotParametres
    from app.bd.init_bd import creer_administrateur, inserer_catalogue_kpi

    bd.definir_configuration(base_test)
    with bd.transaction() as cur:
        cur.execute("TRUNCATE " + ", ".join(TABLES_DONNEES) + " RESTART IDENTITY CASCADE")
        inserer_catalogue_kpi(cur)
        DepotParametres(cur).ecrire("donnees_demonstration", "non")
    creer_administrateur("admin", MOT_DE_PASSE_ADMIN)
    yield base_test


@pytest.fixture
def ctx_admin(bd_vierge):
    from app.services.auth import authentifier

    return authentifier("admin", MOT_DE_PASSE_ADMIN)


@pytest.fixture
def demo_referentiels(bd_vierge):
    """Référentiels et comptes de démonstration (sans historique)."""
    from datetime import date

    from app.demo.generateur import generer_referentiels

    return generer_referentiels(date.today())
