"""UC04 · Importer / saisir l'historique d'activité — UC05 · même chose pour les prévisions
de volume — UC06 · Contrôler la qualité des données (inclus dans les deux, voir
``app.services.qualite``).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.bd.depots.previsions import DepotPrevisionsVolume
from app.bd.depots.referentiels import DepotReferentiels
from app.config import DOSSIER_MODELES_FICHIERS
from app.contexte import Contexte
from app.erreurs import DonneesInvalides
from app.journal import journal
from app.services.droits import verifier_droit, verifier_site
from app.services.qualite import (
    Avertissement,
    ContexteValidation,
    Rejet,
    ResultatControleQualite,
    controler_qualite,
)
from app.utils.fichiers_excel import ecrire_classeur, lire_lignes_fichier

_log = journal(__name__)

MODELES_FICHIERS = {
    "historique": DOSSIER_MODELES_FICHIERS / "modele_historique_activite.csv",
    "prevision": DOSSIER_MODELES_FICHIERS / "modele_previsions_volume.csv",
}

HORIZON_PREVISION_JOURS = 28


# =====================================================================
# Contexte de validation (référentiels visibles + historique de référence)
# =====================================================================
def _contexte_validation(cur, ctx: Contexte, jour: date | None = None) -> ContexteValidation:
    ref = DepotReferentiels(cur)
    ids_visibles = None if ctx.voit_tous_les_sites else sorted(ctx.sites)
    sites = {s["nom"].lower(): s for s in ref.lister_sites(ids=ids_visibles)}
    zones: dict[tuple[int, str], dict] = {}
    for site in sites.values():
        for zone in ref.lister_zones(site["id"]):
            zones[(site["id"], zone["nom"].lower())] = zone
    historique = DepotHistorique(cur)

    def valeurs_reference(site_id: int, zone_id: int, jour_ligne: date) -> list[float]:
        return historique.volumes_semaine_precedente(site_id, zone_id, jour_ligne)

    return ContexteValidation(sites, zones, valeurs_reference, aujourd_hui=jour or date.today())


def _nom_site_zone(cur, site_id: int, zone_id: int) -> tuple[str, str]:
    ref = DepotReferentiels(cur)
    return ref.site(site_id)["nom"], ref.zone(zone_id)["nom"]


# =====================================================================
# UC04 · Historique d'activité
# =====================================================================
def lister_historique(
    ctx: Contexte, site_id: int | None = None, zone_id: int | None = None, jours: int = 60
) -> list[dict]:
    """Historique des ``jours`` derniers jours (tableau de l'écran Données).

    ``site_id=None`` liste l'ensemble des sites auxquels l'utilisateur est rattaché.
    """
    verifier_droit(ctx, "UC04")
    sites = _sites_cibles(ctx, site_id)
    fin = date.today()
    with transaction() as cur:
        return DepotHistorique(cur).lister(sites, zone_id, fin - timedelta(days=jours - 1), fin)


def _sites_cibles(ctx: Contexte, site_id: int | None) -> list[int] | None:
    """Sites sur lesquels porte une lecture : un site précis, ou tous ceux visibles."""
    if site_id is not None:
        verifier_site(ctx, site_id)
        return [site_id]
    return None if ctx.voit_tous_les_sites else sorted(ctx.sites)


def saisir_historique(ctx: Contexte, site_id: int, zone_id: int, champs: dict) -> list[str]:
    """Saisie manuelle d'une ligne d'historique (formulaire).

    Retourne les messages d'avertissement éventuels (valeur inhabituelle, acceptée
    quand même). Lève :class:`DonneesInvalides` (``erreurs`` = ``{champ: message}``)
    si la ligne est rejetée.
    """
    verifier_droit(ctx, "UC04")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        nom_site, nom_zone = _nom_site_zone(cur, site_id, zone_id)
        ligne_brute = {**champs, "site": nom_site, "zone": nom_zone}
        contexte = _contexte_validation(cur, ctx)
        resultat = controler_qualite("historique", [ligne_brute], contexte)
        if resultat.rejets:
            raise DonneesInvalides(
                "La ligne saisie est invalide.",
                {rejet.colonne: rejet.raison for rejet in resultat.rejets},
            )
        DepotHistorique(cur).upsert(_ligne_pour_ecriture(resultat.valides[0], "saisie"))
    _log.info(
        "Historique saisi pour le %s (site %s, zone %s) par %s.",
        champs.get("date"),
        site_id,
        zone_id,
        ctx.identifiant,
    )
    return [a.message for a in resultat.avertissements]


def importer_historique(ctx: Contexte, chemin: Path) -> ResultatControleQualite:
    """UC04 (import) : lit le fichier et applique UC06, sans écrire en base."""
    verifier_droit(ctx, "UC04")
    lignes_brutes = lire_lignes_fichier(chemin)
    with transaction() as cur:
        contexte = _contexte_validation(cur, ctx)
        resultat = controler_qualite("historique", lignes_brutes, contexte)
    _log.info(
        "Import historique « %s » par %s : %d valides, %d rejetées, %d avertissements.",
        chemin.name,
        ctx.identifiant,
        len(resultat.valides),
        len(resultat.rejets),
        len(resultat.avertissements),
    )
    return resultat


def enregistrer_lignes_historique(ctx: Contexte, valides: list[dict]) -> int:
    """Écrit les lignes validées par UC06 (bouton « Enregistrer les lignes valides »)."""
    verifier_droit(ctx, "UC04")
    for ligne in valides:
        verifier_site(ctx, ligne["site_id"])
    with transaction() as cur:
        lignes = [_ligne_pour_ecriture(ligne, "import") for ligne in valides]
        nombre = DepotHistorique(cur).upsert_plusieurs(lignes)
    _log.info("%d lignes d'historique enregistrées par %s.", nombre, ctx.identifiant)
    return nombre


def _ligne_pour_ecriture(valeurs: dict, source: str) -> dict:
    return {
        "site_id": valeurs["site_id"],
        "zone_id": valeurs["zone_id"],
        "date_jour": valeurs["date"],
        "volume_traite": valeurs["volume_traite"],
        "effectif_present": valeurs["effectif_present"],
        "heures_travaillees": valeurs["heures_travaillees"],
        "heures_sup": valeurs["heures_sup"],
        "heures_interim": valeurs["heures_interim"],
        "heures_absence": valeurs["heures_absence"],
        "heures_inactives": valeurs["heures_inactives"],
        "equipements_mobilises": valeurs["equipements_mobilises"],
        "heures_usage_equipement": valeurs["heures_usage_equipement"],
        "heures_disponibles_equipement": valeurs["heures_disponibles_equipement"],
        "heures_panne_equipement": valeurs["heures_panne_equipement"],
        "cout_rh": valeurs["cout_rh"],
        "commandes_a_temps": valeurs["commandes_a_temps"],
        "commandes_totales": valeurs["commandes_totales"],
        "indicateur_pic": valeurs["indicateur_pic"],
        "source": source,
    }


# =====================================================================
# UC05 · Prévisions de volume
# =====================================================================
def lister_previsions_volume(
    ctx: Contexte,
    site_id: int | None = None,
    zone_id: int | None = None,
    horizon_jours: int = HORIZON_PREVISION_JOURS,
) -> list[dict]:
    """Prévisions de volume saisies pour les ``horizon_jours`` prochains jours.

    ``site_id=None`` liste l'ensemble des sites auxquels l'utilisateur est rattaché.
    """
    verifier_droit(ctx, "UC05")
    sites = _sites_cibles(ctx, site_id)
    debut = date.today() + timedelta(days=1)
    with transaction() as cur:
        return DepotPrevisionsVolume(cur).lister(
            sites, zone_id, debut, debut + timedelta(days=horizon_jours - 1)
        )


def saisir_prevision_volume(ctx: Contexte, site_id: int, zone_id: int, champs: dict) -> list[str]:
    """Saisie manuelle d'une prévision de volume (formulaire)."""
    verifier_droit(ctx, "UC05")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        nom_site, nom_zone = _nom_site_zone(cur, site_id, zone_id)
        ligne_brute = {**champs, "site": nom_site, "zone": nom_zone}
        contexte = _contexte_validation(cur, ctx)
        resultat = controler_qualite("prevision", [ligne_brute], contexte)
        if resultat.rejets:
            raise DonneesInvalides(
                "La prévision saisie est invalide.",
                {rejet.colonne: rejet.raison for rejet in resultat.rejets},
            )
        DepotPrevisionsVolume(cur).upsert(
            _ligne_prevision_pour_ecriture(resultat.valides[0], "saisie")
        )
    _log.info(
        "Prévision de volume saisie pour le %s (site %s, zone %s) par %s.",
        champs.get("date"),
        site_id,
        zone_id,
        ctx.identifiant,
    )
    return [a.message for a in resultat.avertissements]


def importer_previsions_volume(ctx: Contexte, chemin: Path) -> ResultatControleQualite:
    """UC05 (import) : lit le fichier et applique UC06, sans écrire en base."""
    verifier_droit(ctx, "UC05")
    lignes_brutes = lire_lignes_fichier(chemin)
    with transaction() as cur:
        contexte = _contexte_validation(cur, ctx)
        resultat = controler_qualite("prevision", lignes_brutes, contexte)
    _log.info(
        "Import prévisions « %s » par %s : %d valides, %d rejetées, %d avertissements.",
        chemin.name,
        ctx.identifiant,
        len(resultat.valides),
        len(resultat.rejets),
        len(resultat.avertissements),
    )
    return resultat


def enregistrer_lignes_previsions(ctx: Contexte, valides: list[dict]) -> int:
    """Écrit les prévisions validées par UC06."""
    verifier_droit(ctx, "UC05")
    for ligne in valides:
        verifier_site(ctx, ligne["site_id"])
    with transaction() as cur:
        lignes = [_ligne_prevision_pour_ecriture(ligne, "import") for ligne in valides]
        nombre = DepotPrevisionsVolume(cur).upsert_plusieurs(lignes)
    _log.info("%d prévisions de volume enregistrées par %s.", nombre, ctx.identifiant)
    return nombre


def _ligne_prevision_pour_ecriture(valeurs: dict, source: str) -> dict:
    return {
        "site_id": valeurs["site_id"],
        "zone_id": valeurs["zone_id"],
        "date_jour": valeurs["date"],
        "volume_prevu": valeurs["volume_prevu"],
        "indicateur_pic": valeurs["indicateur_pic"],
        "source": source,
    }


# =====================================================================
# Modèles de fichiers et rapport d'erreurs
# =====================================================================
def chemin_modele_fichier(type_donnees: str) -> Path:
    """Chemin du modèle CSV à proposer pour « Télécharger le modèle de fichier »."""
    return MODELES_FICHIERS[type_donnees]


def exporter_rapport_erreurs(
    chemin: Path, rejets: list[Rejet], avertissements: list[Avertissement]
) -> None:
    """Écrit un classeur Excel des lignes rejetées et des avertissements."""
    ecrire_classeur(
        chemin,
        {
            "Rejets": (
                ["Ligne", "Colonne", "Raison"],
                [[r.ligne, r.colonne, r.raison] for r in rejets],
            ),
            "Avertissements": (
                ["Ligne", "Colonne", "Message"],
                [[a.ligne, a.colonne, a.message] for a in avertissements],
            ),
        },
    )
