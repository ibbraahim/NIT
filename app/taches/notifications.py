"""Alerte par e-mail lorsqu'une tâche automatique échoue.

Le courrier part du poste ou du serveur qui exécute Workly, par un serveur SMTP (par exemple
Gmail avec un « mot de passe d'application »). Tout se règle par variables d'environnement ;
sans elles, la notification est simplement désactivée et rien d'autre ne change.

    WORKLY_SMTP_UTILISATEUR   compte d'envoi (obligatoire)
    WORKLY_SMTP_MOT_DE_PASSE  mot de passe d'application (obligatoire)
    WORKLY_ALERTE_DESTINATAIRE  adresse qui reçoit les alertes (défaut : le compte d'envoi)
    WORKLY_SMTP_HOTE          défaut smtp.gmail.com
    WORKLY_SMTP_PORT          défaut 587 (STARTTLS)
"""

from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from app.journal import journal

_log = journal(__name__)

DELAI_SMTP_S = 20


def configuration() -> dict | None:
    """Réglages SMTP lus dans l'environnement, ou ``None`` si la notification est désactivée."""
    utilisateur = os.environ.get("WORKLY_SMTP_UTILISATEUR", "").strip()
    mot_de_passe = os.environ.get("WORKLY_SMTP_MOT_DE_PASSE", "")
    if not utilisateur or not mot_de_passe:
        return None
    return {
        "hote": os.environ.get("WORKLY_SMTP_HOTE", "smtp.gmail.com").strip(),
        "port": int(os.environ.get("WORKLY_SMTP_PORT", "587")),
        "utilisateur": utilisateur,
        "mot_de_passe": mot_de_passe,
        "destinataire": os.environ.get("WORKLY_ALERTE_DESTINATAIRE", "").strip() or utilisateur,
    }


def envoyer(sujet: str, corps: str) -> bool:
    """Envoie un e-mail d'alerte ; renvoie ``True`` s'il est parti. Ne lève jamais d'exception :
    une panne de messagerie ne doit pas aggraver l'échec de la tâche."""
    reglages = configuration()
    if reglages is None:
        _log.info("Notification par e-mail non configurée : « %s » non envoyé.", sujet)
        return False
    message = EmailMessage()
    message["Subject"] = sujet
    message["From"] = reglages["utilisateur"]
    message["To"] = reglages["destinataire"]
    message.set_content(corps)
    try:
        with smtplib.SMTP(reglages["hote"], reglages["port"], timeout=DELAI_SMTP_S) as smtp:
            smtp.starttls()
            smtp.login(reglages["utilisateur"], reglages["mot_de_passe"])
            smtp.send_message(message)
    except (TimeoutError, smtplib.SMTPException, OSError) as exc:
        _log.warning("Envoi de l'alerte « %s » impossible : %s", sujet, exc)
        return False
    _log.info("Alerte « %s » envoyée à %s.", sujet, reglages["destinataire"])
    return True


def notifier_echec(tache: str, erreur: str = "") -> bool:
    """Alerte « la tâche ``tache`` a échoué » (sans détail technique sensible)."""
    quand = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    corps = (
        f"La tâche automatique « {tache} » de Workly a échoué le {quand}.\n\n"
        "Pour comprendre la cause : Workly > Administration > Tâches > Voir le journal, "
        "ou le fichier journaux/application.log.\n"
        "Vérifiez aussi que PostgreSQL est démarré."
    )
    if erreur:
        corps += f"\n\nMessage : {erreur}"
    return envoyer(f"Workly : échec de la tâche {tache}", corps)
