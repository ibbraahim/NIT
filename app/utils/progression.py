"""Suivi d'avancement et annulation des traitements longs (sans dépendance à Tkinter)."""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.erreurs import OperationAnnulee


class Progression:
    """Transmet l'avancement d'un traitement et porte la demande d'annulation."""

    def __init__(self, rappel: Callable[[float | None, str], None] | None = None) -> None:
        self._rappel = rappel
        self.annulation = threading.Event()

    def signaler(self, fraction: float | None, texte: str = "") -> None:
        """Signale l'avancement (``fraction`` entre 0 et 1, ou ``None`` si inconnu)."""
        if self._rappel is not None:
            self._rappel(fraction, texte)

    def annuler(self) -> None:
        """Demande l'arrêt du traitement."""
        self.annulation.set()

    @property
    def est_annulee(self) -> bool:
        return self.annulation.is_set()

    def verifier(self) -> None:
        """Lève :class:`OperationAnnulee` si l'annulation a été demandée."""
        if self.annulation.is_set():
            raise OperationAnnulee()


def signaler(progression: Progression | None, fraction: float | None, texte: str = "") -> None:
    """Raccourci tolérant ``progression=None`` ; vérifie aussi l'annulation."""
    if progression is not None:
        progression.verifier()
        progression.signaler(fraction, texte)
