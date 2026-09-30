"""Petites icônes générées et mises en cache (PIL), pour les endroits où Tkinter n'a pas
d'équivalent natif (icône « œil » du champ mot de passe)."""

from __future__ import annotations

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
