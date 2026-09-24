"""Droits par rôle, vérifiés dans les services (et pas seulement dans l'interface)."""

from datetime import date

import pytest

from app.contexte import CONTEXTE_SYSTEME, Contexte
from app.erreurs import AccesRefuse
from app.services import admin
from app.services.droits import DROITS, a_le_droit, verifier_droit, verifier_site


def ctx(role: str, sites=(1,)) -> Contexte:
    return Contexte(utilisateur_id=99, identifiant=role, role=role, sites=frozenset(sites))


# Tableau du prompt : acteur → cas d'utilisation autorisés.
ATTENDU = {
    "planificateur": {"UC01", "UC04", "UC05", "UC11", "UC12", "UC13", "UC19", "UC22"},
    "responsable": {"UC01", "UC14", "UC15", "UC17", "UC19", "UC20", "UC22", "UC23", "UC24"},
    "direction": {"UC01", "UC22"},
    "administrateur": {"UC01", "UC02", "UC03", "UC07", "UC08", "UC10"},
    # Planificateur de tâches (UC08, UC11, UC17, UC20, UC23 + export du rapport, réception
    # de UC04) et système source WMS / SIRH (UC04, UC05).
    "systeme": {"UC04", "UC05", "UC08", "UC11", "UC17", "UC20", "UC23", "UC24"},
}
# Cas inclus ou en extension, exécutés avec les droits du cas qui les déclenche.
INCLUS = {"UC06", "UC09", "UC16", "UC18", "UC21"}


@pytest.mark.parametrize("role", list(ATTENDU))
def test_matrice_conforme_au_prompt(role):
    autorises = {uc for uc in DROITS if uc.startswith("UC") and a_le_droit(ctx(role), uc)}
    assert autorises - INCLUS == ATTENDU[role]


def test_direction_ne_voit_que_le_tableau_de_bord():
    for uc in DROITS:
        if uc.startswith("UC") and uc not in {"UC01", "UC22"}:
            assert not a_le_droit(ctx("direction"), uc), uc


def test_verifier_droit_message_francais():
    with pytest.raises(AccesRefuse, match="Votre rôle \\(Direction\\) ne permet pas"):
        verifier_droit(ctx("direction"), "UC12")


def test_verification_site():
    verifier_site(ctx("planificateur", sites=[1]), 1)
    with pytest.raises(AccesRefuse, match="rattaché"):
        verifier_site(ctx("planificateur", sites=[1]), 2)
    verifier_site(ctx("administrateur", sites=[]), 2)
    verifier_site(CONTEXTE_SYSTEME, 2)


@pytest.mark.parametrize("role", ["planificateur", "responsable", "direction"])
def test_services_uc03_refuses_hors_administrateur(role):
    c = ctx(role)
    appels = [
        lambda: admin.enregistrer_site(c, "Site X"),
        lambda: admin.desactiver_site(c, 1),
        lambda: admin.enregistrer_zone(c, 1, "Z", "chariot_elevateur", 7.5),
        lambda: admin.desactiver_zone(c, 1),
        lambda: admin.enregistrer_equipement(c, 1, 1, "chariot_elevateur", "X-1"),
        lambda: admin.desactiver_equipement(c, 1),
        lambda: admin.declarer_indisponibilite(c, 1, date.today(), date.today(), "test"),
        lambda: admin.enregistrer_capacites(c, 1, {}),
        lambda: admin.copier_semaine_precedente(c, 1, date.today()),
        lambda: admin.enregistrer_cout(c, "interne", 45, "MAD", date.today()),
    ]
    for appel in appels:
        with pytest.raises(AccesRefuse):
            appel()


def test_lecture_referentiels_limitee_aux_sites_rattaches():
    with pytest.raises(AccesRefuse):
        admin.lister_zones(ctx("planificateur", sites=[1]), site_id=2)
