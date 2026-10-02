"""Alertes par e-mail des tâches automatiques (SMTP simulé : aucun message réel n'est envoyé)."""

from __future__ import annotations

import smtplib

import pytest

from app.taches import notifications

pytestmark = pytest.mark.integration

VARIABLES = (
    "WORKLY_SMTP_UTILISATEUR",
    "WORKLY_SMTP_MOT_DE_PASSE",
    "WORKLY_ALERTE_DESTINATAIRE",
    "WORKLY_SMTP_HOTE",
    "WORKLY_SMTP_PORT",
)


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch):
    for nom in VARIABLES:
        monkeypatch.delenv(nom, raising=False)


class FauxSmtp:
    envois: list = []
    appels: list = []

    def __init__(self, hote, port, timeout=None, context=None):
        FauxSmtp.appels.append(("connexion", hote, port))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, context=None):
        FauxSmtp.appels.append(("starttls",))

    def login(self, utilisateur, mot_de_passe):
        FauxSmtp.appels.append(("login", utilisateur))

    def send_message(self, message):
        FauxSmtp.envois.append(message)


@pytest.fixture
def faux_smtp(monkeypatch):
    FauxSmtp.envois, FauxSmtp.appels = [], []
    monkeypatch.setattr(smtplib, "SMTP", FauxSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FauxSmtp)
    return FauxSmtp


def configurer(monkeypatch, destinataire=None):
    monkeypatch.setenv("WORKLY_SMTP_UTILISATEUR", "alertes@exemple.test")
    monkeypatch.setenv("WORKLY_SMTP_MOT_DE_PASSE", "secret-de-test")
    if destinataire:
        monkeypatch.setenv("WORKLY_ALERTE_DESTINATAIRE", destinataire)


def test_sans_configuration_rien_n_est_envoye(faux_smtp):
    assert notifications.configuration() is None
    assert notifications.envoyer("sujet", "corps") is False
    assert faux_smtp.appels == []


def test_envoi_avec_starttls_et_connexion(monkeypatch, faux_smtp):
    configurer(monkeypatch, "equipe@exemple.test")
    assert notifications.envoyer("Sujet", "Corps") is True
    assert faux_smtp.appels == [
        ("connexion", "smtp.gmail.com", 587),
        ("starttls",),
        ("login", "alertes@exemple.test"),
    ]
    message = faux_smtp.envois[0]
    assert message["To"] == "equipe@exemple.test"
    assert message["From"] == "alertes@exemple.test"
    assert message["Subject"] == "Sujet"


def test_port_465_utilise_ssl_direct_sans_starttls(monkeypatch, faux_smtp):
    configurer(monkeypatch)
    monkeypatch.setenv("WORKLY_SMTP_PORT", "465")
    assert notifications.envoyer("Sujet", "Corps") is True
    assert faux_smtp.appels == [
        ("connexion", "smtp.gmail.com", 465),
        ("login", "alertes@exemple.test"),
    ]


def test_destinataire_par_defaut_est_le_compte_d_envoi(monkeypatch, faux_smtp):
    configurer(monkeypatch)
    notifications.envoyer("Sujet", "Corps")
    assert faux_smtp.envois[0]["To"] == "alertes@exemple.test"


def test_une_panne_de_messagerie_ne_leve_pas_d_exception(monkeypatch):
    configurer(monkeypatch)

    def casse(*_a, **_k):
        raise smtplib.SMTPAuthenticationError(535, b"refuse")

    monkeypatch.setattr(smtplib, "SMTP", casse)
    assert notifications.envoyer("Sujet", "Corps") is False


def test_le_message_d_echec_ne_contient_pas_le_mot_de_passe(monkeypatch, faux_smtp):
    configurer(monkeypatch)
    notifications.notifier_echec("kpi_quotidiens", "erreur technique")
    message = faux_smtp.envois[0]
    assert "kpi_quotidiens" in message["Subject"]
    assert "secret-de-test" not in message.as_string()


def test_une_tache_en_echec_declenche_l_alerte(bd_vierge, monkeypatch, faux_smtp):
    from app.taches import planificateur

    configurer(monkeypatch)

    def casse():
        raise RuntimeError("panne")

    monkeypatch.setitem(planificateur.TACHES, "kpi_quotidiens", casse)
    with pytest.raises(RuntimeError):
        planificateur.executer_tache("kpi_quotidiens")
    assert len(faux_smtp.envois) == 1
    assert "kpi_quotidiens" in faux_smtp.envois[0]["Subject"]


def test_une_tache_reussie_n_envoie_rien(bd_vierge, monkeypatch, faux_smtp):
    from app.taches import planificateur

    configurer(monkeypatch)
    planificateur.executer_tache("kpi_quotidiens")
    assert faux_smtp.envois == []
