"""Requêtes sur le catalogue des KPI, les objectifs et les valeurs calculées (UC15, UC16, UC17)."""

from __future__ import annotations

from datetime import date

from app.bd.depots.base import Depot

COLONNES_DEFINITION = """id, code, libelle, famille::text AS famille, formule, unite,
                         sens::text AS sens, par_methode, ordre"""

COLONNES_OBJECTIF = """o.id, o.kpi_id, k.code AS kpi_code, o.site_id, s.nom AS site, o.zone_id,
                       z.nom AS zone, o.periodicite::text AS periodicite, o.sens::text AS sens,
                       o.valeur_cible::float AS valeur_cible, o.seuil_orange::float AS seuil_orange,
                       o.seuil_rouge::float AS seuil_rouge, o.valeur_min::float AS valeur_min,
                       o.valeur_max::float AS valeur_max, o.seuils_relatifs,
                       o.date_debut_validite, o.date_fin_validite"""
_DE_OBJECTIF = (
    "FROM objectifs_kpi o JOIN kpi_definitions k ON k.id = o.kpi_id "
    "LEFT JOIN sites s ON s.id = o.site_id LEFT JOIN zones z ON z.id = o.zone_id"
)

COLONNES_VALEUR = """v.id, v.kpi_id, k.code AS kpi_code, k.libelle AS kpi_libelle,
                     k.famille::text AS famille, k.sens::text AS sens, k.unite,
                     v.site_id, v.zone_id, z.nom AS zone, v.periodicite::text AS periodicite,
                     v.date_debut_periode, v.methode::text AS methode,
                     v.valeur::float AS valeur, v.cible::float AS cible,
                     v.statut::text AS statut, v.date_calcul"""
_DE_VALEUR = (
    "FROM kpi_valeurs v JOIN kpi_definitions k ON k.id = v.kpi_id "
    "LEFT JOIN zones z ON z.id = v.zone_id"
)


class DepotKpi(Depot):
    """Accès à ``kpi_definitions``, ``objectifs_kpi`` et ``kpi_valeurs``."""

    # --- Catalogue -----------------------------------------------------
    def definitions(self) -> list[dict]:
        return self._tous(f"SELECT {COLONNES_DEFINITION} FROM kpi_definitions ORDER BY ordre")

    def definition(self, kpi_id: int) -> dict | None:
        return self._un(
            f"SELECT {COLONNES_DEFINITION} FROM kpi_definitions WHERE id = %s", (kpi_id,)
        )

    def definition_par_code(self, code: str) -> dict | None:
        return self._un(
            f"SELECT {COLONNES_DEFINITION} FROM kpi_definitions WHERE code = %s", (code,)
        )

    # --- Objectifs (UC15) ------------------------------------------------
    def objectifs(self, site_id: int | None = None) -> list[dict]:
        """Tous les objectifs (``site_id`` filtre : ceux de ce site et les objectifs généraux)."""
        return self._tous(
            f"""SELECT {COLONNES_OBJECTIF} {_DE_OBJECTIF}
                WHERE %s::int IS NULL OR o.site_id = %s OR o.site_id IS NULL
                ORDER BY k.ordre, o.site_id NULLS FIRST, o.zone_id NULLS FIRST, o.periodicite""",
            (site_id, site_id),
        )

    def objectif(self, objectif_id: int) -> dict | None:
        return self._un(
            f"SELECT {COLONNES_OBJECTIF} {_DE_OBJECTIF} WHERE o.id = %s", (objectif_id,)
        )

    def objectif_applicable(
        self, kpi_id: int, site_id: int, zone_id: int | None, periodicite: str, jour: date
    ) -> dict | None:
        """L'objectif en vigueur, par priorité décroissante : site+zone > site > général."""
        return self._un(
            f"""SELECT {COLONNES_OBJECTIF} {_DE_OBJECTIF}
                WHERE o.kpi_id = %s AND o.periodicite = %s
                  AND (o.site_id = %s OR o.site_id IS NULL)
                  AND (o.zone_id = %s OR o.zone_id IS NULL)
                  AND o.date_debut_validite <= %s
                  AND (o.date_fin_validite IS NULL OR o.date_fin_validite >= %s)
                ORDER BY o.site_id IS NULL, o.zone_id IS NULL, o.date_debut_validite DESC
                LIMIT 1""",
            (kpi_id, periodicite, site_id, zone_id, jour, jour),
        )

    def creer_objectif(
        self,
        kpi_id: int,
        site_id: int | None,
        zone_id: int | None,
        periodicite: str,
        sens: str,
        valeur_cible: float | None,
        seuil_orange: float | None,
        seuil_rouge: float | None,
        valeur_min: float | None,
        valeur_max: float | None,
        seuils_relatifs: bool,
        date_debut: date,
    ) -> int:
        return self._un(
            """INSERT INTO objectifs_kpi (kpi_id, site_id, zone_id, periodicite, sens,
                   valeur_cible, seuil_orange, seuil_rouge, valeur_min, valeur_max,
                   seuils_relatifs, date_debut_validite)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                kpi_id,
                site_id,
                zone_id,
                periodicite,
                sens,
                valeur_cible,
                seuil_orange,
                seuil_rouge,
                valeur_min,
                valeur_max,
                seuils_relatifs,
                date_debut,
            ),
        )["id"]

    def modifier_objectif(
        self,
        objectif_id: int,
        valeur_cible: float | None,
        seuil_orange: float | None,
        seuil_rouge: float | None,
        valeur_min: float | None,
        valeur_max: float | None,
    ) -> None:
        self._executer(
            """UPDATE objectifs_kpi SET valeur_cible = %s, seuil_orange = %s, seuil_rouge = %s,
                      valeur_min = %s, valeur_max = %s
               WHERE id = %s""",
            (valeur_cible, seuil_orange, seuil_rouge, valeur_min, valeur_max, objectif_id),
        )

    def supprimer_objectif(self, objectif_id: int) -> None:
        self._executer("DELETE FROM objectifs_kpi WHERE id = %s", (objectif_id,))

    # --- Valeurs calculées (UC16, UC17) -----------------------------------
    def upsert_valeur(
        self,
        kpi_id: int,
        site_id: int,
        zone_id: int | None,
        periodicite: str,
        date_debut_periode: date,
        methode: str | None,
        valeur: float | None,
        cible: float | None,
        statut: str,
    ) -> int:
        return self._un(
            """INSERT INTO kpi_valeurs (kpi_id, site_id, zone_id, periodicite,
                   date_debut_periode, methode, valeur, cible, statut)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (kpi_id, site_id, zone_id, periodicite, date_debut_periode, methode)
               DO UPDATE SET valeur = EXCLUDED.valeur, cible = EXCLUDED.cible,
                             statut = EXCLUDED.statut, date_calcul = now()
               RETURNING id""",
            (
                kpi_id,
                site_id,
                zone_id,
                periodicite,
                date_debut_periode,
                methode,
                valeur,
                cible,
                statut,
            ),
        )["id"]

    def valeurs(
        self,
        site_id: int,
        zone_id: int | None,
        periodicite: str,
        date_debut_periode: date,
    ) -> list[dict]:
        return self._tous(
            f"""SELECT {COLONNES_VALEUR} {_DE_VALEUR}
                WHERE v.site_id = %s AND (%s::int IS NULL OR v.zone_id = %s)
                  AND v.periodicite = %s AND v.date_debut_periode = %s
                ORDER BY k.ordre, v.methode""",
            (site_id, zone_id, zone_id, periodicite, date_debut_periode),
        )

    def historique_valeur(
        self,
        kpi_id: int,
        site_id: int,
        zone_id: int | None,
        periodicite: str,
        methode: str | None,
        nb_periodes: int = 2,
    ) -> list[dict]:
        """Les ``nb_periodes`` dernières valeurs (pour la tendance ↑ ↓ →)."""
        return self._tous(
            f"""SELECT {COLONNES_VALEUR} {_DE_VALEUR}
                WHERE v.kpi_id = %s AND v.site_id = %s
                  AND (%s::int IS NULL OR v.zone_id = %s) AND v.periodicite = %s
                  AND (%s::text IS NULL OR v.methode = %s)
                ORDER BY v.date_debut_periode DESC LIMIT %s""",
            (kpi_id, site_id, zone_id, zone_id, periodicite, methode, methode, nb_periodes),
        )
