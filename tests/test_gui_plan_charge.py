"""Test de fumée de l'écran Plan de charge (UC12, UC13, UC14)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.previsions import DepotPrevisionsVolume
from app.services import admin, auth, modeles, planification
from app.utils.dates import jours_semaine, lundi_de
from tests.conftest import connecter
from tests.test_modeles import _inserer_historique

pytestmark = [pytest.mark.gui, pytest.mark.integration]

SEMAINE_CIBLE_DECALAGE = 10  # une semaine sans conflit avec l'historique synthétique


def _preparer_semaine_avec_prevision(application):
    """Historique, modèle actif, capacités et prévisions de ressources pour une semaine."""
    ctx = application.contexte  # administrateur : entraînement (UC08) et activation (UC10)
    ctx_planif = auth.authentifier("planif", "Planif2026!")  # UC11 : réservé au planificateur
    site_id = admin.lister_sites(ctx)[0]["id"]
    zones = admin.lister_zones(ctx, site_id)
    lundi = lundi_de(date.today() + timedelta(days=SEMAINE_CIBLE_DECALAGE))
    jours = jours_semaine(lundi)
    for zone in zones:
        _inserer_historique(site_id, zone["id"])
        resume = modeles.entrainer_modeles(ctx, site_id, zone["id"])
        for version in resume.versions:
            modeles.activer_version(
                ctx, version.version_id, retenir_pour_plan=version.methode == "regression_lineaire"
            )
        with transaction() as cur:
            DepotPrevisionsVolume(cur).upsert_plusieurs(
                [
                    {
                        "site_id": site_id,
                        "zone_id": zone["id"],
                        "date_jour": jour,
                        "volume_prevu": 1000.0,
                        "indicateur_pic": False,
                        "source": "test",
                    }
                    for jour in jours
                ]
            )
        for jour in jours:
            admin.enregistrer_capacites(ctx, site_id, {(zone["id"], jour): (10, 1)})
        planification.generer_previsions(ctx_planif, site_id, zone["id"], horizon_jours=28)
    return site_id, lundi


@pytest.fixture
def plan_pret(application):
    connecter(application, "admin")
    site_id, lundi = _preparer_semaine_avec_prevision(application)
    application.se_deconnecter()
    return site_id, lundi


def test_proposer_construit_la_grille(plan_pret, application):
    site_id, lundi = plan_pret
    connecter(application, "planif")
    application.naviguer("plan_charge")
    application.racine.update()
    vue = application.vues["plan_charge"]
    vue.site.definir(site_id)
    vue._sur_changement_site()
    vue.semaine = lundi
    vue.charger_semaine()
    application.racine.update()
    assert "Aucun plan" in vue.label_statut.cget("text")

    vue.proposer()
    application.racine.update()

    assert application.erreurs == []
    assert vue.plan_donnees is not None
    assert vue.plan_donnees["plan"]["statut"] == "brouillon"
    assert len(vue.cellules) == 28  # 4 zones x 7 jours
    assert "Brouillon" in vue.label_statut.cget("text")


def test_enregistrer_brouillon_et_soumettre(plan_pret, application):
    site_id, lundi = plan_pret
    connecter(application, "planif")
    application.naviguer("plan_charge")
    application.racine.update()
    vue = application.vues["plan_charge"]
    vue.site.definir(site_id)
    vue._sur_changement_site()
    vue.semaine = lundi
    vue.charger_semaine()
    vue.proposer()
    application.racine.update()

    # Commente toutes les cases en dépassement, condition pour pouvoir soumettre.
    for cellule in vue.cellules.values():
        if planification.statut_couleur_ligne(cellule["ligne"]) == "rouge":
            cellule["commentaire"]["texte"] = "Renfort prévu."

    vue.soumettre()
    application.racine.update()

    assert application.erreurs == []
    assert vue.plan_donnees["plan"]["statut"] == "soumis"


def test_responsable_valide_le_plan(plan_pret, application):
    site_id, lundi = plan_pret
    connecter(application, "planif")
    application.naviguer("plan_charge")
    application.racine.update()
    vue = application.vues["plan_charge"]
    vue.site.definir(site_id)
    vue._sur_changement_site()
    vue.semaine = lundi
    vue.charger_semaine()
    vue.proposer()
    application.racine.update()
    for cellule in vue.cellules.values():
        if planification.statut_couleur_ligne(cellule["ligne"]) == "rouge":
            cellule["commentaire"]["texte"] = "Renfort prévu."
    vue.soumettre()
    application.racine.update()

    application.se_deconnecter()
    connecter(application, "resp")
    application.naviguer("plan_charge")
    application.racine.update()
    vue_resp = application.vues["plan_charge"]
    vue_resp.site.definir(site_id)
    vue_resp._sur_changement_site()
    vue_resp.semaine = lundi
    vue_resp.charger_semaine()
    application.racine.update()
    assert "Soumis" in vue_resp.label_statut.cget("text")

    vue_resp.valider()
    application.racine.update()

    assert application.erreurs == []
    assert vue_resp.plan_donnees["plan"]["statut"] == "valide"


def test_planificateur_ne_voit_pas_les_boutons_responsable(application):
    connecter(application, "planif")
    application.naviguer("plan_charge")
    application.racine.update()
    vue = application.vues["plan_charge"]
    textes = {b.cget("text") for b in vue.boutons_action}
    assert textes == {
        "Proposer le plan",
        "Simuler un scénario…",
        "Enregistrer le brouillon",
        "Soumettre pour validation",
    }
