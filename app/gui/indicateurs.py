"""Cases à cocher et boutons radio du nouveau design.

Le thème ttk « clam » dessine un indicateur de 10 pixels, trop petit et peu lisible. On le
remplace par de petites images (carré ou disque arrondi, coche blanche) générées avec PIL aux
couleurs du thème courant et branchées comme élément ttk ``image`` dans la disposition des
styles ``TCheckbutton`` et ``TRadiobutton``.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image

from app.gui.formes import photo, rectangle_arrondi
from app.gui.icones import icone_interface
from app.gui.style import COULEURS, theme_courant

TAILLE = 20


def _case(fond: str, bordure: str, coche: bool) -> Image.Image:
    image = rectangle_arrondi(TAILLE, TAILLE, 6, (fond,), bordure=bordure, epaisseur=1.4)
    if coche:
        image.alpha_composite(icone_interface("coche", "#FFFFFF", TAILLE))
    return image


def _radio(fond: str, bordure: str, point: bool) -> Image.Image:
    image = rectangle_arrondi(TAILLE, TAILLE, TAILLE / 2, (fond,), bordure=bordure, epaisseur=1.4)
    if point:
        centre = rectangle_arrondi(8, 8, 4, ("#FFFFFF",))
        image.alpha_composite(centre, ((TAILLE - 8) // 2, (TAILLE - 8) // 2))
    return image


#: (état, couleur de fond, couleur de bordure, coché) d'après la palette du thème courant.
def _etats() -> dict[str, tuple[str, str, bool]]:
    c = COULEURS
    return {
        "normal": (c["champ"], c["champ_bordure"], False),
        "survol": (c["champ"], c["accent"], False),
        "coche": (c["accent"], c["accent"], True),
        "inactif": (c["surface_2"], c["bordure"], False),
        "coche_inactif": (c["desactive"], c["desactive"], True),
    }


def _image_tk(racine: tk.Tk, genre: str, theme: str, etat: str) -> str:
    fond, bordure, marque = _etats()[etat]
    dessiner = _case if genre == "coche" else _radio
    return str(photo(racine, (genre, theme, etat), lambda: dessiner(fond, bordure, marque)))


def creer_indicateurs(racine: tk.Tk, style: ttk.Style) -> None:
    """Crée les éléments d'indicateur du thème courant et les branche aux deux styles."""
    theme = theme_courant()
    for genre, style_widget, famille in (
        ("coche", "TCheckbutton", "Checkbutton"),
        ("radio", "TRadiobutton", "Radiobutton"),
    ):
        nom = f"Workly.{genre}.{theme}"
        if nom not in style.element_names():
            images = {etat: _image_tk(racine, genre, theme, etat) for etat in _etats()}
            style.element_create(
                nom,
                "image",
                images["normal"],
                ("disabled", "selected", images["coche_inactif"]),
                ("disabled", images["inactif"]),
                ("selected", images["coche"]),
                ("active", images["survol"]),
                width=TAILLE + 4,
                sticky="w",
            )
        style.layout(
            style_widget,
            [
                (
                    f"{famille}.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            (nom, {"side": "left", "sticky": ""}),
                            (
                                f"{famille}.focus",
                                {
                                    "side": "left",
                                    "sticky": "",
                                    "children": [(f"{famille}.label", {"sticky": "nswe"})],
                                },
                            ),
                        ],
                    },
                )
            ],
        )
