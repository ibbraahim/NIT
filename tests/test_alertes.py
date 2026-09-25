"""UC18 · Émettre une alerte — UC19 · Traiter une alerte. Tests d'intégration (base
PostgreSQL de test)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.kpi import DepotKpi
from app.bd.depots.plans import DepotPlansCharge
from app.erreurs import AccesRefuse, DonneesInvalides, OperationImpossible
from app.services import admin, alertes, auth
from app.utils.dates import lundi_de

pytestmark = pytest.mark.integration

CHAMPS_LIGNE_DEFAUT = {
    "besoin_heures": 0.0,
    "besoin_effectif": 0,
    "besoin_equipements": 0,
    "effectif_planifie": 0,
    "interim_planifie": 0,
    "equipements_planifies": 0,
    "capacite_effectif": 20,
    "capacite_equipements": 5,
    "commentaire": "",
}


@pytest.fixture
def site_zone(ctx_admin):
    site_id = admin.enregistrer_site(ctx_admin, "Plateforme Test")
    zone_id = admin.enregistrer_zone(ctx_admin, site_id, "Réception", "chariot_elevateur", 7.5)
    return site_id, zone_id


@pytest.fixture
def ctx_responsable(site_zone):
    from app.bd.depots.utilisateurs import DepotUtilisateurs

    site_id, _zone_id = site_zone
    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Resp2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("resp", "R", "R", "", h, s, "responsable")
        depot.definir_sites(uid, [site_id])
    return auth.authentifier("resp", "Resp2026!")


@pytest.fixture
def ctx_planificateur(site_zone):
    from app.bd.depots.utilisateurs import DepotUtilisateurs

    site_id, _zone_id = site_zone
    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Planif2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("planif", "P", "P", "", h, s, "planificateur")
        depot.definir_sites(uid, [site_id])
    return auth.authentifier("planif", "Planif2026!")


def _creer_plan_valide(site_id: int, semaine: date, lignes: list[dict]) -> int:
    lundi = lundi_de(semaine)
    with transaction() as cur:
        depot = DepotPlansCharge(cur)
        plan_id = depot.creer_plan(site_id, lundi, "regression_lineaire", None)
        depot.inserer_lignes(plan_id, [{**CHAMPS_LIGNE_DEFAUT, **l} for l in lignes])
        depot.mettre_a_jour_plan(plan_id, statut="valide")
    return plan_id


# ---------------------------------------------------------------------
# UC18 · Émettre une alerte
# ---------------------------------------------------------------------
def test_emettre_alertes_refuse_hors_responsable(ctx_planificateur, site_zone):
    site_id, _zone_id = site_zone
    with pytest.raises(AccesRefuse):
        alertes.emettre_alertes(ctx_planificateur, site_id)


def test_sous_effectif_rouge_j1_j2_orange_j3_j7(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    aujourdhui = date(2026, 3, 16)  # lundi
    lignes = []
    for decalage in range(1, 9):  # J+1 à J+8
        lignes.append(
            {
                "zone_id": zone_id,
                "date_jour": aujourdhui + timedelta(days=decalage),
                "besoin_effectif": 10,
                "effectif_planifie": 5,  # 50 % du besoin : sous-effectif net
            }
        )
    _creer_plan_valide(site_id, aujourdhui + timedelta(days=1), lignes)
    _creer_plan_valide(site_id, aujourdhui + timedelta(days=8), lignes[-1:])

    resultat = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    sous_effectif = {a["date_jour"]: a["niveau"] for a in resultat if a["type"] == "sous_effectif"}

    assert sous_effectif[aujourdhui + timedelta(days=1)] == "rouge"
    assert sous_effectif[aujourdhui + timedelta(days=2)] == "rouge"
    assert sous_effectif[aujourdhui + timedelta(days=3)] == "orange"
    assert sous_effectif[aujourdhui + timedelta(days=7)] == "orange"
    assert (aujourdhui + timedelta(days=8)) not in sous_effectif  # hors horizon (J+7 max)


def test_sous_effectif_absent_si_adequation_suffisante(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    aujourdhui = date(2026, 3, 16)
    _creer_plan_valide(
        site_id,
        aujourdhui + timedelta(days=1),
        [
            {
                "zone_id": zone_id,
                "date_jour": aujourdhui + timedelta(days=1),
                "besoin_effectif": 10,
                "effectif_planifie": 10,  # 100 % : pas de sous-effectif
            }
        ],
    )
    resultat = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    assert not [a for a in resultat if a["type"] == "sous_effectif"]


def test_sureffectif_detecte_jusqu_a_j14(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    aujourdhui = date(2026, 3, 16)
    lignes_semaine1 = [
        {
            "zone_id": zone_id,
            "date_jour": aujourdhui + timedelta(days=d),
            "besoin_effectif": 5,
            "effectif_planifie": 10,  # 200 % : sureffectif
        }
        for d in range(1, 8)
    ]
    lignes_semaine2 = [
        {
            "zone_id": zone_id,
            "date_jour": aujourdhui + timedelta(days=d),
            "besoin_effectif": 5,
            "effectif_planifie": 10,
        }
        for d in range(8, 16)
    ]
    _creer_plan_valide(site_id, aujourdhui + timedelta(days=1), lignes_semaine1)
    _creer_plan_valide(site_id, aujourdhui + timedelta(days=8), lignes_semaine2)

    resultat = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    sureffectif = {a["date_jour"] for a in resultat if a["type"] == "sureffectif"}
    assert (aujourdhui + timedelta(days=14)) in sureffectif
    assert (aujourdhui + timedelta(days=15)) not in sureffectif  # hors horizon (J+14 max)
    assert all(a["niveau"] == "orange" for a in resultat if a["type"] == "sureffectif")


def test_sureffectif_sans_aucun_besoin(ctx_responsable, site_zone):
    """Personnel planifié alors qu'aucun besoin n'est prévu (besoin_effectif = 0)."""
    site_id, zone_id = site_zone
    aujourdhui = date(2026, 3, 16)
    _creer_plan_valide(
        site_id,
        aujourdhui + timedelta(days=1),
        [
            {
                "zone_id": zone_id,
                "date_jour": aujourdhui + timedelta(days=1),
                "besoin_effectif": 0,
                "effectif_planifie": 6,
            }
        ],
    )
    resultat = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    sureffectif = [a for a in resultat if a["type"] == "sureffectif"]
    assert len(sureffectif) == 1
    assert "aucun besoin" in _dernier_message(site_id, sureffectif[0]["alerte_id"])


def _dernier_message(site_id: int, alerte_id: int) -> str:
    with transaction() as cur:
        cur.execute("SELECT message FROM alertes WHERE id = %s", (alerte_id,))
        return cur.fetchone()["message"]


def test_penurie_equipement_detectee(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    aujourdhui = date(2026, 3, 16)
    _creer_plan_valide(
        site_id,
        aujourdhui + timedelta(days=2),
        [
            {
                "zone_id": zone_id,
                "date_jour": aujourdhui + timedelta(days=2),
                "besoin_equipements": 4,
                "capacite_equipements": 2,  # 2 chariots en maintenance
            }
        ],
    )
    resultat = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    penurie = [a for a in resultat if a["type"] == "penurie_equipement"]
    assert len(penurie) == 1
    assert penurie[0]["niveau"] == "rouge"  # J+2


def test_seuil_kpi_detecte(ctx_responsable, site_zone):
    site_id, _zone_id = site_zone
    aujourdhui = date(2026, 3, 16)
    debut_semaine = lundi_de(aujourdhui)
    with transaction() as cur:
        depot = DepotKpi(cur)
        taux_hs = depot.definition_par_code("TAUX_HS")
        depot.upsert_valeur(
            taux_hs["id"], site_id, None, "semaine", debut_semaine, None, 12.0, 5.0, "rouge"
        )
    resultat = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    seuil_kpi = [a for a in resultat if a["type"] == "seuil_kpi"]
    assert len(seuil_kpi) == 1
    assert seuil_kpi[0]["kpi_code"] == "TAUX_HS"
    assert seuil_kpi[0]["niveau"] == "rouge"


def test_emettre_alertes_deduplique(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    aujourdhui = date(2026, 3, 16)
    _creer_plan_valide(
        site_id,
        aujourdhui + timedelta(days=1),
        [
            {
                "zone_id": zone_id,
                "date_jour": aujourdhui + timedelta(days=1),
                "besoin_effectif": 10,
                "effectif_planifie": 5,
            }
        ],
    )
    premier = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    second = alertes.emettre_alertes(ctx_responsable, site_id, date_reference=aujourdhui)
    id_sous_effectif_1 = next(a["alerte_id"] for a in premier if a["type"] == "sous_effectif")
    id_sous_effectif_2 = next(a["alerte_id"] for a in second if a["type"] == "sous_effectif")
    assert id_sous_effectif_1 == id_sous_effectif_2  # même alerte mise à jour, pas dupliquée
    with transaction() as cur:
        cur.execute(
            "SELECT count(*) AS n, max(nb_occurrences) AS occ FROM alertes WHERE id = %s",
            (id_sous_effectif_1,),
        )
        ligne = cur.fetchone()
    assert ligne["n"] == 1
    assert ligne["occ"] == 2


# ---------------------------------------------------------------------
# UC19 · Traiter une alerte
# ---------------------------------------------------------------------
def _emettre_une_alerte(ctx, site_id, zone_id, aujourdhui) -> int:
    _creer_plan_valide(
        site_id,
        aujourdhui + timedelta(days=1),
        [
            {
                "zone_id": zone_id,
                "date_jour": aujourdhui + timedelta(days=1),
                "besoin_effectif": 10,
                "effectif_planifie": 5,
            }
        ],
    )
    resultat = alertes.emettre_alertes(ctx, site_id, date_reference=aujourdhui)
    return next(a["alerte_id"] for a in resultat if a["type"] == "sous_effectif")


def test_prendre_en_charge_refuse_hors_planificateur_ou_responsable(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    alerte_id = _emettre_une_alerte(ctx_responsable, site_id, zone_id, date(2026, 3, 16))
    ctx_direction = _ctx_direction(site_id)
    with pytest.raises(AccesRefuse):
        alertes.prendre_en_charge(ctx_direction, alerte_id)


def _ctx_direction(site_id: int):
    from app.bd.depots.utilisateurs import DepotUtilisateurs

    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Direction2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("direction", "D", "D", "", h, s, "direction")
        depot.definir_sites(uid, [site_id])
    return auth.authentifier("direction", "Direction2026!")


def test_prendre_en_charge_puis_resoudre(ctx_responsable, ctx_planificateur, site_zone):
    site_id, zone_id = site_zone
    alerte_id = _emettre_une_alerte(ctx_responsable, site_id, zone_id, date(2026, 3, 16))

    alertes.prendre_en_charge(ctx_planificateur, alerte_id)
    ouverte = next(
        a for a in alertes.lister_alertes(ctx_responsable, site_id) if a["id"] == alerte_id
    )
    assert ouverte["statut"] == "en_cours"
    assert ouverte["pris_en_charge_par"] == ctx_planificateur.utilisateur_id

    alertes.resoudre_alerte(ctx_planificateur, alerte_id, "Intérim supplémentaire réservé.")
    resolue = next(
        a for a in alertes.lister_alertes(ctx_responsable, site_id) if a["id"] == alerte_id
    )
    assert resolue["statut"] == "resolue"
    assert resolue["action_menee"] == "Intérim supplémentaire réservé."
    assert resolue["resolu_par"] == ctx_planificateur.utilisateur_id


def test_resoudre_sans_action_menee_refuse(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    alerte_id = _emettre_une_alerte(ctx_responsable, site_id, zone_id, date(2026, 3, 16))
    with pytest.raises(DonneesInvalides):
        alertes.resoudre_alerte(ctx_responsable, alerte_id, "   ")


def test_resoudre_alerte_deja_resolue_refuse(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    alerte_id = _emettre_une_alerte(ctx_responsable, site_id, zone_id, date(2026, 3, 16))
    alertes.resoudre_alerte(ctx_responsable, alerte_id, "Résolu.")
    with pytest.raises(OperationImpossible):
        alertes.resoudre_alerte(ctx_responsable, alerte_id, "Encore.")


def test_alerte_introuvable(ctx_responsable):
    with pytest.raises(OperationImpossible):
        alertes.prendre_en_charge(ctx_responsable, 999999)
    with pytest.raises(OperationImpossible):
        alertes.resoudre_alerte(ctx_responsable, 999999, "Action.")


# ---------------------------------------------------------------------
# Lectures transverses
# ---------------------------------------------------------------------
def test_compter_et_lister_alertes_ouvertes(ctx_responsable, site_zone):
    site_id, zone_id = site_zone
    _emettre_une_alerte(ctx_responsable, site_id, zone_id, date(2026, 3, 16))
    assert alertes.compter_alertes_ouvertes(ctx_responsable) >= 1
    ouvertes = alertes.lister_alertes_ouvertes(ctx_responsable, site_id)
    assert all(a["statut"] != "resolue" for a in ouvertes)
