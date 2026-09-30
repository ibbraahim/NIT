"""Tracés matplotlib du nouveau design : anneau, jauge et barres arrondies.

Les formes sont construites en unités de données (``Wedge``, ``Circle``) ou ajustées à la taille
réelle de l'axe à chaque dessin (barres), pour que les arrondis restent ronds quelle que soit la
proportion du graphique. Aucune ne dépend de Tkinter : elles peuvent servir à un rendu Agg.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Wedge

from app.gui.style import COULEURS


def _extremite_ronde(
    axe, rayon_milieu: float, angle_deg: float, epaisseur: float, couleur, surplus: float = 0.0
) -> None:
    angle = math.radians(angle_deg)
    axe.add_patch(
        Circle(
            (rayon_milieu * math.cos(angle), rayon_milieu * math.sin(angle)),
            epaisseur / 2 + surplus,
            facecolor=couleur,
            edgecolor="none",
            zorder=3,
        )
    )


def _arc(
    axe,
    debut_deg: float,
    fin_deg: float,
    epaisseur: float,
    couleur,
    arrondi: bool,
    ecart_deg: float = 0.0,
    surplus: float = 0.0,
) -> None:
    """Arc d'anneau (rayon extérieur 1) balayé dans le sens horaire de ``debut`` à ``fin``
    (degrés), aux extrémités arrondies si ``arrondi``, raccourci de ``ecart_deg`` à chaque bout."""
    rayon_milieu = 1 - epaisseur / 2
    cap = math.degrees((epaisseur / 2) / rayon_milieu) if arrondi else 0.0
    haut = debut_deg - ecart_deg / 2 - cap
    bas = fin_deg + ecart_deg / 2 + cap
    if haut <= bas:
        _extremite_ronde(axe, rayon_milieu, (haut + bas) / 2, epaisseur, couleur, surplus)
        return
    axe.add_patch(
        Wedge(
            (0, 0),
            1 + surplus,
            bas,
            haut,
            width=epaisseur + 2 * surplus,
            facecolor=couleur,
            edgecolor="none",
            zorder=2,
        )
    )
    if arrondi:
        _extremite_ronde(axe, rayon_milieu, haut, epaisseur, couleur, surplus)
        _extremite_ronde(axe, rayon_milieu, bas, epaisseur, couleur, surplus)


def anneau(
    axe,
    valeurs: Sequence[float],
    couleurs: Sequence[str],
    epaisseur: float = 0.24,
    ecart_deg: float = 7.0,
    centre: str = "",
    sous_centre: str = "",
) -> None:
    """Anneau de segments proportionnels à ``valeurs``, extrémités arrondies, départ en haut ;
    ``centre`` et ``sous_centre`` s'inscrivent au milieu (total, libellé…)."""
    total = float(sum(v for v in valeurs if v > 0))
    axe.set_axis_off()
    axe.set_aspect("equal")
    axe.set_xlim(-1.08, 1.08)
    axe.set_ylim(-1.08, 1.08)
    if total <= 0:
        _arc(axe, 90, -270, epaisseur, COULEURS["surface_2"], False)
    else:
        position = 90.0
        visibles = [(v, c) for v, c in zip(valeurs, couleurs, strict=False) if v > 0]
        seul = len(visibles) == 1
        for valeur, couleur in visibles:
            etendue = 360.0 * valeur / total
            if seul:
                _arc(axe, 90, -270, epaisseur, couleur, False)
            else:
                _arc(axe, position, position - etendue, epaisseur, couleur, True, ecart_deg)
            position -= etendue
    if centre:
        axe.text(
            0,
            0.06 if sous_centre else 0,
            centre,
            ha="center",
            va="center",
            fontsize=17,
            fontweight="bold",
            color=COULEURS["texte"],
        )
    if sous_centre:
        axe.text(
            0,
            -0.22,
            sous_centre,
            ha="center",
            va="center",
            fontsize=8.5,
            color=COULEURS["texte_secondaire"],
        )


def jauge(
    axe,
    fraction: float,
    couleur: str,
    centre: str = "",
    sous_centre: str = "",
    epaisseur: float = 0.26,
) -> None:
    """Jauge en demi-cercle : piste grise, arc de progression arrondi de ``couleur`` couvrant
    ``fraction`` (0 à 1) de l'arc, valeur au centre."""
    fraction = min(max(fraction, 0.0), 1.0)
    axe.set_axis_off()
    axe.set_aspect("equal")
    axe.set_xlim(-1.1, 1.1)
    axe.set_ylim(-0.12, 1.1)
    _arc(axe, 180, 0, epaisseur, COULEURS["surface_2"], True)
    if fraction > 0:
        # Léger surplus : la piste dessous ne doit pas déborder de l'anticrénelage.
        _arc(axe, 180, 180 - 180 * fraction, epaisseur, couleur, True, surplus=0.006)
    if centre:
        axe.text(
            0,
            0.22,
            centre,
            ha="center",
            va="center",
            fontsize=20,
            fontweight="bold",
            color=COULEURS["texte"],
        )
    if sous_centre:
        axe.text(
            0,
            0.0,
            sous_centre,
            ha="center",
            va="center",
            fontsize=8.5,
            color=COULEURS["texte_secondaire"],
        )


class _BarresArrondies:
    """Barres à coins arrondis dont le rayon reste circulaire : à chaque dessin, l'arrondi est
    recalculé d'après la taille réelle de l'axe (pixels par unité en x et en y)."""

    def __init__(self, axe, patches: list[FancyBboxPatch], rayon_px: float) -> None:
        self.axe = axe
        self.patches = patches
        self.rayon_px = rayon_px
        self._dernier: tuple[float, float] | None = None
        cid = axe.figure.canvas.mpl_connect("draw_event", self._ajuster)
        # matplotlib ne garde qu'une référence faible vers une méthode : l'axe garde l'objet.
        axe.__dict__.setdefault("_rappels_workly", []).append(cid)
        axe.__dict__.setdefault("_objets_workly", []).append(self)

    def _ajuster(self, _evenement=None) -> None:
        boite = self.axe.get_window_extent()
        x0, x1 = self.axe.get_xlim()
        y0, y1 = self.axe.get_ylim()
        if boite.width < 2 or boite.height < 2 or x1 == x0 or y1 == y0:
            return
        x_par_px = abs(x1 - x0) / boite.width
        y_par_px = abs(y1 - y0) / boite.height
        cle = (round(x_par_px, 6), round(y_par_px, 6))
        if cle == self._dernier:
            return
        self._dernier = cle
        for patch in self.patches:
            largeur = patch.get_width()
            rayon = min(self.rayon_px * x_par_px, largeur / 2)
            patch.set_boxstyle("round", pad=0, rounding_size=rayon)
            patch.set_mutation_aspect(y_par_px / x_par_px)
        # Un dessin demandé pendant un dessin est ignoré par Tk : on le reporte d'un instant.
        canevas = self.axe.figure.canvas
        minuteur = canevas.new_timer(interval=20)
        minuteur.single_shot = True
        minuteur.add_callback(canevas.draw_idle)
        minuteur.start()


def barres_arrondies(
    axe,
    positions: Sequence[float],
    hauteurs: Sequence[float],
    largeur: float,
    couleur: str,
    libelle: str | None = None,
    rayon_px: float = 7.0,
) -> None:
    """Barres verticales à coins arrondis posées sur l'axe des x (valeurs nulles ou absentes
    ignorées). ``libelle`` alimente la légende. Les limites de l'axe sont à régler par
    l'appelant (voir :func:`barres_groupees`)."""
    patches = []
    for x, hauteur in zip(positions, hauteurs, strict=False):
        if hauteur is None or not np.isfinite(hauteur) or hauteur <= 0:
            continue
        patch = FancyBboxPatch(
            (x - largeur / 2, 0),
            largeur,
            hauteur,
            boxstyle="round,pad=0,rounding_size=0.01",
            facecolor=couleur,
            edgecolor="none",
            zorder=2,
            label=libelle if not patches else "_nolegend_",
        )
        axe.add_patch(patch)
        patches.append(patch)
    if patches:
        _BarresArrondies(axe, patches, rayon_px)


def barres_groupees(
    axe,
    categories: Sequence[str],
    series: Sequence[tuple[Sequence[float | None], str, str | None]],
    largeur_groupe: float = 0.74,
    rayon_px: float = 7.0,
) -> None:
    """Groupes de barres arrondies : une catégorie par groupe, une barre par série
    (``(hauteurs, couleur, libellé)``), étiquettes de catégorie sous l'axe, limites ajustées."""
    positions = np.arange(len(categories))
    n = max(len(series), 1)
    largeur = largeur_groupe / n
    ecart = min(0.05, largeur * 0.14)
    sommet = 0.0
    for rang, (hauteurs, couleur, libelle) in enumerate(series):
        decalage = (rang - (n - 1) / 2) * largeur
        barres_arrondies(
            axe, positions + decalage, hauteurs, largeur - ecart, couleur, libelle, rayon_px
        )
        sommet = max(
            sommet, max((h for h in hauteurs if h is not None and np.isfinite(h)), default=0)
        )
    axe.set_xticks(positions)
    axe.set_xticklabels(list(categories), fontsize=8)
    axe.set_xlim(-0.6, len(categories) - 0.4)
    axe.set_ylim(0, (sommet or 1) * 1.14)
    axe.grid(axis="x", visible=False)
