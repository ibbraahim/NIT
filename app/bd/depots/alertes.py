"""Requêtes sur les alertes."""

from __future__ import annotations

from datetime import date

from app.bd.depots.base import Depot

COLONNES = """a.id, a.type::text AS type, a.niveau::text AS niveau, a.kpi_id, a.site_id,
             a.zone_id, z.nom AS zone, a.date_concernee, a.message, a.statut::text AS statut,
             a.nb_occurrences, a.date_creation, a.date_maj"""
_DE = "FROM alertes a LEFT JOIN zones z ON z.id = a.zone_id"


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

    def emettre(
        self,
        type_alerte: str,
        niveau: str,
        kpi_id: int | None,
        site_id: int,
        zone_id: int | None,
        date_concernee: date,
        cle_deduplication: str,
        message: str,
    ) -> int:
        """Crée l'alerte, ou l'actualise (niveau, date, message, occurrences) si une alerte
        identique est déjà ouverte ou en cours (déduplication par ``cle_deduplication``,
        UC18/UC21)."""
        return self._un(
            """INSERT INTO alertes (type, niveau, kpi_id, site_id, zone_id, date_concernee,
                   cle_deduplication, message)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (cle_deduplication) WHERE statut <> 'resolue' DO UPDATE SET
                   niveau = EXCLUDED.niveau, date_concernee = EXCLUDED.date_concernee,
                   message = EXCLUDED.message, nb_occurrences = alertes.nb_occurrences + 1,
                   date_maj = now()
               RETURNING id""",
            (
                type_alerte,
                niveau,
                kpi_id,
                site_id,
                zone_id,
                date_concernee,
                cle_deduplication,
                message,
            ),
        )["id"]

    def ouvertes(self, site_id: int, type_alerte: str | None = None) -> list[dict]:
        """Alertes ouvertes ou en cours d'un site, les plus critiques et récentes d'abord."""
        return self._tous(
            f"""SELECT {COLONNES} {_DE}
                WHERE a.site_id = %s AND a.statut <> 'resolue'
                  AND (%s::text IS NULL OR a.type = %s)
                ORDER BY (a.niveau = 'rouge') DESC, a.date_maj DESC""",
            (site_id, type_alerte, type_alerte),
        )

    def lister(
        self, site_id: int, statut: str | None = None, type_alerte: str | None = None
    ) -> list[dict]:
        """Toutes les alertes d'un site (écran Alertes, UC19), y compris résolues."""
        return self._tous(
            f"""SELECT {COLONNES}, a.assigne_a, a.pris_en_charge_par, a.resolu_par,
                       a.action_menee, a.date_prise_en_charge, a.date_resolution
                {_DE}
                WHERE a.site_id = %s AND (%s::text IS NULL OR a.statut = %s)
                  AND (%s::text IS NULL OR a.type = %s)
                ORDER BY (a.statut <> 'resolue') DESC, (a.niveau = 'rouge') DESC, a.date_maj DESC""",
            (site_id, statut, statut, type_alerte, type_alerte),
        )

    def alerte(self, alerte_id: int) -> dict | None:
        return self._un(
            f"""SELECT {COLONNES}, a.assigne_a, a.pris_en_charge_par, a.resolu_par,
                       a.action_menee, a.date_prise_en_charge, a.date_resolution
                {_DE} WHERE a.id = %s""",
            (alerte_id,),
        )

    def prendre_en_charge(self, alerte_id: int, utilisateur_id: int | None) -> None:
        self._executer(
            """UPDATE alertes SET statut = 'en_cours', assigne_a = %s, pris_en_charge_par = %s,
                   date_prise_en_charge = now(), date_maj = now()
               WHERE id = %s""",
            (utilisateur_id, utilisateur_id, alerte_id),
        )

    def resoudre(self, alerte_id: int, utilisateur_id: int | None, action_menee: str) -> None:
        self._executer(
            """UPDATE alertes SET statut = 'resolue', resolu_par = %s, action_menee = %s,
                   date_resolution = now(), date_maj = now()
               WHERE id = %s""",
            (utilisateur_id, action_menee, alerte_id),
        )
