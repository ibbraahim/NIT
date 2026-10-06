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

    def dernieres_executions(self) -> list[dict]:
        """Dernière exécution de chaque tâche (une ligne par tâche)."""
        return self._tous(
            f"""SELECT DISTINCT ON (tache) {COLONNES} FROM journal_taches
                ORDER BY tache, debut DESC"""
        )

    def echecs_depuis(self, jours: int, limite: int = 50) -> list[dict]:
        """Exécutions en échec des ``jours`` derniers jours, de la plus récente à la plus ancienne."""
        return self._tous(
            f"""SELECT {COLONNES} FROM journal_taches
                WHERE statut = 'echec' AND debut >= now() - make_interval(days => %s)
                ORDER BY debut DESC LIMIT %s""",
            (jours, limite),
        )

    def succes_depuis(self, heures: int) -> list[str]:
        """Noms des tâches réussies pendant les ``heures`` dernières heures."""
        lignes = self._tous(
            """SELECT DISTINCT tache FROM journal_taches
               WHERE statut = 'succes' AND debut >= now() - make_interval(hours => %s)""",
            (heures,),
        )
        return [ligne["tache"] for ligne in lignes]
