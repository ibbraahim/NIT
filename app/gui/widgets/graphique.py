"""Graphique matplotlib intégré à Tkinter (sans barre d'outils : ses info-bulles sont en
anglais et ne peuvent pas être francisées)."""

from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk

import matplotlib

matplotlib.use("TkAgg")
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from app.gui.style import COULEURS  # noqa: E402

#: Palette de séries, dans l'ordre d'utilisation habituel (réel, RL, RN, capacité…).
COULEURS_SERIES = [
    COULEURS["primaire"],
    COULEURS["orange"],
    COULEURS["vert"],
    COULEURS["rouge"],
    COULEURS["gris"],
]


class GraphiqueIntegre(ttk.Frame):
    """Zone de graphique réutilisable ; ``dessiner`` reçoit un axe matplotlib à remplir."""

    def __init__(self, parent, largeur: float = 6.4, hauteur: float = 3.4, dpi: int = 100) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(largeur, hauteur), dpi=dpi, facecolor=COULEURS["surface"])
        self.axe = self.figure.add_subplot(111)
        self.canevas = FigureCanvasTkAgg(self.figure, master=self)
        self.canevas.get_tk_widget().pack(fill="both", expand=True)
        self._message_vide = None
        self.dessiner(lambda axe: None)

    def dessiner(self, construire: Callable[..., None]) -> None:
        """Efface le graphique puis appelle ``construire(axe)`` pour le remplir."""
        self.axe.clear()
        self.axe.set_facecolor(COULEURS["surface"])
        construire(self.axe)
        self.figure.tight_layout()
        self.canevas.draw_idle()

    def afficher_message(self, message: str) -> None:
        """Affiche un message à la place du graphique (aucune donnée à tracer)."""

        def _dessiner(axe):
            axe.axis("off")
            axe.text(
                0.5,
                0.5,
                message,
                ha="center",
                va="center",
                color=COULEURS["texte_secondaire"],
                wrap=True,
                transform=axe.transAxes,
            )

        self.dessiner(_dessiner)
