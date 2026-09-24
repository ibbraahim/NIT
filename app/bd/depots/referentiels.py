"""Requêtes sur les référentiels : sites, zones, équipements, capacités, coûts."""

from __future__ import annotations

from datetime import date

from app.bd.depots.base import Depot


class DepotReferentiels(Depot):
    """Accès aux tables de référence (UC03)."""

    # --- Sites -----------------------------------------------------------
    def lister_sites(
        self, inclure_inactifs: bool = False, ids: list[int] | None = None
    ) -> list[dict]:
        return self._tous(
            """SELECT id, nom, adresse, actif FROM sites
               WHERE (%s OR actif) AND (%s::int[] IS NULL OR id = ANY(%s::int[]))
               ORDER BY nom""",
            (inclure_inactifs, ids, ids),
        )

    def site(self, site_id: int) -> dict | None:
        return self._un("SELECT id, nom, adresse, actif FROM sites WHERE id = %s", (site_id,))

    def site_par_nom(self, nom: str) -> dict | None:
        return self._un(
            "SELECT id, nom, adresse, actif FROM sites WHERE lower(nom) = lower(%s)", (nom.strip(),)
        )

    def creer_site(self, nom: str, adresse: str) -> int:
        return self._un(
            "INSERT INTO sites (nom, adresse) VALUES (%s, %s) RETURNING id", (nom, adresse)
        )["id"]

    def modifier_site(self, site_id: int, nom: str, adresse: str, actif: bool) -> None:
        self._executer(
            "UPDATE sites SET nom = %s, adresse = %s, actif = %s WHERE id = %s",
            (nom, adresse, actif, site_id),
        )

    def desactiver_site(self, site_id: int) -> None:
        self._executer("UPDATE sites SET actif = FALSE WHERE id = %s", (site_id,))
        self._executer("UPDATE zones SET actif = FALSE WHERE site_id = %s", (site_id,))

    # --- Zones -----------------------------------------------------------
    def lister_zones(
        self, site_id: int | None = None, inclure_inactives: bool = False
    ) -> list[dict]:
        return self._tous(
            """SELECT z.id, z.site_id, s.nom AS site, z.nom, z.type_equipement_principal,
                      z.duree_poste_heures::float AS duree_poste_heures, z.actif
               FROM zones z JOIN sites s ON s.id = z.site_id
               WHERE (%s::int IS NULL OR z.site_id = %s) AND (%s OR z.actif)
               ORDER BY s.nom, z.id""",
            (site_id, site_id, inclure_inactives),
        )

    def zone(self, zone_id: int) -> dict | None:
        return self._un(
            """SELECT id, site_id, nom, type_equipement_principal,
                      duree_poste_heures::float AS duree_poste_heures, actif
               FROM zones WHERE id = %s""",
            (zone_id,),
        )

    def zone_par_nom(self, site_id: int, nom: str) -> dict | None:
        return self._un(
            """SELECT id, site_id, nom, duree_poste_heures::float AS duree_poste_heures, actif
               FROM zones WHERE site_id = %s AND lower(nom) = lower(%s)""",
            (site_id, nom.strip()),
        )

    def creer_zone(self, site_id: int, nom: str, type_equipement: str, duree_poste: float) -> int:
        return self._un(
            """INSERT INTO zones (site_id, nom, type_equipement_principal, duree_poste_heures)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (site_id, nom, type_equipement, duree_poste),
        )["id"]

    def modifier_zone(
        self, zone_id: int, nom: str, type_equipement: str, duree_poste: float, actif: bool
    ) -> None:
        self._executer(
            """UPDATE zones SET nom = %s, type_equipement_principal = %s,
                      duree_poste_heures = %s, actif = %s WHERE id = %s""",
            (nom, type_equipement, duree_poste, actif, zone_id),
        )

    def desactiver_zone(self, zone_id: int) -> None:
        self._executer("UPDATE zones SET actif = FALSE WHERE id = %s", (zone_id,))

    # --- Équipements -----------------------------------------------------
    def lister_equipements(
        self, site_id: int | None = None, zone_id: int | None = None, inclure_inactifs: bool = False
    ) -> list[dict]:
        return self._tous(
            """SELECT e.id, e.site_id, s.nom AS site, e.zone_id, z.nom AS zone, e.type, e.code,
                      e.statut::text AS statut, e.actif,
                      (SELECT min(i.date_debut) FROM indisponibilites_equipements i
                        WHERE i.equipement_id = e.id AND i.date_fin >= CURRENT_DATE)
                        AS prochaine_indisponibilite
               FROM equipements e
               JOIN sites s ON s.id = e.site_id JOIN zones z ON z.id = e.zone_id
               WHERE (%s::int IS NULL OR e.site_id = %s) AND (%s::int IS NULL OR e.zone_id = %s)
                 AND (%s OR e.actif)
               ORDER BY s.nom, z.id, e.code""",
            (site_id, site_id, zone_id, zone_id, inclure_inactifs),
        )

    def equipement(self, equipement_id: int) -> dict | None:
        return self._un(
            """SELECT id, site_id, zone_id, type, code, statut::text AS statut, actif
               FROM equipements WHERE id = %s""",
            (equipement_id,),
        )

    def creer_equipement(
        self, site_id: int, zone_id: int, type_eqp: str, code: str, statut: str
    ) -> int:
        return self._un(
            """INSERT INTO equipements (site_id, zone_id, type, code, statut)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (site_id, zone_id, type_eqp, code, statut),
        )["id"]

    def modifier_equipement(
        self, equipement_id: int, zone_id: int, type_eqp: str, code: str, statut: str, actif: bool
    ) -> None:
        self._executer(
            """UPDATE equipements SET zone_id = %s, type = %s, code = %s, statut = %s, actif = %s
               WHERE id = %s""",
            (zone_id, type_eqp, code, statut, actif, equipement_id),
        )

    def desactiver_equipement(self, equipement_id: int) -> None:
        self._executer("UPDATE equipements SET actif = FALSE WHERE id = %s", (equipement_id,))

    def ajouter_indisponibilite(
        self, equipement_id: int, debut: date, fin: date, motif: str
    ) -> int:
        return self._un(
            """INSERT INTO indisponibilites_equipements (equipement_id, date_debut, date_fin, motif)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (equipement_id, debut, fin, motif),
        )["id"]

    def lister_indisponibilites(self, site_id: int, debut: date, fin: date) -> list[dict]:
        return self._tous(
            """SELECT i.id, i.equipement_id, e.code, e.type, e.zone_id, z.nom AS zone,
                      i.date_debut, i.date_fin, i.motif
               FROM indisponibilites_equipements i
               JOIN equipements e ON e.id = i.equipement_id JOIN zones z ON z.id = e.zone_id
               WHERE e.site_id = %s AND i.date_fin >= %s AND i.date_debut <= %s
               ORDER BY i.date_debut, e.code""",
            (site_id, debut, fin),
        )

    def equipements_disponibles(self, site_id: int, debut: date, fin: date) -> list[dict]:
        """Nombre d'équipements disponibles par zone, type et date sur une plage.

        Un équipement est indisponible s'il est inactif, hors service, en
        maintenance (statut courant, appliqué à partir d'aujourd'hui) ou
        couvert par une période d'indisponibilité.
        """
        return self._tous(
            """SELECT z.id AS zone_id, g.jour::date AS date_jour, e.type,
                      count(e.id) FILTER (
                          WHERE e.id IS NOT NULL
                            AND e.statut <> 'hors_service'
                            AND NOT (e.statut = 'maintenance' AND g.jour::date >= CURRENT_DATE)
                            AND NOT EXISTS (
                                SELECT 1 FROM indisponibilites_equipements i
                                WHERE i.equipement_id = e.id
                                  AND g.jour::date BETWEEN i.date_debut AND i.date_fin)
                      ) AS disponibles,
                      count(e.id) AS total
               FROM zones z
               CROSS JOIN generate_series(%s::date, %s::date, interval '1 day') AS g(jour)
               LEFT JOIN equipements e ON e.zone_id = z.id AND e.actif
               WHERE z.site_id = %s AND z.actif
               GROUP BY z.id, g.jour, e.type
               ORDER BY z.id, g.jour""",
            (debut, fin, site_id),
        )

    def zone_utilisee(self, zone_id: int) -> bool:
        ligne = self._un(
            """SELECT EXISTS (SELECT 1 FROM historique_activite WHERE zone_id = %s)
                   OR EXISTS (SELECT 1 FROM equipements WHERE zone_id = %s)
                   OR EXISTS (SELECT 1 FROM previsions_volume WHERE zone_id = %s) AS utilisee""",
            (zone_id, zone_id, zone_id),
        )
        return ligne["utilisee"]

    # --- Capacités de personnel -----------------------------------------
    def capacites(self, site_id: int, debut: date, fin: date) -> list[dict]:
        return self._tous(
            """SELECT zone_id, date_jour, effectif_planifie, absences_prevues
               FROM capacites_personnel
               WHERE site_id = %s AND date_jour BETWEEN %s AND %s
               ORDER BY zone_id, date_jour""",
            (site_id, debut, fin),
        )

    def enregistrer_capacite(
        self, site_id: int, zone_id: int, jour: date, effectif: int, absences: int
    ) -> None:
        self._executer(
            """INSERT INTO capacites_personnel
                   (site_id, zone_id, date_jour, effectif_planifie, absences_prevues)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (site_id, zone_id, date_jour) DO UPDATE
               SET effectif_planifie = EXCLUDED.effectif_planifie,
                   absences_prevues = EXCLUDED.absences_prevues""",
            (site_id, zone_id, jour, effectif, absences),
        )

    # --- Coûts horaires --------------------------------------------------
    def lister_couts(self) -> list[dict]:
        return self._tous(
            """SELECT id, categorie::text AS categorie, taux::float AS taux, devise, date_debut
               FROM couts_horaires ORDER BY categorie, date_debut DESC"""
        )

    def couts_en_vigueur(self, jour: date) -> dict[str, float]:
        """Taux horaire en vigueur à une date, par catégorie."""
        lignes = self._tous(
            """SELECT DISTINCT ON (categorie) categorie::text AS categorie, taux::float AS taux
               FROM couts_horaires WHERE date_debut <= %s
               ORDER BY categorie, date_debut DESC""",
            (jour,),
        )
        return {ligne["categorie"]: ligne["taux"] for ligne in lignes}

    def enregistrer_cout(self, categorie: str, taux: float, devise: str, date_debut: date) -> None:
        self._executer(
            """INSERT INTO couts_horaires (categorie, taux, devise, date_debut)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (categorie, date_debut) DO UPDATE
               SET taux = EXCLUDED.taux, devise = EXCLUDED.devise""",
            (categorie, taux, devise, date_debut),
        )
