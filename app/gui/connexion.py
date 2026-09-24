"""Écran 1 — Connexion (UC01)."""

from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk

from app import NOM_APPLICATION, VERSION
from app.contexte import Contexte
from app.erreurs import ErreurApplication
from app.gui.widgets.champs import ChampTexte
from app.journal import journal
from app.services import auth

_log = journal(__name__)


class EcranConnexion(ttk.Frame):
    """Formulaire Identifiant / Mot de passe ; boutons « Se connecter » et « Quitter »."""

    def __init__(
        self, parent, sur_connexion: Callable[[Contexte], None], sur_quitter: Callable[[], None]
    ) -> None:
        super().__init__(parent)
        self.sur_connexion = sur_connexion
        carte = ttk.Frame(self, style="Carte.TFrame", padding=32)
        carte.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(carte, text=NOM_APPLICATION, style="Titre.TLabel", background="#ffffff").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            carte,
            text="Traduire la prévision de volume en ressources : heures, "
            "effectifs et équipements.",
            style="Aide.TLabel",
            background="#ffffff",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 18))
        self.identifiant = ChampTexte(carte, "Identifiant", largeur=34, style_cadre="Carte.TFrame")
        self.identifiant.grid(row=2, column=0, columnspan=2, sticky="we")
        self.mot_de_passe = ChampTexte(
            carte, "Mot de passe", largeur=34, masque=True, style_cadre="Carte.TFrame"
        )
        self.mot_de_passe.grid(row=3, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.message = ttk.Label(
            carte, text="", style="Erreur.TLabel", wraplength=320, background="#ffffff"
        )
        self.message.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        boutons = ttk.Frame(carte, style="Surface.TFrame")
        boutons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
        self.bouton_quitter = ttk.Button(boutons, text="Quitter", command=sur_quitter)
        self.bouton_quitter.pack(side="right")
        self.bouton_connexion = ttk.Button(
            boutons, text="Se connecter", style="Primaire.TButton", command=self.se_connecter
        )
        self.bouton_connexion.pack(side="right", padx=(0, 8))
        ttk.Label(carte, text=f"Version {VERSION}", style="Aide.TLabel", background="#ffffff").grid(
            row=6, column=0, sticky="w", pady=(18, 0)
        )
        for champ in (self.identifiant, self.mot_de_passe):
            champ.saisie.bind("<Return>", lambda _e: self.se_connecter())
        self.identifiant.focus()

    def se_connecter(self) -> None:
        """UC01 : vérifie les champs puis authentifie l'utilisateur."""
        self.identifiant.effacer_erreur()
        self.mot_de_passe.effacer_erreur()
        self.message.configure(text="")
        identifiant = self.identifiant.valeur()
        mot_de_passe = self.mot_de_passe.variable.get()
        manquant = False
        if not identifiant:
            self.identifiant.signaler_erreur("Saisissez votre identifiant.")
            manquant = True
        if not mot_de_passe:
            self.mot_de_passe.signaler_erreur("Saisissez votre mot de passe.")
            manquant = True
        if manquant:
            return
        self.bouton_connexion.state(["disabled"])
        self.update_idletasks()
        try:
            contexte = auth.authentifier(identifiant, mot_de_passe)
        except ErreurApplication as exc:
            self.message.configure(text=exc.message)
            self.mot_de_passe.vider()
            self.mot_de_passe.focus()
            return
        except Exception as exc:  # noqa: BLE001 - message français, trace au journal
            _log.exception("Erreur inattendue à la connexion : %s", exc)
            self.message.configure(text="Erreur inattendue. Consultez le journal de l'application.")
            return
        finally:
            if self.winfo_exists():
                self.bouton_connexion.state(["!disabled"])
        self.sur_connexion(contexte)
