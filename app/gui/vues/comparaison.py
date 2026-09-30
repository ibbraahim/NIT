"""Écran 6 — Comparaison réel / prévu (UC20, UC21) : responsable."""

from __future__ import annotations

from datetime import date, timedelta
from tkinter import ttk

import matplotlib.dates as mdates

from app.gui.style import COULEURS, PUCE_STATUT
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampDate, ChampListe
from app.gui.widgets.dialogues import choisir_fichier_a_enregistrer, informer
from app.gui.widgets.graphique import GraphiqueIntegre, legende_en_haut, remplissage_degrade
from app.gui.widgets.taches_fond import executer_en_fond
from app.services import admin, alertes, comparaison, kpi, recommandations
from app.services.droits import a_le_droit
from app.utils.fichiers_excel import ecrire_classeur
from app.utils.format_fr import formater_date, formater_nombre

#: (libellé, fonction de calcul, sens de la meilleure valeur) pour les 5 premières métriques ;
#: le taux de victoire (comparatif par nature) est calculé à part.
_FORMULES_METRIQUES = (
    ("MAE (heures)", "calculer_mae", "bas"),
    ("RMSE (heures)", "calculer_rmse", "bas"),
    ("MAPE (%)", "calculer_mape", "bas"),
    ("Biais (%)", "calculer_biais", "zero"),
    ("Couverture IC (%)", "calculer_couverture_ic", "80"),
)


def _calculer_metriques(
    rl: list[dict], rn: list[dict]
) -> list[tuple[str, float | None, float | None, str]]:
    lignes = [
        (libelle, getattr(kpi, nom_fonction)(rl), getattr(kpi, nom_fonction)(rn), mode)
        for libelle, nom_fonction, mode in _FORMULES_METRIQUES
    ]
    lignes.append(
        (
            "Taux de victoire (%)",
            kpi.calculer_taux_victoire(rl, rn),
            kpi.calculer_taux_victoire(rn, rl),
            "haut",
        )
    )
    return lignes


def _meilleure_colonne(valeur_rl: float | None, valeur_rn: float | None, mode: str) -> str | None:
    """« rl », « rn » ou ``None`` (égalité ou valeur manquante) : quelle colonne est en gras."""
    if valeur_rl is None or valeur_rn is None or valeur_rl == valeur_rn:
        return None
    if mode == "bas":
        return "rl" if valeur_rl < valeur_rn else "rn"
    if mode == "haut":
        return "rl" if valeur_rl > valeur_rn else "rn"
    if mode == "zero":
        return "rl" if abs(valeur_rl) < abs(valeur_rn) else "rn"
    if mode == "80":
        return "rl" if abs(valeur_rl - 80) < abs(valeur_rn - 80) else "rn"
    return None


def _serie(dates: list[date], valeurs_par_date: dict[date, float]) -> list[float]:
    return [valeurs_par_date.get(jour, float("nan")) for jour in dates]


class VueComparaison(Vue):
    """Filtres Site/Zone/Période, rapprochement (UC20), graphique Réel/RL/RN, tableau des
    métriques par méthode (meilleure valeur en gras) et bandeau de dérive (UC21)."""

    titre = "Comparaison réel / prévu"
    sous_titre = "Rapprochement des prévisions RL et RN au réalisé"

    def construire(self) -> None:
        self.peut_comparer = a_le_droit(self.ctx, "UC20")

        self.bandeau_derive = ttk.Frame(self.contenu, style="Derive.TFrame", padding=(16, 10))
        self.label_derive = ttk.Label(
            self.bandeau_derive, text="", style="Derive.TLabel", wraplength=900
        )
        self.label_derive.pack(anchor="w")
        self.bandeau_derive.pack(fill="x", pady=(0, self.ECART))
        self.bandeau_derive.pack_forget()

        carte_filtres = self.carte(marge=14)
        self._barre_filtres = carte_filtres
        barre = carte_filtres.zone
        self.site = ChampListe(barre, "Site", largeur=22)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(barre, "Zone", largeur=18)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_donnees)
        aujourdhui = date.today()
        self.date_debut = ChampDate(barre, "Date de début")
        self.date_debut.definir(aujourdhui - timedelta(days=27))
        self.date_debut.pack(side="left", padx=(16, 0))
        self.date_debut.sur_changement(self.actualiser_donnees)
        self.date_fin = ChampDate(barre, "Date de fin")
        self.date_fin.definir(aujourdhui - timedelta(days=1))
        self.date_fin.pack(side="left", padx=(16, 0))
        self.date_fin.sur_changement(self.actualiser_donnees)

        carte_graphique = self.carte("Réel contre prévisions", "Heures par jour sur la période")
        boutons = carte_graphique.actions
        self.b_comparer = Bouton(boutons, "Lancer la comparaison", self.comparer, primaire=True)
        self.b_comparer.pack(side="left")
        if not self.peut_comparer:
            self.b_comparer.pack_forget()
        self.b_exporter = Bouton(boutons, "Exporter en Excel", self.exporter)
        self.b_exporter.pack(side="left", padx=(8, 0))
        self.graphique = GraphiqueIntegre(carte_graphique.zone, largeur=9, hauteur=3)
        self.graphique.pack(fill="both", expand=True)

        carte_metriques = self.carte(
            "Métriques par méthode",
            "Meilleure valeur en gras et en vert",
            dernier=True,
        )
        self.cadre_metriques = ttk.Frame(carte_metriques.zone)
        self.cadre_metriques.pack(fill="x")

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
        self._actualiser_bandeau_derive(site_id)
        self.actualiser_donnees()

    def _actualiser_bandeau_derive(self, site_id: int | None) -> None:
        """UC21 : avertit qu'une dérive de modèle a été détectée sur ce site."""
        ouvertes = (
            self.executer(
                lambda: alertes.lister_alertes_ouvertes(self.ctx, site_id, "derive_modele")
            )
            or []
            if site_id is not None
            else []
        )
        if not ouvertes:
            self.bandeau_derive.pack_forget()
            return
        texte = " · ".join(f"{PUCE_STATUT} {a['message']}" for a in ouvertes)
        texte += f" — {recommandations.suggestion_alerte('derive_modele')}"
        self.label_derive.configure(text=texte)
        self.bandeau_derive.pack(fill="x", pady=(0, self.ECART), before=self._barre_filtres)

    def _periode(self) -> tuple[date, date] | None:
        try:
            return self.date_debut.valeur(), self.date_fin.valeur()
        except ValueError:
            return None

    def actualiser_donnees(self) -> None:
        site_id, zone_id = self.site.valeur(), self.zone.valeur()
        periode = self._periode()
        self.b_comparer.activer(
            self.peut_comparer and site_id is not None, "Choisissez d'abord un site."
        )
        if site_id is None or periode is None:
            self.graphique.afficher_message("Choisissez un site.")
            self._effacer_metriques()
            self.b_exporter.activer(False, "Choisissez d'abord un site.")
            return
        debut, fin = periode
        self._lignes_rl = (
            self.executer(
                lambda: comparaison.lister_comparaisons(
                    self.ctx, site_id, zone_id, debut, fin, "regression_lineaire"
                )
            )
            or []
        )
        self._lignes_rn = (
            self.executer(
                lambda: comparaison.lister_comparaisons(
                    self.ctx, site_id, zone_id, debut, fin, "reseau_neurones"
                )
            )
            or []
        )
        self._dessiner_graphique(self._lignes_rl, self._lignes_rn)
        self._construire_metriques(self._lignes_rl, self._lignes_rn)
        self.b_exporter.activer(
            bool(self._lignes_rl or self._lignes_rn), "Lancez d'abord une comparaison."
        )

    def _dessiner_graphique(self, lignes_rl: list[dict], lignes_rn: list[dict]) -> None:
        if not lignes_rl and not lignes_rn:
            self.graphique.afficher_message(
                "Aucun rapprochement pour cette période. Utilisez « Lancer la comparaison » "
                "une fois l'historique de la période connu."
            )
            return
        dates = sorted({r["date_jour"] for r in lignes_rl + lignes_rn})
        reel: dict[date, float] = {}
        rl_par_date: dict[date, float] = {}
        rn_par_date: dict[date, float] = {}
        zones_vues: dict[date, set[int]] = {}
        for lignes, cible in ((lignes_rl, rl_par_date), (lignes_rn, rn_par_date)):
            for r in lignes:
                cible[r["date_jour"]] = cible.get(r["date_jour"], 0.0) + (
                    r["heures_prevues"] or 0.0
                )
                vues = zones_vues.setdefault(r["date_jour"], set())
                if r["zone_id"] not in vues and r["heures_reelles"] is not None:
                    vues.add(r["zone_id"])
                    reel[r["date_jour"]] = reel.get(r["date_jour"], 0.0) + r["heures_reelles"]

        def _dessiner(axe):
            serie_reel = _serie(dates, reel)
            axe.plot(
                dates,
                serie_reel,
                marker="o",
                markersize=3,
                color=COULEURS["primaire"],
                label="Réalisé",
            )
            remplissage_degrade(axe, dates, serie_reel, COULEURS["primaire"])
            axe.plot(
                dates,
                _serie(dates, rl_par_date),
                marker="o",
                markersize=3,
                color=COULEURS["orange"],
                label="Prévu (RL)",
            )
            axe.plot(
                dates,
                _serie(dates, rn_par_date),
                marker="o",
                markersize=3,
                color=COULEURS["vert"],
                label="Prévu (RN)",
            )
            axe.set_ylabel("Heures")
            legende_en_haut(axe)
            axe.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
            axe.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
            axe.tick_params(axis="x", rotation=30, labelsize=8)

        self.graphique.dessiner(_dessiner)

    def _effacer_metriques(self) -> None:
        for enfant in self.cadre_metriques.winfo_children():
            enfant.destroy()
        ttk.Label(self.cadre_metriques, text="Choisissez un site.", style="Aide.TLabel").grid(
            row=0, column=0, sticky="w"
        )

    def _construire_metriques(self, lignes_rl: list[dict], lignes_rn: list[dict]) -> None:
        for enfant in self.cadre_metriques.winfo_children():
            enfant.destroy()
        for colonne, texte in enumerate(
            ("Métrique", "Régression linéaire (RL)", "Réseau de neurones (RN)")
        ):
            ttk.Label(self.cadre_metriques, text=texte, style="KpiTitre.TLabel").grid(
                row=0, column=colonne, sticky="w", padx=(0, 40), pady=(0, 8)
            )
        for ligne, (libelle_m, valeur_rl, valeur_rn, mode) in enumerate(
            _calculer_metriques(lignes_rl, lignes_rn), start=1
        ):
            gagnant = _meilleure_colonne(valeur_rl, valeur_rn, mode)
            ttk.Label(self.cadre_metriques, text=libelle_m).grid(
                row=ligne, column=0, sticky="w", padx=(0, 40), pady=3
            )
            for colonne, (cle, valeur) in enumerate(
                (("rl", valeur_rl), ("rn", valeur_rn)), start=1
            ):
                texte = formater_nombre(valeur, 2) if valeur is not None else "—"
                style = "Gagnant.TLabel" if gagnant == cle else "TLabel"
                ttk.Label(self.cadre_metriques, text=texte, style=style).grid(
                    row=ligne, column=colonne, sticky="w", padx=(0, 40), pady=3
                )

    def comparer(self) -> None:
        site_id, zone_id = self.site.valeur(), self.zone.valeur()
        periode = self._periode()
        if site_id is None or periode is None:
            return
        debut, fin = periode

        def traiter(_progression):
            return comparaison.comparer_realise(self.ctx, site_id, zone_id, debut, fin)

        def succes(resultat):
            self.actualiser_donnees()
            informer(
                self,
                f"{resultat['nb_traites']} prévision(s) rapprochée(s), dont "
                f"{resultat['nb_comparables']} avec un réel connu.",
                "Comparaison terminée",
            )

        executer_en_fond(
            self,
            traiter,
            succes,
            titre="Comparaison réel / prévu",
            message="Rapprochement des prévisions au réalisé…",
        )

    def exporter(self) -> None:
        lignes_rl = getattr(self, "_lignes_rl", [])
        lignes_rn = getattr(self, "_lignes_rn", [])
        if not lignes_rl and not lignes_rn:
            return
        chemin = choisir_fichier_a_enregistrer(
            self,
            f"comparaison_{self.zone.variable.get() or 'site'}_{date.today():%Y-%m-%d}.xlsx",
            "Exporter en Excel",
            [("Classeur Excel", "*.xlsx")],
        )
        if chemin is None:
            return
        entetes_metriques = ["Métrique", "RL", "RN"]
        lignes_metriques = [
            [libelle_m, formater_nombre(valeur_rl, 2), formater_nombre(valeur_rn, 2)]
            for libelle_m, valeur_rl, valeur_rn, _mode in _calculer_metriques(lignes_rl, lignes_rn)
        ]
        entetes_detail = [
            "Date",
            "Zone",
            "Méthode",
            "Heures prévues",
            "Heures réelles",
            "Écart (%)",
        ]
        lignes_detail = [
            [
                formater_date(r["date_jour"]),
                r["zone"],
                "RL" if r["methode"] == "regression_lineaire" else "RN",
                r["heures_prevues"],
                r["heures_reelles"],
                r["ecart_relatif"],
            ]
            for r in sorted(lignes_rl + lignes_rn, key=lambda r: (r["date_jour"], r["zone"]))
        ]
        ecrire_classeur(
            chemin.with_suffix(".xlsx"),
            {
                "Métriques": (entetes_metriques, lignes_metriques),
                "Détail": (entetes_detail, lignes_detail),
            },
        )
        informer(self, f"Export enregistré : {chemin.with_suffix('.xlsx').name}")
