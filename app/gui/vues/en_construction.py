"""Écran provisoire des fonctionnalités livrées dans un lot ultérieur."""

from __future__ import annotations

from tkinter import ttk

from app.gui.vues.base import Vue


class VueEnConstruction(Vue):
    """Écran provisoire : indique le lot de livraison."""

    lot = ""

    def construire(self) -> None:
        ttk.Label(
            self.contenu,
            text=f"Cet écran sera livré avec le {self.lot} du projet.",
            style="Aide.TLabel",
        ).pack(anchor="w")
