"""Test de fumée de l'écran Tableau de bord (UC22) : contenu propre à chaque rôle."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.services import admin, alertes
from app.utils.dates import jours_semaine, lundi_de
from tests.conftest import connecter

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def _preparer_historique_charge(application) -> tuple[int, int]:
    """Historique chargeant fortement les heures supplémentaires (KPI hors cible, UC17)."""
    ctx = application.contexte
    site_id = admin.lister_sites(ctx)[0]["id"]
    zone_id = admin.lister_zones(ctx, site_id)[0]["id"]
    lundi = lundi_de(date.today())
    with transaction() as cur:
        DepotHistorique(cur).upsert_plusieurs(
            [
                {
                    "site_id": site_id,
                    "zone_id": zone_id,
                    "date_jour": jour,
                    "volume_traite": 1000.0,
                    "effectif_present": 10,
                    "heures_travaillees": 100.0,
                    "heures_sup": 20.0,
                    "heures_interim": 0,
                    "heures_absence": 0,
                    "heures_inactives": 0,
                    "equipements_mobilises": 2,
                    "heures_usage_equipement": 20.0,
                    "heures_disponibles_equipement": 24.0,
                    "heures_panne_equipement": 0.0,
                    "cout_rh": 100.0,
                    "commandes_a_temps": 95,
                    "commandes_totales": 100,
                    "indicateur_pic": False,
                    "source": "test",
                }
                for jour in jours_semaine(lundi)
            ]
        )
    return site_id, zone_id


def test_tableau_de_bord_planificateur_tuiles_ecarts_et_alertes(application):
    from app.services import kpi

    connecter(application, "admin")
    site_id, zone_id = _preparer_historique_charge(application)
    application.se_deconnecter()
    connecter(application, "resp")
    kpi.comparer_kpi_cibles(application.contexte, site_id, None, "jour", date.today())
    application.se_deconnecter()
    connecter(application, "planif")

    with transaction() as cur:
        from app.bd.depots.alertes import DepotAlertes

        alerte_id = DepotAlertes(cur).emettre(
            "penurie_equipement",
            "orange",
            None,
            site_id,
            zone_id,
            date.today() + timedelta(days=1),
            f"test_dashboard_{site_id}_{zone_id}",
            "Pénurie de test pour le tableau de bord.",
        )

    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    assert vue.periode.valeur() == "jour"  # vue jour par défaut pour le planificateur
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert application.erreurs == []
    codes = {v["kpi_code"] for v in vue.dernieres_valeurs_kpi}
    assert {"ADEQUATION", "TAUX_DISPO_EQP", "JOURS_PENURIE"} <= codes
    assert vue.tableau_ecarts is not None
    assert alertes.compter_alertes_ouvertes(application.contexte) >= 1
    assert vue.tableau_alertes.lignes()

    vue._ouvrir_alerte({"id": alerte_id})
    application.racine.update()
    assert application.vue_courante == "alertes"
    vue_alertes = application.vues["alertes"]
    assert vue_alertes.tableau.ligne_selectionnee()["id"] == alerte_id


def test_tableau_de_bord_responsable_tuiles_et_periode_semaine(application):
    connecter(application, "resp")
    site_id = admin.lister_sites(application.contexte)[0]["id"]

    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    assert vue.periode.valeur() == "semaine"  # vue semaine par défaut pour le responsable
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert application.erreurs == []
    assert hasattr(vue, "dernieres_valeurs_kpi")
    # Contrairement au planificateur, le tableau de bord du responsable ne montre pas la
    # liste des alertes ni le tableau des écarts (contenu propre au rôle, cf. le prompt).
    assert not hasattr(vue, "tableau_alertes")
    assert not hasattr(vue, "tableau_ecarts")


def test_tableau_de_bord_direction_tuiles_et_periode_mois(application):
    connecter(application, "direction")
    site_id = admin.lister_sites(application.contexte)[0]["id"]

    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    assert vue.periode.valeur() == "mois"  # vue mois par défaut pour la direction
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert application.erreurs == []
    assert hasattr(vue, "dernieres_valeurs_kpi")


def test_tableau_de_bord_navigation_periode(application):
    connecter(application, "resp")
    site_id = admin.lister_sites(application.contexte)[0]["id"]
    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()
    reference_initiale = vue.periode_reference

    vue._changer_periode(-1)
    application.racine.update()
    assert application.erreurs == []
    assert vue.periode_reference < reference_initiale
