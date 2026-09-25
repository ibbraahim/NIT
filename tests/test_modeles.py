"""UC07 · Paramétrer — UC08 · Entraîner (inclut UC09) — UC10 · Changer le modèle actif."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.erreurs import AccesRefuse, DonneesInvalides, OperationImpossible
from app.services import modeles

pytestmark = pytest.mark.integration

NB_JOURS_DEMO = 100


@pytest.fixture
def site_zone(ctx_admin):
    from app.services import admin

    site_id = admin.enregistrer_site(ctx_admin, "Plateforme Test")
    zone_id = admin.enregistrer_zone(ctx_admin, site_id, "Réception", "chariot_elevateur", 7.5)
    return site_id, zone_id


def _inserer_historique(site_id: int, zone_id: int, nb_jours: int = NB_JOURS_DEMO) -> None:
    """Historique déterministe : heures ≈ 0,05 × volume + 10, apprenable par la RL."""
    debut = date(2026, 1, 5)  # lundi
    lignes = []
    for i in range(nb_jours):
        jour = debut + timedelta(days=i)
        pic = jour.weekday() == 3  # jeudi
        volume = 1000 + 30 * (i % 14) + (300 if pic else 0)
        heures = 0.05 * volume + 10
        lignes.append(
            {
                "site_id": site_id,
                "zone_id": zone_id,
                "date_jour": jour,
                "volume_traite": volume,
                "effectif_present": 10,
                "heures_travaillees": heures,
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
                "indicateur_pic": pic,
                "source": "demonstration",
            }
        )
    with transaction() as cur:
        DepotHistorique(cur).upsert_plusieurs(lignes)


# ---------------------------------------------------------------------
# UC07 · Paramètres
# ---------------------------------------------------------------------
def test_parametres_par_defaut_sans_enregistrement(ctx_admin):
    assert modeles.recuperer_parametres(ctx_admin) == modeles.DEFAUT_PARAMETRES


def test_parametrer_modeles_puis_relire(ctx_admin):
    config = {**modeles.DEFAUT_PARAMETRES, "part_test": 0.3, "seuil_derive_mape": 12}
    enregistree = modeles.parametrer_modeles(ctx_admin, config)
    assert enregistree["part_test"] == 0.3
    assert modeles.recuperer_parametres(ctx_admin)["part_test"] == 0.3


def test_retablir_defaut_apres_modification(ctx_admin):
    modeles.parametrer_modeles(ctx_admin, {**modeles.DEFAUT_PARAMETRES, "part_test": 0.4})
    retabli = modeles.retablir_defaut(ctx_admin)
    assert retabli == modeles.DEFAUT_PARAMETRES
    assert modeles.recuperer_parametres(ctx_admin) == modeles.DEFAUT_PARAMETRES


def test_parametrage_refuse_hors_administrateur(bd_vierge):
    from app.services.auth import authentifier

    with transaction() as cur:
        from app.bd.depots.utilisateurs import DepotUtilisateurs
        from app.services.auth import hacher_mot_de_passe

        h, s = hacher_mot_de_passe("Resp2026!")
        DepotUtilisateurs(cur).creer("resp", "R", "R", "", h, s, "responsable")
    ctx = authentifier("resp", "Resp2026!")
    with pytest.raises(AccesRefuse):
        modeles.parametrer_modeles(ctx, modeles.DEFAUT_PARAMETRES)


@pytest.mark.parametrize(
    "champ,valeur",
    [
        ("variables_actives", ["jour_semaine"]),  # sans "volume"
        ("part_test", 0.9),
        ("niveau_confiance", 1.5),
        ("seuil_derive_mape", -1),
        ("jour_reentrainement", "lunedi"),
        ("heure_reentrainement", "25:00"),
    ],
)
def test_parametres_invalides(ctx_admin, champ, valeur):
    config = {**modeles.DEFAUT_PARAMETRES, champ: valeur}
    with pytest.raises(DonneesInvalides) as erreur:
        modeles.parametrer_modeles(ctx_admin, config)
    assert champ in erreur.value.erreurs


def test_hyperparametres_rn_invalides(ctx_admin):
    config = {
        **modeles.DEFAUT_PARAMETRES,
        "hyperparametres_rn": {"hidden_layer_sizes": [], "activation": "relu", "max_iter": 100},
    }
    with pytest.raises(DonneesInvalides) as erreur:
        modeles.parametrer_modeles(ctx_admin, config)
    assert "hyperparametres_rn" in erreur.value.erreurs


# ---------------------------------------------------------------------
# UC08 · Entraînement (et UC09, l'évaluation)
# ---------------------------------------------------------------------
def test_entrainement_historique_insuffisant(ctx_admin, site_zone):
    site_id, zone_id = site_zone
    _inserer_historique(site_id, zone_id, nb_jours=30)
    resume = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    assert resume.versions == []
    assert len(resume.avertissements) == 1
    assert "insuffisant" in resume.avertissements[0]


def test_entrainement_cree_quatre_versions_par_zone(ctx_admin, site_zone):
    site_id, zone_id = site_zone
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    combinaisons = {(v.methode, v.cible) for v in resume.versions}
    assert combinaisons == {
        ("regression_lineaire", "heures"),
        ("regression_lineaire", "equipements"),
        ("reseau_neurones", "heures"),
        ("reseau_neurones", "equipements"),
    }
    for version in resume.versions:
        assert "mae" in version.metriques and "couverture_ic" in version.metriques

    versions_bd = modeles.lister_versions(ctx_admin, site_id, zone_id)
    assert len(versions_bd) == 4
    assert all(not v["actif"] for v in versions_bd)  # jamais activé automatiquement
    rl_heures = next(
        v for v in versions_bd if v["methode"] == "regression_lineaire" and v["cible"] == "heures"
    )
    assert rl_heures["metriques"]["mae"] < 1.0  # relation quasi linéaire, bien apprise
    assert rl_heures["coefficients"] is not None
    # La moyenne mobile des 7 jours précédents prive les 7 premiers jours de variable :
    # seuls (NB_JOURS_DEMO - 7) jours sont utilisables, découpés en 80 % / 20 %.
    lignes_utilisables = NB_JOURS_DEMO - 7
    n_test_attendu = round(lignes_utilisables * 0.2)
    assert rl_heures["nb_lignes_test"] == n_test_attendu
    assert rl_heures["nb_lignes_apprentissage"] == lignes_utilisables - n_test_attendu


def test_entrainement_toutes_les_zones(ctx_admin, site_zone):
    from app.services import admin

    site_id, zone_id_1 = site_zone
    zone_id_2 = admin.enregistrer_zone(ctx_admin, site_id, "Stockage", "chariot_elevateur", 7.5)
    _inserer_historique(site_id, zone_id_1)
    _inserer_historique(site_id, zone_id_2)
    resume = modeles.entrainer_modeles(ctx_admin, site_id)  # zone_id=None : toutes les zones
    assert {v.zone_id for v in resume.versions} == {zone_id_1, zone_id_2}
    assert len(resume.versions) == 8


def test_entrainement_refuse_hors_administrateur(ctx_admin, site_zone, demo_referentiels):
    from app.services.auth import authentifier

    site_id, zone_id = site_zone
    ctx_planif = authentifier("planif", "Planif2026!")
    with pytest.raises(AccesRefuse):
        modeles.entrainer_modeles(ctx_planif, site_id, zone_id)


def test_entrainement_suit_la_progression(ctx_admin, site_zone):
    from app.utils.progression import Progression

    site_id, zone_id = site_zone
    _inserer_historique(site_id, zone_id)
    suivi = []
    progression = Progression(lambda fraction, texte: suivi.append((fraction, texte)))
    modeles.entrainer_modeles(ctx_admin, site_id, zone_id, progression)
    assert suivi[-1][0] == 1.0
    assert any("Réception" in texte for _f, texte in suivi)


# ---------------------------------------------------------------------
# UC10 · Changer le modèle actif
# ---------------------------------------------------------------------
def test_activer_version_et_retenue_pour_le_plan(ctx_admin, site_zone):
    site_id, zone_id = site_zone
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    version_rl_heures = next(
        v for v in resume.versions if v.methode == "regression_lineaire" and v.cible == "heures"
    )
    version_rl_equipements = next(
        v
        for v in resume.versions
        if v.methode == "regression_lineaire" and v.cible == "equipements"
    )

    comparaison = modeles.comparer_avant_activation(ctx_admin, version_rl_heures.version_id)
    assert comparaison["actif_actuel"] is None
    assert comparaison["candidate"]["id"] == version_rl_heures.version_id

    modeles.activer_version(ctx_admin, version_rl_heures.version_id)
    versions = modeles.lister_versions(ctx_admin, site_id, zone_id)
    actives = {(v["methode"], v["cible"]) for v in versions if v["actif"]}
    assert actives == {("regression_lineaire", "heures")}
    retenues = {(v["methode"], v["cible"]) for v in versions if v["retenue_pour_plan"]}
    assert retenues == {("regression_lineaire", "heures")}

    # Activer aussi la version équipements de la même méthode : les deux méthodes restent
    # actives indépendamment (RL et RN pourront coexister pour UC11), une seule est retenue.
    modeles.activer_version(ctx_admin, version_rl_equipements.version_id)
    versions = modeles.lister_versions(ctx_admin, site_id, zone_id)
    actives = {(v["methode"], v["cible"]) for v in versions if v["actif"]}
    assert actives == {("regression_lineaire", "heures"), ("regression_lineaire", "equipements")}


def test_activer_version_bascule_la_methode_retenue(ctx_admin, site_zone):
    site_id, zone_id = site_zone
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    rl_heures = next(
        v for v in resume.versions if v.methode == "regression_lineaire" and v.cible == "heures"
    )
    rn_heures = next(
        v for v in resume.versions if v.methode == "reseau_neurones" and v.cible == "heures"
    )

    modeles.activer_version(ctx_admin, rl_heures.version_id)
    modeles.activer_version(ctx_admin, rn_heures.version_id)

    versions = modeles.lister_versions(ctx_admin, site_id, zone_id)
    retenues = [v for v in versions if v["retenue_pour_plan"]]
    assert len(retenues) == 1 and retenues[0]["methode"] == "reseau_neurones"
    # La version RL reste active pour sa propre méthode (UC11 en a besoin) mais n'est plus retenue.
    rl_apres = next(v for v in versions if v["id"] == rl_heures.version_id)
    assert rl_apres["actif"] is True and rl_apres["retenue_pour_plan"] is False


def test_activer_deuxieme_version_desactive_la_premiere(ctx_admin, site_zone):
    site_id, zone_id = site_zone
    _inserer_historique(site_id, zone_id)
    premiere = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    rl_heures_1 = next(
        v for v in premiere.versions if v.methode == "regression_lineaire" and v.cible == "heures"
    )
    modeles.activer_version(ctx_admin, rl_heures_1.version_id)

    seconde = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    rl_heures_2 = next(
        v for v in seconde.versions if v.methode == "regression_lineaire" and v.cible == "heures"
    )
    modeles.activer_version(ctx_admin, rl_heures_2.version_id)

    versions = modeles.lister_versions(ctx_admin, site_id, zone_id)
    version_1 = next(v for v in versions if v["id"] == rl_heures_1.version_id)
    version_2 = next(v for v in versions if v["id"] == rl_heures_2.version_id)
    assert version_1["actif"] is False and version_2["actif"] is True


def test_activer_version_introuvable(ctx_admin):
    with pytest.raises(OperationImpossible, match="introuvable"):
        modeles.activer_version(ctx_admin, 999999)


def test_charger_pipeline_apres_entrainement(ctx_admin, site_zone):
    site_id, zone_id = site_zone
    _inserer_historique(site_id, zone_id)
    resume = modeles.entrainer_modeles(ctx_admin, site_id, zone_id)
    versions = modeles.lister_versions(ctx_admin, site_id, zone_id)
    version = next(v for v in versions if v["id"] == resume.versions[0].version_id)
    pipeline = modeles.charger_pipeline(version["chemin_fichier"])
    assert hasattr(pipeline, "predict")
