"""Feuille de style unique de l'interface : deux thèmes (sombre et clair), un seul moteur.

La palette est un dictionnaire *modifiable sur place* (``COULEURS``) : changer de thème le
remplit avec l'autre jeu de valeurs sans que les modules qui l'ont importé aient à le
savoir. Les structures construites à partir de la palette au moment de l'import (couleurs de
séries, étiquettes de tableau…) s'inscrivent avec ``@a_chaque_theme`` pour être recalculées.
Un changement de thème en cours de session se fait donc en trois temps : ``definir_theme``,
``appliquer_style``, puis reconstruction de l'espace de travail.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont
from tkinter import ttk

from app.gui import preferences

#: Thème sombre : navy profond, cartes légèrement plus claires, textes bleutés. Il reprend
#: l'ambiance de l'identité Workly (fond navy du logo, accents néon du dégradé).
_SOMBRE = {
    "fond": "#0C1124",
    "barre": "#090D1C",
    "surface": "#141A33",
    "surface_2": "#1B2242",
    "bordure": "#242C52",
    "champ": "#0F1530",
    "champ_bordure": "#2B3461",
    "texte": "#F2F4FF",
    "texte_secondaire": "#93A0C9",
    "desactive": "#5A6594",
    "primaire": "#7C93FF",
    "primaire_clair": "#3DB8FF",
    "primaire_fonce": "#F2F4FF",
    "accent": "#7C93FF",
    "selection": "#222C5E",
    "infobulle": "#232C58",
    "barre_texte": "#AEB8DE",
    "barre_actif": "#1E2754",
    "barre_survol": "#131A3B",
    "vert": "#34D399",
    "vert_clair": "#0F2E2B",
    "orange": "#FBB13C",
    "orange_clair": "#33270F",
    "rouge": "#FB7185",
    "rouge_clair": "#3A1527",
    "rouge_tres_clair": "#2A1120",
    "gris": "#93A0C9",
    "gris_clair": "#1B2242",
    "demo": "#33290F",
    "demo_texte": "#F5D27A",
}

#: Thème clair : cartes blanches sur fond gris-bleu très pâle, accent indigo de la marque.
_CLAIR = {
    "fond": "#F3F5FB",
    "barre": "#FFFFFF",
    "surface": "#FFFFFF",
    "surface_2": "#F1F3FC",
    "bordure": "#E4E8F6",
    "champ": "#FFFFFF",
    "champ_bordure": "#D5DBF0",
    "texte": "#1A2044",
    "texte_secondaire": "#6B7394",
    "desactive": "#A9B0CC",
    "primaire": "#4C6CF0",
    "primaire_clair": "#2FA8F5",
    "primaire_fonce": "#1A2044",
    "accent": "#4C6CF0",
    "selection": "#E8EDFF",
    "infobulle": "#EEF1FE",
    "barre_texte": "#6B7394",
    "barre_actif": "#E8EDFF",
    "barre_survol": "#F1F3FC",
    "vert": "#2FA36B",
    "vert_clair": "#E3F6EC",
    "orange": "#D98A1C",
    "orange_clair": "#FCEFD9",
    "rouge": "#DC4F5D",
    "rouge_clair": "#FCE6E9",
    "rouge_tres_clair": "#FEF1F3",
    "gris": "#7F88A8",
    "gris_clair": "#EEF0F9",
    "demo": "#FFF3D6",
    "demo_texte": "#7A5B12",
}

THEMES: dict[str, dict[str, str]] = {"sombre": _SOMBRE, "clair": _CLAIR}
THEME_PAR_DEFAUT = "sombre"

#: Palette courante (remplie par :func:`definir_theme`). Le sens des couleurs de statut
#: (vert = bon, orange = attention, rouge = problème) est un repère métier : il ne change
#: pas d'un thème à l'autre, seule sa luminosité s'adapte au fond.
COULEURS: dict[str, str] = {}
COULEURS_STATUT: dict[str | None, str] = {}
COULEURS_STATUT_CLAIR: dict[str, str] = {}

#: Identité de marque Workly : fond navy (deux profondeurs) de l'écran de connexion, de
#: « À propos » et de la page de garde des rapports ; dégradé à 5 accents (froid → chaud) pour
#: les boutons principaux, les cartes « héros » et les éléments actifs. Ces couleurs ne
#: dépendent pas du thème.
COULEUR_FOND_MARQUE = "#0A1128"
COULEUR_FOND_MARQUE_PROFOND = "#070C1C"
COULEUR_ACCENT_1 = "#22D3EE"  # cyan
COULEUR_ACCENT_2 = "#2FA8F5"  # bleu ciel
COULEUR_ACCENT_3 = "#4C6CF0"  # bleu indigo
COULEUR_ACCENT_4 = "#7B4AE2"  # violet
COULEUR_ACCENT_5 = "#B24AE2"  # magenta
#: Les 5 accents, du froid au chaud : le dégradé de marque complet.
COULEURS_DEGRADE_MARQUE = [
    COULEUR_ACCENT_1,
    COULEUR_ACCENT_2,
    COULEUR_ACCENT_3,
    COULEUR_ACCENT_4,
    COULEUR_ACCENT_5,
]
#: Dégradés des cartes « héros » du tableau de bord (rose → violet, cyan → indigo).
DEGRADE_HERO_ROSE = ["#E05AE6", "#7B4AE2"]
DEGRADE_HERO_CYAN = [COULEUR_ACCENT_1, COULEUR_ACCENT_3]
#: Teinte représentative du dégradé, là où un aplat est obligatoire (ttk, PDF, Excel).
COULEUR_ACCENT = COULEUR_ACCENT_3

#: Puce devant le texte de statut dans les tableaux : Tk ne rend pas les émojis couleur dans
#: un Treeview, la couleur vient donc de la couleur de texte de la ligne (tag « vert »,
#: « orange », « rouge » de TableauTriable), pas du glyphe lui-même.
PUCE_STATUT = "●"

TAILLE_POLICE = 10

_theme_courant = THEME_PAR_DEFAUT
_abonnes: list[Callable[[], None]] = []


def theme_courant() -> str:
    """Nom du thème actif (``sombre`` ou ``clair``)."""
    return _theme_courant


def a_chaque_theme(fonction: Callable[[], None]) -> Callable[[], None]:
    """Décorateur : ``fonction`` est appelée tout de suite, puis à chaque changement de thème."""
    _abonnes.append(fonction)
    fonction()
    return fonction


def definir_theme(nom: str) -> None:
    """Active le thème ``nom`` (remplit la palette sur place et prévient les abonnés)."""
    global _theme_courant
    if nom not in THEMES:
        nom = THEME_PAR_DEFAUT
    _theme_courant = nom
    palette = THEMES[nom]
    COULEURS.clear()
    COULEURS.update(palette)
    COULEURS_STATUT.clear()
    COULEURS_STATUT.update(
        {
            "vert": palette["vert"],
            "orange": palette["orange"],
            "rouge": palette["rouge"],
            "gris": palette["gris"],
            None: palette["gris"],
        }
    )
    COULEURS_STATUT_CLAIR.clear()
    COULEURS_STATUT_CLAIR.update(
        {
            "vert": palette["vert_clair"],
            "orange": palette["orange_clair"],
            "rouge": palette["rouge_clair"],
            "gris": palette["gris_clair"],
        }
    )
    for abonne in _abonnes:
        abonne()


def basculer_theme() -> str:
    """Passe d'un thème à l'autre, mémorise le choix et retourne le nouveau thème."""
    nouveau = "clair" if _theme_courant == "sombre" else "sombre"
    definir_theme(nouveau)
    preferences.ecrire("theme", nouveau)
    return nouveau


definir_theme(str(preferences.lire().get("theme", THEME_PAR_DEFAUT)))


def famille_police(racine: tk.Misc) -> str:
    """Première police disponible parmi une liste de polices lisibles."""
    disponibles = set(tkfont.families(racine))
    for candidate in ("Segoe UI", "Helvetica Neue", "DejaVu Sans", "Liberation Sans", "Arial"):
        if candidate in disponibles:
            return candidate
    return tkfont.nametofont("TkDefaultFont").actual("family")


def appliquer_style(racine: tk.Tk) -> ttk.Style:
    """Configure le thème ttk, les polices et tous les styles nommés pour le thème courant.

    Règle de fond : les widgets ttk sont par défaut sur une *surface* (fond des cartes) ; le
    fond de page, derrière les cartes, s'obtient avec les styles ``Page.*``.
    """
    famille = famille_police(racine)
    for nom in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(nom).configure(family=famille, size=TAILLE_POLICE)
    c = COULEURS
    racine.configure(background=c["fond"])
    for motif, valeur in {
        "*TCombobox*Listbox.font": (famille, TAILLE_POLICE),
        "*TCombobox*Listbox.background": c["champ"],
        "*TCombobox*Listbox.foreground": c["texte"],
        "*TCombobox*Listbox.selectBackground": c["selection"],
        "*TCombobox*Listbox.selectForeground": c["texte"],
        "*TCombobox*Listbox.borderWidth": 0,
        "*TCombobox*Listbox.relief": "flat",
        "*Menu.background": c["surface"],
        "*Menu.foreground": c["texte"],
        "*Menu.activeBackground": c["selection"],
        "*Menu.activeForeground": c["texte"],
        "*Menu.relief": "flat",
        "*Menu.borderWidth": 0,
        "*Text.background": c["champ"],
        "*Text.foreground": c["texte"],
        "*Text.insertBackground": c["texte"],
        "*Text.selectBackground": c["selection"],
        "*Text.selectForeground": c["texte"],
    }.items():
        racine.option_add(motif, valeur)

    style = ttk.Style(racine)
    style.theme_use("clam")
    style.configure(
        ".",
        background=c["surface"],
        foreground=c["texte"],
        font=(famille, TAILLE_POLICE),
        bordercolor=c["bordure"],
        lightcolor=c["surface"],
        darkcolor=c["surface"],
        troughcolor=c["surface_2"],
        focuscolor=c["accent"],
        selectbackground=c["selection"],
        selectforeground=c["texte"],
        insertcolor=c["texte"],
        fieldbackground=c["champ"],
    )

    # Cadres : surface (intérieur des cartes) par défaut, « Page » pour le fond de l'écran.
    style.configure("TFrame", background=c["surface"])
    style.configure("Page.TFrame", background=c["fond"])
    style.configure("Carte.TFrame", background=c["surface"], borderwidth=0)
    style.configure("Surface.TFrame", background=c["surface"], borderwidth=0)
    style.configure("Interne.TFrame", background=c["surface_2"], borderwidth=0)

    # Étiquettes
    style.configure("TLabel", background=c["surface"], foreground=c["texte"])
    style.configure("Page.TLabel", background=c["fond"])
    style.configure("Carte.TLabel", background=c["surface"])
    style.configure("Titre.TLabel", font=(famille, 16, "bold"), foreground=c["texte"])
    style.configure(
        "PageTitre.TLabel",
        background=c["fond"],
        font=(famille, 20, "bold"),
        foreground=c["texte"],
    )
    style.configure(
        "PageSousTitre.TLabel",
        background=c["fond"],
        font=(famille, 10),
        foreground=c["texte_secondaire"],
    )
    style.configure("SousTitre.TLabel", font=(famille, 12, "bold"), foreground=c["accent"])
    style.configure("Section.TLabel", font=(famille, 11, "bold"), foreground=c["texte"])
    style.configure("Aide.TLabel", foreground=c["texte_secondaire"], font=(famille, 9))
    style.configure(
        "PageAide.TLabel",
        background=c["fond"],
        foreground=c["texte_secondaire"],
        font=(famille, 9),
    )
    style.configure(
        "KpiTitre.TLabel",
        foreground=c["texte_secondaire"],
        font=(famille, 9, "bold"),
    )
    style.configure("KpiValeur.TLabel", foreground=c["texte"], font=(famille, 22, "bold"))
    style.configure("Erreur.TLabel", foreground=c["rouge"], font=(famille, 9))
    style.configure("Gras.TLabel", font=(famille, TAILLE_POLICE, "bold"))
    style.configure("Gagnant.TLabel", foreground=c["vert"], font=(famille, TAILLE_POLICE, "bold"))
    for statut in ("vert", "orange", "rouge", "gris"):
        style.configure(
            f"{statut.capitalize()}.TLabel",
            foreground=COULEURS_STATUT[statut],
            font=(famille, TAILLE_POLICE, "bold"),
        )

    # Bandeau supérieur (conservé jusqu'à la nouvelle coque) et écrans de marque (connexion,
    # À propos) : toujours sur le fond navy de la marque.
    style.configure("Bandeau.TFrame", background=COULEUR_FOND_MARQUE)
    style.configure("Bandeau.TLabel", background=COULEUR_FOND_MARQUE, foreground="#ffffff")
    style.configure(
        "BandeauTitre.TLabel",
        background=COULEUR_FOND_MARQUE,
        foreground="#ffffff",
        font=(famille, 15, "bold"),
    )
    style.configure(
        "BandeauRepere.TLabel",
        background=COULEUR_FOND_MARQUE,
        foreground=COULEUR_ACCENT_2,
        font=(famille, 9),
    )
    style.configure(
        "Bandeau.TButton",
        background=COULEUR_ACCENT_3,
        foreground="#ffffff",
        bordercolor=COULEUR_ACCENT_3,
        padding=(10, 4),
    )
    style.map("Bandeau.TButton", background=[("active", COULEUR_ACCENT_4)])
    style.configure("Marque.TFrame", background=COULEUR_FOND_MARQUE)
    style.configure(
        "MarqueTitre.TLabel",
        background=COULEUR_FOND_MARQUE,
        foreground="#ffffff",
        font=(famille, 22, "bold"),
    )
    style.configure(
        "MarqueAccroche.TLabel",
        background=COULEUR_FOND_MARQUE,
        foreground=COULEUR_ACCENT_2,
        font=(famille, 11),
    )
    style.configure(
        "MarqueAide.TLabel",
        background=COULEUR_FOND_MARQUE,
        foreground="#9aa4c2",
        font=(famille, 9),
    )
    style.configure(
        "MarqueEtiquette.TLabel",
        background=COULEUR_FOND_MARQUE,
        foreground="#ffffff",
        font=(famille, TAILLE_POLICE),
    )

    # Bandeaux d'information
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
    style.configure("Etat.TFrame", background=c["fond"])
    style.configure(
        "Etat.TLabel",
        background=c["fond"],
        foreground=c["texte_secondaire"],
        font=(famille, 9),
    )

    # Boutons de repli (les boutons de l'application sont des widgets dédiés, voir bouton.py)
    style.configure(
        "TButton",
        padding=(16, 8),
        background=c["surface_2"],
        foreground=c["texte"],
        bordercolor=c["bordure"],
        lightcolor=c["surface_2"],
        darkcolor=c["surface_2"],
        relief="flat",
    )
    style.map(
        "TButton",
        foreground=[("disabled", c["desactive"])],
        background=[("active", c["selection"]), ("disabled", c["surface_2"])],
        bordercolor=[("focus", c["accent"])],
    )
    style.configure(
        "Primaire.TButton",
        background=COULEUR_ACCENT_3,
        foreground="#ffffff",
        bordercolor=COULEUR_ACCENT_3,
        lightcolor=COULEUR_ACCENT_3,
        darkcolor=COULEUR_ACCENT_3,
    )
    style.map(
        "Primaire.TButton",
        background=[("disabled", c["surface_2"]), ("active", COULEUR_ACCENT_4)],
        foreground=[("disabled", c["desactive"])],
    )

    # Champs de saisie (normal et en erreur) : plats, bordure discrète, bordure d'accent au focus
    plat = {
        "fieldbackground": c["champ"],
        "foreground": c["texte"],
        "bordercolor": c["champ_bordure"],
        "lightcolor": c["champ"],
        "darkcolor": c["champ"],
        "insertcolor": c["texte"],
        "padding": 6,
    }
    en_focus = {
        "bordercolor": [("focus", c["accent"]), ("hover", c["desactive"])],
        "lightcolor": [("focus", c["accent"])],
        "darkcolor": [("focus", c["accent"])],
    }
    style.configure("TEntry", **plat)
    style.map("TEntry", **en_focus)
    style.configure(
        "Marque.TEntry",
        fieldbackground="#16204a",
        foreground="#ffffff",
        insertcolor="#ffffff",
        bordercolor=COULEUR_ACCENT_3,
        lightcolor="#16204a",
        darkcolor="#16204a",
        padding=3,
    )
    style.configure(
        "Erreur.TEntry",
        fieldbackground=c["rouge_tres_clair"],
        bordercolor=c["rouge"],
        lightcolor=c["rouge"],
        darkcolor=c["rouge"],
    )
    style.configure(
        "TCombobox",
        **plat,
        background=c["surface_2"],
        arrowcolor=c["texte_secondaire"],
        arrowsize=14,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["champ"]), ("disabled", c["surface_2"])],
        foreground=[("disabled", c["desactive"])],
        background=[("active", c["selection"])],
        selectbackground=[("readonly", c["champ"])],
        selectforeground=[("readonly", c["texte"])],
        **en_focus,
    )
    style.configure(
        "Erreur.TCombobox", bordercolor=c["rouge"], lightcolor=c["rouge"], darkcolor=c["rouge"]
    )
    style.map("Erreur.TCombobox", fieldbackground=[("readonly", c["rouge_tres_clair"])])
    style.configure(
        "Erreur.DateEntry",
        bordercolor=c["rouge"],
        lightcolor=c["rouge"],
        darkcolor=c["rouge"],
        fieldbackground=c["rouge_tres_clair"],
    )
    for nom in ("TCheckbutton", "Carte.TCheckbutton", "TRadiobutton"):
        style.configure(
            nom,
            background=c["surface"],
            foreground=c["texte"],
            focuscolor=c["surface"],
            indicatorbackground=c["champ"],
            indicatorforeground="#FFFFFF",
            upperbordercolor=c["champ_bordure"],
            lowerbordercolor=c["champ_bordure"],
            indicatorcolor=c["champ"],
        )
        style.map(
            nom,
            indicatorbackground=[("selected", c["accent"]), ("!selected", c["champ"])],
            indicatorcolor=[("selected", c["accent"]), ("!selected", c["champ"])],
            upperbordercolor=[("selected", c["accent"])],
            lowerbordercolor=[("selected", c["accent"])],
            background=[("active", c["surface"])],
        )
    style.configure("TSeparator", background=c["bordure"])

    # Onglets : le bandeau natif est masqué, la barre de pilules (widgets/onglets.py) le remplace
    style.layout("Plat.TNotebook.Tab", [])
    style.configure(
        "Plat.TNotebook",
        background=c["fond"],
        borderwidth=0,
        bordercolor=c["fond"],
        lightcolor=c["fond"],
        darkcolor=c["fond"],
        tabmargins=(0, 0, 0, 0),
    )
    style.configure("TNotebook", background=c["fond"], borderwidth=0, tabmargins=(0, 0, 0, 0))

    # Tableaux : lignes aérées, en-tête discret, sélection teintée d'accent
    style.configure(
        "Treeview",
        background=c["surface"],
        fieldbackground=c["surface"],
        foreground=c["texte"],
        rowheight=34,
        bordercolor=c["surface"],
        lightcolor=c["surface"],
        darkcolor=c["surface"],
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        font=(famille, 9, "bold"),
        background=c["surface_2"],
        foreground=c["texte_secondaire"],
        bordercolor=c["surface_2"],
        lightcolor=c["surface_2"],
        darkcolor=c["surface_2"],
        relief="flat",
        padding=(8, 8),
    )
    style.map("Treeview.Heading", background=[("active", c["selection"])])
    style.map(
        "Treeview",
        background=[("selected", c["selection"])],
        foreground=[("selected", c["texte"])],
    )

    # Ancien menu de navigation (remplacé par la barre latérale)
    style.configure(
        "Navigation.Treeview",
        background=c["barre"],
        fieldbackground=c["barre"],
        foreground=c["barre_texte"],
        rowheight=36,
        font=(famille, 11),
        borderwidth=0,
    )
    style.map("Navigation.Treeview", background=[("selected", c["barre_actif"])])
    style.layout("Navigation.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Navigation.TFrame", background=c["barre"])

    # Barres de défilement fines, sans flèches
    for sens, cote in (("Vertical", "ns"), ("Horizontal", "we")):
        style.layout(
            f"{sens}.TScrollbar",
            [
                (
                    f"{sens}.Scrollbar.trough",
                    {
                        "children": [
                            (f"{sens}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})
                        ],
                        "sticky": cote,
                    },
                )
            ],
        )
    style.configure(
        "TScrollbar",
        background=c["bordure"],
        troughcolor=c["surface"],
        bordercolor=c["surface"],
        lightcolor=c["bordure"],
        darkcolor=c["bordure"],
        relief="flat",
        arrowsize=11,
        gripcount=0,
    )
    style.map("TScrollbar", background=[("pressed", c["accent"]), ("active", c["desactive"])])

    # Barres de progression
    style.configure(
        "TProgressbar",
        background=COULEUR_ACCENT_3,
        troughcolor=c["surface_2"],
        bordercolor=c["surface_2"],
        lightcolor=COULEUR_ACCENT_3,
        darkcolor=COULEUR_ACCENT_3,
        thickness=8,
    )
    from app.gui.indicateurs import creer_indicateurs

    creer_indicateurs(racine, style)
    return style
