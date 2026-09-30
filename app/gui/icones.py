"""Petites icônes générées et mises en cache (PIL), pour les endroits où Tkinter n'a pas
d'équivalent natif (icône « œil » du champ mot de passe)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from app.config import DOSSIER_IMAGES

DOSSIER_ICONES = DOSSIER_IMAGES / "icones"

TAILLE_OEIL = 18


def icone_oeil(couleur: str, barre: bool) -> Path:
    """Icône « œil » (ouvert, ou barré) de la couleur donnée, en PNG avec transparence."""
    DOSSIER_ICONES.mkdir(parents=True, exist_ok=True)
    nom = f"oeil_{'barre' if barre else 'ouvert'}_{couleur.lstrip('#').lower()}.png"
    chemin = DOSSIER_ICONES / nom
    if chemin.is_file():
        return chemin
    echelle = 4
    taille = TAILLE_OEIL * echelle
    image = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    centre = taille / 2
    marge_x = taille * 0.08
    demi_hauteur = taille * 0.24
    largeur_trait = max(round(taille * 0.09), 1)
    # Forme en amande (deux arcs d'une même ellipse large et basse) : l'œil.
    dessin.arc(
        [marge_x, centre - demi_hauteur, taille - marge_x, centre + demi_hauteur],
        start=180,
        end=360,
        fill=couleur,
        width=largeur_trait,
    )
    dessin.arc(
        [marge_x, centre - demi_hauteur, taille - marge_x, centre + demi_hauteur],
        start=0,
        end=180,
        fill=couleur,
        width=largeur_trait,
    )
    rayon = taille * 0.11
    dessin.ellipse(
        [centre - rayon, centre - rayon, centre + rayon, centre + rayon],
        outline=couleur,
        width=largeur_trait,
    )
    if barre:
        dessin.line(
            [marge_x * 0.5, taille - marge_x * 0.5, taille - marge_x * 0.5, marge_x * 0.5],
            fill=couleur,
            width=largeur_trait,
        )
    image = image.resize((TAILLE_OEIL, TAILLE_OEIL), Image.LANCZOS)
    image.save(chemin)
    return chemin


# ---------------------------------------------------------------------------
# Icônes d'interface (menu latéral, en-tête) : tracés au trait sur une grille 24 × 24,
# dessinés en masque sur-échantillonné puis teintés, donc nets à toute taille et de toute couleur.
# ---------------------------------------------------------------------------
_SURECHANTILLONNAGE = 8


class _Crayon:
    """Petit outil de dessin en unités de la grille 24 × 24 (traits à bouts arrondis)."""

    def __init__(self, taille: int) -> None:
        self.n = taille * _SURECHANTILLONNAGE
        self.k = self.n / 24
        self.masque = Image.new("L", (self.n, self.n), 0)
        self.d = ImageDraw.Draw(self.masque)
        self.w = max(round(1.8 * self.k), 1)

    def _p(self, points):
        return [(x * self.k, y * self.k) for x, y in points]

    def ligne(self, *points) -> None:
        pts = self._p(points)
        self.d.line(pts, fill=255, width=self.w, joint="curve")
        rayon = self.w / 2
        for x, y in pts:
            self.d.ellipse((x - rayon, y - rayon, x + rayon, y + rayon), fill=255)

    def cercle(self, cx, cy, r, plein=False) -> None:
        boite = [(cx - r) * self.k, (cy - r) * self.k, (cx + r) * self.k, (cy + r) * self.k]
        if plein:
            self.d.ellipse(boite, fill=255)
        else:
            self.d.ellipse(boite, outline=255, width=self.w)

    def efface_cercle(self, cx, cy, r) -> None:
        self.d.ellipse(
            [(cx - r) * self.k, (cy - r) * self.k, (cx + r) * self.k, (cy + r) * self.k], fill=0
        )

    def rect(self, x0, y0, x1, y1, r=0, plein=False) -> None:
        boite = [x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k]
        if plein:
            self.d.rounded_rectangle(boite, radius=r * self.k, fill=255)
        else:
            self.d.rounded_rectangle(boite, radius=r * self.k, outline=255, width=self.w)

    def arc(self, x0, y0, x1, y1, debut, fin) -> None:
        self.d.arc(
            [x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k],
            debut,
            fin,
            fill=255,
            width=self.w,
        )

    def ellipse(self, x0, y0, x1, y1) -> None:
        self.d.ellipse(
            [x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k], outline=255, width=self.w
        )


def _tableau_bord(c: _Crayon) -> None:
    for x, y in ((3.5, 3.5), (13.5, 3.5), (3.5, 13.5), (13.5, 13.5)):
        c.rect(x, y, x + 7, y + 7, r=2)


def _donnees(c: _Crayon) -> None:
    c.ellipse(4.5, 3, 19.5, 8.5)
    c.ligne((4.5, 5.75), (4.5, 18.25))
    c.ligne((19.5, 5.75), (19.5, 18.25))
    c.arc(4.5, 9.5, 19.5, 15, 0, 180)
    c.arc(4.5, 15.5, 19.5, 21, 0, 180)


def _previsions(c: _Crayon) -> None:
    c.ligne((3.5, 3.5), (3.5, 20.5), (20.5, 20.5))
    c.ligne((7, 16), (11, 11.5), (14, 14), (20, 7))
    c.cercle(20, 7, 1.6, plein=True)


def _plan_charge(c: _Crayon) -> None:
    c.rect(3.5, 5, 20.5, 20.5, r=3)
    c.ligne((3.5, 10), (20.5, 10))
    c.ligne((8, 3), (8, 7))
    c.ligne((16, 3), (16, 7))
    for x in (8, 12, 16):
        c.cercle(x, 14.8, 0.9, plein=True)


def _comparaison(c: _Crayon) -> None:
    c.ligne((4, 8), (20, 8))
    c.ligne((16, 4.5), (20, 8), (16, 11.5))
    c.ligne((20, 16), (4, 16))
    c.ligne((8, 12.5), (4, 16), (8, 19.5))


def _kpi_cibles(c: _Crayon) -> None:
    c.cercle(12, 12, 9)
    c.cercle(12, 12, 5)
    c.cercle(12, 12, 1.5, plein=True)


def _alertes(c: _Crayon) -> None:
    c.arc(6, 4, 18, 16, 180, 360)
    c.ligne((6, 10), (5.2, 16), (3.5, 17.5))
    c.ligne((18, 10), (18.8, 16), (20.5, 17.5))
    c.ligne((3.5, 17.5), (20.5, 17.5))
    c.arc(9.5, 18.5, 14.5, 22.5, 0, 180)
    c.ligne((12, 2.5), (12, 4))


def _rapports(c: _Crayon) -> None:
    c.ligne((6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3))
    c.ligne((14, 3), (14, 8), (19, 8))
    c.ligne((9.5, 13), (15.5, 13))
    c.ligne((9.5, 17), (15.5, 17))


def _modeles(c: _Crayon) -> None:
    noeuds = {"g": (4.5, 12), "h": (12, 5), "b": (12, 19), "d": (19.5, 12)}
    for a, b in (("g", "h"), ("g", "b"), ("h", "d"), ("b", "d"), ("h", "b")):
        c.ligne(noeuds[a], noeuds[b])
    for x, y in noeuds.values():
        c.cercle(x, y, 2.3, plein=True)


def _administration(c: _Crayon) -> None:
    for y, x in ((6, 9), (12, 16), (18, 8)):
        c.ligne((3.5, y), (20.5, y))
        c.cercle(x, y, 2.4, plein=True)


def _soleil(c: _Crayon) -> None:
    import math

    c.cercle(12, 12, 4.3)
    for i in range(8):
        a = math.radians(i * 45)
        c.ligne(
            (12 + 7.6 * math.cos(a), 12 + 7.6 * math.sin(a)),
            (12 + 10 * math.cos(a), 12 + 10 * math.sin(a)),
        )


def _lune(c: _Crayon) -> None:
    c.cercle(12, 12, 8.5, plein=True)
    c.efface_cercle(16.5, 8, 7.2)


def _deconnexion(c: _Crayon) -> None:
    c.ligne((9, 3.5), (4.5, 3.5), (4.5, 20.5), (9, 20.5))
    c.ligne((9, 12), (20, 12))
    c.ligne((16, 8), (20, 12), (16, 16))


def _chevron_bas(c: _Crayon) -> None:
    c.ligne((6.5, 9.5), (12, 15), (17.5, 9.5))


def _chevron_gauche(c: _Crayon) -> None:
    c.ligne((14.5, 6.5), (9, 12), (14.5, 17.5))


def _chevron_droite(c: _Crayon) -> None:
    c.ligne((9.5, 6.5), (15, 12), (9.5, 17.5))


def _rafraichir(c: _Crayon) -> None:
    c.arc(4.5, 4.5, 19.5, 19.5, 30, 320)
    c.ligne((19.5, 3.5), (19.5, 8.2), (14.8, 8.2))


def _plus(c: _Crayon) -> None:
    c.ligne((12, 5), (12, 19))
    c.ligne((5, 12), (19, 12))


_DESSINS = {
    "tableau_bord": _tableau_bord,
    "donnees": _donnees,
    "previsions": _previsions,
    "plan_charge": _plan_charge,
    "comparaison": _comparaison,
    "kpi_cibles": _kpi_cibles,
    "alertes": _alertes,
    "rapports": _rapports,
    "modeles": _modeles,
    "administration": _administration,
    "soleil": _soleil,
    "lune": _lune,
    "deconnexion": _deconnexion,
    "chevron_bas": _chevron_bas,
    "chevron_gauche": _chevron_gauche,
    "chevron_droite": _chevron_droite,
    "rafraichir": _rafraichir,
    "plus": _plus,
}


@lru_cache(maxsize=256)
def icone_interface(nom: str, couleur: str, taille: int = 20) -> Image.Image:
    """Icône d'interface ``nom`` (voir ``_DESSINS``), teinte ``couleur``, carrée de ``taille``
    pixels, sur fond transparent."""
    crayon = _Crayon(taille)
    _DESSINS[nom](crayon)
    masque = crayon.masque.resize((taille, taille), Image.LANCZOS)
    image = Image.new("RGBA", (taille, taille), couleur)
    image.putalpha(masque)
    return image
