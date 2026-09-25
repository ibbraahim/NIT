"""Test de fumée de l'écran Modèles (UC07, UC08, UC09, UC10)."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from tests.conftest import connecter

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def _inserer_historique(site_id: int, zone_id: int, nb_jours: int = 100) -> None:
    debut = date(2026, 1, 5)
    lignes = []
    for i in range(nb_jours):
        jour = debut + timedelta(days=i)
        volume = 1000 + 30 * (i % 14)
        lignes.append(
            {
                "site_id": site_id,
                "zone_id": zone_id,
                "date_jour": jour,
                "volume_traite": volume,
                "effectif_present": 10,
                "heures_travaillees": 0.05 * volume + 10,
                "heures_sup": 0,
                "heures_interim": 0,
                "heures_absence": 0,
                "heures_inactives": 2,
                "equipements_mobilises": 4,
                "heures_usage_equipement": 20,
                "heures_disponibles_equipement": 30,
                "heures_panne_equipement": 0,
                "cout_rh": 0,
                "commandes_a_temps": 95,
                "commandes_totales": 100,
                "indicateur_pic": False,
                "source": "demonstration",
            }
        )
    with transaction() as cur:
        DepotHistorique(cur).upsert_plusieurs(lignes)


@pytest.fixture
def onglets_modeles(application):
    connecter(application, "admin")
    application.naviguer("modeles")
    application.racine.update()
    return application.vues["modeles"]


def test_parametres_recharges_apres_enregistrement(onglets_modeles, application):
    from app.services import modeles as service_modeles

    page = onglets_modeles.page_parametres
    page.widgets["part_test"].definir(25)
    page.widgets["seuil_derive_mape"].definir(12)

    page.enregistrer()
    application.racine.update()

    assert application.erreurs == []
    assert application.infos == ["Paramètres enregistrés."]
    enregistre = service_modeles.recuperer_parametres(application.contexte)
    assert enregistre["part_test"] == pytest.approx(0.25)
    assert enregistre["seuil_derive_mape"] == 12


def test_parametres_invalides_encadres(onglets_modeles, application):
    page = onglets_modeles.page_parametres
    page.widgets["part_test"].definir(99)  # hors bornes (5 % à 50 %)

    page.enregistrer()
    application.racine.update()

    assert application.erreurs == []  # message affiché sous le champ, pas en boîte de dialogue
    assert page.widgets["part_test"].message.cget("text") != ""


def test_retablir_defaut(onglets_modeles, application, monkeypatch):
    import app.gui.vues.modeles as vd

    page = onglets_modeles.page_parametres
    page.widgets["part_test"].definir(30)
    page.enregistrer()
    application.racine.update()

    monkeypatch.setattr(vd, "confirmer", lambda *a, **k: True)
    page.retablir()
    application.racine.update()

    assert page.widgets["part_test"].valeur() == "20"


def test_entrainement_complet_active_une_version(onglets_modeles, application, monkeypatch):
    import app.gui.vues.modeles as vd
    from app.services import admin as service_admin

    monkeypatch.setattr(vd, "_confirmer_activation", lambda *a, **k: True)
    page = onglets_modeles.page_entrainement
    site_id = page.site.valeur()
    assert site_id is not None
    zones = service_admin.lister_zones(application.contexte, site_id)
    zone = next(z for z in zones if z["nom"] == "Réception")
    _inserer_historique(site_id, zone["id"])

    page.zone.definir(zone["id"])
    application.racine.update()

    page.entrainer()
    for _ in range(200):  # jusqu'à ~10 s : laisse le fil d'entraînement se terminer
        application.racine.update()
        if len(page.tableau.lignes()) >= 4:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    versions = page.tableau.lignes()
    assert len(versions) == 4
    assert all(not v["actif"] for v in versions)

    candidate = next(
        v for v in versions if v["methode"] == "regression_lineaire" and v["cible"] == "heures"
    )
    page.tableau.selectionner(candidate["id"])
    application.racine.update()

    page.activer()
    application.racine.update()

    assert application.erreurs == []
    versions_apres = page.tableau.lignes()
    active = next(v for v in versions_apres if v["id"] == candidate["id"])
    assert active["actif"] is True and active["retenue_pour_plan"] is True
