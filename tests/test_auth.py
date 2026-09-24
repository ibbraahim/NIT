"""UC01 · S'authentifier."""

from datetime import UTC, datetime, timedelta

import pytest

from app.bd.connexion import transaction
from app.bd.depots.utilisateurs import DepotUtilisateurs
from app.erreurs import ErreurAuthentification
from app.services import auth
from tests.conftest import MOT_DE_PASSE_ADMIN

pytestmark = pytest.mark.integration


def _utilisateur(identifiant="admin"):
    with transaction() as cur:
        return DepotUtilisateurs(cur).par_identifiant(identifiant)


def _journal():
    with transaction() as cur:
        cur.execute("SELECT succes, motif FROM journal_connexions ORDER BY id")
        return [(l["succes"], l["motif"]) for l in cur.fetchall()]


def test_hachage_pbkdf2():
    h1, sel1 = auth.hacher_mot_de_passe("Secret123")
    h2, sel2 = auth.hacher_mot_de_passe("Secret123")
    assert sel1 != sel2 and h1 != h2
    assert len(sel1) == 32 and len(h1) == 64
    assert auth.verifier_mot_de_passe("Secret123", h1, sel1)
    assert not auth.verifier_mot_de_passe("Secret124", h1, sel1)
    assert auth.ITERATIONS == 200_000


def test_connexion_reussie(bd_vierge):
    ctx = auth.authentifier("admin", MOT_DE_PASSE_ADMIN)
    assert ctx.role == "administrateur" and ctx.voit_tous_les_sites
    assert _journal() == [(True, "succes")]


def test_identifiant_insensible_a_la_casse(bd_vierge):
    assert auth.authentifier("  ADMIN ", MOT_DE_PASSE_ADMIN).identifiant == "admin"


def test_message_identique_quelle_que_soit_la_cause(bd_vierge):
    with pytest.raises(ErreurAuthentification) as inconnu:
        auth.authentifier("personne", "x")
    with pytest.raises(ErreurAuthentification) as mauvais_mdp:
        auth.authentifier("admin", "mauvais")
    assert str(inconnu.value) == str(mauvais_mdp.value) == auth.MESSAGE_ECHEC
    assert _journal() == [(False, "identifiant_inconnu"), (False, "mot_de_passe_incorrect")]


def test_cinq_echecs_verrouillent_quinze_minutes(bd_vierge):
    for _ in range(4):
        with pytest.raises(ErreurAuthentification):
            auth.authentifier("admin", "mauvais")
    assert _utilisateur()["verrouille_jusqu_a"] is None
    with pytest.raises(ErreurAuthentification):
        auth.authentifier("admin", "mauvais")
    verrou = _utilisateur()["verrouille_jusqu_a"]
    assert verrou is not None
    duree = verrou - datetime.now(UTC)
    assert timedelta(minutes=14) < duree <= timedelta(minutes=15)
    # Même le bon mot de passe est refusé pendant le verrouillage, avec le même message.
    with pytest.raises(ErreurAuthentification, match="identifiant ou mot de passe|Identifiant"):
        auth.authentifier("admin", MOT_DE_PASSE_ADMIN)
    assert _journal()[-1] == (False, "compte_verrouille")


def test_verrou_expire(bd_vierge):
    with transaction() as cur:
        cur.execute(
            "UPDATE utilisateurs SET tentatives_echouees = 5, verrouille_jusqu_a = now() - "
            "interval '1 minute' WHERE identifiant = 'admin'"
        )
    ctx = auth.authentifier("admin", MOT_DE_PASSE_ADMIN)
    assert ctx.identifiant == "admin"
    utilisateur = _utilisateur()
    assert utilisateur["tentatives_echouees"] == 0 and utilisateur["verrouille_jusqu_a"] is None


def test_succes_remet_le_compteur_a_zero(bd_vierge):
    for _ in range(3):
        with pytest.raises(ErreurAuthentification):
            auth.authentifier("admin", "mauvais")
    auth.authentifier("admin", MOT_DE_PASSE_ADMIN)
    assert _utilisateur()["tentatives_echouees"] == 0


def test_compte_inactif_refuse(bd_vierge):
    with transaction() as cur:
        cur.execute("UPDATE utilisateurs SET actif = FALSE WHERE identifiant = 'admin'")
    with pytest.raises(ErreurAuthentification) as erreur:
        auth.authentifier("admin", MOT_DE_PASSE_ADMIN)
    assert str(erreur.value) == auth.MESSAGE_ECHEC
    assert _journal()[-1] == (False, "compte_inactif")


def test_sites_rattaches(demo_referentiels):
    ctx = auth.authentifier("planif", "Planif2026!")
    assert ctx.role == "planificateur"
    assert ctx.sites == frozenset({demo_referentiels["site_id"]})
