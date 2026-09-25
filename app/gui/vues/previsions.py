"""Écran 4 — Prévisions (UC11) : planificateur (génération), responsable (lecture)."""

from __future__ import annotations

from tkinter import ttk

import matplotlib.dates as mdates

from app.gui.style import COULEURS
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampListe
from app.gui.widgets.dialogues import choisir_fichier_a_enregistrer, informer
from app.gui.widgets.graphique import GraphiqueIntegre
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.taches_fond import executer_en_fond
from app.services import admin, planification
from app.services.droits import a_le_droit
from app.services.planification import HORIZONS_VALIDES
from app.utils.fichiers_excel import ecrire_classeur
from app.utils.format_fr import formater_date, formater_nombre

OPTIONS_HORIZON = [(h, f"{h} jours") for h in HORIZONS_VALIDES]

COLONNES_TABLEAU = [
    Colonne("date_jour", "Date", 100, "center"),
    Colonne("zone", "Zone", 120),
    Colonne("volume_prevu", "Volume prévu", 110, "e"),
    Colonne("heures_rl", "Heures RL", 100, "e"),
    Colonne("heures_rn", "Heures RN", 100, "e"),
    Colonne("effectif_rl", "Effectif RL", 100, "e"),
    Colonne("effectif_rn", "Effectif RN", 100, "e"),
    Colonne("equipements_rl", "Équipements RL", 120, "e"),
    Colonne("equipements_rn", "Équipements RN", 120, "e"),
    Colonne("ic_actif", "Intervalle de confiance", 170, "center"),
    Colonne("modele_actif_coche", "Modèle actif", 100, "center"),
]


def _intervalle_actif(ligne: dict) -> str:
    suffixe = (ligne.get("modele_actif") or "").lower()
    if not suffixe or ligne.get(f"ic_bas_{suffixe}") is None:
        return "—"
    return (
        f"[{formater_nombre(ligne[f'ic_bas_{suffixe}'], 1)} ; "
        f"{formater_nombre(ligne[f'ic_haut_{suffixe}'], 1)}]"
    )


class VuePrevisions(Vue):
    """Filtres Site/Zone/Horizon, génération, tableau et graphique RL/RN."""

    titre = "Prévisions"
    sous_titre = "Traduction du volume prévu en heures, effectif et équipements"

    def construire(self) -> None:
        self.peut_generer = a_le_droit(self.ctx, "UC11")
        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 10))
        self.site = ChampListe(barre, "Site", largeur=26)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(barre, "Zone", largeur=22)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_donnees)
        self.horizon = ChampListe(barre, "Horizon", options=OPTIONS_HORIZON, largeur=12)
        self.horizon.pack(side="left", padx=(16, 0))
        self.horizon.sur_changement(self.actualiser_donnees)

        boutons = ttk.Frame(barre)
        boutons.pack(side="left", padx=(24, 0), pady=(14, 0))
        self.b_generer = Bouton(boutons, "Générer les prévisions", self.generer, primaire=True)
        self.b_generer.pack(side="left")
        if not self.peut_generer:
            self.b_generer.pack_forget()
        self.b_exporter = Bouton(boutons, "Exporter en Excel", self.exporter)
        self.b_exporter.pack(side="left", padx=(8, 0))

        corps = ttk.Frame(self.contenu)
        corps.pack(fill="both", expand=True)
        self.tableau = TableauTriable(corps, COLONNES_TABLEAU, hauteur=14)
        self.tableau.pack(fill="both", expand=True)

        ttk.Label(
            self.contenu,
            text="Heures nécessaires : réel des deux méthodes, avec la "
            "bande de confiance de la méthode retenue",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(10, 4))
        self.graphique = GraphiqueIntegre(self.contenu, largeur=9, hauteur=3.2)
        self.graphique.pack(fill="both", expand=True)

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
        self.zone.definir_options([(z["id"], z["nom"]) for z in zones])
        self.actualiser_donnees()

    def actualiser_donnees(self) -> None:
        site_id, zone_id, horizon = self.site.valeur(), self.zone.valeur(), self.horizon.valeur()
        self.b_generer.activer(
            site_id is not None and zone_id is not None, "Choisissez un site et une zone."
        )
        self.b_exporter.activer(False, "Générez d'abord des prévisions.")
        if site_id is None or zone_id is None:
            self.tableau.charger([], message_vide="Choisissez un site et une zone.")
            self.graphique.afficher_message("Choisissez un site et une zone.")
            return
        lignes = (
            self.executer(
                lambda: planification.lister_previsions_ressources(
                    self.ctx, site_id, zone_id, horizon
                )
            )
            or []
        )
        for ligne in lignes:
            ligne["ic_actif"] = _intervalle_actif(ligne)
            ligne["modele_actif_coche"] = ligne["modele_actif"] or "—"
        self.tableau.charger(
            lignes,
            cle_id="date_jour",
            etiquettes=lambda l: "vert" if l["modele_actif"] else None,
            message_vide="Aucune prévision générée pour cette période. "
            "Utilisez « Générer les prévisions ».",
        )
        self.b_exporter.activer(bool(lignes), "Générez d'abord des prévisions.")
        self._dessiner_graphique(lignes)

    def _dessiner_graphique(self, lignes: list[dict]) -> None:
        if not lignes:
            self.graphique.afficher_message("Aucune prévision à afficher.")
            return
        lignes = sorted(lignes, key=lambda l: l["date_jour"])
        dates = [l["date_jour"] for l in lignes]

        def _dessiner(axe):
            axe.plot(
                dates,
                [l["heures_rl"] for l in lignes],
                marker="o",
                markersize=3,
                color=COULEURS["primaire"],
                label="Régression linéaire (RL)",
            )
            axe.plot(
                dates,
                [l["heures_rn"] for l in lignes],
                marker="o",
                markersize=3,
                color=COULEURS["orange"],
                label="Réseau de neurones (RN)",
            )
            suffixe = (lignes[0].get("modele_actif") or "rl").lower()
            bas = [l.get(f"ic_bas_{suffixe}") for l in lignes]
            haut = [l.get(f"ic_haut_{suffixe}") for l in lignes]
            if all(v is not None for v in bas + haut):
                axe.fill_between(
                    dates,
                    bas,
                    haut,
                    color=COULEURS["gris"],
                    alpha=0.2,
                    label="Intervalle de confiance (méthode retenue)",
                )
            axe.set_ylabel("Heures nécessaires")
            axe.legend(fontsize=8, loc="upper left")
            axe.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
            axe.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
            axe.tick_params(axis="x", rotation=30)

        self.graphique.dessiner(_dessiner)

    def generer(self) -> None:
        site_id, zone_id, horizon = self.site.valeur(), self.zone.valeur(), self.horizon.valeur()
        if site_id is None or zone_id is None:
            return

        def traiter(progression):
            return planification.generer_previsions(
                self.ctx, site_id, zone_id, horizon, progression
            )

        def succes(resume):
            self.actualiser_donnees()
            message = f"{resume.nb_lignes} ligne(s) de prévision générée(s)."
            if resume.avertissements:
                message += "\n\nAvertissements :\n" + "\n".join(resume.avertissements)
            informer(self, message, "Prévisions générées")

        executer_en_fond(
            self,
            traiter,
            succes,
            titre="Génération des prévisions",
            message="Calcul des prévisions avec la régression linéaire et le réseau de "
            "neurones…",
            annulable=True,
        )

    def exporter(self) -> None:
        lignes = self.tableau.lignes()
        if not lignes:
            return
        date_nom = formater_date(lignes[0]["date_jour"]).replace("/", "-")
        nom = f"previsions_{self.zone.variable.get()}_{date_nom}"
        chemin = choisir_fichier_a_enregistrer(
            self, f"{nom}.xlsx", "Exporter en Excel", [("Classeur Excel", "*.xlsx")]
        )
        if chemin is None:
            return
        entetes = [
            "Date",
            "Zone",
            "Volume prévu",
            "Heures RL",
            "Heures RN",
            "Effectif RL",
            "Effectif RN",
            "Équipements RL",
            "Équipements RN",
            "Intervalle de confiance",
            "Modèle actif",
        ]
        lignes_feuille = [
            [
                formater_date(l["date_jour"]),
                l["zone"],
                l["volume_prevu"],
                l["heures_rl"],
                l["heures_rn"],
                l["effectif_rl"],
                l["effectif_rn"],
                l["equipements_rl"],
                l["equipements_rn"],
                l["ic_actif"],
                l["modele_actif_coche"],
            ]
            for l in sorted(lignes, key=lambda x: x["date_jour"])
        ]
        ecrire_classeur(chemin.with_suffix(".xlsx"), {"Prévisions": (entetes, lignes_feuille)})
        informer(self, f"Export enregistré : {chemin.with_suffix('.xlsx').name}")
