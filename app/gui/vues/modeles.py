"""Écran 10 — Modèles (UC07, UC08, UC09, UC10) : administrateur."""

from __future__ import annotations

from tkinter import ttk

from app.erreurs import DonneesInvalides, ErreurApplication
from app.gui.style import COULEURS, PUCE_STATUT
from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.carte import ECART_CARTES, ajouter_carte
from app.gui.widgets.champs import ChampCase, ChampListe, ChampNombre, ChampTexte, appliquer_erreurs
from app.gui.widgets.dialogues import DialogueBase, afficher_erreur, confirmer, informer
from app.gui.widgets.graphique import COULEURS_SERIES, GraphiqueIntegre, couleur_methode
from app.gui.widgets.onglets import Onglets
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.taches_fond import executer_en_fond
from app.libelles import CIBLES_MODELE, METHODES
from app.ml.preparation import JOURS_SEMAINE, LIBELLES_VARIABLES, VARIABLES_PAR_DEFAUT
from app.services import admin, alertes, modeles, recommandations
from app.utils.format_fr import formater_date_heure, formater_nombre, formater_pourcentage

OPTIONS_ACTIVATION = [
    ("relu", "ReLU (recommandée)"),
    ("tanh", "Tangente hyperbolique"),
    ("logistic", "Logistique (sigmoïde)"),
    ("identity", "Identité (linéaire)"),
]
OPTIONS_JOURS = [(jour, jour.capitalize()) for jour in JOURS_SEMAINE]
OPTION_TOUTES_ZONES = (None, "Toutes les zones")


class VueModeles(Vue):
    """Onglets « Paramètres » et « Entraînement »."""

    titre = "Modèles"
    sous_titre = "Paramétrage, entraînement et activation des modèles de prévision"

    def construire(self) -> None:
        self.onglets = Onglets(self.contenu)
        self.onglets.pack(fill="both", expand=True)
        self.page_parametres = OngletParametres(self.onglets, self)
        self.onglets.add(self.page_parametres, text="Paramètres")
        self.page_entrainement = OngletEntrainement(self.onglets, self)
        self.onglets.add(self.page_entrainement, text="Entraînement")

    def actualiser(self) -> None:
        self.page_parametres.actualiser()
        self.page_entrainement.actualiser()


# =====================================================================
# Onglet « Paramètres » (UC07)
# =====================================================================
class OngletParametres(ttk.Frame):
    """Formulaire des paramètres ; boutons « Enregistrer les paramètres », « Rétablir les
    valeurs par défaut »."""

    def __init__(self, parent, vue: VueModeles) -> None:
        super().__init__(parent, style="Page.TFrame")
        self.vue = vue
        self.ctx = vue.ctx
        self.widgets: dict[str, object] = {}
        self._construire()

    def _construire(self) -> None:
        carte = ajouter_carte(
            self,
            "Variables d'entrée actives",
            "Les variables prises en compte par les trois modèles",
        )
        cadre = carte.zone
        self.variables: dict[str, ChampCase] = {}
        for i, cle in enumerate(VARIABLES_PAR_DEFAUT):
            case = ChampCase(cadre, LIBELLES_VARIABLES[cle], valeur=True)
            case.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 28), pady=2)
            self.variables[cle] = case
        self.variables["volume"].activer(False)
        self.variables["volume"].saisie.configure(
            text=LIBELLES_VARIABLES["volume"] + " (toujours active)"
        )

        carte = ajouter_carte(self, "Réseau de neurones", "Architecture et entraînement")
        cadre = carte.zone
        self.widgets["hidden_layer_sizes"] = ChampTexte(
            cadre, "Couches cachées (ex. 32,16)", largeur=20
        )
        self.widgets["hidden_layer_sizes"].grid(row=0, column=0, sticky="w", padx=(0, 24))
        self.widgets["activation"] = ChampListe(
            cadre, "Fonction d'activation", options=OPTIONS_ACTIVATION
        )
        self.widgets["activation"].grid(row=0, column=1, sticky="w", padx=(0, 24))
        self.widgets["max_iter"] = ChampNombre(cadre, "Itérations maximum", decimales=0)
        self.widgets["max_iter"].grid(row=0, column=2, sticky="w")

        carte = ajouter_carte(self, "Gradient boosting", "Arbres de décision boostés")
        cadre = carte.zone
        self.widgets["gb_n_estimators"] = ChampNombre(cadre, "Nombre d'arbres", decimales=0)
        self.widgets["gb_n_estimators"].grid(row=0, column=0, sticky="w", padx=(0, 24))
        self.widgets["gb_learning_rate"] = ChampNombre(cadre, "Taux d'apprentissage", decimales=3)
        self.widgets["gb_learning_rate"].grid(row=0, column=1, sticky="w", padx=(0, 24))
        self.widgets["gb_max_depth"] = ChampNombre(cadre, "Profondeur des arbres", decimales=0)
        self.widgets["gb_max_depth"].grid(row=0, column=2, sticky="w")

        carte = ajouter_carte(
            self, "Découpage et fiabilité", "Jeu de test, intervalle de confiance et dérive"
        )
        cadre = carte.zone
        self.widgets["part_test"] = ChampNombre(cadre, "Part du jeu de test (%)", decimales=0)
        self.widgets["part_test"].grid(row=0, column=0, sticky="w", padx=(0, 24))
        self.widgets["niveau_confiance"] = ChampNombre(
            cadre, "Niveau de l'intervalle de confiance (%)", decimales=0
        )
        self.widgets["niveau_confiance"].grid(row=0, column=1, sticky="w", padx=(0, 24))
        self.widgets["seuil_derive_mape"] = ChampNombre(
            cadre, "Seuil de dérive — MAPE (%)", decimales=0
        )
        self.widgets["seuil_derive_mape"].grid(row=0, column=2, sticky="w")

        carte = ajouter_carte(
            self, "Réentraînement automatique", "Jour et heure de la tâche hebdomadaire"
        )
        cadre = carte.zone
        self.widgets["jour_reentrainement"] = ChampListe(cadre, "Jour", options=OPTIONS_JOURS)
        self.widgets["jour_reentrainement"].grid(row=0, column=0, sticky="w", padx=(0, 24))
        self.widgets["heure_reentrainement"] = ChampTexte(cadre, "Heure (HH:MM)", largeur=10)
        self.widgets["heure_reentrainement"].grid(row=0, column=1, sticky="w")

        self.message_general = ttk.Label(self, text="", style="Erreur.TLabel", wraplength=760)
        self.message_general.pack(anchor="w", pady=(0, 8))

        barre = ttk.Frame(self, style="Page.TFrame")
        barre.pack(fill="x")
        Bouton(barre, "Enregistrer les paramètres", self.enregistrer, primaire=True).pack(
            side="left"
        )
        Bouton(barre, "Rétablir les valeurs par défaut", self.retablir).pack(
            side="left", padx=(8, 0)
        )

    def actualiser(self) -> None:
        config = self.vue.executer(lambda: modeles.recuperer_parametres(self.ctx))
        if config is None:
            return
        self._remplir(config)

    def _remplir(self, config: dict) -> None:
        for cle, case in self.variables.items():
            if cle != "volume":
                case.definir(cle in config["variables_actives"])
        hyper = config["hyperparametres_rn"]
        self.widgets["hidden_layer_sizes"].definir(
            ",".join(str(c) for c in hyper["hidden_layer_sizes"])
        )
        self.widgets["activation"].definir(hyper["activation"])
        self.widgets["max_iter"].definir(hyper["max_iter"])
        hyper_gb = config["hyperparametres_gb"]
        self.widgets["gb_n_estimators"].definir(hyper_gb["n_estimators"])
        self.widgets["gb_learning_rate"].definir(hyper_gb["learning_rate"])
        self.widgets["gb_max_depth"].definir(hyper_gb["max_depth"])
        self.widgets["part_test"].definir(config["part_test"] * 100)
        self.widgets["niveau_confiance"].definir(config["niveau_confiance"] * 100)
        self.widgets["seuil_derive_mape"].definir(config["seuil_derive_mape"])
        self.widgets["jour_reentrainement"].definir(config["jour_reentrainement"])
        self.widgets["heure_reentrainement"].definir(config["heure_reentrainement"])
        for widget in self.widgets.values():
            widget.effacer_erreur()
        self.message_general.configure(text="")

    def _lire_configuration(self) -> dict:
        variables = [cle for cle, case in self.variables.items() if case.valeur()]
        couches_texte = self.widgets["hidden_layer_sizes"].valeur()
        return {
            "variables_actives": variables,
            "hyperparametres_rn": {
                "hidden_layer_sizes": [c.strip() for c in couches_texte.split(",") if c.strip()],
                "activation": self.widgets["activation"].valeur(),
                "max_iter": self.widgets["max_iter"].valeur(),
            },
            "hyperparametres_gb": {
                "n_estimators": self.widgets["gb_n_estimators"].valeur(),
                "learning_rate": self.widgets["gb_learning_rate"].valeur(),
                "max_depth": self.widgets["gb_max_depth"].valeur(),
            },
            "part_test": _pourcentage_vers_fraction(self.widgets["part_test"].valeur()),
            "niveau_confiance": _pourcentage_vers_fraction(
                self.widgets["niveau_confiance"].valeur()
            ),
            "seuil_derive_mape": self.widgets["seuil_derive_mape"].valeur(),
            "jour_reentrainement": self.widgets["jour_reentrainement"].valeur(),
            "heure_reentrainement": self.widgets["heure_reentrainement"].valeur(),
        }

    def enregistrer(self) -> None:
        for widget in self.widgets.values():
            widget.effacer_erreur()
        self.message_general.configure(text="")
        try:
            enregistree = modeles.parametrer_modeles(self.ctx, self._lire_configuration())
        except DonneesInvalides as exc:
            mappees = {cle: message for cle, message in exc.erreurs.items() if cle in self.widgets}
            appliquer_erreurs(self.widgets, mappees)
            reste = [message for cle, message in exc.erreurs.items() if cle not in self.widgets]
            self.message_general.configure(text=" ".join(reste) or exc.message)
            return
        except ErreurApplication as exc:
            afficher_erreur(self, exc.message)
            return
        self._remplir(enregistree)
        informer(self, "Paramètres enregistrés.")

    def retablir(self) -> None:
        if not confirmer(
            self,
            "Rétablir les valeurs par défaut de tous les paramètres des "
            "modèles ? Les valeurs actuelles seront perdues.",
            "Confirmer le rétablissement",
        ):
            return
        defaut = self.vue.executer(lambda: modeles.retablir_defaut(self.ctx))
        if defaut is not None:
            self._remplir(defaut)
            informer(self, "Valeurs par défaut rétablies.")


def _pourcentage_vers_fraction(valeur) -> float | None:
    if valeur in (None, ""):
        return None
    from app.utils.format_fr import lire_nombre

    return lire_nombre(valeur) / 100


# =====================================================================
# Onglet « Entraînement » (UC08, UC09, UC10)
# =====================================================================
class OngletEntrainement(ttk.Frame):
    """Sélection site/zone, entraînement, tableau des versions, activation, résidus."""

    def __init__(self, parent, vue: VueModeles) -> None:
        super().__init__(parent, style="Page.TFrame")
        self.vue = vue
        self.ctx = vue.ctx
        self._construire()

    def _construire(self) -> None:
        self.bandeau_derive = ttk.Frame(self, style="Derive.TFrame", padding=(16, 10))
        self.label_derive = ttk.Label(
            self.bandeau_derive, text="", style="Derive.TLabel", wraplength=900
        )
        self.label_derive.pack(anchor="w")
        self.bandeau_derive.pack(fill="x", pady=(0, ECART_CARTES))
        self.bandeau_derive.pack_forget()  # masqué tant qu'aucune alerte de dérive n'est connue

        carte_filtres = ajouter_carte(self, marge=14)
        self.haut_barre = carte_filtres
        haut = carte_filtres.zone
        self.site = ChampListe(haut, "Site", largeur=26)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(haut, "Zone", largeur=22)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_tableau)
        self.b_entrainer = Bouton(haut, "Entraîner maintenant", self.entrainer, primaire=True)
        self.b_entrainer.pack(side="right", pady=(16, 0))

        carte_versions = ajouter_carte(
            self,
            "Versions entraînées",
            "Sélectionnez une version pour l'activer ou voir ses résidus",
        )
        self.tableau = TableauTriable(
            carte_versions.zone,
            [
                Colonne("methode_libelle", "Méthode", 150),
                Colonne("cible_libelle", "Cible", 120),
                Colonne("zone", "Zone", 110),
                Colonne("date_entrainement", "Date", 140, formateur=formater_date_heure),
                Colonne("mae", "MAE", 75, "e", formateur=lambda v: formater_nombre(v, 2)),
                Colonne("rmse", "RMSE", 75, "e", formateur=lambda v: formater_nombre(v, 2)),
                Colonne("mape", "MAPE", 75, "e", formateur=lambda v: formater_pourcentage(v, 1)),
                Colonne(
                    "biais", "Biais", 75, "e", formateur=lambda v: formater_pourcentage(v, 1, True)
                ),
                Colonne(
                    "couverture_ic",
                    "Couverture IC",
                    105,
                    "e",
                    formateur=lambda v: formater_pourcentage(v, 1),
                ),
                Colonne("actif", "Actif", 60, "center"),
                Colonne("retenue_pour_plan", "Retenue pour le plan", 150, "center"),
            ],
            hauteur=10,
        )
        self.tableau.pack(fill="both", expand=True)
        self.tableau.sur_selection(self._sur_selection)
        self.b_activer = Bouton(
            carte_versions.actions, "Activer la version sélectionnée", self.activer
        )
        self.b_activer.pack(anchor="e")

        carte_residus = ajouter_carte(
            self,
            "Résidus du jeu de test",
            "Écart entre le réel et le prédit, par valeur prédite",
            dernier=True,
        )
        self.graphique = GraphiqueIntegre(carte_residus.zone, largeur=8, hauteur=3.2)
        self.graphique.pack(fill="both", expand=True)
        self.graphique.afficher_message("Sélectionnez une version pour voir ses résidus.")

    def actualiser(self) -> None:
        sites = self.vue.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self._sur_changement_site()

    def _sur_changement_site(self) -> None:
        site_id = self.site.valeur()
        zones = (
            self.vue.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
            if site_id is not None
            else []
        )
        self.zone.definir_options(
            [OPTION_TOUTES_ZONES] + [(z["id"], z["nom"]) for z in zones], conserver=False
        )
        self._actualiser_bandeau_derive(site_id)
        self.actualiser_tableau()

    def _actualiser_bandeau_derive(self, site_id: int | None) -> None:
        """Bandeau des alertes de dérive de modèle du site (UC21) : les avertit qu'une
        méthode retenue pour le plan a décroché du réel, avant qu'ils n'activent une autre
        version (UC10)."""
        ouvertes = (
            self.vue.executer(
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
        self.bandeau_derive.pack(fill="x", pady=(0, ECART_CARTES), before=self.haut_barre)

    def actualiser_tableau(self) -> None:
        site_id = self.site.valeur()
        self.b_entrainer.activer(site_id is not None, "Créez d'abord un site et une zone.")
        if site_id is None:
            self.tableau.charger([], message_vide="Aucun site.")
            return
        zone_id = self.zone.valeur()
        versions = (
            self.vue.executer(lambda: modeles.lister_versions(self.ctx, site_id, zone_id)) or []
        )
        for version in versions:
            version["methode_libelle"] = METHODES[version["methode"]]
            version["cible_libelle"] = CIBLES_MODELE[version["cible"]]
            metriques = version["metriques"]
            for cle in ("mae", "rmse", "mape", "biais", "couverture_ic"):
                version[cle] = metriques.get(cle)
        self.tableau.charger(
            versions,
            etiquettes=lambda v: "vert" if v["actif"] else None,
            message_vide="Aucune version entraînée pour cette sélection. "
            "Utilisez « Entraîner maintenant ».",
        )
        self._sur_selection()

    def _sur_selection(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        self.b_activer.activer(ligne is not None, "Sélectionnez une version dans le tableau.")
        if ligne is None:
            self.graphique.afficher_message("Sélectionnez une version pour voir ses résidus.")
            return
        residus = ligne["metriques"].get("residus_test") or []
        predictions = ligne["metriques"].get("predictions_test") or []
        if not residus:
            self.graphique.afficher_message("Résidus indisponibles pour cette version.")
            return

        def _dessiner(axe):
            couleur = {
                "regression_lineaire": COULEURS_SERIES[0],
                "reseau_neurones": COULEURS_SERIES[1],
                "gradient_boosting": couleur_methode("gradient_boosting"),
            }[ligne["methode"]]
            axe.scatter(predictions, residus, color=couleur, alpha=0.75, edgecolors="none")
            axe.axhline(0, color=COULEURS["texte_secondaire"], linewidth=1, linestyle="--")
            axe.set_xlabel("Valeur prédite")
            axe.set_ylabel("Résidu (réel − prédit)")
            axe.set_title(
                f"{ligne['methode_libelle']} — {ligne['cible_libelle']}",
                fontsize=9,
                loc="left",
                color=COULEURS["texte_secondaire"],
            )

        self.graphique.dessiner(_dessiner)

    def entrainer(self) -> None:
        site_id = self.site.valeur()
        zone_id = self.zone.valeur()
        if site_id is None:
            return

        def traiter(progression):
            return modeles.entrainer_modeles(self.ctx, site_id, zone_id, progression)

        def succes(resume):
            self.actualiser_tableau()
            if resume.avertissements:
                informer(
                    self,
                    f"{len(resume.versions)} version(s) créée(s).\n\n"
                    "Avertissements :\n" + "\n".join(resume.avertissements),
                    "Entraînement terminé",
                )
            else:
                informer(
                    self,
                    f"{len(resume.versions)} version(s) créée(s) et évaluée(s).",
                    "Entraînement terminé",
                )

        executer_en_fond(
            self,
            traiter,
            succes,
            titre="Entraînement des modèles",
            message="Entraînement de la régression linéaire, du réseau de neurones et du "
            "gradient boosting…",
            annulable=True,
        )

    def activer(self) -> None:
        ligne = self.tableau.ligne_selectionnee()
        if ligne is None:
            return
        comparaison = self.vue.executer(
            lambda: modeles.comparer_avant_activation(self.ctx, ligne["id"])
        )
        if comparaison is None:
            return
        if not _confirmer_activation(self, comparaison):
            return
        if self.vue.executer(lambda: modeles.activer_version(self.ctx, ligne["id"])):
            self.actualiser_tableau()
            informer(self, "Version activée.")


def _confirmer_activation(parent, comparaison: dict) -> bool:
    """Fenêtre de confirmation : métriques de la version actuelle et de la candidate, côte à côte."""
    candidate, actif = comparaison["candidate"], comparaison["actif_actuel"]
    dialogue = DialogueBase(parent, "Activer la version sélectionnée", redimensionnable=True)
    ttk.Label(
        dialogue.corps,
        wraplength=520,
        justify="left",
        text=f"Activer la version du {formater_date_heure(candidate['date_entrainement'])} "
        f"({METHODES[candidate['methode']]}, {CIBLES_MODELE[candidate['cible']]}) pour la "
        f"zone « {candidate['zone']} » ?"
        + (
            " Elle deviendra la méthode retenue pour le plan de charge."
            if candidate["cible"] == "heures"
            else ""
        ),
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

    colonnes = [("Actuellement active", actif), ("Nouvelle version", candidate)]
    for c, (titre, version) in enumerate(colonnes):
        ttk.Label(dialogue.corps, text=titre, style="Gras.TLabel").grid(
            row=1, column=c, sticky="w", padx=(0, 20)
        )
        texte = _resume_metriques(version)
        ttk.Label(dialogue.corps, text=texte, justify="left").grid(
            row=2, column=c, sticky="nw", padx=(0, 20)
        )

    resultat = {"valeur": False}

    def repondre(valeur: bool) -> None:
        resultat["valeur"] = valeur
        dialogue.fermer()

    dialogue.ajouter_bouton("Non", lambda: repondre(False))
    dialogue.ajouter_bouton("Oui", lambda: repondre(True), primaire=True, defaut=True)
    dialogue.afficher()
    return resultat["valeur"]


def _resume_metriques(version: dict | None) -> str:
    if version is None:
        return "Aucune version active actuellement."
    m = version["metriques"]
    return (
        f"MAE : {formater_nombre(m.get('mae'), 2)}\n"
        f"RMSE : {formater_nombre(m.get('rmse'), 2)}\n"
        f"MAPE : {formater_pourcentage(m.get('mape'), 1)}\n"
        f"Biais : {formater_pourcentage(m.get('biais'), 1, True)}\n"
        f"Couverture IC : {formater_pourcentage(m.get('couverture_ic'), 1)}"
    )
