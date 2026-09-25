"""Écran 7 — KPI et cibles (UC15, UC16, UC17) : responsable."""

from __future__ import annotations

from datetime import date
from tkinter import ttk

from app.erreurs import DonneesInvalides, ErreurApplication, OperationImpossible
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampCase, ChampDate, ChampListe, ChampNombre, appliquer_erreurs
from app.gui.widgets.dialogues import DialogueBase, afficher_erreur, confirmer, informer
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.taches_fond import executer_en_fond
from app.libelles import FAMILLES_KPI, METHODES_COURTES, PERIODICITES, STATUTS_KPI, libelle
from app.services import admin, kpi
from app.services.droits import a_le_droit
from app.utils.format_fr import formater_nombre

OPTION_TOUTE_FAMILLE = (None, "Toutes les familles")
OPTIONS_FAMILLE = [OPTION_TOUTE_FAMILLE] + list(FAMILLES_KPI.items())
OPTIONS_PERIODICITE = list(PERIODICITES.items())

COLONNES_TABLEAU = [
    Colonne("famille_libelle", "Famille", 130),
    Colonne("kpi_libelle", "KPI", 220),
    Colonne("methode_libelle", "Méthode", 70, "center"),
    Colonne("valeur_affichee", "Valeur", 110, "e"),
    Colonne("cible_affichee", "Cible", 110, "e"),
    Colonne("tendance", "Tendance", 70, "center"),
    Colonne("statut_libelle", "Statut", 100, "center"),
]

COLONNES_CIBLES = [
    Colonne("kpi_code", "KPI", 100),
    Colonne("portee", "Portée", 160),
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
    """Filtres Site/Zone/Périodicité/Date, calcul (UC16/UC17), tableau des KPI, gestion des
    cibles (UC15)."""

    titre = "KPI et cibles"
    sous_titre = "Suivi des 20 indicateurs et de leurs objectifs"

    def construire(self) -> None:
        self.peut_calculer = a_le_droit(self.ctx, "UC17")
        self.peut_definir_cibles = a_le_droit(self.ctx, "UC15")

        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 10))
        self.site = ChampListe(barre, "Site", largeur=22)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(barre, "Zone", largeur=18)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_donnees)
        self.periodicite = ChampListe(barre, "Périodicité", options=OPTIONS_PERIODICITE, largeur=14)
        self.periodicite.definir("semaine")
        self.periodicite.pack(side="left", padx=(16, 0))
        self.periodicite.sur_changement(self.actualiser_donnees)
        self.date_reference = ChampDate(barre, "Date de référence")
        self.date_reference.definir(date.today())
        self.date_reference.pack(side="left", padx=(16, 0))
        self.date_reference.sur_changement(self.actualiser_donnees)

        barre2 = ttk.Frame(self.contenu)
        barre2.pack(fill="x", pady=(0, 10))
        self.famille = ChampListe(barre2, "Famille", options=OPTIONS_FAMILLE, largeur=22)
        self.famille.pack(side="left")
        self.famille.sur_changement(self._filtrer_tableau)

        boutons = ttk.Frame(barre2)
        boutons.pack(side="left", padx=(24, 0), pady=(14, 0))
        self.b_calculer = Bouton(boutons, "Calculer les KPI", self.calculer, primaire=True)
        self.b_calculer.pack(side="left")
        if not self.peut_calculer:
            self.b_calculer.pack_forget()
        self.b_cibles = Bouton(boutons, "Gérer les cibles…", self.ouvrir_cibles)
        self.b_cibles.pack(side="left", padx=(8, 0))
        if not self.peut_definir_cibles:
            self.b_cibles.pack_forget()

        corps = ttk.Frame(self.contenu)
        corps.pack(fill="both", expand=True)
        self.tableau = TableauTriable(corps, COLONNES_TABLEAU, hauteur=16)
        self.tableau.pack(fill="both", expand=True)
        self._lignes: list[dict] = []

    def actualiser(self) -> None:
        sites = self.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self._sur_changement_site()

    def _sur_changement_site(self) -> None:
        site_id = self.site.valeur()
        zones = (
            self.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
            if site_id is not None
            else []
        )
        self.zone.definir_options(
            [(None, "Toutes les zones")] + [(z["id"], z["nom"]) for z in zones], conserver=False
        )
        self.b_cibles.activer(
            self.peut_definir_cibles and site_id is not None, "Choisissez d'abord un site."
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
            self.executer(
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
            ligne["statut_libelle"] = libelle(STATUTS_KPI, ligne["statut"])
        self._lignes = lignes
        self._filtrer_tableau()

    def _filtrer_tableau(self) -> None:
        famille = self.famille.valeur()
        lignes = [l for l in self._lignes if famille is None or l["famille"] == famille]
        self.tableau.charger(
            lignes,
            cle_id="id",
            etiquettes=_etiquette_statut,
            message_vide="Aucun KPI calculé pour cette période. Utilisez « Calculer les KPI ».",
        )

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
            informer(self, "KPI calculés et comparés à leurs cibles.", "Calcul terminé")

        executer_en_fond(
            self, traiter, succes, titre="Calcul des KPI", message="Calcul des indicateurs…"
        )

    def ouvrir_cibles(self) -> None:
        site_id = self.site.valeur()
        if site_id is None:
            return
        FenetreCibles(self, self.ctx, site_id).afficher()
        self.actualiser_donnees()


# =====================================================================
# UC15 · Gestion des cibles
# =====================================================================
class FenetreCibles(DialogueBase):
    """Liste des cibles applicables au site (générales, du site, par zone) ; Ajouter /
    Modifier / Supprimer."""

    def __init__(self, parent, ctx, site_id: int) -> None:
        super().__init__(parent, "Gérer les cibles", redimensionnable=True)
        self.ctx = ctx
        self.site_id = site_id

        self.tableau = TableauTriable(self.corps, COLONNES_CIBLES, hauteur=12)
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self._sur_selection)

        self.ajouter_bouton("Fermer", self.fermer)
        self.b_supprimer = self.ajouter_bouton("Supprimer la cible sélectionnée", self._supprimer)
        self.b_supprimer.state(["disabled"])
        self.b_modifier = self.ajouter_bouton("Modifier la cible sélectionnée", self._modifier)
        self.b_modifier.state(["disabled"])
        self.ajouter_bouton("Ajouter une cible", self._ajouter, primaire=True)

        self._charger()

    def _sur_selection(self) -> None:
        actif = self.tableau.ligne_selectionnee() is not None
        self.b_modifier.state(["!disabled"] if actif else ["disabled"])
        self.b_supprimer.state(["!disabled"] if actif else ["disabled"])

    def _charger(self) -> None:
        try:
            objectifs = kpi.lister_objectifs(self.ctx, self.site_id)
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            objectifs = []
        for o in objectifs:
            if o["site_id"] is None:
                o["portee"] = "Général (tous les sites)"
            elif o["zone_id"] is None:
                o["portee"] = f"{o['site']} (toutes zones)"
            else:
                o["portee"] = f"{o['site']} — {o['zone']}"
            o["periodicite_libelle"] = libelle(PERIODICITES, o["periodicite"])
        self.tableau.charger(objectifs, cle_id="id", message_vide="Aucune cible définie.")

    def _ajouter(self) -> None:
        if FenetreObjectif(self, self.ctx, self.site_id).afficher():
            self._charger()

    def _modifier(self) -> None:
        objectif = self.tableau.ligne_selectionnee()
        if objectif is None:
            return
        if FenetreObjectif(self, self.ctx, self.site_id, objectif=objectif).afficher():
            self._charger()

    def _supprimer(self) -> None:
        objectif = self.tableau.ligne_selectionnee()
        if objectif is None:
            return
        if not confirmer(self, "Supprimer cette cible ?", "Supprimer la cible"):
            return
        try:
            kpi.supprimer_objectif(self.ctx, objectif["id"])
        except (ErreurApplication, OperationImpossible) as exc:
            afficher_erreur(self, exc.message)
            return
        self._charger()
        informer(self, "Cible supprimée.")


class FenetreObjectif(DialogueBase):
    """Formulaire d'ajout ou de modification d'une cible (UC15)."""

    def __init__(self, parent, ctx, site_id: int, objectif: dict | None = None) -> None:
        titre = "Modifier la cible" if objectif else "Ajouter une cible"
        super().__init__(parent, titre, redimensionnable=False)
        self.ctx = ctx
        self.site_id = site_id
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

        self.generale = ChampCase(formulaire, "Cible générale (tous les sites)")
        self.generale.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.generale.variable.trace_add("write", lambda *_a: self._sur_generale())
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
            self.generale.definir(self.objectif["site_id"] is None)
            self.generale.activer(False)
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

    def _sur_generale(self) -> None:
        self._charger_zones()

    def _charger_zones(self) -> None:
        if self.generale.valeur():
            self.zone.definir_options([(None, "—")], conserver=False)
            self.zone.activer(False)
            return
        try:
            zones = admin.lister_zones(self.ctx, self.site_id)
        except ErreurApplication:
            zones = []
        self.zone.definir_options(
            [(None, "Toutes les zones du site")] + [(z["id"], z["nom"]) for z in zones],
            conserver=False,
        )
        self.zone.activer(True)

    def _enregistrer(self) -> None:
        for champ in self.widgets.values():
            champ.effacer_erreur()
        kpi_id = self.kpi.valeur()
        if kpi_id is None:
            afficher_erreur(self, "Choisissez un KPI.")
            return
        site_id = None if self.generale.valeur() else self.site_id
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
