"""Classe de base des écrans."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.gui.style import COULEURS
from app.gui.widgets.dialogues import executer_action


class Vue(ttk.Frame):
    """Écran affiché dans la zone de contenu de la fenêtre principale.

    Le titre et le sous-titre (attributs de classe) sont affichés par l'en-tête de la fenêtre
    principale. Le contenu (``self.contenu``) défile verticalement sans limite : les écrans dont
    les éléments dépassent la hauteur visible restent entièrement accessibles à la molette ou
    à l'ascenseur, plutôt que d'être comprimés ou coupés.
    """

    titre = ""
    sous_titre = ""

    def __init__(self, parent, application) -> None:
        super().__init__(parent, padding=(28, 10, 14, 10), style="Page.TFrame")
        self.application = application
        self.ctx = application.contexte

        cadre_defilant = ttk.Frame(self, style="Page.TFrame")
        cadre_defilant.pack(fill="both", expand=True)
        canevas = tk.Canvas(cadre_defilant, highlightthickness=0, background=COULEURS["fond"])
        ascenseur = ttk.Scrollbar(cadre_defilant, orient="vertical", command=canevas.yview)
        canevas.configure(yscrollcommand=ascenseur.set)
        ascenseur.pack(side="right", fill="y")
        canevas.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.contenu = ttk.Frame(canevas, style="Page.TFrame")
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
