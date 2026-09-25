"""Requêtes sur le rapprochement réel / prévu (UC20) et ses résultats persistés."""

from __future__ import annotations

from datetime import date

from app.bd.depots.base import Depot

COLONNES_RAPPROCHEMENT = """p.id AS prevision_id, p.site_id, p.zone_id, z.nom AS zone,
    p.date_jour, p.methode::text AS methode, p.heures::float AS heures_prevues,
    p.effectif AS effectif_prevu, p.equipements AS equipements_prevus,
    p.ic_bas::float AS ic_bas, p.ic_haut::float AS ic_haut,
    (h.heures_travaillees - h.heures_inactives)::float AS heures_reelles,
    h.equipements_mobilises AS equipements_reels, (h.id IS NOT NULL) AS comparable"""


class DepotComparaisons(Depot):
    """Rapproche les dernières prévisions de ressources à l'historique réel, et persiste le
    résultat dans ``comparaisons_realise``."""

    def rapprochements(
        self, site_id: int, zone_id: int | None, debut: date, fin: date, methode: str | None = None
    ) -> list[dict]:
        """Dernière prévision de chaque (zone, date, méthode) rapprochée au réel, s'il existe."""
        return self._tous(
            f"""SELECT {COLONNES_RAPPROCHEMENT}
                FROM (
                    SELECT DISTINCT ON (zone_id, date_jour, methode) *
                    FROM previsions_ressources
                    WHERE site_id = %s AND (%s::int IS NULL OR zone_id = %s)
                      AND date_jour BETWEEN %s AND %s AND (%s::text IS NULL OR methode = %s)
                    ORDER BY zone_id, date_jour, methode, date_generation DESC
                ) p
                JOIN zones z ON z.id = p.zone_id
                LEFT JOIN historique_activite h
                    ON h.site_id = p.site_id AND h.zone_id = p.zone_id AND h.date_jour = p.date_jour
                ORDER BY p.zone_id, p.date_jour, p.methode""",
            (site_id, zone_id, zone_id, debut, fin, methode, methode),
        )

    def upsert(
        self,
        prevision_id: int,
        heures_reelles: float | None,
        equipements_reels: int | None,
        ecart_absolu: float | None,
        ecart_relatif: float | None,
        ecart_equipements: float | None,
        dans_ic: bool | None,
        comparable: bool,
    ) -> None:
        self._executer(
            """INSERT INTO comparaisons_realise (prevision_id, heures_reelles, equipements_reels,
                   ecart_absolu, ecart_relatif, ecart_equipements, dans_ic, comparable)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (prevision_id) DO UPDATE SET
                   heures_reelles = EXCLUDED.heures_reelles,
                   equipements_reels = EXCLUDED.equipements_reels,
                   ecart_absolu = EXCLUDED.ecart_absolu, ecart_relatif = EXCLUDED.ecart_relatif,
                   ecart_equipements = EXCLUDED.ecart_equipements, dans_ic = EXCLUDED.dans_ic,
                   comparable = EXCLUDED.comparable, date_calcul = now()""",
            (
                prevision_id,
                heures_reelles,
                equipements_reels,
                ecart_absolu,
                ecart_relatif,
                ecart_equipements,
                dans_ic,
                comparable,
            ),
        )
