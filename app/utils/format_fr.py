"""Formatage à la française, indépendant de la locale du système.

- dates ``JJ/MM/AAAA`` et dates longues (« jeudi 12 mars 2026 ») ;
- nombres avec virgule décimale et espace pour les milliers (``1 250,5``) ;
- pourcentages (``12,3 %``) et montants (``1 250,00 MAD``).
"""

from __future__ import annotations

import math
from datetime import date, datetime

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
MOIS_COURTS = [
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
]

#: Séparateur des milliers : espace (le prompt impose « 1 250,5 »).
SEPARATEUR_MILLIERS = " "
VALEUR_ABSENTE = "—"


def formater_date(valeur: date | datetime | None) -> str:
    """``date(2026, 3, 12)`` → ``"12/03/2026"``."""
    if valeur is None:
        return VALEUR_ABSENTE
    return f"{valeur.day:02d}/{valeur.month:02d}/{valeur.year:04d}"


def formater_date_heure(valeur: datetime | None) -> str:
    """``datetime(2026, 3, 12, 8, 5)`` → ``"12/03/2026 08:05"``."""
    if valeur is None:
        return VALEUR_ABSENTE
    return f"{formater_date(valeur)} {valeur.hour:02d}:{valeur.minute:02d}"


def formater_date_longue(valeur: date | None, avec_jour: bool = True) -> str:
    """``date(2026, 3, 12)`` → ``"jeudi 12 mars 2026"``."""
    if valeur is None:
        return VALEUR_ABSENTE
    jour = "1er" if valeur.day == 1 else str(valeur.day)
    texte = f"{jour} {MOIS[valeur.month - 1]} {valeur.year}"
    return f"{JOURS[valeur.weekday()]} {texte}" if avec_jour else texte


def formater_jour_court(valeur: date) -> str:
    """``date(2026, 3, 12)`` → ``"jeu. 12/03"``."""
    return f"{JOURS_COURTS[valeur.weekday()]} {valeur.day:02d}/{valeur.month:02d}"


def formater_mois(valeur: date) -> str:
    """``date(2026, 3, 1)`` → ``"mars 2026"``."""
    return f"{MOIS[valeur.month - 1]} {valeur.year}"


def lire_date(texte: str) -> date:
    """Convertit ``JJ/MM/AAAA`` (ou ``AAAA-MM-JJ``) en date. Lève ``ValueError`` en français."""
    texte = (texte or "").strip()
    try:
        if "/" in texte:
            jour, mois, annee = (int(p) for p in texte.split("/"))
            return date(annee, mois, jour)
        if "-" in texte:
            return date.fromisoformat(texte[:10])
    except (ValueError, TypeError):
        pass
    raise ValueError(f"Date invalide : « {texte} ». Format attendu : JJ/MM/AAAA.")


def _grouper_milliers(entier: str) -> str:
    signe = ""
    if entier.startswith("-"):
        signe, entier = "-", entier[1:]
    groupes = []
    while len(entier) > 3:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    groupes.insert(0, entier)
    return signe + SEPARATEUR_MILLIERS.join(groupes)


def formater_nombre(
    valeur: float | int | None, decimales: int = 1, supprimer_zeros: bool = False
) -> str:
    """``1250.5`` → ``"1 250,5"`` ; ``None`` ou NaN → ``"—"``.

    Avec ``supprimer_zeros=True``, les zéros décimaux inutiles sont retirés
    (``1250.0`` → ``"1 250"``).
    """
    if valeur is None or (isinstance(valeur, float) and (math.isnan(valeur) or math.isinf(valeur))):
        return VALEUR_ABSENTE
    texte = f"{float(valeur):.{decimales}f}" if decimales > 0 else f"{round(float(valeur)):d}"
    if texte in ("-0", "-0." + "0" * decimales):
        texte = texte[1:]
    entier, _, fraction = texte.partition(".")
    if supprimer_zeros:
        fraction = fraction.rstrip("0")
    resultat = _grouper_milliers(entier)
    return f"{resultat},{fraction}" if fraction else resultat


def formater_entier(valeur: float | int | None) -> str:
    """``12500`` → ``"12 500"``."""
    return formater_nombre(valeur, 0)


def formater_pourcentage(valeur: float | None, decimales: int = 1, signe: bool = False) -> str:
    """``12.345`` → ``"12,3 %"``. La valeur est déjà exprimée en pourcentage."""
    if valeur is None or (isinstance(valeur, float) and math.isnan(valeur)):
        return VALEUR_ABSENTE
    texte = formater_nombre(valeur, decimales)
    if signe and valeur > 0 and not texte.startswith("-"):
        texte = "+" + texte
    return f"{texte} %"


def formater_montant(valeur: float | None, devise: str = "MAD", decimales: int = 2) -> str:
    """``1250.5`` → ``"1 250,50 MAD"``."""
    if valeur is None or (isinstance(valeur, float) and math.isnan(valeur)):
        return VALEUR_ABSENTE
    return f"{formater_nombre(valeur, decimales)} {devise}"


def lire_nombre(texte: str | float | int | None) -> float:
    """Lit un nombre saisi à la française (``"1 250,5"``) ou à l'anglaise (``"1250.5"``).

    Lève ``ValueError`` avec un message français si la saisie n'est pas un nombre.
    """
    if isinstance(texte, (int, float)):
        return float(texte)
    brut = (texte or "").strip()
    nettoye = brut.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(nettoye)
    except ValueError:
        raise ValueError(f"« {brut} » n'est pas un nombre valide.") from None


def formater_booleen(valeur: bool | None) -> str:
    """``True`` → ``"Oui"``."""
    if valeur is None:
        return VALEUR_ABSENTE
    return "Oui" if valeur else "Non"
