"""Préférences d'interface de l'utilisateur (thème sombre ou clair), conservées localement.

Elles tiennent dans un petit fichier JSON à la racine du projet, hors base de données :
ce sont des réglages de poste, pas des données métier. Un fichier absent ou illisible
revient simplement aux valeurs par défaut.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app import RACINE


def chemin() -> Path:
    """Fichier de préférences (modifiable par ``WORKLY_PREFERENCES``, utile aux tests)."""
    return Path(os.environ.get("WORKLY_PREFERENCES", RACINE / "preferences.json"))


def lire() -> dict:
    """Préférences enregistrées, ou un dictionnaire vide si le fichier manque ou est invalide."""
    try:
        contenu = json.loads(chemin().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return contenu if isinstance(contenu, dict) else {}


def ecrire(cle: str, valeur) -> None:
    """Enregistre une préférence ; un disque en lecture seule n'empêche pas de travailler."""
    preferences = lire()
    preferences[cle] = valeur
    try:
        chemin().write_text(json.dumps(preferences, indent=2), encoding="utf-8")
    except OSError:
        pass
