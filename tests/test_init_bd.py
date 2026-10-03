"""Initialisation de la base : catalogue des KPI, cibles par défaut, administrateur."""

import pytest

from app.bd.catalogue_kpi import CATALOGUE, objectifs_par_defaut
from app.bd.connexion import transaction

pytestmark = pytest.mark.integration


def test_catalogue_kpi_complet(bd_vierge):
    with transaction() as cur:
        cur.execute(
            "SELECT code, sens::text AS sens, par_methode FROM kpi_definitions ORDER BY ordre"
        )
        lignes = cur.fetchall()
    assert len(lignes) == 20
    assert [l["code"] for l in lignes] == [k.code for k in CATALOGUE]
    sens = {l["code"]: l["sens"] for l in lignes}
    assert sens["MAPE_H"] == "baisse" and sens["BIAIS_H"] == "plage"
    assert sens["PRODUCTIVITE"] == "hausse" and sens["MAE_H"] == "information"


def test_cibles_par_defaut(bd_vierge):
    with transaction() as cur:
        cur.execute("""SELECT k.code, o.periodicite::text AS p, o.valeur_cible::float AS cible,
                      o.seuil_orange::float AS orange, o.seuil_rouge::float AS rouge,
                      o.valeur_min::float AS mini, o.valeur_max::float AS maxi
               FROM objectifs_kpi o JOIN kpi_definitions k ON k.id = o.kpi_id""")
        objectifs = {(l["code"], l["p"]): l for l in cur.fetchall()}
    assert len(objectifs) == len(objectifs_par_defaut()) == 17 * 4
    assert (objectifs[("MAPE_H", "jour")]["orange"], objectifs[("MAPE_H", "jour")]["rouge"]) == (
        10,
        15,
    )
    assert (objectifs[("MAPE_H", "mois")]["orange"], objectifs[("MAPE_H", "mois")]["rouge"]) == (
        5,
        8,
    )
    assert (objectifs[("BIAIS_H", "jour")]["mini"], objectifs[("BIAIS_H", "jour")]["maxi"]) == (
        -3,
        3,
    )
    assert objectifs[("TAUX_UTIL_EQP", "semaine")]["orange"] == 10
    assert objectifs[("PRODUCTIVITE", "jour")]["cible"] is None


def test_administrateur_cree(bd_vierge):
    with transaction() as cur:
        cur.execute(
            "SELECT identifiant, role::text AS role, sel, hash_mot_de_passe FROM utilisateurs"
        )
        (admin,) = cur.fetchall()
    assert admin["role"] == "administrateur"
    assert "Admin2026!" not in admin["hash_mot_de_passe"]


def test_contraintes_du_schema(bd_vierge):
    from app.erreurs import DonneesInvalides

    with pytest.raises(DonneesInvalides):
        with transaction() as cur:
            cur.execute("INSERT INTO sites (nom) VALUES ('A')")
            cur.execute("INSERT INTO plans_charge (site_id, semaine) VALUES (1, '2026-03-10')")


def test_migration_ajoute_gradient_boosting_a_une_base_ancienne(base_test):
    """Une base créée avant le gradient boosting reçoit la valeur d'énuméré à l'ouverture."""
    from app.bd import connexion as bd
    from app.bd.init_bd import CHEMIN_SCHEMA, creer_base, supprimer_base

    ancienne = base_test.avec_base(f"{base_test.base}_ancienne")
    creer_base(ancienne)
    try:
        bd.definir_configuration(ancienne)
        schema = CHEMIN_SCHEMA.read_text(encoding="utf-8").replace(
            "ENUM ('regression_lineaire', 'reseau_neurones', 'gradient_boosting')",
            "ENUM ('regression_lineaire', 'reseau_neurones')",
        )
        with bd.transaction() as cur:  # le pool est ouvert avant le schéma : rien à migrer
            cur.execute(schema)
        bd.definir_configuration(ancienne)  # ferme le pool : la prochaine ouverture migre
        with bd.transaction() as cur:
            cur.execute("SELECT enum_range(NULL::methode_prevision)::text AS valeurs")
            assert "gradient_boosting" in cur.fetchone()["valeurs"]
    finally:
        bd.definir_configuration(base_test)
        supprimer_base(ancienne)
