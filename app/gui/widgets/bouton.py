"""Bouton qui explique, par une info-bulle, pourquoi il est grisé."""

from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk

from app.gui.widgets.infobulle import InfoBulle


class Bouton(ttk.Button):
    """``ttk.Button`` avec :meth:`activer` et info-bulle explicative quand il est grisé."""

    def __init__(
        self,
        parent,
        texte: str,
        commande: Callable[[], None],
        aide: str = "",
        primaire: bool = False,
        **options,
    ) -> None:
        if primaire:
            options.setdefault("style", "Primaire.TButton")
        super().__init__(parent, text=texte, command=commande, **options)
        self._aide = aide
        self._infobulle = InfoBulle(self, aide)
        self.raison = ""

    def activer(self, actif: bool, raison: str = "") -> None:
        """Active le bouton, ou le grise en affichant ``raison`` au survol."""
        self.state(["!disabled"] if actif else ["disabled"])
        self.raison = "" if actif else raison
        self._infobulle.definir(self._aide if actif else raison)

    @property
    def est_actif(self) -> bool:
        return not self.instate(["disabled"])
