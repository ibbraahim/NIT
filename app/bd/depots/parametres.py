"""Paramètres généraux de l'application (clé / valeur)."""

from __future__ import annotations

from app.bd.depots.base import Depot


class DepotParametres(Depot):
    """Accès à ``parametres_application``."""

    def lire(self, cle: str, defaut: str | None = None) -> str | None:
        ligne = self._un("SELECT valeur FROM parametres_application WHERE cle = %s", (cle,))
        return ligne["valeur"] if ligne else defaut

    def ecrire(self, cle: str, valeur: str) -> None:
        self._executer(
            """INSERT INTO parametres_application (cle, valeur) VALUES (%s, %s)
               ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur""",
            (cle, valeur),
        )
