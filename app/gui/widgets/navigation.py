"""Barre latérale de navigation : groupes, icônes, élément actif en accent, compteur d'alertes.

Elle garde l'interface qu'avait le menu ``Treeview`` qu'elle remplace (``selection``,
``selection_set``, ``get_children``, ``exists``) pour que le reste de l'application n'ait pas à
changer, et ajoute :meth:`BarreNavigation.definir_badge` pour le compteur d'alertes.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import font as tkfont

from app.gui.formes import photo, rectangle_arrondi
from app.gui.icones import icone_interface
from app.gui.style import COULEURS, COULEURS_DEGRADE_MARQUE

LARGEUR_BARRE = 268
HAUTEUR_ITEM = 42
MARGE_BARRE = 12


class _ItemNavigation(tk.Canvas):
    """Une entrée du menu : icône, libellé, pastille de compteur ; survol, focus et état actif."""

    def __init__(
        self,
        parent: tk.Misc,
        cle: str,
        libelle: str,
        icone: str,
        commande: Callable[[str], None],
        largeur: int,
    ) -> None:
        super().__init__(
            parent,
            width=largeur,
            height=HAUTEUR_ITEM,
            highlightthickness=0,
            borderwidth=0,
            background=COULEURS["barre"],
            cursor="hand2",
            takefocus=True,
        )
        self.cle, self._libelle, self._icone = cle, libelle, icone
        self._commande = commande
        self._largeur = largeur
        self._actif = False
        self._survole = False
        self._focus = False
        self._badge = 0
        self._police = tkfont.Font(root=self, font=tkfont.nametofont("TkDefaultFont"))
        self._police.configure(size=11)
        self._police_gras = tkfont.Font(root=self, font=self._police)
        self._police_gras.configure(weight="bold")
        self._dessiner()
        self.bind("<Enter>", lambda _e: self._etat(survole=True))
        self.bind("<Leave>", lambda _e: self._etat(survole=False))
        self.bind("<FocusIn>", lambda _e: self._etat(focus=True))
        self.bind("<FocusOut>", lambda _e: self._etat(focus=False))
        self.bind("<ButtonRelease-1>", lambda _e: self._commande(self.cle))
        for touche in ("<Return>", "<space>"):
            self.bind(touche, lambda _e: self._commande(self.cle))

    def _etat(self, **changements) -> None:
        self._survole = changements.get("survole", self._survole)
        self._focus = changements.get("focus", self._focus)
        self._dessiner()

    def definir_actif(self, actif: bool) -> None:
        self._actif = actif
        self._dessiner()

    def definir_badge(self, nombre: int) -> None:
        self._badge = nombre
        self._dessiner()

    def _dessiner(self) -> None:
        self.delete("all")
        c = COULEURS
        largeur, hauteur = self._largeur, HAUTEUR_ITEM
        if self._actif or self._survole or self._focus:
            fond = c["barre_actif"] if self._actif else c["barre_survol"]
            bordure = c["accent"] if self._focus else None
            image = photo(
                self,
                ("nav-fond", largeur, fond, bordure),
                lambda: rectangle_arrondi(largeur, hauteur - 4, 12, (fond,), 0.0, bordure, 1.0),
            )
            self.create_image(0, 2, anchor="nw", image=image)
        if self._actif:
            barre = photo(
                self,
                ("nav-indicateur",),
                lambda: rectangle_arrondi(4, 22, 2, tuple(COULEURS_DEGRADE_MARQUE), 90.0),
            )
            self.create_image(0, hauteur / 2, anchor="w", image=barre)
        couleur = c["accent"] if self._actif else c["barre_texte"]
        icone = photo(
            self,
            ("nav-icone", self._icone, couleur),
            lambda: icone_interface(self._icone, couleur, 20),
        )
        self.create_image(22, hauteur / 2, image=icone)
        self.create_text(
            46,
            hauteur / 2,
            text=self._libelle,
            anchor="w",
            fill=c["texte"] if self._actif else couleur,
            font=self._police_gras if self._actif else self._police,
        )
        if self._badge:
            texte = str(self._badge) if self._badge < 100 else "99+"
            largeur_badge = max(self._police.measure(texte) * 0.85 + 14, 26)
            pastille = photo(
                self,
                ("nav-badge", round(largeur_badge), c["rouge"]),
                lambda: rectangle_arrondi(round(largeur_badge), 20, 10, (c["rouge"],)),
            )
            self.create_image(largeur - 14, hauteur / 2, anchor="e", image=pastille)
            self.create_text(
                largeur - 14 - largeur_badge / 2,
                hauteur / 2,
                text=texte,
                fill="#FFFFFF",
                font=("", 8, "bold"),
            )


class BarreNavigation(tk.Frame):
    """Liste verticale d'entrées regroupées sous des intitulés (``éléments`` : tuples
    ``(clé, libellé, nom d'icône, groupe)``)."""

    def __init__(
        self,
        parent: tk.Misc,
        elements: Sequence[tuple[str, str, str, str]],
        commande: Callable[[str], None],
    ) -> None:
        super().__init__(parent, background=COULEURS["barre"])
        self._commande = commande
        self._items: dict[str, _ItemNavigation] = {}
        self._cle_active: str | None = None
        groupe_precedent = None
        largeur = LARGEUR_BARRE - 2 * MARGE_BARRE
        for cle, libelle, icone, groupe in elements:
            if groupe != groupe_precedent:
                tk.Label(
                    self,
                    text=groupe.upper(),
                    background=COULEURS["barre"],
                    foreground=COULEURS["desactive"],
                    font=("", 8, "bold"),
                    anchor="w",
                ).pack(fill="x", padx=MARGE_BARRE + 10, pady=(16 if self._items else 4, 4))
                groupe_precedent = groupe
            item = _ItemNavigation(self, cle, libelle, icone, self._sur_clic, largeur)
            item.pack(padx=MARGE_BARRE, pady=1)
            self._items[cle] = item
        self._ordre = tuple(self._items)
        self._lier_clavier()

    def _sur_clic(self, cle: str) -> None:
        self._commande(cle)

    def _lier_clavier(self) -> None:
        """Flèches haut/bas : déplacent le focus d'une entrée à l'autre."""
        cles = list(self._ordre)
        for position, cle in enumerate(cles):
            item = self._items[cle]
            item.bind(
                "<Down>",
                lambda _e, p=position: self._items[cles[min(p + 1, len(cles) - 1)]].focus_set(),
            )
            item.bind("<Up>", lambda _e, p=position: self._items[cles[max(p - 1, 0)]].focus_set())

    # --- Interface reprise du Treeview de navigation ------------------------------
    def get_children(self) -> tuple[str, ...]:
        return self._ordre

    def exists(self, cle: str) -> bool:
        return cle in self._items

    def selection(self) -> tuple[str, ...]:
        return (self._cle_active,) if self._cle_active else ()

    def selection_set(self, cle: str) -> None:
        """Marque ``cle`` comme entrée active (n'appelle pas la commande de navigation)."""
        if self._cle_active in self._items:
            self._items[self._cle_active].definir_actif(False)
        self._cle_active = cle
        if cle in self._items:
            self._items[cle].definir_actif(True)

    def definir_badge(self, cle: str, nombre: int) -> None:
        """Affiche un compteur sur l'entrée ``cle`` (masqué quand ``nombre`` vaut 0)."""
        if cle in self._items:
            self._items[cle].definir_badge(nombre)
