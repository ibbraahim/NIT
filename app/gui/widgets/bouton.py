"""Boutons de l'application, en pilule.

``Bouton`` est le point d'entrée unique : ``primaire=True`` construit un :class:`BoutonPrimaire`
(dégradé de marque), sinon un :class:`BoutonSecondaire` (contour discret). Les deux sont des
``Canvas`` (Tk ne sait pas arrondir un ``ttk.Button``) qui exposent la même API qu'un bouton
ttk pour le reste du code : :meth:`activer`, :attr:`est_actif`, ``state``/``instate``,
``cget("text")``/``configure(text=...)``, ``invoke``, plus une info-bulle qui explique pourquoi un
bouton est grisé. Ils prennent le focus au clavier (Tab) et se déclenchent avec Espace ou Entrée.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont
from tkinter import ttk

from app.gui.degrades import eclaircir, melanger
from app.gui.formes import photo, rectangle_arrondi
from app.gui.icones import icone_interface
from app.gui.style import (
    COULEUR_ACCENT_2,
    COULEUR_ACCENT_3,
    COULEUR_ACCENT_4,
    COULEUR_ACCENT_5,
    COULEURS,
)
from app.gui.widgets.infobulle import InfoBulle

HAUTEUR_BOUTON = 38
MARGE_HORIZONTALE = 22
DEGRADE_BOUTON = (COULEUR_ACCENT_2, COULEUR_ACCENT_3, COULEUR_ACCENT_4, COULEUR_ACCENT_5)


def couleur_fond(widget: tk.Misc) -> str:
    """Couleur de fond réellement peinte derrière ``widget`` (widget Tk, ou cadre/étiquette ttk
    dont on lit le style)."""
    try:
        return str(widget.cget("background"))
    except tk.TclError:
        style = ttk.Style(widget)
        nom = str(widget.cget("style")) or widget.winfo_class()
        return style.lookup(nom, "background") or COULEURS["surface"]


class _BoutonPilule(tk.Canvas):
    """Logique commune : dessin en pilule, survol, appui, focus clavier, état grisé."""

    def __init__(
        self,
        parent,
        texte: str,
        commande: Callable[[], None],
        aide: str = "",
        icone: str | None = None,
        sur_marque: bool = False,
        **_options,
    ) -> None:
        self._sur_marque = sur_marque
        self._commande = commande
        self._texte = texte
        self._icone = icone
        self._actif = True
        self._survole = False
        self._enfonce = False
        self._a_le_focus = False
        self._aide = aide
        self.raison = ""
        super().__init__(
            parent,
            height=HAUTEUR_BOUTON,
            highlightthickness=0,
            borderwidth=0,
            background=couleur_fond(parent),
            cursor="hand2",
            takefocus=True,
        )
        self._police = tkfont.Font(root=self, font=tkfont.nametofont("TkDefaultFont"))
        self._police.configure(weight="bold")
        self._infobulle = InfoBulle(self, aide)
        self._mesurer()
        self._dessiner()
        self.bind("<Enter>", self._entrer)
        self.bind("<Leave>", self._sortir)
        self.bind("<ButtonPress-1>", self._appuyer)
        self.bind("<ButtonRelease-1>", self._relacher)
        self.bind("<FocusIn>", lambda _e: self._changer_focus(True))
        self.bind("<FocusOut>", lambda _e: self._changer_focus(False))
        for touche in ("<space>", "<Return>", "<KP_Enter>"):
            self.bind(touche, lambda _e: self.invoke())

    # --- Rendu ------------------------------------------------------------
    def _mesurer(self) -> None:
        largeur = self._police.measure(self._texte) + 2 * MARGE_HORIZONTALE
        if self._icone:
            largeur += 24
        self._largeur = max(largeur, 84)
        self.configure(width=self._largeur)

    def _image_fond(self):  # pragma: no cover - redéfinie
        raise NotImplementedError

    def _couleurs_texte(self) -> tuple[str, str]:  # pragma: no cover - redéfinie
        """(couleur du texte actif, couleur de l'icône)."""
        raise NotImplementedError

    def _dessiner(self) -> None:
        self.delete("all")
        image = self._image_fond()
        self.create_image(0, 0, anchor="nw", image=image)
        couleur = COULEURS["desactive"] if not self._actif else self._couleurs_texte()[0]
        decalage = 1 if self._enfonce and self._actif else 0
        x = self._largeur / 2 + decalage
        if self._icone:
            icone = photo(
                self,
                ("bouton-icone", self._icone, couleur),
                lambda: icone_interface(self._icone, couleur, 16),
            )
            largeur_texte = self._police.measure(self._texte)
            debut = self._largeur / 2 - (largeur_texte + 24) / 2 + decalage
            self.create_image(debut + 8, HAUTEUR_BOUTON / 2 + decalage, image=icone)
            x = debut + 24 + largeur_texte / 2
        self.create_text(
            x,
            HAUTEUR_BOUTON / 2 + decalage,
            text=self._texte,
            fill=couleur,
            font=self._police,
        )

    # --- Interactions -----------------------------------------------------
    def _entrer(self, _evenement=None) -> None:
        if self._actif:
            self._survole = True
            self._dessiner()

    def _sortir(self, _evenement=None) -> None:
        self._survole = False
        self._enfonce = False
        self._dessiner()

    def _appuyer(self, _evenement=None) -> None:
        if self._actif:
            self._enfonce = True
            self._dessiner()

    def _relacher(self, evenement=None) -> None:
        etait_enfonce = self._enfonce
        self._enfonce = False
        self._dessiner()
        # Un clic qui commence puis quitte le bouton avant relâchement ne déclenche rien
        # (même comportement qu'un ttk.Button).
        if evenement is not None and not (
            0 <= evenement.x <= self._largeur and 0 <= evenement.y <= HAUTEUR_BOUTON
        ):
            return
        if etait_enfonce:
            self.invoke()

    def _changer_focus(self, focus: bool) -> None:
        self._a_le_focus = focus
        self._dessiner()

    def invoke(self) -> None:
        """Déclenche l'action du bouton (sans effet s'il est grisé)."""
        if self._actif:
            self._commande()

    # --- API compatible avec ttk.Button ----------------------------------------
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
            self._mesurer()
            self._dessiner()
        if fusion:
            super().configure(**fusion)

    config = configure

    def activer(self, actif: bool, raison: str = "") -> None:
        """Active le bouton, ou le grise en affichant ``raison`` au survol."""
        self._actif = actif
        self._survole = False
        self._enfonce = False
        self.raison = "" if actif else raison
        self._infobulle.definir(self._aide if actif else raison)
        super().configure(cursor="hand2" if actif else "arrow", takefocus=actif)
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


class BoutonPrimaire(_BoutonPilule):
    """Bouton principal : pilule en dégradé de marque, plus claire au survol."""

    def _image_fond(self):
        c = COULEURS
        if not self._actif:
            fabrique = lambda: rectangle_arrondi(  # noqa: E731
                self._largeur, HAUTEUR_BOUTON, HAUTEUR_BOUTON / 2, (c["surface_2"],)
            )
            cle = ("pilule-inactive", self._largeur, c["surface_2"])
        else:
            couleurs = DEGRADE_BOUTON
            if self._enfonce:
                couleurs = tuple(melanger(x, "#000000", 0.18) for x in couleurs)
            elif self._survole:
                couleurs = tuple(eclaircir(x, 0.16) for x in couleurs)
            bordure = c["primaire_clair"] if self._a_le_focus else None
            fabrique = lambda: rectangle_arrondi(  # noqa: E731
                self._largeur,
                HAUTEUR_BOUTON,
                HAUTEUR_BOUTON / 2,
                couleurs,
                0.0,
                bordure,
                2.0,
            )
            cle = ("pilule-primaire", self._largeur, couleurs, bordure)
        return photo(self, cle, fabrique)

    def _couleurs_texte(self) -> tuple[str, str]:
        return "#FFFFFF", "#FFFFFF"


#: Couleurs d'un bouton secondaire posé sur un fond de marque (toujours navy, quel que soit le
#: thème) : écran de connexion.
_SUR_MARQUE = {
    "surface_2": "#16204A",
    "selection": "#1E2A5E",
    "accent": COULEUR_ACCENT_2,
    "champ_bordure": "#3A4680",
    "texte": "#FFFFFF",
    "desactive": "#6B76A8",
}


class BoutonSecondaire(_BoutonPilule):
    """Bouton secondaire : pilule à contour discret, fond de la carte, teinte au survol."""

    def _palette(self):
        return _SUR_MARQUE if self._sur_marque else COULEURS

    def _image_fond(self):
        c = self._palette()
        fond = couleur_fond(self.master)
        if not self._actif:
            remplissage, bordure = c["surface_2"], None
        elif self._enfonce:
            remplissage, bordure = c["selection"], c["accent"]
        elif self._survole:
            remplissage, bordure = c["surface_2"], c["accent"]
        else:
            remplissage = fond
            bordure = c["accent"] if self._a_le_focus else c["champ_bordure"]
        cle = ("pilule-secondaire", self._largeur, remplissage, bordure)
        return photo(
            self,
            cle,
            lambda: rectangle_arrondi(
                self._largeur,
                HAUTEUR_BOUTON,
                HAUTEUR_BOUTON / 2,
                (remplissage,),
                0.0,
                bordure,
                1.5 if self._a_le_focus else 1.0,
            ),
        )

    def _couleurs_texte(self) -> tuple[str, str]:
        texte = self._palette()["texte"]
        return texte, texte


class Bouton:
    """Point d'entrée : ``Bouton(parent, texte, commande, aide, primaire)`` construit, selon
    ``primaire``, un :class:`BoutonPrimaire` ou un :class:`BoutonSecondaire`."""

    def __new__(
        cls,
        parent,
        texte: str,
        commande: Callable[[], None],
        aide: str = "",
        primaire: bool = False,
        **options,
    ):
        classe = BoutonPrimaire if primaire else BoutonSecondaire
        return classe(parent, texte, commande, aide, **options)
