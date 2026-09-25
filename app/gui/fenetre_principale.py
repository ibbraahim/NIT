"""Fenêtre principale : bandeau, menu de navigation par rôle, contenu et barre d'état."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import ttk

from app import NOM_APPLICATION
from app.contexte import Contexte
from app.erreurs import ErreurApplication
from app.gui.connexion import EcranConnexion
from app.gui.style import COULEURS, appliquer_style
from app.gui.vues import ACCUEIL, ecran, ecrans_autorises
from app.gui.widgets.dialogues import afficher_erreur, franciser_tk
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
    # Connexion / déconnexion
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

    def ouvrir_session(self, contexte: Contexte) -> None:
        """Construit l'espace de travail de l'utilisateur connecté."""
        self._vider()
        self.contexte = contexte
        self._cadre = ttk.Frame(self.racine)
        self._cadre.pack(fill="both", expand=True)
        self._construire_menu_aide()
        self._construire_bandeau()
        self._construire_bandeau_demo()
        self._construire_barre_etat()
        corps = ttk.Frame(self._cadre)
        corps.pack(fill="both", expand=True)
        self._construire_navigation(corps)
        self.zone_contenu = ttk.Frame(corps)
        self.zone_contenu.pack(side="left", fill="both", expand=True)
        self.naviguer(ACCUEIL[contexte.role])
        self.actualiser_compteur_alertes()
        self.actualiser_barre_etat()

    def se_deconnecter(self) -> None:
        """Bouton « Se déconnecter » : retour à l'écran de connexion."""
        _log.info("Déconnexion de « %s ».", self.contexte.identifiant if self.contexte else "?")
        self.afficher_connexion()

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
    def _construire_menu_aide(self) -> None:
        barre = tk.Menu(self.racine, tearoff=False)
        aide = tk.Menu(barre, tearoff=False)
        aide.add_command(label="À propos", command=self.ouvrir_a_propos)
        barre.add_cascade(label="Aide", menu=aide)
        self.racine.configure(menu=barre)

    def _construire_bandeau(self) -> None:
        bandeau = ttk.Frame(self._cadre, style="Bandeau.TFrame", padding=(16, 10))
        bandeau.pack(fill="x")
        ttk.Label(bandeau, text=NOM_APPLICATION, style="BandeauTitre.TLabel").pack(side="left")
        ttk.Button(
            bandeau, text="Se déconnecter", style="Bandeau.TButton", command=self.se_deconnecter
        ).pack(side="right")
        ctx = self.contexte
        ttk.Label(
            bandeau,
            text=f"{ctx.nom_complet or ctx.identifiant}  ·  {ctx.libelle_role}",
            style="Bandeau.TLabel",
        ).pack(side="right", padx=(0, 16))

    def _construire_bandeau_demo(self) -> None:
        try:
            from app.services.admin import etat_application

            self.etat = etat_application(self.contexte)
        except ErreurApplication as exc:
            _log.warning("État de l'application indisponible : %s", exc)
            self.etat = {"demonstration": False}
        if self.etat.get("demonstration"):
            cadre = ttk.Frame(self._cadre, style="Demo.TFrame", padding=(16, 4))
            cadre.pack(fill="x")
            ttk.Label(
                cadre,
                style="Demo.TLabel",
                text="Données de démonstration — ce jeu de données est fictif et sert "
                "uniquement à rejouer la situation du lundi.",
            ).pack(side="left")

    def _construire_navigation(self, parent: ttk.Frame) -> None:
        cadre = ttk.Frame(parent, style="Navigation.TFrame", width=230)
        cadre.pack(side="left", fill="y")
        cadre.pack_propagate(False)
        self.navigation = ttk.Treeview(
            cadre, show="tree", selectmode="browse", style="Navigation.Treeview"
        )
        self.navigation.column("#0", width=230)
        self.navigation.pack(fill="both", expand=True, pady=(8, 0))
        for element in ecrans_autorises(self.contexte.role):
            self.navigation.insert("", "end", iid=element.cle, text=f"   {element.libelle}")
        self.navigation.bind("<<TreeviewSelect>>", self._sur_navigation)

    def _construire_barre_etat(self) -> None:
        barre = ttk.Frame(self._cadre, style="Etat.TFrame", padding=(12, 3))
        barre.pack(side="bottom", fill="x")
        self.etat_synchro = ttk.Label(barre, text="", style="Etat.TLabel")
        self.etat_synchro.pack(side="left")
        self.etat_planificateur = ttk.Label(barre, text="", style="Etat.TLabel")
        self.etat_planificateur.pack(side="left", padx=(24, 0))
        ttk.Label(
            barre, text=formater_date_longue(date.today()).capitalize(), style="Etat.TLabel"
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _sur_navigation(self, _evenement=None) -> None:
        selection = self.navigation.selection()
        if selection and selection[0] != self.vue_courante:
            self.naviguer(selection[0])

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
        if tuple(self.navigation.selection()) != (cle,):
            self.navigation.selection_set(cle)
        if parametres:
            vue.afficher_parametres(**parametres)
        try:
            vue.actualiser()
        except ErreurApplication as exc:
            afficher_erreur(self.racine, exc.message)

    # ------------------------------------------------------------------
    # Compteur d'alertes et barre d'état
    # ------------------------------------------------------------------
    def actualiser_compteur_alertes(self) -> None:
        """Met à jour « Alertes (n) » dans le menu, puis se reprogramme."""
        if self.contexte is None:
            return
        if self.navigation.exists("alertes"):
            try:
                from app.services.alertes import compter_alertes_ouvertes

                nombre = compter_alertes_ouvertes(self.contexte)
                texte = "   Alertes" + (f"  ({nombre})" if nombre else "")
                self.navigation.item("alertes", text=texte)
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
            text=f"Planificateur de tâches : {'en marche' if actif else 'arrêté'}",
            foreground=COULEURS["vert"] if actif else COULEURS["texte_secondaire"],
        )

    # ------------------------------------------------------------------
    # Divers
    # ------------------------------------------------------------------
    def ouvrir_a_propos(self) -> None:
        """Écran 12 — À propos (menu « Aide »)."""
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
