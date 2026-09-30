"""Écran 2 — Tableau de bord (UC22) : tous les rôles, contenu différent selon le rôle."""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

import numpy as np

from app.erreurs import ErreurApplication
from app.gui.degrades import image_degradee
from app.gui.style import (
    COULEUR_ACCENT_3,
    COULEURS,
    COULEURS_DEGRADE_MARQUE,
    COULEURS_STATUT,
    COULEURS_STATUT_CLAIR,
    PUCE_STATUT,
)
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampListe
from app.gui.widgets.dialogues import afficher_erreur
from app.gui.widgets.graphique import GraphiqueIntegre, remplissage_degrade
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
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

LIBELLES_STATUT = {"vert": "Conforme", "orange": "Vigilance", "rouge": "Critique"}

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


def _etiquette_alerte(ligne: dict) -> str | None:
    return ligne["niveau"]


def _trouver_kpi(valeurs: list[dict], code: str) -> dict | None:
    return next((v for v in valeurs if v["kpi_code"] == code), None)


def _lier_survol_tuile(cadre: tk.Frame, couleur_repos: str, couleur_survol: str) -> None:
    """Illumine la bordure de ``cadre`` au survol de la tuile (élévation légère, équivalent
    statique du « hover » de la référence visuelle). Lié à tous les descendants : les
    événements Entrer/Sortir de Tk ne remontent pas d'un enfant vers son parent, et un « Sortir »
    déclenché en passant d'un enfant à un autre (donc toujours à l'intérieur de la tuile) est
    ignoré grâce à une vérification du widget réellement sous le pointeur."""

    def _entrer(_evenement=None) -> None:
        cadre.configure(highlightbackground=couleur_survol, highlightcolor=couleur_survol)

    def _sortir(_evenement=None) -> None:
        x, y = cadre.winfo_pointerxy()
        sous_pointeur = cadre.winfo_containing(x, y)
        if sous_pointeur is not None and str(sous_pointeur).startswith(str(cadre)):
            return
        cadre.configure(highlightbackground=couleur_repos, highlightcolor=couleur_repos)

    for widget in (cadre, *cadre.winfo_children()):
        widget.bind("<Enter>", _entrer, add="+")
        widget.bind("<Leave>", _sortir, add="+")
        for petit_enfant in widget.winfo_children():
            petit_enfant.bind("<Enter>", _entrer, add="+")
            petit_enfant.bind("<Leave>", _sortir, add="+")


def _construire_tuile(
    parent: tk.Widget, titre: str, valeur_texte: str, cible_texte: str, statut
) -> tk.Frame:
    """Une carte KPI colorée selon son statut (vert/orange/rouge/gris), avec une fine bande en
    dégradé de marque en haut et une bordure qui s'illumine légèrement au survol."""
    couleur_bordure_repos = COULEURS["gris_clair"]
    cadre = tk.Frame(
        parent,
        background=COULEURS["surface"],
        highlightthickness=1,
        highlightbackground=couleur_bordure_repos,
        highlightcolor=couleur_bordure_repos,
        borderwidth=0,
    )
    bande = tk.Canvas(cadre, height=4, highlightthickness=0, background=COULEURS["surface"])
    bande.pack(fill="x", side="top")
    bande._image_degradee = None  # référence conservée pour éviter le ramasse-miettes de Tk

    def _redessiner_bande(_evenement=None) -> None:
        largeur = bande.winfo_width()
        if largeur <= 1:
            return
        chemin = image_degradee(largeur, 4, COULEURS_DEGRADE_MARQUE)
        bande._image_degradee = tk.PhotoImage(file=str(chemin))
        bande.delete("all")
        bande.create_image(0, 0, anchor="nw", image=bande._image_degradee)

    bande.bind("<Configure>", _redessiner_bande)

    corps = tk.Frame(cadre, background=COULEURS["surface"])
    corps.pack(fill="both", expand=True, padx=12, pady=(8, 12))
    fond = {"background": COULEURS["surface"]}
    tk.Label(
        corps, text=titre, font=("", 9, "bold"), foreground=COULEURS["texte_secondaire"], **fond
    ).pack(anchor="w")
    tk.Label(
        corps, text=valeur_texte, font=("", 20, "bold"), foreground=COULEURS["texte"], **fond
    ).pack(anchor="w", pady=(2, 0))
    if cible_texte:
        tk.Label(
            corps, text=cible_texte, font=("", 9), foreground=COULEURS["texte_secondaire"], **fond
        ).pack(anchor="w")
    if statut is not None:
        tk.Label(
            corps,
            text=LIBELLES_STATUT.get(statut, "Non calculé"),
            font=("", 8, "bold"),
            background=COULEURS_STATUT_CLAIR.get(statut, COULEURS["gris_clair"]),
            foreground=COULEURS_STATUT.get(statut, COULEURS["gris"]),
            padx=8,
            pady=2,
        ).pack(anchor="w", pady=(8, 0))
    _lier_survol_tuile(cadre, couleur_bordure_repos, COULEUR_ACCENT_3)
    return cadre


def _serie(dates: list[date], valeurs_par_date: dict[date, float | None]) -> list[float]:
    """Valeurs alignées sur ``dates``, ``nan`` là où le KPI n'a pas encore été calculé (pour
    que le tracé laisse un blanc plutôt que d'échouer)."""
    return [v if (v := valeurs_par_date.get(jour)) is not None else float("nan") for jour in dates]


class VueTableauBord(Vue):
    """Filtres Site/Zone/Période/Date, navigation de période, et contenu propre à chaque
    rôle (planificateur, responsable, direction)."""

    titre = "Tableau de bord"
    sous_titre = "Vue d'ensemble adaptée au rôle"

    def construire(self) -> None:
        self.voit_les_alertes = a_le_droit(self.ctx, "lecture_alertes")
        self.voit_les_previsions = a_le_droit(self.ctx, "lecture_previsions")
        self.voit_le_plan = a_le_droit(self.ctx, "lecture_plan")
        self.periode_reference = date.today()

        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 6))
        self.site = ChampListe(barre, "Site", largeur=22)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(barre, "Zone", largeur=18)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_donnees)
        self.periode = ChampListe(barre, "Période", options=OPTIONS_PERIODICITE, largeur=12)
        self.periode.definir(PERIODICITE_PAR_DEFAUT.get(self.ctx.role, "semaine"))
        self.periode.pack(side="left", padx=(16, 0))
        self.periode.sur_changement(self._sur_changement_periode)

        nav = ttk.Frame(barre)
        nav.pack(side="left", padx=(24, 0), pady=(14, 0))
        Bouton(nav, "◀ Période précédente", lambda: self._changer_periode(-1)).pack(side="left")
        self.label_periode = ttk.Label(nav, text="", style="Gras.TLabel")
        self.label_periode.pack(side="left", padx=10)
        Bouton(nav, "Période suivante ▶", lambda: self._changer_periode(1)).pack(side="left")
        Bouton(nav, "Actualiser", self.actualiser_donnees).pack(side="left", padx=(16, 0))

        self.cadre_contenu = ttk.Frame(self.contenu)
        self.cadre_contenu.pack(fill="both", expand=True, pady=(8, 0))

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
            ttk.Label(self.cadre_contenu, text="Choisissez un site.", style="Aide.TLabel").pack(
                anchor="w"
            )
            return
        if self.ctx.role == "planificateur":
            self._construire_planificateur(site_id, zone_id, periodicite)
        elif self.ctx.role == "responsable":
            self._construire_responsable(site_id, zone_id, periodicite)
        elif self.ctx.role == "direction":
            self._construire_direction(site_id, zone_id, periodicite)

    def _construire_tuiles(self, codes: list[tuple[str, str]], valeurs: list[dict]) -> None:
        ligne = ttk.Frame(self.cadre_contenu)
        ligne.pack(fill="x", pady=(0, 12))
        for code, titre in codes:
            trouve = _trouver_kpi(valeurs, code)
            if trouve is None:
                tuile = _construire_tuile(ligne, titre, "—", "Pas encore calculé", None)
            else:
                tuile = _construire_tuile(
                    ligne,
                    titre,
                    _formater_valeur(trouve["valeur"], trouve["unite"]),
                    f"Cible {_formater_valeur(trouve['cible'], trouve['unite'])}",
                    trouve["statut"],
                )
            tuile.pack(side="left", fill="both", expand=True, padx=(0, 10))

    # =====================================================================
    # Planificateur (vue jour par défaut)
    # =====================================================================
    def _construire_planificateur(
        self, site_id: int, zone_id: int | None, periodicite: str
    ) -> None:
        valeurs = self._valeurs_kpi(site_id, zone_id, periodicite)
        self._construire_tuiles(TUILES_PLANIFICATEUR, valeurs)

        graphiques = ttk.Frame(self.cadre_contenu)
        graphiques.pack(fill="both", pady=(0, 12))
        graphique_besoin = GraphiqueIntegre(graphiques, largeur=7, hauteur=2.6)
        graphique_besoin.pack(side="left", fill="both", expand=True)
        graphique_eqp = GraphiqueIntegre(graphiques, largeur=3.2, hauteur=2.6)
        graphique_eqp.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self._dessiner_besoin_vs_capacite(graphique_besoin, site_id)
        self._dessiner_gauge_equipements(graphique_eqp, valeurs)

        ttk.Label(self.cadre_contenu, text="Écarts de la veille", style="Section.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        self.tableau_ecarts = TableauTriable(self.cadre_contenu, COLONNES_ECARTS, hauteur=6)
        self.tableau_ecarts.pack(fill="both", expand=True, pady=(0, 12))
        self._charger_ecarts_veille(self.tableau_ecarts, site_id, zone_id)

        if self.voit_les_alertes:
            ttk.Label(self.cadre_contenu, text="Alertes ouvertes", style="Section.TLabel").pack(
                anchor="w", pady=(0, 4)
            )
            self.tableau_alertes = TableauTriable(self.cadre_contenu, COLONNES_ALERTES, hauteur=6)
            self.tableau_alertes.pack(fill="both", expand=True)
            self.tableau_alertes.sur_double_clic(self._ouvrir_alerte)
            self._charger_alertes(self.tableau_alertes, site_id)

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
            x = np.arange(len(zones_communes))
            largeur = 0.35
            axe.bar(
                x - largeur / 2,
                [besoin_par_zone.get(z, 0.0) for z in zones_communes],
                largeur,
                label="Besoin prévu",
                color=COULEURS["primaire"],
            )
            axe.bar(
                x + largeur / 2,
                [capacite_par_zone.get(z, 0.0) for z in zones_communes],
                largeur,
                label="Capacité",
                color=COULEURS["vert"],
            )
            axe.set_xticks(x)
            axe.set_xticklabels(zones_communes, fontsize=7)
            axe.set_ylabel("Heures")
            axe.legend(fontsize=7)
            axe.set_title("Besoin prévu J+1 à J+7 vs capacité", fontsize=9, loc="left")

        graphique.dessiner(_dessiner)

    def _dessiner_gauge_equipements(self, graphique: GraphiqueIntegre, valeurs: list[dict]) -> None:
        trouve = _trouver_kpi(valeurs, "TAUX_DISPO_EQP")
        if trouve is None or trouve["valeur"] is None:
            graphique.afficher_message("Disponibilité non calculée.")
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

        graphique.dessiner(_dessiner)

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

    def _charger_alertes(self, tableau: TableauTriable, site_id: int) -> None:
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

    def _ouvrir_alerte(self, ligne: dict) -> None:
        self.application.naviguer("alertes", alerte_id=ligne["id"])

    # =====================================================================
    # Responsable (vue semaine par défaut)
    # =====================================================================
    def _construire_responsable(self, site_id: int, zone_id: int | None, periodicite: str) -> None:
        valeurs = self._valeurs_kpi(site_id, zone_id, periodicite)
        self._construire_tuiles(TUILES_RESPONSABLE, valeurs)

        graphiques = ttk.Frame(self.cadre_contenu)
        graphiques.pack(fill="both", expand=True)
        graphique_heures = GraphiqueIntegre(graphiques, largeur=7, hauteur=3)
        graphique_heures.pack(side="left", fill="both", expand=True)
        self._dessiner_reel_vs_previsions(graphique_heures, site_id)

        cadre_methodes = ttk.Frame(graphiques)
        cadre_methodes.pack(side="left", fill="y", padx=(12, 0))
        ttk.Label(cadre_methodes, text="MAPE et biais par méthode", style="Section.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        for code in ("MAPE_H", "BIAIS_H"):
            for v in [ligne for ligne in valeurs if ligne["kpi_code"] == code]:
                _construire_tuile(
                    cadre_methodes,
                    f"{v['kpi_libelle']} — {METHODES_COURTES.get(v['methode'], v['methode'])}",
                    _formater_valeur(v["valeur"], v["unite"]),
                    "",
                    v["statut"],
                ).pack(fill="x", pady=(0, 8))

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
            remplissage_degrade(axe, libelles, [v["reel"] for _, v in points], COULEURS["primaire"])
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
            axe.set_title("Réel vs RL vs RN", fontsize=9, loc="left")

        graphique.dessiner(_dessiner)

    # =====================================================================
    # Direction (vue mois par défaut)
    # =====================================================================
    def _construire_direction(self, site_id: int, zone_id: int | None, periodicite: str) -> None:
        valeurs = self._valeurs_kpi(site_id, zone_id, periodicite)
        self._construire_tuiles(TUILES_DIRECTION, valeurs)

        graphiques = ttk.Frame(self.cadre_contenu)
        graphiques.pack(fill="both", pady=(0, 12))
        graphique_tendances = GraphiqueIntegre(graphiques, largeur=7, hauteur=2.8)
        graphique_tendances.pack(side="left", fill="both", expand=True)
        graphique_victoire = GraphiqueIntegre(graphiques, largeur=3.2, hauteur=2.8)
        graphique_victoire.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self._dessiner_tendances_12_mois(graphique_tendances, site_id, zone_id)
        self._dessiner_taux_victoire(graphique_victoire, valeurs)

        self._construire_progression(site_id, zone_id)

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
                color=COULEURS["primaire"],
                label="Adéquation de l'effectif (%)",
            )
            remplissage_degrade(axe, dates, serie_adequation, COULEURS["primaire"])
            axe.plot(
                dates,
                _serie(dates, par_a_temps),
                marker="o",
                markersize=3,
                color=COULEURS["orange"],
                label="Commandes à temps (%)",
            )
            axe.set_ylabel("%")
            axe.legend(fontsize=7, loc="upper left")
            axe.tick_params(axis="x", rotation=30, labelsize=7)
            axe.set_title("Tendances sur 12 mois", fontsize=9, loc="left")

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
            couleurs = [COULEURS["primaire"], COULEURS["orange"]][: len(lignes)]
            axe.bar(methodes, valeurs_pct, color=couleurs)
            axe.set_ylabel("%")
            axe.set_ylim(0, 100)
            axe.set_title("Taux de victoire RL vs RN", fontsize=9, loc="left")
            for i, v in enumerate(valeurs_pct):
                axe.text(i, min(v + 2, 96), f"{formater_nombre(v, 0)} %", ha="center", fontsize=8)

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
        cadre = ttk.Frame(self.cadre_contenu, style="Carte.TFrame", padding=12)
        cadre.pack(fill="x")
        fond = {"background": COULEURS["surface"]}
        tk.Label(
            cadre,
            text="Progression de l'adéquation depuis la situation de référence",
            font=("", 9, "bold"),
            foreground=COULEURS["texte_secondaire"],
            **fond,
        ).pack(anchor="w")
        if len(utilisables) < 2:
            tk.Label(cadre, text="Historique mensuel insuffisant.", font=("", 12), **fond).pack(
                anchor="w"
            )
            return
        reference, actuelle = utilisables[0], utilisables[-1]
        delta = actuelle["valeur"] - reference["valeur"]
        signe = "+" if delta >= 0 else ""
        texte = (
            f"{signe}{formater_nombre(delta, 1)} points depuis "
            f"{formater_date(reference['date_debut_periode'])} (référence : "
            f"{formater_nombre(reference['valeur'], 1)} %, actuel : "
            f"{formater_nombre(actuelle['valeur'], 1)} %)"
        )
        tk.Label(
            cadre,
            text=texte,
            font=("", 14, "bold"),
            foreground=COULEURS["vert"] if delta >= 0 else COULEURS["rouge"],
            **fond,
        ).pack(anchor="w", pady=(2, 0))
