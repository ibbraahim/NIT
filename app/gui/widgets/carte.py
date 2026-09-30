"""Cartes du nouveau design : panneaux à coins arrondis posés sur le fond de page.

Tk ne sait pas arrondir un cadre : la carte est un ``Frame`` ordinaire à bordure d'un pixel, dont
les quatre coins sont recouverts par de petites images (l'arc de cercle, avec sa bordure) aux
couleurs exactes de la carte et de ce qu'il y a derrière. Il faut donc dire sur quel fond la
carte est posée (``sur``) : la page, ou une autre carte.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.gui.formes import coins_arrondis
from app.gui.style import COULEURS

RAYON_CARTE = 14
#: Espace vertical entre deux cartes empilées.
ECART_CARTES = 16


class Carte(tk.Frame):
    """Panneau arrondi. ``zone`` est le cadre où placer le contenu ; un titre (et un sous-titre)
    facultatifs forment un en-tête dont la droite (``actions``) peut recevoir des boutons."""

    def __init__(
        self,
        parent: tk.Misc,
        titre: str = "",
        sous_titre: str = "",
        sur: str = "page",
        marge: int = 18,
        rayon: int = RAYON_CARTE,
        couleur: str | None = None,
        fond: str | None = None,
        bordure: str | None = None,
    ) -> None:
        """``couleur``, ``fond`` et ``bordure`` remplacent les couleurs d'une carte ordinaire (par
        exemple pour un encart teinté dans la barre latérale) ; le contenu est alors posé dans
        ``corps``, un ``tk.Frame`` de cette couleur, avec des widgets Tk de même fond."""
        c = COULEURS
        fond = fond or (c["fond"] if sur == "page" else c["surface"])
        couleur_carte = couleur or c["surface"]
        couleur_bordure = bordure or c["bordure"]
        super().__init__(
            parent,
            background=couleur_carte,
            highlightthickness=1,
            highlightbackground=couleur_bordure,
            highlightcolor=couleur_bordure,
            borderwidth=0,
        )
        self.corps = tk.Frame(self, background=couleur_carte) if couleur else ttk.Frame(self)
        self.corps.pack(fill="both", expand=True, padx=max(marge, rayon), pady=max(marge, rayon))
        self.entete: ttk.Frame | None = None
        self.actions: ttk.Frame | None = None
        if titre:
            self.entete = ttk.Frame(self.corps)
            self.entete.pack(fill="x", pady=(0, 10))
            textes = ttk.Frame(self.entete)
            textes.pack(side="left", fill="x", expand=True)
            ttk.Label(textes, text=titre, style="Section.TLabel").pack(anchor="w")
            if sous_titre:
                ttk.Label(textes, text=sous_titre, style="Aide.TLabel").pack(anchor="w")
            self.actions = ttk.Frame(self.entete)
            self.actions.pack(side="right")
            self.zone = ttk.Frame(self.corps)
            self.zone.pack(fill="both", expand=True)
        else:
            self.zone = self.corps
        coins = coins_arrondis(self, rayon, couleur_carte, fond, couleur_bordure)
        for nom, (x, y) in {"nw": (0, 0), "ne": (1, 0), "sw": (0, 1), "se": (1, 1)}.items():
            coin = tk.Label(
                self, image=coins[nom], borderwidth=0, highlightthickness=0, background=fond
            )
            coin.place(relx=x, rely=y, anchor=nom, bordermode="outside")


def ajouter_carte(
    parent: tk.Misc,
    titre: str = "",
    sous_titre: str = "",
    marge: int = 18,
    expand: bool = False,
    dernier: bool = False,
) -> Carte:
    """Carte ajoutée en bas de ``parent`` (empilement vertical, pleine largeur) ; ``dernier``
    supprime l'espace sous la carte et ``expand`` la laisse occuper la place restante."""
    carte = Carte(parent, titre, sous_titre, marge=marge)
    carte.pack(
        fill="both" if expand else "x", expand=expand, pady=(0, 0 if dernier else ECART_CARTES)
    )
    return carte
