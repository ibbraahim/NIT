"""Éléments de l'en-tête de page : bouton rond à icône et puce utilisateur avec son menu."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import font as tkfont

from app.gui.formes import avatar, photo, rectangle_arrondi
from app.gui.icones import icone_interface
from app.gui.style import COULEUR_ACCENT_2, COULEUR_ACCENT_4, COULEUR_ACCENT_5, COULEURS
from app.gui.widgets.bouton import couleur_fond
from app.gui.widgets.infobulle import InfoBulle

DIAMETRE_AVATAR = 38


class BoutonIcone(tk.Canvas):
    """Bouton rond à contour discret portant une icône (bascule de thème…)."""

    def __init__(
        self,
        parent: tk.Misc,
        icone: str,
        commande: Callable[[], None],
        aide: str = "",
        taille: int = 40,
    ) -> None:
        super().__init__(
            parent,
            width=taille,
            height=taille,
            highlightthickness=0,
            borderwidth=0,
            background=couleur_fond(parent),
            cursor="hand2",
            takefocus=True,
        )
        self._taille = taille
        self._icone = icone
        self._commande = commande
        self._survole = False
        self._focus = False
        self._infobulle = InfoBulle(self, aide)
        self._dessiner()
        self.bind("<Enter>", lambda _e: self._etat(survole=True))
        self.bind("<Leave>", lambda _e: self._etat(survole=False))
        self.bind("<FocusIn>", lambda _e: self._etat(focus=True))
        self.bind("<FocusOut>", lambda _e: self._etat(focus=False))
        self.bind("<ButtonRelease-1>", lambda _e: self._commande())
        for touche in ("<Return>", "<space>"):
            self.bind(touche, lambda _e: self._commande())

    def _etat(self, **changements) -> None:
        self._survole = changements.get("survole", self._survole)
        self._focus = changements.get("focus", self._focus)
        self._dessiner()

    def definir_icone(self, icone: str, aide: str = "") -> None:
        self._icone = icone
        if aide:
            self._infobulle.definir(aide)
        self._dessiner()

    def _dessiner(self) -> None:
        self.delete("all")
        c = COULEURS
        taille = self._taille
        fond = c["surface_2"] if self._survole else couleur_fond(self.master)
        bordure = c["accent"] if self._focus else c["champ_bordure"]
        image = photo(
            self,
            ("bouton-rond", taille, fond, bordure),
            lambda: rectangle_arrondi(taille, taille, taille / 2, (fond,), 0.0, bordure, 1.0),
        )
        self.create_image(0, 0, anchor="nw", image=image)
        couleur = c["texte"] if self._survole else c["texte_secondaire"]
        icone = photo(
            self,
            ("rond-icone", self._icone, couleur),
            lambda: icone_interface(self._icone, couleur, 18),
        )
        self.create_image(taille / 2, taille / 2, image=icone)


def initiales(nom: str) -> str:
    """Initiales (deux lettres au plus) d'un nom complet ou d'un identifiant."""
    mots = [m for m in nom.replace("-", " ").split() if m]
    if len(mots) >= 2:
        return mots[0][0] + mots[-1][0]
    return (mots[0][:2] if mots else "?").upper()


class PuceUtilisateur(tk.Frame):
    """Avatar, nom et rôle de l'utilisateur ; un clic ouvre un menu d'actions
    (``entrees`` : ``(libellé, commande)`` ou ``None`` pour un séparateur)."""

    def __init__(
        self,
        parent: tk.Misc,
        nom: str,
        role: str,
        entrees: Sequence[tuple[str, Callable[[], None]] | None],
    ) -> None:
        fond = couleur_fond(parent)
        super().__init__(parent, background=fond, cursor="hand2")
        self._entrees = entrees
        lettres = initiales(nom)
        image = photo(
            self,
            ("avatar", lettres, DIAMETRE_AVATAR),
            lambda: avatar(
                lettres, DIAMETRE_AVATAR, (COULEUR_ACCENT_2, COULEUR_ACCENT_4, COULEUR_ACCENT_5)
            ),
        )
        c = COULEURS
        police_nom = tkfont.Font(root=self, font=tkfont.nametofont("TkDefaultFont"))
        police_nom.configure(weight="bold")
        self._police_nom = police_nom
        widgets = [
            tk.Label(self, image=image, background=fond, borderwidth=0),
        ]
        widgets[0].pack(side="left")
        textes = tk.Frame(self, background=fond)
        textes.pack(side="left", padx=(10, 6))
        widgets.append(textes)
        widgets.append(
            tk.Label(
                textes,
                text=nom,
                background=fond,
                foreground=c["texte"],
                font=police_nom,
                anchor="w",
            )
        )
        widgets[-1].pack(anchor="w")
        widgets.append(
            tk.Label(
                textes,
                text=role,
                background=fond,
                foreground=c["texte_secondaire"],
                font=("", 9),
                anchor="w",
            )
        )
        widgets[-1].pack(anchor="w")
        chevron = photo(
            self,
            ("chevron", c["texte_secondaire"]),
            lambda: icone_interface("chevron_bas", c["texte_secondaire"], 16),
        )
        widgets.append(tk.Label(self, image=chevron, background=fond, borderwidth=0))
        widgets[-1].pack(side="left")
        for widget in (self, *widgets):
            widget.bind("<Button-1>", self._ouvrir_menu)

    def _ouvrir_menu(self, _evenement=None) -> None:
        menu = tk.Menu(self, tearoff=False)
        for entree in self._entrees:
            if entree is None:
                menu.add_separator()
            else:
                libelle, commande = entree
                menu.add_command(label=libelle, command=commande)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
