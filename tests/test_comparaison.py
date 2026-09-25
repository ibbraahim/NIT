"""UC20 · Comparer le réalisé aux prévisions RL et RN — UC21 · Détecter une dérive de modèle.
Tests d'intégration (base PostgreSQL de test)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.alertes import DepotAlertes
from app.bd.depots.comparaisons import DepotComparaisons
from app.bd.depots.historique import DepotHistorique
from app.bd.depots.modeles import DepotModeles
from app.bd.depots.previsions_ressources import DepotPrevisionsRessources
from app.erreurs import AccesRefuse
from app.services import admin, auth, comparaison, modeles
from app.utils.dates import decaler_periode
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


def _semer_jour(
    site_id,
    zone_id,
    methode,
    jour,
    heures_prevues,
    heures_reelles,
    equipements_prevus=3,
    equipements_reels=3,
    ic_bas=None,
    ic_haut=None,
):
    with transaction() as cur:
        depot_modeles = DepotModeles(cur)
        version = depot_modeles.version_active(site_id, zone_id, methode, "heures")
        version_eqp = depot_modeles.version_active(site_id, zone_id, methode, "equipements")
        DepotPrevisionsRessources(cur).inserer_plusieurs(
            [
                {
                    "site_id": site_id,
                    "zone_id": zone_id,
                    "date_jour": jour,
                    "modele_version_id": version["id"],
                    "modele_version_equipements_id": version_eqp["id"],
                    "methode": methode,
                    "volume_prevu": 1000.0,
                    "heures": heures_prevues,
                    "effectif": 10,
                    "equipements": equipements_prevus,
                    "ic_bas": ic_bas if ic_bas is not None else max(heures_prevues - 5, 0),
                    "ic_haut": ic_haut if ic_haut is not None else heures_prevues + 5,
                    "ic_bas_equipements": 1,
                    "ic_haut_equipements": 5,
                    "date_generation": datetime.now(),
                }
            ]
        )
        DepotHistorique(cur).upsert(
            {
                "site_id": site_id,
                "zone_id": zone_id,
                "date_jour": jour,
                "volume_traite": 1000.0,
                "effectif_present": 10,
                "heures_travaillees": heures_reelles,
                "heures_sup": 0,
                "heures_interim": 0,
                "heures_absence": 0,
                "heures_inactives": 0,
                "equipements_mobilises": equipements_reels,
                "heures_usage_equipement": 20.0,
                "heures_disponibles_equipement": 24.0,
                "heures_panne_equipement": 0.0,
                "cout_rh": 100.0,
                "commandes_a_temps": 95,
                "commandes_totales": 100,
                "indicateur_pic": False,
                "source": "test",
            }
        )


def _semer_semaine(site_id, zone_id, methode, lundi, heures_prevues, heures_reelles):
    for i in range(7):
        _semer_jour(
            site_id, zone_id, methode, lundi + timedelta(days=i), heures_prevues, heures_reelles
        )


# ---------------------------------------------------------------------
# UC20 · Comparer le réalisé aux prévisions
# ---------------------------------------------------------------------
def test_comparer_realise_refuse_hors_responsable(ctx_planificateur, site_zone_modeles):
    site_id, _zone_id = site_zone_modeles
    with pytest.raises(AccesRefuse):
        comparaison.comparer_realise(ctx_planificateur, site_id)


def test_comparer_realise_calcule_les_ecarts(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    jour = date(2026, 2, 2)
    _semer_jour(
        site_id,
        zone_id,
        "regression_lineaire",
        jour,
        heures_prevues=100.0,
        heures_reelles=90.0,
        equipements_prevus=4,
        equipements_reels=3,
        ic_bas=80.0,
        ic_haut=110.0,
    )
    resultat = comparaison.comparer_realise(ctx_responsable, site_id, zone_id, debut=jour, fin=jour)
    assert resultat["nb_traites"] == 1
    assert resultat["nb_comparables"] == 1

    with transaction() as cur:
        rapprochements = DepotComparaisons(cur).rapprochements(
            site_id, zone_id, jour, jour, "regression_lineaire"
        )
    ligne = rapprochements[0]
    assert ligne["comparable"] is True

    with transaction() as cur:
        cur.execute(
            "SELECT ecart_absolu, ecart_relatif, ecart_equipements, dans_ic, comparable "
            "FROM comparaisons_realise WHERE prevision_id = %s",
            (ligne["prevision_id"],),
        )
        enregistre = cur.fetchone()
    assert float(enregistre["ecart_absolu"]) == pytest.approx(10.0)  # |90 - 100|
    # (100-90)/90 * 100
    assert float(enregistre["ecart_relatif"]) == pytest.approx(11.111, rel=1e-3)
    assert float(enregistre["ecart_equipements"]) == pytest.approx(1.0)  # |3 - 4|
    assert enregistre["dans_ic"] is True  # 80 <= 90 <= 110
    assert enregistre["comparable"] is True


def test_comparer_realise_jour_sans_reel_non_comparable(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    jour = date(2026, 6, 1)  # hors de l'historique déterministe (100 jours depuis 2026-01-05)
    with transaction() as cur:
        depot_modeles = DepotModeles(cur)
        version = depot_modeles.version_active(site_id, zone_id, "regression_lineaire", "heures")
        version_eqp = depot_modeles.version_active(
            site_id, zone_id, "regression_lineaire", "equipements"
        )
        DepotPrevisionsRessources(cur).inserer_plusieurs(
            [
                {
                    "site_id": site_id,
                    "zone_id": zone_id,
                    "date_jour": jour,
                    "modele_version_id": version["id"],
                    "modele_version_equipements_id": version_eqp["id"],
                    "methode": "regression_lineaire",
                    "volume_prevu": 1000.0,
                    "heures": 100.0,
                    "effectif": 10,
                    "equipements": 4,
                    "ic_bas": 90.0,
                    "ic_haut": 110.0,
                    "ic_bas_equipements": 1,
                    "ic_haut_equipements": 5,
                    "date_generation": datetime.now(),
                }
            ]
        )
    resultat = comparaison.comparer_realise(ctx_responsable, site_id, zone_id, debut=jour, fin=jour)
    assert resultat["nb_traites"] == 1
    assert resultat["nb_comparables"] == 0
    with transaction() as cur:
        cur.execute(
            """SELECT c.comparable, c.heures_reelles FROM comparaisons_realise c
               JOIN previsions_ressources p ON p.id = c.prevision_id
               WHERE p.date_jour = %s""",
            (jour,),
        )
        enregistre = cur.fetchone()
    assert enregistre["comparable"] is False
    assert enregistre["heures_reelles"] is None


# ---------------------------------------------------------------------
# UC21 · Détecter une dérive de modèle
# ---------------------------------------------------------------------
def test_detecter_derive_refuse_hors_responsable(ctx_planificateur, site_zone_modeles):
    site_id, _zone_id = site_zone_modeles
    with pytest.raises(AccesRefuse):
        comparaison.detecter_derive(ctx_planificateur, site_id)


def test_detecter_derive_aucune_alerte_sous_le_seuil(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    date_reference = date(2026, 3, 16)  # lundi
    semaine_courante = decaler_periode(date_reference, "semaine", -1)
    _semer_semaine(
        site_id,
        zone_id,
        "regression_lineaire",
        semaine_courante,
        heures_prevues=100.0,
        heures_reelles=98.0,  # MAPE ≈ 2 %, sous le seuil (10 %)
    )
    comparaison.comparer_realise(
        ctx_responsable,
        site_id,
        zone_id,
        debut=semaine_courante,
        fin=semaine_courante + timedelta(days=6),
    )
    alertes = comparaison.detecter_derive(ctx_responsable, site_id, date_reference=date_reference)
    assert alertes == []


def test_detecter_derive_orange_puis_rouge(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    date_reference = date(2026, 3, 16)  # lundi
    semaine_courante = decaler_periode(date_reference, "semaine", -1)

    # Une seule semaine en dérive (MAPE 20 %, au-delà du seuil de 10 %) -> orange.
    _semer_semaine(
        site_id,
        zone_id,
        "regression_lineaire",
        semaine_courante,
        heures_prevues=80.0,
        heures_reelles=100.0,
    )
    comparaison.comparer_realise(
        ctx_responsable,
        site_id,
        zone_id,
        debut=semaine_courante,
        fin=semaine_courante + timedelta(days=6),
    )
    alertes = comparaison.detecter_derive(ctx_responsable, site_id, date_reference=date_reference)
    assert len(alertes) == 1
    assert alertes[0]["niveau"] == "orange"
    assert alertes[0]["zone_id"] == zone_id
    alerte_id = alertes[0]["alerte_id"]

    with transaction() as cur:
        alerte = DepotAlertes(cur).ouvertes(site_id, "derive_modele")[0]
    assert alerte["id"] == alerte_id
    assert alerte["niveau"] == "orange"
    assert alerte["nb_occurrences"] == 1

    # La semaine suivante est, elle aussi, en dérive -> confirmation en rouge, même alerte
    # (déduplication), occurrences incrémentées.
    date_reference_suivante = date_reference + timedelta(days=7)
    semaine_suivante = decaler_periode(date_reference_suivante, "semaine", -1)
    _semer_semaine(
        site_id,
        zone_id,
        "regression_lineaire",
        semaine_suivante,
        heures_prevues=80.0,
        heures_reelles=100.0,
    )
    comparaison.comparer_realise(
        ctx_responsable,
        site_id,
        zone_id,
        debut=semaine_suivante,
        fin=semaine_suivante + timedelta(days=6),
    )
    alertes2 = comparaison.detecter_derive(
        ctx_responsable, site_id, date_reference=date_reference_suivante
    )
    assert len(alertes2) == 1
    assert alertes2[0]["niveau"] == "rouge"
    assert alertes2[0]["alerte_id"] == alerte_id  # même alerte mise à jour, pas dupliquée

    with transaction() as cur:
        ouvertes = DepotAlertes(cur).ouvertes(site_id, "derive_modele")
    assert len(ouvertes) == 1
    assert ouvertes[0]["niveau"] == "rouge"
    assert ouvertes[0]["nb_occurrences"] == 2
