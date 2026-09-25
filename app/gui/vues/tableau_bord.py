"""Écran 5 — Tableau de bord (UC22) : planificateur, responsable, direction."""

from __future__ import annotations

from datetime import date
from tkinter import ttk

from app.gui.vues.base import Vue
from app.gui.widgets.champs import ChampListe
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.libelles import FAMILLES_KPI, METHODES_COURTES, NIVEAUX_ALERTE, TYPES_ALERTE, libelle
from app.services import admin, alertes, kpi
from app.services.droits import a_le_droit
from app.utils.format_fr import formater_nombre

STATUTS_ATTENTION = ("rouge", "orange")

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


class VueTableauBord(Vue):
    """Vue d'ensemble par site : KPI nécessitant une attention (orange/rouge) et alertes
    ouvertes, avec double-clic vers l'écran Alertes (UC18/UC19)."""

    titre = "Tableau de bord"
    sous_titre = "KPI hors cible et alertes ouvertes, semaine en cours"

    def construire(self) -> None:
        self.voit_les_alertes = a_le_droit(self.ctx, "lecture_alertes")

        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 10))
        self.site = ChampListe(barre, "Site", largeur=26)
        self.site.pack(side="left")
        self.site.sur_changement(self.actualiser_donnees)

        ttk.Label(self.contenu, text="KPI nécessitant une attention", style="Section.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        self.tableau_kpi = TableauTriable(self.contenu, COLONNES_KPI, hauteur=8)
        self.tableau_kpi.pack(fill="both", expand=True)

        self.section_alertes = ttk.Frame(self.contenu)
        ttk.Label(self.section_alertes, text="Alertes ouvertes", style="Section.TLabel").pack(
            anchor="w", pady=(14, 4)
        )
        self.tableau_alertes = TableauTriable(self.section_alertes, COLONNES_ALERTES, hauteur=8)
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
            self.tableau_kpi.charger([], message_vide="Choisissez un site.")
            self.tableau_alertes.charger([], message_vide="Choisissez un site.")
            return

        valeurs = (
            self.executer(
                lambda: kpi.lister_kpi_valeurs(self.ctx, site_id, None, "semaine", date.today())
            )
            or []
        )
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
        ouvertes = self.executer(lambda: alertes.lister_alertes_ouvertes(self.ctx, site_id)) or []
        for ligne in ouvertes:
            ligne["type_libelle"] = libelle(TYPES_ALERTE, ligne["type"])
            ligne["niveau_libelle"] = libelle(NIVEAUX_ALERTE, ligne["niveau"])
        self.tableau_alertes.charger(
            ouvertes,
            cle_id="id",
            etiquettes=_etiquette_alerte,
            message_vide="Aucune alerte ouverte.",
        )

    def _ouvrir_alerte(self, ligne: dict) -> None:
        self.application.naviguer("alertes", alerte_id=ligne["id"])
