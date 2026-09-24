"""Classe de base des écrans."""

from __future__ import annotations

from tkinter import ttk

from app.gui.widgets.dialogues import executer_action


class Vue(ttk.Frame):
    """Écran affiché dans la zone de contenu de la fenêtre principale."""

    titre = ""
    sous_titre = ""

    def __init__(self, parent, application) -> None:
        super().__init__(parent, padding=(18, 14))
        self.application = application
        self.ctx = application.contexte
        entete = ttk.Frame(self)
        entete.pack(fill="x", pady=(0, 10))
        ttk.Label(entete, text=self.titre, style="Titre.TLabel").pack(side="left")
        if self.sous_titre:
            ttk.Label(entete, text=self.sous_titre, style="Aide.TLabel").pack(
                side="left", padx=(12, 0), pady=(6, 0)
            )
        self.entete = entete
        self.contenu = ttk.Frame(self)
        self.contenu.pack(fill="both", expand=True)
        self.construire()

    def construire(self) -> None:
        """Crée les widgets de l'écran (à redéfinir)."""

    def actualiser(self) -> None:
        """Recharge les données affichées (appelé à chaque affichage de l'écran)."""

    def afficher_parametres(self, **parametres) -> None:
        """Reçoit des paramètres de navigation (ex. alerte à sélectionner)."""

    def executer(self, action, succes: str | None = None):
        """Appelle un service et affiche l'erreur éventuelle en français."""
        return executer_action(self, action, succes)
