"""UC06 · Contrôler la qualité des données (inclus dans UC04 et UC05).

Ce module contient les règles de validation, indépendantes de la base de données :
``controler_qualite`` reçoit les lignes brutes et un :class:`ContexteValidation` déjà
préparé (référentiels et historique nécessaires aux comparaisons), et rend
``(valides, rejets, avertissements)``. L'orchestration qui construit ce contexte à
partir de la base se trouve dans ``app.services.donnees``.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

NB_JOURS_REFERENCE = 8
SEUIL_ECARTS_TYPE = 3


@dataclass(frozen=True)
class Rejet:
    """Une ligne rejetée : le numéro de ligne, la colonne fautive et la raison."""

    ligne: int
    colonne: str
    raison: str


@dataclass(frozen=True)
class Avertissement:
    """Une valeur inhabituelle, acceptée mais signalée."""

    ligne: int
    colonne: str
    message: str


@dataclass(frozen=True)
class ChampSpec:
    """Description d'un champ à valider."""

    cle: str
    libelle: str
    type: str  # "texte" | "nombre" | "entier" | "booleen" | "date"
    obligatoire: bool = False
    defaut: object = None
    minimum: float | None = 0


@dataclass(frozen=True)
class ContexteValidation:
    """Référentiels et historique nécessaires à la validation d'un lot de lignes.

    - ``sites`` : nom de site en minuscules -> ``{"id", "actif"}`` ;
    - ``zones`` : (site_id, nom de zone en minuscules) -> ``{"id", "actif", "duree_poste_heures"}`` ;
    - ``valeurs_reference`` : ``(site_id, zone_id, jour) -> valeurs`` des occurrences précédentes
      du même jour de semaine, utilisées pour l'avertissement d'écart-type ;
    - ``aujourd_hui`` : date du jour (pour le refus des dates passées, UC05).
    """

    sites: dict[str, dict]
    zones: dict[tuple[int, str], dict]
    valeurs_reference: Callable[[int, int, date], list[float]] = field(default=lambda *_: [])
    aujourd_hui: date = field(default_factory=date.today)


@dataclass
class ResultatControleQualite:
    """Résultat de :func:`controler_qualite`."""

    valides: list[dict]
    rejets: list[Rejet]
    avertissements: list[Avertissement]

    @property
    def nb_lignes(self) -> int:
        return len(self.valides) + len({r.ligne for r in self.rejets})


CHAMPS_HISTORIQUE: list[ChampSpec] = [
    ChampSpec("volume_traite", "Volume traité", "nombre", obligatoire=True),
    ChampSpec("effectif_present", "Effectif présent", "entier", obligatoire=True),
    ChampSpec("heures_travaillees", "Heures travaillées", "nombre", obligatoire=True),
    ChampSpec("heures_sup", "Heures supplémentaires", "nombre", defaut=0.0),
    ChampSpec("heures_interim", "Heures d'intérim", "nombre", defaut=0.0),
    ChampSpec("heures_absence", "Heures d'absence", "nombre", defaut=0.0),
    ChampSpec("heures_inactives", "Heures inactives", "nombre", defaut=0.0),
    ChampSpec("equipements_mobilises", "Équipements mobilisés", "entier", defaut=0),
    ChampSpec("heures_usage_equipement", "Heures d'usage équipement", "nombre", defaut=0.0),
    ChampSpec(
        "heures_disponibles_equipement", "Heures disponibles équipement", "nombre", defaut=0.0
    ),
    ChampSpec("heures_panne_equipement", "Heures de panne équipement", "nombre", defaut=0.0),
    ChampSpec("cout_rh", "Coût RH", "nombre", defaut=0.0),
    ChampSpec("commandes_a_temps", "Commandes expédiées à temps", "entier", defaut=0),
    ChampSpec("commandes_totales", "Commandes totales", "entier", defaut=0),
    ChampSpec("indicateur_pic", "Indicateur de pic", "booleen", defaut=False),
]

CHAMPS_PREVISION: list[ChampSpec] = [
    ChampSpec("volume_prevu", "Volume prévu", "nombre", obligatoire=True),
    ChampSpec("indicateur_pic", "Indicateur de pic", "booleen", defaut=False),
]

CHAMPS_IDENTITE = [
    ChampSpec("site", "Site", "texte", obligatoire=True),
    ChampSpec("zone", "Zone", "texte", obligatoire=True),
    ChampSpec("date", "Date", "date", obligatoire=True),
]

_CHAMPS_PAR_TYPE = {"historique": CHAMPS_HISTORIQUE, "prevision": CHAMPS_PREVISION}
_CHAMP_VOLUME_PAR_TYPE = {"historique": "volume_traite", "prevision": "volume_prevu"}


def _est_vide(brut) -> bool:
    return brut is None or (isinstance(brut, str) and not brut.strip())


def _convertir_nombre(brut, libelle: str) -> float:
    from app.utils.format_fr import lire_nombre

    if isinstance(brut, bool):
        raise ValueError(f"« {libelle} » doit être un nombre.")
    if isinstance(brut, (int, float)):
        return float(brut)
    try:
        return lire_nombre(str(brut))
    except ValueError:
        raise ValueError(f"« {libelle} » doit être un nombre.") from None


def _convertir_booleen(brut) -> bool:
    if isinstance(brut, bool):
        return brut
    texte = str(brut).strip().lower()
    if texte in ("oui", "vrai", "1", "true", "x"):
        return True
    if texte in ("non", "faux", "0", "false"):
        return False
    raise ValueError("valeur booléenne invalide")


def _convertir_date(brut) -> date:
    from app.utils.format_fr import lire_date

    if isinstance(brut, datetime):
        return brut.date()
    if isinstance(brut, date):
        return brut
    return lire_date(str(brut))


def _convertir_champ(spec: ChampSpec, brut) -> object:
    if _est_vide(brut):
        if spec.obligatoire:
            raise ValueError(f"Le champ « {spec.libelle} » est obligatoire.")
        return spec.defaut
    if spec.type == "texte":
        return str(brut).strip()
    if spec.type == "date":
        return _convertir_date(brut)
    if spec.type == "booleen":
        try:
            return _convertir_booleen(brut)
        except ValueError:
            raise ValueError(f"« {spec.libelle} » doit valoir Oui ou Non.") from None
    valeur = _convertir_nombre(brut, spec.libelle)
    if spec.minimum is not None and valeur < spec.minimum:
        raise ValueError(f"« {spec.libelle} » ne peut pas être négatif.")
    if spec.type == "entier":
        if valeur != int(valeur):
            raise ValueError(f"« {spec.libelle} » doit être un nombre entier.")
        return int(valeur)
    return valeur


def controler_qualite(
    type_donnees: str, lignes_brutes: list[dict], contexte: ContexteValidation
) -> ResultatControleQualite:
    """UC06 : contrôle un lot de lignes brutes (historique ou prévision).

    Rejette : champ obligatoire manquant, valeur négative, site ou zone inconnus, doublon
    dans le fichier et, pour l'historique, heures travaillées > effectif × durée de poste ×
    1,5 et heures d'usage > heures disponibles ; pour la prévision, une date passée.
    Signale (sans rejeter) une valeur à plus de 3 écarts-types de la moyenne des 8 mêmes
    jours de semaine précédents.
    """
    if type_donnees not in _CHAMPS_PAR_TYPE:
        raise ValueError(f"Type de données inconnu : « {type_donnees} ».")
    specs = CHAMPS_IDENTITE + _CHAMPS_PAR_TYPE[type_donnees]
    champ_volume = _CHAMP_VOLUME_PAR_TYPE[type_donnees]

    valides: list[dict] = []
    rejets: list[Rejet] = []
    avertissements: list[Avertissement] = []
    cles_vues: set[tuple[int, int, date]] = set()

    for numero, brut in enumerate(lignes_brutes, start=1):
        valeurs: dict = {}
        erreurs: list[tuple[str, str]] = []
        for spec in specs:
            try:
                valeurs[spec.cle] = _convertir_champ(spec, brut.get(spec.cle))
            except ValueError as exc:
                erreurs.append((spec.cle, str(exc)))

        site_id = zone_id = duree_poste = None
        if "site" not in dict(erreurs):
            site = contexte.sites.get(str(valeurs["site"]).lower())
            if site is None or not site.get("actif", True):
                erreurs.append(("site", f"Site inconnu ou inactif : « {valeurs['site']} »."))
            else:
                site_id = site["id"]
        if site_id is not None and "zone" not in dict(erreurs):
            zone = contexte.zones.get((site_id, str(valeurs["zone"]).lower()))
            if zone is None or not zone.get("actif", True):
                erreurs.append(("zone", f"Zone inconnue ou inactive : « {valeurs['zone']} »."))
            else:
                zone_id = zone["id"]
                duree_poste = zone["duree_poste_heures"]

        if type_donnees == "prevision" and not dict(erreurs).get("date") and valeurs.get("date"):
            if valeurs["date"] < contexte.aujourd_hui:
                erreurs.append(("date", "Cette date est déjà passée."))

        if type_donnees == "historique" and site_id is not None and zone_id is not None:
            if (
                valeurs.get("heures_travaillees") is not None
                and valeurs.get("effectif_present") is not None
            ):
                limite = valeurs["effectif_present"] * duree_poste * 1.5
                if valeurs["heures_travaillees"] > limite:
                    erreurs.append(
                        (
                            "heures_travaillees",
                            "Les heures travaillées dépassent l'effectif présent multiplié par la "
                            "durée de poste et 1,5 (heures manifestement excessives).",
                        )
                    )
            if (
                valeurs.get("heures_usage_equipement") is not None
                and valeurs.get("heures_disponibles_equipement") is not None
                and valeurs["heures_usage_equipement"] > valeurs["heures_disponibles_equipement"]
            ):
                erreurs.append(
                    (
                        "heures_usage_equipement",
                        "Les heures d'usage dépassent les heures disponibles de l'équipement.",
                    )
                )
            if (
                valeurs.get("heures_inactives") is not None
                and valeurs.get("heures_travaillees") is not None
                and valeurs["heures_inactives"] > valeurs["heures_travaillees"]
            ):
                erreurs.append(
                    (
                        "heures_inactives",
                        "Les heures inactives dépassent les heures travaillées.",
                    )
                )
            if (
                valeurs.get("commandes_a_temps") is not None
                and valeurs.get("commandes_totales") is not None
                and valeurs["commandes_a_temps"] > valeurs["commandes_totales"]
            ):
                erreurs.append(
                    (
                        "commandes_a_temps",
                        "Les commandes expédiées à temps dépassent les commandes totales.",
                    )
                )

        if site_id is not None and zone_id is not None and valeurs.get("date") is not None:
            cle = (site_id, zone_id, valeurs["date"])
            if cle in cles_vues:
                erreurs.append(
                    ("date", "Doublon : site, zone et date déjà présents dans ce fichier.")
                )
            else:
                cles_vues.add(cle)

        if erreurs:
            rejets.extend(Rejet(numero, colonne, raison) for colonne, raison in erreurs)
            continue

        if site_id is not None and zone_id is not None:
            reference = contexte.valeurs_reference(site_id, zone_id, valeurs["date"])
            if len(reference) >= NB_JOURS_REFERENCE:
                moyenne = statistics.mean(reference)
                ecart_type = statistics.stdev(reference)
                valeur = valeurs[champ_volume]
                inhabituelle = (
                    valeur != moyenne
                    if ecart_type == 0
                    else abs(valeur - moyenne) > SEUIL_ECARTS_TYPE * ecart_type
                )
                if inhabituelle:
                    avertissements.append(
                        Avertissement(
                            numero,
                            champ_volume,
                            f"Valeur inhabituelle : {valeur:g} contre une moyenne de "
                            f"{moyenne:.1f} sur les {NB_JOURS_REFERENCE} mêmes jours de semaine "
                            "précédents (écart supérieur à 3 écarts-types).",
                        )
                    )

        valides.append({**valeurs, "site_id": site_id, "zone_id": zone_id, "_ligne": numero})

    return ResultatControleQualite(valides, rejets, avertissements)
