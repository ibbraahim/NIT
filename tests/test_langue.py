"""Test de langue : 100 % français.

- Aucun identifiant Python (fonction, classe, variable, paramètre, attribut) n'est accentué
  (règle du projet : snake_case, sans accent).
- Aucun texte d'interface (``text=...``) n'est un mot anglais isolé resté en place.
- ``tkinter.messagebox`` (boutons dans la langue du système) n'est jamais utilisé : les
  boîtes de dialogue passent par ``app.gui.widgets.dialogues``, entièrement en français.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app import RACINE

MOTIF_ACCENT = re.compile(r"[À-ÿ]")
MOTIF_TEXTE = re.compile(r'text\s*=\s*"([^"]+)"')

MOTS_ANGLAIS_INTERDITS = {
    "cancel",
    "ok",
    "save",
    "delete",
    "error",
    "warning",
    "yes",
    "no",
    "close",
    "edit",
    "add",
    "remove",
    "confirm",
    "submit",
    "loading",
    "please wait",
    "help",
}


def _fichiers_python(dossier: Path) -> list[Path]:
    return [f for f in dossier.rglob("*.py") if "__pycache__" not in f.parts]


def test_identifiants_sans_accent():
    """Aucun identifiant Python n'est accentué (fonctions, classes, variables, paramètres,
    attributs) — seuls les textes destinés à l'utilisateur (chaînes) portent des accents."""
    fautifs = []
    for fichier in _fichiers_python(RACINE / "app"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            noms = []
            if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                noms.append(noeud.name)
            elif isinstance(noeud, ast.Name):
                noms.append(noeud.id)
            elif isinstance(noeud, ast.arg):
                noms.append(noeud.arg)
            elif isinstance(noeud, ast.Attribute):
                noms.append(noeud.attr)
            for nom in noms:
                if MOTIF_ACCENT.search(nom):
                    fautifs.append(f"{fichier.relative_to(RACINE)} : « {nom} »")
    assert not fautifs, "Identifiants accentués trouvés :\n" + "\n".join(fautifs)


def test_aucun_texte_d_interface_reste_en_anglais():
    """Les chaînes passées à ``text=`` dans les écrans ne sont pas des mots anglais isolés
    (« Cancel », « OK », « Save »…)."""
    fautifs = []
    for fichier in _fichiers_python(RACINE / "app" / "gui"):
        contenu = fichier.read_text(encoding="utf-8")
        for correspondance in MOTIF_TEXTE.finditer(contenu):
            texte = correspondance.group(1).strip().lower()
            if texte in MOTS_ANGLAIS_INTERDITS:
                fautifs.append(f"{fichier.relative_to(RACINE)} : « {correspondance.group(1)} »")
    assert not fautifs, "Texte d'interface resté en anglais :\n" + "\n".join(fautifs)


def test_aucune_boite_de_dialogue_tkinter_standard():
    """``tkinter.messagebox`` et ``tkinter.simpledialog`` suivent la langue du système : les
    écrans doivent utiliser ``app.gui.widgets.dialogues`` à la place."""
    fautifs = []
    for fichier in _fichiers_python(RACINE / "app" / "gui"):
        if fichier.name == "dialogues.py":
            continue  # le module qui les remplace peut les citer en commentaire
        contenu = fichier.read_text(encoding="utf-8")
        if re.search(r"\b(messagebox|simpledialog)\b", contenu):
            fautifs.append(str(fichier.relative_to(RACINE)))
    assert not fautifs, "Boîtes de dialogue Tk standard (langue du système) :\n" + "\n".join(
        fautifs
    )
