"""Requêtes sur l'historique d'activité (UC04)."""

from __future__ import annotations

from datetime import date

from psycopg2.extras import execute_values

from app.bd.depots.base import Depot

COLONNES = """h.id, h.site_id, s.nom AS site, h.zone_id, z.nom AS zone, h.date_jour,
              h.volume_traite::float AS volume_traite, h.effectif_present,
              h.heures_travaillees::float AS heures_travaillees,
              h.heures_sup::float AS heures_sup, h.heures_interim::float AS heures_interim,
              h.heures_absence::float AS heures_absence,
              h.heures_inactives::float AS heures_inactives, h.equipements_mobilises,
              h.heures_usage_equipement::float AS heures_usage_equipement,
              h.heures_disponibles_equipement::float AS heures_disponibles_equipement,
              h.heures_panne_equipement::float AS heures_panne_equipement,
              h.cout_rh::float AS cout_rh, h.commandes_a_temps, h.commandes_totales,
              h.indicateur_pic, h.source, h.date_maj"""
_DE = "FROM historique_activite h JOIN sites s ON s.id = h.site_id JOIN zones z ON z.id = h.zone_id"

#: Colonnes de la table dans l'ordre des paramètres de l'upsert.
CHAMPS_UPSERT = [
    "site_id",
    "zone_id",
    "date_jour",
    "volume_traite",
    "effectif_present",
    "heures_travaillees",
    "heures_sup",
    "heures_interim",
    "heures_absence",
    "heures_inactives",
    "equipements_mobilises",
    "heures_usage_equipement",
    "heures_disponibles_equipement",
    "heures_panne_equipement",
    "cout_rh",
    "commandes_a_temps",
    "commandes_totales",
    "indicateur_pic",
    "source",
]


class DepotHistorique(Depot):
    """Accès à la table ``historique_activite``."""

    def lister(
        self, sites: list[int] | None, zone_id: int | None, debut: date, fin: date
    ) -> list[dict]:
        """Historique sur une plage de dates, filtré par sites (``None`` : tous les sites
        visibles) et facultativement par zone."""
        return self._tous(
            f"""SELECT {COLONNES} {_DE}
                WHERE (%s::int[] IS NULL OR h.site_id = ANY(%s::int[]))
                  AND (%s::int IS NULL OR h.zone_id = %s)
                  AND h.date_jour BETWEEN %s AND %s
                ORDER BY h.date_jour DESC, z.id""",
            (sites, sites, zone_id, zone_id, debut, fin),
        )

    def historique_complet(self, site_id: int, zone_id: int) -> list[dict]:
        """Tout l'historique d'une zone, trié par date croissante (entraînement des modèles)."""
        return self._tous(
            f"SELECT {COLONNES} {_DE} WHERE h.site_id = %s AND h.zone_id = %s "
            "ORDER BY h.date_jour ASC",
            (site_id, zone_id),
        )

    def ligne(self, site_id: int, zone_id: int, jour: date) -> dict | None:
        return self._un(
            f"SELECT {COLONNES} {_DE} "
            "WHERE h.site_id = %s AND h.zone_id = %s AND h.date_jour = %s",
            (site_id, zone_id, jour),
        )

    def upsert(self, ligne: dict) -> None:
        """Insère ou met à jour une ligne (``ON CONFLICT (site, zone, date) DO UPDATE``)."""
        self.upsert_plusieurs([ligne])

    def upsert_plusieurs(self, lignes: list[dict]) -> int:
        """Insère ou met à jour plusieurs lignes en une seule requête."""
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
            f"""INSERT INTO historique_activite ({", ".join(CHAMPS_UPSERT)}, date_maj)
                VALUES %s
                ON CONFLICT (site_id, zone_id, date_jour) DO UPDATE SET {maj}, date_maj = now()""",
            valeurs,
            template="(" + ", ".join(["%s"] * len(CHAMPS_UPSERT)) + ", now())",
        )
        return len(lignes)

    def volumes_semaine_precedente(
        self, site_id: int, zone_id: int, jour: date, nb: int = 8
    ) -> list[float]:
        """Volumes traités des ``nb`` occurrences précédentes du même jour de semaine."""
        return [
            l["volume_traite"]
            for l in self._tous(
                """SELECT volume_traite::float AS volume_traite FROM historique_activite
                   WHERE site_id = %s AND zone_id = %s AND date_jour < %s
                     AND EXTRACT(ISODOW FROM date_jour) = EXTRACT(ISODOW FROM %s::date)
                   ORDER BY date_jour DESC LIMIT %s""",
                (site_id, zone_id, jour, jour, nb),
            )
        ]

    def premiere_et_derniere_date(
        self, site_id: int, zone_id: int
    ) -> tuple[date | None, date | None]:
        ligne = self._un(
            "SELECT min(date_jour) AS premiere, max(date_jour) AS derniere "
            "FROM historique_activite WHERE site_id = %s AND zone_id = %s",
            (site_id, zone_id),
        )
        return (ligne["premiere"], ligne["derniere"]) if ligne else (None, None)

    def nb_jours(self, site_id: int, zone_id: int) -> int:
        return self._un(
            "SELECT count(*) AS n FROM historique_activite WHERE site_id = %s AND zone_id = %s",
            (site_id, zone_id),
        )["n"]
