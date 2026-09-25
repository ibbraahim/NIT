"""Requêtes sur les plans de charge (UC12, UC13, UC14)."""

from __future__ import annotations

from datetime import date

from psycopg2.extras import Json, execute_values

from app.bd.depots.base import Depot

COLONNES_PLAN = """p.id, p.site_id, s.nom AS site, p.semaine, p.statut::text AS statut,
                   p.commentaire, p.methode::text AS methode, p.cree_par, p.soumis_par,
                   p.valide_par, p.date_creation, p.date_maj, p.date_soumission,
                   p.date_validation"""
_DE_PLAN = "FROM plans_charge p JOIN sites s ON s.id = p.site_id"

COLONNES_LIGNE = """l.id, l.plan_id, l.zone_id, z.nom AS zone, l.date_jour,
                    l.besoin_heures::float AS besoin_heures, l.besoin_effectif,
                    l.besoin_equipements, l.effectif_planifie, l.interim_planifie,
                    l.equipements_planifies, l.capacite_effectif, l.capacite_equipements,
                    l.commentaire"""

CHAMPS_LIGNE = [
    "zone_id",
    "date_jour",
    "besoin_heures",
    "besoin_effectif",
    "besoin_equipements",
    "effectif_planifie",
    "interim_planifie",
    "equipements_planifies",
    "capacite_effectif",
    "capacite_equipements",
    "commentaire",
]


class DepotPlansCharge(Depot):
    """Accès aux tables ``plans_charge`` et ``plans_charge_lignes``."""

    # --- Plan --------------------------------------------------------------
    def plan_semaine(self, site_id: int, semaine: date) -> dict | None:
        return self._un(
            f"SELECT {COLONNES_PLAN} {_DE_PLAN} WHERE p.site_id = %s AND p.semaine = %s",
            (site_id, semaine),
        )

    def plan(self, plan_id: int) -> dict | None:
        return self._un(f"SELECT {COLONNES_PLAN} {_DE_PLAN} WHERE p.id = %s", (plan_id,))

    def creer_plan(
        self, site_id: int, semaine: date, methode: str | None, cree_par: int | None
    ) -> int:
        return self._un(
            """INSERT INTO plans_charge (site_id, semaine, methode, cree_par)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (site_id, semaine, methode, cree_par),
        )["id"]

    def mettre_a_jour_plan(self, plan_id: int, **champs) -> None:
        """Met à jour des colonnes de ``plans_charge`` (``statut``, ``commentaire``, dates…)."""
        colonnes = ", ".join(f"{c} = %s" for c in champs)
        self._executer(
            f"UPDATE plans_charge SET {colonnes}, date_maj = now() WHERE id = %s",
            (*champs.values(), plan_id),
        )

    def lister_plans(self, site_id: int, debut: date, fin: date) -> list[dict]:
        return self._tous(
            f"""SELECT {COLONNES_PLAN} {_DE_PLAN}
                WHERE p.site_id = %s AND p.semaine BETWEEN %s AND %s ORDER BY p.semaine""",
            (site_id, debut, fin),
        )

    # --- Lignes --------------------------------------------------------------
    def lignes(self, plan_id: int) -> list[dict]:
        return self._tous(
            f"""SELECT {COLONNES_LIGNE} FROM plans_charge_lignes l
                JOIN zones z ON z.id = l.zone_id WHERE l.plan_id = %s
                ORDER BY z.id, l.date_jour""",
            (plan_id,),
        )

    def remplacer_lignes(self, plan_id: int, lignes: list[dict]) -> int:
        """Remplace toutes les lignes du plan (utilisé par « Proposer le plan »)."""
        self._executer("DELETE FROM plans_charge_lignes WHERE plan_id = %s", (plan_id,))
        return self.inserer_lignes(plan_id, lignes)

    def inserer_lignes(self, plan_id: int, lignes: list[dict]) -> int:
        if not lignes:
            return 0
        valeurs = [(plan_id, *(ligne[c] for c in CHAMPS_LIGNE)) for ligne in lignes]
        execute_values(
            self.cur,
            f"INSERT INTO plans_charge_lignes (plan_id, {', '.join(CHAMPS_LIGNE)}) VALUES %s",
            valeurs,
        )
        return len(lignes)

    def mettre_a_jour_lignes(self, plan_id: int, lignes: list[dict]) -> int:
        """Met à jour des lignes existantes (édition par le planificateur)."""
        for ligne in lignes:
            self._executer(
                """UPDATE plans_charge_lignes
                   SET effectif_planifie = %s, interim_planifie = %s, equipements_planifies = %s,
                       commentaire = %s
                   WHERE plan_id = %s AND zone_id = %s AND date_jour = %s""",
                (
                    ligne["effectif_planifie"],
                    ligne["interim_planifie"],
                    ligne["equipements_planifies"],
                    ligne.get("commentaire", ""),
                    plan_id,
                    ligne["zone_id"],
                    ligne["date_jour"],
                ),
            )
        return len(lignes)


class DepotScenarios(Depot):
    """Accès à la table ``scenarios`` (UC13)."""

    def creer(self, plan_id: int, hypotheses: dict, resultats: dict, auteur_id: int | None) -> int:
        return self._un(
            """INSERT INTO scenarios (plan_id, hypotheses, resultats, auteur_id)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (plan_id, Json(hypotheses), Json(resultats), auteur_id),
        )["id"]

    def scenario(self, scenario_id: int) -> dict | None:
        return self._un(
            """SELECT id, plan_id, hypotheses, resultats, applique, auteur_id, date_creation
               FROM scenarios WHERE id = %s""",
            (scenario_id,),
        )

    def marquer_applique(self, scenario_id: int) -> None:
        self._executer("UPDATE scenarios SET applique = TRUE WHERE id = %s", (scenario_id,))

    def lister(self, plan_id: int) -> list[dict]:
        return self._tous(
            """SELECT id, hypotheses, resultats, applique, auteur_id, date_creation
               FROM scenarios WHERE plan_id = %s ORDER BY date_creation DESC""",
            (plan_id,),
        )
