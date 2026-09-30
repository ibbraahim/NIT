"""Écran 1 — Connexion (UC01)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from app import ACCROCHE, NOM_APPLICATION, VERSION
from app.config import DOSSIER_IMAGES
from app.contexte import Contexte
from app.erreurs import ErreurApplication
from app.gui.degrades import image_lueur_radiale, melanger
from app.gui.style import COULEUR_ACCENT_4, COULEUR_FOND_MARQUE, COULEUR_FOND_MARQUE_PROFOND
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampTexte
from app.journal import journal
from app.services import auth

_log = journal(__name__)


class EcranConnexion(ttk.Frame):
    """Fond aux couleurs de la marque Workly ; formulaire Identifiant / Mot de passe ;
    boutons « Se connecter » et « Quitter »."""

    def __init__(
        self, parent, sur_connexion: Callable[[Contexte], None], sur_quitter: Callable[[], None]
    ) -> None:
        super().__init__(parent, style="Marque.TFrame")
        self.sur_connexion = sur_connexion

        centre_lueur = melanger(COULEUR_ACCENT_4, COULEUR_FOND_MARQUE_PROFOND, 0.45)
        chemin_fond = image_lueur_radiale(1400, 850, centre_lueur, COULEUR_FOND_MARQUE_PROFOND)
        self._fond = tk.PhotoImage(file=str(chemin_fond))
        tk.Label(
            self, image=self._fond, background=COULEUR_FOND_MARQUE_PROFOND, borderwidth=0
        ).place(x=0, y=0, relwidth=1, relheight=1)

        carte = ttk.Frame(self, style="Marque.TFrame", padding=32)
        carte.place(relx=0.5, rely=0.45, anchor="center")

        self._logo = tk.PhotoImage(file=str(DOSSIER_IMAGES / "logo_workly_88.png"))
        ttk.Label(carte, image=self._logo, background=COULEUR_FOND_MARQUE).grid(
            row=0, column=0, columnspan=2, pady=(0, 12)
        )
        ttk.Label(carte, text=NOM_APPLICATION, style="MarqueTitre.TLabel").grid(
            row=1, column=0, columnspan=2
        )
        ttk.Label(carte, text=ACCROCHE, style="MarqueAccroche.TLabel").grid(
            row=2, column=0, columnspan=2, pady=(2, 24)
        )
        self.identifiant = ChampTexte(carte, "Identifiant", largeur=34, style_cadre="Marque.TFrame")
        self.identifiant.grid(row=3, column=0, columnspan=2, sticky="we")
        self.mot_de_passe = ChampTexte(
            carte, "Mot de passe", largeur=34, masque=True, style_cadre="Marque.TFrame"
        )
        self.mot_de_passe.grid(row=4, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.message = ttk.Label(
            carte, text="", style="Erreur.TLabel", wraplength=320, background=COULEUR_FOND_MARQUE
        )
        self.message.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        boutons = ttk.Frame(carte, style="Marque.TFrame")
        boutons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(16, 0))
        self.bouton_quitter = ttk.Button(boutons, text="Quitter", command=sur_quitter)
        self.bouton_quitter.pack(side="right")
        self.bouton_connexion = Bouton(boutons, "Se connecter", self.se_connecter, primaire=True)
        self.bouton_connexion.pack(side="right", padx=(0, 8))
        ttk.Label(carte, text=f"Version {VERSION}", style="MarqueAide.TLabel").grid(
            row=7, column=0, sticky="w", pady=(18, 0)
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
