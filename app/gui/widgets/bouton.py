"""Boutons de l'application.

``Bouton`` est le point d'entrée unique : ``primaire=False`` construit un ``ttk.Button``
standard, ``primaire=True`` construit plutôt un :class:`BoutonPrimaire` en dégradé de
marque (la référence visuelle demande des boutons principaux en dégradé, avec un léger
« glow » au survol). Les deux exposent la même API (:meth:`activer`, :attr:`est_actif`,
info-bulle qui explique pourquoi un bouton est grisé), pour que le reste du code n'ait pas
à savoir lequel il manipule.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont
from tkinter import ttk

from app.gui.degrades import eclaircir, image_degradee
from app.gui.style import COULEURS, COULEURS_DEGRADE_MARQUE
from app.gui.widgets.infobulle import InfoBulle

HAUTEUR_PRIMAIRE = 32


class Bouton(ttk.Button):
    """``ttk.Button`` (bouton secondaire) avec :meth:`activer` et info-bulle explicative
    quand il est grisé."""

    def __new__(
        cls,
        parent,
        texte: str,
        commande: Callable[[], None],
        aide: str = "",
        primaire: bool = False,
        **options,
    ):
        if primaire:
            return BoutonPrimaire(parent, texte, commande, aide, **options)
        return super().__new__(cls)

    def __init__(
        self,
        parent,
        texte: str,
        commande: Callable[[], None],
        aide: str = "",
        primaire: bool = False,
        **options,
    ) -> None:
        super().__init__(parent, text=texte, command=commande, **options)
        self._aide = aide
        self._infobulle = InfoBulle(self, aide)
        self.raison = ""

    def activer(self, actif: bool, raison: str = "") -> None:
        """Active le bouton, ou le grise en affichant ``raison`` au survol."""
        self.state(["!disabled"] if actif else ["disabled"])
        self.raison = "" if actif else raison
        self._infobulle.definir(self._aide if actif else raison)

    @property
    def est_actif(self) -> bool:
        return not self.instate(["disabled"])


class BoutonPrimaire(tk.Canvas):
    """Bouton principal en dégradé de marque (5 accents), avec un léger éclaircissement au
    survol et un état grisé — équivalent statique (ttk ne peint qu'une couleur unie par
    widget) du bouton « en dégradé, mis en avant » de la référence visuelle."""

    def __init__(
        self,
        parent,
        texte: str,
        commande: Callable[[], None],
        aide: str = "",
        **_options,
    ) -> None:
        self._commande = commande
        self._texte = texte
        self._police = tkfont.nametofont("TkDefaultFont")
        largeur = self._police.measure(texte) + 44
        super().__init__(
            parent,
            width=largeur,
            height=HAUTEUR_PRIMAIRE,
            highlightthickness=0,
            borderwidth=0,
            background=COULEURS["fond"],
            cursor="hand2",
        )
        self._largeur = largeur
        self._actif = True
        self._survole = False
        self._aide = aide
        self._infobulle = InfoBulle(self, aide)
        self.raison = ""
        self._images: dict[str, tk.PhotoImage] = {}
        self._dessiner()
        self.bind("<Enter>", self._survol_entrer)
        self.bind("<Leave>", self._survol_sortir)
        self.bind("<ButtonRelease-1>", self._clic)

    # --- Rendu --------------------------------------------------------------
    def _image_degradee(self, cle: str, couleurs: list[str]) -> tk.PhotoImage:
        if cle not in self._images:
            chemin = image_degradee(self._largeur, HAUTEUR_PRIMAIRE, couleurs)
            self._images[cle] = tk.PhotoImage(file=str(chemin))
        return self._images[cle]

    def _dessiner(self) -> None:
        self.delete("all")
        if not self._actif:
            self.create_rectangle(
                0, 0, self._largeur, HAUTEUR_PRIMAIRE, fill=COULEURS["gris_clair"], width=0
            )
            couleur_texte = COULEURS["desactive"]
        else:
            if self._survole:
                couleurs = [eclaircir(c, 0.15) for c in COULEURS_DEGRADE_MARQUE]
                image = self._image_degradee("survol", couleurs)
            else:
                image = self._image_degradee("normal", COULEURS_DEGRADE_MARQUE)
            self.create_image(0, 0, anchor="nw", image=image)
            couleur_texte = "#ffffff"
        self.create_text(
            self._largeur / 2,
            HAUTEUR_PRIMAIRE / 2,
            text=self._texte,
            fill=couleur_texte,
            font=self._police,
        )

    # --- Interactions ---------------------------------------------------------
    def _survol_entrer(self, _evenement=None) -> None:
        if not self._actif:
            return
        self._survole = True
        self._dessiner()

    def _survol_sortir(self, _evenement=None) -> None:
        self._survole = False
        self._dessiner()

    def _clic(self, evenement=None) -> None:
        if not self._actif:
            return
        # Un clic qui commence puis quitte le bouton avant relâchement ne doit pas déclencher
        # l'action (même comportement qu'un ttk.Button).
        if evenement is not None and not (
            0 <= evenement.x <= self._largeur and 0 <= evenement.y <= HAUTEUR_PRIMAIRE
        ):
            return
        self._commande()

    # --- API compatible avec Bouton / ttk.Button -----------------------------
    def cget(self, key):
        """Compatibilité : ``cget("text")`` renvoie le libellé du bouton."""
        if key == "text":
            return self._texte
        return super().cget(key)

    def configure(self, cnf=None, **kwargs):
        """Compatibilité : ``configure(text=...)`` change le libellé et redessine."""
        fusion = dict(cnf or {}, **kwargs)
        if "text" in fusion:
            self._texte = fusion.pop("text")
            self._largeur = self._police.measure(self._texte) + 44
            self._images.clear()
            super().configure(width=self._largeur)
            self._dessiner()
        if fusion:
            super().configure(**fusion)

    config = configure

    def activer(self, actif: bool, raison: str = "") -> None:
        """Active le bouton, ou le grise en affichant ``raison`` au survol."""
        self._actif = actif
        self._survole = False
        self.raison = "" if actif else raison
        self._infobulle.definir(self._aide if actif else raison)
        self.configure(cursor="hand2" if actif else "arrow")
        self._dessiner()

    @property
    def est_actif(self) -> bool:
        return self._actif

    def state(self, drapeaux) -> None:
        """Compatibilité avec le code qui manipule un ``ttk.Button`` générique."""
        if "disabled" in drapeaux:
            self.activer(False, self.raison)
        elif "!disabled" in drapeaux:
            self.activer(True)

    def instate(self, drapeaux) -> bool:
        if "disabled" in drapeaux:
            return not self._actif
        return self._actif
