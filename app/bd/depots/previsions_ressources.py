"""Requêtes sur les prévisions de ressources (UC11)."""

from __future__ import annotations

from datetime import date, datetime

from psycopg2.extras import execute_values

from app.bd.depots.base import Depot

COLONNES = """p.id, p.site_id, s.nom AS site, p.zone_id, z.nom AS zone, p.date_jour,
              p.modele_version_id, p.modele_version_equipements_id, p.methode::text AS methode,
              p.volume_prevu::float AS volume_prevu, p.heures::float AS heures, p.effectif,
              p.equipements, p.ic_bas::float AS ic_bas, p.ic_haut::float AS ic_haut,
              p.ic_bas_equipements::float AS ic_bas_equipements,
              p.ic_haut_equipements::float AS ic_haut_equipements, p.date_generation"""
_DE = (
    "FROM previsions_ressources p JOIN sites s ON s.id = p.site_id "
    "JOIN zones z ON z.id = p.zone_id"
)

CHAMPS_INSERTION = [
    "site_id",
    "zone_id",
    "date_jour",
    "modele_version_id",
    "modele_version_equipements_id",
    "methode",
    "volume_prevu",
    "heures",
    "effectif",
    "equipements",
    "ic_bas",
    "ic_haut",
    "ic_bas_equipements",
    "ic_haut_equipements",
    "date_generation",
]


class DepotPrevisionsRessources(Depot):
    """Accès à la table ``previsions_ressources``.

    Chaque génération (UC11) ajoute de nouvelles lignes plutôt que d'écraser les précédentes
    (``date_generation`` fait partie de la clé) : on garde ainsi la trace de l'évolution des
    prévisions, et UC20 pourra comparer le réalisé à la dernière prévision en date.
    """

    def inserer_plusieurs(self, lignes: list[dict]) -> int:
        if not lignes:
            return 0
        valeurs = [tuple(ligne[champ] for champ in CHAMPS_INSERTION) for ligne in lignes]
        execute_values(
            self.cur,
            f"INSERT INTO previsions_ressources ({', '.join(CHAMPS_INSERTION)}) VALUES %s",
            valeurs,
        )
        return len(lignes)

    def dernieres(
        self, site_id: int, zone_id: int | None, debut: date, fin: date, methode: str | None = None
    ) -> list[dict]:
        """La prévision la plus récente pour chaque (zone, date, méthode) de la période."""
        return self._tous(
            f"""SELECT DISTINCT ON (p.zone_id, p.date_jour, p.methode) {COLONNES} {_DE}
                WHERE p.site_id = %s AND (%s::int IS NULL OR p.zone_id = %s)
                  AND p.date_jour BETWEEN %s AND %s AND (%s::text IS NULL OR p.methode = %s)
                ORDER BY p.zone_id, p.date_jour, p.methode, p.date_generation DESC""",
            (site_id, zone_id, zone_id, debut, fin, methode, methode),
        )

    def derniere_ligne(self, site_id: int, zone_id: int, jour: date, methode: str) -> dict | None:
        return self._un(
            f"""SELECT {COLONNES} {_DE}
                WHERE p.site_id = %s AND p.zone_id = %s AND p.date_jour = %s AND p.methode = %s
                ORDER BY p.date_generation DESC LIMIT 1""",
            (site_id, zone_id, jour, methode),
        )

    def derniere_generation(self, site_id: int, zone_id: int | None = None) -> datetime | None:
        ligne = self._un(
            """SELECT max(date_generation) AS derniere FROM previsions_ressources
               WHERE site_id = %s AND (%s::int IS NULL OR zone_id = %s)""",
            (site_id, zone_id, zone_id),
        )
        return ligne["derniere"] if ligne else None
