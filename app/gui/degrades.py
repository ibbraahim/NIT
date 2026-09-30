"""Génération et mise en cache disque d'images en dégradé multi-couleurs.

ttk ne sait peindre qu'une couleur unie par widget : pour les zones de marque (fonds,
boutons principaux, barres d'accent) où le prompt demande un véritable dégradé
multi-couleurs, on le peint une fois dans une image PNG, mise en cache dans
``ressources/images/degrades/`` (nom dérivé des couleurs et des dimensions : pas besoin
de régénérer tant qu'elles ne changent pas).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.config import DOSSIER_IMAGES

DOSSIER_DEGRADES = DOSSIER_IMAGES / "degrades"


def _hex_vers_rgb(couleur: str) -> tuple[int, int, int]:
    couleur = couleur.lstrip("#")
    return tuple(int(couleur[i : i + 2], 16) for i in (0, 2, 4))


def _interpoler(couleurs: list[str], t: float) -> tuple[int, int, int]:
    """Couleur RGB au point ``t`` (0 à 1) d'un dégradé multi-stops uniformément réparti."""
    if t <= 0:
        return _hex_vers_rgb(couleurs[0])
    if t >= 1:
        return _hex_vers_rgb(couleurs[-1])
    segments = len(couleurs) - 1
    position = t * segments
    indice = min(int(position), segments - 1)
    local = position - indice
    debut = _hex_vers_rgb(couleurs[indice])
    fin = _hex_vers_rgb(couleurs[indice + 1])
    return tuple(round(debut[i] + (fin[i] - debut[i]) * local) for i in range(3))


def image_degradee(
    largeur: int, hauteur: int, couleurs: list[str], horizontal: bool = True
) -> Path:
    """Chemin d'un PNG ``largeur``×``hauteur`` en dégradé linéaire passant par ``couleurs``
    (2 stops ou plus), horizontal ou vertical. Généré une seule fois puis mis en cache."""
    DOSSIER_DEGRADES.mkdir(parents=True, exist_ok=True)
    cle = "-".join(c.lstrip("#").lower() for c in couleurs)
    chemin = (
        DOSSIER_DEGRADES / f"degrade_{'h' if horizontal else 'v'}_{largeur}x{hauteur}_{cle}.png"
    )
    if chemin.is_file():
        return chemin
    taille = largeur if horizontal else hauteur
    bande = Image.new("RGB", (taille, 1) if horizontal else (1, taille))
    for i in range(taille):
        position = (i, 0) if horizontal else (0, i)
        bande.putpixel(position, _interpoler(couleurs, i / max(taille - 1, 1)))
    bande.resize((largeur, hauteur), Image.NEAREST).save(chemin)
    return chemin


def melanger(couleur_1: str, couleur_2: str, t: float) -> str:
    """Mélange linéaire de deux couleurs (``t`` = 0 → ``couleur_1``, 1 → ``couleur_2``)."""
    r1, g1, b1 = _hex_vers_rgb(couleur_1)
    r2, g2, b2 = _hex_vers_rgb(couleur_2)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def eclaircir(couleur: str, quantite: float) -> str:
    """``couleur`` mélangée avec du blanc (``quantite`` de 0 à 1) : survol/glow léger."""
    return melanger(couleur, "#ffffff", quantite)


def image_lueur_radiale(
    largeur: int,
    hauteur: int,
    couleur_centre: str,
    couleur_bord: str,
    centre_relatif: tuple[float, float] = (0.5, 0.38),
) -> Path:
    """Lueur radiale : ``couleur_centre`` au point ``centre_relatif`` (proportion de la
    largeur/hauteur), qui se fond progressivement en ``couleur_bord`` vers les coins. Pour un
    fond de marque avec un halo de lumière autour d'un élément central (écran de connexion),
    en équivalent statique du « glow » animé de la référence visuelle."""
    DOSSIER_DEGRADES.mkdir(parents=True, exist_ok=True)
    cle = f"{couleur_centre.lstrip('#')}_{couleur_bord.lstrip('#')}_{centre_relatif[0]}_{centre_relatif[1]}"
    chemin = DOSSIER_DEGRADES / f"lueur_{largeur}x{hauteur}_{cle}.png".lower()
    if chemin.is_file():
        return chemin
    y, x = np.mgrid[0:hauteur, 0:largeur]
    cx, cy = centre_relatif[0] * largeur, centre_relatif[1] * hauteur
    distance = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    t = np.clip(distance / distance.max(), 0, 1)[..., None]
    rgb_centre = np.array(_hex_vers_rgb(couleur_centre), dtype=float)
    rgb_bord = np.array(_hex_vers_rgb(couleur_bord), dtype=float)
    pixels = rgb_centre * (1 - t) + rgb_bord * t
    Image.fromarray(pixels.astype("uint8"), "RGB").save(chemin)
    return chemin
