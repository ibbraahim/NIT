"""Écran 8 — Alertes (UC18, UC19) : planificateur et responsable (traiter), responsable
(émettre)."""

from __future__ import annotations

from tkinter import ttk

from app.erreurs import DonneesInvalides, ErreurApplication
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampListe, ChampTexteLong
from app.gui.widgets.dialogues import DialogueBase, afficher_erreur, informer
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.taches_fond import executer_en_fond
from app.libelles import NIVEAUX_ALERTE, STATUTS_ALERTE, TYPES_ALERTE, libelle
from app.services import admin, alertes
from app.services.droits import a_le_droit
from app.utils.format_fr import formater_date_heure

OPTION_TOUS_STATUTS = (None, "Tous les statuts")
OPTIONS_STATUT = [OPTION_TOUS_STATUTS] + list(STATUTS_ALERTE.items())
OPTION_TOUS_TYPES = (None, "Tous les types")
OPTIONS_TYPE = [OPTION_TOUS_TYPES] + list(TYPES_ALERTE.items())

COLONNES_TABLEAU = [
    Colonne("type_libelle", "Type", 170),
    Colonne("niveau_libelle", "Niveau", 80, "center"),
    Colonne("zone", "Zone", 110),
    Colonne("date_concernee", "Date concernée", 110, "center"),
    Colonne("message", "Message", 380),
    Colonne("statut_libelle", "Statut", 90, "center"),
    Colonne("date_maj", "Dernière mise à jour", 150, "center", formateur=formater_date_heure),
]


def _etiquette(ligne: dict) -> str | None:
    return "gris" if ligne["statut"] == "resolue" else ligne["niveau"]


class VueAlertes(Vue):
    """Filtres Site/Statut/Type, détection (UC18), table des alertes, prise en charge et
    résolution (UC19)."""

    titre = "Alertes"
    sous_titre = "Sous-effectif, sureffectif, pénurie d'équipements, seuils de KPI, dérive"

    def construire(self) -> None:
        self.peut_emettre = a_le_droit(self.ctx, "UC18")
        self.peut_traiter = a_le_droit(self.ctx, "UC19")
        self._alerte_a_selectionner: int | None = None

        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 10))
        self.site = ChampListe(barre, "Site", largeur=24)
        self.site.pack(side="left")
        self.site.sur_changement(self.actualiser_donnees)
        self.statut = ChampListe(barre, "Statut", options=OPTIONS_STATUT, largeur=16)
        self.statut.pack(side="left", padx=(16, 0))
        self.statut.sur_changement(self.actualiser_donnees)
        self.type_alerte = ChampListe(barre, "Type", options=OPTIONS_TYPE, largeur=22)
        self.type_alerte.pack(side="left", padx=(16, 0))
        self.type_alerte.sur_changement(self.actualiser_donnees)

        boutons = ttk.Frame(barre)
        boutons.pack(side="left", padx=(24, 0), pady=(14, 0))
        self.b_detecter = Bouton(boutons, "Détecter les alertes", self.detecter, primaire=True)
        self.b_detecter.pack(side="left")
        if not self.peut_emettre:
            self.b_detecter.pack_forget()

        corps = ttk.Frame(self.contenu)
        corps.pack(fill="both", expand=True)
        self.tableau = TableauTriable(corps, COLONNES_TABLEAU, hauteur=16)
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self._sur_selection)

        actions = ttk.Frame(self.contenu)
        actions.pack(fill="x", pady=(10, 0))
        self.b_prendre_en_charge = Bouton(actions, "Prendre en charge", self.prendre_en_charge)
        self.b_prendre_en_charge.pack(side="left")
        self.b_resoudre = Bouton(actions, "Résoudre…", self.resoudre)
        self.b_resoudre.pack(side="left", padx=(8, 0))
        if not self.peut_traiter:
            self.b_prendre_en_charge.pack_forget()
            self.b_resoudre.pack_forget()
        self._desactiver_actions()

    def actualiser(self) -> None:
        sites = self.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self.actualiser_donnees()

    def afficher_parametres(self, alerte_id: int | None = None, **_autres) -> None:
        """Reçoit l'alerte à sélectionner (double-clic depuis le tableau de bord, à venir)."""
        self._alerte_a_selectionner = alerte_id

    def actualiser_donnees(self) -> None:
        site_id = self.site.valeur()
        statut, type_alerte = self.statut.valeur(), self.type_alerte.valeur()
        self.b_detecter.activer(
            self.peut_emettre and site_id is not None, "Choisissez d'abord un site."
        )
        if site_id is None:
            self.tableau.charger([], message_vide="Choisissez un site.")
            self._desactiver_actions()
            return
        lignes = (
            self.executer(lambda: alertes.lister_alertes(self.ctx, site_id, statut, type_alerte))
            or []
        )
        for ligne in lignes:
            ligne["type_libelle"] = libelle(TYPES_ALERTE, ligne["type"])
            ligne["niveau_libelle"] = libelle(NIVEAUX_ALERTE, ligne["niveau"])
            ligne["statut_libelle"] = libelle(STATUTS_ALERTE, ligne["statut"])
        self.tableau.charger(
            lignes,
            cle_id="id",
            etiquettes=_etiquette,
            message_vide="Aucune alerte pour ces filtres.",
        )
        self._desactiver_actions()
        if self._alerte_a_selectionner is not None:
            self.tableau.selectionner(self._alerte_a_selectionner)
            self._alerte_a_selectionner = None

    def _sur_selection(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        actif = self.peut_traiter and ligne is not None and ligne["statut"] != "resolue"
        self.b_prendre_en_charge.activer(
            actif and ligne["statut"] == "ouverte", "Sélectionnez une alerte ouverte."
        )
        self.b_resoudre.activer(actif, "Sélectionnez une alerte non résolue.")

    def _desactiver_actions(self) -> None:
        self.b_prendre_en_charge.activer(False, "Sélectionnez une alerte ouverte.")
        self.b_resoudre.activer(False, "Sélectionnez une alerte non résolue.")

    def detecter(self) -> None:
        site_id = self.site.valeur()
        if site_id is None:
            return

        def traiter(_progression):
            return alertes.emettre_alertes(self.ctx, site_id)

        def succes(resultat):
            self.actualiser_donnees()
            informer(
                self, f"{len(resultat)} alerte(s) émise(s) ou confirmée(s).", "Détection terminée"
            )

        executer_en_fond(
            self,
            traiter,
            succes,
            titre="Détection des alertes",
            message="Analyse du plan de charge validé et des KPI…",
        )

    def prendre_en_charge(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None:
            return
        try:
            alertes.prendre_en_charge(self.ctx, ligne["id"])
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.actualiser_donnees()
        informer(self, "Alerte prise en charge.")

    def resoudre(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None:
            return
        if FenetreResolution(self, self.ctx, ligne["id"]).afficher():
            self.actualiser_donnees()
            informer(self, "Alerte résolue.")


class FenetreResolution(DialogueBase):
    """UC19 : commentaire obligatoire de clôture d'une alerte (docs/plan.md, Q7)."""

    def __init__(self, parent, ctx, alerte_id: int) -> None:
        super().__init__(parent, "Résoudre l'alerte", redimensionnable=False)
        self.ctx = ctx
        self.alerte_id = alerte_id
        self.action = ChampTexteLong(self.corps, "Action menée", hauteur=5, largeur=60)
        self.action.pack(fill="both", expand=True)
        self.ajouter_bouton("Annuler", self.fermer)
        self.ajouter_bouton("Enregistrer", self._enregistrer, primaire=True, defaut=True)

    def _enregistrer(self) -> None:
        self.action.effacer_erreur()
        try:
            alertes.resoudre_alerte(self.ctx, self.alerte_id, self.action.valeur())
        except DonneesInvalides as exc:
            self.action.signaler_erreur(exc.erreurs.get("action_menee", exc.message))
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.fermer(True)
