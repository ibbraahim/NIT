"""Classe de base des dépôts."""

from __future__ import annotations

from typing import Any


class Depot:
    """Dépôt SQL travaillant sur le curseur d'une transaction existante."""

    def __init__(self, curseur: Any) -> None:
        self.cur = curseur

    def _un(self, requete: str, parametres: tuple | dict = ()) -> dict | None:
        self.cur.execute(requete, parametres)
        ligne = self.cur.fetchone()
        return dict(ligne) if ligne else None

    def _tous(self, requete: str, parametres: tuple | dict = ()) -> list[dict]:
        self.cur.execute(requete, parametres)
        return [dict(ligne) for ligne in self.cur.fetchall()]

    def _executer(self, requete: str, parametres: tuple | dict = ()) -> int:
        self.cur.execute(requete, parametres)
        return self.cur.rowcount
