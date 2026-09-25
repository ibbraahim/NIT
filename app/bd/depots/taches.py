"""Requêtes sur le journal des tâches automatiques (``journal_taches``)."""

from __future__ import annotations

from app.bd.depots.base import Depot

COLONNES = "id, tache, debut, fin, statut::text AS statut, message"


class DepotTaches(Depot):
    """Accès à la table ``journal_taches``."""

    def demarrer(self, tache: str) -> int:
        return self._un("INSERT INTO journal_taches (tache) VALUES (%s) RETURNING id", (tache,))[
            "id"
        ]

    def terminer(self, tache_id: int, statut: str, message: str) -> None:
        self._executer(
            "UPDATE journal_taches SET fin = now(), statut = %s, message = %s WHERE id = %s",
            (statut, message[:4000], tache_id),
        )

    def journal(self, limite: int = 100) -> list[dict]:
        return self._tous(
            f"SELECT {COLONNES} FROM journal_taches ORDER BY debut DESC LIMIT %s", (limite,)
        )

    def derniere_execution(self, tache: str) -> dict | None:
        return self._un(
            f"""SELECT {COLONNES} FROM journal_taches WHERE tache = %s
                ORDER BY debut DESC LIMIT 1""",
            (tache,),
        )
