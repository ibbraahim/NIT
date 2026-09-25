"""Requêtes sur les prévisions de volume (UC05)."""

from __future__ import annotations

from datetime import date

from psycopg2.extras import execute_values

from app.bd.depots.base import Depot

COLONNES = """p.id, p.site_id, s.nom AS site, p.zone_id, z.nom AS zone, p.date_jour,
              p.volume_prevu::float AS volume_prevu, p.indicateur_pic, p.source, p.date_maj"""
_DE = "FROM previsions_volume p JOIN sites s ON s.id = p.site_id JOIN zones z ON z.id = p.zone_id"

CHAMPS_UPSERT = ["site_id", "zone_id", "date_jour", "volume_prevu", "indicateur_pic", "source"]


class DepotPrevisionsVolume(Depot):
    """Accès à la table ``previsions_volume``."""

    def lister(
        self, sites: list[int] | None, zone_id: int | None, debut: date, fin: date
    ) -> list[dict]:
        """Prévisions sur une plage de dates, filtrées par sites (``None`` : tous les sites
        visibles) et facultativement par zone."""
        return self._tous(
            f"""SELECT {COLONNES} {_DE}
                WHERE (%s::int[] IS NULL OR p.site_id = ANY(%s::int[]))
                  AND (%s::int IS NULL OR p.zone_id = %s)
                  AND p.date_jour BETWEEN %s AND %s
                ORDER BY p.date_jour, z.id""",
            (sites, sites, zone_id, zone_id, debut, fin),
        )

    def ligne(self, site_id: int, zone_id: int, jour: date) -> dict | None:
        return self._un(
            f"SELECT {COLONNES} {_DE} "
            "WHERE p.site_id = %s AND p.zone_id = %s AND p.date_jour = %s",
            (site_id, zone_id, jour),
        )

    def upsert(self, ligne: dict) -> None:
        self.upsert_plusieurs([ligne])

    def upsert_plusieurs(self, lignes: list[dict]) -> int:
        if not lignes:
            return 0
        valeurs = [tuple(ligne[champ] for champ in CHAMPS_UPSERT) for ligne in lignes]
        maj = ", ".join(
            f"{c} = EXCLUDED.{c}"
            for c in CHAMPS_UPSERT
            if c not in ("site_id", "zone_id", "date_jour")
        )
        execute_values(
            self.cur,
            f"""INSERT INTO previsions_volume ({", ".join(CHAMPS_UPSERT)}, date_maj)
                VALUES %s
                ON CONFLICT (site_id, zone_id, date_jour) DO UPDATE SET {maj}, date_maj = now()""",
            valeurs,
            template="(" + ", ".join(["%s"] * len(CHAMPS_UPSERT)) + ", now())",
        )
        return len(lignes)
