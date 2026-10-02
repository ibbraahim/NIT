"""Requêtes du « bottom line » : jours comparables, alertes et tâches automatiques d'une période."""

from __future__ import annotations

from datetime import date

from app.bd.depots.base import Depot


class DepotBottomLine(Depot):
    """Lectures agrégées servant à chiffrer l'apport de l'application (aucune écriture)."""

    def jours_comparables(
        self, site_id: int, zone_id: int | None, debut: date, fin: date
    ) -> list[dict]:
        """Jours (zone, date) pour lesquels on connaît à la fois le réel, la prévision de la
        méthode retenue pour le plan (à défaut, la régression linéaire) et le réel du même
        jour de la semaine précédente (planning reconduit, scénario « sans Workly »)."""
        return self._tous(
            """WITH prevision AS (
                   SELECT DISTINCT ON (p.zone_id, p.date_jour) p.zone_id, p.date_jour,
                          p.heures::float AS heures_prevues
                   FROM previsions_ressources p
                   LEFT JOIN modeles_versions m
                       ON m.site_id = p.site_id AND m.zone_id = p.zone_id
                          AND m.cible = 'heures' AND m.retenue_pour_plan
                   WHERE p.site_id = %s AND (%s::int IS NULL OR p.zone_id = %s)
                     AND p.date_jour BETWEEN %s AND %s
                     AND p.methode = COALESCE(m.methode, 'regression_lineaire')
                   ORDER BY p.zone_id, p.date_jour, p.date_generation DESC
               )
               SELECT h.zone_id, z.nom AS zone, h.date_jour,
                      z.duree_poste_heures::float AS duree_poste,
                      (h.heures_travaillees - h.heures_inactives)::float AS besoin,
                      pr.heures_prevues AS plan_workly,
                      (h7.heures_travaillees - h7.heures_inactives)::float AS plan_reconduit,
                      h.commandes_totales, h.commandes_a_temps
               FROM historique_activite h
               JOIN zones z ON z.id = h.zone_id
               JOIN prevision pr ON pr.zone_id = h.zone_id AND pr.date_jour = h.date_jour
               JOIN historique_activite h7
                   ON h7.site_id = h.site_id AND h7.zone_id = h.zone_id
                      AND h7.date_jour = h.date_jour - 7
               WHERE h.site_id = %s AND (%s::int IS NULL OR h.zone_id = %s)
                 AND h.date_jour BETWEEN %s AND %s
               ORDER BY h.date_jour, h.zone_id""",
            (site_id, zone_id, zone_id, debut, fin, site_id, zone_id, zone_id, debut, fin),
        )

    def nb_jours_historique(self, site_id: int, zone_id: int | None, debut: date, fin: date) -> int:
        """Nombre de jours (zone, date) avec un historique réel sur la période."""
        return self._un(
            """SELECT count(*) AS n FROM historique_activite
               WHERE site_id = %s AND (%s::int IS NULL OR zone_id = %s)
                 AND date_jour BETWEEN %s AND %s""",
            (site_id, zone_id, zone_id, debut, fin),
        )["n"]

    def alertes_periode(
        self, site_id: int, zone_id: int | None, debut: date, fin: date
    ) -> list[dict]:
        """Alertes créées sur la période, avec leurs dates de traitement."""
        return self._tous(
            """SELECT type::text AS type, niveau::text AS niveau, statut::text AS statut,
                      zone_id, date_concernee, date_creation, date_prise_en_charge,
                      date_resolution
               FROM alertes
               WHERE site_id = %s AND (%s::int IS NULL OR zone_id = %s)
                 AND date_creation::date BETWEEN %s AND %s""",
            (site_id, zone_id, zone_id, debut, fin),
        )

    def taches_periode(self, debut: date, fin: date) -> list[dict]:
        """Exécutions de tâches automatiques terminées ou en cours sur la période."""
        return self._tous(
            """SELECT tache, statut::text AS statut,
                      EXTRACT(EPOCH FROM (fin - debut))::float AS duree_s
               FROM journal_taches WHERE debut::date BETWEEN %s AND %s""",
            (debut, fin),
        )
