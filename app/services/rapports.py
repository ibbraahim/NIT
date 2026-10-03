"""UC23 · Générer un rapport de performance — UC24 · Exporter un rapport.

UC23 calcule les KPI de la période (UC17) et recense les alertes qui la concernent, écrit un
PDF et un classeur Excel dans ``rapports/`` (nom stable, régénérer un rapport identique
écrase le précédent) et enregistre la trace dans la table ``rapports`` (le contenu JSON permet
de rouvrir un rapport sans recalculer). UC24 renvoie le chemin du fichier déjà généré, pour
que l'écran l'enregistre où l'utilisateur le souhaite (même geste que les autres exports).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
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
from app.ml.entrainement import METHODES
from app.services.alertes import lister_alertes
from app.services.comparaison import lister_comparaisons
from app.services.droits import verifier_droit, verifier_site
from app.services.kpi import (
    calculer_biais,
    calculer_couverture_ic,
    calculer_mae,
    calculer_mape,
    calculer_rmse,
    calculer_taux_victoire,
    comparer_kpi_cibles,
)
from app.services.planification import lister_plan_valide_periode
from app.utils.dates import bornes_periode
from app.utils.fichiers_excel import ecrire_classeur
from app.utils.fichiers_pdf import (
    COULEUR_REEL,
    COULEURS_METHODES,
    SectionRapport,
    ecrire_rapport_pdf,
    graphique_png,
)
from app.utils.format_fr import formater_date, formater_nombre

_log = journal(__name__)

FORMATS_VALIDES = ("pdf", "excel", "pdf_excel")

#: (libellé, fonction de calcul, sens de la meilleure valeur) pour les 5 premières métriques de
#: comparaison entre méthodes ; le taux de victoire (comparatif par nature) est calculé à part. Même
#: convention que l'écran Comparaison réel/prévu (UC20).
_FORMULES_METRIQUES = (
    ("MAE (heures)", calculer_mae, "bas"),
    ("RMSE (heures)", calculer_rmse, "bas"),
    ("MAPE (%)", calculer_mape, "bas"),
    ("Biais (%)", calculer_biais, "zero"),
    ("Couverture IC (%)", calculer_couverture_ic, "80"),
)


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


def _meilleure_methode(valeurs: dict[str, float | None], mode: str) -> str | None:
    """Méthode qui l'emporte (``None`` : moins de deux valeurs, ou égalité en tête)."""
    presentes = {m: v for m, v in valeurs.items() if v is not None}
    if len(presentes) < 2:
        return None
    ecart = {
        "bas": lambda v: v,
        "haut": lambda v: -v,
        "zero": abs,
        "80": lambda v: abs(v - 80),
    }.get(mode)
    if ecart is None:
        return None
    scores = {m: ecart(v) for m, v in presentes.items()}
    meilleur = min(scores.values())
    gagnantes = [m for m, score in scores.items() if score == meilleur]
    return gagnantes[0] if len(gagnantes) == 1 else None


def _lignes_comparaison(
    lignes_par_methode: dict[str, list[dict]],
) -> tuple[list[str], list[list[str]]]:
    """UC20 : métriques de précision de chaque méthode côte à côte, et celle qui l'emporte."""
    methodes = list(lignes_par_methode)
    en_tetes = ["Métrique", *(METHODES_COURTES[m] for m in methodes), "Meilleure méthode"]
    metriques = [
        (libelle_m, {m: fonction(lignes_par_methode[m]) for m in methodes}, mode)
        for libelle_m, fonction, mode in _FORMULES_METRIQUES
    ]
    metriques.append(
        (
            "Taux de victoire (%)",
            {
                m: calculer_taux_victoire(
                    lignes_par_methode[m], *(lignes_par_methode[a] for a in methodes if a != m)
                )
                for m in methodes
            },
            "haut",
        )
    )
    lignes = []
    for libelle_m, valeurs, mode in metriques:
        meilleure = _meilleure_methode(valeurs, mode)
        lignes.append(
            [
                libelle_m,
                *(
                    formater_nombre(valeurs[m], 2) if valeurs[m] is not None else "—"
                    for m in methodes
                ),
                METHODES_COURTES[meilleure] if meilleure else "—",
            ]
        )
    return en_tetes, lignes


def _agregation_reel_methodes(
    lignes_par_methode: dict[str, list[dict]],
) -> tuple[list[date], dict[date, float], dict[str, dict[date, float]]] | None:
    """Heures réel et prévues (par méthode) agrégées par jour, toutes zones confondues (même
    agrégation que l'écran Comparaison réel/prévu, UC20). ``None`` si aucun rapprochement."""
    toutes = [r for lignes in lignes_par_methode.values() for r in lignes]
    if not toutes:
        return None
    dates = sorted({r["date_jour"] for r in toutes})
    reel: dict[date, float] = {}
    prevu: dict[str, dict[date, float]] = {m: {} for m in lignes_par_methode}
    zones_vues: dict[date, set[int]] = {}
    for methode, lignes in lignes_par_methode.items():
        cible = prevu[methode]
        for r in lignes:
            cible[r["date_jour"]] = cible.get(r["date_jour"], 0.0) + (r["heures_prevues"] or 0.0)
            vues = zones_vues.setdefault(r["date_jour"], set())
            if r["zone_id"] not in vues and r["heures_reelles"] is not None:
                vues.add(r["zone_id"])
                reel[r["date_jour"]] = reel.get(r["date_jour"], 0.0) + r["heures_reelles"]
    return dates, reel, prevu


def _graphique_reel_methodes(lignes_par_methode: dict[str, list[dict]]) -> BytesIO | None:
    agregation = _agregation_reel_methodes(lignes_par_methode)
    if agregation is None:
        return None
    dates, reel, prevu = agregation

    def serie(valeurs_par_date: dict[date, float]) -> list[float]:
        return [valeurs_par_date.get(jour, float("nan")) for jour in dates]

    return graphique_png(
        dates,
        [
            ("Réalisé", serie(reel), COULEUR_REEL),
            *(
                (f"Prévu ({METHODES_COURTES[m]})", serie(prevu[m]), COULEURS_METHODES[m])
                for m in lignes_par_methode
            ),
        ],
    )


def _feuille_reel_methodes(
    lignes_par_methode: dict[str, list[dict]],
) -> tuple[list[str], list]:
    """Équivalent Excel du graphique réel/prévu : valeurs journalières brutes (une feuille par
    section, UC24)."""
    en_tetes = [
        "Date",
        "Réalisé (h)",
        *(f"Prévu {METHODES_COURTES[m]} (h)" for m in lignes_par_methode),
    ]
    agregation = _agregation_reel_methodes(lignes_par_methode)
    if agregation is None:
        return en_tetes, []
    dates, reel, prevu = agregation
    lignes = [
        [formater_date(jour), reel.get(jour), *(prevu[m].get(jour) for m in lignes_par_methode)]
        for jour in dates
    ]
    return en_tetes, lignes


def _lignes_plan_charge(lignes_plan: list[dict]) -> tuple[list[str], list[list[str]]]:
    en_tetes = [
        "Zone",
        "Date",
        "Besoin effectif",
        "Effectif planifié",
        "Écart effectif",
        "Besoin équipements",
        "Équipements planifiés",
        "Écart équipements",
        "Commentaire",
    ]
    lignes = [
        [
            l["zone"],
            formater_date(l["date_jour"]),
            str(l["besoin_effectif"]),
            str(l["effectif_planifie"] + l["interim_planifie"]),
            str(l["effectif_planifie"] + l["interim_planifie"] - l["besoin_effectif"]),
            str(l["besoin_equipements"]),
            str(l["equipements_planifies"]),
            str(l["equipements_planifies"] - l["besoin_equipements"]),
            l["commentaire"] or "—",
        ]
        for l in lignes_plan
    ]
    return en_tetes, lignes


def _synthese(
    valeurs_kpi: list[dict],
    alertes_periode: list[dict],
    lignes_par_methode: dict[str, list[dict]],
    lignes_plan: list[dict],
) -> list[str]:
    """Synthèse en 5 lignes maximum, générée à partir des chiffres de la période (UC23)."""
    lignes: list[str] = []
    if valeurs_kpi:
        nb_hors_cible = sum(1 for v in valeurs_kpi if v["statut"] in ("orange", "rouge"))
        lignes.append(
            f"{nb_hors_cible} indicateur(s) sur {len(valeurs_kpi)} hors cible "
            "(statut orange ou rouge)."
        )
    if alertes_periode:
        nb_ouvertes = sum(1 for a in alertes_periode if a["statut"] != "resolue")
        lignes.append(
            f"{len(alertes_periode)} alerte(s) sur la période, dont {nb_ouvertes} encore "
            "non résolue(s)."
        )
    parties = [
        f"{METHODES_COURTES[m]} {formater_nombre(mae, 1)} h"
        for m, lignes_methode in lignes_par_methode.items()
        if (mae := calculer_mae(lignes_methode)) is not None
    ]
    if parties:
        lignes.append("Écart moyen réel/prévu (MAE) : " + ", ".join(parties) + ".")
    if lignes_plan:
        nb_couvertes = sum(
            1
            for l in lignes_plan
            if l["effectif_planifie"] + l["interim_planifie"] >= l["besoin_effectif"]
        )
        lignes.append(
            f"Plan de charge validé : {nb_couvertes} case(s) sur {len(lignes_plan)} "
            "couvrant le besoin en effectif."
        )
    if not lignes:
        lignes.append("Aucune donnée disponible pour cette période.")
    return lignes[:5]


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
    lignes_par_methode = {
        methode: lister_comparaisons(ctx, site_id, None, debut, fin, methode)
        for methode in METHODES
    }
    lignes_plan = lister_plan_valide_periode(ctx, site_id, debut, fin)

    titre = f"Rapport de performance — {site['nom']}"
    sous_titre = (
        f"{libelle(PERIODICITES, periodicite)} du {formater_date(debut)} au "
        f"{formater_date(fin)} — généré par {ctx.identifiant} le {formater_date(date.today())}"
    )
    synthese = _synthese(valeurs_kpi, alertes_periode, lignes_par_methode, lignes_plan)
    entetes_kpi, lignes_kpi = _lignes_kpi(valeurs_kpi)
    entetes_comparaison, lignes_comparaison = _lignes_comparaison(lignes_par_methode)
    entetes_alertes, lignes_alertes = _lignes_alertes(alertes_periode)
    entetes_plan, lignes_plan_tableau = _lignes_plan_charge(lignes_plan)

    nom_base = f"rapport_{site_id}_{periodicite}_{debut.isoformat()}"
    chemin_pdf = chemin_excel = None
    if format_rapport in ("pdf", "pdf_excel"):
        chemin_pdf = f"{nom_base}.pdf"
        ecrire_rapport_pdf(
            DOSSIER_RAPPORTS / chemin_pdf,
            titre,
            sous_titre,
            [
                SectionRapport("Synthèse", texte=synthese),
                SectionRapport(
                    "Indicateurs de performance (KPI)", tableau=(entetes_kpi, lignes_kpi)
                ),
                SectionRapport(
                    "Réel / RL / RN / GB des heures",
                    image=_graphique_reel_methodes(lignes_par_methode),
                ),
                SectionRapport(
                    "Comparaison RL, RN et GB", tableau=(entetes_comparaison, lignes_comparaison)
                ),
                SectionRapport("Alertes de la période", tableau=(entetes_alertes, lignes_alertes)),
                SectionRapport(
                    "Plan de charge validé et écarts", tableau=(entetes_plan, lignes_plan_tableau)
                ),
            ],
        )
    if format_rapport in ("excel", "pdf_excel"):
        chemin_excel = f"{nom_base}.xlsx"
        ecrire_classeur(
            DOSSIER_RAPPORTS / chemin_excel,
            {
                "Synthèse": (["Ligne"], [[ligne] for ligne in synthese]),
                "KPI": (entetes_kpi, lignes_kpi),
                "Réel RL RN GB": _feuille_reel_methodes(lignes_par_methode),
                "Comparaison RL RN GB": (entetes_comparaison, lignes_comparaison),
                "Alertes": (entetes_alertes, lignes_alertes),
                "Plan de charge": (entetes_plan, lignes_plan_tableau),
            },
        )

    contenu = {
        "site": site["nom"],
        "periodicite": periodicite,
        "date_debut": debut.isoformat(),
        "date_fin": fin.isoformat(),
        "kpi": valeurs_kpi,
        "alertes": alertes_periode,
        "synthese": synthese,
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
