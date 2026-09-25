"""UC11 · Générer les prévisions de ressources — UC12 · Élaborer le plan de charge —
UC13 · Simuler un scénario — UC14 · Valider le plan de charge."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.previsions import DepotPrevisionsVolume
from app.erreurs import AccesRefuse, DonneesInvalides, OperationImpossible
from app.services import admin, modeles, planification
from app.utils.dates import jours_semaine, lundi_de
from tests.test_modeles import _inserer_historique

pytestmark = pytest.mark.integration


@pytest.fixture
def site_zone_modeles(ctx_admin):
    site_id = admin.enregistrer_site(ctx_admin, "Plateforme Test")
    zone_id = admin.enregistrer_zone(ctx_admin, site_id, "Réception", "chariot_elevateur", 7.5)
    for i in range(4):
        admin.enregistrer_equipement(ctx_admin, site_id, zone_id, "chariot_elevateur", f"CE-{i}")
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    for version in resume.versions:
        modeles.activer_version(
            ctx_admin,
            version.version_id,
            retenir_pour_plan=version.methode == "regression_lineaire",
        )
    return site_id, zone_id


@pytest.fixture
def ctx_planificateur(site_zone_modeles):
    from app.bd.depots.utilisateurs import DepotUtilisateurs
    from app.services import auth

    site_id, _zone_id = site_zone_modeles
    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Planif2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("planif", "P", "P", "", h, s, "planificateur")
        depot.definir_sites(uid, [site_id])
    return auth.authentifier("planif", "Planif2026!")


@pytest.fixture
def ctx_responsable(site_zone_modeles):
    from app.bd.depots.utilisateurs import DepotUtilisateurs
    from app.services import auth

    site_id, _zone_id = site_zone_modeles
    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Resp2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("resp", "R", "R", "", h, s, "responsable")
        depot.definir_sites(uid, [site_id])
    return auth.authentifier("resp", "Resp2026!")


def _semer_previsions_volume(site_id, zone_id, dates, volume=1000.0):
    lignes = [
        {
            "site_id": site_id,
            "zone_id": zone_id,
            "date_jour": jour,
            "volume_prevu": volume,
            "indicateur_pic": False,
            "source": "test",
        }
        for jour in dates
    ]
    with transaction() as cur:
        DepotPrevisionsVolume(cur).upsert_plusieurs(lignes)


def _semer_capacites(site_id, zone_id, jours, effectif=10, absences=0):
    from app.bd.depots.referentiels import DepotReferentiels

    with transaction() as cur:
        depot = DepotReferentiels(cur)
        for jour in jours:
            depot.enregistrer_capacite(site_id, zone_id, jour, effectif, absences)


# ---------------------------------------------------------------------
# UC11 · Générer les prévisions de ressources
# ---------------------------------------------------------------------
def test_generer_previsions_cree_rl_et_rn(ctx_planificateur, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    demain = date.today() + timedelta(days=1)
    dates = [demain + timedelta(days=i) for i in range(7)]
    _semer_previsions_volume(site_id, zone_id, dates)

    resume = planification.generer_previsions(ctx_planificateur, site_id, zone_id, 7)
    assert resume.nb_lignes == 14  # 7 jours x 2 méthodes
    assert resume.avertissements == []

    lignes = planification.lister_previsions_ressources(ctx_planificateur, site_id, zone_id, 7)
    assert len(lignes) == 7
    for ligne in lignes:
        assert ligne["heures_rl"] > 0 and ligne["heures_rn"] > 0
        assert ligne["effectif_rl"] >= 1
        assert ligne["ic_bas_rl"] <= ligne["heures_rl"] <= ligne["ic_haut_rl"]
        assert ligne["modele_actif"] == "RL"  # méthode retenue par défaut dans le générateur


def test_generer_previsions_signale_volume_manquant(ctx_planificateur, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    demain = date.today() + timedelta(days=1)
    _semer_previsions_volume(site_id, zone_id, [demain + timedelta(days=i) for i in range(5)])

    resume = planification.generer_previsions(ctx_planificateur, site_id, zone_id, 7)
    assert resume.nb_lignes == 10  # 5 jours x 2 méthodes
    assert any("manquant" in a for a in resume.avertissements)


def test_generer_previsions_horizon_invalide(ctx_planificateur, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    with pytest.raises(ValueError, match="Horizon invalide"):
        planification.generer_previsions(ctx_planificateur, site_id, zone_id, 10)


def test_generer_previsions_sans_modele_actif(ctx_planificateur, ctx_admin, site_zone_modeles):
    site_id, _zone_id = site_zone_modeles
    # Une zone sans historique ni entraînement : aucun modèle actif pour aucune méthode.
    autre_zone = admin.enregistrer_zone(ctx_admin, site_id, "Stockage", "chariot_elevateur", 7.5)
    demain = date.today() + timedelta(days=1)
    _semer_previsions_volume(site_id, autre_zone, [demain + timedelta(days=i) for i in range(7)])

    resume = planification.generer_previsions(ctx_planificateur, site_id, autre_zone, 7)
    assert resume.nb_lignes == 0
    assert len(resume.avertissements) == 2  # une par méthode (RL, RN)
    assert all("aucun modèle actif" in a.lower() for a in resume.avertissements)


def test_refus_hors_site(ctx_planificateur):
    with pytest.raises(AccesRefuse):
        planification.generer_previsions(ctx_planificateur, 999999, None, 7)


def test_refus_hors_planificateur(ctx_responsable, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    with pytest.raises(AccesRefuse):
        planification.generer_previsions(ctx_responsable, site_id, zone_id, 7)


# ---------------------------------------------------------------------
# UC12 · Élaborer le plan de charge
# ---------------------------------------------------------------------
@pytest.fixture
def semaine_avec_previsions(ctx_planificateur, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    lundi = lundi_de(date.today() + timedelta(days=10))
    jours = jours_semaine(lundi)
    _semer_previsions_volume(site_id, zone_id, jours)
    _semer_capacites(site_id, zone_id, jours, effectif=10, absences=1)
    planification.generer_previsions(
        ctx_planificateur,
        site_id,
        zone_id,
        horizon_jours=next(h for h in planification.HORIZONS_VALIDES if h >= 10 + 7),
    )
    return site_id, zone_id, lundi


def test_proposer_plan_calcule_besoin_capacite(ctx_planificateur, semaine_avec_previsions):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    plan = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)
    assert plan["plan"]["statut"] == "brouillon"
    assert plan["plan"]["id"] == resultat["plan_id"]
    assert len(plan["lignes"]) == 7
    for ligne in plan["lignes"]:
        assert ligne["capacite_effectif"] == 9  # 10 planifiés - 1 absence
        assert ligne["effectif_planifie"] == min(ligne["besoin_effectif"], 9)
        assert ligne["interim_planifie"] == max(ligne["besoin_effectif"] - 9, 0)
        assert ligne["besoin_heures"] > 0


def test_proposer_plan_signale_capacite_et_prevision_absentes(ctx_planificateur, site_zone_modeles):
    site_id, zone_id = site_zone_modeles
    lundi = lundi_de(date.today() + timedelta(days=10))
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    assert any("prévision" in a.lower() for a in resultat["avertissements"])


def test_reproposer_plan_soumis_refuse(ctx_planificateur, semaine_avec_previsions):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    for ligne in planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"]:
        if planification._en_depassement(ligne):
            planification.enregistrer_brouillon_plan(
                ctx_planificateur,
                resultat["plan_id"],
                [
                    {
                        **ligne,
                        "commentaire": "Renfort prévu.",
                    }
                ],
            )
    planification.soumettre_plan(ctx_planificateur, resultat["plan_id"])
    with pytest.raises(OperationImpossible, match="déjà|soumis"):
        planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)


def test_lire_plan_inexistant_renvoie_none(ctx_planificateur, site_zone_modeles):
    site_id, _zone_id = site_zone_modeles
    assert planification.lire_plan_charge(ctx_planificateur, site_id, date.today()) is None


def test_enregistrer_brouillon_met_a_jour_les_cellules(ctx_planificateur, semaine_avec_previsions):
    site_id, zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    ligne = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"][0]
    planification.enregistrer_brouillon_plan(
        ctx_planificateur,
        resultat["plan_id"],
        [
            {
                "zone_id": ligne["zone_id"],
                "date_jour": ligne["date_jour"],
                "effectif_planifie": 12,
                "interim_planifie": 2,
                "equipements_planifies": 3,
                "commentaire": "Ajustement manuel.",
            }
        ],
    )
    lignes = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"]
    modifiee = next(
        l
        for l in lignes
        if l["zone_id"] == ligne["zone_id"] and l["date_jour"] == ligne["date_jour"]
    )
    assert modifiee["effectif_planifie"] == 12
    assert modifiee["commentaire"] == "Ajustement manuel."


def test_enregistrer_brouillon_valeurs_invalides(ctx_planificateur, semaine_avec_previsions):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    ligne = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"][0]
    with pytest.raises(DonneesInvalides):
        planification.enregistrer_brouillon_plan(
            ctx_planificateur,
            resultat["plan_id"],
            [
                {
                    "zone_id": ligne["zone_id"],
                    "date_jour": ligne["date_jour"],
                    "effectif_planifie": -1,
                    "interim_planifie": 0,
                    "equipements_planifies": 0,
                }
            ],
        )


def test_soumettre_plan_exige_commentaire_sur_depassement(
    ctx_planificateur, semaine_avec_previsions
):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    lignes = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"]
    if not any(planification._en_depassement(l) for l in lignes):
        pytest.skip("Aucune case en dépassement dans ce jeu de données.")
    with pytest.raises(DonneesInvalides, match="commentée"):
        planification.soumettre_plan(ctx_planificateur, resultat["plan_id"])


def test_soumettre_puis_valider_plan(ctx_planificateur, ctx_responsable, semaine_avec_previsions):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    for ligne in planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"]:
        if planification._en_depassement(ligne):
            planification.enregistrer_brouillon_plan(
                ctx_planificateur,
                resultat["plan_id"],
                [
                    {
                        **ligne,
                        "commentaire": "Renfort prévu.",
                    }
                ],
            )
    planification.soumettre_plan(ctx_planificateur, resultat["plan_id"])
    plan = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["plan"]
    assert plan["statut"] == "soumis"

    with pytest.raises(AccesRefuse):
        planification.valider_plan(ctx_planificateur, resultat["plan_id"])

    planification.valider_plan(ctx_responsable, resultat["plan_id"])
    plan = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["plan"]
    assert plan["statut"] == "valide" and plan["valide_par"] is not None


def test_rejeter_plan_exige_commentaire(
    ctx_planificateur, ctx_responsable, semaine_avec_previsions
):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    for ligne in planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"]:
        if planification._en_depassement(ligne):
            planification.enregistrer_brouillon_plan(
                ctx_planificateur,
                resultat["plan_id"],
                [
                    {
                        **ligne,
                        "commentaire": "Renfort prévu.",
                    }
                ],
            )
    planification.soumettre_plan(ctx_planificateur, resultat["plan_id"])
    with pytest.raises(DonneesInvalides):
        planification.rejeter_plan(ctx_responsable, resultat["plan_id"], "")
    planification.rejeter_plan(ctx_responsable, resultat["plan_id"], "Capacité insuffisante.")
    plan = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["plan"]
    assert plan["statut"] == "rejete" and plan["commentaire"] == "Capacité insuffisante."
    # Un plan rejeté peut être repris.
    planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    plan = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["plan"]
    assert plan["statut"] == "brouillon"


# ---------------------------------------------------------------------
# UC13 · Simuler un scénario
# ---------------------------------------------------------------------
def test_simuler_scenario_hausse_volume_augmente_le_besoin(
    ctx_planificateur, semaine_avec_previsions
):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    plan_id = resultat["plan_id"]
    simulation = planification.simuler_scenario(
        ctx_planificateur,
        plan_id,
        {
            "variation_volume_pct": 50,
            "taux_absence_pct": 0,
            "equipements_indisponibles": {},
        },
    )
    avant = {l["date_jour"]: l["besoin_heures"] for l in simulation["avant"]}
    for ligne in simulation["apres"]:
        assert ligne["besoin_heures"] == pytest.approx(avant[ligne["date_jour"]] * 1.5)

    scenarios = planification.lister_scenarios(ctx_planificateur, plan_id)
    assert len(scenarios) == 1 and scenarios[0]["applique"] is False


def test_appliquer_scenario_modifie_le_plan(ctx_planificateur, semaine_avec_previsions):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    besoin_avant = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)["lignes"][0][
        "besoin_heures"
    ]
    planification.simuler_scenario(
        ctx_planificateur,
        resultat["plan_id"],
        {
            "variation_volume_pct": 40,
            "taux_absence_pct": 10,
            "equipements_indisponibles": {},
        },
    )
    planification.appliquer_scenario(
        ctx_planificateur,
        planification.lister_scenarios(ctx_planificateur, resultat["plan_id"])[0]["id"],
    )

    plan_apres = planification.lire_plan_charge(ctx_planificateur, site_id, lundi)
    besoin_apres = plan_apres["lignes"][0]["besoin_heures"]
    assert besoin_apres == pytest.approx(besoin_avant * 1.4)
    scenarios = planification.lister_scenarios(ctx_planificateur, resultat["plan_id"])
    assert scenarios[0]["applique"] is True


def test_simuler_hypotheses_invalides(ctx_planificateur, semaine_avec_previsions):
    site_id, _zone_id, lundi = semaine_avec_previsions
    resultat = planification.proposer_plan_charge(ctx_planificateur, site_id, lundi)
    with pytest.raises(DonneesInvalides):
        planification.simuler_scenario(
            ctx_planificateur,
            resultat["plan_id"],
            {
                "variation_volume_pct": -1000,
                "taux_absence_pct": 0,
                "equipements_indisponibles": {},
            },
        )
