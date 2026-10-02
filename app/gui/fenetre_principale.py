"""Fenêtre principale : barre latérale de navigation, en-tête de page, contenu, état du système."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import ttk

from app import NOM_APPLICATION
from app.config import DOSSIER_IMAGES
from app.contexte import Contexte
from app.erreurs import ErreurApplication
from app.gui.connexion import EcranConnexion
from app.gui.formes import image_arrondie, photo
from app.gui.style import COULEURS, appliquer_style, basculer_theme, theme_courant
from app.gui.vues import ACCUEIL, ecran, ecrans_autorises
from app.gui.widgets.carte import Carte
from app.gui.widgets.dialogues import afficher_erreur, franciser_tk
from app.gui.widgets.entete import BoutonIcone, PuceUtilisateur
from app.gui.widgets.navigation import LARGEUR_BARRE, BarreNavigation
from app.journal import journal
from app.taches.planificateur import Planificateur
from app.utils.format_fr import formater_date_heure, formater_date_longue

_log = journal(__name__)

LARGEUR_MIN, HAUTEUR_MIN = 1366, 768
INTERVALLE_COMPTEUR_MS = 60_000


class Application:
    """Gère la fenêtre racine : écran de connexion puis session de travail."""

    def __init__(self, racine: tk.Tk | None = None) -> None:
        self.racine = racine or tk.Tk()
        self.racine.title(NOM_APPLICATION)
        self._definir_icone()
        appliquer_style(self.racine)
        franciser_tk(self.racine)
        largeur = min(LARGEUR_MIN, self.racine.winfo_screenwidth())
        hauteur = min(HAUTEUR_MIN, self.racine.winfo_screenheight())
        self.racine.minsize(largeur, hauteur)
        self.racine.geometry(f"{largeur}x{hauteur}")
        self.racine.report_callback_exception = self._erreur_non_geree
        self.racine.protocol("WM_DELETE_WINDOW", self.quitter)
        self.contexte: Contexte | None = None
        self.vues: dict[str, ttk.Frame] = {}
        self.vue_courante: str | None = None
        self._cadre: ttk.Frame | None = None
        self._minuterie: str | None = None
        self.planificateur = (
            Planificateur()
        )  # programmé, mais démarré depuis l'écran Administration
        self.afficher_connexion()

    # ------------------------------------------------------------------
    # Connexion / déconnexion / thème
    # ------------------------------------------------------------------
    def _vider(self) -> None:
        if self._minuterie is not None:
            self.racine.after_cancel(self._minuterie)
            self._minuterie = None
        if self._cadre is not None:
            self._cadre.destroy()
            self._cadre = None
        self.racine.configure(menu="")
        self.vues.clear()
        self.vue_courante = None

    def afficher_connexion(self) -> None:
        """Écran 1 : connexion."""
        self._vider()
        self.contexte = None
        self._cadre = EcranConnexion(self.racine, self.ouvrir_session, self.quitter)
        self._cadre.pack(fill="both", expand=True)

    def ouvrir_session(self, contexte: Contexte, ecran_initial: str | None = None) -> None:
        """Construit l'espace de travail de l'utilisateur connecté."""
        self._vider()
        self.contexte = contexte
        self._cadre = ttk.Frame(self.racine, style="Page.TFrame")
        self._cadre.pack(fill="both", expand=True)
        self._charger_etat()
        self._construire_barre_laterale(self._cadre)
        droite = ttk.Frame(self._cadre, style="Page.TFrame")
        droite.pack(side="left", fill="both", expand=True)
        self._construire_entete(droite)
        self.zone_contenu = ttk.Frame(droite, style="Page.TFrame")
        self.zone_contenu.pack(fill="both", expand=True)
        self.naviguer(ecran_initial or ACCUEIL[contexte.role])
        self.actualiser_compteur_alertes()
        self.actualiser_barre_etat()

    def se_deconnecter(self) -> None:
        """Retour à l'écran de connexion."""
        _log.info("Déconnexion de « %s ».", self.contexte.identifiant if self.contexte else "?")
        self.afficher_connexion()

    def basculer_theme(self) -> None:
        """Passe du thème sombre au thème clair (ou l'inverse), puis reconstruit l'espace de
        travail sur le même écran : les couleurs sont lues à la création des widgets."""
        ecran_courant, contexte = self.vue_courante, self.contexte
        basculer_theme()
        appliquer_style(self.racine)
        if contexte is None:
            self.afficher_connexion()
        else:
            self.ouvrir_session(contexte, ecran_courant)

    def quitter(self) -> None:
        """Ferme l'application (le planificateur de tâches est arrêté proprement)."""
        if self.planificateur is not None:
            try:
                self.planificateur.arreter()
            except Exception:  # noqa: BLE001 - fermeture best effort
                _log.exception("Arrêt du planificateur de tâches impossible.")
        self._vider()
        self.racine.destroy()

    # ------------------------------------------------------------------
    # Structure de la fenêtre
    # ------------------------------------------------------------------
    def _definir_icone(self) -> None:
        """Icône de la fenêtre (barre de titre / barre des tâches) : logo Workly."""
        try:
            self.racine.iconbitmap(str(DOSSIER_IMAGES / "logo_workly.ico"))
        except tk.TclError:
            try:
                self._icone = tk.PhotoImage(file=str(DOSSIER_IMAGES / "logo_workly_88.png"))
                self.racine.iconphoto(True, self._icone)
            except tk.TclError:
                _log.warning("Icône de fenêtre indisponible.")

    def _charger_etat(self) -> None:
        try:
            from app.services.admin import etat_application

            self.etat = etat_application(self.contexte)
        except ErreurApplication as exc:
            _log.warning("État de l'application indisponible : %s", exc)
            self.etat = {"demonstration": False}

    def _construire_barre_laterale(self, parent: ttk.Frame) -> None:
        c = COULEURS
        barre = tk.Frame(parent, background=c["barre"], width=LARGEUR_BARRE)
        barre.pack(side="left", fill="y")
        barre.pack_propagate(False)
        tk.Frame(parent, background=c["bordure"], width=1).pack(side="left", fill="y")

        marque = tk.Frame(barre, background=c["barre"])
        marque.pack(fill="x", padx=22, pady=(24, 14))
        logo = photo(
            barre,
            ("logo", 44),
            lambda: image_arrondie(str(DOSSIER_IMAGES / "logo_workly_88.png"), 44, 12),
        )
        tk.Label(marque, image=logo, background=c["barre"], borderwidth=0).pack(side="left")
        textes = tk.Frame(marque, background=c["barre"])
        textes.pack(side="left", padx=(12, 0))
        tk.Label(
            textes,
            text=NOM_APPLICATION,
            background=c["barre"],
            foreground=c["texte"],
            font=("", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            textes,
            text="Planification RH",
            background=c["barre"],
            foreground=c["texte_secondaire"],
            font=("", 9),
        ).pack(anchor="w")

        elements = [
            (e.cle, e.libelle, e.cle, e.groupe) for e in ecrans_autorises(self.contexte.role)
        ]
        self.navigation = BarreNavigation(barre, elements, self.naviguer)
        self.navigation.pack(fill="x")

        etat = Carte(
            barre,
            couleur=c["surface_2"],
            fond=c["barre"],
            bordure=c["surface_2"],
            marge=14,
        )
        etat.pack(side="bottom", fill="x", padx=14, pady=16)
        ligne = tk.Frame(etat.corps, background=c["surface_2"])
        ligne.pack(fill="x")
        self._pastille_etat = tk.Label(
            ligne, text="●", background=c["surface_2"], foreground=c["gris"], font=("", 10)
        )
        self._pastille_etat.pack(side="left")
        tk.Label(
            ligne,
            text="Planificateur de tâches",
            background=c["surface_2"],
            foreground=c["texte"],
            font=("", 9, "bold"),
            anchor="w",
        ).pack(side="left", padx=(6, 0))
        self.etat_planificateur = tk.Label(
            etat.corps,
            text="",
            background=c["surface_2"],
            foreground=c["texte_secondaire"],
            font=("", 9),
            anchor="w",
        )
        self.etat_planificateur.pack(fill="x", padx=(20, 0))
        self.etat_synchro = tk.Label(
            etat.corps,
            text="",
            background=c["surface_2"],
            foreground=c["texte_secondaire"],
            font=("", 8),
            anchor="w",
            justify="left",
            wraplength=LARGEUR_BARRE - 84,
        )
        self.etat_synchro.pack(fill="x", pady=(6, 0))

    def _construire_entete(self, parent: ttk.Frame) -> None:
        entete = ttk.Frame(parent, style="Page.TFrame", padding=(28, 22, 28, 4))
        entete.pack(fill="x")
        gauche = ttk.Frame(entete, style="Page.TFrame")
        gauche.pack(side="left")
        self.titre_page = ttk.Label(gauche, text="", style="PageTitre.TLabel")
        self.titre_page.pack(anchor="w")
        self.sous_titre_page = ttk.Label(gauche, text="", style="PageSousTitre.TLabel")
        self.sous_titre_page.pack(anchor="w")

        ctx = self.contexte
        droite = ttk.Frame(entete, style="Page.TFrame")
        droite.pack(side="right")
        ttk.Label(
            droite, text=formater_date_longue(date.today()).capitalize(), style="PageAide.TLabel"
        ).pack(side="left", padx=(0, 18))
        sombre = theme_courant() == "sombre"
        self.bouton_theme = BoutonIcone(
            droite,
            "soleil" if sombre else "lune",
            self.basculer_theme,
            "Passer au thème clair" if sombre else "Passer au thème sombre",
        )
        self.bouton_theme.pack(side="left", padx=(0, 16))
        PuceUtilisateur(
            droite,
            ctx.nom_complet or ctx.identifiant,
            ctx.libelle_role,
            [
                ("À propos de Workly", self.ouvrir_a_propos),
                ("Changer de thème", self.basculer_theme),
                None,
                ("Se déconnecter", self.se_deconnecter),
            ],
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def naviguer(self, cle: str, **parametres) -> None:
        """Affiche l'écran ``cle`` (créé à la première ouverture)."""
        definition = ecran(cle)
        if self.contexte.role not in definition.roles:
            afficher_erreur(self.racine, "Cet écran n'est pas accessible avec votre rôle.")
            return
        if self.vue_courante and self.vue_courante in self.vues:
            self.vues[self.vue_courante].pack_forget()
        vue = self.vues.get(cle)
        if vue is None:
            try:
                vue = definition.charger()(self.zone_contenu, self)
            except ErreurApplication as exc:
                afficher_erreur(self.racine, exc.message)
                return
            self.vues[cle] = vue
        vue.pack(fill="both", expand=True)
        self.vue_courante = cle
        self.titre_page.configure(text=vue.titre)
        self.sous_titre_page.configure(text=vue.sous_titre)
        if tuple(self.navigation.selection()) != (cle,):
            self.navigation.selection_set(cle)
        if parametres:
            vue.afficher_parametres(**parametres)
        try:
            vue.actualiser()
        except ErreurApplication as exc:
            afficher_erreur(self.racine, exc.message)

    # ------------------------------------------------------------------
    # Compteur d'alertes et état du système
    # ------------------------------------------------------------------
    def actualiser_compteur_alertes(self) -> None:
        """Met à jour le compteur de l'entrée « Alertes », puis se reprogramme."""
        if self.contexte is None:
            return
        if self.navigation.exists("alertes"):
            try:
                from app.services.alertes import compter_alertes_ouvertes

                self.navigation.definir_badge("alertes", compter_alertes_ouvertes(self.contexte))
            except ErreurApplication as exc:
                _log.warning("Compteur d'alertes indisponible : %s", exc)
        self._minuterie = self.racine.after(
            INTERVALLE_COMPTEUR_MS, self.actualiser_compteur_alertes
        )

    def actualiser_barre_etat(self) -> None:
        """Dernière synchronisation et état du planificateur de tâches."""
        synchro = self.etat.get("derniere_synchronisation") if hasattr(self, "etat") else None
        if synchro:
            try:
                synchro = formater_date_heure(datetime.fromisoformat(synchro))
            except ValueError:
                pass
        else:
            maj = (
                self.etat.get("derniere_mise_a_jour_historique") if hasattr(self, "etat") else None
            )
            synchro = formater_date_heure(maj) if maj else "aucune"
        self.etat_synchro.configure(text=f"Dernière synchronisation : {synchro}")
        actif = self.planificateur is not None and self.planificateur.est_actif
        self.etat_planificateur.configure(
            text="En marche" if actif else "Arrêté",
            foreground=COULEURS["vert"] if actif else COULEURS["texte_secondaire"],
        )
        self._pastille_etat.configure(
            foreground=COULEURS["vert"] if actif else COULEURS["texte_secondaire"]
        )

    # ------------------------------------------------------------------
    # Divers
    # ------------------------------------------------------------------
    def ouvrir_a_propos(self) -> None:
        """Écran 12 — À propos (menu de l'utilisateur)."""
        from app.gui.vues.a_propos import FenetreAPropos

        FenetreAPropos(self.racine).afficher()

    def _erreur_non_geree(self, type_exc, valeur, trace) -> None:
        if isinstance(valeur, ErreurApplication):
            afficher_erreur(self.racine, valeur.message)
            return
        _log.error("Erreur non gérée dans l'interface", exc_info=(type_exc, valeur, trace))
        afficher_erreur(
            self.racine,
            "Une erreur inattendue s'est produite. " "Consultez le journal de l'application.",
        )

    def lancer(self) -> None:
        """Boucle principale Tkinter."""
        self.racine.mainloop()
