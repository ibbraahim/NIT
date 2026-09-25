"""UC15 · Définir les cibles et seuils des KPI — UC16 · Calculer les KPI — UC17 · Comparer
les KPI aux cibles. Tests d'intégration (base PostgreSQL de test)."""

from __future__ import annotations

from datetime import date

import pytest

from app.bd.connexion import transaction
from app.erreurs import AccesRefuse, DonneesInvalides, OperationImpossible
from app.services import admin, auth, kpi, modeles
from tests.test_modeles import _inserer_historique

pytestmark = pytest.mark.integration


@pytest.fixture
def site_zone_modeles(ctx_admin):
    """Site, zone, historique déterministe et modèles RL/RN entraînés et activés (RL retenue
    pour le plan) — mêmes fixtures que ``tests/test_planification.py``."""
    site_id = admin.enregistrer_site(ctx_admin, "Plateforme Test")
    zone_id = admin.enregistrer_zone(ctx_admin, site_id, "Réception", "chariot_elevateur", 7.5)
    for i in range(4):
        admin.enregistrer_equipement(ctx_admin, site_id, zone_id, "chariot_elevateur", f"CE-{i}")
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    for version in resume.versions:
        modeles.activer_version(
            ctx_admin,
            version.version_id,
            retenir_pour_plan=version.methode == "regression_lineaire",
        )
    return site_id, zone_id


@pytest.fixture
def ctx_planificateur(site_zone_modeles):
    from app.bd.depots.utilisateurs import DepotUtilisateurs

    site_id, _zone_id = site_zone_modeles
    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Planif2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("planif", "P", "P", "", h, s, "planificateur")
        depot.definir_sites(uid, [site_id])
    return auth.authentifier("planif", "Planif2026!")


@pytest.fixture
def ctx_responsable(site_zone_modeles):
    from app.bd.depots.utilisateurs import DepotUtilisateurs

    site_id, _zone_id = site_zone_modeles
    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Resp2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("resp", "R", "R", "", h, s, "responsable")
        depot.definir_sites(uid, [site_id])
    return auth.authentifier("resp", "Resp2026!")


# ---------------------------------------------------------------------
# UC16 / UC17 · Calcul et comparaison
# ---------------------------------------------------------------------
def test_calculer_kpi_refuse_hors_responsable(ctx_planificateur, site_zone_modeles):
    site_id, _zone_id = site_zone_modeles
    with pytest.raises(AccesRefuse):
        kpi.calculer_kpi(ctx_planificateur, site_id, None, "semaine")


def test_calculer_kpi_calcule_les_kpi_sans_methode(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    valeurs = kpi.calculer_kpi(
        ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 6)
    )
    par_code = {v["kpi_code"]: v for v in valeurs if v["methode"] is None}
    # Historique déterministe (tests/test_modeles.py) : heures ≈ 0,05 × volume + 10.
    assert par_code["PRODUCTIVITE"]["valeur"] == pytest.approx(1 / 0.05, rel=0.2)
    assert par_code["PRODUCTIVITE"]["statut"] is None or "statut" in par_code["PRODUCTIVITE"]
    # Sans statut demandé (UC16 seul) : pas de cible ni de statut coloré.
    assert par_code["PRODUCTIVITE"]["cible"] is None
    assert par_code["PRODUCTIVITE"]["statut"] == "gris"


def test_calculer_kpi_les_deux_methodes_pour_un_kpi_de_precision(
    ctx_responsable, site_zone_modeles
):
    site_id, zone_id = site_zone_modeles
    valeurs = kpi.calculer_kpi(
        ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 6)
    )
    methodes = {v["methode"] for v in valeurs if v["kpi_code"] == "MAE_H"}
    assert methodes == {"regression_lineaire", "reseau_neurones"}


def test_comparer_kpi_cibles_affecte_un_statut(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    valeurs = kpi.comparer_kpi_cibles(
        ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 6)
    )
    par_code = {v["kpi_code"]: v for v in valeurs if v["methode"] is None}
    # TAUX_HS général par défaut : cible 5, vert si <= 5 (historique déterministe sans heures
    # sup ni intérim : 0 %).
    assert par_code["TAUX_HS"]["valeur"] == pytest.approx(0.0)
    assert par_code["TAUX_HS"]["statut"] == "vert"


def test_calculer_kpi_persiste_les_valeurs_sans_dupliquer(ctx_responsable, site_zone_modeles):
    from app.bd.connexion import transaction
    from app.bd.depots.kpi import DepotKpi

    site_id, zone_id = site_zone_modeles
    kpi.calculer_kpi(ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 6))
    kpi.calculer_kpi(ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 6))
    with transaction() as cur:
        valeurs = DepotKpi(cur).valeurs(site_id, zone_id, "jour", date(2026, 1, 6))
    codes_methodes = [(v["kpi_code"], v["methode"]) for v in valeurs]
    assert len(codes_methodes) == len(set(codes_methodes))  # aucun doublon


def test_lister_kpi_valeurs_calcule_la_tendance(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    kpi.comparer_kpi_cibles(
        ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 5)
    )
    kpi.comparer_kpi_cibles(
        ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 6)
    )
    valeurs = kpi.lister_kpi_valeurs(ctx_responsable, site_id, zone_id, "jour", date(2026, 1, 6))
    assert all("tendance" in v for v in valeurs)
    assert all(v["tendance"] in ("↑", "↓", "→") for v in valeurs)


# ---------------------------------------------------------------------
# UC15 · Définir les cibles et seuils
# ---------------------------------------------------------------------
def test_definir_objectif_refuse_hors_responsable(ctx_planificateur, site_zone_modeles):
    site_id, _zone_id = site_zone_modeles
    with pytest.raises(AccesRefuse):
        kpi.definir_objectif(
            ctx_planificateur,
            1,
            site_id,
            None,
            "jour",
            {"valeur_cible": 5, "seuil_orange": 5, "seuil_rouge": 10},
        )


def test_definir_objectif_refuse_pour_un_kpi_information(ctx_responsable):
    from app.bd.connexion import transaction
    from app.bd.depots.kpi import DepotKpi

    with transaction() as cur:
        mae = DepotKpi(cur).definition_par_code("MAE_H")
    with pytest.raises(OperationImpossible):
        kpi.definir_objectif(ctx_responsable, mae["id"], None, None, "jour", {})


def test_definir_objectif_exige_les_seuils_pour_sens_baisse(ctx_responsable):
    from app.bd.connexion import transaction
    from app.bd.depots.kpi import DepotKpi

    with transaction() as cur:
        taux_hs = DepotKpi(cur).definition_par_code("TAUX_HS")
    with pytest.raises(DonneesInvalides) as exc:
        kpi.definir_objectif(ctx_responsable, taux_hs["id"], None, None, "jour", {})
    assert "seuil_orange" in exc.value.erreurs


def test_definir_objectif_exige_min_max_pour_sens_plage(ctx_responsable):
    from app.bd.connexion import transaction
    from app.bd.depots.kpi import DepotKpi

    with transaction() as cur:
        adequation = DepotKpi(cur).definition_par_code("ADEQUATION")
    with pytest.raises(DonneesInvalides):
        kpi.definir_objectif(ctx_responsable, adequation["id"], None, None, "jour", {})


def test_definir_objectif_min_superieur_au_max_refuse(ctx_responsable):
    from app.bd.connexion import transaction
    from app.bd.depots.kpi import DepotKpi

    with transaction() as cur:
        adequation = DepotKpi(cur).definition_par_code("ADEQUATION")
    with pytest.raises(DonneesInvalides) as exc:
        kpi.definir_objectif(
            ctx_responsable,
            adequation["id"],
            None,
            None,
            "jour",
            {"valeur_min": 110, "valeur_max": 90, "seuil_orange": 5},
        )
    assert "valeur_min" in exc.value.erreurs


def test_definir_objectif_creer_modifier_lister_supprimer(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    from app.bd.connexion import transaction
    from app.bd.depots.kpi import DepotKpi

    with transaction() as cur:
        taux_hs = DepotKpi(cur).definition_par_code("TAUX_HS")

    objectif_id = kpi.definir_objectif(
        ctx_responsable,
        taux_hs["id"],
        site_id,
        zone_id,
        "jour",
        {"valeur_cible": 6, "seuil_orange": 6, "seuil_rouge": 10},
    )
    objectifs = kpi.lister_objectifs(ctx_responsable, site_id)
    cree = next(o for o in objectifs if o["id"] == objectif_id)
    assert cree["seuil_orange"] == pytest.approx(6.0)
    assert cree["zone_id"] == zone_id

    kpi.definir_objectif(
        ctx_responsable,
        taux_hs["id"],
        site_id,
        zone_id,
        "jour",
        {"valeur_cible": 4, "seuil_orange": 4, "seuil_rouge": 8},
        objectif_id=objectif_id,
    )
    modifie = next(
        o for o in kpi.lister_objectifs(ctx_responsable, site_id) if o["id"] == objectif_id
    )
    assert modifie["seuil_orange"] == pytest.approx(4.0)

    kpi.supprimer_objectif(ctx_responsable, objectif_id)
    assert all(o["id"] != objectif_id for o in kpi.lister_objectifs(ctx_responsable, site_id))


def test_supprimer_objectif_introuvable(ctx_responsable):
    with pytest.raises(OperationImpossible):
        kpi.supprimer_objectif(ctx_responsable, 999999)


def test_objectif_par_zone_prevaut_sur_objectif_general(ctx_responsable, site_zone_modeles):
    """Priorité site+zone > général (UC15/UC16). L'objectif est inséré directement (plutôt que
    via ``definir_objectif``, qui date toujours sa validité du jour même) pour qu'il s'applique
    à une date de référence passée, dans l'historique déterministe de test."""
    site_id, zone_id = site_zone_modeles
    from app.bd.connexion import transaction
    from app.bd.depots.kpi import DepotKpi

    with transaction() as cur:
        depot = DepotKpi(cur)
        taux_hs = depot.definition_par_code("TAUX_HS")
        depot.creer_objectif(
            taux_hs["id"],
            site_id,
            zone_id,
            "jour",
            "baisse",
            1,
            1,
            2,
            None,
            None,
            False,
            date(2020, 1, 1),
        )
    valeurs = kpi.comparer_kpi_cibles(
        ctx_responsable, site_id, zone_id, "jour", date_reference=date(2026, 1, 6)
    )
    taux_hs_valeur = next(v for v in valeurs if v["kpi_code"] == "TAUX_HS")
    assert taux_hs_valeur["cible"] == pytest.approx(1.0)  # et non la cible générale (5)
