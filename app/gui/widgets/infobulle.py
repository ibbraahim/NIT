"""Info-bulles affichées au survol d'un widget."""

from __future__ import annotations

import tkinter as tk

from app.gui.style import COULEURS


class InfoBulle:
    """Info-bulle attachée à un widget ; le texte peut être modifié à tout moment."""

    DELAI_MS = 450

    def __init__(self, widget: tk.Widget, texte: str = "") -> None:
        self.widget = widget
        self.texte = texte
        self._fenetre: tk.Toplevel | None = None
        self._minuterie: str | None = None
        widget.bind("<Enter>", self._programmer, add="+")
        widget.bind("<Leave>", self._masquer, add="+")
        widget.bind("<ButtonPress>", self._masquer, add="+")

    def definir(self, texte: str) -> None:
        """Change le texte (une chaîne vide désactive l'info-bulle)."""
        self.texte = texte

    def _programmer(self, _evenement=None) -> None:
        self._annuler()
        if self.texte:
            self._minuterie = self.widget.after(self.DELAI_MS, self._afficher)

    def _annuler(self) -> None:
        if self._minuterie is not None:
            self.widget.after_cancel(self._minuterie)
            self._minuterie = None

    def _afficher(self) -> None:
        if not self.texte or self._fenetre is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._fenetre = tk.Toplevel(self.widget)
        self._fenetre.wm_overrideredirect(True)
        self._fenetre.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._fenetre,
            text=self.texte,
            justify="left",
            background="#ffffe8",
            foreground=COULEURS["texte"],
            relief="solid",
            borderwidth=1,
            wraplength=360,
            padx=6,
            pady=4,
        ).pack()

    def _masquer(self, _evenement=None) -> None:
        self._annuler()
        if self._fenetre is not None:
            self._fenetre.destroy()
            self._fenetre = None
