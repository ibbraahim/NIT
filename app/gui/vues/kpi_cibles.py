"""Écran 7 — KPI et cibles (UC15, UC16, UC17) : responsable."""

from __future__ import annotations

from datetime import date
from tkinter import ttk

from app.erreurs import DonneesInvalides, ErreurApplication, OperationImpossible
from app.gui.style import PUCE_STATUT
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.carte import Carte, ajouter_carte
from app.gui.widgets.champs import ChampCase, ChampDate, ChampListe, ChampNombre, appliquer_erreurs
from app.gui.widgets.dialogues import DialogueBase, afficher_erreur, confirmer, informer
from app.gui.widgets.onglets import Onglets
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.taches_fond import executer_en_fond
from app.libelles import FAMILLES_KPI, METHODES_COURTES, PERIODICITES, STATUTS_KPI, libelle
from app.services import admin, kpi, recommandations
from app.services.droits import a_le_droit
from app.utils.format_fr import formater_nombre

OPTION_TOUTE_FAMILLE = (None, "Toutes les familles")
OPTIONS_FAMILLE = [OPTION_TOUTE_FAMILLE] + list(FAMILLES_KPI.items())
OPTIONS_PERIODICITE = list(PERIODICITES.items())
OPTION_TOUS_SITES = (None, "Tous les sites (cible générale)")
OPTION_TOUTES_ZONES_SITE = (None, "Toutes les zones du site")

COLONNES_TABLEAU = [
    Colonne("kpi_libelle", "KPI", 300),
    Colonne("famille_libelle", "Famille", 130),
    Colonne("methode_libelle", "Méthode", 70, "center"),
    Colonne("valeur_affichee", "Valeur", 110, "e"),
    Colonne("cible_affichee", "Cible", 110, "e"),
    Colonne("statut_libelle", "Statut", 100, "center"),
    Colonne("tendance", "Tendance", 70, "center"),
]

COLONNES_CIBLES = [
    Colonne("kpi_code", "KPI", 100),
    Colonne("portee", "Portée", 200),
    Colonne("periodicite_libelle", "Périodicité", 100),
    Colonne("valeur_cible", "Cible", 90, "e", formateur=lambda v: formater_nombre(v, 2)),
    Colonne("seuil_orange", "Seuil orange", 100, "e", formateur=lambda v: formater_nombre(v, 2)),
    Colonne("seuil_rouge", "Seuil rouge", 100, "e", formateur=lambda v: formater_nombre(v, 2)),
]


def _formater_valeur(valeur, unite) -> str:
    if valeur is None:
        return "—"
    texte = formater_nombre(valeur, 1)
    return f"{texte} {unite}" if unite else texte


def _etiquette_statut(ligne: dict) -> str | None:
    return ligne["statut"]


class VueKpiCibles(Vue):
    """Onglets « Suivi des KPI » (UC16/UC17) et « Cibles » (UC15)."""

    titre = "KPI et cibles"
    sous_titre = "Suivi des 20 indicateurs et de leurs objectifs"

    def construire(self) -> None:
        self.onglets = Onglets(self.contenu)
        self.onglets.pack(fill="both", expand=True)
        self.page_suivi = OngletSuiviKpi(self.onglets, self)
        self.onglets.add(self.page_suivi, text="Suivi des KPI")
        self.page_cibles = OngletCibles(self.onglets, self)
        self.onglets.add(self.page_cibles, text="Cibles")

    def actualiser(self) -> None:
        self.page_suivi.actualiser()
        self.page_cibles.actualiser()


# =====================================================================
# Onglet « Suivi des KPI » (UC16, UC17)
# =====================================================================
class OngletSuiviKpi(ttk.Frame):
    """Filtres Site/Zone/Périodicité/Date, bouton de calcul, tableau des KPI."""

    def __init__(self, parent, vue: VueKpiCibles) -> None:
        super().__init__(parent, style="Page.TFrame")
        self.vue = vue
        self.ctx = vue.ctx
        self.peut_calculer = a_le_droit(self.ctx, "UC17")
        self._lignes: list[dict] = []
        self._construire()

    def _construire(self) -> None:
        carte_filtres = ajouter_carte(self, marge=14)
        barre = carte_filtres.zone
        self.site = ChampListe(barre, "Site", largeur=20)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(barre, "Zone", largeur=16)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_donnees)
        self.periodicite = ChampListe(barre, "Périodicité", options=OPTIONS_PERIODICITE, largeur=11)
        self.periodicite.definir("semaine")
        self.periodicite.pack(side="left", padx=(16, 0))
        self.periodicite.sur_changement(self.actualiser_donnees)
        self.date_reference = ChampDate(barre, "Date de référence")
        self.date_reference.definir(date.today())
        self.date_reference.pack(side="left", padx=(16, 0))
        self.date_reference.sur_changement(self.actualiser_donnees)
        self.famille = ChampListe(barre, "Famille", options=OPTIONS_FAMILLE, largeur=18)
        self.famille.pack(side="left", padx=(16, 0))
        self.famille.sur_changement(self._filtrer_tableau)

        carte = ajouter_carte(
            self, "Indicateurs", "Sélectionnez un indicateur en alerte pour lire l'explication"
        )
        self.b_calculer = Bouton(
            carte.actions, "Calculer et comparer maintenant", self.calculer, primaire=True
        )
        self.b_calculer.pack(side="left")
        if not self.peut_calculer:
            self.b_calculer.pack_forget()
        self.tableau = TableauTriable(carte.zone, COLONNES_TABLEAU, hauteur=14)
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self._sur_selection_kpi)

        self.cadre_interpretation = Carte(self, marge=16)
        self.label_explication = ttk.Label(
            self.cadre_interpretation.zone, text="", style="Section.TLabel", wraplength=900
        )
        self.label_explication.pack(anchor="w")
        self.label_conseil = ttk.Label(self.cadre_interpretation.zone, text="", wraplength=900)
        self.label_conseil.pack(anchor="w", pady=(4, 0))
        self.cadre_interpretation.pack_forget()

    def _sur_selection_kpi(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        interpretation = (
            recommandations.interpreter_kpi(
                ligne["kpi_code"], ligne["sens"], ligne["valeur"], ligne["cible"]
            )
            if ligne is not None and ligne["statut"] in ("orange", "rouge")
            else None
        )
        if interpretation is None:
            self.cadre_interpretation.pack_forget()
            return
        self.label_explication.configure(text=interpretation.explication)
        self.label_conseil.configure(text=f"Action suggérée — {interpretation.conseil}")
        self.cadre_interpretation.pack(fill="x")

    def actualiser(self) -> None:
        sites = self.vue.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self._sur_changement_site()

    def _sur_changement_site(self) -> None:
        site_id = self.site.valeur()
        zones = (
            self.vue.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
            if site_id is not None
            else []
        )
        self.zone.definir_options(
            [(None, "Toutes les zones")] + [(z["id"], z["nom"]) for z in zones], conserver=False
        )
        self.actualiser_donnees()

    def _date_reference(self) -> date | None:
        try:
            return self.date_reference.valeur()
        except ValueError:
            return None

    def actualiser_donnees(self) -> None:
        site_id, zone_id = self.site.valeur(), self.zone.valeur()
        periodicite = self.periodicite.valeur()
        date_reference = self._date_reference()
        self.b_calculer.activer(
            self.peut_calculer and site_id is not None, "Choisissez d'abord un site."
        )
        if site_id is None or date_reference is None:
            self.tableau.charger([], message_vide="Choisissez un site.")
            self._lignes = []
            return
        lignes = (
            self.vue.executer(
                lambda: kpi.lister_kpi_valeurs(
                    self.ctx, site_id, zone_id, periodicite, date_reference
                )
            )
            or []
        )
        for ligne in lignes:
            ligne["famille_libelle"] = libelle(FAMILLES_KPI, ligne["famille"])
            ligne["methode_libelle"] = METHODES_COURTES.get(ligne["methode"], "—")
            ligne["valeur_affichee"] = _formater_valeur(ligne["valeur"], ligne["unite"])
            ligne["cible_affichee"] = _formater_valeur(ligne["cible"], ligne["unite"])
            ligne["statut_libelle"] = f"{PUCE_STATUT} {libelle(STATUTS_KPI, ligne['statut'])}"
        self._lignes = lignes
        self._filtrer_tableau()

    def _filtrer_tableau(self) -> None:
        famille = self.famille.valeur()
        lignes = [l for l in self._lignes if famille is None or l["famille"] == famille]
        self.tableau.charger(
            lignes,
            cle_id="id",
            etiquettes=_etiquette_statut,
            message_vide="Aucun KPI calculé pour cette période. "
            "Utilisez « Calculer et comparer maintenant ».",
        )
        self._sur_selection_kpi()

    def calculer(self) -> None:
        site_id, zone_id = self.site.valeur(), self.zone.valeur()
        periodicite = self.periodicite.valeur()
        date_reference = self._date_reference()
        if site_id is None or date_reference is None:
            return

        def traiter(_progression):
            return kpi.comparer_kpi_cibles(self.ctx, site_id, zone_id, periodicite, date_reference)

        def succes(_resultat):
            self.actualiser_donnees()
            informer(self.vue, "KPI calculés et comparés à leurs cibles.", "Calcul terminé")

        executer_en_fond(
            self.vue, traiter, succes, titre="Calcul des KPI", message="Calcul des indicateurs…"
        )


# =====================================================================
# Onglet « Cibles » (UC15)
# =====================================================================
class OngletCibles(ttk.Frame):
    """Tableau des objectifs (tous sites) ; Ajouter / Modifier / Supprimer une cible."""

    def __init__(self, parent, vue: VueKpiCibles) -> None:
        super().__init__(parent, style="Page.TFrame")
        self.vue = vue
        self.ctx = vue.ctx
        self.peut_definir_cibles = a_le_droit(self.ctx, "UC15")
        self._construire()

    def _construire(self) -> None:
        carte = ajouter_carte(
            self, "Cibles", "Objectifs par KPI, par site ou par zone", dernier=True
        )
        boutons = carte.actions
        self.b_ajouter = Bouton(boutons, "Ajouter une cible", self._ajouter, primaire=True)
        self.b_ajouter.pack(side="left")
        self.b_modifier = Bouton(boutons, "Modifier la cible", self._modifier)
        self.b_modifier.pack(side="left", padx=(8, 0))
        self.b_modifier.activer(False, "Sélectionnez d'abord une cible.")
        self.b_supprimer = Bouton(boutons, "Supprimer la cible", self._supprimer)
        self.b_supprimer.pack(side="left", padx=(8, 0))
        self.b_supprimer.activer(False, "Sélectionnez d'abord une cible.")
        if not self.peut_definir_cibles:
            self.b_ajouter.pack_forget()
            self.b_modifier.pack_forget()
            self.b_supprimer.pack_forget()

        self.tableau = TableauTriable(carte.zone, COLONNES_CIBLES, hauteur=14)
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self._sur_selection)

    def _sur_selection(self) -> None:
        actif = self.peut_definir_cibles and self.tableau.ligne_selectionnee() is not None
        self.b_modifier.activer(actif, "Sélectionnez d'abord une cible.")
        self.b_supprimer.activer(actif, "Sélectionnez d'abord une cible.")

    def actualiser(self) -> None:
        objectifs = self.vue.executer(lambda: kpi.lister_objectifs(self.ctx, None)) or []
        for o in objectifs:
            if o["site_id"] is None:
                o["portee"] = "Général (tous les sites)"
            elif o["zone_id"] is None:
                o["portee"] = f"{o['site']} (toutes zones)"
            else:
                o["portee"] = f"{o['site']} — {o['zone']}"
            o["periodicite_libelle"] = libelle(PERIODICITES, o["periodicite"])
        self.tableau.charger(objectifs, cle_id="id", message_vide="Aucune cible définie.")
        self._sur_selection()

    def _ajouter(self) -> None:
        if FenetreObjectif(self.vue, self.ctx).afficher():
            self.actualiser()

    def _modifier(self) -> None:
        objectif = self.tableau.ligne_selectionnee()
        if objectif is None:
            return
        if FenetreObjectif(self.vue, self.ctx, objectif=objectif).afficher():
            self.actualiser()

    def _supprimer(self) -> None:
        objectif = self.tableau.ligne_selectionnee()
        if objectif is None:
            return
        if not confirmer(self.vue, "Supprimer cette cible ?", "Supprimer la cible"):
            return
        try:
            kpi.supprimer_objectif(self.ctx, objectif["id"])
        except (ErreurApplication, OperationImpossible) as exc:
            afficher_erreur(self.vue, exc.message)
            return
        self.actualiser()
        informer(self.vue, "Cible supprimée.")


class FenetreObjectif(DialogueBase):
    """Formulaire d'ajout ou de modification d'une cible (UC15)."""

    def __init__(self, parent, ctx, objectif: dict | None = None) -> None:
        titre = "Modifier la cible" if objectif else "Ajouter une cible"
        super().__init__(parent, titre, redimensionnable=False)
        self.ctx = ctx
        self.objectif = objectif
        self._construire()

    def _construire(self) -> None:
        try:
            definitions = [
                d for d in kpi.lister_definitions(self.ctx) if d["sens"] != "information"
            ]
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            definitions = []
        try:
            sites = admin.lister_sites(self.ctx)
        except ErreurApplication:
            sites = []

        formulaire = ttk.Frame(self.corps)
        formulaire.pack(fill="x")
        self.kpi = ChampListe(
            formulaire,
            "KPI",
            options=[(d["id"], f"{d['code']} — {d['libelle']}") for d in definitions],
        )
        self.kpi.grid(row=0, column=0, columnspan=2, sticky="w", padx=(0, 16))
        self.periodicite = ChampListe(
            formulaire, "Périodicité", options=OPTIONS_PERIODICITE, largeur=14
        )
        self.periodicite.grid(row=0, column=2, sticky="w")

        self.site = ChampListe(
            formulaire,
            "Site",
            options=[OPTION_TOUS_SITES] + [(s["id"], s["nom"]) for s in sites],
            largeur=24,
        )
        self.site.definir(None)
        self.site.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.site.sur_changement(self._charger_zones)
        self.zone = ChampListe(formulaire, "Zone")
        self.zone.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._charger_zones()

        ttk.Label(
            self.corps,
            text="Seuils : selon le sens du KPI, renseignez la cible et les seuils orange/"
            "rouge (hausse/baisse), ou le minimum/maximum et la marge orange (plage).",
            style="Aide.TLabel",
            wraplength=440,
        ).pack(anchor="w", pady=(14, 4))

        seuils = ttk.Frame(self.corps)
        seuils.pack(fill="x")
        self.widgets = {
            "valeur_cible": ChampNombre(seuils, "Valeur cible", decimales=2),
            "seuil_orange": ChampNombre(seuils, "Seuil orange / marge", decimales=2),
            "seuil_rouge": ChampNombre(seuils, "Seuil rouge", decimales=2),
            "valeur_min": ChampNombre(seuils, "Valeur minimum", decimales=2),
            "valeur_max": ChampNombre(seuils, "Valeur maximum", decimales=2),
        }
        for i, champ in enumerate(self.widgets.values()):
            champ.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 16), pady=(0, 10))
        self.seuils_relatifs = ChampCase(
            self.corps, "Seuils relatifs (% de la moyenne des 90 premiers jours)"
        )
        self.seuils_relatifs.pack(anchor="w")

        if self.objectif:
            self.kpi.definir(self.objectif["kpi_id"])
            self.kpi.activer(False)
            self.periodicite.definir(self.objectif["periodicite"])
            self.periodicite.activer(False)
            self.site.definir(self.objectif["site_id"])
            self.site.activer(False)
            self._charger_zones()
            self.zone.definir(self.objectif["zone_id"])
            self.zone.activer(False)
            for champ, cle in (
                (self.widgets["valeur_cible"], "valeur_cible"),
                (self.widgets["seuil_orange"], "seuil_orange"),
                (self.widgets["seuil_rouge"], "seuil_rouge"),
                (self.widgets["valeur_min"], "valeur_min"),
                (self.widgets["valeur_max"], "valeur_max"),
            ):
                champ.definir(self.objectif[cle])
            self.seuils_relatifs.definir(self.objectif["seuils_relatifs"])

        self.ajouter_bouton("Annuler", self.fermer)
        self.ajouter_bouton("Enregistrer", self._enregistrer, primaire=True, defaut=True)

    def _charger_zones(self) -> None:
        site_id = self.site.valeur()
        if site_id is None:
            self.zone.definir_options([(None, "—")], conserver=False)
            self.zone.activer(False)
            return
        try:
            zones = admin.lister_zones(self.ctx, site_id)
        except ErreurApplication:
            zones = []
        self.zone.definir_options(
            [OPTION_TOUTES_ZONES_SITE] + [(z["id"], z["nom"]) for z in zones], conserver=False
        )
        self.zone.activer(True)

    def _enregistrer(self) -> None:
        for champ in self.widgets.values():
            champ.effacer_erreur()
        kpi_id = self.kpi.valeur()
        if kpi_id is None:
            afficher_erreur(self, "Choisissez un KPI.")
            return
        site_id = self.site.valeur()
        zone_id = None if site_id is None else self.zone.valeur()
        configuration = {
            "valeur_cible": self.widgets["valeur_cible"].valeur(),
            "seuil_orange": self.widgets["seuil_orange"].valeur(),
            "seuil_rouge": self.widgets["seuil_rouge"].valeur(),
            "valeur_min": self.widgets["valeur_min"].valeur(),
            "valeur_max": self.widgets["valeur_max"].valeur(),
            "seuils_relatifs": self.seuils_relatifs.valeur(),
        }
        try:
            kpi.definir_objectif(
                self.ctx,
                kpi_id,
                site_id,
                zone_id,
                self.periodicite.valeur(),
                configuration,
                objectif_id=self.objectif["id"] if self.objectif else None,
            )
        except DonneesInvalides as exc:
            appliquer_erreurs(self.widgets, exc.erreurs)
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.fermer(True)
