"""Onglets du nouveau design : une barre de pilules au-dessus des pages.

``ttk.Notebook`` reste le moteur (pages, sélection, ``<<NotebookTabChanged>>``) mais son bandeau
d'onglets natif est masqué (style ``Plat.TNotebook``) : la barre de pilules, dessinée comme les
boutons, le remplace. La façade :class:`Onglets` reprend la partie de l'API d'un ``Notebook`` dont
les écrans se servent (``add``, ``tabs``, ``select``, ``index``, ``bind``).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from app.gui.formes import photo, rectangle_arrondi
from app.gui.style import COULEURS
from app.gui.widgets.bouton import DEGRADE_BOUTON, couleur_fond

HAUTEUR_BARRE = 44
MARGE_BARRE = 6
MARGE_ONGLET = 20


class _BarreOnglets(tk.Canvas):
    """Pilules cliquables (et accessibles aux flèches) qui pilotent un ``ttk.Notebook``."""

    def __init__(self, parent: tk.Misc, notebook: ttk.Notebook) -> None:
        super().__init__(
            parent,
            height=HAUTEUR_BARRE,
            highlightthickness=0,
            borderwidth=0,
            background=couleur_fond(parent),
            cursor="hand2",
            takefocus=True,
        )
        self._notebook = notebook
        self._police = tkfont.Font(root=self, font=tkfont.nametofont("TkDefaultFont"))
        self._police.configure(weight="bold")
        self._zones: list[tuple[float, float, str]] = []
        self._survol: str | None = None
        self.bind("<ButtonRelease-1>", self._cliquer)
        self.bind("<Motion>", self._survoler)
        self.bind("<Leave>", self._quitter)
        self.bind("<Left>", lambda _e: self._decaler(-1))
        self.bind("<Right>", lambda _e: self._decaler(1))
        self.bind("<FocusIn>", lambda _e: self.redessiner())
        self.bind("<FocusOut>", lambda _e: self.redessiner())

    def redessiner(self, _evenement=None) -> None:
        onglets = self._notebook.tabs()
        self.delete("all")
        self._zones = []
        if not onglets:
            return
        textes = [self._notebook.tab(o, "text") for o in onglets]
        largeurs = [self._police.measure(t) + 2 * MARGE_ONGLET for t in textes]
        total = int(sum(largeurs) + 2 * MARGE_BARRE)
        self.configure(width=total)
        fond = photo(
            self,
            ("onglets-fond", total, COULEURS["surface"], COULEURS["bordure"]),
            lambda: rectangle_arrondi(
                total,
                HAUTEUR_BARRE,
                HAUTEUR_BARRE / 2,
                (COULEURS["surface"],),
                bordure=COULEURS["bordure"],
            ),
        )
        self.create_image(0, 0, anchor="nw", image=fond)
        actif = self._notebook.select()
        hauteur_pilule = HAUTEUR_BARRE - 2 * MARGE_BARRE
        x = float(MARGE_BARRE)
        for onglet, texte, largeur in zip(onglets, textes, largeurs, strict=True):
            self._zones.append((x, x + largeur, onglet))
            if str(onglet) == str(actif):
                largeur_i = int(largeur)
                pilule = photo(
                    self,
                    ("onglet-actif", largeur_i),
                    lambda largeur_i=largeur_i: rectangle_arrondi(
                        largeur_i, hauteur_pilule, hauteur_pilule / 2, tuple(DEGRADE_BOUTON)
                    ),
                )
                self.create_image(x, MARGE_BARRE, anchor="nw", image=pilule)
                couleur = "#FFFFFF"
            else:
                couleur = (
                    COULEURS["texte"]
                    if str(onglet) == self._survol
                    else COULEURS["texte_secondaire"]
                )
            self.create_text(
                x + largeur / 2, HAUTEUR_BARRE / 2, text=texte, fill=couleur, font=self._police
            )
            x += largeur

    def _onglet_sous(self, x: float) -> str | None:
        return next((o for debut, fin, o in self._zones if debut <= x < fin), None)

    def _cliquer(self, evenement) -> None:
        onglet = self._onglet_sous(evenement.x)
        if onglet is not None:
            self._notebook.select(onglet)
            self.focus_set()

    def _survoler(self, evenement) -> None:
        onglet = self._onglet_sous(evenement.x)
        if onglet != self._survol:
            self._survol = onglet
            self.redessiner()

    def _quitter(self, _evenement=None) -> None:
        if self._survol is not None:
            self._survol = None
            self.redessiner()

    def _decaler(self, pas: int) -> None:
        onglets = list(self._notebook.tabs())
        if not onglets:
            return
        index = onglets.index(self._notebook.select()) if self._notebook.select() in onglets else 0
        self._notebook.select(onglets[(index + pas) % len(onglets)])


class Onglets(ttk.Frame):
    """Barre de pilules + pages. S'utilise comme un ``ttk.Notebook`` (``add``, ``tabs``…)."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Page.TFrame")
        self._notebook = ttk.Notebook(self, style="Plat.TNotebook")
        self._barre = _BarreOnglets(self, self._notebook)
        self._barre.pack(anchor="w", pady=(0, 16))
        self._notebook.pack(fill="both", expand=True)
        self._notebook.bind("<<NotebookTabChanged>>", self._barre.redessiner, add="+")

    def add(self, enfant: tk.Widget, **options) -> None:
        self._notebook.add(enfant, **options)
        self.after_idle(self._barre.redessiner)

    def tabs(self) -> tuple[str, ...]:
        return self._notebook.tabs()

    def select(self, onglet=None):
        return self._notebook.select() if onglet is None else self._notebook.select(onglet)

    def index(self, onglet) -> int:
        return self._notebook.index(onglet)

    def tab(self, onglet, option=None, **options):
        return self._notebook.tab(onglet, option, **options)

    def bind(self, sequence=None, func=None, add=None):
        if sequence == "<<NotebookTabChanged>>":
            return self._notebook.bind(sequence, func, add)
        return super().bind(sequence, func, add)
