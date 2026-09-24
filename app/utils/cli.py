"""Analyseur de ligne de commande entièrement en français."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

_TRADUCTIONS = {
    "usage: ": "utilisation : ",
    "options:": "options :",
    "positional arguments:": "arguments :",
    "show this help message and exit": "affiche cette aide et quitte",
}


class AnalyseurFrancais(argparse.ArgumentParser):
    """``ArgumentParser`` dont l'aide et les erreurs sont en français."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)
        self.add_argument("-h", "--aide", action="help", help="affiche cette aide et quitte")

    @staticmethod
    def _traduire(texte: str) -> str:
        for anglais, francais in _TRADUCTIONS.items():
            texte = texte.replace(anglais, francais)
        return texte

    def format_usage(self) -> str:
        return self._traduire(super().format_usage())

    def format_help(self) -> str:
        return self._traduire(super().format_help())

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, "Erreur : arguments invalides. Utilisez --aide pour afficher l'aide.\n")
