"""Connexion Odoo : configuration par l'environnement et messages d'erreur lisibles."""

import pytest

from app.taches import odoo

VARIABLES = (
    "WORKLY_ODOO_URL",
    "WORKLY_ODOO_BASE",
    "WORKLY_ODOO_UTILISATEUR",
    "WORKLY_ODOO_CLE",
)


@pytest.fixture
def env_odoo(monkeypatch):
    monkeypatch.setenv("WORKLY_ODOO_URL", "https://exemple.odoo.com/")
    monkeypatch.setenv("WORKLY_ODOO_BASE", "exemple")
    monkeypatch.setenv("WORKLY_ODOO_UTILISATEUR", "a@b.c")
    monkeypatch.setenv("WORKLY_ODOO_CLE", "secret-cle")


def test_non_configure(monkeypatch):
    for nom in VARIABLES:
        monkeypatch.delenv(nom, raising=False)
    assert odoo.configuration() is None
    with pytest.raises(odoo.ErreurOdoo, match="non configuré"):
        odoo.tester_connexion()


def test_configuration_retire_la_barre_finale(env_odoo):
    assert odoo.configuration()["url"] == "https://exemple.odoo.com"


class _Faux:
    def __init__(self, uid=7):
        self.uid = uid

    def version(self):
        return {"server_version": "17.0"}

    def authenticate(self, *args):
        return self.uid

    def execute_kw(self, *args):
        return 12


def test_connexion_reussie(env_odoo, monkeypatch):
    monkeypatch.setattr(odoo, "_proxy", lambda url, service: _Faux())
    assert odoo.tester_connexion() == {
        "version": "17.0",
        "base": "exemple",
        "commandes_vente": 12,
    }


def test_identifiants_refuses_sans_fuite_de_la_cle(env_odoo, monkeypatch):
    monkeypatch.setattr(odoo, "_proxy", lambda url, service: _Faux(uid=False))
    with pytest.raises(odoo.ErreurOdoo, match="refusés") as erreur:
        odoo.tester_connexion()
    assert "secret-cle" not in str(erreur.value)


def test_odoo_injoignable(env_odoo, monkeypatch):
    class Injoignable:
        def version(self):
            raise OSError("connexion refusée")

    monkeypatch.setattr(odoo, "_proxy", lambda url, service: Injoignable())
    with pytest.raises(odoo.ErreurOdoo, match="injoignable"):
        odoo.tester_connexion()


def test_connexion_valide_sans_droit_sur_les_ventes(env_odoo, monkeypatch):
    import xmlrpc.client

    class SansVentes(_Faux):
        def execute_kw(self, *args):
            raise xmlrpc.client.Fault(4, "You are not allowed to access 'Sales Order'")

    monkeypatch.setattr(odoo, "_proxy", lambda url, service: SansVentes())
    resultat = odoo.tester_connexion()
    assert resultat["version"] == "17.0" and resultat["commandes_vente"] is None
