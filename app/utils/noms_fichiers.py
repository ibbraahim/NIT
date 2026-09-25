"""Construction de noms de fichiers sûrs (sans accent ni espace) à partir de libellés."""

from __future__ import annotations

import re
import unicodedata


def translitterer(texte: str) -> str:
    """Retire les accents et met en minuscules, sans changer la ponctuation."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    return sans_accents.lower()


def normaliser_segment(texte: str) -> str:
    """Un segment de nom de fichier : lettres/chiffres et tirets, sans accent ni espace."""
    nettoye = re.sub(r"[^a-z0-9]+", "-", translitterer(texte)).strip("-")
    return nettoye or "-"


def nom_fichier(*segments: str) -> str:
    """Assemble des segments en un nom de fichier sûr, séparés par des tirets bas."""
    return "_".join(normaliser_segment(segment) for segment in segments)
