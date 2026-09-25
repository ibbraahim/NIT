"""Requêtes sur les rapports générés (UC23, UC24)."""

from __future__ import annotations

import json
from datetime import date

from psycopg2.extras import Json

from app.bd.depots.base import Depot

COLONNES = """r.id, r.periodicite::text AS periodicite, r.date_debut, r.date_fin, r.site_id,
             s.nom AS site, r.format::text AS format, r.chemin_pdf, r.chemin_excel, r.contenu,
             r.genere_par, u.identifiant AS genere_par_identifiant, r.genere_par_systeme,
             r.date_generation"""
_DE = """FROM rapports r JOIN sites s ON s.id = r.site_id
         LEFT JOIN utilisateurs u ON u.id = r.genere_par"""


class DepotRapports(Depot):
    """Accès à la table ``rapports``."""

    def creer(
        self,
        periodicite: str,
        date_debut: date,
        date_fin: date,
        site_id: int,
        format_rapport: str,
        chemin_pdf: str | None,
        chemin_excel: str | None,
        contenu: dict,
        genere_par: int | None,
        genere_par_systeme: bool,
    ) -> int:
        return self._un(
            """INSERT INTO rapports (periodicite, date_debut, date_fin, site_id, format,
                   chemin_pdf, chemin_excel, contenu, genere_par, genere_par_systeme)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                periodicite,
                date_debut,
                date_fin,
                site_id,
                format_rapport,
                chemin_pdf,
                chemin_excel,
                Json(contenu, dumps=lambda obj: json.dumps(obj, default=str)),
                genere_par,
                genere_par_systeme,
            ),
        )["id"]

    def rapport(self, rapport_id: int) -> dict | None:
        return self._un(f"SELECT {COLONNES} {_DE} WHERE r.id = %s", (rapport_id,))

    def lister(self, site_id: int, periodicite: str | None = None) -> list[dict]:
        return self._tous(
            f"""SELECT {COLONNES} {_DE}
                WHERE r.site_id = %s AND (%s::text IS NULL OR r.periodicite = %s)
                ORDER BY r.date_debut DESC, r.date_generation DESC""",
            (site_id, periodicite, periodicite),
        )
