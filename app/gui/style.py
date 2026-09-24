"""Feuille de style unique de l'interface (thème ttk « clam » personnalisé)."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

COULEURS = {
    "primaire": "#1f4e79",
    "primaire_clair": "#2f6aa3",
    "primaire_fonce": "#163a5a",
    "fond": "#f3f5f8",
    "surface": "#ffffff",
    "texte": "#1d2733",
    "texte_secondaire": "#5f6b7a",
    "bordure": "#c9d1dc",
    "selection": "#d6e4f2",
    "vert": "#2e7d32",
    "vert_clair": "#e3f1e4",
    "orange": "#e07b00",
    "orange_clair": "#fdebd3",
    "rouge": "#c62828",
    "rouge_clair": "#f9dcdc",
    "gris": "#8a8f98",
    "gris_clair": "#eceff3",
    "demo": "#fff1c2",
    "demo_texte": "#6b4e00",
    "desactive": "#a4acb6",
}

#: Couleur associée à chaque statut de KPI ou niveau d'alerte.
COULEURS_STATUT = {
    "vert": COULEURS["vert"],
    "orange": COULEURS["orange"],
    "rouge": COULEURS["rouge"],
    "gris": COULEURS["gris"],
    None: COULEURS["gris"],
}
COULEURS_STATUT_CLAIR = {
    "vert": COULEURS["vert_clair"],
    "orange": COULEURS["orange_clair"],
    "rouge": COULEURS["rouge_clair"],
    "gris": COULEURS["gris_clair"],
}

TAILLE_POLICE = 10


def famille_police(racine: tk.Misc) -> str:
    """Première police disponible parmi une liste de polices lisibles."""
    disponibles = set(tkfont.families(racine))
    for candidate in ("Segoe UI", "Helvetica Neue", "DejaVu Sans", "Liberation Sans", "Arial"):
        if candidate in disponibles:
            return candidate
    return tkfont.nametofont("TkDefaultFont").actual("family")


def appliquer_style(racine: tk.Tk) -> ttk.Style:
    """Configure le thème, les polices et tous les styles nommés de l'application."""
    famille = famille_police(racine)
    for nom in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(nom).configure(family=famille, size=TAILLE_POLICE)
    racine.configure(background=COULEURS["fond"])
    racine.option_add("*TCombobox*Listbox.font", (famille, TAILLE_POLICE))
    racine.option_add("*TCombobox*Listbox.selectBackground", COULEURS["primaire"])

    style = ttk.Style(racine)
    style.theme_use("clam")
    c = COULEURS
    style.configure(
        ".",
        background=c["fond"],
        foreground=c["texte"],
        font=(famille, TAILLE_POLICE),
        bordercolor=c["bordure"],
        focuscolor=c["primaire_clair"],
    )
    style.configure("TFrame", background=c["fond"])
    style.configure("Carte.TFrame", background=c["surface"], relief="solid", borderwidth=1)
    style.configure("Surface.TFrame", background=c["surface"], borderwidth=0)
    style.configure("TLabel", background=c["fond"], foreground=c["texte"])
    style.configure("Carte.TLabel", background=c["surface"])
    style.configure("Titre.TLabel", font=(famille, 16, "bold"), foreground=c["primaire_fonce"])
    style.configure("SousTitre.TLabel", font=(famille, 12, "bold"), foreground=c["primaire"])
    style.configure("Section.TLabel", font=(famille, 11, "bold"), foreground=c["texte"])
    style.configure("Aide.TLabel", foreground=c["texte_secondaire"], font=(famille, 9))
    style.configure("Erreur.TLabel", foreground=c["rouge"], font=(famille, 9))
    style.configure("Gras.TLabel", font=(famille, TAILLE_POLICE, "bold"))
    for statut in ("vert", "orange", "rouge", "gris"):
        style.configure(
            f"{statut.capitalize()}.TLabel",
            foreground=COULEURS_STATUT[statut],
            font=(famille, TAILLE_POLICE, "bold"),
        )

    # Bandeau supérieur
    style.configure("Bandeau.TFrame", background=c["primaire"])
    style.configure("Bandeau.TLabel", background=c["primaire"], foreground="#ffffff")
    style.configure(
        "BandeauTitre.TLabel",
        background=c["primaire"],
        foreground="#ffffff",
        font=(famille, 13, "bold"),
    )
    style.configure(
        "Bandeau.TButton",
        background=c["primaire_fonce"],
        foreground="#ffffff",
        bordercolor=c["primaire_fonce"],
        padding=(10, 4),
    )
    style.map("Bandeau.TButton", background=[("active", c["primaire_clair"])])
    style.configure("Demo.TFrame", background=c["demo"])
    style.configure(
        "Demo.TLabel",
        background=c["demo"],
        foreground=c["demo_texte"],
        font=(famille, TAILLE_POLICE, "bold"),
    )
    style.configure("Derive.TFrame", background=c["rouge_clair"])
    style.configure(
        "Derive.TLabel",
        background=c["rouge_clair"],
        foreground=c["rouge"],
        font=(famille, TAILLE_POLICE, "bold"),
    )

    # Barre d'état
    style.configure("Etat.TFrame", background=c["gris_clair"])
    style.configure(
        "Etat.TLabel",
        background=c["gris_clair"],
        foreground=c["texte_secondaire"],
        font=(famille, 9),
    )

    # Boutons
    style.configure("TButton", padding=(10, 4), background=c["surface"])
    style.map(
        "TButton",
        foreground=[("disabled", c["desactive"])],
        background=[("active", c["selection"]), ("disabled", c["gris_clair"])],
    )
    style.configure(
        "Primaire.TButton",
        background=c["primaire"],
        foreground="#ffffff",
        bordercolor=c["primaire"],
    )
    style.map(
        "Primaire.TButton",
        background=[("disabled", c["gris_clair"]), ("active", c["primaire_clair"])],
        foreground=[("disabled", c["desactive"])],
    )

    # Champs de saisie (normal et en erreur)
    style.configure("TEntry", fieldbackground=c["surface"], padding=3)
    style.configure(
        "Erreur.TEntry",
        fieldbackground="#fff6f6",
        bordercolor=c["rouge"],
        lightcolor=c["rouge"],
        darkcolor=c["rouge"],
    )
    style.configure("TCombobox", padding=3)
    style.map("TCombobox", fieldbackground=[("readonly", c["surface"])])
    style.configure(
        "Erreur.TCombobox", bordercolor=c["rouge"], lightcolor=c["rouge"], darkcolor=c["rouge"]
    )
    style.map("Erreur.TCombobox", fieldbackground=[("readonly", "#fff6f6")])
    style.configure(
        "Erreur.DateEntry",
        bordercolor=c["rouge"],
        lightcolor=c["rouge"],
        darkcolor=c["rouge"],
        fieldbackground="#fff6f6",
    )
    style.configure("TCheckbutton", background=c["fond"])
    style.configure("Carte.TCheckbutton", background=c["surface"])
    style.configure("TRadiobutton", background=c["fond"])

    # Onglets
    style.configure("TNotebook", background=c["fond"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 6))
    style.map(
        "TNotebook.Tab",
        background=[("selected", c["surface"])],
        foreground=[("selected", c["primaire"])],
    )

    # Tableaux
    style.configure(
        "Treeview",
        background=c["surface"],
        fieldbackground=c["surface"],
        rowheight=24,
        bordercolor=c["bordure"],
    )
    style.configure(
        "Treeview.Heading",
        font=(famille, TAILLE_POLICE, "bold"),
        background=c["gris_clair"],
        padding=(4, 4),
    )
    style.map(
        "Treeview",
        background=[("selected", c["primaire_clair"])],
        foreground=[("selected", "#ffffff")],
    )

    # Menu de navigation
    style.configure(
        "Navigation.Treeview",
        background=c["primaire_fonce"],
        fieldbackground=c["primaire_fonce"],
        foreground="#ffffff",
        rowheight=36,
        font=(famille, 11),
        borderwidth=0,
    )
    style.map("Navigation.Treeview", background=[("selected", c["primaire_clair"])])
    style.layout("Navigation.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Navigation.TFrame", background=c["primaire_fonce"])

    # Barres de progression
    style.configure("TProgressbar", background=c["primaire"], troughcolor=c["gris_clair"])
    return style
