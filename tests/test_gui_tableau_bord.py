"""Test de fumée de l'écran Tableau de bord (UC22) : contenu propre à chaque rôle."""

from __future__ import annotations

from datetime import UTC, date, timedelta

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


# ---------------------------------------------------------------------
# Bottom line (bloc du responsable et de la direction)
# ---------------------------------------------------------------------
def _resultat_bottom_line_factice() -> dict:
    """Résultat complet (jours comparables, alertes, tâches) sans passer par la base."""
    from datetime import datetime

    from app.services import bottom_line

    parametres = {p.cle: p.defaut for p in bottom_line.PARAMETRES}
    taux = {"interne": 10.0, "heures_sup": 15.0}
    jours = [
        {
            "besoin": 100.0,
            "plan_workly": 105.0,
            "plan_reconduit": 80.0,
            "duree_poste": 7.5,
            "commandes_totales": 200,
            "commandes_a_temps": 190,
        }
    ] * 5
    creation = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    alerte = {
        "type": "penurie_equipement",
        "niveau": "rouge",
        "statut": "resolue",
        "zone_id": 1,
        "date_concernee": date(2026, 9, 3),
        "date_creation": creation,
        "date_prise_en_charge": creation + timedelta(hours=2),
        "date_resolution": creation + timedelta(hours=5),
    }
    alertes = bottom_line.analyser_alertes([alerte], parametres)
    taches = bottom_line.analyser_taches(
        [{"tache": "kpi_quotidiens", "statut": "succes", "duree_s": 30.0}], taux, parametres
    )
    return {
        "debut": date(2026, 9, 1),
        "fin": date(2026, 9, 30),
        "devise": "MAD",
        "nb_jours_historique": 30,
        "simulation": bottom_line.simuler(jours, taux, parametres),
        "alertes": alertes,
        "automatisation": taches,
        "roi": bottom_line.calculer_roi(5000.0, 30, 20000.0),
        "parametres": parametres,
        "limites": ["Limite de test."],
    }


@pytest.mark.parametrize("identifiant", ["resp", "direction"])
def test_bottom_line_visible_pour_responsable_et_direction(application, identifiant):
    connecter(application, identifiant)
    site_id = admin.lister_sites(application.contexte)[0]["id"]
    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert application.erreurs == []
    # Base sans prévision ni historique : le bloc s'affiche quand même, sans jour comparable.
    assert vue.dernier_bottom_line["simulation"]["nb_jours"] == 0
    assert vue.dernier_bottom_line["limites"]


def test_bottom_line_absent_pour_le_planificateur(application):
    connecter(application, "planif")
    site_id = admin.lister_sites(application.contexte)[0]["id"]
    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert application.erreurs == []
    assert not hasattr(vue, "dernier_bottom_line")


def test_bottom_line_affiche_les_chiffres(application, monkeypatch):
    from app.services import bottom_line

    resultat = _resultat_bottom_line_factice()
    monkeypatch.setattr(bottom_line, "calculer_bottom_line", lambda *_a, **_k: resultat)
    connecter(application, "direction")
    site_id = admin.lister_sites(application.contexte)[0]["id"]
    application.naviguer("tableau_bord")
    application.racine.update()
    vue = application.vues["tableau_bord"]
    vue.site.definir(site_id)
    vue.actualiser_donnees()
    application.racine.update()

    assert application.erreurs == []
    textes = _textes_widgets(vue.cadre_contenu)
    assert any("Gain net estimé" in t for t in textes)
    assert any("Limites et hypothèses" in t for t in textes)
    assert any("Limite de test." in t for t in textes)
    assert any("Retour sur investissement" in t for t in textes)


def _textes_widgets(racine) -> list[str]:
    textes = []
    pile = [racine]
    while pile:
        widget = pile.pop()
        pile.extend(widget.winfo_children())
        try:
            textes.append(str(widget.cget("text")))
        except Exception:  # noqa: BLE001, S110 - widget sans option « text »
            pass
        titre = getattr(widget, "_titre", None)
        if titre:
            textes.append(titre)
    return textes
