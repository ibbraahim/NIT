"""Lancement de l'application : ``python -m app``."""

from __future__ import annotations

import sys

from app.config import configuration
from app.erreurs import ErreurApplication
from app.journal import configurer_journal, journal


def principal() -> int:
    """Charge la configuration, vérifie la base puis ouvre la fenêtre de connexion."""
    configurer_journal()
    log = journal(__name__)
    import tkinter as tk

    try:
        config = configuration()
        configurer_journal(config.niveau_journal)
        from app.bd.connexion import tester_connexion

        tester_connexion()
    except ErreurApplication as exc:
        log.error("Démarrage impossible : %s", exc)
        racine = tk.Tk()
        racine.withdraw()
        from app.gui.style import appliquer_style
        from app.gui.widgets.dialogues import afficher_erreur

        appliquer_style(racine)
        afficher_erreur(racine, exc.message, "Démarrage impossible")
        racine.destroy()
        return 1

    from app.gui.fenetre_principale import Application

    log.info("Démarrage de l'application.")
    Application().lancer()
    from app.bd.connexion import fermer_pool

    fermer_pool()
    log.info("Fermeture de l'application.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
