"""Cartes d'indicateurs : carte « héros » en dégradé et carte statistique sobre."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from app.gui.formes import carte_hero, photo, rectangle_arrondi
from app.gui.style import DEGRADE_HERO_CYAN, DEGRADE_HERO_ROSE
from app.gui.widgets.bouton import couleur_fond
from app.gui.widgets.carte import Carte
from app.gui.widgets.pastille import Pastille

DEGRADES_HEROS = {"rose": DEGRADE_HERO_ROSE, "cyan": DEGRADE_HERO_CYAN}
HAUTEUR_HERO = 132
HAUTEUR_HERO_ETROITE = 156
#: En dessous de cette largeur, la pastille passe sous le détail au lieu de s'y accoler.
LARGEUR_ETROITE = 270


class CarteHero(tk.Canvas):
    """Carte d'indicateur en dégradé : titre, grande valeur, détail, et une pastille de statut
    translucide. Elle s'étire en largeur : le fond est redessiné à la taille réelle."""

    def __init__(
        self,
        parent: tk.Misc,
        titre: str,
        valeur: str,
        detail: str = "",
        statut_libelle: str = "",
        degrade: str = "rose",
    ) -> None:
        super().__init__(
            parent,
            height=HAUTEUR_HERO,
            highlightthickness=0,
            borderwidth=0,
            background=couleur_fond(parent),
        )
        self._titre, self._valeur, self._detail = titre, valeur, detail
        self._statut = statut_libelle
        self._degrade = tuple(DEGRADES_HEROS[degrade])
        base = tkfont.nametofont("TkDefaultFont")
        self._police_titre = tkfont.Font(root=self, font=base)
        self._police_titre.configure(weight="bold", size=10)
        self._police_valeur = tkfont.Font(root=self, font=base)
        self._police_valeur.configure(weight="bold", size=26)
        self._police_petite = tkfont.Font(root=self, font=base)
        self._police_petite.configure(size=9)
        self._police_pastille = tkfont.Font(root=self, font=base)
        self._police_pastille.configure(weight="bold", size=9)
        self.bind("<Configure>", self._dessiner)

    @staticmethod
    def _tronquer(police: tkfont.Font, texte: str, largeur_max: float) -> str:
        if police.measure(texte) <= largeur_max:
            return texte
        while texte and police.measure(texte + "…") > largeur_max:
            texte = texte[:-1]
        return texte.rstrip() + "…"

    def _dessiner(self, _evenement=None) -> None:
        largeur = self.winfo_width()
        if largeur < 40:
            return
        etroite = largeur < LARGEUR_ETROITE
        hauteur_min = HAUTEUR_HERO_ETROITE if etroite else HAUTEUR_HERO
        if int(float(self.cget("height"))) != hauteur_min:
            self.configure(height=hauteur_min)
        hauteur = max(self.winfo_height(), hauteur_min)
        utile = largeur - 44
        self.delete("all")
        image = photo(
            self,
            ("hero", largeur, hauteur, self._degrade),
            lambda: carte_hero(largeur, hauteur, 18, self._degrade),
        )
        self.create_image(0, 0, anchor="nw", image=image)
        # Le titre passe à la ligne plutôt que d'être tronqué.
        self.create_text(
            22,
            17,
            text=self._titre,
            anchor="nw",
            width=utile,
            fill="#FFFFFF",
            font=self._police_titre,
        )
        # La valeur rétrécit plutôt que de déborder de la carte.
        taille = 26
        self._police_valeur.configure(size=taille)
        while taille > 14 and self._police_valeur.measure(self._valeur) > utile:
            taille -= 1
            self._police_valeur.configure(size=taille)
        self.create_text(
            22,
            76 if etroite else 66,
            text=self._valeur,
            anchor="w",
            fill="#FFFFFF",
            font=self._police_valeur,
        )
        libelle = f"● {self._statut}" if self._statut else ""
        largeur_p = self._police_pastille.measure(libelle) + 24 if libelle else 0
        sous = (
            etroite or self._police_petite.measure(self._detail) + largeur_p + 16 > utile
            if self._detail
            else False
        )
        y_detail = hauteur - 50 if sous else hauteur - 26
        if self._detail:
            self.create_text(
                22,
                y_detail,
                text=self._tronquer(self._police_petite, self._detail, utile),
                anchor="w",
                fill="#F1EAFF",
                font=self._police_petite,
            )
        if libelle:
            voile = photo(
                self,
                ("hero-voile", largeur_p),
                lambda: rectangle_arrondi(largeur_p, 24, 12, ("#FFFFFF",), 0.0, None, 1.0, 0.24),
            )
            if sous:
                x_droit, y_pastille = 22 + largeur_p, hauteur - 24
            else:
                x_droit, y_pastille = largeur - 18, y_detail
            self.create_image(x_droit, y_pastille, anchor="e", image=voile)
            self.create_text(
                x_droit - largeur_p / 2,
                y_pastille,
                text=libelle,
                fill="#FFFFFF",
                font=self._police_pastille,
            )


def carte_stat(
    parent: tk.Misc,
    titre: str,
    valeur: str,
    detail: str = "",
    statut: str | None = None,
    statut_libelle: str = "",
) -> Carte:
    """Carte d'indicateur sobre : titre discret, grande valeur, détail et pastille de statut."""
    carte = Carte(parent, marge=16)
    etiquette_titre = ttk.Label(carte.zone, text=titre, style="KpiTitre.TLabel", justify="left")
    etiquette_titre.pack(anchor="w", fill="x")
    ttk.Label(carte.zone, text=valeur, style="KpiValeur.TLabel").pack(anchor="w", pady=(6, 2))
    bas = ttk.Frame(carte.zone)
    bas.pack(fill="x", pady=(2, 0))
    etiquette_detail = ttk.Label(bas, text=detail, style="Aide.TLabel") if detail else None
    pastille = Pastille(bas, statut_libelle, statut) if statut_libelle else None
    etat = {"sous": None}

    def _ranger(_evenement=None) -> None:
        """Le titre passe à la ligne et la pastille descend sous le détail quand la carte est étroite."""
        largeur = carte.zone.winfo_width()
        if largeur < 40:
            return
        etiquette_titre.configure(wraplength=largeur)
        if etiquette_detail is None or pastille is None:
            sous = False
        else:
            sous = etiquette_detail.winfo_reqwidth() + pastille.winfo_reqwidth() + 10 > largeur
        if sous == etat["sous"]:
            return
        etat["sous"] = sous
        for widget in (etiquette_detail, pastille):
            if widget is not None:
                widget.pack_forget()
        if sous:
            if etiquette_detail is not None:
                etiquette_detail.pack(anchor="w")
            if pastille is not None:
                pastille.pack(anchor="w", pady=(6, 0))
        else:
            if etiquette_detail is not None:
                etiquette_detail.pack(side="left")
            if pastille is not None:
                pastille.pack(side="right")

    carte.zone.bind("<Configure>", _ranger)
    return carte
