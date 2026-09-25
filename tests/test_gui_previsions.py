"""Test de fumée de l'écran Prévisions (UC11)."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.previsions import DepotPrevisionsVolume
from app.services import admin, modeles
from tests.conftest import connecter
from tests.test_modeles import _inserer_historique

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def _preparer_zone_avec_modele(application):
    """Historique, entraînement et activation (RL et RN) pour la première zone du site."""
    ctx = application.contexte
    site_id = admin.lister_sites(ctx)[0]["id"]
    zone_id = admin.lister_zones(ctx, site_id)[0]["id"]
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx, site_id, zone_id)
    for version in resume.versions:
        modeles.activer_version(
            ctx, version.version_id, retenir_pour_plan=version.methode == "regression_lineaire"
        )
    demain = date.today() + timedelta(days=1)
    with transaction() as cur:
        DepotPrevisionsVolume(cur).upsert_plusieurs(
            [
                {
                    "site_id": site_id,
                    "zone_id": zone_id,
                    "date_jour": demain + timedelta(days=i),
                    "volume_prevu": 1000.0,
                    "indicateur_pic": False,
                    "source": "test",
                }
                for i in range(7)
            ]
        )
    return site_id, zone_id


def test_generer_previsions_remplit_le_tableau(application):
    connecter(application, "admin")
    site_id, zone_id = _preparer_zone_avec_modele(application)
    application.se_deconnecter()
    connecter(application, "planif")  # se reconnecte avec le rôle qui peut générer
    application.naviguer("previsions")
    application.racine.update()
    vue = application.vues["previsions"]

    vue.site.definir(site_id)
    vue._sur_changement_site()
    vue.zone.definir(zone_id)
    vue.actualiser_donnees()
    application.racine.update()
    assert not vue.tableau.lignes()

    vue.generer()
    for _ in range(200):
        application.racine.update()
        if vue.tableau.lignes() or application.erreurs:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    lignes = vue.tableau.lignes()
    assert len(lignes) == 7
    assert all(l["heures_rl"] > 0 for l in lignes)
    assert all(l["modele_actif_coche"] == "RL" for l in lignes)


def test_export_excel(application, tmp_path, monkeypatch):
    import app.gui.vues.previsions as vp

    connecter(application, "admin")
    site_id, zone_id = _preparer_zone_avec_modele(application)
    application.se_deconnecter()
    connecter(application, "planif")
    application.naviguer("previsions")
    application.racine.update()
    vue = application.vues["previsions"]
    vue.site.definir(site_id)
    vue._sur_changement_site()
    vue.zone.definir(zone_id)
    vue.generer()
    for _ in range(200):
        application.racine.update()
        if vue.tableau.lignes() or application.erreurs:
            break
        time.sleep(0.05)

    destination = tmp_path / "export.xlsx"
    monkeypatch.setattr(vp, "choisir_fichier_a_enregistrer", lambda *a, **k: destination)
    vue.exporter()
    assert destination.is_file()


def test_responsable_ne_peut_pas_generer(application):
    connecter(application, "resp")
    application.naviguer("previsions")
    application.racine.update()
    vue = application.vues["previsions"]
    assert not vue.peut_generer
    assert not vue.b_generer.winfo_ismapped()
