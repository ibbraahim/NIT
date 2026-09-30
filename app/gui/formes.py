"""Formes arrondies, dégradés et avatars dessinés avec PIL, pour les widgets Tkinter.

Tk ne sait ni arrondir un coin ni peindre un dégradé : les cartes, boutons en pilule,
pastilles et avatars du nouveau design sont donc de petites images générées ici, avec un
anticrénelage analytique (distance signée à la forme), puis affichées dans des ``Label`` ou
des ``Canvas``. Les images PIL sont mises en cache par paramètres ; les ``PhotoImage`` Tk, liées
à une fenêtre racine, le sont par racine (``photo``) pour ne jamais survivre à leur fenêtre.
"""

from __future__ import annotations

import base64
import tkinter as tk
import weakref
from collections.abc import Callable, Hashable, Sequence
from functools import lru_cache
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.config import DOSSIER_POLICES

_caches: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def photo(widget: tk.Misc, cle: Hashable, fabrique: Callable[[], Image.Image]) -> tk.PhotoImage:
    """``PhotoImage`` mis en cache pour la fenêtre racine de ``widget`` (``fabrique`` construit
    l'image PIL la première fois)."""
    racine = widget._root()
    cache = _caches.setdefault(racine, {})
    if cle not in cache:
        tampon = BytesIO()
        fabrique().save(tampon, "PNG")
        cache[cle] = tk.PhotoImage(master=racine, data=base64.b64encode(tampon.getvalue()))
    return cache[cle]


def hex_vers_rgb(couleur: str) -> tuple[int, int, int]:
    couleur = couleur.lstrip("#")
    return int(couleur[0:2], 16), int(couleur[2:4], 16), int(couleur[4:6], 16)


def _degrade(largeur: int, hauteur: int, couleurs: Sequence[str], angle: float) -> np.ndarray:
    """Tableau ``hauteur × largeur × 3`` : dégradé multi-teintes dans la direction ``angle``
    (degrés, 0 = gauche → droite, 90 = haut → bas)."""
    rgb = np.array([hex_vers_rgb(c) for c in couleurs], dtype=float)
    if len(rgb) == 1:
        return np.broadcast_to(rgb[0], (hauteur, largeur, 3)).copy()
    y, x = np.mgrid[0:hauteur, 0:largeur]
    theta = np.radians(angle)
    dx, dy = np.cos(theta), np.sin(theta)
    etendue = abs(largeur * dx) + abs(hauteur * dy) or 1.0
    t = np.clip(((x + 0.5 - largeur / 2) * dx + (y + 0.5 - hauteur / 2) * dy) / etendue + 0.5, 0, 1)
    reperes = np.linspace(0, 1, len(rgb))
    return np.stack([np.interp(t, reperes, rgb[:, i]) for i in range(3)], axis=-1)


def _distance_signee(largeur: int, hauteur: int, rayon: float) -> np.ndarray:
    """Distance (en pixels) de chaque centre de pixel au bord d'un rectangle arrondi : négative
    à l'intérieur, positive à l'extérieur."""
    y, x = np.mgrid[0:hauteur, 0:largeur]
    qx = np.abs(x + 0.5 - largeur / 2) - (largeur / 2 - rayon)
    qy = np.abs(y + 0.5 - hauteur / 2) - (hauteur / 2 - rayon)
    return (
        np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - rayon
    )


@lru_cache(maxsize=512)
def rectangle_arrondi(
    largeur: int,
    hauteur: int,
    rayon: float,
    remplissage: tuple[str, ...],
    angle: float = 0.0,
    bordure: str | None = None,
    epaisseur: float = 1.0,
    opacite: float = 1.0,
) -> Image.Image:
    """Image RGBA d'un rectangle arrondi plein (aplat ou dégradé), avec bordure facultative ;
    les coins sont transparents (le widget qui l'affiche montre son propre fond) et ``opacite``
    (0 à 1) atténue l'ensemble, pour les voiles translucides posés sur un dégradé."""
    largeur, hauteur = max(int(largeur), 2), max(int(hauteur), 2)
    rayon = min(rayon, largeur / 2, hauteur / 2)
    distance = _distance_signee(largeur, hauteur, rayon)
    couverture = np.clip(0.5 - distance, 0, 1)
    couleur = _degrade(largeur, hauteur, remplissage, angle)
    if bordure:
        anneau = np.clip(distance + epaisseur + 0.5, 0, 1)[..., None]
        couleur = couleur * (1 - anneau) + np.array(hex_vers_rgb(bordure), dtype=float) * anneau
    pixels = np.dstack([couleur, couverture * 255 * opacite]).astype("uint8")
    return Image.fromarray(pixels, "RGBA")


@lru_cache(maxsize=128)
def coin_arrondi(
    rayon: int, couleur_carte: str, couleur_fond: str, couleur_bordure: str | None
) -> Image.Image:
    """Coin haut-gauche ``rayon × rayon`` d'une carte arrondie : la carte à l'intérieur de
    l'arc (avec sa bordure d'un pixel), le fond de la page à l'extérieur. Opaque, donc posé tel
    quel sur un coin de carte sans dépendre de la transparence."""
    y, x = np.mgrid[0:rayon, 0:rayon]
    d = np.hypot(rayon - (x + 0.5), rayon - (y + 0.5))
    interieur = np.clip(rayon - d + 0.5, 0, 1)[..., None]
    carte = np.array(hex_vers_rgb(couleur_carte), dtype=float)
    if couleur_bordure:
        anneau = np.clip(d - (rayon - 1) + 0.5, 0, 1)[..., None]
        carte = carte * (1 - anneau) + np.array(hex_vers_rgb(couleur_bordure), dtype=float) * anneau
    fond = np.array(hex_vers_rgb(couleur_fond), dtype=float)
    pixels = (fond * (1 - interieur) + carte * interieur).astype("uint8")
    return Image.fromarray(pixels, "RGB")


def coins_arrondis(
    widget: tk.Misc, rayon: int, couleur_carte: str, couleur_fond: str, couleur_bordure: str | None
) -> dict[str, tk.PhotoImage]:
    """Les quatre coins (``nw``, ``ne``, ``sw``, ``se``) d'une carte arrondie, prêts à être
    posés avec ``place`` aux quatre angles d'un cadre."""
    base = coin_arrondi(rayon, couleur_carte, couleur_fond, couleur_bordure)
    transformations = {
        "nw": None,
        "ne": Image.FLIP_LEFT_RIGHT,
        "sw": Image.FLIP_TOP_BOTTOM,
        "se": Image.ROTATE_180,
    }
    coins = {}
    for nom, transformation in transformations.items():
        cle = ("coin", nom, rayon, couleur_carte, couleur_fond, couleur_bordure)
        coins[nom] = photo(
            widget,
            cle,
            lambda t=transformation: base if t is None else base.transpose(t),
        )
    return coins


@lru_cache(maxsize=64)
def avatar(initiales: str, diametre: int, couleurs: tuple[str, ...]) -> Image.Image:
    """Pastille ronde en dégradé portant les initiales de l'utilisateur."""
    echelle = 4
    taille = diametre * echelle
    masque = Image.new("L", (taille, taille), 0)
    ImageDraw.Draw(masque).ellipse((0, 0, taille - 1, taille - 1), fill=255)
    fond = Image.fromarray(_degrade(taille, taille, couleurs, 45).astype("uint8"), "RGB")
    image = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    image.paste(fond, (0, 0), masque)
    police = ImageFont.truetype(str(DOSSIER_POLICES / "DejaVuSans-Bold.ttf"), int(taille * 0.38))
    ImageDraw.Draw(image).text(
        (taille / 2, taille / 2), initiales[:2].upper(), font=police, fill="white", anchor="mm"
    )
    return image.resize((diametre, diametre), Image.LANCZOS)


@lru_cache(maxsize=16)
def image_arrondie(chemin: str, taille: int, rayon: float) -> Image.Image:
    """Image carrée (logo) redimensionnée et aux coins arrondis, sur fond transparent."""
    image = Image.open(chemin).convert("RGBA").resize((taille, taille), Image.LANCZOS)
    couverture = np.clip(0.5 - _distance_signee(taille, taille, rayon), 0, 1)
    image.putalpha(Image.fromarray((couverture * 255).astype("uint8"), "L"))
    return image


@lru_cache(maxsize=128)
def carte_hero(
    largeur: int, hauteur: int, rayon: float, degrade: tuple[str, ...], angle: float = 35.0
) -> Image.Image:
    """Fond d'une carte « héros » : rectangle arrondi en dégradé, avec deux grands disques
    translucides en bas à droite (comme sur les cartes de la référence)."""
    base = np.array(rectangle_arrondi(largeur, hauteur, rayon, degrade, angle), dtype=float)
    y, x = np.mgrid[0:hauteur, 0:largeur]
    for cx, cy, r, opacite in (
        (largeur * 0.88, hauteur * 0.98, hauteur * 0.85, 0.11),
        (largeur * 0.68, hauteur * 1.18, hauteur * 0.78, 0.07),
    ):
        couverture = np.clip(r - np.hypot(x + 0.5 - cx, y + 0.5 - cy) + 0.5, 0, 1) * opacite
        base[..., :3] = base[..., :3] * (1 - couverture[..., None]) + 255 * couverture[..., None]
    return Image.fromarray(base.astype("uint8"), "RGBA")
