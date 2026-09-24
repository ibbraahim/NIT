"""Journalisation dans journaux/application.log (messages en français)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import DOSSIER_JOURNAUX

NOM_JOURNAL = "planification"
_configure = False


def configurer_journal(niveau: str = "INFO") -> None:
    """Configure le journal fichier (idempotent)."""
    global _configure
    if _configure:
        return
    DOSSIER_JOURNAUX.mkdir(parents=True, exist_ok=True)
    gestionnaire = RotatingFileHandler(
        DOSSIER_JOURNAUX / "application.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    gestionnaire.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%d/%m/%Y %H:%M:%S"
        )
    )
    racine = logging.getLogger(NOM_JOURNAL)
    racine.setLevel(getattr(logging, niveau, logging.INFO))
    racine.addHandler(gestionnaire)
    racine.propagate = False
    for nom, libelle in (
        ("DEBUG", "DÉBOGAGE"),
        ("INFO", "INFO"),
        ("WARNING", "AVERTISSEMENT"),
        ("ERROR", "ERREUR"),
        ("CRITICAL", "CRITIQUE"),
    ):
        logging.addLevelName(getattr(logging, nom), libelle)
    _configure = True


def journal(module: str) -> logging.Logger:
    """Retourne le journal d'un module (ex. ``journal(__name__)``)."""
    return logging.getLogger(f"{NOM_JOURNAL}.{module}")
