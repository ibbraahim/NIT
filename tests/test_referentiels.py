"""UC03 · Gérer les référentiels (dépôts et services sur base de test)."""

from datetime import date, timedelta

import pytest

from app.bd.connexion import transaction
from app.erreurs import DonneesInvalides, OperationImpossible
from app.services import admin

pytestmark = pytest.mark.integration


def _site_zone(ctx):
    site_id = admin.enregistrer_site(ctx, "Site test", "Adresse")
    zone_id = admin.enregistrer_zone(ctx, site_id, "Réception", "chariot_elevateur", "7,5")
    return site_id, zone_id


def test_creation_site_zone(ctx_admin):
    site_id, zone_id = _site_zone(ctx_admin)
    zones = admin.lister_zones(ctx_admin, site_id)
    assert [(z["nom"], z["duree_poste_heures"]) for z in zones] == [("Réception", 7.5)]


def test_doublons_refuses_avec_champ_signale(ctx_admin):
    site_id, _ = _site_zone(ctx_admin)
    with pytest.raises(DonneesInvalides) as erreur:
        admin.enregistrer_site(ctx_admin, "site TEST")
    assert "nom" in erreur.value.erreurs
    with pytest.raises(DonneesInvalides) as erreur:
        admin.enregistrer_zone(ctx_admin, site_id, "réception", "chariot_elevateur", 7.5)
    assert erreur.value.erreurs == {"nom": "Une zone de ce site porte déjà ce nom."}


def test_validation_des_champs(ctx_admin):
    site_id, _ = _site_zone(ctx_admin)
    with pytest.raises(DonneesInvalides) as erreur:
        admin.enregistrer_zone(ctx_admin, site_id, "", "inconnu", "abc")
    assert set(erreur.value.erreurs) == {"nom", "type_equipement_principal", "duree_poste_heures"}


def test_desactivation_sans_suppression(ctx_admin):
    site_id, zone_id = _site_zone(ctx_admin)
    eqp = admin.enregistrer_equipement(ctx_admin, site_id, zone_id, "chariot_elevateur", "ce-01")
    admin.desactiver_equipement(ctx_admin, eqp)
    admin.desactiver_site(ctx_admin, site_id)
    with transaction() as cur:
        cur.execute("SELECT count(*) AS n FROM sites")
        assert cur.fetchone()["n"] == 1
        cur.execute("SELECT actif FROM zones WHERE id = %s", (zone_id,))
        assert cur.fetchone()["actif"] is False
        cur.execute("SELECT code, actif FROM equipements WHERE id = %s", (eqp,))
        assert dict(cur.fetchone()) == {"code": "CE-01", "actif": False}
    assert admin.lister_sites(ctx_admin) == []
    assert len(admin.lister_sites(ctx_admin, inclure_inactifs=True)) == 1


def test_equipement_zone_d_un_autre_site(ctx_admin):
    site_id, zone_id = _site_zone(ctx_admin)
    autre = admin.enregistrer_site(ctx_admin, "Autre site")
    with pytest.raises(DonneesInvalides, match="n'appartient pas au site"):
        admin.enregistrer_equipement(ctx_admin, autre, zone_id, "chariot_elevateur", "X")


def test_disponibilite_equipements(ctx_admin):
    site_id, zone_id = _site_zone(ctx_admin)
    ids = [
        admin.enregistrer_equipement(ctx_admin, site_id, zone_id, "chariot_elevateur", f"CE-{i}")
        for i in range(4)
    ]
    demain = date.today() + timedelta(days=1)
    admin.declarer_indisponibilite(
        ctx_admin, ids[0], demain, demain + timedelta(days=4), "Révision"
    )
    admin.enregistrer_equipement(
        ctx_admin, site_id, zone_id, "chariot_elevateur", "CE-1", "hors_service", ids[1]
    )
    admin.enregistrer_equipement(
        ctx_admin, site_id, zone_id, "chariot_elevateur", "CE-2", "maintenance", ids[2]
    )
    lignes = admin.disponibilite_equipements(
        ctx_admin, site_id, date.today(), demain + timedelta(days=5)
    )
    dispo = {l["date_jour"]: l["disponibles"] for l in lignes}
    assert dispo[date.today()] == 2  # hors service et maintenance exclus
    assert dispo[demain] == 1  # plus l'indisponibilité déclarée
    assert dispo[demain + timedelta(days=5)] == 2  # fin de l'indisponibilité
    assert all(l["total"] == 4 for l in lignes)


def test_indisponibilite_dates_incoherentes(ctx_admin):
    site_id, zone_id = _site_zone(ctx_admin)
    eqp = admin.enregistrer_equipement(ctx_admin, site_id, zone_id, "chariot_elevateur", "CE-01")
    with pytest.raises(DonneesInvalides) as erreur:
        admin.declarer_indisponibilite(ctx_admin, eqp, "10/03/2026", "01/03/2026", "Révision")
    assert "date_fin" in erreur.value.erreurs
    with pytest.raises(DonneesInvalides) as erreur:
        admin.declarer_indisponibilite(ctx_admin, eqp, "32/03/2026", "01/04/2026", "")
    assert {"date_debut", "motif"} <= set(erreur.value.erreurs)


def test_capacites_et_copie_semaine(ctx_admin):
    site_id, zone_id = _site_zone(ctx_admin)
    lundi = date(2026, 3, 9)
    admin.enregistrer_capacites(
        ctx_admin, site_id, {(zone_id, lundi + timedelta(days=i)): (10, i % 2) for i in range(7)}
    )
    assert admin.copier_semaine_precedente(ctx_admin, site_id, lundi + timedelta(days=10)) == 7
    copie = admin.lire_capacites(ctx_admin, site_id, lundi + timedelta(days=7))
    assert copie[(zone_id, lundi + timedelta(days=8))]["absences_prevues"] == 1
    assert copie[(zone_id, lundi + timedelta(days=7))]["effectif_planifie"] == 10
    with pytest.raises(OperationImpossible, match="aucune capacité"):
        admin.copier_semaine_precedente(ctx_admin, site_id, date(2030, 1, 7))


def test_capacites_invalides(ctx_admin):
    site_id, zone_id = _site_zone(ctx_admin)
    jour = date(2026, 3, 9)
    with pytest.raises(DonneesInvalides) as erreur:
        admin.enregistrer_capacites(ctx_admin, site_id, {(zone_id, jour): ("5", "8")})
    assert "dépassent" in erreur.value.erreurs[f"{zone_id}_2026-03-09"]
    with pytest.raises(DonneesInvalides):
        admin.enregistrer_capacites(ctx_admin, site_id, {(zone_id, jour): ("-1", "0")})


def test_couts_horaires(ctx_admin):
    admin.enregistrer_cout(ctx_admin, "interne", "45,5", "mad", "01/01/2026")
    admin.enregistrer_cout(ctx_admin, "interne", 47, "MAD", date(2026, 7, 1))
    couts = admin.lister_couts(ctx_admin)
    assert [(c["taux"], c["devise"]) for c in couts] == [(47.0, "MAD"), (45.5, "MAD")]
    with pytest.raises(DonneesInvalides) as erreur:
        admin.enregistrer_cout(ctx_admin, "prime", -1, "EURO", "x")
    assert set(erreur.value.erreurs) == {"categorie", "taux", "devise", "date_debut"}
