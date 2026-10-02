"""Bloc « Bottom line — l'impact de Workly » du tableau de bord (responsable et direction).

Mixin de :class:`~app.gui.vues.tableau_bord.VueTableauBord` : il réutilise ses briques de mise
en page (rangées, cartes, graphiques) et ses filtres (site, zone, période).
"""

from __future__ import annotations

from tkinter import ttk

from matplotlib.dates import DateFormatter

from app.gui.style import (
    COULEUR_ACCENT_1,
    COULEUR_ACCENT_4,
    COULEUR_ACCENT_5,
    COULEURS,
    PUCE_STATUT,
)
from app.gui.widgets.carte import Carte
from app.gui.widgets.graphique import GraphiqueIntegre, legende_en_haut, remplissage_degrade
from app.gui.widgets.kpi import CarteHero, carte_stat
from app.gui.widgets.traces import anneau, barres_groupees, jauge
from app.services import bottom_line
from app.services.droits import a_le_droit
from app.utils.dates import bornes_periode
from app.utils.format_fr import (
    formater_montant,
    formater_nombre,
    formater_pourcentage,
)

ABSENT = "—"


def _heures(valeur: float | None) -> str:
    return f"{formater_nombre(valeur, 0)} h" if valeur is not None else ABSENT


def _pourcentage(valeur: float | None, decimales: int = 0) -> str:
    return formater_pourcentage(valeur, decimales) if valeur is not None else ABSENT


def _duree_h(valeur: float | None) -> str:
    return f"{formater_nombre(valeur, 1)} h" if valeur is not None else ABSENT


def _signe(texte: str, valeur: float) -> str:
    return f"+{texte}" if valeur > 0 else texte


def _reduction(sans: float, avec: float) -> float | None:
    """Baisse relative en % de ``sans`` à ``avec`` (positive = Workly réduit), ``None`` si
    ``sans`` est nul."""
    return (sans - avec) / sans * 100 if sans else None


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
        ttk.Label(entete, text="Bottom line — l'impact de Workly", style="Gras.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            entete,
            text=(
                "Ce que Workly change par rapport à un planning reconduit chaque semaine, sur "
                "la période choisie."
            ),
            style="Aide.TLabel",
        ).pack(anchor="w")

        devise = resultat["devise"]
        self._tuiles_bottom_line(resultat, devise)

        ligne = self._rangee([1, 1, 1])
        self._carte_delais(ligne, 0, 3, resultat["simulation"])
        self._carte_service(ligne, 1, 3, resultat["simulation"], devise)
        self._carte_indices(ligne, 2, 3, resultat["simulation"])

        ligne = self._rangee([3, 2])
        self._carte_gain_cumule(ligne, 0, 2, resultat["simulation"], devise)
        self._carte_gain_par_zone(ligne, 1, 2, resultat["simulation"], devise)

        ligne = self._rangee([1, 1, 1])
        self._carte_repartition(ligne, 0, 3, resultat, devise)
        self._carte_lignes(
            ligne,
            1,
            3,
            "Système d'alertes",
            "Réactivité, anticipation et pénuries",
            self._lignes_alertes(resultat["alertes"], devise),
        )
        self._carte_lignes(
            ligne,
            2,
            3,
            "Retour sur investissement",
            "Gain annualisé et automatisation",
            self._lignes_roi(resultat, devise),
        )

    # --- Tuiles ---------------------------------------------------------
    def _tuiles_bottom_line(self, resultat: dict, devise: str) -> None:
        simulation = resultat["simulation"]
        gains, sans, avec = simulation["gains"], simulation["sans"], simulation["avec"]
        comparable = simulation["nb_jours"] > 0
        ligne = self._rangee([1, 1, 1, 1])

        def valeur(texte: str) -> str:
            return texte if comparable else ABSENT

        gain_net = resultat["gain_net"]
        self._placer(
            ligne,
            CarteHero(
                ligne,
                "Gain net",
                _signe(formater_montant(gain_net, devise, 0), gain_net),
                f"Sur {simulation['nb_jours']} jours de zone",
                "",
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
                f"{formater_nombre(sans['commandes_en_retard'], 0)} → "
                f"{formater_nombre(avec['commandes_en_retard'], 0)} commandes",
            ),
            3,
            4,
        )

    # --- Cartes à graphique ------------------------------------------------------
    def _carte_graphique_et_texte(
        self,
        ligne: ttk.Frame,
        colonne: int,
        total: int,
        titre: str,
        sous_titre: str,
        largeur: float = 3.2,
        hauteur: float = 2.3,
    ) -> tuple[GraphiqueIntegre, Carte]:
        carte = Carte(ligne, titre, sous_titre)
        self._placer(ligne, carte, colonne, total)
        graphique = GraphiqueIntegre(carte.zone, largeur=largeur, hauteur=hauteur)
        graphique.pack(fill="both", expand=True)
        return graphique, carte

    @staticmethod
    def _texte_sous_graphique(carte: Carte, principal: str, secondaire: str) -> None:
        ttk.Label(carte.zone, text=principal, font=("", 13, "bold"), justify="center").pack(
            pady=(8, 0)
        )
        ttk.Label(carte.zone, text=secondaire, style="Aide.TLabel", justify="center").pack()

    def _carte_delais(self, ligne: ttk.Frame, colonne: int, total: int, simulation: dict) -> None:
        graphique, carte = self._carte_graphique_et_texte(
            ligne, colonne, total, "Délais", "Commandes livrées en retard"
        )
        baisse = _reduction(
            simulation["sans"]["commandes_en_retard"], simulation["avec"]["commandes_en_retard"]
        )
        if not simulation["nb_jours"] or baisse is None:
            graphique.afficher_message("Aucun retard à comparer sur la période.")
            return
        part = min(max(baisse, 0.0), 100.0)
        couleur = COULEURS["vert"] if baisse >= 0 else COULEURS["rouge"]
        graphique.dessiner(
            lambda axe: anneau(
                axe,
                [part, 100 - part],
                [couleur, COULEURS["surface_2"]],
                centre=_pourcentage(abs(baisse)),
            )
        )
        self._texte_sous_graphique(
            carte,
            f"{'−' if baisse >= 0 else '+'}{_pourcentage(abs(baisse))} de retards",
            "vs planning reconduit",
        )

    def _carte_service(
        self, ligne: ttk.Frame, colonne: int, total: int, simulation: dict, devise: str
    ) -> None:
        graphique, carte = self._carte_graphique_et_texte(
            ligne, colonne, total, "Service", "Qualité et pénalités"
        )
        sans, avec = simulation["sans"], simulation["avec"]
        if not simulation["nb_jours"] or avec["taux_service"] is None:
            graphique.afficher_message("Aucune commande à comparer sur la période.")
            return
        graphique.dessiner(
            lambda axe: jauge(
                axe,
                avec["taux_service"] / 100,
                COULEURS["orange"],
                centre=_pourcentage(avec["taux_service"], 1),
                sous_centre="taux de service",
            )
        )
        self._texte_sous_graphique(
            carte,
            f"{_pourcentage(sans['taux_service'], 1)} → {_pourcentage(avec['taux_service'], 1)}",
            f"{formater_montant(simulation['gains']['penalites'], devise, 0)} "
            "de pénalités évitées",
        )

    def _carte_indices(self, ligne: ttk.Frame, colonne: int, total: int, simulation: dict) -> None:
        graphique, _carte = self._carte_graphique_et_texte(
            ligne,
            colonne,
            total,
            "Coûts et gaspillage",
            "Indice : sans Workly = 100",
            largeur=3.6,
            hauteur=2.9,
        )
        sans, avec = simulation["sans"], simulation["avec"]
        mesures = [
            ("Coût", "cout_total"),
            ("Gaspillage", "heures_mal_allouees"),
            ("Heures sup.", "heures_sup"),
            ("Pénalités", "penalites"),
        ]
        retenues = [(nom, cle) for nom, cle in mesures if simulation["nb_jours"] and sans[cle] > 0]
        if not retenues:
            graphique.afficher_message("Aucune donnée à comparer sur la période.")
            return
        categories = [nom for nom, _cle in retenues]
        indices = [round(avec[cle] / sans[cle] * 100) for _nom, cle in retenues]

        def _dessiner(axe):
            barres_groupees(
                axe,
                categories,
                [
                    ([100] * len(categories), COULEURS["gris"], "Sans Workly"),
                    (indices, COULEURS["primaire"], "Avec Workly"),
                ],
            )
            axe.set_yticks([])
            axe.spines["left"].set_visible(False)
            axe.set_ylim(0, max(max(indices), 100) * 1.22)
            legende_en_haut(axe)
            decalage = 0.74 / 4
            for rang, indice in enumerate(indices):
                axe.text(
                    rang - decalage,
                    103,
                    "100",
                    ha="center",
                    fontsize=8,
                    color=COULEURS["texte_secondaire"],
                )
                axe.text(
                    rang + decalage,
                    indice + 3,
                    str(indice),
                    ha="center",
                    fontsize=8,
                    fontweight="bold",
                    color=COULEURS["texte"],
                )
            axe.tick_params(axis="x", labelsize=7)

        graphique.dessiner(_dessiner)

    def _carte_gain_cumule(
        self, ligne: ttk.Frame, colonne: int, total: int, simulation: dict, devise: str
    ) -> None:
        graphique, _carte = self._carte_graphique_et_texte(
            ligne,
            colonne,
            total,
            "Gain cumulé",
            f"Économies jour après jour, en {devise}",
            largeur=5.4,
            hauteur=2.6,
        )
        serie = simulation["serie_gains"]
        if len(serie) < 2:
            graphique.afficher_message("Pas assez de jours pour tracer une évolution.")
            return
        jours = [jour for jour, _gain in serie]
        cumul, somme = [], 0.0
        for _jour, gain in serie:
            somme += gain
            cumul.append(somme)

        def _dessiner(axe):
            axe.plot(jours, cumul, linewidth=2.2, color=COULEURS["primaire"])
            remplissage_degrade(axe, jours, cumul, COULEURS["primaire"])
            axe.axhline(0, color=COULEURS["bordure"], linewidth=1)
            axe.set_ylabel(devise)
            axe.xaxis.set_major_formatter(DateFormatter("%d/%m"))
            axe.tick_params(axis="x", labelsize=7)

        graphique.dessiner(_dessiner)

    def _carte_gain_par_zone(
        self, ligne: ttk.Frame, colonne: int, total: int, simulation: dict, devise: str
    ) -> None:
        graphique, _carte = self._carte_graphique_et_texte(
            ligne,
            colonne,
            total,
            "Gain par zone",
            f"Économies sur la période, en {devise}",
            largeur=3.6,
            hauteur=2.6,
        )
        zones = simulation["gains_par_zone"]
        if not zones:
            graphique.afficher_message("Aucune zone à comparer sur la période.")
            return
        noms = [nom for nom, _gain in zones]
        gains = [gain for _nom, gain in zones]

        def _dessiner(axe):
            barres_groupees(axe, noms, [([max(g, 0.0) for g in gains], COULEURS["primaire"], None)])
            axe.set_yticks([])
            axe.spines["left"].set_visible(False)
            sommet = max(max(gains), 1.0)
            axe.set_ylim(0, sommet * 1.2)
            for rang, gain in enumerate(gains):
                axe.text(
                    rang,
                    max(gain, 0.0) + sommet * 0.03,
                    formater_nombre(gain, 0),
                    ha="center",
                    fontsize=8,
                    fontweight="bold",
                    color=COULEURS["texte"],
                )
            axe.tick_params(axis="x", labelsize=7)

        graphique.dessiner(_dessiner)

    def _carte_repartition(
        self, ligne: ttk.Frame, colonne: int, total: int, resultat: dict, devise: str
    ) -> None:
        graphique, carte = self._carte_graphique_et_texte(
            ligne, colonne, total, "D'où vient le gain", "Répartition des économies", 2.8, 2.1
        )
        couleurs = [
            COULEUR_ACCENT_1,
            COULEURS["primaire"],
            COULEUR_ACCENT_4,
            COULEUR_ACCENT_5,
            COULEURS["vert"],
        ]
        parts = [
            (nom, valeur, couleur)
            for (nom, valeur), couleur in zip(
                resultat["repartition_gain"].items(), couleurs, strict=True
            )
            if valeur > 0
        ]
        if not parts:
            graphique.afficher_message("Aucun gain à répartir sur la période.")
            return
        graphique.dessiner(
            lambda axe: anneau(
                axe,
                [valeur for _n, valeur, _c in parts],
                [couleur for _n, _v, couleur in parts],
                centre=formater_nombre(sum(v for _n, v, _c in parts), 0),
                sous_centre=devise,
            )
        )
        legende = ttk.Frame(carte.zone)
        legende.pack(fill="x", pady=(8, 0))
        somme = sum(v for _n, v, _c in parts)
        for nom, valeur, couleur in parts:
            rang = ttk.Frame(legende)
            rang.pack(fill="x", pady=1)
            ttk.Label(rang, text=PUCE_STATUT, foreground=couleur).pack(side="left")
            ttk.Label(rang, text=nom).pack(side="left", padx=(6, 0))
            ttk.Label(rang, text=_pourcentage(valeur / somme * 100), style="Gras.TLabel").pack(
                side="right"
            )

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
    def _lignes_alertes(a: dict, devise: str) -> list[tuple[str, str]]:
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
            ("Pénuries d'équipement traitées à l'avance", str(a["penuries_traitees"])),
            ("Coût de pénurie évité", formater_montant(a["valeur_penuries"], devise, 0)),
        ]

    @staticmethod
    def _lignes_roi(resultat: dict, devise: str) -> list[tuple[str, str]]:
        roi, auto = resultat["roi"], resultat["automatisation"]
        return [
            ("Gain annualisé", formater_montant(roi["gain_annuel"], devise, 0)),
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
