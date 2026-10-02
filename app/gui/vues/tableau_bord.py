"""Écran 2 — Tableau de bord (UC22) : tous les rôles, contenu différent selon le rôle."""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.erreurs import ErreurApplication
from app.gui.style import COULEURS, COULEURS_STATUT, PUCE_STATUT
from app.gui.vues.base import Vue
from app.gui.vues.bloc_bottom_line import BlocBottomLine
from app.gui.widgets.carte import Carte
from app.gui.widgets.champs import ChampListe
from app.gui.widgets.dialogues import afficher_erreur
from app.gui.widgets.entete import BoutonIcone
from app.gui.widgets.graphique import (
    GraphiqueIntegre,
    couleur_methode,
    legende_en_haut,
    remplissage_degrade,
)
from app.gui.widgets.kpi import CarteHero, carte_stat
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.traces import anneau, barres_groupees, jauge
from app.libelles import (
    METHODES_COURTES,
    NIVEAUX_ALERTE,
    PERIODICITES,
    TYPES_ALERTE,
    libelle,
)
from app.services import admin, alertes, comparaison, kpi, planification
from app.services.droits import a_le_droit
from app.utils.dates import decaler_periode, libelle_periode, lundi_de
from app.utils.format_fr import formater_date, formater_nombre, formater_pourcentage

OPTIONS_PERIODICITE = list(PERIODICITES.items())
PERIODICITE_PAR_DEFAUT = {"planificateur": "jour", "responsable": "semaine", "direction": "mois"}

LIBELLES_STATUT = {
    "vert": "Conforme",
    "orange": "Vigilance",
    "rouge": "Critique",
    "gris": "Sans objectif",
}

TUILES_PLANIFICATEUR = [
    ("ADEQUATION", "Adéquation de l'effectif"),
    ("TAUX_DISPO_EQP", "Disponibilité des équipements"),
    ("JOURS_PENURIE", "Jours de pénurie d'équipements"),
]
TUILES_RESPONSABLE = [
    ("ADEQUATION", "Adéquation de l'effectif"),
    ("TAUX_A_TEMPS", "Commandes à temps"),
    ("TAUX_HS", "Taux d'heures supplémentaires"),
    ("TAUX_INTERIM", "Taux de recours à l'intérim"),
    ("PRODUCTIVITE", "Productivité"),
]
TUILES_DIRECTION = [
    ("TAUX_A_TEMPS", "Commandes à temps"),
    ("COUT_UNITE", "Coût RH par unité traitée"),
    ("ECART_COUT", "Écart de coût prévu / réel"),
]
#: Les deux premières cartes d'une rangée sont des cartes « héros » en dégradé.
DEGRADES_TUILES = ("rose", "cyan")

COLONNES_ECARTS = [
    Colonne("zone", "Zone", 140),
    Colonne("methode_libelle", "Méthode", 80, "center"),
    Colonne(
        "heures_prevues", "Heures prévues", 110, "e", formateur=lambda v: formater_nombre(v, 1)
    ),
    Colonne(
        "heures_reelles", "Heures réelles", 110, "e", formateur=lambda v: formater_nombre(v, 1)
    ),
    Colonne(
        "ecart_relatif",
        "Écart (%)",
        100,
        "e",
        formateur=lambda v: formater_pourcentage(v, 1, signe=True),
    ),
]

COLONNES_ALERTES = [
    Colonne("type_libelle", "Type", 170),
    Colonne("niveau_libelle", "Niveau", 90, "center"),
    Colonne("zone", "Zone", 110),
    Colonne("date_concernee", "Date concernée", 110, "center"),
    Colonne("message", "Message", 340),
]

ECART_CARTES = 16


def _formater_valeur(valeur, unite) -> str:
    if valeur is None:
        return "—"
    texte = formater_nombre(valeur, 1)
    return f"{texte} {unite}" if unite else texte


def _etiquette_alerte(ligne: dict) -> str | None:
    return ligne["niveau"]


def _trouver_kpi(valeurs: list[dict], code: str) -> dict | None:
    return next((v for v in valeurs if v["kpi_code"] == code), None)


def _serie(dates: list[date], valeurs_par_date: dict[date, float | None]) -> list[float]:
    """Valeurs alignées sur ``dates``, ``nan`` là où le KPI n'a pas encore été calculé (pour
    que le tracé laisse un blanc plutôt que d'échouer)."""
    return [v if (v := valeurs_par_date.get(jour)) is not None else float("nan") for jour in dates]


class VueTableauBord(BlocBottomLine, Vue):
    """Filtres Site/Zone/Période, navigation de période, et contenu propre à chaque rôle
    (planificateur, responsable, direction), en cartes."""

    titre = "Tableau de bord"
    sous_titre = "Vue d'ensemble adaptée au rôle"

    def construire(self) -> None:
        self.voit_les_alertes = a_le_droit(self.ctx, "lecture_alertes")
        self.voit_les_previsions = a_le_droit(self.ctx, "lecture_previsions")
        self.voit_le_plan = a_le_droit(self.ctx, "lecture_plan")
        self.periode_reference = date.today()

        filtres = Carte(self.contenu, marge=14)
        filtres.pack(fill="x")
        barre = filtres.zone
        self.site = ChampListe(barre, "Site", largeur=20)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(barre, "Zone", largeur=15)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_donnees)
        self.periode = ChampListe(barre, "Période", options=OPTIONS_PERIODICITE, largeur=9)
        self.periode.definir(PERIODICITE_PAR_DEFAUT.get(self.ctx.role, "semaine"))
        self.periode.pack(side="left", padx=(16, 0))
        self.periode.sur_changement(self._sur_changement_periode)

        nav = ttk.Frame(barre)
        nav.pack(side="right", pady=(16, 0))
        BoutonIcone(
            nav, "chevron_gauche", lambda: self._changer_periode(-1), "Période précédente", 36
        ).pack(side="left")
        self.label_periode = ttk.Label(nav, text="", style="Gras.TLabel", width=33, anchor="center")
        self.label_periode.pack(side="left", padx=8)
        BoutonIcone(
            nav, "chevron_droite", lambda: self._changer_periode(1), "Période suivante", 36
        ).pack(side="left")
        BoutonIcone(nav, "rafraichir", self.actualiser_donnees, "Actualiser les données", 36).pack(
            side="left", padx=(14, 0)
        )

        self.cadre_contenu = ttk.Frame(self.contenu, style="Page.TFrame")
        self.cadre_contenu.pack(fill="both", expand=True, pady=(ECART_CARTES, 0))

    # --- Chargement ---------------------------------------------------------
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
        self.actualiser_donnees()

    def _sur_changement_periode(self) -> None:
        self.periode_reference = date.today()
        self.actualiser_donnees()

    def _changer_periode(self, pas: int) -> None:
        self.periode_reference = decaler_periode(self.periode_reference, self.periode.valeur(), pas)
        self.actualiser_donnees()

    def _valeurs_kpi(self, site_id: int, zone_id: int | None, periodicite: str) -> list[dict]:
        valeurs = (
            self.executer(
                lambda: kpi.lister_kpi_valeurs(
                    self.ctx, site_id, zone_id, periodicite, self.periode_reference
                )
            )
            or []
        )
        self.dernieres_valeurs_kpi = valeurs
        return valeurs

    def actualiser_donnees(self) -> None:
        for enfant in self.cadre_contenu.winfo_children():
            enfant.destroy()
        site_id, zone_id = self.site.valeur(), self.zone.valeur()
        periodicite = self.periode.valeur()
        self.label_periode.configure(
            text=libelle_periode(self.periode_reference, periodicite).capitalize()
        )
        if site_id is None:
            ttk.Label(self.cadre_contenu, text="Choisissez un site.", style="PageAide.TLabel").pack(
                anchor="w"
            )
            return
        if self.ctx.role == "planificateur":
            self._construire_planificateur(site_id, zone_id, periodicite)
        elif self.ctx.role == "responsable":
            self._construire_responsable(site_id, zone_id, periodicite)
        elif self.ctx.role == "direction":
            self._construire_direction(site_id, zone_id, periodicite)

    # --- Briques de mise en page -------------------------------------------------
    def _rangee(self, poids: list[int]) -> ttk.Frame:
        """Rangée de cartes en colonnes proportionnelles à ``poids``."""
        ligne = ttk.Frame(self.cadre_contenu, style="Page.TFrame")
        ligne.pack(fill="x", pady=(0, ECART_CARTES))
        for colonne, poids_colonne in enumerate(poids):
            ligne.columnconfigure(colonne, weight=poids_colonne, uniform="colonne")
        ligne.rowconfigure(0, weight=1)
        return ligne

    @staticmethod
    def _placer(ligne: ttk.Frame, carte: tk.Widget, colonne: int, total: int) -> None:
        carte.grid(
            row=0,
            column=colonne,
            sticky="nsew",
            padx=(0, ECART_CARTES if colonne < total - 1 else 0),
        )

    def _carte_indicateur(
        self, ligne: ttk.Frame, colonne: int, total: int, titre: str, trouve: dict | None
    ) -> None:
        if trouve is None:
            valeur, detail, statut, libelle_statut = "—", "Pas encore calculé", None, "Non calculé"
        else:
            valeur = _formater_valeur(trouve["valeur"], trouve["unite"])
            detail = f"Cible {_formater_valeur(trouve['cible'], trouve['unite'])}"
            statut = trouve["statut"]
            libelle_statut = LIBELLES_STATUT.get(statut, "Non calculé")
        if colonne < len(DEGRADES_TUILES):
            carte = CarteHero(
                ligne, titre, valeur, detail, libelle_statut, DEGRADES_TUILES[colonne]
            )
        else:
            carte = carte_stat(ligne, titre, valeur, detail, statut, libelle_statut)
        self._placer(ligne, carte, colonne, total)

    def _construire_tuiles(self, codes: list[tuple[str, str]], valeurs: list[dict]) -> None:
        ligne = self._rangee([1] * len(codes))
        for colonne, (code, titre) in enumerate(codes):
            self._carte_indicateur(ligne, colonne, len(codes), titre, _trouver_kpi(valeurs, code))

    def _carte_graphique(
        self,
        ligne: ttk.Frame,
        colonne: int,
        total: int,
        titre: str,
        sous_titre: str = "",
        largeur: float = 5.4,
        hauteur: float = 2.7,
    ) -> GraphiqueIntegre:
        carte = Carte(ligne, titre, sous_titre)
        self._placer(ligne, carte, colonne, total)
        graphique = GraphiqueIntegre(carte.zone, largeur=largeur, hauteur=hauteur)
        graphique.pack(fill="both", expand=True)
        return graphique

    def _carte_anneau(
        self,
        ligne: ttk.Frame,
        colonne: int,
        total: int,
        titre: str,
        sous_titre: str,
        parts: list[tuple[str, int, str]],
        libelle_total: str,
    ) -> None:
        """Anneau de répartition : ``parts`` = ``(libellé, effectif, couleur)``, légende dessous."""
        carte = Carte(ligne, titre, sous_titre)
        self._placer(ligne, carte, colonne, total)
        graphique = GraphiqueIntegre(carte.zone, largeur=2.8, hauteur=2.1)
        graphique.pack(fill="both", expand=True)
        valeurs = [n for _l, n, _c in parts]
        graphique.dessiner(
            lambda axe: anneau(
                axe,
                valeurs,
                [c for _l, _n, c in parts],
                centre=str(sum(valeurs)),
                sous_centre=libelle_total,
            )
        )
        legende = ttk.Frame(carte.zone)
        legende.pack(fill="x", pady=(8, 0))
        for libelle_part, effectif, couleur in parts:
            ligne_legende = ttk.Frame(legende)
            ligne_legende.pack(fill="x", pady=1)
            ttk.Label(ligne_legende, text=PUCE_STATUT, foreground=couleur).pack(side="left")
            ttk.Label(ligne_legende, text=libelle_part).pack(side="left", padx=(6, 0))
            ttk.Label(ligne_legende, text=str(effectif), style="Gras.TLabel").pack(side="right")

    def _tableau_dans_carte(
        self,
        conteneur: tk.Widget,
        titre: str,
        sous_titre: str,
        colonnes: list[Colonne],
        hauteur: int,
    ) -> tuple[Carte, TableauTriable]:
        carte = Carte(conteneur, titre, sous_titre)
        tableau = TableauTriable(carte.zone, colonnes, hauteur=hauteur)
        tableau.pack(fill="both", expand=True)
        return carte, tableau

    # =====================================================================
    # Planificateur (vue jour par défaut)
    # =====================================================================
    def _construire_planificateur(
        self, site_id: int, zone_id: int | None, periodicite: str
    ) -> None:
        valeurs = self._valeurs_kpi(site_id, zone_id, periodicite)
        self._construire_tuiles(TUILES_PLANIFICATEUR, valeurs)

        ligne = self._rangee([3, 2])
        graphique_besoin = self._carte_graphique(
            ligne, 0, 2, "Besoin prévu et capacité", "Heures par zone, J+1 à J+7"
        )
        graphique_eqp = self._carte_graphique(
            ligne, 1, 2, "Disponibilité des équipements", "Taux sur la période", 3.2
        )
        self._dessiner_besoin_vs_capacite(graphique_besoin, site_id)
        self._dessiner_gauge_equipements(graphique_eqp, valeurs)

        carte_ecarts, self.tableau_ecarts = self._tableau_dans_carte(
            self.cadre_contenu, "Écarts de la veille", "Prévu contre réalisé", COLONNES_ECARTS, 6
        )
        carte_ecarts.pack(fill="x", pady=(0, ECART_CARTES))
        self._charger_ecarts_veille(self.tableau_ecarts, site_id, zone_id)

        if self.voit_les_alertes:
            ligne_alertes = self._rangee([1, 3])
            carte_alertes, self.tableau_alertes = self._tableau_dans_carte(
                ligne_alertes,
                "Alertes ouvertes",
                "Double-clic pour ouvrir l'alerte",
                COLONNES_ALERTES,
                6,
            )
            self.tableau_alertes.sur_double_clic(self._ouvrir_alerte)
            ouvertes = self._charger_alertes(self.tableau_alertes, site_id)
            parts = [
                (
                    "Critiques",
                    sum(1 for a in ouvertes if a["niveau"] == "rouge"),
                    COULEURS["rouge"],
                ),
                (
                    "Vigilance",
                    sum(1 for a in ouvertes if a["niveau"] == "orange"),
                    COULEURS["orange"],
                ),
            ]
            self._carte_anneau(
                ligne_alertes, 0, 2, "Alertes par niveau", "", parts, "alertes ouvertes"
            )
            self._placer(ligne_alertes, carte_alertes, 1, 2)

    def _dessiner_besoin_vs_capacite(self, graphique: GraphiqueIntegre, site_id: int) -> None:
        if not self.voit_les_previsions:
            graphique.afficher_message("Réservé aux rôles planificateur et responsable.")
            return
        try:
            lignes = planification.lister_previsions_ressources(self.ctx, site_id, None, 7)
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        if not lignes:
            graphique.afficher_message("Aucune prévision pour les 7 prochains jours.")
            return
        besoin_par_zone: dict[str, float] = {}
        for ligne in lignes:
            suffixe = (ligne.get("modele_actif") or "rl").lower()
            heures = ligne.get(f"heures_{suffixe}")
            if heures is not None:
                besoin_par_zone[ligne["zone"]] = besoin_par_zone.get(ligne["zone"], 0.0) + heures

        debut = date.today() + timedelta(days=1)
        fin = debut + timedelta(days=6)
        zones = self.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
        duree_poste = {z["id"]: z["duree_poste_heures"] for z in zones}
        noms_zone = {z["id"]: z["nom"] for z in zones}
        try:
            capacites = {
                **admin.lire_capacites(self.ctx, site_id, debut),
                **admin.lire_capacites(self.ctx, site_id, fin),
            }
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        capacite_par_zone: dict[str, float] = {}
        for (zone_id, jour), ligne in capacites.items():
            if debut <= jour <= fin:
                nom = noms_zone.get(zone_id, "—")
                capacite_par_zone[nom] = capacite_par_zone.get(nom, 0.0) + ligne[
                    "effectif_planifie"
                ] * duree_poste.get(zone_id, 0)

        zones_communes = sorted(set(besoin_par_zone) | set(capacite_par_zone))
        if not zones_communes:
            graphique.afficher_message("Aucune donnée exploitable.")
            return

        def _dessiner(axe):
            barres_groupees(
                axe,
                zones_communes,
                [
                    (
                        [besoin_par_zone.get(z, 0.0) for z in zones_communes],
                        COULEURS["primaire"],
                        "Besoin prévu",
                    ),
                    (
                        [capacite_par_zone.get(z, 0.0) for z in zones_communes],
                        COULEURS["vert"],
                        "Capacité",
                    ),
                ],
            )
            axe.set_ylabel("Heures")
            legende_en_haut(axe)

        graphique.dessiner(_dessiner)

    def _dessiner_gauge_equipements(self, graphique: GraphiqueIntegre, valeurs: list[dict]) -> None:
        trouve = _trouver_kpi(valeurs, "TAUX_DISPO_EQP")
        if trouve is None or trouve["valeur"] is None:
            graphique.afficher_message("Disponibilité non calculée.")
            return
        valeur = max(0.0, min(100.0, trouve["valeur"]))
        couleur = COULEURS_STATUT.get(trouve["statut"], COULEURS["gris"])
        graphique.dessiner(
            lambda axe: jauge(
                axe,
                valeur / 100,
                couleur,
                centre=f"{formater_nombre(valeur, 0)} %",
                sous_centre=LIBELLES_STATUT.get(trouve["statut"], ""),
            )
        )

    def _charger_ecarts_veille(
        self, tableau: TableauTriable, site_id: int, zone_id: int | None
    ) -> None:
        if not self.voit_les_previsions:
            tableau.charger([], message_vide="Réservé aux rôles planificateur et responsable.")
            return
        hier = date.today() - timedelta(days=1)
        lignes = (
            self.executer(
                lambda: comparaison.lister_comparaisons(self.ctx, site_id, zone_id, hier, hier)
            )
            or []
        )
        for ligne in lignes:
            ligne["methode_libelle"] = METHODES_COURTES.get(ligne["methode"], ligne["methode"])
        tableau.charger(lignes, cle_id="prevision_id", message_vide="Aucun écart pour hier.")

    def _charger_alertes(self, tableau: TableauTriable, site_id: int) -> list[dict]:
        ouvertes = self.executer(lambda: alertes.lister_alertes_ouvertes(self.ctx, site_id)) or []
        for ligne in ouvertes:
            ligne["type_libelle"] = libelle(TYPES_ALERTE, ligne["type"])
            ligne["niveau_libelle"] = f"{PUCE_STATUT} {libelle(NIVEAUX_ALERTE, ligne['niveau'])}"
        tableau.charger(
            ouvertes,
            cle_id="id",
            etiquettes=_etiquette_alerte,
            message_vide="Aucune alerte ouverte.",
        )
        return ouvertes

    def _ouvrir_alerte(self, ligne: dict) -> None:
        self.application.naviguer("alertes", alerte_id=ligne["id"])

    # =====================================================================
    # Responsable (vue semaine par défaut)
    # =====================================================================
    def _construire_responsable(self, site_id: int, zone_id: int | None, periodicite: str) -> None:
        valeurs = self._valeurs_kpi(site_id, zone_id, periodicite)
        self._construire_tuiles(TUILES_RESPONSABLE, valeurs)

        ligne = self._rangee([3, 2])
        graphique_heures = self._carte_graphique(
            ligne,
            0,
            2,
            "Réel contre prévisions",
            "Heures par semaine : réalisé, régression (RL), réseau (RN), boosting (GB)",
        )
        self._dessiner_reel_vs_previsions(graphique_heures, site_id)
        comptes = {"vert": 0, "orange": 0, "rouge": 0, "gris": 0}
        for v in valeurs:
            comptes[v["statut"] if v["statut"] in comptes else "gris"] += 1
        parts = [
            ("Conformes", comptes["vert"], COULEURS["vert"]),
            ("Vigilance", comptes["orange"], COULEURS["orange"]),
            ("Critiques", comptes["rouge"], COULEURS["rouge"]),
            ("Sans objectif", comptes["gris"], COULEURS["gris"]),
        ]
        self._carte_anneau(
            ligne, 1, 2, "Santé des KPI", "Indicateurs de la période", parts, "indicateurs"
        )

        precision = [v for code in ("MAPE_H", "BIAIS_H") for v in valeurs if v["kpi_code"] == code]
        if precision:
            ligne_precision = self._rangee([1] * len(precision))
            for colonne, v in enumerate(precision):
                self._carte_indicateur_precision(ligne_precision, colonne, len(precision), v)

        self._construire_bottom_line(site_id, zone_id, periodicite)

    def _carte_indicateur_precision(
        self, ligne: ttk.Frame, colonne: int, total: int, v: dict
    ) -> None:
        titre = f"{v['kpi_libelle']} — {METHODES_COURTES.get(v['methode'], v['methode'])}"
        carte = carte_stat(
            ligne,
            titre,
            _formater_valeur(v["valeur"], v["unite"]),
            "",
            v["statut"],
            LIBELLES_STATUT.get(v["statut"], "Non calculé"),
        )
        self._placer(ligne, carte, colonne, total)

    def _dessiner_reel_vs_previsions(self, graphique: GraphiqueIntegre, site_id: int) -> None:
        if not self.voit_les_previsions:
            graphique.afficher_message("Réservé aux rôles planificateur et responsable.")
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
            graphique.afficher_message("Pas encore de réalisé comparable.")
            return

        semaines: dict[date, dict[str, float]] = {}
        zones_vues_par_jour: dict[date, set[int]] = {}
        for r in rapprochements:
            semaine = lundi_de(r["date_jour"])
            acc = semaines.setdefault(
                semaine,
                {
                    "reel": 0.0,
                    "regression_lineaire": 0.0,
                    "reseau_neurones": 0.0,
                    "gradient_boosting": 0.0,
                },
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
            reel = [v["reel"] for _, v in points]
            axe.plot(
                libelles,
                reel,
                marker="o",
                markersize=4,
                linewidth=2.2,
                color=COULEURS["primaire"],
                label="Réalisé",
            )
            remplissage_degrade(axe, libelles, reel, COULEURS["primaire"])
            axe.plot(
                libelles,
                [v["regression_lineaire"] for _, v in points],
                marker="o",
                markersize=3,
                linewidth=1.8,
                color=COULEURS["orange"],
                label="Prévu (RL)",
            )
            axe.plot(
                libelles,
                [v["reseau_neurones"] for _, v in points],
                marker="o",
                markersize=3,
                linewidth=1.8,
                color=COULEURS["vert"],
                label="Prévu (RN)",
            )
            axe.plot(
                libelles,
                [v["gradient_boosting"] for _, v in points],
                marker="o",
                markersize=3,
                linewidth=1.8,
                color=couleur_methode("gradient_boosting"),
                label="Prévu (GB)",
            )
            axe.set_ylabel("Heures / semaine")
            legende_en_haut(axe)

        graphique.dessiner(_dessiner)

    # =====================================================================
    # Direction (vue mois par défaut)
    # =====================================================================
    def _construire_direction(self, site_id: int, zone_id: int | None, periodicite: str) -> None:
        valeurs = self._valeurs_kpi(site_id, zone_id, periodicite)
        self._construire_tuiles(TUILES_DIRECTION, valeurs)

        ligne = self._rangee([3, 2])
        graphique_tendances = self._carte_graphique(
            ligne, 0, 2, "Tendances sur 12 mois", "Adéquation de l'effectif et commandes à temps"
        )
        graphique_victoire = self._carte_graphique(
            ligne,
            1,
            2,
            "Taux de victoire",
            "Régression linéaire, réseau de neurones et gradient boosting",
            3.4,
        )
        self._dessiner_tendances_12_mois(graphique_tendances, site_id, zone_id)
        self._dessiner_taux_victoire(graphique_victoire, valeurs)

        self._construire_progression(site_id, zone_id)
        self._construire_bottom_line(site_id, zone_id, periodicite)

    def _dessiner_tendances_12_mois(
        self, graphique: GraphiqueIntegre, site_id: int, zone_id: int | None
    ) -> None:
        adequation = (
            self.executer(
                lambda: kpi.historique_kpi(
                    self.ctx, site_id, zone_id, "ADEQUATION", "mois", nb_periodes=12
                )
            )
            or []
        )
        a_temps = (
            self.executer(
                lambda: kpi.historique_kpi(
                    self.ctx, site_id, zone_id, "TAUX_A_TEMPS", "mois", nb_periodes=12
                )
            )
            or []
        )
        if not adequation and not a_temps:
            graphique.afficher_message("Historique mensuel insuffisant.")
            return
        dates = sorted({v["date_debut_periode"] for v in adequation + a_temps})
        par_adequation = {v["date_debut_periode"]: v["valeur"] for v in adequation}
        par_a_temps = {v["date_debut_periode"]: v["valeur"] for v in a_temps}

        def _dessiner(axe):
            serie_adequation = _serie(dates, par_adequation)
            axe.plot(
                dates,
                serie_adequation,
                marker="o",
                markersize=3,
                linewidth=2.2,
                color=COULEURS["primaire"],
                label="Adéquation de l'effectif (%)",
            )
            remplissage_degrade(axe, dates, serie_adequation, COULEURS["primaire"])
            axe.plot(
                dates,
                _serie(dates, par_a_temps),
                marker="o",
                markersize=3,
                linewidth=1.8,
                color=COULEURS["orange"],
                label="Commandes à temps (%)",
            )
            axe.set_ylabel("%")
            legende_en_haut(axe)
            axe.tick_params(axis="x", rotation=30, labelsize=7)

        graphique.dessiner(_dessiner)

    def _dessiner_taux_victoire(self, graphique: GraphiqueIntegre, valeurs: list[dict]) -> None:
        lignes = [
            v for v in valeurs if v["kpi_code"] == "TAUX_VICTOIRE" and v["valeur"] is not None
        ]
        if not lignes:
            graphique.afficher_message("Taux de victoire non calculé.")
            return

        def _dessiner(axe):
            methodes = [METHODES_COURTES.get(v["methode"], v["methode"]) for v in lignes]
            valeurs_pct = [v["valeur"] for v in lignes]
            couleurs = [
                COULEURS["primaire"],
                COULEURS["orange"],
                couleur_methode("gradient_boosting"),
            ]
            for rang, valeur in enumerate(valeurs_pct):
                barres_groupees(
                    axe,
                    methodes,
                    [
                        (
                            [valeur if i == rang else None for i in range(len(methodes))],
                            couleurs[rang % 3],
                            None,
                        )
                    ],
                    largeur_groupe=0.46,
                )
            axe.set_ylim(0, 100)
            axe.set_ylabel("%")
            for i, v in enumerate(valeurs_pct):
                axe.text(
                    i,
                    min(v + 3, 96),
                    f"{formater_nombre(v, 0)} %",
                    ha="center",
                    fontsize=9,
                    fontweight="bold",
                    color=COULEURS["texte"],
                )

        graphique.dessiner(_dessiner)

    def _construire_progression(self, site_id: int, zone_id: int | None) -> None:
        historique = (
            self.executer(
                lambda: kpi.historique_kpi(
                    self.ctx, site_id, zone_id, "ADEQUATION", "mois", nb_periodes=24
                )
            )
            or []
        )
        utilisables = [v for v in historique if v["valeur"] is not None]
        carte = Carte(
            self.cadre_contenu,
            "Progression de l'adéquation",
            "Depuis la situation de référence",
        )
        carte.pack(fill="x")
        if len(utilisables) < 2:
            ttk.Label(carte.zone, text="Historique mensuel insuffisant.", style="Aide.TLabel").pack(
                anchor="w"
            )
            return
        reference, actuelle = utilisables[0], utilisables[-1]
        delta = actuelle["valeur"] - reference["valeur"]
        signe = "+" if delta >= 0 else ""
        ttk.Label(
            carte.zone,
            text=f"{signe}{formater_nombre(delta, 1)} points",
            font=("", 22, "bold"),
            foreground=COULEURS["vert"] if delta >= 0 else COULEURS["rouge"],
        ).pack(anchor="w")
        ttk.Label(
            carte.zone,
            text=(
                f"Depuis le {formater_date(reference['date_debut_periode'])} "
                f"(référence : {formater_nombre(reference['valeur'], 1)} %, "
                f"actuel : {formater_nombre(actuelle['valeur'], 1)} %)"
            ),
            style="Aide.TLabel",
        ).pack(anchor="w", pady=(2, 0))
