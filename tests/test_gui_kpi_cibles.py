"""Test de fumée de l'écran KPI et cibles (UC15, UC16, UC17)."""

from __future__ import annotations

import time
from datetime import date

import pytest

from app.services import admin, modeles
from tests.conftest import connecter
from tests.test_modeles import _inserer_historique

pytestmark = [pytest.mark.gui, pytest.mark.integration]

JOUR_REFERENCE = date(2026, 1, 6)  # dans les 100 jours d'historique déterministe de test


def _preparer_zone(application):
    ctx = application.contexte
    site_id = admin.lister_sites(ctx)[0]["id"]
    zone_id = admin.lister_zones(ctx, site_id)[0]["id"]
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx, site_id, zone_id)
    for version in resume.versions:
        modeles.activer_version(
            ctx, version.version_id, retenir_pour_plan=version.methode == "regression_lineaire"
        )
    return site_id, zone_id


@pytest.fixture
def vue_kpi(application):
    connecter(application, "admin")
    site_id, zone_id = _preparer_zone(application)
    application.se_deconnecter()
    connecter(application, "resp")
    application.naviguer("kpi_cibles")
    application.racine.update()
    vue = application.vues["kpi_cibles"].page_suivi
    vue.site.definir(site_id)
    vue._sur_changement_site()
    vue.zone.definir(zone_id)
    vue.periodicite.definir("jour")
    vue.date_reference.definir(JOUR_REFERENCE)
    application.racine.update()
    return vue, site_id, zone_id


def test_calculer_les_kpi_remplit_le_tableau(vue_kpi, application):
    vue, _site_id, _zone_id = vue_kpi
    assert not vue.tableau.lignes()

    vue.calculer()
    for _ in range(200):
        application.racine.update()
        if vue.tableau.lignes() or application.erreurs:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    lignes = vue.tableau.lignes()
    assert len(lignes) == 27  # 7 précision x 2 méthodes + 13 sans méthode
    taux_hs = next(l for l in lignes if l["kpi_code"] == "TAUX_HS")
    assert taux_hs["valeur"] == pytest.approx(0.0)  # historique déterministe : pas d'heures sup
    assert taux_hs["statut"] == "vert"


def test_filtre_par_famille(vue_kpi, application):
    vue, _site_id, _zone_id = vue_kpi
    vue.calculer()
    for _ in range(200):
        application.racine.update()
        if vue.tableau.lignes() or application.erreurs:
            break
        time.sleep(0.05)
    assert application.erreurs == []

    vue.famille.definir("precision")
    vue._filtrer_tableau()
    application.racine.update()
    assert vue.tableau.lignes()
    assert all(l["famille"] == "precision" for l in vue.tableau.lignes())


def test_interpretation_kpi_hors_cible(vue_kpi, application):
    vue, _site_id, _zone_id = vue_kpi
    # Ligne synthétique (KPI hors cible), pour tester le panneau d'interprétation sans
    # dépendre du statut, incidental, des 27 KPI calculés à partir du jeu de test.
    vue.tableau.charger(
        [
            {
                "id": 999999,
                "kpi_code": "TAUX_HS",
                "kpi_libelle": "Taux d'heures supplémentaires (%)",
                "famille_libelle": "Ressources humaines",
                "methode_libelle": "—",
                "valeur_affichee": "20,0 %",
                "cible_affichee": "5,0 %",
                "statut_libelle": "Rouge",
                "tendance": "→",
                "sens": "baisse",
                "valeur": 20.0,
                "cible": 5.0,
                "statut": "rouge",
            }
        ],
        cle_id="id",
    )
    application.racine.update()
    assert not vue.cadre_interpretation.winfo_ismapped()  # rien sélectionné

    vue.tableau.selectionner(999999)
    application.racine.update()
    vue._sur_selection_kpi()
    application.racine.update()

    assert vue.cadre_interpretation.winfo_ismapped()
    assert "heures supplémentaires" in vue.label_explication.cget("text").lower()
    assert vue.label_conseil.cget("text").startswith("Action suggérée")

    vue.tableau.charger([], cle_id="id")
    vue._sur_selection_kpi()
    application.racine.update()
    assert not vue.cadre_interpretation.winfo_ismapped()


def test_gerer_les_cibles_ajouter_modifier_supprimer(vue_kpi, application):
    from app.gui.vues.kpi_cibles import FenetreObjectif
    from app.services import kpi

    _vue_suivi, site_id, zone_id = vue_kpi
    ctx = application.contexte
    onglet = application.vues["kpi_cibles"].page_cibles
    onglet.actualiser()
    application.racine.update()
    # Les cibles générales par défaut sont là, mais aucune n'est spécifique au site.
    assert onglet.tableau.lignes()
    assert not [l for l in onglet.tableau.lignes() if l["site_id"] == site_id]

    dialogue = FenetreObjectif(onglet, ctx)
    application.racine.update()
    taux_hs_id = next(v for v, libelle in dialogue.kpi._choix if "TAUX_HS" in libelle)
    dialogue.kpi.definir(taux_hs_id)
    dialogue.periodicite.definir("jour")
    dialogue.site.definir(site_id)
    dialogue._charger_zones()
    dialogue.zone.definir(zone_id)
    dialogue.widgets["valeur_cible"].definir(6)
    dialogue.widgets["seuil_orange"].definir(6)
    dialogue.widgets["seuil_rouge"].definir(10)
    dialogue._enregistrer()
    application.racine.update()
    assert dialogue.resultat is True
    dialogue.destroy()

    onglet.actualiser()
    application.racine.update()
    ajoutee = next(l for l in onglet.tableau.lignes() if l["site_id"] == site_id)
    assert ajoutee["kpi_code"] == "TAUX_HS"
    assert ajoutee["portee"].startswith("Plateforme Casablanca")

    modification = FenetreObjectif(onglet, ctx, objectif=ajoutee)
    application.racine.update()
    assert modification.kpi.saisie.instate(["disabled"])  # le KPI n'est plus modifiable
    assert modification.site.saisie.instate(["disabled"])  # le site n'est plus modifiable
    modification.widgets["seuil_orange"].definir(4)
    modification._enregistrer()
    application.racine.update()
    assert modification.resultat is True
    modification.destroy()

    onglet.actualiser()
    application.racine.update()
    ajoutee = next(l for l in onglet.tableau.lignes() if l["site_id"] == site_id)
    assert ajoutee["seuil_orange"] == pytest.approx(4.0)

    onglet.tableau.selectionner(ajoutee["id"])
    application.racine.update()
    onglet._supprimer()
    application.racine.update()
    assert not [o for o in kpi.lister_objectifs(ctx, site_id) if o["site_id"] == site_id]
