"""Test de fumée de l'écran Comparaison réel / prévu (UC20)."""

from __future__ import annotations

import time
from datetime import date, datetime

import pytest

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.bd.depots.modeles import DepotModeles
from app.bd.depots.previsions_ressources import DepotPrevisionsRessources
from app.services import admin, modeles
from tests.conftest import connecter
from tests.test_modeles import _inserer_historique

pytestmark = [pytest.mark.gui, pytest.mark.integration]

JOUR_COMPARAISON = date(2026, 2, 2)  # dans les 100 jours d'historique déterministe de test


def _preparer_zone_avec_rapprochement(application):
    """Historique, modèles entraînés/activés et une prévision RL sur ``JOUR_COMPARAISON``."""
    ctx = application.contexte
    site_id = admin.lister_sites(ctx)[0]["id"]
    zone_id = admin.lister_zones(ctx, site_id)[0]["id"]
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx, site_id, zone_id)
    for version in resume.versions:
        modeles.activer_version(
            ctx, version.version_id, retenir_pour_plan=version.methode == "regression_lineaire"
        )
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
                    "date_jour": JOUR_COMPARAISON,
                    "modele_version_id": version["id"],
                    "modele_version_equipements_id": version_eqp["id"],
                    "methode": "regression_lineaire",
                    "volume_prevu": 1000.0,
                    "heures": 60.0,
                    "effectif": 8,
                    "equipements": 3,
                    "ic_bas": 55.0,
                    "ic_haut": 65.0,
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
                "date_jour": JOUR_COMPARAISON,
                "volume_traite": 1000.0,
                "effectif_present": 8,
                "heures_travaillees": 62.0,
                "heures_sup": 0,
                "heures_interim": 0,
                "heures_absence": 0,
                "heures_inactives": 0,
                "equipements_mobilises": 4,
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
    return site_id, zone_id


def test_comparer_le_realise_remplit_le_tableau(application):
    connecter(application, "admin")
    site_id, zone_id = _preparer_zone_avec_rapprochement(application)
    application.se_deconnecter()
    connecter(application, "resp")
    application.naviguer("comparaison")
    application.racine.update()
    vue = application.vues["comparaison"]

    vue.site.definir(site_id)
    vue._sur_changement_site()
    vue.zone.definir(zone_id)
    vue.date_debut.definir(JOUR_COMPARAISON)
    vue.date_fin.definir(JOUR_COMPARAISON)
    vue.actualiser_donnees()
    application.racine.update()

    # Le tableau lit les rapprochements en direct (JOIN prévision/réel) : pas besoin d'avoir
    # cliqué sur « Comparer le réalisé » pour voir les écarts.
    assert application.erreurs == []
    lignes = vue.tableau.lignes()
    assert len(lignes) == 1
    assert lignes[0]["methode_libelle"] == "RL"
    assert lignes[0]["heures_prevues"] == pytest.approx(60.0)
    assert lignes[0]["heures_reelles"] == pytest.approx(62.0)
    assert lignes[0]["ecart_absolu"] == pytest.approx(2.0)
    assert lignes[0]["dans_ic"] is True

    # « Comparer le réalisé » persiste le résultat dans comparaisons_realise (UC20 : matière
    # première des KPI de précision et de la détection de dérive, UC21).
    with transaction() as cur:
        cur.execute("SELECT count(*) AS n FROM comparaisons_realise")
        assert cur.fetchone()["n"] == 0

    vue.comparer()
    for _ in range(200):
        application.racine.update()
        if application.infos or application.erreurs:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    assert len(application.infos) == 1
    with transaction() as cur:
        cur.execute("SELECT ecart_absolu, dans_ic FROM comparaisons_realise")
        enregistre = cur.fetchone()
    assert enregistre is not None
    assert float(enregistre["ecart_absolu"]) == pytest.approx(2.0)
    assert enregistre["dans_ic"] is True
