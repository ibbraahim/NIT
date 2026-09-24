"""Écran 11 — Administration (UC02, UC03, tâches automatiques) : administrateur."""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.config import configuration
from app.erreurs import DonneesInvalides, ErreurApplication
from app.gui.style import COULEURS
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampCase, ChampDate, ChampListe, ChampNombre, ChampTexte
from app.gui.widgets.dialogues import DialogueFormulaire, afficher_erreur, confirmer, informer
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.libelles import CATEGORIES_COUT, STATUTS_EQUIPEMENT, TYPES_EQUIPEMENT, libelle
from app.services import admin
from app.utils.dates import jours_semaine, lundi_de
from app.utils.format_fr import (
    formater_date,
    formater_jour_court,
    formater_nombre,
)

OPTIONS_TYPES = list(TYPES_EQUIPEMENT.items())
OPTIONS_STATUTS = list(STATUTS_EQUIPEMENT.items())


def _etat(actif: bool) -> str:
    return "Actif" if actif else "Inactif"


class VueAdministration(Vue):
    """Onglets de l'administration."""

    titre = "Administration"
    sous_titre = "Référentiels, utilisateurs et tâches automatiques"

    def construire(self) -> None:
        self.onglets = ttk.Notebook(self.contenu)
        self.onglets.pack(fill="both", expand=True)
        self.pages = []
        for classe, titre in self._pages():
            page = classe(self.onglets, self)
            self.onglets.add(page, text=titre)
            self.pages.append(page)
        self.onglets.bind("<<NotebookTabChanged>>", lambda _e: self.actualiser())

    def _pages(self):
        return [
            (OngletSitesZones, "Sites et zones"),
            (OngletEquipements, "Équipements"),
            (OngletCapacitesCouts, "Capacités et coûts"),
        ]

    def actualiser(self) -> None:
        index = self.onglets.index("current") if self.pages else None
        if index is not None:
            self.pages[index].actualiser()


class Onglet(ttk.Frame):
    """Page d'onglet ayant accès à la vue parente."""

    def __init__(self, parent, vue: VueAdministration) -> None:
        super().__init__(parent, padding=12)
        self.vue = vue
        self.ctx = vue.ctx
        self.construire()

    def construire(self) -> None:
        """Crée les widgets de l'onglet."""

    def actualiser(self) -> None:
        """Recharge les données de l'onglet."""

    def barre_boutons(self) -> ttk.Frame:
        barre = ttk.Frame(self)
        barre.pack(fill="x", pady=(0, 8))
        return barre


# =====================================================================
# Onglet « Sites et zones »
# =====================================================================
class OngletSitesZones(Onglet):
    """Boutons : « Ajouter un site », « Ajouter une zone », « Modifier », « Désactiver »."""

    def construire(self) -> None:
        barre = self.barre_boutons()
        self.b_site = Bouton(barre, "Ajouter un site", self.ajouter_site, primaire=True)
        self.b_zone = Bouton(barre, "Ajouter une zone", self.ajouter_zone)
        self.b_modifier = Bouton(barre, "Modifier", self.modifier)
        self.b_desactiver = Bouton(barre, "Désactiver", self.desactiver)
        for bouton in (self.b_site, self.b_zone, self.b_modifier, self.b_desactiver):
            bouton.pack(side="left", padx=(0, 8))
        self.tableau = TableauTriable(
            self,
            [
                Colonne("type_libelle", "Type d'équipement principal", 230),
                Colonne("duree", "Durée de poste (h)", 150, "e"),
                Colonne("adresse", "Adresse", 320),
                Colonne("etat", "État", 90),
            ],
            hauteur=18,
            arborescence=True,
            titre_arbre="Site / zone",
            largeur_arbre=260,
        )
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self.mettre_a_jour_boutons)
        self.tableau.sur_double_clic(lambda _l: self.modifier())

    def actualiser(self) -> None:
        sites = self.vue.executer(lambda: admin.lister_sites(self.ctx, inclure_inactifs=True))
        zones = self.vue.executer(lambda: admin.lister_zones(self.ctx, inclure_inactives=True))
        if sites is None or zones is None:
            return
        lignes = []
        for site in sites:
            lignes.append(
                {
                    "cle": f"s{site['id']}",
                    "genre": "site",
                    "nom": site["nom"],
                    "adresse": site["adresse"],
                    "etat": _etat(site["actif"]),
                    "actif": site["actif"],
                    "donnees": site,
                }
            )
        for zone in zones:
            lignes.append(
                {
                    "cle": f"z{zone['id']}",
                    "_parent": f"s{zone['site_id']}",
                    "genre": "zone",
                    "nom": zone["nom"],
                    "type_libelle": libelle(TYPES_EQUIPEMENT, zone["type_equipement_principal"]),
                    "duree": zone["duree_poste_heures"],
                    "etat": _etat(zone["actif"]),
                    "actif": zone["actif"],
                    "donnees": zone,
                }
            )
        self.tableau.charger(
            lignes,
            cle_id="cle",
            texte_arbre=lambda lg: lg["nom"],
            etiquettes=lambda lg: None if lg["actif"] else "inactif",
            message_vide="Aucun site. Utilisez « Ajouter un site ».",
        )
        self.mettre_a_jour_boutons()

    def mettre_a_jour_boutons(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        site_actif = False
        if ligne is not None:
            site_actif = (
                ligne["actif"] if ligne["genre"] == "site" else self._site_de(ligne)["actif"]
            )
        self.b_zone.activer(
            site_actif, "Sélectionnez d'abord un site actif (ou l'une de ses zones)."
        )
        self.b_modifier.activer(ligne is not None, "Sélectionnez un site ou une zone.")
        self.b_desactiver.activer(
            ligne is not None and ligne["actif"],
            (
                "Sélectionnez un site ou une zone actif."
                if ligne is None
                else "Cet élément est déjà désactivé."
            ),
        )

    def _site_de(self, ligne: dict) -> dict:
        if ligne["genre"] == "site":
            return ligne["donnees"]
        cle = f"s{ligne['donnees']['site_id']}"
        return next(lg["donnees"] for lg in self.tableau.lignes() if lg["cle"] == cle)

    # --- Formulaires ---------------------------------------------------
    def _formulaire_site(self, site: dict | None) -> None:
        def construire(corps):
            champs = {
                "nom": ChampTexte(corps, "Nom du site", largeur=40),
                "adresse": ChampTexte(corps, "Adresse", largeur=40),
            }
            champs["nom"].grid(row=0, column=0, sticky="we")
            champs["adresse"].grid(row=1, column=0, sticky="we", pady=(8, 0))
            if site is not None:
                champs["actif"] = ChampCase(corps, "Site actif")
                champs["actif"].grid(row=2, column=0, sticky="w")
            return champs

        def enregistrer(v):
            return admin.enregistrer_site(
                self.ctx, v["nom"], v["adresse"], site["id"] if site else None, v.get("actif", True)
            )

        valeurs = dict(site) if site else None
        if DialogueFormulaire(
            self,
            "Modifier le site" if site else "Ajouter un site",
            construire,
            enregistrer,
            valeurs,
        ).afficher():
            self.actualiser()

    def _formulaire_zone(self, site_id: int, zone: dict | None) -> None:
        def construire(corps):
            champs = {
                "nom": ChampTexte(corps, "Nom de la zone", largeur=34),
                "type_equipement_principal": ChampListe(
                    corps, "Type d'équipement principal", options=OPTIONS_TYPES, largeur=32
                ),
                "duree_poste_heures": ChampNombre(
                    corps, "Durée de poste (heures)", aide="Exemple : 7,5"
                ),
            }
            for ligne, champ in enumerate(champs.values()):
                champ.grid(row=ligne, column=0, sticky="we", pady=(0, 8))
            if zone is not None:
                champs["actif"] = ChampCase(corps, "Zone active")
                champs["actif"].grid(row=3, column=0, sticky="w")
            else:
                champs["duree_poste_heures"].definir(7.5)
            return champs

        def enregistrer(v):
            return admin.enregistrer_zone(
                self.ctx,
                site_id,
                v["nom"],
                v["type_equipement_principal"],
                v["duree_poste_heures"],
                zone["id"] if zone else None,
                v.get("actif", True),
            )

        if DialogueFormulaire(
            self,
            "Modifier la zone" if zone else "Ajouter une zone",
            construire,
            enregistrer,
            dict(zone) if zone else None,
        ).afficher():
            self.actualiser()

    # --- Actions -------------------------------------------------------
    def ajouter_site(self) -> None:
        self._formulaire_site(None)

    def ajouter_zone(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is not None:
            self._formulaire_zone(self._site_de(ligne)["id"], None)

    def modifier(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None:
            return
        if ligne["genre"] == "site":
            self._formulaire_site(ligne["donnees"])
        else:
            self._formulaire_zone(ligne["donnees"]["site_id"], ligne["donnees"])

    def desactiver(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None or not ligne["actif"]:
            return
        if ligne["genre"] == "site":
            message = (
                f"Désactiver le site « {ligne['nom']} » ? Ses zones seront aussi "
                "désactivées. Les données historiques sont conservées."
            )
            action = lambda: admin.desactiver_site(self.ctx, ligne["donnees"]["id"])  # noqa: E731
        else:
            message = (
                f"Désactiver la zone « {ligne['nom']} » ? Les données historiques sont "
                "conservées."
            )
            action = lambda: admin.desactiver_zone(self.ctx, ligne["donnees"]["id"])  # noqa: E731
        if confirmer(self, message, "Confirmer la désactivation"):
            if self.vue.executer(action):
                self.actualiser()


# =====================================================================
# Onglet « Équipements »
# =====================================================================
class OngletEquipements(Onglet):
    """Boutons : « Ajouter », « Modifier », « Déclarer une indisponibilité… », « Désactiver »."""

    def construire(self) -> None:
        haut = ttk.Frame(self)
        haut.pack(fill="x", pady=(0, 8))
        self.site = ChampListe(haut, "Site", largeur=30)
        self.site.pack(side="left")
        self.site.sur_changement(self.actualiser)
        barre = ttk.Frame(haut)
        barre.pack(side="left", padx=(24, 0), pady=(14, 0))
        self.b_ajouter = Bouton(barre, "Ajouter", self.ajouter, primaire=True)
        self.b_modifier = Bouton(barre, "Modifier", self.modifier)
        self.b_indispo = Bouton(barre, "Déclarer une indisponibilité…", self.declarer)
        self.b_desactiver = Bouton(barre, "Désactiver", self.desactiver)
        for bouton in (self.b_ajouter, self.b_modifier, self.b_indispo, self.b_desactiver):
            bouton.pack(side="left", padx=(0, 8))
        self.tableau = TableauTriable(
            self,
            [
                Colonne("code", "Code", 90),
                Colonne("type_libelle", "Type", 190),
                Colonne("zone", "Zone", 140),
                Colonne("statut_libelle", "Statut", 130),
                Colonne("etat", "État", 80),
                Colonne("prochaine_indisponibilite", "Prochaine indisponibilité", 170, "center"),
            ],
            hauteur=11,
        )
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self.mettre_a_jour_boutons)
        self.tableau.sur_double_clic(lambda _l: self.modifier())
        ttk.Label(self, text="Indisponibilités en cours et à venir", style="Section.TLabel").pack(
            anchor="w", pady=(12, 4)
        )
        self.indispos = TableauTriable(
            self,
            [
                Colonne("code", "Équipement", 110),
                Colonne("zone", "Zone", 140),
                Colonne("date_debut", "Du", 110, "center"),
                Colonne("date_fin", "Au", 110, "center"),
                Colonne("motif", "Motif", 360),
            ],
            hauteur=6,
        )
        self.indispos.pack(fill="both", expand=True)

    def actualiser(self) -> None:
        sites = self.vue.executer(lambda: admin.lister_sites(self.ctx))
        if sites is None:
            return
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        site_id = self.site.valeur()
        lignes, indispos = [], []
        if site_id is not None:
            lignes = (
                self.vue.executer(
                    lambda: admin.lister_equipements(self.ctx, site_id, inclure_inactifs=True)
                )
                or []
            )
            aujourd_hui = date.today()
            indispos = (
                self.vue.executer(
                    lambda: admin.lister_indisponibilites(
                        self.ctx, site_id, aujourd_hui, aujourd_hui + timedelta(days=365)
                    )
                )
                or []
            )
        for ligne in lignes:
            ligne["type_libelle"] = libelle(TYPES_EQUIPEMENT, ligne["type"])
            ligne["statut_libelle"] = libelle(STATUTS_EQUIPEMENT, ligne["statut"])
            ligne["etat"] = _etat(ligne["actif"])

        def couleur(lg):
            if not lg["actif"]:
                return "inactif"
            return {"maintenance": "orange", "hors_service": "rouge"}.get(lg["statut"])

        self.tableau.charger(
            lignes, etiquettes=couleur, message_vide="Aucun équipement pour ce site."
        )
        self.indispos.charger(indispos, message_vide="Aucune indisponibilité déclarée.")
        self.b_ajouter.activer(site_id is not None, "Créez d'abord un site.")
        self.mettre_a_jour_boutons()

    def mettre_a_jour_boutons(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        raison = "Sélectionnez un équipement dans le tableau."
        self.b_modifier.activer(ligne is not None, raison)
        actif = ligne is not None and ligne["actif"]
        raison_actif = raison if ligne is None else "Cet équipement est désactivé."
        self.b_indispo.activer(actif, raison_actif)
        self.b_desactiver.activer(actif, raison_actif)

    def _formulaire(self, equipement: dict | None) -> None:
        site_id = self.site.valeur()
        zones = self.vue.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []

        def construire(corps):
            champs = {
                "zone": ChampListe(corps, "Zone", options=[(z["id"], z["nom"]) for z in zones]),
                "type": ChampListe(corps, "Type", options=OPTIONS_TYPES),
                "code": ChampTexte(corps, "Code", aide="Exemple : CE-09"),
                "statut": ChampListe(corps, "Statut", options=OPTIONS_STATUTS),
            }
            for ligne, champ in enumerate(champs.values()):
                champ.grid(row=ligne // 2, column=ligne % 2, sticky="we", padx=(0, 12), pady=(0, 8))
            if equipement is not None:
                champs["actif"] = ChampCase(corps, "Équipement actif")
                champs["actif"].grid(row=2, column=0, sticky="w")
                champs["zone"].definir(equipement["zone_id"])
            return champs

        def enregistrer(v):
            return admin.enregistrer_equipement(
                self.ctx,
                site_id,
                v["zone"],
                v["type"],
                v["code"],
                v["statut"],
                equipement["id"] if equipement else None,
                v.get("actif", True),
            )

        titre = "Modifier l'équipement" if equipement else "Ajouter un équipement"
        if DialogueFormulaire(
            self, titre, construire, enregistrer, dict(equipement) if equipement else None
        ).afficher():
            self.actualiser()

    def ajouter(self) -> None:
        if self.site.valeur() is not None:
            self._formulaire(None)

    def modifier(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is not None:
            self._formulaire(ligne)

    def declarer(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None:
            return

        def construire(corps):
            ttk.Label(
                corps,
                text=f"Équipement {ligne['code']} — {ligne['type_libelle']}, "
                f"zone {ligne['zone']}",
                style="Gras.TLabel",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
            champs = {
                "date_debut": ChampDate(corps, "Date de début"),
                "date_fin": ChampDate(corps, "Date de fin"),
                "motif": ChampTexte(
                    corps, "Motif", largeur=46, aide="Exemple : maintenance préventive"
                ),
            }
            champs["date_debut"].grid(row=1, column=0, sticky="w", padx=(0, 12))
            champs["date_fin"].grid(row=1, column=1, sticky="w")
            champs["motif"].grid(row=2, column=0, columnspan=2, sticky="we", pady=(8, 0))
            return champs

        def valeurs_textes(v):
            return admin.declarer_indisponibilite(
                self.ctx, ligne["id"], v["date_debut"], v["date_fin"], v["motif"]
            )

        dialogue = DialogueFormulaire(
            self, "Déclarer une indisponibilité", construire, valeurs_textes
        )
        # Les dates sont transmises en texte : le service les valide et signale le champ fautif.
        dialogue.valeurs = lambda: {
            n: (c.texte() if isinstance(c, ChampDate) else c.valeur())
            for n, c in dialogue.champs.items()
        }
        if dialogue.afficher():
            self.actualiser()

    def desactiver(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None:
            return
        if confirmer(
            self,
            f"Désactiver l'équipement « {ligne['code']} » ? Il ne sera plus "
            "compté dans la capacité. Son historique est conservé.",
            "Confirmer la désactivation",
        ):
            if self.vue.executer(lambda: admin.desactiver_equipement(self.ctx, ligne["id"])):
                self.actualiser()


# =====================================================================
# Onglet « Capacités et coûts »
# =====================================================================
class OngletCapacitesCouts(Onglet):
    """Grille des capacités par zone et par jour, coûts horaires.

    Boutons : « Enregistrer », « Copier la semaine précédente ».
    """

    def construire(self) -> None:
        haut = ttk.Frame(self)
        haut.pack(fill="x", pady=(0, 8))
        self.site = ChampListe(haut, "Site", largeur=30)
        self.site.pack(side="left")
        self.site.sur_changement(self.charger_grille)
        self.semaine = ChampDate(haut, "Semaine du")
        self.semaine.pack(side="left", padx=(16, 0))
        self.semaine.sur_changement(self.charger_grille)
        barre = ttk.Frame(haut)
        barre.pack(side="left", padx=(24, 0), pady=(14, 0))
        self.b_enregistrer = Bouton(barre, "Enregistrer", self.enregistrer, primaire=True)
        self.b_copier = Bouton(barre, "Copier la semaine précédente", self.copier)
        self.b_enregistrer.pack(side="left", padx=(0, 8))
        self.b_copier.pack(side="left")

        ttk.Label(
            self,
            text="Capacité de personnel planifiée (effectif / absences prévues, en " "personnes)",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(4, 4))
        self.grille = ttk.Frame(self, style="Carte.TFrame", padding=8)
        self.grille.pack(fill="x")
        self.message_grille = ttk.Label(self, text="", style="Erreur.TLabel", wraplength=900)
        self.message_grille.pack(anchor="w", pady=(4, 0))

        ttk.Label(self, text="Coûts horaires", style="Section.TLabel").pack(
            anchor="w", pady=(14, 4)
        )
        couts = ttk.Frame(self, style="Carte.TFrame", padding=8)
        couts.pack(fill="x")
        self.champs_couts: dict[str, ChampNombre] = {}
        for colonne, (categorie, texte) in enumerate(CATEGORIES_COUT.items()):
            champ = ChampNombre(couts, f"{texte} (taux horaire)", style_cadre="Carte.TFrame")
            champ.grid(row=0, column=colonne, sticky="w", padx=(0, 18))
            self.champs_couts[categorie] = champ
        self.devise = ChampTexte(couts, "Devise", largeur=6, style_cadre="Carte.TFrame")
        self.devise.grid(row=0, column=3, sticky="w", padx=(0, 18))
        self.date_effet = ChampDate(couts, "Applicable à partir du", style_cadre="Carte.TFrame")
        self.date_effet.grid(row=0, column=4, sticky="w")
        self.historique_couts = TableauTriable(
            self,
            [
                Colonne("categorie_libelle", "Catégorie", 220),
                Colonne(
                    "taux", "Taux horaire", 120, "e", formateur=lambda v: formater_nombre(v, 2)
                ),
                Colonne("devise", "Devise", 80, "center"),
                Colonne("date_debut", "Applicable à partir du", 170, "center"),
            ],
            hauteur=5,
        )
        self.historique_couts.pack(fill="both", expand=True, pady=(8, 0))
        self.cellules: dict[tuple[int, date], tuple[tk.StringVar, tk.StringVar, list]] = {}
        self._couts_actuels: dict[str, float] = {}

    def actualiser(self) -> None:
        sites = self.vue.executer(lambda: admin.lister_sites(self.ctx))
        if sites is None:
            return
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self.charger_grille()
        self.charger_couts()

    # --- Capacités -----------------------------------------------------
    def _lundi(self) -> date:
        try:
            return lundi_de(self.semaine.valeur())
        except ValueError:
            return lundi_de(date.today())

    def charger_grille(self) -> None:
        for enfant in self.grille.winfo_children():
            enfant.destroy()
        self.cellules.clear()
        self.message_grille.configure(text="")
        site_id = self.site.valeur()
        self.b_enregistrer.activer(site_id is not None, "Créez d'abord un site.")
        self.b_copier.activer(site_id is not None, "Créez d'abord un site.")
        if site_id is None:
            return
        lundi = self._lundi()
        zones = self.vue.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
        capacites = self.vue.executer(lambda: admin.lire_capacites(self.ctx, site_id, lundi)) or {}
        jours = jours_semaine(lundi)
        ttk.Label(self.grille, text="Zone", style="Gras.TLabel", background="#ffffff").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        for c, jour in enumerate(jours, start=1):
            ttk.Label(
                self.grille,
                text=formater_jour_court(jour),
                style="Gras.TLabel",
                background="#ffffff",
            ).grid(row=0, column=c, padx=6)
            ttk.Label(
                self.grille, text="eff. / abs.", style="Aide.TLabel", background="#ffffff"
            ).grid(row=1, column=c)
        for r, zone in enumerate(zones, start=2):
            ttk.Label(self.grille, text=zone["nom"], background="#ffffff").grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=2
            )
            for c, jour in enumerate(jours, start=1):
                existant = capacites.get((zone["id"], jour), {})
                cadre = ttk.Frame(self.grille, style="Surface.TFrame")
                cadre.grid(row=r, column=c, padx=6, pady=2)
                eff = tk.StringVar(value=str(existant.get("effectif_planifie", "")))
                abs_ = tk.StringVar(value=str(existant.get("absences_prevues", "")))
                e1 = ttk.Entry(cadre, textvariable=eff, width=4, justify="right")
                e2 = ttk.Entry(cadre, textvariable=abs_, width=3, justify="right")
                e1.pack(side="left")
                ttk.Label(cadre, text="/", background="#ffffff").pack(side="left", padx=1)
                e2.pack(side="left")
                self.cellules[(zone["id"], jour)] = (eff, abs_, [e1, e2])
        if not zones:
            ttk.Label(
                self.grille,
                text="Aucune zone active pour ce site.",
                style="Aide.TLabel",
                background="#ffffff",
            ).grid(row=2, column=0, columnspan=8, sticky="w")

    def charger_couts(self) -> None:
        couts = self.vue.executer(lambda: admin.lister_couts(self.ctx)) or []
        for ligne in couts:
            ligne["categorie_libelle"] = libelle(CATEGORIES_COUT, ligne["categorie"])
        self.historique_couts.charger(couts, message_vide="Aucun coût horaire enregistré.")
        self._couts_actuels = {}
        for ligne in sorted(couts, key=lambda lg: lg["date_debut"]):
            if ligne["date_debut"] <= date.today():
                self._couts_actuels[ligne["categorie"]] = ligne["taux"]
        for categorie, champ in self.champs_couts.items():
            champ.definir(self._couts_actuels.get(categorie))
            champ.effacer_erreur()
        self.devise.definir(couts[0]["devise"] if couts else configuration().devise)
        self.date_effet.definir(date.today())

    # --- Actions -------------------------------------------------------
    def enregistrer(self) -> None:
        site_id = self.site.valeur()
        if site_id is None:
            return
        valeurs = {}
        for cle, (eff, abs_, entrees) in self.cellules.items():
            for entree in entrees:
                entree.configure(style="TEntry")
            if eff.get().strip() == "" and abs_.get().strip() == "":
                continue
            valeurs[cle] = (eff.get(), abs_.get() or "0")
        try:
            nombre = admin.enregistrer_capacites(self.ctx, site_id, valeurs)
            couts_modifies = self._enregistrer_couts()
        except DonneesInvalides as exc:
            self._signaler(exc)
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.message_grille.configure(text="")
        informer(
            self,
            f"{nombre} capacités enregistrées"
            + (f" et {couts_modifies} coût(s) horaire(s) mis à jour." if couts_modifies else "."),
        )
        self.charger_grille()
        self.charger_couts()

    def _enregistrer_couts(self) -> int:
        modifies = 0
        erreurs = {}
        for categorie, champ in self.champs_couts.items():
            champ.effacer_erreur()
            saisie = champ.valeur_nombre()
            if champ.valeur() == "" or saisie == self._couts_actuels.get(categorie):
                continue
            try:
                admin.enregistrer_cout(
                    self.ctx,
                    categorie,
                    champ.valeur(),
                    self.devise.valeur(),
                    self.date_effet.texte(),
                )
                modifies += 1
            except DonneesInvalides as exc:
                message = exc.erreurs.get("taux") or next(iter(exc.erreurs.values()), exc.message)
                champ.signaler_erreur(message)
                erreurs[categorie] = message
        if erreurs:
            raise DonneesInvalides("Certains coûts horaires sont invalides.", {})
        return modifies

    def _signaler(self, exc: DonneesInvalides) -> None:
        messages = []
        for cle, message in exc.erreurs.items():
            zone_id, _, jour = cle.partition("_")
            try:
                cellule = self.cellules[(int(zone_id), date.fromisoformat(jour))]
            except (KeyError, ValueError):
                continue
            for entree in cellule[2]:
                entree.configure(style="Erreur.TEntry")
            messages.append(f"{formater_date(date.fromisoformat(jour))} : {message}")
        texte = exc.message + ("\n" + "\n".join(messages[:5]) if messages else "")
        self.message_grille.configure(text=texte, foreground=COULEURS["rouge"])

    def copier(self) -> None:
        site_id = self.site.valeur()
        if site_id is None:
            return
        lundi = self._lundi()
        if not confirmer(
            self,
            "Copier les capacités de la semaine précédente sur la semaine du "
            f"{formater_date(lundi)} ? Les valeurs existantes seront "
            "remplacées.",
            "Confirmer la copie",
        ):
            return
        nombre = self.vue.executer(
            lambda: admin.copier_semaine_precedente(self.ctx, site_id, lundi)
        )
        if nombre:
            informer(self, f"{nombre} capacités copiées depuis la semaine précédente.")
            self.charger_grille()
