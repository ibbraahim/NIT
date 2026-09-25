"""Test de fumée de l'écran Tableau de bord (UC22)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.services import admin, alertes
from app.utils.dates import jours_semaine, lundi_de
from tests.conftest import connecter

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def _preparer_kpi_rouge_et_alerte(application) -> tuple[int, int]:
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


def test_tableau_de_bord_affiche_kpi_hors_cible(application):
    from app.services import kpi

    connecter(application, "admin")
    site_id, _zone_id = _preparer_kpi_rouge_et_alerte(application)
    application.se_deconnecter()
    connecter(application, "resp")
    # UC17 calcule et enregistre les statuts que le tableau de bord lira ensuite.
    kpi.comparer_kpi_cibles(application.contexte, site_id, None, "semaine", date.today())

    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert application.erreurs == []
    lignes = vue.tableau_kpi.lignes()
    taux_hs = next(l for l in lignes if l["kpi_code"] == "TAUX_HS")
    assert taux_hs["statut"] == "rouge"


def test_tableau_de_bord_double_clic_ouvre_l_alerte(application):
    connecter(application, "admin")
    site_id = admin.lister_sites(application.contexte)[0]["id"]
    zone_id = admin.lister_zones(application.contexte, site_id)[0]["id"]
    application.se_deconnecter()
    connecter(application, "resp")

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
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert alertes.compter_alertes_ouvertes(application.contexte) >= 1
    assert vue.tableau_alertes.lignes()

    vue._ouvrir_alerte({"id": alerte_id})
    application.racine.update()
    assert application.vue_courante == "alertes"
    vue_alertes = application.vues["alertes"]
    assert vue_alertes.tableau.ligne_selectionnee()["id"] == alerte_id
