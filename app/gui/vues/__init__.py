"""Écrans de l'application et navigation par rôle."""

from __future__ import annotations

import importlib
from dataclasses import dataclass

P, R, D, A = "planificateur", "responsable", "direction", "administrateur"


@dataclass(frozen=True)
class Ecran:
    """Écran accessible depuis le menu de navigation."""

    cle: str
    libelle: str
    module: str
    classe: str
    roles: frozenset[str]

    def charger(self):
        """Classe de la vue (importée à la demande)."""
        return getattr(importlib.import_module(self.module), self.classe)


ECRANS: list[Ecran] = [
    Ecran(
        "tableau_bord",
        "Tableau de bord",
        "app.gui.vues.tableau_bord",
        "VueTableauBord",
        frozenset({P, R, D}),
    ),
    Ecran("donnees", "Données", "app.gui.vues.donnees", "VueDonnees", frozenset({P})),
    Ecran(
        "previsions", "Prévisions", "app.gui.vues.previsions", "VuePrevisions", frozenset({P, R})
    ),
    Ecran(
        "plan_charge",
        "Plan de charge",
        "app.gui.vues.plan_charge",
        "VuePlanCharge",
        frozenset({P, R}),
    ),
    Ecran(
        "comparaison",
        "Comparaison réel / prévu",
        "app.gui.vues.comparaison",
        "VueComparaison",
        frozenset({R}),
    ),
    Ecran("kpi_cibles", "KPI et cibles", "app.gui.vues.kpi_cibles", "VueKpiCibles", frozenset({R})),
    Ecran("alertes", "Alertes", "app.gui.vues.alertes", "VueAlertes", frozenset({P, R})),
    Ecran("rapports", "Rapports", "app.gui.vues.rapports", "VueRapports", frozenset({R})),
    Ecran("modeles", "Modèles", "app.gui.vues.modeles", "VueModeles", frozenset({A})),
    Ecran(
        "administration",
        "Administration",
        "app.gui.vues.administration",
        "VueAdministration",
        frozenset({A}),
    ),
]

#: Écran d'accueil après connexion.
ACCUEIL = {P: "tableau_bord", R: "tableau_bord", D: "tableau_bord", A: "modeles"}


def ecrans_autorises(role: str) -> list[Ecran]:
    """Écrans du menu de navigation pour un rôle."""
    return [ecran for ecran in ECRANS if role in ecran.roles]


def ecran(cle: str) -> Ecran:
    return next(e for e in ECRANS if e.cle == cle)
