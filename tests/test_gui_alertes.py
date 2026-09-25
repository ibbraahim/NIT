"""Test de fumée de l'écran Alertes (UC18, UC19)."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.plans import DepotPlansCharge
from app.services import admin
from app.utils.dates import lundi_de
from tests.conftest import connecter
from tests.test_alertes import CHAMPS_LIGNE_DEFAUT

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def _preparer_sous_effectif(application) -> tuple[int, int]:
    ctx = application.contexte
    site_id = admin.lister_sites(ctx)[0]["id"]
    zone_id = admin.lister_zones(ctx, site_id)[0]["id"]
    demain = date.today() + timedelta(days=1)
    with transaction() as cur:
        depot = DepotPlansCharge(cur)
        plan_id = depot.creer_plan(site_id, lundi_de(demain), "regression_lineaire", None)
        depot.inserer_lignes(
            plan_id,
            [
                {
                    **CHAMPS_LIGNE_DEFAUT,
                    "zone_id": zone_id,
                    "date_jour": demain,
                    "besoin_effectif": 10,
                    "effectif_planifie": 5,
                }
            ],
        )
        depot.mettre_a_jour_plan(plan_id, statut="valide")
    return site_id, zone_id


def test_detecter_puis_prendre_en_charge_et_resoudre(application):
    connecter(application, "admin")
    site_id, _zone_id = _preparer_sous_effectif(application)
    application.se_deconnecter()
    connecter(application, "resp")
    application.naviguer("alertes")
    application.racine.update()
    vue = application.vues["alertes"]

    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()
    assert not vue.tableau.lignes()

    vue.detecter()
    for _ in range(200):
        application.racine.update()
        if vue.tableau.lignes() or application.erreurs:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    lignes = vue.tableau.lignes()
    assert len(lignes) == 1
    alerte = lignes[0]
    assert alerte["type"] == "sous_effectif"
    assert alerte["niveau"] == "rouge"
    assert alerte["statut"] == "ouverte"

    vue.tableau.selectionner(alerte["id"])
    application.racine.update()
    vue._sur_selection()
    assert vue.b_prendre_en_charge.est_actif
    assert vue.b_resoudre.est_actif

    vue.prendre_en_charge()
    application.racine.update()
    assert application.erreurs == []
    en_cours = next(l for l in vue.tableau.lignes() if l["id"] == alerte["id"])
    assert en_cours["statut"] == "en_cours"

    from app.gui.vues.alertes import FenetreResolution

    vue.tableau.selectionner(alerte["id"])
    application.racine.update()
    dialogue = FenetreResolution(vue, application.contexte, alerte["id"])
    application.racine.update()
    dialogue.action.definir("Intérim supplémentaire réservé pour la journée.")
    dialogue._enregistrer()
    application.racine.update()
    assert dialogue.resultat is True
    dialogue.destroy()

    vue.actualiser_donnees()
    application.racine.update()
    resolue = next(l for l in vue.tableau.lignes() if l["id"] == alerte["id"])
    assert resolue["statut"] == "resolue"


def test_afficher_parametres_selectionne_l_alerte(application):
    connecter(application, "admin")
    site_id, _zone_id = _preparer_sous_effectif(application)
    application.se_deconnecter()
    connecter(application, "resp")

    from app.services import alertes as service_alertes

    resultat = service_alertes.emettre_alertes(application.contexte, site_id)
    alerte_id = resultat[0]["alerte_id"]

    # Un seul site existe dans la démo : il est sélectionné automatiquement, et
    # afficher_parametres() sélectionne l'alerte dès l'actualisation qui suit la navigation
    # (double-clic depuis le tableau de bord, à venir au lot 7).
    application.naviguer("alertes", alerte_id=alerte_id)
    application.racine.update()
    vue = application.vues["alertes"]
    assert vue.site.valeur() == site_id
    assert vue.tableau.ligne_selectionnee()["id"] == alerte_id
