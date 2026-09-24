"""Validateurs de saisie réutilisables par les services et les formulaires.

Chaque validateur retourne la valeur convertie ou lève ``ValueError`` avec un
message français prêt à être affiché sous le champ fautif.
"""

from __future__ import annotations

import re
from datetime import date

from app.utils.format_fr import lire_date, lire_nombre

MOTIF_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOTIF_IDENTIFIANT = re.compile(r"^[a-zA-Z0-9._-]{3,50}$")


def obligatoire(valeur: str | None, libelle: str) -> str:
    """Refuse une saisie vide."""
    texte = (valeur or "").strip()
    if not texte:
        raise ValueError(f"Le champ « {libelle} » est obligatoire.")
    return texte


def nombre(
    valeur: str | float | int | None,
    libelle: str,
    minimum: float | None = 0,
    maximum: float | None = None,
    entier: bool = False,
) -> float:
    """Convertit et borne un nombre."""
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        raise ValueError(f"Le champ « {libelle} » est obligatoire.")
    try:
        resultat = lire_nombre(valeur)
    except ValueError:
        raise ValueError(f"« {libelle} » doit être un nombre.") from None
    if entier and resultat != int(resultat):
        raise ValueError(f"« {libelle} » doit être un nombre entier.")
    if minimum is not None and resultat < minimum:
        raise ValueError(
            f"« {libelle} » doit être supérieur ou égal à {minimum:g}.".replace(".", ",")
        )
    if maximum is not None and resultat > maximum:
        raise ValueError(
            f"« {libelle} » doit être inférieur ou égal à {maximum:g}.".replace(".", ",")
        )
    return int(resultat) if entier else resultat


def date_saisie(valeur: str | date | None, libelle: str) -> date:
    """Convertit une date saisie au format JJ/MM/AAAA."""
    if isinstance(valeur, date):
        return valeur
    obligatoire(valeur, libelle)
    try:
        return lire_date(str(valeur))
    except ValueError:
        raise ValueError(f"« {libelle} » : date invalide, format attendu JJ/MM/AAAA.") from None


def email(valeur: str | None, libelle: str = "E-mail") -> str:
    """Valide une adresse e-mail (facultative : vide accepté)."""
    texte = (valeur or "").strip()
    if texte and not MOTIF_EMAIL.match(texte):
        raise ValueError(f"« {libelle} » : adresse e-mail invalide.")
    return texte


def identifiant(valeur: str | None) -> str:
    """Identifiant de connexion : 3 à 50 caractères (lettres, chiffres, . _ -)."""
    texte = obligatoire(valeur, "Identifiant")
    if not MOTIF_IDENTIFIANT.match(texte):
        raise ValueError(
            "L'identifiant doit contenir de 3 à 50 caractères : lettres sans accent, chiffres, "
            "point, tiret ou tiret bas."
        )
    return texte


def mot_de_passe(valeur: str | None) -> str:
    """Mot de passe : au moins 8 caractères, dont une lettre et un chiffre."""
    texte = valeur or ""
    if len(texte) < 8 or not re.search(r"[A-Za-z]", texte) or not re.search(r"\d", texte):
        raise ValueError(
            "Le mot de passe doit contenir au moins 8 caractères, dont une lettre et un chiffre."
        )
    return texte
