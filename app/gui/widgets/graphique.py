"""Graphique matplotlib intégré à Tkinter (sans barre d'outils : ses info-bulles sont en
anglais et ne peuvent pas être francisées)."""

from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk

import matplotlib
import numpy as np

matplotlib.use("TkAgg")
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from app.gui.style import COULEUR_ACCENT_3, COULEURS  # noqa: E402

# En-têtes de graphiques dans l'accent de marque (identité Workly).
matplotlib.rcParams["axes.titlecolor"] = COULEUR_ACCENT_3
matplotlib.rcParams["axes.titleweight"] = "bold"

#: Palette de séries, dans l'ordre d'utilisation habituel (réel, RL, RN, capacité…).
COULEURS_SERIES = [
    COULEURS["primaire"],
    COULEURS["orange"],
    COULEURS["vert"],
    COULEURS["rouge"],
    COULEURS["gris"],
]


def remplissage_degrade(axe, x, y, couleur: str, alpha_max: float = 0.32) -> None:
    """Remplissage en dégradé sous la courbe principale ``(x, y)`` : ``couleur`` pleine près
    de la courbe, qui s'estompe progressivement vers la ligne de base — équivalent du
    remplissage en dégradé de la référence visuelle (``fill_between`` ne peint qu'un aplat
    uni ; on découpe une image en dégradé de transparence à la forme de l'aire sous la
    courbe). À appeler après le ``axe.plot(x, y, ...)`` de la courbe concernée, pour que
    ``x`` catégoriel ou en dates soit déjà converti par l'axe."""
    x_num = np.asarray(axe.convert_xunits(list(x)), dtype=float)
    y_num = np.asarray([v if v is not None else float("nan") for v in y], dtype=float)
    valides = ~np.isnan(y_num)
    if valides.sum() < 2:
        return
    x_num, y_num = x_num[valides], y_num[valides]
    limite_x, limite_y = axe.get_xlim(), axe.get_ylim()
    base = min(0.0, float(y_num.min()))
    degrade = np.zeros((256, 1, 4))
    degrade[:, 0, :3] = to_rgb(couleur)
    degrade[:, 0, 3] = np.linspace(alpha_max, 0.0, 256)
    image = axe.imshow(
        degrade,
        aspect="auto",
        extent=[x_num.min(), x_num.max(), base, y_num.max()],
        origin="upper",
        zorder=1,
    )
    sommets = np.vstack([[x_num[0], base], np.column_stack([x_num, y_num]), [x_num[-1], base]])
    decoupe = Polygon(sommets, closed=True, facecolor="none", edgecolor="none")
    axe.add_patch(decoupe)
    image.set_clip_path(decoupe)
    axe.set_xlim(limite_x)
    axe.set_ylim(limite_y)


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
