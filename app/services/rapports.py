"""UC23 · Générer un rapport de performance — UC24 · Exporter un rapport.

UC23 calcule les KPI de la période (UC17) et recense les alertes qui la concernent, écrit un
PDF et un classeur Excel dans ``rapports/`` (nom stable, régénérer un rapport identique
écrase le précédent) et enregistre la trace dans la table ``rapports`` (le contenu JSON permet
de rouvrir un rapport sans recalculer). UC24 renvoie le chemin du fichier déjà généré, pour
que l'écran l'enregistre où l'utilisateur le souhaite (même geste que les autres exports).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.bd.connexion import transaction
from app.bd.depots.rapports import DepotRapports
from app.bd.depots.referentiels import DepotReferentiels
from app.config import DOSSIER_RAPPORTS
from app.contexte import Contexte
from app.erreurs import OperationImpossible
from app.journal import journal
from app.libelles import (
    FAMILLES_KPI,
    METHODES_COURTES,
    NIVEAUX_ALERTE,
    PERIODICITES,
    STATUTS_ALERTE,
    STATUTS_KPI,
    TYPES_ALERTE,
    libelle,
)
from app.services.alertes import lister_alertes
from app.services.droits import verifier_droit, verifier_site
from app.services.kpi import comparer_kpi_cibles
from app.utils.dates import bornes_periode
from app.utils.fichiers_excel import ecrire_classeur
from app.utils.fichiers_pdf import ecrire_rapport_pdf
from app.utils.format_fr import formater_date, formater_nombre

_log = journal(__name__)

FORMATS_VALIDES = ("pdf", "excel", "pdf_excel")


def _lignes_kpi(valeurs: list[dict]) -> tuple[list[str], list[list[str]]]:
    en_tetes = ["Famille", "KPI", "Méthode", "Valeur", "Unité", "Cible", "Statut"]
    lignes = [
        [
            libelle(FAMILLES_KPI, v["famille"]),
            v["kpi_libelle"],
            METHODES_COURTES.get(v["methode"], "—"),
            formater_nombre(v["valeur"], 2),
            v["unite"] or "—",
            formater_nombre(v["cible"], 2),
            libelle(STATUTS_KPI, v["statut"]),
        ]
        for v in valeurs
    ]
    return en_tetes, lignes


def _lignes_alertes(alertes: list[dict]) -> tuple[list[str], list[list[str]]]:
    en_tetes = ["Type", "Niveau", "Zone", "Date concernée", "Statut", "Message"]
    lignes = [
        [
            libelle(TYPES_ALERTE, a["type"]),
            libelle(NIVEAUX_ALERTE, a["niveau"]),
            a["zone"] or "Général",
            formater_date(a["date_concernee"]),
            libelle(STATUTS_ALERTE, a["statut"]),
            a["message"],
        ]
        for a in alertes
    ]
    return en_tetes, lignes


def generer_rapport(
    ctx: Contexte,
    site_id: int,
    periodicite: str,
    date_reference: date | None = None,
    format_rapport: str = "pdf_excel",
) -> dict:
    """UC23 : calcule les KPI et recense les alertes de la période, écrit le(s) fichier(s)
    demandé(s) et enregistre le rapport."""
    verifier_droit(ctx, "UC23")
    verifier_site(ctx, site_id)
    if format_rapport not in FORMATS_VALIDES:
        raise ValueError(f"Format de rapport invalide : « {format_rapport} ».")
    date_reference = date_reference or date.today()
    debut, fin = bornes_periode(date_reference, periodicite)

    with transaction() as cur:
        site = DepotReferentiels(cur).site(site_id)
    if site is None:
        raise OperationImpossible("Site introuvable.")

    valeurs_kpi = comparer_kpi_cibles(ctx, site_id, None, periodicite, date_reference)
    toutes_alertes = lister_alertes(ctx, site_id)
    alertes_periode = [a for a in toutes_alertes if debut <= a["date_concernee"] <= fin]

    titre = f"Rapport de performance — {site['nom']}"
    sous_titre = (
        f"{libelle(PERIODICITES, periodicite)} du {formater_date(debut)} au "
        f"{formater_date(fin)} — généré par {ctx.identifiant} le {formater_date(date.today())}"
    )
    entetes_kpi, lignes_kpi = _lignes_kpi(valeurs_kpi)
    entetes_alertes, lignes_alertes = _lignes_alertes(alertes_periode)

    nom_base = f"rapport_{site_id}_{periodicite}_{debut.isoformat()}"
    chemin_pdf = chemin_excel = None
    if format_rapport in ("pdf", "pdf_excel"):
        chemin_pdf = f"{nom_base}.pdf"
        ecrire_rapport_pdf(
            DOSSIER_RAPPORTS / chemin_pdf,
            titre,
            sous_titre,
            [
                ("Indicateurs de performance (KPI)", entetes_kpi, lignes_kpi),
                ("Alertes de la période", entetes_alertes, lignes_alertes),
            ],
        )
    if format_rapport in ("excel", "pdf_excel"):
        chemin_excel = f"{nom_base}.xlsx"
        ecrire_classeur(
            DOSSIER_RAPPORTS / chemin_excel,
            {
                "KPI": (entetes_kpi, lignes_kpi),
                "Alertes": (entetes_alertes, lignes_alertes),
            },
        )

    contenu = {
        "site": site["nom"],
        "periodicite": periodicite,
        "date_debut": debut.isoformat(),
        "date_fin": fin.isoformat(),
        "kpi": valeurs_kpi,
        "alertes": alertes_periode,
    }
    with transaction() as cur:
        rapport_id = DepotRapports(cur).creer(
            periodicite,
            debut,
            fin,
            site_id,
            format_rapport,
            chemin_pdf,
            chemin_excel,
            contenu,
            ctx.utilisateur_id,
            ctx.est_systeme,
        )
    _log.info(
        "Rapport n° %s généré par %s (site %s, %s du %s au %s).",
        rapport_id,
        ctx.identifiant,
        site_id,
        periodicite,
        debut,
        fin,
    )
    return {
        "rapport_id": rapport_id,
        "site": site["nom"],
        "debut": debut,
        "fin": fin,
        "kpi": valeurs_kpi,
        "alertes": alertes_periode,
        "chemin_pdf": chemin_pdf,
        "chemin_excel": chemin_excel,
    }


def lister_rapports(ctx: Contexte, site_id: int, periodicite: str | None = None) -> list[dict]:
    """Rapports déjà générés pour un site (écran Rapports)."""
    verifier_droit(ctx, "UC23")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        return DepotRapports(cur).lister(site_id, periodicite)


def exporter_rapport(ctx: Contexte, rapport_id: int, format_fichier: str) -> Path:
    """UC24 : chemin du fichier déjà généré (PDF ou Excel), pour l'enregistrer où l'utilisateur
    le souhaite."""
    verifier_droit(ctx, "UC24")
    if format_fichier not in ("pdf", "excel"):
        raise ValueError(f"Format de fichier invalide : « {format_fichier} ».")
    with transaction() as cur:
        rapport = DepotRapports(cur).rapport(rapport_id)
    if rapport is None:
        raise OperationImpossible("Rapport introuvable.")
    verifier_site(ctx, rapport["site_id"])
    chemin_relatif = rapport["chemin_pdf"] if format_fichier == "pdf" else rapport["chemin_excel"]
    if chemin_relatif is None:
        raise OperationImpossible(f"Ce rapport n'a pas de fichier {format_fichier.upper()}.")
    chemin = DOSSIER_RAPPORTS / chemin_relatif
    if not chemin.is_file():
        raise OperationImpossible("Le fichier du rapport est introuvable sur le serveur.")
    _log.info("Rapport n° %s exporté (%s) par %s.", rapport_id, format_fichier, ctx.identifiant)
    return chemin
