"""Requêtes sur la configuration des modèles de prévision (UC07)."""

from __future__ import annotations

from psycopg2.extras import Json

from app.bd.depots.base import Depot


class DepotParametresModele(Depot):
    """Accès à la table ``parametres_modele`` : chaque enregistrement fait foi jusqu'au suivant."""

    def dernier(self) -> dict | None:
        return self._un(
            """SELECT id, configuration, date_enregistrement, auteur_id FROM parametres_modele
               ORDER BY date_enregistrement DESC LIMIT 1"""
        )

    def enregistrer(self, configuration: dict, auteur_id: int | None) -> int:
        return self._un(
            """INSERT INTO parametres_modele (configuration, auteur_id) VALUES (%s, %s)
               RETURNING id""",
            (Json(configuration), auteur_id),
        )["id"]
