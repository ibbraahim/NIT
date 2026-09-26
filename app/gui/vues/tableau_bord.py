"""Écran 5 — Tableau de bord (UC22) : planificateur, responsable, direction."""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.erreurs import ErreurApplication
from app.gui.style import COULEURS, COULEURS_STATUT, COULEURS_STATUT_CLAIR
from app.gui.vues.base import Vue
from app.gui.widgets.champs import ChampListe
from app.gui.widgets.dialogues import afficher_erreur
from app.gui.widgets.graphique import GraphiqueIntegre
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.libelles import FAMILLES_KPI, METHODES_COURTES, NIVEAUX_ALERTE, TYPES_ALERTE, libelle
from app.services import admin, alertes, comparaison, kpi, planification
from app.services.droits import a_le_droit
from app.utils.dates import lundi_de
from app.utils.format_fr import formater_nombre

STATUTS_ATTENTION = ("rouge", "orange")

LIBELLES_STATUT = {"vert": "Conforme", "orange": "Vigilance", "rouge": "Critique"}

# Sélection résumée des 20 KPI pour les tuiles de synthèse (l'écran KPI et cibles couvre les 20).
TUILES_KPI = [
    ("ADEQUATION", "Adéquation de l'effectif"),
    ("TAUX_A_TEMPS", "Commandes à temps"),
    ("MAPE_H", "Précision des prévisions"),
    ("TAUX_DISPO_EQP", "Disponibilité des équipements"),
    ("ECART_COUT", "Écart de coût prévu / réel"),
]

COLONNES_KPI = [
    Colonne("famille_libelle", "Famille", 130),
    Colonne("kpi_libelle", "KPI", 220),
    Colonne("methode_libelle", "Méthode", 70, "center"),
    Colonne("valeur_affichee", "Valeur", 110, "e"),
    Colonne("cible_affichee", "Cible", 110, "e"),
    Colonne("statut_libelle", "Statut", 90, "center"),
]

COLONNES_ALERTES = [
    Colonne("type_libelle", "Type", 170),
    Colonne("niveau_libelle", "Niveau", 80, "center"),
    Colonne("zone", "Zone", 110),
    Colonne("date_concernee", "Date concernée", 110, "center"),
    Colonne("message", "Message", 380),
]


def _formater_valeur(valeur, unite) -> str:
    if valeur is None:
        return "—"
    texte = formater_nombre(valeur, 1)
    return f"{texte} {unite}" if unite else texte


def _etiquette_kpi(ligne: dict) -> str | None:
    return ligne["statut"]


def _etiquette_alerte(ligne: dict) -> str | None:
    return ligne["niveau"]


def _trouver_kpi(valeurs: list[dict], code: str) -> dict | None:
    return next((v for v in valeurs if v["kpi_code"] == code), None)


def _construire_tuile(
    parent: tk.Widget, titre: str, valeur_texte: str, cible_texte: str, statut
) -> ttk.Frame:
    """Une carte KPI colorée selon son statut (vert/orange/rouge/gris)."""
    cadre = ttk.Frame(parent, style="Carte.TFrame", padding=12)
    fond = {"background": COULEURS["surface"]}
    tk.Label(
        cadre, text=titre, font=("", 9, "bold"), foreground=COULEURS["texte_secondaire"], **fond
    ).pack(anchor="w")
    tk.Label(
        cadre, text=valeur_texte, font=("", 20, "bold"), foreground=COULEURS["texte"], **fond
    ).pack(anchor="w", pady=(2, 0))
    tk.Label(
        cadre, text=cible_texte, font=("", 9), foreground=COULEURS["texte_secondaire"], **fond
    ).pack(anchor="w")
    tk.Label(
        cadre,
        text=LIBELLES_STATUT.get(statut, "Non calculé"),
        font=("", 8, "bold"),
        background=COULEURS_STATUT_CLAIR.get(statut, COULEURS["gris_clair"]),
        foreground=COULEURS_STATUT.get(statut, COULEURS["gris"]),
        padx=8,
        pady=2,
    ).pack(anchor="w", pady=(8, 0))
    return cadre


class VueTableauBord(Vue):
    """Vue d'ensemble par site : tuiles KPI, graphiques de synthèse (heures réel/prévu,
    adéquation par zone, disponibilité des équipements), KPI hors cible et alertes ouvertes,
    avec double-clic vers l'écran Alertes (UC18/UC19)."""

    titre = "Tableau de bord"
    sous_titre = "Synthèse et alertes ouvertes, semaine en cours"

    def construire(self) -> None:
        self.voit_les_alertes = a_le_droit(self.ctx, "lecture_alertes")
        self.voit_les_previsions = a_le_droit(self.ctx, "lecture_previsions")
        self.voit_le_plan = a_le_droit(self.ctx, "lecture_plan")

        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 10))
        self.site = ChampListe(barre, "Site", largeur=26)
        self.site.pack(side="left")
        self.site.sur_changement(self.actualiser_donnees)

        self.cadre_tuiles = ttk.Frame(self.contenu)
        self.cadre_tuiles.pack(fill="x", pady=(0, 12))

        cadre_graphiques = ttk.Frame(self.contenu)
        cadre_graphiques.pack(fill="both", pady=(0, 12))
        self.graphique_heures = GraphiqueIntegre(cadre_graphiques, largeur=6, hauteur=2.6)
        self.graphique_heures.pack(side="left", fill="both", expand=True)
        self.graphique_adequation = GraphiqueIntegre(cadre_graphiques, largeur=5, hauteur=2.6)
        self.graphique_adequation.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.graphique_equipements = GraphiqueIntegre(cadre_graphiques, largeur=3.4, hauteur=2.6)
        self.graphique_equipements.pack(side="left", fill="both", expand=True, padx=(12, 0))

        ttk.Label(self.contenu, text="KPI nécessitant une attention", style="Section.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        self.tableau_kpi = TableauTriable(self.contenu, COLONNES_KPI, hauteur=6)
        self.tableau_kpi.pack(fill="both", expand=True)

        self.section_alertes = ttk.Frame(self.contenu)
        ttk.Label(self.section_alertes, text="Alertes ouvertes", style="Section.TLabel").pack(
            anchor="w", pady=(14, 4)
        )
        self.tableau_alertes = TableauTriable(self.section_alertes, COLONNES_ALERTES, hauteur=6)
        self.tableau_alertes.pack(fill="both", expand=True)
        self.tableau_alertes.sur_double_clic(self._ouvrir_alerte)
        if self.voit_les_alertes:
            self.section_alertes.pack(fill="both", expand=True)

    def actualiser(self) -> None:
        sites = self.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self.actualiser_donnees()

    def actualiser_donnees(self) -> None:
        site_id = self.site.valeur()
        if site_id is None:
            for enfant in self.cadre_tuiles.winfo_children():
                enfant.destroy()
            self.graphique_heures.afficher_message("Choisissez un site.")
            self.graphique_adequation.afficher_message("Choisissez un site.")
            self.graphique_equipements.afficher_message("Choisissez un site.")
            self.tableau_kpi.charger([], message_vide="Choisissez un site.")
            self.tableau_alertes.charger([], message_vide="Choisissez un site.")
            return

        valeurs = (
            self.executer(
                lambda: kpi.lister_kpi_valeurs(self.ctx, site_id, None, "semaine", date.today())
            )
            or []
        )

        ouvertes = []
        if self.voit_les_alertes:
            ouvertes = (
                self.executer(lambda: alertes.lister_alertes_ouvertes(self.ctx, site_id)) or []
            )

        self._construire_tuiles(valeurs, ouvertes)
        self._dessiner_graphique_heures(site_id)
        self._dessiner_graphique_adequation(site_id)
        self._dessiner_graphique_equipements(valeurs)

        attention = [v for v in valeurs if v["statut"] in STATUTS_ATTENTION]
        for ligne in attention:
            ligne["famille_libelle"] = libelle(FAMILLES_KPI, ligne["famille"])
            ligne["methode_libelle"] = METHODES_COURTES.get(ligne["methode"], "—")
            ligne["valeur_affichee"] = _formater_valeur(ligne["valeur"], ligne["unite"])
            ligne["cible_affichee"] = _formater_valeur(ligne["cible"], ligne["unite"])
            ligne["statut_libelle"] = "Rouge" if ligne["statut"] == "rouge" else "Orange"
        self.tableau_kpi.charger(
            attention,
            cle_id="id",
            etiquettes=_etiquette_kpi,
            message_vide="Aucun KPI hors cible cette semaine.",
        )

        if not self.voit_les_alertes:
            return
        for ligne in ouvertes:
            ligne["type_libelle"] = libelle(TYPES_ALERTE, ligne["type"])
            ligne["niveau_libelle"] = libelle(NIVEAUX_ALERTE, ligne["niveau"])
        self.tableau_alertes.charger(
            ouvertes,
            cle_id="id",
            etiquettes=_etiquette_alerte,
            message_vide="Aucune alerte ouverte.",
        )

    # --- Tuiles KPI ------------------------------------------------------------
    def _construire_tuiles(self, valeurs: list[dict], ouvertes: list[dict]) -> None:
        for enfant in self.cadre_tuiles.winfo_children():
            enfant.destroy()
        for code, titre in TUILES_KPI:
            trouve = _trouver_kpi(valeurs, code)
            if trouve is None:
                tuile = _construire_tuile(self.cadre_tuiles, titre, "—", "Pas encore calculé", None)
            else:
                tuile = _construire_tuile(
                    self.cadre_tuiles,
                    titre,
                    _formater_valeur(trouve["valeur"], trouve["unite"]),
                    f"Cible {_formater_valeur(trouve['cible'], trouve['unite'])}",
                    trouve["statut"],
                )
            tuile.pack(side="left", fill="both", expand=True, padx=(0, 10))

        if self.voit_les_alertes:
            nb_rouge = sum(1 for a in ouvertes if a["niveau"] == "rouge")
            statut_alertes = "rouge" if nb_rouge else ("orange" if ouvertes else "vert")
            sous_texte = (
                f"Dont {nb_rouge} de niveau rouge" if nb_rouge else "Aucune alerte critique"
            )
            _construire_tuile(
                self.cadre_tuiles,
                "Alertes ouvertes",
                str(len(ouvertes)),
                sous_texte,
                statut_alertes,
            ).pack(side="left", fill="both", expand=True)

    # --- Graphique : heures nécessaires réel / prévu ----------------------------
    def _dessiner_graphique_heures(self, site_id: int) -> None:
        if not self.voit_les_previsions:
            self.graphique_heures.afficher_message(
                "Réservé aux rôles planificateur et responsable."
            )
            return
        fin = date.today() - timedelta(days=1)
        debut = fin - timedelta(days=27)
        rapprochements = (
            self.executer(
                lambda: comparaison.lister_comparaisons(self.ctx, site_id, None, debut, fin)
            )
            or []
        )
        if not rapprochements:
            self.graphique_heures.afficher_message("Pas encore de réalisé comparable.")
            return

        semaines: dict[date, dict[str, float]] = {}
        zones_vues_par_jour: dict[date, set[int]] = {}
        for r in rapprochements:
            semaine = lundi_de(r["date_jour"])
            acc = semaines.setdefault(
                semaine, {"reel": 0.0, "regression_lineaire": 0.0, "reseau_neurones": 0.0}
            )
            acc[r["methode"]] += r["heures_prevues"] or 0.0
            vues = zones_vues_par_jour.setdefault(r["date_jour"], set())
            if r["zone_id"] not in vues and r["heures_reelles"] is not None:
                vues.add(r["zone_id"])
                acc["reel"] += r["heures_reelles"]

        points = sorted(semaines.items())

        nb_semaines = len(points)
        libelles = [
            "S (en cours)" if i == nb_semaines - 1 else f"S-{nb_semaines - 1 - i}"
            for i in range(nb_semaines)
        ]

        def _dessiner(axe):
            axe.plot(
                libelles,
                [v["reel"] for _, v in points],
                marker="o",
                markersize=4,
                color=COULEURS["primaire"],
                label="Réalisé",
            )
            axe.plot(
                libelles,
                [v["regression_lineaire"] for _, v in points],
                marker="o",
                markersize=3,
                color=COULEURS["orange"],
                label="Prévu (RL)",
            )
            axe.plot(
                libelles,
                [v["reseau_neurones"] for _, v in points],
                marker="o",
                markersize=3,
                color=COULEURS["vert"],
                label="Prévu (RN)",
            )
            axe.set_ylabel("Heures / semaine")
            axe.legend(fontsize=7, loc="upper left")
            axe.set_title("Heures nécessaires — réalisé et prévu", fontsize=9, loc="left")

        self.graphique_heures.dessiner(_dessiner)

    # --- Graphique : adéquation par zone -----------------------------------------
    def _dessiner_graphique_adequation(self, site_id: int) -> None:
        if not self.voit_le_plan:
            self.graphique_adequation.afficher_message(
                "Réservé aux rôles planificateur et responsable."
            )
            return
        # ``None`` (pas encore de plan) est une réponse valide qu'il ne faut pas confondre avec
        # un succès sans donnée : appelé hors de ``self.executer`` pour cette raison.
        try:
            plan_donnees = planification.lire_plan_charge(self.ctx, site_id, lundi_de(date.today()))
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        if not plan_donnees or not plan_donnees["lignes"]:
            self.graphique_adequation.afficher_message("Aucun plan de charge cette semaine.")
            return

        par_zone: dict[str, list[float]] = {}
        for ligne in plan_donnees["lignes"]:
            valeur = planification.adequation_ligne(ligne)
            if valeur is None or valeur == float("inf"):
                continue
            par_zone.setdefault(ligne["zone"], []).append(valeur)
        if not par_zone:
            self.graphique_adequation.afficher_message("Aucune donnée d'adéquation exploitable.")
            return
        moyennes = {zone: sum(v) / len(v) for zone, v in par_zone.items()}

        def _dessiner(axe):
            zones = list(moyennes)
            valeurs_zones = [moyennes[z] for z in zones]
            couleurs = [
                COULEURS[
                    {"vert": "vert", "orange": "orange", "rouge": "rouge"}[
                        kpi.statut_plage(v, 95, 105, 5)
                    ]
                ]
                for v in valeurs_zones
            ]
            axe.bar(zones, valeurs_zones, color=couleurs)
            axe.axhline(100, color=COULEURS["gris"], linestyle="--", linewidth=1)
            axe.set_ylabel("Adéquation (%)")
            axe.set_title("Adéquation de l'effectif par zone", fontsize=9, loc="left")
            axe.tick_params(axis="x", labelsize=7)

        self.graphique_adequation.dessiner(_dessiner)

    # --- Graphique : disponibilité des équipements (jauge) -----------------------
    def _dessiner_graphique_equipements(self, valeurs: list[dict]) -> None:
        trouve = _trouver_kpi(valeurs, "TAUX_DISPO_EQP")
        if trouve is None or trouve["valeur"] is None:
            self.graphique_equipements.afficher_message("Disponibilité non calculée.")
            return
        valeur = max(0.0, min(100.0, trouve["valeur"]))
        couleur = COULEURS[
            {"vert": "vert", "orange": "orange", "rouge": "rouge"}.get(trouve["statut"], "gris")
        ]

        def _dessiner(axe):
            axe.pie(
                [valeur, 100 - valeur],
                colors=[couleur, COULEURS["gris_clair"]],
                startangle=90,
                counterclock=False,
                wedgeprops={"width": 0.35, "edgecolor": COULEURS["surface"]},
            )
            axe.text(
                0,
                0,
                f"{formater_nombre(valeur, 0)} %",
                ha="center",
                va="center",
                fontsize=13,
                fontweight="bold",
                color=COULEURS["texte"],
            )
            axe.set_title("Disponibilité des équipements", fontsize=9, loc="left")
            axe.set_aspect("equal")

        self.graphique_equipements.dessiner(_dessiner)

    def _ouvrir_alerte(self, ligne: dict) -> None:
        self.application.naviguer("alertes", alerte_id=ligne["id"])
