"""Champs de formulaire avec libellé, validation et message d'erreur sous le champ.

Un champ en erreur est encadré en rouge et affiche son message en dessous.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from datetime import date
from tkinter import ttk

from app.gui.style import COULEURS
from app.utils.format_fr import formater_date, formater_nombre, lire_date, lire_nombre


class Champ(ttk.Frame):
    """Base : libellé au-dessus, widget de saisie, message d'erreur en dessous."""

    style_normal = "TEntry"
    style_erreur = "Erreur.TEntry"

    def __init__(self, parent, libelle: str, aide: str = "", **options) -> None:
        sur_carte = options.pop("style_cadre", "TFrame") in ("Carte.TFrame", "Surface.TFrame")
        super().__init__(parent, style="Surface.TFrame" if sur_carte else "TFrame")
        fond = {"background": COULEURS["surface"]} if sur_carte else {}
        self.libelle = libelle
        self.etiquette = ttk.Label(self, text=libelle, **fond)
        self.etiquette.grid(row=0, column=0, sticky="w")
        self.saisie = self._creer_saisie(**options)
        self.saisie.grid(row=1, column=0, sticky="we", pady=(2, 0))
        self.message = ttk.Label(self, text=aide, style="Aide.TLabel", wraplength=320, **fond)
        self._aide = aide
        self.message.grid(row=2, column=0, sticky="w")
        self.columnconfigure(0, weight=1)

    def _creer_saisie(self, **options) -> tk.Widget:  # pragma: no cover - abstraite
        raise NotImplementedError

    def signaler_erreur(self, message: str) -> None:
        """Encadre le champ en rouge et affiche le message sous le champ."""
        self.saisie.configure(style=self.style_erreur)
        self.message.configure(text=message, style="Erreur.TLabel")

    def effacer_erreur(self) -> None:
        """Rétablit l'apparence normale du champ."""
        self.saisie.configure(style=self.style_normal)
        self.message.configure(text=self._aide, style="Aide.TLabel")

    def activer(self, actif: bool) -> None:
        """Active ou grise la saisie."""
        self.saisie.state(["!disabled"] if actif else ["disabled"])

    def focus(self) -> None:
        self.saisie.focus_set()


class ChampTexte(Champ):
    """Saisie d'une ligne de texte (``masque=True`` pour un mot de passe)."""

    def _creer_saisie(self, largeur: int = 28, masque: bool = False, **options) -> tk.Widget:
        self.variable = tk.StringVar()
        return ttk.Entry(
            self, textvariable=self.variable, width=largeur, show="•" if masque else "", **options
        )

    def valeur(self) -> str:
        return self.variable.get().strip()

    def definir(self, valeur) -> None:
        self.variable.set("" if valeur is None else str(valeur))

    def vider(self) -> None:
        self.variable.set("")


class ChampNombre(ChampTexte):
    """Saisie d'un nombre au format français (virgule décimale)."""

    def _creer_saisie(self, largeur: int = 12, decimales: int = 2, **options) -> tk.Widget:
        self.decimales = decimales
        return super()._creer_saisie(largeur=largeur, justify="right", **options)

    def valeur(self) -> str:
        """Texte brut saisi (la conversion est faite par le service, qui la valide)."""
        return self.variable.get().strip()

    def valeur_nombre(self) -> float | None:
        """Valeur convertie, ou ``None`` si la saisie est vide ou invalide."""
        try:
            return lire_nombre(self.variable.get()) if self.variable.get().strip() else None
        except ValueError:
            return None

    def definir(self, valeur) -> None:
        if valeur is None or valeur == "":
            self.variable.set("")
        elif isinstance(valeur, (int, float)):
            self.variable.set(formater_nombre(valeur, self.decimales, supprimer_zeros=True))
        else:
            self.variable.set(str(valeur))


class ChampListe(Champ):
    """Liste déroulante non modifiable ; ``options`` = [(valeur, libellé), …]."""

    style_normal = "TCombobox"
    style_erreur = "Erreur.TCombobox"

    def _creer_saisie(self, options: Sequence[tuple] = (), largeur: int = 26) -> tk.Widget:
        self.variable = tk.StringVar()
        liste = ttk.Combobox(self, textvariable=self.variable, state="readonly", width=largeur)
        self._liste = liste
        self.definir_options(options)
        return liste

    def definir_options(self, options: Sequence[tuple], conserver: bool = True) -> None:
        """Remplace les choix proposés (en conservant la sélection si elle existe encore)."""
        ancienne = self.valeur() if conserver and hasattr(self, "_choix") else None
        self._choix = list(options)
        self._liste.configure(values=[libelle for _v, libelle in self._choix])
        if ancienne is not None and any(v == ancienne for v, _l in self._choix):
            self.definir(ancienne)
        elif self._choix:
            self.variable.set(self._choix[0][1])
        else:
            self.variable.set("")

    def valeur(self):
        libelle = self.variable.get()
        for valeur, texte in getattr(self, "_choix", []):
            if texte == libelle:
                return valeur
        return None

    def definir(self, valeur) -> None:
        for v, texte in self._choix:
            if v == valeur:
                self.variable.set(texte)
                return

    def activer(self, actif: bool) -> None:
        self.saisie.configure(state="readonly" if actif else "disabled")

    def sur_changement(self, rappel) -> None:
        """Appelle ``rappel()`` quand l'utilisateur change la sélection."""
        self._liste.bind("<<ComboboxSelected>>", lambda _e: rappel(), add="+")


class ChampDate(Champ):
    """Sélecteur de date (tkcalendar, locale ``fr_FR``, format JJ/MM/AAAA)."""

    style_normal = "DateEntry"
    style_erreur = "Erreur.DateEntry"

    def _creer_saisie(self, largeur: int = 12) -> tk.Widget:
        from tkcalendar import DateEntry

        return DateEntry(
            self,
            width=largeur,
            locale="fr_FR",
            date_pattern="dd/MM/yyyy",
            firstweekday="monday",
            showweeknumbers=False,
        )

    def valeur(self) -> date:
        """Date saisie ; lève ``ValueError`` (message français) si elle est invalide."""
        return lire_date(self.saisie.get())

    def definir(self, valeur: date) -> None:
        self.saisie.set_date(valeur)

    def texte(self) -> str:
        return self.saisie.get()

    def sur_changement(self, rappel) -> None:
        self.saisie.bind("<<DateEntrySelected>>", lambda _e: rappel(), add="+")
        self.saisie.bind("<FocusOut>", lambda _e: rappel(), add="+")


class ChampCase(ttk.Frame):
    """Case à cocher avec la même interface que les autres champs."""

    def __init__(self, parent, libelle: str, valeur: bool = False, **options) -> None:
        sur_carte = options.pop("style_cadre", "TFrame") in ("Carte.TFrame", "Surface.TFrame")
        super().__init__(parent, style="Surface.TFrame" if sur_carte else "TFrame")
        self.variable = tk.BooleanVar(value=valeur)
        style = "Carte.TCheckbutton" if sur_carte else "TCheckbutton"
        self.saisie = ttk.Checkbutton(self, text=libelle, variable=self.variable, style=style)
        self.saisie.grid(row=0, column=0, sticky="w", pady=(16, 0))
        fond = {"background": COULEURS["surface"]} if sur_carte else {}
        self.message = ttk.Label(self, text="", style="Erreur.TLabel", **fond)
        self.message.grid(row=1, column=0, sticky="w")

    def valeur(self) -> bool:
        return bool(self.variable.get())

    def definir(self, valeur: bool) -> None:
        self.variable.set(bool(valeur))

    def signaler_erreur(self, message: str) -> None:
        self.message.configure(text=message)

    def effacer_erreur(self) -> None:
        self.message.configure(text="")

    def activer(self, actif: bool) -> None:
        self.saisie.state(["!disabled"] if actif else ["disabled"])


class ChampTexteLong(ttk.Frame):
    """Zone de texte sur plusieurs lignes (commentaires, actions menées)."""

    def __init__(
        self, parent, libelle: str, hauteur: int = 4, largeur: int = 50, aide: str = ""
    ) -> None:
        super().__init__(parent)
        ttk.Label(self, text=libelle).grid(row=0, column=0, sticky="w")
        self.saisie = tk.Text(
            self,
            height=hauteur,
            width=largeur,
            wrap="word",
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightcolor="#2f6aa3",
        )
        self.saisie.grid(row=1, column=0, sticky="nsew", pady=(2, 0))
        self._aide = aide
        self.message = ttk.Label(self, text=aide, style="Aide.TLabel", wraplength=420)
        self.message.grid(row=2, column=0, sticky="w")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

    def valeur(self) -> str:
        return self.saisie.get("1.0", "end").strip()

    def definir(self, valeur: str) -> None:
        self.saisie.delete("1.0", "end")
        self.saisie.insert("1.0", valeur or "")

    def signaler_erreur(self, message: str) -> None:
        self.saisie.configure(highlightbackground="#c62828", highlightcolor="#c62828")
        self.message.configure(text=message, style="Erreur.TLabel")

    def effacer_erreur(self) -> None:
        self.saisie.configure(highlightbackground="#c9d1dc", highlightcolor="#2f6aa3")
        self.message.configure(text=self._aide, style="Aide.TLabel")

    def focus(self) -> None:
        self.saisie.focus_set()


def appliquer_erreurs(champs: dict[str, object], erreurs: dict[str, str]) -> None:
    """Efface les erreurs précédentes puis signale celles de ``erreurs`` (clé = nom du champ)."""
    for nom, champ in champs.items():
        champ.effacer_erreur()
        if nom in erreurs:
            champ.signaler_erreur(erreurs[nom])
    premier = next((champs[n] for n in champs if n in erreurs), None)
    if premier is not None and hasattr(premier, "focus"):
        premier.focus()


def formater_date_champ(valeur: date | None) -> str:
    """Date au format du champ (JJ/MM/AAAA)."""
    return formater_date(valeur) if valeur else ""
