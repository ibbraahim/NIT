"""Recommandations : suggestion de correction pour un rejet ou un avertissement d'import
(UC06), action suggérée pour une alerte (UC18, UC21) et interprétation d'un KPI hors cible
(UC17).

Fonctionnalité ajoutée à la demande de l'utilisateur, au-delà du prompt d'origine : ces
textes accompagnent des cas d'utilisation déjà en place (aide à la décision), sans créer de
nouveau cas d'utilisation, de nouvel écran ni de nouveau droit.
"""

from __future__ import annotations

from dataclasses import dataclass

# =====================================================================
# UC06 · Corriger un rejet ou un avertissement d'import
# =====================================================================
_SUGGESTIONS_COLONNE: dict[str, str] = {
    "site": "Vérifiez l'orthographe du site dans le fichier : elle doit correspondre "
    "exactement à un site actif (Administration → Sites et zones).",
    "zone": "Vérifiez l'orthographe de la zone : elle doit correspondre exactement à une "
    "zone active de ce site (Administration → Sites et zones).",
    "date": "Vérifiez le format de la date (JJ/MM/AAAA). Pour la demande client, la date ne "
    "peut pas être dans le passé : corrigez-la ou supprimez la ligne.",
    "heures_travaillees": "Les heures saisies dépassent l'effectif présent multiplié par la "
    "durée de poste de la zone et 1,5 : vérifiez l'effectif déclaré ou la saisie des heures.",
    "heures_usage_equipement": "Les heures d'usage ne peuvent pas dépasser les heures "
    "disponibles de l'équipement : vérifiez la saisie ou la durée d'indisponibilité déclarée.",
    "heures_inactives": "Les heures inactives ne peuvent pas dépasser les heures "
    "travaillées : vérifiez la saisie.",
    "commandes_a_temps": "Les commandes à temps ne peuvent pas dépasser les commandes "
    "totales : vérifiez la saisie.",
    "volume_traite": "Vérifiez la valeur : le volume traité doit être un nombre positif.",
    "volume_prevu": "Vérifiez la valeur de la demande client : elle doit être un nombre "
    "positif.",
}

_SUGGESTION_DEFAUT_REJET = "Corrigez la ligne signalée avant de réimporter le fichier."


def suggestion_rejet(colonne: str, raison: str) -> str:
    """Suggestion de correction pour une ligne rejetée à l'import (UC06)."""
    if colonne in _SUGGESTIONS_COLONNE:
        return _SUGGESTIONS_COLONNE[colonne]
    minuscules = raison.lower()
    if "obligatoire" in minuscules:
        return "Ce champ ne peut pas être laissé vide : complétez-le avant de réimporter."
    if "doublon" in minuscules:
        return (
            "Supprimez ou fusionnez les lignes en double (même site, zone et date) dans le "
            "fichier."
        )
    if "oui ou non" in minuscules:
        return "Utilisez « Oui » ou « Non » (ou 1/0) pour ce champ."
    if "négatif" in minuscules or "entier" in minuscules or "nombre" in minuscules:
        return (
            "Corrigez la valeur : elle doit être un nombre positif (entier si demandé par "
            "le champ)."
        )
    return _SUGGESTION_DEFAUT_REJET


def suggestion_avertissement(_colonne: str) -> str:
    """Suggestion pour une valeur inhabituelle, acceptée mais signalée (UC06)."""
    return (
        "Vérifiez qu'il ne s'agit pas d'une erreur de saisie. Si la valeur est correcte "
        "(pic d'activité connu, incident ponctuel…), aucune action n'est nécessaire."
    )


# =====================================================================
# UC18, UC21 · Agir face à une alerte
# =====================================================================
_SUGGESTIONS_ALERTE: dict[str, str] = {
    "sous_effectif": (
        "Planifiez de l'intérim ou des heures supplémentaires sur la zone concernée, ou "
        "décalez des effectifs depuis une zone moins chargée."
    ),
    "sureffectif": (
        "Réduisez l'effectif planifié sur la zone et la date concernées, ou réaffectez le "
        "personnel excédentaire vers une zone en sous-effectif."
    ),
    "penurie_equipement": (
        "Réaffectez des équipements disponibles depuis une autre zone, ou avancez une "
        "maintenance prévue pour libérer du matériel à temps."
    ),
    "seuil_kpi": (
        "Consultez l'écran « KPI et cibles » : la ligne du KPI concerné y affiche son "
        "interprétation et l'action recommandée."
    ),
    "derive_modele": (
        "Réentraînez le modèle avec l'historique le plus récent (écran Modèles), ou activez "
        "temporairement l'autre méthode (RL/RN) si elle est actuellement plus fiable."
    ),
}

_SUGGESTION_DEFAUT_ALERTE = (
    "Consultez le détail de l'alerte et l'écran concerné pour décider d'une action."
)


def suggestion_alerte(type_alerte: str) -> str:
    """Action suggérée pour une alerte de capacité, de seuil de KPI ou de dérive de modèle
    (UC18, UC21)."""
    return _SUGGESTIONS_ALERTE.get(type_alerte, _SUGGESTION_DEFAUT_ALERTE)


# =====================================================================
# UC17 · Interpréter un KPI hors cible
# =====================================================================
@dataclass(frozen=True)
class InterpretationKpi:
    """Explication d'un écart et action recommandée, pour un KPI orange ou rouge."""

    explication: str
    conseil: str


#: KPI dont le sens est « baisse » ou « hausse » (une seule direction est jamais bonne).
_INTERPRETATIONS_UNE_DIRECTION: dict[str, InterpretationKpi] = {
    "MAPE_H": InterpretationKpi(
        "L'écart entre les heures prévues et les heures réellement nécessaires dépasse le "
        "seuil toléré : les prévisions manquent de précision sur cette période.",
        "Vérifiez que la demande client saisie était fiable et à jour, puis envisagez de "
        "réentraîner les modèles (écran Modèles) si l'écart se répète sur plusieurs "
        "semaines.",
    ),
    "ECART_EQP": InterpretationKpi(
        "L'écart moyen entre équipements prévus et réellement nécessaires dépasse le seuil "
        "toléré.",
        "Vérifiez la disponibilité réelle des équipements déclarée dans l'historique, et "
        "réentraînez les modèles si l'écart persiste.",
    ),
    "PRODUCTIVITE": InterpretationKpi(
        "La productivité (volume traité par heure travaillée) est en dessous de la cible.",
        "Identifiez les zones ou jours les moins productifs (heures inactives, absences, "
        "formation) et ajustez l'organisation ou la répartition des effectifs.",
    ),
    "TAUX_HS": InterpretationKpi(
        "Le taux d'heures supplémentaires dépasse le seuil toléré.",
        "Recrutez de l'intérim ou ajustez le plan de charge pour réduire le recours aux "
        "heures supplémentaires, coûteuses et sources de fatigue.",
    ),
    "TAUX_INTERIM": InterpretationKpi(
        "Le recours à l'intérim dépasse le seuil toléré.",
        "Vérifiez si un recrutement permanent serait plus économique sur la durée, ou si la "
        "demande client peut être anticipée plus tôt pour lisser le recours à l'intérim.",
    ),
    "TAUX_SOUS_CHARGE": InterpretationKpi(
        "Le taux d'heures inactives (personnel payé mais sans activité) dépasse le seuil "
        "toléré.",
        "Réduisez l'effectif planifié sur les périodes concernées, ou réaffectez le "
        "personnel excédentaire vers d'autres zones ou tâches.",
    ),
    "TAUX_ABSENTEISME": InterpretationKpi(
        "Le taux d'absentéisme dépasse le seuil toléré.",
        "Analysez les causes avec les ressources humaines, et anticipez un volant d'intérim "
        "ou de remplacement sur les zones les plus touchées.",
    ),
    "DELAI_ANTICIPATION": InterpretationKpi(
        "Le délai moyen entre la détection d'un sous-effectif et la date concernée est plus "
        "court que la cible : les alertes arrivent trop tard pour réagir efficacement.",
        "Saisissez ou importez la demande client plus tôt (horizon plus large) pour "
        "permettre au planificateur d'anticiper davantage.",
    ),
    "TAUX_DISPO_EQP": InterpretationKpi(
        "Le taux de disponibilité des équipements (hors panne) est en dessous de la cible.",
        "Vérifiez le plan de maintenance des équipements de la zone et anticipez les "
        "remplacements ou réparations récurrentes.",
    ),
    "JOURS_PENURIE": InterpretationKpi(
        "Le nombre de jours où le besoin en équipements dépasse la disponibilité dépasse le "
        "seuil toléré.",
        "Augmentez la capacité d'équipements disponible sur la zone, ou décalez des "
        "équipements depuis une zone moins chargée sur les dates concernées.",
    ),
    "COUT_UNITE": InterpretationKpi(
        "Le coût RH par unité traitée dépasse la cible.",
        "Vérifiez le taux de recours à l'intérim et aux heures supplémentaires (plus "
        "coûteux), et la productivité de la zone.",
    ),
    "TAUX_A_TEMPS": InterpretationKpi(
        "Le taux de commandes expédiées à temps est en dessous de la cible : le niveau de "
        "service se dégrade.",
        "Croisez ce résultat avec les KPI d'adéquation et de pénurie d'équipements de la "
        "même période pour identifier si le service a été affecté par un manque de "
        "ressources.",
    ),
}

#: KPI dont le sens est « plage » : (interprétation si trop bas, interprétation si trop haut).
_INTERPRETATIONS_PLAGE: dict[str, tuple[InterpretationKpi, InterpretationKpi]] = {
    "BIAIS_H": (
        InterpretationKpi(
            "Le biais est négatif : les modèles sous-estiment systématiquement les heures "
            "nécessaires par rapport au réel.",
            "Le plan de charge basé sur ces prévisions risque le sous-effectif : majorez "
            "prudemment les besoins tant que le biais n'est pas corrigé, et réentraînez les "
            "modèles avec l'historique le plus récent.",
        ),
        InterpretationKpi(
            "Le biais est positif : les modèles surestiment systématiquement les heures "
            "nécessaires par rapport au réel.",
            "Le plan de charge basé sur ces prévisions risque le sureffectif et le surcoût : "
            "réentraînez les modèles avec l'historique le plus récent.",
        ),
    ),
    "COUV_IC": (
        InterpretationKpi(
            "Moins de réels que prévu tombent dans l'intervalle de confiance : les modèles "
            "sont trop confiants, leurs marges d'incertitude sont trop étroites.",
            "Augmentez le niveau de confiance dans les paramètres du modèle (écran Modèles, "
            "UC07), ou réentraînez avec un historique plus long pour mieux capter la "
            "variabilité.",
        ),
        InterpretationKpi(
            "Plus de réels que prévu tombent dans l'intervalle de confiance : les marges "
            "d'incertitude sont plus larges que nécessaire, ce qui les rend peu informatives "
            "pour la planification.",
            "Réduisez le niveau de confiance dans les paramètres du modèle si vous "
            "souhaitez des intervalles plus resserrés.",
        ),
    ),
    "ADEQUATION": (
        InterpretationKpi(
            "L'effectif planifié couvre moins de besoin réel que la cible : le plan de "
            "charge validé est en sous-effectif par rapport au besoin réel constaté.",
            "Renforcez le plan de charge (intérim, heures supplémentaires) pour les "
            "prochaines périodes similaires, ou revoyez à la hausse la demande client "
            "utilisée pour les prévisions.",
        ),
        InterpretationKpi(
            "L'effectif planifié dépasse largement le besoin réel : le plan de charge "
            "validé est en sureffectif par rapport au besoin réel constaté.",
            "Réduisez l'effectif planifié pour les prochaines périodes similaires afin de "
            "limiter le surcoût.",
        ),
    ),
    "TAUX_UTIL_EQP": (
        InterpretationKpi(
            "Le taux d'utilisation des équipements est en dessous de la cible : une partie "
            "du parc reste inutilisée.",
            "Réduisez le nombre d'équipements planifiés sur les zones concernées, ou "
            "réaffectez-les vers des zones plus chargées.",
        ),
        InterpretationKpi(
            "Le taux d'utilisation des équipements dépasse la cible : le parc est fortement "
            "sollicité, avec un risque accru de panne.",
            "Augmentez le parc disponible sur la zone, ou planifiez des maintenances "
            "préventives pour limiter le risque de panne.",
        ),
    ),
    "ECART_COUT": (
        InterpretationKpi(
            "Le coût réel est nettement inférieur au coût du plan validé : le plan était "
            "surdimensionné par rapport aux besoins réels.",
            "Ajustez à la baisse les prochains plans de charge similaires pour éviter la "
            "sur-planification.",
        ),
        InterpretationKpi(
            "Le coût réel dépasse nettement le coût du plan validé : le plan initial "
            "sous-estimait les besoins réels.",
            "Analysez la cause du dépassement (intérim, heures supplémentaires non "
            "planifiées) et ajustez à la hausse les prochains plans similaires.",
        ),
    ),
}


def interpreter_kpi(
    kpi_code: str, sens: str, valeur: float | None, cible: float | None
) -> InterpretationKpi | None:
    """Explication et conseil pour un KPI hors cible (orange ou rouge, UC17). ``None`` si
    le KPI n'a pas d'interprétation prévue (KPI d'information) ou si la direction de l'écart
    ne peut pas être déterminée (valeur ou cible manquante, KPI « plage »)."""
    if sens == "plage":
        paire = _INTERPRETATIONS_PLAGE.get(kpi_code)
        if paire is None or valeur is None or cible is None:
            return None
        trop_bas, trop_haut = paire
        return trop_bas if valeur < cible else trop_haut
    return _INTERPRETATIONS_UNE_DIRECTION.get(kpi_code)
