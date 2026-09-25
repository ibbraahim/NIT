"""Lecture de fichiers CSV/Excel et écriture de classeurs Excel simples."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.erreurs import DonneesInvalides

EXTENSIONS_PRISES_EN_CHARGE = (".csv", ".xlsx")


def lire_lignes_fichier(chemin: Path) -> list[dict[str, Any]]:
    """Lit un fichier CSV ou Excel : en-têtes en clés (minuscules), une ligne = un dictionnaire.

    Les cellules vides deviennent ``None``. Les colonnes en trop dans une ligne sont ignorées,
    celles manquantes valent ``None``.
    """
    if not chemin.is_file():
        raise DonneesInvalides(f"Le fichier « {chemin.name} » est introuvable.")
    if chemin.suffix.lower() == ".csv":
        lignes = _lire_csv(chemin)
    elif chemin.suffix.lower() == ".xlsx":
        lignes = _lire_xlsx(chemin)
    else:
        raise DonneesInvalides(
            "Format de fichier non pris en charge. Utilisez un fichier CSV ou Excel (.xlsx)."
        )
    if not lignes:
        raise DonneesInvalides("Le fichier ne contient aucune ligne de données.")
    return lignes


def _lire_csv(chemin: Path) -> list[dict[str, Any]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        contenu = fichier.read()
    if not contenu.strip():
        return []
    try:
        dialecte = csv.Sniffer().sniff(contenu.splitlines()[0], delimiters=";,\t")
    except csv.Error:
        dialecte = csv.excel
        dialecte.delimiter = ";"
    lecteur = csv.reader(io.StringIO(contenu), dialecte)
    lignes = [ligne for ligne in lecteur if any(cellule.strip() for cellule in ligne)]
    if not lignes:
        return []
    entetes = [entete.strip().lower() for entete in lignes[0]]
    resultat = []
    for ligne in lignes[1:]:
        valeurs = [cellule.strip() or None for cellule in ligne]
        valeurs += [None] * (len(entetes) - len(valeurs))
        resultat.append(dict(zip(entetes, valeurs, strict=False)))
    return resultat


def _lire_xlsx(chemin: Path) -> list[dict[str, Any]]:
    try:
        classeur = load_workbook(chemin, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - message français, détail au journal
        raise DonneesInvalides(
            "Impossible de lire ce fichier Excel. Vérifiez qu'il n'est pas endommagé."
        ) from exc
    feuille = classeur.worksheets[0]
    lignes_brutes = list(feuille.iter_rows(values_only=True))
    classeur.close()
    lignes_brutes = [ligne for ligne in lignes_brutes if any(c is not None for c in ligne)]
    if not lignes_brutes:
        return []
    entetes = [
        str(entete).strip().lower() if entete is not None else "" for entete in lignes_brutes[0]
    ]
    resultat = []
    for ligne in lignes_brutes[1:]:
        valeurs = list(ligne) + [None] * (len(entetes) - len(ligne))
        valeurs = [v.strip() if isinstance(v, str) and not v.strip() else v for v in valeurs]
        resultat.append(dict(zip(entetes, valeurs, strict=False)))
    return resultat


def ecrire_classeur(chemin: Path, feuilles: dict[str, tuple[list[str], list[list[Any]]]]) -> None:
    """Écrit un classeur Excel : ``{nom_feuille: (en_tetes, lignes)}``."""
    classeur = Workbook()
    classeur.remove(classeur.active)
    for nom, (en_tetes, lignes) in feuilles.items():
        feuille = classeur.create_sheet(nom[:31])
        feuille.append(en_tetes)
        for cellule in feuille[1]:
            cellule.font = Font(bold=True)
        for ligne in lignes:
            feuille.append(ligne)
        for colonne in feuille.columns:
            largeur = max((len(str(c.value)) for c in colonne if c.value is not None), default=10)
            feuille.column_dimensions[colonne[0].column_letter].width = min(largeur + 2, 60)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    classeur.save(chemin)
