"""Écran 3 — Données (UC04, UC05, UC06) : planificateur."""

from __future__ import annotations

from datetime import date
from tkinter import ttk

from app.erreurs import DonneesInvalides, ErreurApplication
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampCase, ChampDate, ChampListe, ChampNombre, appliquer_erreurs
from app.gui.widgets.dialogues import (
    afficher_erreur,
    choisir_fichier_a_enregistrer,
    choisir_fichier_a_ouvrir,
    informer,
)
from app.gui.widgets.resultat_import import ouvrir_resultat_import
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.services import admin, donnees
from app.services.qualite import CHAMPS_HISTORIQUE, CHAMPS_PREVISION

LIBELLES_SOURCE = {
    "saisie": "Saisie manuelle",
    "import": "Import de fichier",
    "demonstration": "Données de démonstration",
}


def _formateur_source(valeur):
    return LIBELLES_SOURCE.get(valeur, valeur)


class VueDonnees(Vue):
    """Onglets « Historique d'activité » et « Prévisions de volume »."""

    titre = "Données"
    sous_titre = "Historique d'activité et prévisions de volume"

    def construire(self) -> None:
        self.onglets = ttk.Notebook(self.contenu)
        self.onglets.pack(fill="both", expand=True)
        self.page_historique = OngletHistorique(self.onglets, self)
        self.onglets.add(self.page_historique, text="Historique d'activité")
        self.page_previsions = OngletPrevisions(self.onglets, self)
        self.onglets.add(self.page_previsions, text="Prévisions de volume")

    def actualiser(self) -> None:
        self.page_historique.actualiser()
        self.page_previsions.actualiser()


class OngletSaisieImport(ttk.Frame):
    """Base commune : sélection site/zone, formulaire dynamique, import et tableau."""

    type_donnees = ""
    specs: list = []
    libelle_type = ""
    colonnes_tableau: list[Colonne] = []

    def __init__(self, parent, vue: VueDonnees) -> None:
        super().__init__(parent, padding=12)
        self.vue = vue
        self.ctx = vue.ctx
        self.sites: list[dict] = []
        self.zones: list[dict] = []
        self.widgets_champs: dict[str, object] = {}
        self._construire_widgets()

    # --- Construction ----------------------------------------------------
    def _construire_widgets(self) -> None:
        cadre_formulaire = ttk.Frame(self, style="Carte.TFrame", padding=12)
        cadre_formulaire.pack(fill="x")
        ttk.Label(
            cadre_formulaire, text="Saisie manuelle", style="Section.TLabel", background="#ffffff"
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.site = ChampListe(cadre_formulaire, "Site", style_cadre="Carte.TFrame")
        self.site.grid(row=1, column=0, sticky="we", padx=(0, 16), pady=(0, 8))
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(cadre_formulaire, "Zone", style_cadre="Carte.TFrame")
        self.zone.grid(row=1, column=1, sticky="we", padx=(0, 16), pady=(0, 8))
        self.zone.sur_changement(self.actualiser_tableau)
        self.champ_date = ChampDate(cadre_formulaire, "Date", style_cadre="Carte.TFrame")
        self.champ_date.grid(row=1, column=2, sticky="w", pady=(0, 8))

        ligne, colonne = 2, 0
        for spec in self.specs:
            widget = self._creer_widget_champ(cadre_formulaire, spec)
            widget.grid(row=ligne, column=colonne, sticky="we", padx=(0, 16), pady=(0, 8))
            self.widgets_champs[spec.cle] = widget
            colonne += 1
            if colonne == 3:
                colonne, ligne = 0, ligne + 1
        for c in range(3):
            cadre_formulaire.columnconfigure(c, weight=1)

        barre = ttk.Frame(self)
        barre.pack(fill="x", pady=(10, 10))
        Bouton(barre, "Enregistrer", self.enregistrer, primaire=True).pack(side="left")
        Bouton(barre, "Effacer le formulaire", self.effacer_formulaire).pack(
            side="left", padx=(8, 0)
        )
        Bouton(barre, "Importer un fichier…", self.importer).pack(side="left", padx=(24, 0))
        Bouton(barre, "Télécharger le modèle de fichier", self.telecharger_modele).pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(self, text=self.titre_tableau, style="Section.TLabel").pack(anchor="w")
        self.tableau = TableauTriable(self, self.colonnes_tableau, hauteur=14)
        self.tableau.pack(fill="both", expand=True, pady=(4, 0))

    def _creer_widget_champ(self, parent, spec):
        if spec.type == "booleen":
            return ChampCase(
                parent, spec.libelle, valeur=bool(spec.defaut), style_cadre="Carte.TFrame"
            )
        aide = "" if spec.obligatoire else "Facultatif : 0 si laissé vide."
        return ChampNombre(
            parent,
            spec.libelle + (" *" if spec.obligatoire else ""),
            aide=aide,
            style_cadre="Carte.TFrame",
        )

    # --- Rafraîchissement --------------------------------------------------
    def actualiser(self) -> None:
        self.sites = self.vue.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in self.sites])
        self._sur_changement_site()

    def _sur_changement_site(self) -> None:
        site_id = self.site.valeur()
        self.zones = (
            self.vue.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
            if site_id is not None
            else []
        )
        self.zone.definir_options([(z["id"], z["nom"]) for z in self.zones])
        self.actualiser_tableau()

    def actualiser_tableau(self) -> None:  # pragma: no cover - redéfinie par les sous-classes
        raise NotImplementedError

    def effacer_formulaire(self) -> None:
        for widget in self.widgets_champs.values():
            widget.definir(False if isinstance(widget, ChampCase) else "")
            widget.effacer_erreur()
        self.champ_date.definir(date.today())
        self.champ_date.effacer_erreur()

    def _lire_champs(self) -> dict:
        champs = {
            spec.cle: widget.valeur()
            for spec, widget in zip(self.specs, self.widgets_champs.values(), strict=True)
        }
        champs["date"] = self.champ_date.texte()
        return champs

    def _erreur_generale(self, texte: str) -> None:
        if not hasattr(self, "_label_erreur"):
            self._label_erreur = ttk.Label(self, text="", style="Erreur.TLabel", wraplength=700)
            self._label_erreur.pack(anchor="w", before=self.tableau)
        self._label_erreur.configure(text=texte)

    # --- Actions -----------------------------------------------------------
    def enregistrer(self) -> None:
        site_id, zone_id = self.site.valeur(), self.zone.valeur()
        self._erreur_generale("")
        self.champ_date.effacer_erreur()
        for widget in self.widgets_champs.values():
            widget.effacer_erreur()
        if site_id is None or zone_id is None:
            self._erreur_generale("Choisissez un site et une zone avant d'enregistrer.")
            return
        champs = self._lire_champs()
        try:
            avertissements = self._saisir(site_id, zone_id, champs)
        except DonneesInvalides as exc:
            widgets = {**self.widgets_champs, "date": self.champ_date}
            appliquer_erreurs(widgets, exc.erreurs)
            if not exc.erreurs:
                self._erreur_generale(exc.message)
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.actualiser_tableau()
        if avertissements:
            informer(
                self,
                "Ligne enregistrée avec un avertissement :\n" + "\n".join(avertissements),
                "Enregistré avec avertissement",
            )
        else:
            informer(self, "Ligne enregistrée.")

    def _saisir(self, site_id: int, zone_id: int, champs: dict) -> list[str]:
        raise NotImplementedError

    def importer(self) -> None:
        chemin = choisir_fichier_a_ouvrir(self, f"Importer {self.libelle_type}")
        if chemin is None:
            return
        try:
            resultat = self._importer(chemin)
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        enrichis = self._enrichir_valides(resultat.valides)
        resultat.valides = enrichis
        enregistrer = ouvrir_resultat_import(
            self,
            f"Résultat de l'import — {self.libelle_type}",
            resultat,
            self.colonnes_import,
            f"rapport_erreurs_{self.type_donnees}_{date.today():%Y-%m-%d}.xlsx",
        )
        if enregistrer:
            nombre = self.vue.executer(lambda: self._enregistrer(resultat.valides))
            if nombre is not None:
                self.actualiser_tableau()
                informer(self, f"{nombre} ligne(s) enregistrée(s).")

    def _importer(self, chemin):
        raise NotImplementedError

    def _enregistrer(self, valides: list[dict]) -> int:
        raise NotImplementedError

    def _enrichir_valides(self, valides: list[dict]) -> list[dict]:
        noms_sites = {
            s["id"]: s["nom"]
            for s in (self.vue.executer(lambda: admin.lister_sites(self.ctx, True)) or [])
        }
        noms_zones = {
            z["id"]: z["nom"]
            for z in (
                self.vue.executer(lambda: admin.lister_zones(self.ctx, inclure_inactives=True))
                or []
            )
        }
        for ligne in valides:
            ligne["site"] = noms_sites.get(ligne["site_id"], "—")
            ligne["zone"] = noms_zones.get(ligne["zone_id"], "—")
        return valides

    def telecharger_modele(self) -> None:
        source = donnees.chemin_modele_fichier(self.type_donnees)
        destination = choisir_fichier_a_enregistrer(
            self, source.name, "Télécharger le modèle de fichier", [("Fichier CSV", "*.csv")]
        )
        if destination is None:
            return
        destination.write_bytes(source.read_bytes())
        informer(self, f"Modèle enregistré : {destination.name}")


class OngletHistorique(OngletSaisieImport):
    """Onglet « Historique d'activité »."""

    type_donnees = "historique"
    specs = CHAMPS_HISTORIQUE
    libelle_type = "l'historique d'activité"
    titre_tableau = "Historique des 60 derniers jours"
    colonnes_import = [
        Colonne("site", "Site", 150),
        Colonne("zone", "Zone", 120),
        Colonne("date", "Date", 100, "center"),
        Colonne("volume_traite", "Volume traité", 100, "e"),
        Colonne("effectif_present", "Effectif", 80, "e"),
        Colonne("heures_travaillees", "Heures travaillées", 110, "e"),
    ]
    colonnes_tableau = [
        Colonne("site", "Site", 150),
        Colonne("zone", "Zone", 120),
        Colonne("date_jour", "Date", 100, "center"),
        Colonne("volume_traite", "Volume traité", 110, "e"),
        Colonne("effectif_present", "Effectif présent", 100, "e"),
        Colonne("heures_travaillees", "Heures travaillées", 120, "e"),
        Colonne("heures_sup", "Heures sup.", 100, "e"),
        Colonne("heures_interim", "Heures intérim", 110, "e"),
        Colonne("heures_absence", "Heures absence", 110, "e"),
        Colonne("heures_inactives", "Heures inactives", 110, "e"),
        Colonne("equipements_mobilises", "Équipements mobilisés", 140, "e"),
        Colonne("heures_usage_equipement", "Heures usage éqp.", 130, "e"),
        Colonne("heures_disponibles_equipement", "Heures disponibles éqp.", 150, "e"),
        Colonne("heures_panne_equipement", "Heures panne éqp.", 130, "e"),
        Colonne("cout_rh", "Coût RH", 110, "e"),
        Colonne("commandes_a_temps", "Commandes à temps", 130, "e"),
        Colonne("commandes_totales", "Commandes totales", 130, "e"),
        Colonne("indicateur_pic", "Pic", 60, "center"),
        Colonne("source", "Origine", 140, formateur=_formateur_source),
    ]

    def actualiser_tableau(self) -> None:
        site_id = self.site.valeur()
        zone_id = self.zone.valeur()
        lignes = (
            self.vue.executer(lambda: donnees.lister_historique(self.ctx, site_id, zone_id)) or []
        )
        self.tableau.charger(lignes, message_vide="Aucune donnée sur les 60 derniers jours.")

    def _saisir(self, site_id, zone_id, champs):
        return donnees.saisir_historique(self.ctx, site_id, zone_id, champs)

    def _importer(self, chemin):
        return donnees.importer_historique(self.ctx, chemin)

    def _enregistrer(self, valides):
        return donnees.enregistrer_lignes_historique(self.ctx, valides)


class OngletPrevisions(OngletSaisieImport):
    """Onglet « Prévisions de volume »."""

    type_donnees = "prevision"
    specs = CHAMPS_PREVISION
    libelle_type = "les prévisions de volume"
    titre_tableau = "Prévisions saisies (28 prochains jours)"
    colonnes_import = [
        Colonne("site", "Site", 150),
        Colonne("zone", "Zone", 120),
        Colonne("date", "Date", 100, "center"),
        Colonne("volume_prevu", "Volume prévu", 110, "e"),
    ]
    colonnes_tableau = [
        Colonne("site", "Site", 150),
        Colonne("zone", "Zone", 120),
        Colonne("date_jour", "Date", 100, "center"),
        Colonne("volume_prevu", "Volume prévu", 120, "e"),
        Colonne("indicateur_pic", "Pic annoncé", 100, "center"),
        Colonne("source", "Origine", 140, formateur=_formateur_source),
    ]

    def effacer_formulaire(self) -> None:
        super().effacer_formulaire()
        from datetime import timedelta

        self.champ_date.definir(date.today() + timedelta(days=1))

    def actualiser_tableau(self) -> None:
        site_id = self.site.valeur()
        zone_id = self.zone.valeur()
        lignes = (
            self.vue.executer(lambda: donnees.lister_previsions_volume(self.ctx, site_id, zone_id))
            or []
        )
        self.tableau.charger(lignes, message_vide="Aucune prévision saisie sur l'horizon.")

    def _saisir(self, site_id, zone_id, champs):
        return donnees.saisir_prevision_volume(self.ctx, site_id, zone_id, champs)

    def _importer(self, chemin):
        return donnees.importer_previsions_volume(self.ctx, chemin)

    def _enregistrer(self, valides):
        return donnees.enregistrer_lignes_previsions(self.ctx, valides)
