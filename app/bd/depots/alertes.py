"""Requêtes sur les alertes."""

from __future__ import annotations

from app.bd.depots.base import Depot


class DepotAlertes(Depot):
    """Accès à la table ``alertes``."""

    def compter_ouvertes(self, sites: list[int] | None) -> int:
        """Alertes ouvertes ou en cours sur les sites donnés (``None`` : tous)."""
        ligne = self._un(
            """SELECT count(*) AS n FROM alertes
               WHERE statut <> 'resolue' AND (%s::int[] IS NULL OR site_id = ANY(%s::int[]))""",
            (sites, sites),
        )
        return ligne["n"]
