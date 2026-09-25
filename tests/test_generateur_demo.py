"""Générateur de démonstration : historique, prévisions, entraînement et activation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.demo import generateur

pytestmark = pytest.mark.integration

DATE_REFERENCE = date(2026, 9, 25)  # vendredi


# ---------------------------------------------------------------------
# Historique : congestion, heures sup/intérim, saisonnalité
# ---------------------------------------------------------------------
def test_ligne_activite_jour_normal_pas_de_sup_ni_interim():
    ligne = generateur._ligne_activite(
        1,
        1,
        "Réception",
        date(2026, 3, 9),
        1000.0,
        False,
        __import__("numpy").random.default_rng(1),
    )
    assert ligne["heures_sup"] == 0.0 and ligne["heures_interim"] == 0.0
    assert ligne["heures_inactives"] > 0  # volume sous la capacité : personnel sous-utilisé
    assert ligne["heures_travaillees"] == pytest.approx(75.0)  # capacité = 10 x 7,5 h
    assert ligne["heures_travaillees"] - ligne["heures_inactives"] < 75.0


def test_ligne_activite_pic_declenche_heures_sup_et_interim():
    import numpy as np

    # Volume très supérieur à la capacité de la zone (10 x 7,5 h = 75 h) : congestion.
    ligne = generateur._ligne_activite(
        1, 1, "Réception", date(2026, 3, 12), 2500.0, True, np.random.default_rng(1)
    )
    assert ligne["heures_sup"] > 0 and ligne["heures_interim"] > 0
    assert ligne["heures_inactives"] == 0.0
    assert ligne["effectif_present"] > generateur.EFFECTIF_ZONES["Réception"]
    assert ligne["indicateur_pic"] is True


def test_ligne_activite_effet_congestion_non_lineaire():
    """Au-delà de 85 % de la capacité, les heures nécessaires augmentent plus vite que le
    volume (non-linéarité que seul le réseau de neurones peut apprendre)."""
    import numpy as np

    rng = np.random.default_rng(1)
    # Un point juste avant le seuil et un point bien après, avec le même écart de volume.
    heures_zone = generateur.EFFECTIF_ZONES["Réception"] * generateur.DUREE_POSTE
    coeff = heures_zone / generateur.VOLUME_BASE_ZONES["Réception"]
    volume_avant_seuil = (heures_zone * 0.80) / coeff
    volume_apres_seuil = (heures_zone * 1.10) / coeff
    avant = generateur._ligne_activite(
        1, 1, "Réception", date(2026, 3, 9), volume_avant_seuil, False, rng
    )
    apres = generateur._ligne_activite(
        1, 1, "Réception", date(2026, 3, 9), volume_apres_seuil, False, rng
    )
    heures_necessaires_avant = avant["heures_travaillees"] - avant["heures_inactives"]
    heures_necessaires_apres = apres["heures_travaillees"]  # > capacité : tout est "nécessaire"
    ratio_volume = volume_apres_seuil / volume_avant_seuil
    ratio_heures = heures_necessaires_apres / heures_necessaires_avant
    assert ratio_heures > ratio_volume  # la relation n'est plus linéaire au-delà du seuil


def test_ligne_activite_respecte_les_contraintes_du_schema():
    import numpy as np

    for volume in (0.0, 500.0, 1200.0, 3000.0, 6000.0):
        ligne = generateur._ligne_activite(
            1, 1, "Réception", date(2026, 3, 9), volume, False, np.random.default_rng(1)
        )
        assert ligne["heures_inactives"] <= ligne["heures_travaillees"]
        assert ligne["heures_usage_equipement"] <= ligne["heures_disponibles_equipement"]
        assert ligne["commandes_a_temps"] <= ligne["commandes_totales"]
        assert ligne["equipements_mobilises"] <= generateur.NB_EQUIPEMENTS_ZONES["Réception"]
        assert all(
            ligne[champ] >= 0
            for champ in (
                "volume_traite",
                "effectif_present",
                "heures_travaillees",
                "heures_sup",
                "heures_interim",
                "heures_inactives",
                "equipements_mobilises",
                "heures_usage_equipement",
                "heures_panne_equipement",
                "cout_rh",
            )
        )


def test_saison_annuelle_pic_decembre_creux_juin():
    assert generateur._saison_annuelle(12) > generateur._saison_annuelle(6)
    assert generateur._saison_annuelle(12) == pytest.approx(
        1 + generateur.AMPLITUDE_SAISON_ANNUELLE
    )


def test_campagnes_promotionnelles_bornees():
    import numpy as np

    rng = np.random.default_rng(generateur.GRAINE)
    debut, fin = date(2025, 1, 1), date(2026, 6, 30)
    campagnes = generateur._campagnes_promotionnelles(rng, debut, fin)
    assert campagnes  # au moins une campagne sur 18 mois
    assert all(debut <= jour <= fin for jour in campagnes)
    assert all(
        generateur.BOOST_CAMPAGNE_MIN <= b <= generateur.BOOST_CAMPAGNE_MAX
        for b in campagnes.values()
    )


# ---------------------------------------------------------------------
# Générateur complet (base de test)
# ---------------------------------------------------------------------
@pytest.fixture
def demo_complete(bd_vierge):
    return generateur.generer_demonstration(DATE_REFERENCE, afficher=lambda _m: None)


def test_historique_genere_pour_toutes_les_zones(demo_complete):
    site_id = demo_complete["site_id"]
    with transaction() as cur:
        cur.execute(
            "SELECT zone_id, count(*) AS n FROM historique_activite WHERE site_id = %s "
            "GROUP BY zone_id",
            (site_id,),
        )
        comptes = {ligne["zone_id"]: ligne["n"] for ligne in cur.fetchall()}
    assert set(comptes) == set(demo_complete["zones"].values())
    # Environ 18 mois x 6 jours ouvrés / 7, jamais un dimanche.
    for n in comptes.values():
        assert 460 <= n <= 500
    with transaction() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM historique_activite WHERE EXTRACT(ISODOW FROM date_jour) = 7"
        )
        assert cur.fetchone()["n"] == 0


def test_previsions_incluent_le_pic_et_le_creux(demo_complete):
    jeudi_pic = generateur.semaine_demonstration(DATE_REFERENCE) + timedelta(days=3)
    mardi_creux = generateur.semaine_demonstration(DATE_REFERENCE) + timedelta(days=8)
    zone_reception = demo_complete["zones"]["Réception"]
    with transaction() as cur:
        cur.execute(
            "SELECT volume_prevu::float, indicateur_pic FROM previsions_volume "
            "WHERE zone_id = %s AND date_jour = %s",
            (zone_reception, jeudi_pic),
        )
        pic = cur.fetchone()
        cur.execute(
            "SELECT volume_prevu::float FROM previsions_volume WHERE zone_id = %s AND date_jour = %s",
            (zone_reception, mardi_creux),
        )
        creux = cur.fetchone()
    # Volume de référence (sans le pic) recalculé à partir de la même formule que le générateur.
    baseline = (
        generateur.VOLUME_BASE_ZONES["Réception"]
        * generateur.MULTIPLICATEURS_JOUR[3]
        * generateur._saison_annuelle(jeudi_pic.month)
    )
    assert pic["indicateur_pic"] is True
    assert pic["volume_prevu"] == pytest.approx(baseline * generateur.BOOST_PIC_DEMO, rel=1e-6)
    assert creux is not None and creux["volume_prevu"] > 0


def test_deux_chariots_reception_en_maintenance(demo_complete):
    lundi_demo = generateur.semaine_demonstration(DATE_REFERENCE)
    with transaction() as cur:
        cur.execute(
            """SELECT count(*) AS n FROM indisponibilites_equipements i
               JOIN equipements e ON e.id = i.equipement_id
               WHERE e.zone_id = %s AND i.date_debut = %s AND i.date_fin = %s""",
            (demo_complete["zones"]["Réception"], lundi_demo, lundi_demo + timedelta(days=4)),
        )
        assert cur.fetchone()["n"] == generateur.NB_CHARIOTS_MAINTENANCE_DEMO


def test_modeles_entraines_et_regression_lineaire_retenue(demo_complete):
    site_id = demo_complete["site_id"]
    with transaction() as cur:
        cur.execute(
            """SELECT methode::text, cible::text, count(*) AS n,
                      count(*) FILTER (WHERE actif) AS actifs,
                      count(*) FILTER (WHERE retenue_pour_plan) AS retenues
               FROM modeles_versions WHERE site_id = %s GROUP BY methode, cible""",
            (site_id,),
        )
        lignes = {(l["methode"], l["cible"]): l for l in cur.fetchall()}
    nb_zones = len(demo_complete["zones"])
    assert lignes[("regression_lineaire", "heures")]["actifs"] == nb_zones
    assert lignes[("regression_lineaire", "heures")]["retenues"] == nb_zones
    assert lignes[("regression_lineaire", "equipements")]["actifs"] == nb_zones
    assert lignes[("reseau_neurones", "heures")]["actifs"] == 0
    assert lignes[("reseau_neurones", "equipements")]["actifs"] == 0
    for cle in lignes:
        assert lignes[cle]["n"] == nb_zones  # une version par zone et par entraînement


def test_bandeau_de_demonstration_signale(demo_complete):
    with transaction() as cur:
        cur.execute("SELECT valeur FROM parametres_application WHERE cle = 'donnees_demonstration'")
        assert cur.fetchone()["valeur"] == "oui"
