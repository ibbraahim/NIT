"""Écran 5 — Plan de charge (UC12, UC13, UC14)."""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.erreurs import ConflitMiseAJour, DonneesInvalides, ErreurApplication
from app.gui.style import COULEURS, COULEURS_STATUT, PUCE_STATUT, a_chaque_theme
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampListe, ChampNombre
from app.gui.widgets.dialogues import (
    DialogueBase,
    afficher_erreur,
    confirmer,
    informer,
    saisir_texte,
)
from app.gui.widgets.entete import BoutonIcone
from app.gui.widgets.infobulle import InfoBulle
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.libelles import STATUTS_PLAN, TYPES_EQUIPEMENT
from app.services import admin, planification
from app.services.planification import STATUTS_MODIFIABLES
from app.utils.dates import jours_semaine, lundi_de
from app.utils.format_fr import formater_date, formater_jour_court, formater_nombre

COULEUR_CASE: dict[str | None, str] = {}


@a_chaque_theme
def _couleurs_cases() -> None:
    COULEUR_CASE.update(
        {
            "rouge": COULEURS["rouge_clair"],
            "orange": COULEURS["orange_clair"],
            None: COULEURS["surface_2"],
        }
    )


class LienAction(tk.Label):
    """Petite action textuelle (« Commentaire ») : accent, soulignée au survol, activable."""

    def __init__(self, parent, texte: str, commande, fond: str) -> None:
        self._commande = commande
        self._actif = True
        self._fond = fond
        super().__init__(
            parent,
            text=texte,
            foreground=COULEURS["accent"],
            background=fond,
            font=("", 8, "bold"),
            cursor="hand2",
        )
        self.bind("<Enter>", lambda _e: self._souligner(True))
        self.bind("<Leave>", lambda _e: self._souligner(False))
        self.bind("<ButtonRelease-1>", lambda _e: self.invoke())

    def _souligner(self, oui: bool) -> None:
        if self._actif:
            self.configure(font=("", 8, "bold underline" if oui else "bold"))

    def invoke(self) -> None:
        if self._actif:
            self._commande()

    def activer(self, actif: bool, raison: str = "") -> None:
        self._actif = actif
        self.configure(
            foreground=COULEURS["accent"] if actif else COULEURS["desactive"],
            cursor="hand2" if actif else "arrow",
        )


class VuePlanCharge(Vue):
    """Grille éditable zones × jours ; boutons selon le rôle."""

    titre = "Plan de charge"
    sous_titre = "Effectif, intérim et équipements par zone et par jour"

    def construire(self) -> None:
        self.semaine = lundi_de(date.today())
        self.plan_donnees: dict | None = None
        self.zones: list[dict] = []
        self.cellules: dict[tuple, dict] = {}

        barre_filtres = self.barre_filtres()
        self.site = ChampListe(barre_filtres, "Site", largeur=24)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        nav = ttk.Frame(barre_filtres)
        nav.pack(side="right", pady=(16, 0))
        BoutonIcone(
            nav, "chevron_gauche", lambda: self._changer_semaine(-1), "Semaine précédente", 36
        ).pack(side="left")
        self.label_semaine = ttk.Label(nav, text="", style="Gras.TLabel", width=34, anchor="center")
        self.label_semaine.pack(side="left", padx=8)
        BoutonIcone(
            nav, "chevron_droite", lambda: self._changer_semaine(1), "Semaine suivante", 36
        ).pack(side="left")

        carte = self.carte(
            "Plan de la semaine",
            "Effectif, intérim et équipements par zone et par jour",
            dernier=True,
        )
        self.label_statut = ttk.Label(carte.actions, text="", style="Gras.TLabel")
        self.label_statut.pack(side="right")
        self.label_commentaire = ttk.Label(carte.zone, text="", style="Aide.TLabel", wraplength=900)
        self.label_commentaire.pack(anchor="w")

        zone_grille = ttk.Frame(carte.zone)
        zone_grille.pack(fill="both", expand=True, pady=(4, 8))
        self._canevas_grille = tk.Canvas(
            zone_grille, highlightthickness=0, background=COULEURS["surface"]
        )
        ascenseur_h = ttk.Scrollbar(
            zone_grille, orient="horizontal", command=self._canevas_grille.xview
        )
        self._canevas_grille.configure(xscrollcommand=ascenseur_h.set)
        self._canevas_grille.pack(side="top", fill="both", expand=True)
        ascenseur_h.pack(side="bottom", fill="x")

        self.cadre_grille = ttk.Frame(self._canevas_grille)
        self._canevas_grille.create_window((0, 0), window=self.cadre_grille, anchor="nw")

        def _grille_a_jour(_evenement=None) -> None:
            self._canevas_grille.configure(scrollregion=self._canevas_grille.bbox("all"))
            self._canevas_grille.configure(height=self.cadre_grille.winfo_reqheight())

        self.cadre_grille.bind("<Configure>", _grille_a_jour)

        def _molette_horizontale(evenement) -> None:
            self._canevas_grille.xview_scroll(int(-1 * (evenement.delta / 120)), "units")

        self._canevas_grille.bind(
            "<Enter>",
            lambda _e: self._canevas_grille.bind_all("<Shift-MouseWheel>", _molette_horizontale),
        )
        self._canevas_grille.bind(
            "<Leave>", lambda _e: self._canevas_grille.unbind_all("<Shift-MouseWheel>")
        )

        barre = ttk.Frame(carte.zone)
        barre.pack(fill="x", pady=(6, 0))
        if self.ctx.role == "planificateur":
            Bouton(barre, "Proposer le plan", self.proposer, primaire=True).pack(side="left")
            Bouton(barre, "Simuler un scénario…", self.simuler).pack(side="left", padx=(8, 0))
            Bouton(barre, "Enregistrer le brouillon", self.enregistrer_brouillon).pack(
                side="left", padx=(8, 0)
            )
            Bouton(barre, "Soumettre pour validation", self.soumettre).pack(
                side="left", padx=(8, 0)
            )
        elif self.ctx.role == "responsable":
            Bouton(barre, "Valider le plan", self.valider).pack(side="left")
            Bouton(barre, "Rejeter le plan…", self.rejeter).pack(side="left", padx=(8, 0))
        self.boutons_action = list(barre.winfo_children())

    # --- Chargement ---------------------------------------------------------
    def actualiser(self) -> None:
        sites = self.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self._sur_changement_site()

    def _sur_changement_site(self) -> None:
        self.charger_semaine()

    def _changer_semaine(self, pas: int) -> None:
        self.semaine += timedelta(weeks=pas)
        self.charger_semaine()

    def _lire_plan(self, site_id: int) -> dict | None:
        """Lit le plan de la semaine ; ``None`` est une réponse valide (pas encore de plan),
        donc appelé hors de :meth:`executer` qui la confondrait avec un succès sans donnée."""
        try:
            return planification.lire_plan_charge(self.ctx, site_id, self.semaine)
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return None

    def charger_semaine(self) -> None:
        site_id = self.site.valeur()
        self.label_semaine.configure(
            text=f"Semaine du {formater_date(self.semaine)} au "
            f"{formater_date(self.semaine + timedelta(days=6))}"
        )
        if site_id is None:
            self.zones = []
            self.plan_donnees = None
            self._construire_grille()
            self._mettre_a_jour_statut()
            self._mettre_a_jour_boutons()
            return
        self.zones = self.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
        self.plan_donnees = self._lire_plan(site_id)
        self._construire_grille()
        self._mettre_a_jour_statut()
        self._mettre_a_jour_boutons()

    # --- Statut et boutons ---------------------------------------------------
    def _mettre_a_jour_statut(self) -> None:
        if self.plan_donnees is None:
            self.label_statut.configure(
                text="Aucun plan pour cette semaine.", foreground=COULEURS["texte_secondaire"]
            )
            self.label_commentaire.configure(text="")
            return
        plan = self.plan_donnees["plan"]
        couleur = {
            "brouillon": COULEURS["gris"],
            "soumis": COULEURS["orange"],
            "valide": COULEURS["vert"],
            "rejete": COULEURS["rouge"],
        }[plan["statut"]]
        self.label_statut.configure(
            text=f"{PUCE_STATUT} Statut : {STATUTS_PLAN[plan['statut']]}", foreground=couleur
        )
        self.label_commentaire.configure(
            text=(
                f"Motif du rejet : {plan['commentaire']}"
                if plan["statut"] == "rejete" and plan["commentaire"]
                else ""
            )
        )

    def _mettre_a_jour_boutons(self) -> None:
        site_choisi = self.site.valeur() is not None
        modifiable = (
            self.plan_donnees is None or self.plan_donnees["plan"]["statut"] in STATUTS_MODIFIABLES
        )
        soumis = self.plan_donnees is not None and self.plan_donnees["plan"]["statut"] == "soumis"
        for bouton in self.boutons_action:
            texte = bouton.cget("text")
            if texte == "Proposer le plan":
                bouton.activer(
                    site_choisi and modifiable,
                    (
                        "Choisissez un site."
                        if not site_choisi
                        else "Le plan de cette semaine n'est plus modifiable."
                    ),
                )
            elif texte in (
                "Simuler un scénario…",
                "Enregistrer le brouillon",
                "Soumettre pour validation",
            ):
                bouton.activer(
                    self.plan_donnees is not None and modifiable,
                    (
                        "Proposez d'abord le plan."
                        if self.plan_donnees is None
                        else "Le plan de cette semaine n'est plus modifiable."
                    ),
                )
            elif texte in ("Valider le plan", "Rejeter le plan…"):
                bouton.activer(soumis, "Seul un plan soumis peut être traité.")

    # --- Grille ---------------------------------------------------------------
    def _construire_grille(self) -> None:
        for enfant in self.cadre_grille.winfo_children():
            enfant.destroy()
        self.cellules.clear()
        jours = jours_semaine(self.semaine)
        modifiable = (
            self.ctx.role == "planificateur"
            and self.plan_donnees is not None
            and self.plan_donnees["plan"]["statut"] in STATUTS_MODIFIABLES
        )
        ttk.Label(self.cadre_grille, text="Zone", style="KpiTitre.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 6)
        )
        for c, jour in enumerate(jours, start=1):
            ttk.Label(
                self.cadre_grille, text=formater_jour_court(jour), style="KpiTitre.TLabel"
            ).grid(row=0, column=c, pady=(0, 6))
        if not self.zones:
            ttk.Label(self.cadre_grille, text="Choisissez un site.", style="Aide.TLabel").grid(
                row=1, column=0, sticky="w"
            )
            return
        lignes_index = {}
        if self.plan_donnees is not None:
            lignes_index = {(l["zone_id"], l["date_jour"]): l for l in self.plan_donnees["lignes"]}
        for r, zone in enumerate(self.zones, start=1):
            ttk.Label(self.cadre_grille, text=zone["nom"], style="Gras.TLabel").grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=3
            )
            for c, jour in enumerate(jours, start=1):
                ligne = lignes_index.get((zone["id"], jour))
                self._construire_cellule(r, c, zone, jour, ligne, modifiable)

    def _construire_cellule(
        self, r: int, c: int, zone: dict, jour: date, ligne: dict | None, modifiable: bool
    ) -> None:
        couleurs = COULEURS
        if ligne is None:
            cadre = tk.Frame(
                self.cadre_grille,
                background=couleurs["surface_2"],
                highlightbackground=couleurs["bordure"],
                highlightthickness=1,
            )
            cadre.grid(row=r, column=c, padx=2, pady=3, sticky="nsew")
            tk.Label(
                cadre,
                text="—",
                background=couleurs["surface_2"],
                foreground=couleurs["texte_secondaire"],
            ).pack(expand=True, pady=30)
            return
        statut = planification.statut_couleur_ligne(ligne)
        fond_case = COULEUR_CASE[statut]
        cadre = tk.Frame(
            self.cadre_grille,
            background=fond_case,
            highlightbackground=(
                COULEURS_STATUT.get(statut, couleurs["bordure"]) if statut else couleurs["bordure"]
            ),
            highlightthickness=1,
        )
        cadre.grid(row=r, column=c, padx=2, pady=3, sticky="nsew")
        interieur = tk.Frame(cadre, background=fond_case)
        interieur.pack(padx=6, pady=6)
        fond = {"background": fond_case}
        tk.Label(
            interieur,
            text=f"Besoin {formater_nombre(ligne['besoin_heures'], 0)} h",
            foreground=couleurs["texte"],
            font=("", 9, "bold"),
            **fond,
        ).pack(anchor="w")
        tk.Label(
            interieur,
            text=f"{ligne['besoin_effectif']} p · {ligne['besoin_equipements']} éq",
            foreground=couleurs["texte_secondaire"],
            font=("", 8),
            **fond,
        ).pack(anchor="w")

        saisie = tk.Frame(interieur, **fond)
        saisie.pack(anchor="w", pady=(5, 4))
        var_eff = tk.StringVar(value=str(ligne["effectif_planifie"]))
        var_int = tk.StringVar(value=str(ligne["interim_planifie"]))
        var_eqp = tk.StringVar(value=str(ligne["equipements_planifies"]))
        for colonne, (prefixe, variable) in enumerate(
            (("Plan.", var_eff), ("Intér.", var_int), ("Équip.", var_eqp))
        ):
            tk.Label(
                saisie, text=prefixe, foreground=couleurs["texte_secondaire"], font=("", 7), **fond
            ).grid(row=0, column=colonne, sticky="w", padx=(0 if colonne == 0 else 4, 0))
            entree = tk.Entry(
                saisie,
                textvariable=variable,
                width=3,
                justify="center",
                relief="flat",
                borderwidth=2,
                highlightthickness=1,
                highlightbackground=couleurs["champ_bordure"],
                highlightcolor=couleurs["accent"],
                background=couleurs["champ"],
                foreground=couleurs["texte"],
                insertbackground=couleurs["texte"],
                disabledbackground=couleurs["surface_2"],
                disabledforeground=couleurs["texte_secondaire"],
                state="normal" if modifiable else "disabled",
            )
            entree.grid(row=1, column=colonne, padx=(0 if colonne == 0 else 4, 0))

        tk.Label(
            interieur,
            text=f"Capacité {ligne['capacite_effectif']} p · {ligne['capacite_equipements']} éq",
            foreground=couleurs["texte_secondaire"],
            font=("", 8),
            **fond,
        ).pack(anchor="w")

        commentaire_var = {"texte": ligne["commentaire"]}
        texte_bouton = "Commentaire ✓" if ligne["commentaire"] else "Commentaire"
        bouton_commentaire = LienAction(
            interieur, texte_bouton, lambda: self._editer_commentaire(zone["id"], jour), fond_case
        )
        bouton_commentaire.pack(anchor="w", pady=(3, 0))
        InfoBulle(bouton_commentaire, ligne["commentaire"] or "Aucun commentaire.")
        if not modifiable:
            bouton_commentaire.activer(False, "Le plan n'est plus modifiable.")

        self.cellules[(zone["id"], jour)] = {
            "effectif": var_eff,
            "interim": var_int,
            "equipements": var_eqp,
            "commentaire": commentaire_var,
            "bouton_commentaire": bouton_commentaire,
            "ligne": ligne,
        }

    def _editer_commentaire(self, zone_id: int, jour: date) -> None:
        cellule = self.cellules[(zone_id, jour)]
        texte = saisir_texte(
            self,
            "Commentaire de la case",
            "Commentaire",
            obligatoire=False,
            valeur=cellule["commentaire"]["texte"],
            message="Obligatoire si le besoin dépasse la capacité, avant de soumettre le plan.",
        )
        if texte is None:
            return
        cellule["commentaire"]["texte"] = texte
        cellule["bouton_commentaire"].configure(text="Commentaire ✓" if texte else "Commentaire")

    def _lignes_saisies(self) -> list[dict]:
        return [
            {
                "zone_id": zone_id,
                "date_jour": jour,
                "effectif_planifie": c["effectif"].get(),
                "interim_planifie": c["interim"].get(),
                "equipements_planifies": c["equipements"].get(),
                "commentaire": c["commentaire"]["texte"],
            }
            for (zone_id, jour), c in self.cellules.items()
        ]

    # --- Actions planificateur -------------------------------------------------
    def proposer(self) -> None:
        site_id = self.site.valeur()
        if site_id is None:
            return
        resultat = self.executer(
            lambda: planification.proposer_plan_charge(self.ctx, site_id, self.semaine)
        )
        if resultat is None:
            return
        self.charger_semaine()
        message = "Plan proposé à partir des prévisions."
        if resultat["avertissements"]:
            message += "\n\nAvertissements :\n" + "\n".join(resultat["avertissements"])
        informer(self, message, "Plan proposé")

    def enregistrer_brouillon(self) -> None:
        if self.plan_donnees is None:
            return
        plan_id = self.plan_donnees["plan"]["id"]
        date_maj = self.plan_donnees["plan"]["date_maj"]
        try:
            planification.enregistrer_brouillon_plan(
                self.ctx, plan_id, self._lignes_saisies(), date_maj
            )
        except ConflitMiseAJour as exc:
            self.charger_semaine()
            afficher_erreur(self, exc.message)
            return
        except DonneesInvalides as exc:
            afficher_erreur(self, exc.message)
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.charger_semaine()
        informer(self, "Brouillon enregistré.")

    def soumettre(self) -> None:
        if self.plan_donnees is None:
            return
        plan_id = self.plan_donnees["plan"]["id"]
        date_maj = self.plan_donnees["plan"]["date_maj"]
        try:
            planification.enregistrer_brouillon_plan(
                self.ctx, plan_id, self._lignes_saisies(), date_maj
            )
            planification.soumettre_plan(self.ctx, plan_id)
        except ConflitMiseAJour as exc:
            self.charger_semaine()
            afficher_erreur(self, exc.message)
            return
        except DonneesInvalides as exc:
            afficher_erreur(self, exc.message)
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.charger_semaine()
        informer(self, "Plan soumis pour validation.")

    def simuler(self) -> None:
        if self.plan_donnees is None:
            return
        types_presents = sorted({z["type_equipement_principal"] for z in self.zones})
        FenetreScenario(
            self, self.ctx, self.plan_donnees["plan"]["id"], types_presents, self.charger_semaine
        )

    # --- Actions responsable -------------------------------------------------
    def valider(self) -> None:
        if self.plan_donnees is None:
            return
        if not confirmer(
            self,
            "Valider ce plan de charge ? Il deviendra la référence de "
            "l'adéquation de l'effectif.",
            "Confirmer la validation",
        ):
            return
        if self.executer(
            lambda: planification.valider_plan(self.ctx, self.plan_donnees["plan"]["id"])
        ):
            self.charger_semaine()
            informer(self, "Plan validé.")

    def rejeter(self) -> None:
        if self.plan_donnees is None:
            return
        commentaire = saisir_texte(self, "Rejeter le plan", "Motif du rejet", obligatoire=True)
        if commentaire is None:
            return
        try:
            planification.rejeter_plan(self.ctx, self.plan_donnees["plan"]["id"], commentaire)
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.charger_semaine()
        informer(self, "Plan rejeté.")


class FenetreScenario(DialogueBase):
    """UC13 : hypothèses, boutons « Calculer », « Appliquer au plan », « Fermer »."""

    def __init__(
        self, parent, ctx, plan_id: int, types_equipement: list[str], sur_fermeture
    ) -> None:
        super().__init__(parent, "Simuler un scénario", redimensionnable=True)
        self.ctx = ctx
        self.plan_id = plan_id
        self.sur_fermeture = sur_fermeture
        self.scenario_id: int | None = None

        formulaire = ttk.Frame(self.corps)
        formulaire.pack(fill="x")
        self.variation = ChampNombre(formulaire, "Variation du volume (%)", decimales=0)
        self.variation.definir(0)
        self.variation.grid(row=0, column=0, sticky="w", padx=(0, 16))
        self.absence = ChampNombre(formulaire, "Taux d'absence (%)", decimales=0)
        self.absence.definir(0)
        self.absence.grid(row=0, column=1, sticky="w", padx=(0, 16))
        self.equipements: dict[str, ChampNombre] = {}
        for i, type_eqp in enumerate(types_equipement):
            champ = ChampNombre(
                formulaire, f"{TYPES_EQUIPEMENT.get(type_eqp, type_eqp)} indisponibles", decimales=0
            )
            champ.definir(0)
            champ.grid(row=1, column=i, sticky="w", padx=(0, 16), pady=(8, 0))
            self.equipements[type_eqp] = champ

        ttk.Label(
            self.corps,
            text="Avant / après (Σ besoin en heures et effectif planifié " "de la semaine)",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(14, 4))
        self.tableau = TableauTriable(
            self.corps,
            [
                Colonne("zone", "Zone", 130),
                Colonne("date_jour", "Date", 100, "center"),
                Colonne("besoin_avant", "Besoin avant (h)", 120, "e"),
                Colonne("besoin_apres", "Besoin après (h)", 120, "e"),
                Colonne("effectif_avant", "Effectif avant", 110, "e"),
                Colonne("effectif_apres", "Effectif après", 110, "e"),
            ],
            hauteur=8,
        )
        self.tableau.pack(fill="both", expand=True)

        self.ajouter_bouton("Fermer", self.fermer)
        self.b_appliquer = self.ajouter_bouton("Appliquer au plan", self._appliquer, primaire=True)
        self.b_appliquer.state(["disabled"])
        self.ajouter_bouton("Calculer", self._calculer)
        self.afficher()

    def _hypotheses(self) -> dict:
        return {
            "variation_volume_pct": self.variation.valeur(),
            "taux_absence_pct": self.absence.valeur(),
            "equipements_indisponibles": {t: c.valeur() for t, c in self.equipements.items()},
        }

    def _calculer(self) -> None:
        try:
            resultat = planification.simuler_scenario(self.ctx, self.plan_id, self._hypotheses())
        except DonneesInvalides as exc:
            afficher_erreur(self, exc.message)
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.scenario_id = resultat["scenario_id"]
        zones = {ligne["zone_id"]: ligne.get("zone", "") for ligne in resultat["avant"]}
        lignes_tableau = []
        for avant, apres in zip(resultat["avant"], resultat["apres"], strict=True):
            lignes_tableau.append(
                {
                    "_id": f"{avant['zone_id']}_{avant['date_jour']}",
                    "zone": zones.get(avant["zone_id"], str(avant["zone_id"])),
                    "date_jour": avant["date_jour"],
                    "besoin_avant": avant["besoin_heures"],
                    "besoin_apres": apres["besoin_heures"],
                    "effectif_avant": avant["effectif_planifie"],
                    "effectif_apres": apres["effectif_planifie"],
                }
            )
        self.tableau.charger(lignes_tableau, cle_id="_id")
        self.b_appliquer.state(["!disabled"])

    def _appliquer(self) -> None:
        if self.scenario_id is None:
            return
        try:
            planification.appliquer_scenario(self.ctx, self.scenario_id)
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self.sur_fermeture()
        informer(self, "Scénario appliqué au plan.")
        self.fermer()
