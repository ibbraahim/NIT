"""Catalogue des 20 KPI et cibles par défaut, inséré par ``init_bd``.

Les pourcentages sont exprimés en points (5 → 5 %).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefinitionKpi:
    """Définition d'un KPI (table ``kpi_definitions``)."""

    code: str
    libelle: str
    famille: str
    formule: str
    unite: str
    sens: str
    par_methode: bool


@dataclass(frozen=True)
class ObjectifDefaut:
    """Objectif général (tous sites) d'un KPI pour une périodicité."""

    code: str
    periodicite: str
    valeur_cible: float | None = None
    seuil_orange: float | None = None
    seuil_rouge: float | None = None
    valeur_min: float | None = None
    valeur_max: float | None = None
    seuils_relatifs: bool = False


CATALOGUE: list[DefinitionKpi] = [
    DefinitionKpi(
        "MAE_H",
        "Erreur absolue moyenne (heures)",
        "precision",
        "moyenne de |réel − prévu|",
        "h",
        "information",
        True,
    ),
    DefinitionKpi(
        "RMSE_H",
        "Racine de l'erreur quadratique moyenne",
        "precision",
        "√moyenne((réel − prévu)²)",
        "h",
        "information",
        True,
    ),
    DefinitionKpi(
        "MAPE_H",
        "Erreur absolue moyenne en %",
        "precision",
        "moyenne de |réel − prévu| / réel (jours à réel nul exclus)",
        "%",
        "baisse",
        True,
    ),
    DefinitionKpi(
        "BIAIS_H",
        "Biais de prévision (%)",
        "precision",
        "Σ(prévu − réel) / Σréel",
        "%",
        "plage",
        True,
    ),
    DefinitionKpi(
        "COUV_IC",
        "Couverture de l'intervalle de confiance (%)",
        "precision",
        "part des réels comprise dans [ic_bas ; ic_haut]",
        "%",
        "plage",
        True,
    ),
    DefinitionKpi(
        "ECART_EQP",
        "Écart moyen sur les équipements",
        "precision",
        "moyenne de |équipements réels − prévus|",
        "équipements",
        "baisse",
        True,
    ),
    DefinitionKpi(
        "TAUX_VICTOIRE",
        "Taux de victoire",
        "precision",
        "part des jours où la méthode a l'erreur absolue la plus faible",
        "%",
        "information",
        True,
    ),
    DefinitionKpi(
        "PRODUCTIVITE",
        "Productivité",
        "rh",
        "Σvolume / Σheures travaillées",
        "unités/h",
        "hausse",
        False,
    ),
    DefinitionKpi(
        "ADEQUATION",
        "Adéquation de l'effectif (%)",
        "rh",
        "Σheures planifiées (plan validé) / Σheures nécessaires réelles",
        "%",
        "plage",
        False,
    ),
    DefinitionKpi(
        "TAUX_HS",
        "Taux d'heures supplémentaires (%)",
        "rh",
        "Σheures sup / Σheures travaillées",
        "%",
        "baisse",
        False,
    ),
    DefinitionKpi(
        "TAUX_INTERIM",
        "Taux de recours à l'intérim (%)",
        "rh",
        "Σheures intérim / Σheures travaillées",
        "%",
        "baisse",
        False,
    ),
    DefinitionKpi(
        "TAUX_SOUS_CHARGE",
        "Taux de sous-charge (%)",
        "rh",
        "Σheures inactives / Σheures payées",
        "%",
        "baisse",
        False,
    ),
    DefinitionKpi(
        "TAUX_ABSENTEISME",
        "Taux d'absentéisme (%)",
        "rh",
        "Σheures d'absence / Σ(heures travaillées + heures d'absence)",
        "%",
        "baisse",
        False,
    ),
    DefinitionKpi(
        "DELAI_ANTICIPATION",
        "Délai d'anticipation (jours)",
        "rh",
        "moyenne de (date concernée − date de création) des alertes de sous-effectif",
        "jours",
        "hausse",
        False,
    ),
    DefinitionKpi(
        "TAUX_UTIL_EQP",
        "Taux d'utilisation des équipements (%)",
        "equipements",
        "Σheures d'usage / Σheures disponibles",
        "%",
        "plage",
        False,
    ),
    DefinitionKpi(
        "TAUX_DISPO_EQP",
        "Taux de disponibilité des équipements (%)",
        "equipements",
        "1 − Σheures de panne / Σ(heures disponibles + heures de panne)",
        "%",
        "hausse",
        False,
    ),
    DefinitionKpi(
        "JOURS_PENURIE",
        "Jours de pénurie d'équipements",
        "equipements",
        "nombre de jours où les équipements nécessaires dépassent les disponibles",
        "jours",
        "baisse",
        False,
    ),
    DefinitionKpi(
        "COUT_UNITE",
        "Coût RH par unité traitée",
        "couts",
        "Σcoût RH / Σvolume",
        "devise/unité",
        "baisse",
        False,
    ),
    DefinitionKpi(
        "ECART_COUT",
        "Écart de coût prévu / réel (%)",
        "couts",
        "(coût réel − coût du plan validé) / coût du plan validé",
        "%",
        "plage",
        False,
    ),
    DefinitionKpi(
        "TAUX_A_TEMPS",
        "Commandes expédiées à temps (%)",
        "service",
        "Σcommandes à temps / Σcommandes totales",
        "%",
        "hausse",
        False,
    ),
]

PERIODICITES = ("jour", "semaine", "mois", "annee")


def objectifs_par_defaut() -> list[ObjectifDefaut]:
    """Objectifs généraux (tous sites, toutes zones) pour chaque périodicité."""
    objectifs: list[ObjectifDefaut] = []
    for p in PERIODICITES:
        if p == "jour":
            objectifs.append(ObjectifDefaut("MAPE_H", p, 10, 10, 15))
        else:
            objectifs.append(ObjectifDefaut("MAPE_H", p, 5, 5, 8))
        objectifs += [
            ObjectifDefaut("BIAIS_H", p, 0, 2, None, -3, 3),
            ObjectifDefaut("COUV_IC", p, 80, 5, None, 75, 90),
            ObjectifDefaut("ECART_EQP", p, 1, 1, 2),
            ObjectifDefaut("PRODUCTIVITE", p, None, 95, 90, seuils_relatifs=True),
            ObjectifDefaut("ADEQUATION", p, 100, 5, None, 95, 105),
            ObjectifDefaut("TAUX_HS", p, 5, 5, 8),
            ObjectifDefaut("TAUX_INTERIM", p, 10, 10, 15),
            ObjectifDefaut("TAUX_SOUS_CHARGE", p, 5, 5, 10),
            ObjectifDefaut("TAUX_ABSENTEISME", p, 5, 5, 8),
            ObjectifDefaut("DELAI_ANTICIPATION", p, 2, 2, 1),
            ObjectifDefaut("TAUX_UTIL_EQP", p, 77.5, 10, None, 70, 85),
            ObjectifDefaut("TAUX_DISPO_EQP", p, 95, 95, 90),
            ObjectifDefaut("JOURS_PENURIE", p, 0, 0, 1),
            ObjectifDefaut("COUT_UNITE", p, None, 105, 110, seuils_relatifs=True),
            ObjectifDefaut("ECART_COUT", p, 0, 5, None, -5, 5),
            ObjectifDefaut("TAUX_A_TEMPS", p, 95, 95, 90),
        ]
    return objectifs
