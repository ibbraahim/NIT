"""Classe de base des écrans."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.gui.style import COULEURS
from app.gui.widgets.dialogues import executer_action


class Vue(ttk.Frame):
    """Écran affiché dans la zone de contenu de la fenêtre principale.

    Le contenu (``self.contenu``) défile verticalement sans limite : les écrans dont les
    éléments dépassent la hauteur visible restent entièrement accessibles à la molette ou
    à l'ascenseur, plutôt que d'être comprimés ou coupés.
    """

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

        cadre_defilant = ttk.Frame(self)
        cadre_defilant.pack(fill="both", expand=True)
        canevas = tk.Canvas(cadre_defilant, highlightthickness=0, background=COULEURS["fond"])
        ascenseur = ttk.Scrollbar(cadre_defilant, orient="vertical", command=canevas.yview)
        canevas.configure(yscrollcommand=ascenseur.set)
        ascenseur.pack(side="right", fill="y")
        canevas.pack(side="left", fill="both", expand=True)

        self.contenu = ttk.Frame(canevas)
        fenetre = canevas.create_window((0, 0), window=self.contenu, anchor="nw")

        def _region_a_jour(_evenement=None) -> None:
            canevas.configure(scrollregion=canevas.bbox("all"))

        def _largeur_a_jour(evenement) -> None:
            canevas.itemconfigure(fenetre, width=evenement.width)

        self.contenu.bind("<Configure>", _region_a_jour)
        canevas.bind("<Configure>", _largeur_a_jour)

        def _molette(evenement) -> None:
            canevas.yview_scroll(int(-1 * (evenement.delta / 120)), "units")

        canevas.bind("<Enter>", lambda _e: canevas.bind_all("<MouseWheel>", _molette))
        canevas.bind("<Leave>", lambda _e: canevas.unbind_all("<MouseWheel>"))

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
