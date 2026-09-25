"""Requêtes sur les versions de modèles de prévision (UC08, UC09, UC10)."""

from __future__ import annotations

from datetime import date, datetime

from psycopg2.extras import Json

from app.bd.depots.base import Depot

COLONNES = """v.id, v.methode::text AS methode, v.site_id, s.nom AS site, v.zone_id,
              z.nom AS zone, v.cible::text AS cible, v.chemin_fichier, v.metriques,
              v.coefficients, v.parametres, v.nb_lignes_apprentissage, v.nb_lignes_test,
              v.date_debut_donnees, v.date_fin_donnees, v.statut::text AS statut, v.actif,
              v.retenue_pour_plan, v.date_entrainement, v.entraine_par"""
_DE = "FROM modeles_versions v JOIN sites s ON s.id = v.site_id JOIN zones z ON z.id = v.zone_id"


class DepotModeles(Depot):
    """Accès à la table ``modeles_versions``."""

    def creer(
        self,
        site_id: int,
        zone_id: int,
        methode: str,
        cible: str,
        chemin_fichier: str,
        metriques: dict,
        coefficients: dict | None,
        parametres: dict,
        nb_lignes_apprentissage: int,
        nb_lignes_test: int,
        date_debut_donnees: date | None,
        date_fin_donnees: date | None,
        statut: str,
        entraine_par: int | None,
    ) -> int:
        return self._un(
            """INSERT INTO modeles_versions
                   (site_id, zone_id, methode, cible, chemin_fichier, metriques, coefficients,
                    parametres, nb_lignes_apprentissage, nb_lignes_test, date_debut_donnees,
                    date_fin_donnees, statut, entraine_par)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                site_id,
                zone_id,
                methode,
                cible,
                chemin_fichier,
                Json(metriques),
                Json(coefficients or {}),
                Json(parametres),
                nb_lignes_apprentissage,
                nb_lignes_test,
                date_debut_donnees,
                date_fin_donnees,
                statut,
                entraine_par,
            ),
        )["id"]

    def version(self, version_id: int) -> dict | None:
        return self._un(f"SELECT {COLONNES} {_DE} WHERE v.id = %s", (version_id,))

    def lister(self, site_id: int, zone_id: int | None = None) -> list[dict]:
        """Versions d'un site (et, facultativement, d'une seule zone), les plus récentes d'abord."""
        return self._tous(
            f"""SELECT {COLONNES} {_DE}
                WHERE v.site_id = %s AND (%s::int IS NULL OR v.zone_id = %s)
                ORDER BY v.date_entrainement DESC""",
            (site_id, zone_id, zone_id),
        )

    def version_active(self, site_id: int, zone_id: int, methode: str, cible: str) -> dict | None:
        return self._un(
            f"""SELECT {COLONNES} {_DE}
                WHERE v.site_id = %s AND v.zone_id = %s AND v.methode = %s AND v.cible = %s
                  AND v.actif""",
            (site_id, zone_id, methode, cible),
        )

    def version_retenue_pour_plan(
        self, site_id: int, zone_id: int, cible: str = "heures"
    ) -> dict | None:
        """Version dont la méthode est retenue pour le plan de charge et la dérive (UC12, UC21)."""
        return self._un(
            f"""SELECT {COLONNES} {_DE}
                WHERE v.site_id = %s AND v.zone_id = %s AND v.cible = %s AND v.retenue_pour_plan""",
            (site_id, zone_id, cible),
        )

    def derniere_version_retenue(
        self, site_id: int, zone_id: int, methode: str, cible: str
    ) -> dict | None:
        """Dernière version entraînée et retenue (candidate pour l'activation, UC10)."""
        return self._un(
            f"""SELECT {COLONNES} {_DE}
                WHERE v.site_id = %s AND v.zone_id = %s AND v.methode = %s AND v.cible = %s
                  AND v.statut = 'retenue'
                ORDER BY v.date_entrainement DESC LIMIT 1""",
            (site_id, zone_id, methode, cible),
        )

    def activer(self, version_id: int) -> None:
        """Active une version : désactive l'ancienne version active de même site/zone/méthode/cible."""
        version = self.version(version_id)
        # La version désactivée perd aussi, le cas échéant, son statut de méthode retenue pour
        # le plan (sans quoi la contrainte « retenue ⇒ actif » serait violée) ; la nouvelle
        # version l'obtient à sa place via ``definir_retenue_pour_plan`` si elle porte sur les
        # heures.
        self._executer(
            """UPDATE modeles_versions SET actif = FALSE, retenue_pour_plan = FALSE
               WHERE site_id = %s AND zone_id = %s AND methode = %s AND cible = %s AND id <> %s""",
            (
                version["site_id"],
                version["zone_id"],
                version["methode"],
                version["cible"],
                version_id,
            ),
        )
        self._executer("UPDATE modeles_versions SET actif = TRUE WHERE id = %s", (version_id,))

    def definir_retenue_pour_plan(self, version_id: int) -> None:
        """Retient la méthode d'une version (cible ``heures``) pour le plan de charge et la dérive."""
        version = self.version(version_id)
        self._executer(
            """UPDATE modeles_versions SET retenue_pour_plan = FALSE
               WHERE site_id = %s AND zone_id = %s AND cible = %s AND id <> %s""",
            (version["site_id"], version["zone_id"], version["cible"], version_id),
        )
        self._executer(
            "UPDATE modeles_versions SET retenue_pour_plan = TRUE WHERE id = %s", (version_id,)
        )

    def marquer_entraine(self, version_id: int, date_entrainement: datetime) -> None:
        """Utilisé par le générateur de démonstration pour dater des entraînements passés."""
        self._executer(
            "UPDATE modeles_versions SET date_entrainement = %s WHERE id = %s",
            (date_entrainement, version_id),
        )
