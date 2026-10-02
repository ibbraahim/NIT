"""Bottom line : simulation sans / avec Workly, alertes, automatisation, ROI et paramètres."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.bd.connexion import transaction
from app.contexte import Contexte
from app.demo import generateur
from app.erreurs import AccesRefuse, DonneesInvalides
from app.services import bottom_line
from app.services.auth import authentifier

DEFAUTS = {p.cle: p.defaut for p in bottom_line.PARAMETRES}
TAUX = {"interne": 10.0, "heures_sup": 15.0}


def _jour(besoin, plan_workly, plan_reconduit, commandes=100, jour=1, zone="Réception"):
    return {
        "date_jour": date(2026, 9, jour),
        "zone": zone,
        "besoin": besoin,
        "plan_workly": plan_workly,
        "plan_reconduit": plan_reconduit,
        "duree_poste": 10.0,
        "commandes_totales": commandes,
        "commandes_a_temps": commandes,
    }


# ---------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------
def test_simulation_deficit_et_exces_valorises():
    # Besoin 100 h. Reconduit : 80 h (déficit 20 h). Workly : 110 h (excès 10 h).
    resultat = bottom_line.simuler([_jour(100, 110, 80)], TAUX, DEFAUTS)
    sans, avec, gains = resultat["sans"], resultat["avec"], resultat["gains"]
    assert sans["heures_sup"] == 20 and sans["heures_inactives"] == 0
    assert avec["heures_sup"] == 0 and avec["heures_inactives"] == 10
    assert sans["cout_rh"] == 80 * 10 + 20 * 15
    assert avec["cout_rh"] == 110 * 10
    assert gains["heures_mal_allouees"] == 10  # 20 h mal allouées contre 10 h
    assert gains["postes_mal_alloues"] == pytest.approx(1.0)


def test_simulation_retard_estime_et_penalites():
    # Déficit de 20 % du besoin, sensibilité 0,5, 100 commandes → 10 commandes en retard.
    parametres = {**DEFAUTS, "bl_sensibilite_retard": 0.5, "bl_penalite_retard": 20.0}
    resultat = bottom_line.simuler([_jour(100, 100, 80)], TAUX, parametres)
    assert resultat["sans"]["commandes_en_retard"] == pytest.approx(10)
    assert resultat["sans"]["penalites"] == pytest.approx(200)
    assert resultat["sans"]["taux_service"] == pytest.approx(90)
    assert resultat["avec"]["taux_service"] == pytest.approx(100)
    assert resultat["gains"]["points_service"] == pytest.approx(10)
    assert resultat["gains"]["cout_total"] > 200  # pénalités + heures sup évitées


def test_simulation_sans_jour_comparable():
    resultat = bottom_line.simuler([], TAUX, DEFAUTS)
    assert resultat["nb_jours"] == 0
    assert resultat["gains"]["cout_total"] == 0
    assert resultat["gains"]["points_service"] is None


def test_simulation_gain_negatif_quand_workly_fait_moins_bien():
    resultat = bottom_line.simuler([_jour(100, 70, 100)], TAUX, DEFAUTS)
    assert resultat["gains"]["heures_mal_allouees"] < 0
    assert resultat["gains"]["cout_total"] < 0


# ---------------------------------------------------------------------
# Alertes, automatisation, ROI
# ---------------------------------------------------------------------
def _alerte(type_alerte="penurie_equipement", statut="resolue", avance=2, prise=3, zone=1):
    creation = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    return {
        "type": type_alerte,
        "niveau": "rouge",
        "statut": statut,
        "zone_id": zone,
        "date_concernee": creation.date() + timedelta(days=avance),
        "date_creation": creation,
        "date_prise_en_charge": creation + timedelta(hours=prise) if statut != "ouverte" else None,
        "date_resolution": creation + timedelta(hours=prise * 2) if statut == "resolue" else None,
    }


def test_analyse_alertes_delais_et_penuries_anticipees():
    lignes = [
        _alerte(avance=2, prise=2),
        _alerte(avance=2, prise=4),  # même zone et même date : une seule pénurie
        _alerte(type_alerte="sous_effectif", avance=0, prise=6, zone=2),
        _alerte(statut="ouverte", avance=1, zone=3),
    ]
    resultat = bottom_line.analyser_alertes(lignes, {**DEFAUTS, "bl_cout_penurie_jour": 1000})
    assert resultat["nb"] == 4 and resultat["nb_traitees"] == 3
    assert resultat["taux_traitement"] == pytest.approx(75)
    assert resultat["delai_prise_en_charge_h"] == pytest.approx(4)  # (2 + 4 + 6) / 3
    assert resultat["nb_anticipees"] == 3 and resultat["taux_anticipation"] == pytest.approx(75)
    assert resultat["avance_moyenne_j"] == pytest.approx(5 / 3)
    assert resultat["penuries_traitees"] == 1
    assert resultat["valeur_penuries"] == 1000


def test_analyse_alertes_vide():
    resultat = bottom_line.analyser_alertes([], DEFAUTS)
    assert resultat["nb"] == 0 and resultat["taux_traitement"] is None
    assert resultat["delai_prise_en_charge_h"] is None and resultat["valeur_penuries"] == 0


def test_analyse_taches_temps_manuel_evite():
    lignes = [
        {"tache": "a", "statut": "succes", "duree_s": 600.0},
        {"tache": "b", "statut": "succes", "duree_s": 1200.0},
        {"tache": "c", "statut": "echec", "duree_s": 600.0},
    ]
    parametres = {**DEFAUTS, "bl_minutes_manuelles_par_tache": 30}
    resultat = bottom_line.analyser_taches(lignes, TAUX, parametres)
    assert resultat["nb_succes"] == 2 and resultat["nb_echecs"] == 1
    assert resultat["taux_reussite"] == pytest.approx(200 / 3)
    assert resultat["heures_evitees"] == pytest.approx(1.0)
    assert resultat["valeur_heures_evitees"] == pytest.approx(10.0)
    assert resultat["duree_machine_h"] == pytest.approx(0.6667, abs=1e-3)


def test_roi_annualise_et_delai_de_retour():
    roi = bottom_line.calculer_roi(gain_periode=1000, nb_jours=30, cout_mise_en_place=6000)
    assert roi["gain_annuel"] == pytest.approx(1000 * 365 / 30)
    assert roi["roi_pct"] == pytest.approx((roi["gain_annuel"] - 6000) / 6000 * 100)
    assert roi["retour_mois"] == pytest.approx(6000 / (roi["gain_annuel"] / 12))


def test_roi_non_renseigne_sans_cout_de_mise_en_place():
    roi = bottom_line.calculer_roi(gain_periode=1000, nb_jours=30, cout_mise_en_place=0)
    assert roi["roi_pct"] is None and roi["retour_mois"] is None


def test_simulation_series_par_jour_et_par_zone():
    jours = [
        _jour(100, 100, 80, jour=1, zone="A"),
        _jour(100, 100, 80, jour=2, zone="B"),
        _jour(100, 100, 100, jour=2, zone="A"),
    ]
    resultat = bottom_line.simuler(jours, TAUX, DEFAUTS)
    par_jour = dict(resultat["serie_gains"])
    par_zone = dict(resultat["gains_par_zone"])
    assert list(par_jour) == [date(2026, 9, 1), date(2026, 9, 2)]
    assert par_jour[date(2026, 9, 1)] > 0 and par_jour[date(2026, 9, 2)] > 0
    assert par_zone["A"] == pytest.approx(par_jour[date(2026, 9, 1)])
    assert par_zone["B"] > 0
    assert sum(par_jour.values()) == pytest.approx(resultat["gains"]["cout_total"])
    assert sum(par_zone.values()) == pytest.approx(resultat["gains"]["cout_total"])


# ---------------------------------------------------------------------
# Droits et paramètres
# ---------------------------------------------------------------------
def _ctx(role):
    return Contexte(utilisateur_id=99, identifiant=role, role=role, sites=frozenset({1}))


@pytest.mark.parametrize("role", ["planificateur"])
def test_planificateur_ne_lit_pas_le_bottom_line(role):
    with pytest.raises(AccesRefuse):
        bottom_line.calculer_bottom_line(_ctx(role), 1, None, date(2026, 9, 1), date(2026, 9, 30))


def test_enregistrer_parametres_refuse_hors_administrateur():
    with pytest.raises(AccesRefuse):
        bottom_line.enregistrer_parametres(_ctx("responsable"), {"bl_penalite_retard": 5})


@pytest.mark.integration
def test_parametres_par_defaut_puis_enregistres(ctx_admin):
    assert bottom_line.lire_parametres(ctx_admin) == DEFAUTS
    assert (
        bottom_line.enregistrer_parametres(
            ctx_admin, {"bl_penalite_retard": "35,5", "bl_cout_mise_en_place": "120000"}
        )
        == 2
    )
    lus = bottom_line.lire_parametres(ctx_admin)
    assert lus["bl_penalite_retard"] == pytest.approx(35.5)
    assert lus["bl_cout_mise_en_place"] == 120000
    assert lus["bl_sensibilite_retard"] == DEFAUTS["bl_sensibilite_retard"]


@pytest.mark.integration
def test_enregistrer_parametres_rejette_les_valeurs_invalides(ctx_admin):
    with pytest.raises(DonneesInvalides) as exc:
        bottom_line.enregistrer_parametres(
            ctx_admin, {"bl_sensibilite_retard": "1,5", "bl_penalite_retard": "abc"}
        )
    assert set(exc.value.erreurs) == {"bl_sensibilite_retard", "bl_penalite_retard"}
    assert bottom_line.lire_parametres(ctx_admin) == DEFAUTS  # rien n'a été écrit


# ---------------------------------------------------------------------
# Jeu de démonstration complet
# ---------------------------------------------------------------------
@pytest.mark.integration
def test_bottom_line_sur_la_demonstration(bd_vierge):
    reference = date(2026, 9, 25)
    demo = generateur.generer_demonstration(reference, afficher=lambda _m: None)
    site_id = demo["site_id"]
    ctx_resp = authentifier("resp", "Resp2026!")

    with transaction() as cur:
        cur.execute("""SELECT min(date_jour) AS debut, max(date_jour) AS fin
               FROM comparaisons_realise c JOIN previsions_ressources p ON p.id = c.prevision_id
               WHERE c.comparable""")
        bornes = cur.fetchone()
    resultat = bottom_line.calculer_bottom_line(
        ctx_resp, site_id, None, bornes["debut"], bornes["fin"]
    )

    simulation = resultat["simulation"]
    assert simulation["nb_jours"] > 0
    assert simulation["avec"]["heures_mal_allouees"] > 0  # une prévision n'est jamais exacte
    assert simulation["sans"]["cout_total"] > 0
    assert resultat["nb_jours_historique"] >= simulation["nb_jours"]
    assert resultat["devise"] == "MAD"
    assert resultat["gain_net"] == pytest.approx(
        simulation["gains"]["cout_total"]
        + resultat["alertes"]["valeur_penuries"]
        + resultat["automatisation"]["valeur_heures_evitees"]
    )
    assert set(resultat["repartition_gain"]) >= {"Heures sup. évitées", "Pénuries évitées"}
    assert simulation["serie_gains"] and simulation["gains_par_zone"]

    # Filtrer sur une zone restreint les jours comparés.
    with transaction() as cur:
        cur.execute("SELECT min(id) AS id FROM zones WHERE site_id = %s", (site_id,))
        zone_id = cur.fetchone()["id"]
    une_zone = bottom_line.calculer_bottom_line(
        ctx_resp, site_id, zone_id, bornes["debut"], bornes["fin"]
    )
    assert 0 < une_zone["simulation"]["nb_jours"] < simulation["nb_jours"]
