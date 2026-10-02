"""Bloc « Bottom line — apports et limites » du tableau de bord (responsable et direction).

Mixin de :class:`~app.gui.vues.tableau_bord.VueTableauBord` : il réutilise ses briques de mise
en page (rangées, cartes, graphiques) et ses filtres (site, zone, période).
"""

from __future__ import annotations

from tkinter import ttk

from app.gui.style import COULEURS
from app.gui.widgets.carte import Carte
from app.gui.widgets.graphique import GraphiqueIntegre, legende_en_haut
from app.gui.widgets.kpi import CarteHero, carte_stat
from app.gui.widgets.traces import barres_groupees
from app.services import bottom_line
from app.services.droits import a_le_droit
from app.utils.dates import bornes_periode
from app.utils.format_fr import formater_montant, formater_nombre, formater_pourcentage

ABSENT = "—"


def _heures(valeur: float | None) -> str:
    return f"{formater_nombre(valeur, 0)} h" if valeur is not None else ABSENT


def _pourcentage(valeur: float | None, decimales: int = 0) -> str:
    return formater_pourcentage(valeur, decimales) if valeur is not None else ABSENT


def _duree_h(valeur: float | None) -> str:
    return f"{formater_nombre(valeur, 1)} h" if valeur is not None else ABSENT


def _signe(texte: str, valeur: float) -> str:
    return f"+{texte}" if valeur > 0 else texte


class BlocBottomLine:
    """Construit le bloc à la suite du contenu propre au rôle."""

    def _construire_bottom_line(self, site_id: int, zone_id: int | None, periodicite: str) -> None:
        if not a_le_droit(self.ctx, "lecture_bottom_line"):
            return
        debut, fin = bornes_periode(self.periode_reference, periodicite)
        resultat = self.executer(
            lambda: bottom_line.calculer_bottom_line(self.ctx, site_id, zone_id, debut, fin)
        )
        if resultat is None:
            return
        self.dernier_bottom_line = resultat

        entete = ttk.Frame(self.cadre_contenu, style="Page.TFrame")
        entete.pack(fill="x", pady=(8, 10))
        ttk.Label(entete, text="Bottom line — apports et limites", style="Gras.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            entete,
            text=(
                "Ce que Workly change par rapport à un planning reconduit chaque semaine, sur "
                "la période choisie. Chiffres simulés : voir les limites en bas du bloc."
            ),
            style="Aide.TLabel",
        ).pack(anchor="w")

        devise = resultat["devise"]
        simulation = resultat["simulation"]
        self._tuiles_bottom_line(resultat, devise)
        self._graphiques_bottom_line(simulation, devise)

        ligne = self._rangee([1, 1, 1])
        self._carte_lignes(
            ligne,
            0,
            3,
            "Système d'alertes",
            "Réactivité et anticipation",
            self._lignes_alertes(resultat["alertes"]),
        )
        self._carte_lignes(
            ligne,
            1,
            3,
            "Équipements et service",
            "Pénuries et qualité de service",
            self._lignes_equipements(resultat, devise),
        )
        self._carte_lignes(
            ligne,
            2,
            3,
            "Retour sur investissement",
            "Gain annualisé et automatisation",
            self._lignes_roi(resultat, devise),
        )
        self._carte_limites(resultat["limites"])

    # --- Tuiles ---------------------------------------------------------
    def _tuiles_bottom_line(self, resultat: dict, devise: str) -> None:
        simulation = resultat["simulation"]
        gains, sans, avec = simulation["gains"], simulation["sans"], simulation["avec"]
        comparable = simulation["nb_jours"] > 0
        ligne = self._rangee([1, 1, 1, 1])

        def valeur(texte: str) -> str:
            return texte if comparable else ABSENT

        gain_net = gains["cout_total"] + resultat["alertes"]["valeur_penuries"]
        gain_net += resultat["automatisation"]["valeur_heures_evitees"]
        self._placer(
            ligne,
            CarteHero(
                ligne,
                "Gain net estimé",
                _signe(formater_montant(gain_net, devise, 0), gain_net),
                f"Sur {simulation['nb_jours']} jours de zone comparés",
                "Estimation",
                "rose",
            ),
            0,
            4,
        )
        self._placer(
            ligne,
            CarteHero(
                ligne,
                "Heures de travail mal allouées évitées",
                valeur(_heures(gains["heures_mal_allouees"])),
                f"{_heures(sans['heures_mal_allouees'])} → {_heures(avec['heures_mal_allouees'])}",
                "",
                "cyan",
            ),
            1,
            4,
        )
        self._placer(
            ligne,
            carte_stat(
                ligne,
                "Ressources humaines : postes-jours mal alloués évités",
                valeur(formater_nombre(gains["postes_mal_alloues"], 0)),
                f"{formater_nombre(sans['postes_mal_alloues'], 0)} → "
                f"{formater_nombre(avec['postes_mal_alloues'], 0)} postes-jours",
            ),
            2,
            4,
        )
        self._placer(
            ligne,
            carte_stat(
                ligne,
                "Délais : commandes en retard évitées",
                valeur(formater_nombre(gains["commandes_en_retard"], 0)),
                f"Service estimé {_pourcentage(sans['taux_service'], 1)} → "
                f"{_pourcentage(avec['taux_service'], 1)}",
            ),
            3,
            4,
        )

    # --- Graphiques avant / après ------------------------------------------
    def _graphiques_bottom_line(self, simulation: dict, devise: str) -> None:
        ligne = self._rangee([1, 1])
        graphique_heures = self._carte_graphique(
            ligne,
            0,
            2,
            "Heures : sans et avec Workly",
            "Déficit couvert en heures sup. et heures payées inutilisées",
            4.4,
            2.5,
        )
        graphique_couts = self._carte_graphique(
            ligne,
            1,
            2,
            "Coûts de mauvaise allocation",
            f"Sans et avec Workly, en {devise}",
            4.4,
            2.5,
        )
        if not simulation["nb_jours"]:
            for graphique in (graphique_heures, graphique_couts):
                graphique.afficher_message(
                    "Aucun jour comparable : il faut des prévisions et l'historique réel."
                )
            return
        sans, avec = simulation["sans"], simulation["avec"]
        self._barres_avant_apres(
            graphique_heures,
            ["Heures supplémentaires", "Heures inactives"],
            [sans["heures_sup"], sans["heures_inactives"]],
            [avec["heures_sup"], avec["heures_inactives"]],
            "Heures",
        )
        self._barres_avant_apres(
            graphique_couts,
            ["Heures sup.", "Heures inutilisées", "Pénalités de retard"],
            [sans["cout_deficit"], sans["cout_inactif"], sans["penalites"]],
            [avec["cout_deficit"], avec["cout_inactif"], avec["penalites"]],
            devise,
        )

    @staticmethod
    def _barres_avant_apres(
        graphique: GraphiqueIntegre,
        categories: list[str],
        sans: list[float],
        avec: list[float],
        unite: str,
    ) -> None:
        def _dessiner(axe):
            barres_groupees(
                axe,
                categories,
                [
                    (sans, COULEURS["gris"], "Sans Workly"),
                    (avec, COULEURS["primaire"], "Avec Workly"),
                ],
            )
            axe.set_ylabel(unite)
            legende_en_haut(axe)

        graphique.dessiner(_dessiner)

    # --- Cartes de lignes « libellé / valeur » -------------------------------
    def _carte_lignes(
        self,
        ligne: ttk.Frame,
        colonne: int,
        total: int,
        titre: str,
        sous_titre: str,
        lignes: list[tuple[str, str]],
    ) -> None:
        carte = Carte(ligne, titre, sous_titre)
        self._placer(ligne, carte, colonne, total)
        carte.zone.columnconfigure(0, weight=1)
        libelles = []
        valeurs = []
        for rang, (libelle, valeur) in enumerate(lignes):
            etiquette = ttk.Label(carte.zone, text=libelle, style="Aide.TLabel", justify="left")
            etiquette.grid(row=rang, column=0, sticky="w", pady=3)
            resultat = ttk.Label(carte.zone, text=valeur, style="Gras.TLabel", justify="right")
            resultat.grid(row=rang, column=1, sticky="e", padx=(10, 0), pady=3)
            libelles.append(etiquette)
            valeurs.append(resultat)

        def _ajuster(evenement) -> None:
            """Les libellés passent à la ligne dans la place laissée par la plus large valeur."""
            largeur_valeur = max((v.winfo_reqwidth() for v in valeurs), default=0)
            for etiquette in libelles:
                etiquette.configure(wraplength=max(evenement.width - largeur_valeur - 24, 90))

        carte.zone.bind("<Configure>", _ajuster)

    @staticmethod
    def _lignes_alertes(a: dict) -> list[tuple[str, str]]:
        if not a["nb"]:
            return [("Alertes émises", "Aucune sur la période")]
        anticipation = (
            f"{_pourcentage(a['taux_anticipation'])} (en moyenne "
            f"{formater_nombre(a['avance_moyenne_j'], 1)} j avant)"
            if a["avance_moyenne_j"] is not None
            else _pourcentage(a["taux_anticipation"])
        )
        return [
            ("Alertes émises", f"{a['nb']} dont {a['nb_critiques']} critiques"),
            (
                "Alertes traitées",
                f"{_pourcentage(a['taux_traitement'])} ({a['nb_traitees']}/{a['nb']})",
            ),
            ("Délai de prise en charge", _duree_h(a["delai_prise_en_charge_h"])),
            ("Délai de résolution", _duree_h(a["delai_resolution_h"])),
            ("Alertes émises avant la date concernée", anticipation),
        ]

    @staticmethod
    def _lignes_equipements(resultat: dict, devise: str) -> list[tuple[str, str]]:
        a, s = resultat["alertes"], resultat["simulation"]
        return [
            ("Pénuries d'équipement traitées à l'avance", str(a["penuries_traitees"])),
            ("Coût de pénurie évité", formater_montant(a["valeur_penuries"], devise, 0)),
            ("Taux de service sans Workly (estimé)", _pourcentage(s["sans"]["taux_service"], 1)),
            ("Taux de service avec Workly (estimé)", _pourcentage(s["avec"]["taux_service"], 1)),
            (
                "Pénalités de retard évitées",
                formater_montant(s["gains"]["penalites"], devise, 0),
            ),
        ]

    @staticmethod
    def _lignes_roi(resultat: dict, devise: str) -> list[tuple[str, str]]:
        roi, auto = resultat["roi"], resultat["automatisation"]
        lignes = [
            ("Gain annualisé estimé", formater_montant(roi["gain_annuel"], devise, 0)),
            (
                "Coût de mise en place",
                (
                    formater_montant(roi["cout_mise_en_place"], devise, 0)
                    if roi["cout_mise_en_place"]
                    else "Non renseigné"
                ),
            ),
            (
                "Retour sur investissement",
                (
                    _signe(_pourcentage(roi["roi_pct"]), roi["roi_pct"])
                    if roi["roi_pct"] is not None
                    else ABSENT
                ),
            ),
            (
                "Délai de rentabilisation",
                (
                    f"{formater_nombre(roi['retour_mois'], 1)} mois"
                    if roi["retour_mois"] is not None
                    else ABSENT
                ),
            ),
            (
                "Tâches automatiques exécutées",
                (
                    f"{auto['nb']} ({_pourcentage(auto['taux_reussite'])} de réussite)"
                    if auto["nb"]
                    else "Aucune sur la période"
                ),
            ),
            (
                "Temps manuel évité",
                f"{_heures(auto['heures_evitees'])} "
                f"(≈ {formater_montant(auto['valeur_heures_evitees'], devise, 0)})",
            ),
        ]
        return lignes

    # --- Limites ----------------------------------------------------------------
    def _carte_limites(self, limites: list[str]) -> None:
        carte = Carte(
            self.cadre_contenu, "Limites et hypothèses", "À lire avant de citer les chiffres"
        )
        carte.pack(fill="x")
        etiquettes = [
            ttk.Label(carte.zone, text=f"•  {texte}", justify="left") for texte in limites
        ]
        for etiquette in etiquettes:
            etiquette.pack(anchor="w", fill="x", pady=2)

        def _largeur(evenement) -> None:
            for etiquette in etiquettes:
                etiquette.configure(wraplength=max(evenement.width - 8, 200))

        carte.zone.bind("<Configure>", _largeur)
