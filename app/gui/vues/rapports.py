"""Écran 9 — Rapports (UC23, UC24) : responsable."""

from __future__ import annotations

import shutil
from datetime import date
from tkinter import ttk

from app.erreurs import ErreurApplication
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampDate, ChampListe
from app.gui.widgets.dialogues import afficher_erreur, choisir_fichier_a_enregistrer, informer
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.taches_fond import executer_en_fond
from app.libelles import PERIODICITES, libelle
from app.services import admin, rapports
from app.services.droits import a_le_droit
from app.utils.format_fr import formater_date, formater_date_heure

OPTIONS_PERIODICITE = list(PERIODICITES.items())
OPTIONS_FORMAT = [("pdf_excel", "PDF et Excel"), ("pdf", "PDF seul"), ("excel", "Excel seul")]

COLONNES_TABLEAU = [
    Colonne("periodicite_libelle", "Périodicité", 110),
    Colonne("periode", "Période", 210),
    Colonne("genere_par_libelle", "Généré par", 150),
    Colonne("date_generation", "Date de génération", 150, "center", formateur=formater_date_heure),
    Colonne("formats_disponibles", "Fichiers", 120, "center"),
]


class VueRapports(Vue):
    """Filtres Site/Périodicité/Date/Format, génération (UC23), table des rapports déjà
    générés, export (UC24)."""

    titre = "Rapports"
    sous_titre = "Rapports de performance périodiques (KPI et alertes)"

    def construire(self) -> None:
        self.peut_generer = a_le_droit(self.ctx, "UC23")
        self.peut_exporter = a_le_droit(self.ctx, "UC24")

        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 10))
        self.site = ChampListe(barre, "Site", largeur=22)
        self.site.pack(side="left")
        self.site.sur_changement(self.actualiser_donnees)
        self.periodicite = ChampListe(barre, "Périodicité", options=OPTIONS_PERIODICITE, largeur=14)
        self.periodicite.definir("semaine")
        self.periodicite.pack(side="left", padx=(16, 0))
        self.date_reference = ChampDate(barre, "Date de référence")
        self.date_reference.definir(date.today())
        self.date_reference.pack(side="left", padx=(16, 0))
        self.format = ChampListe(barre, "Format", options=OPTIONS_FORMAT, largeur=16)
        self.format.pack(side="left", padx=(16, 0))

        boutons = ttk.Frame(barre)
        boutons.pack(side="left", padx=(24, 0), pady=(14, 0))
        self.b_generer = Bouton(boutons, "Générer un rapport", self.generer, primaire=True)
        self.b_generer.pack(side="left")
        if not self.peut_generer:
            self.b_generer.pack_forget()

        corps = ttk.Frame(self.contenu)
        corps.pack(fill="both", expand=True)
        self.tableau = TableauTriable(corps, COLONNES_TABLEAU, hauteur=14)
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self._sur_selection)

        actions = ttk.Frame(self.contenu)
        actions.pack(fill="x", pady=(10, 0))
        self.b_exporter_pdf = Bouton(actions, "Exporter en PDF…", self.exporter_pdf)
        self.b_exporter_pdf.pack(side="left")
        self.b_exporter_excel = Bouton(actions, "Exporter en Excel…", self.exporter_excel)
        self.b_exporter_excel.pack(side="left", padx=(8, 0))
        if not self.peut_exporter:
            self.b_exporter_pdf.pack_forget()
            self.b_exporter_excel.pack_forget()
        self._desactiver_export()

    def actualiser(self) -> None:
        sites = self.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self.actualiser_donnees()

    def actualiser_donnees(self) -> None:
        site_id = self.site.valeur()
        self.b_generer.activer(
            self.peut_generer and site_id is not None, "Choisissez d'abord un site."
        )
        if site_id is None:
            self.tableau.charger([], message_vide="Choisissez un site.")
            self._desactiver_export()
            return
        lignes = self.executer(lambda: rapports.lister_rapports(self.ctx, site_id)) or []
        for ligne in lignes:
            ligne["periodicite_libelle"] = libelle(PERIODICITES, ligne["periodicite"])
            ligne["periode"] = (
                f"{formater_date(ligne['date_debut'])} – {formater_date(ligne['date_fin'])}"
            )
            ligne["genere_par_libelle"] = (
                "Tâche planifiée"
                if ligne["genere_par_systeme"]
                else (ligne["genere_par_identifiant"] or "—")
            )
            formats = []
            if ligne["chemin_pdf"]:
                formats.append("PDF")
            if ligne["chemin_excel"]:
                formats.append("Excel")
            ligne["formats_disponibles"] = " + ".join(formats) or "—"
        self.tableau.charger(lignes, cle_id="id", message_vide="Aucun rapport généré pour ce site.")
        self._desactiver_export()

    def _sur_selection(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        self.b_exporter_pdf.activer(
            self.peut_exporter and ligne is not None and bool(ligne["chemin_pdf"]),
            "Sélectionnez un rapport avec un fichier PDF.",
        )
        self.b_exporter_excel.activer(
            self.peut_exporter and ligne is not None and bool(ligne["chemin_excel"]),
            "Sélectionnez un rapport avec un fichier Excel.",
        )

    def _desactiver_export(self) -> None:
        self.b_exporter_pdf.activer(False, "Sélectionnez un rapport avec un fichier PDF.")
        self.b_exporter_excel.activer(False, "Sélectionnez un rapport avec un fichier Excel.")

    def generer(self) -> None:
        site_id = self.site.valeur()
        periodicite = self.periodicite.valeur()
        format_rapport = self.format.valeur()
        if site_id is None:
            return
        try:
            date_reference = self.date_reference.valeur()
        except ValueError as exc:
            afficher_erreur(self, str(exc))
            return

        def traiter(_progression):
            return rapports.generer_rapport(
                self.ctx, site_id, periodicite, date_reference, format_rapport
            )

        def succes(_resultat):
            self.actualiser_donnees()
            informer(self, "Rapport généré.", "Génération terminée")

        executer_en_fond(
            self,
            traiter,
            succes,
            titre="Génération du rapport",
            message="Calcul des KPI et recensement des alertes de la période…",
        )

    def _exporter(self, format_fichier: str, titre: str, types: list[tuple[str, str]]) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None:
            return
        try:
            source = rapports.exporter_rapport(self.ctx, ligne["id"], format_fichier)
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        destination = choisir_fichier_a_enregistrer(self, source.name, titre, types)
        if destination is None:
            return
        shutil.copyfile(source, destination)
        informer(self, f"Rapport enregistré : {destination.name}")

    def exporter_pdf(self) -> None:
        self._exporter("pdf", "Exporter en PDF", [("Document PDF", "*.pdf")])

    def exporter_excel(self) -> None:
        self._exporter("excel", "Exporter en Excel", [("Classeur Excel", "*.xlsx")])
