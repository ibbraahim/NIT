"""Pastille de statut : petite pilule colorée portant un texte (« ● Conforme », « Critique »…)."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from app.gui.formes import photo, rectangle_arrondi
from app.gui.style import COULEURS, COULEURS_STATUT, COULEURS_STATUT_CLAIR, PUCE_STATUT
from app.gui.widgets.bouton import couleur_fond

HAUTEUR_PASTILLE = 24


class Pastille(tk.Label):
    """Pilule à fond pâle et texte de la couleur pleine du statut (``vert``, ``orange``,
    ``rouge``, ``gris``) ; ``accent`` donne une pastille aux couleurs d'accent."""

    def __init__(self, parent: tk.Misc, texte: str, statut: str | None = "gris") -> None:
        self._police = tkfont.Font(root=parent, font=tkfont.nametofont("TkDefaultFont"))
        self._police.configure(weight="bold", size=9)
        super().__init__(
            parent,
            compound="center",
            borderwidth=0,
            highlightthickness=0,
            background=couleur_fond(parent),
            font=self._police,
        )
        self.definir(texte, statut)

    def definir(self, texte: str, statut: str | None = "gris") -> None:
        """Change le texte et le statut (donc les couleurs) de la pastille."""
        if statut == "accent":
            fond, texte_couleur = COULEURS["selection"], COULEURS["accent"]
        else:
            fond = COULEURS_STATUT_CLAIR.get(statut, COULEURS["gris_clair"])
            texte_couleur = COULEURS_STATUT.get(statut, COULEURS["gris"])
        libelle = f"{PUCE_STATUT} {texte}" if statut in ("vert", "orange", "rouge") else texte
        largeur = self._police.measure(libelle) + 24
        image = photo(
            self,
            ("pastille", largeur, fond),
            lambda: rectangle_arrondi(largeur, HAUTEUR_PASTILLE, HAUTEUR_PASTILLE / 2, (fond,)),
        )
        self.configure(image=image, text=libelle, foreground=texte_couleur)
