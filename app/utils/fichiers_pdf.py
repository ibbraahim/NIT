"""Écriture de rapports PDF simples (titre, sections, tableaux), en français.

Police DejaVu Sans embarquée (``ressources/polices``) : contrairement aux polices de base du
PDF, elle couvre tous les caractères typographiques français (guillemets « », œ, etc.).
"""

from __future__ import annotations

import threading
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import DOSSIER_POLICES

POLICE = "DejaVuSans"
POLICE_GRAS = "DejaVuSans-Bold"
_polices_enregistrees = False
#: reportlab n'est pas conçu pour être appelé depuis plusieurs fils à la fois (registre des
#: polices et des couleurs partagé, sans verrou côté bibliothèque) : les écritures de PDF
#: (lancées en tâche de fond, UC23) sont donc sérialisées ici.
_verrou = threading.Lock()


def _enregistrer_polices() -> None:
    global _polices_enregistrees
    if _polices_enregistrees:
        return
    pdfmetrics.registerFont(TTFont(POLICE, str(DOSSIER_POLICES / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(POLICE_GRAS, str(DOSSIER_POLICES / "DejaVuSans-Bold.ttf")))
    _polices_enregistrees = True


def ecrire_rapport_pdf(
    chemin: Path,
    titre: str,
    sous_titre: str,
    sections: list[tuple[str, list[str], list[list[str]]]],
) -> None:
    """Écrit un PDF : titre, sous-titre, puis une suite de sections ``(titre, en_tetes,
    lignes)`` rendues en tableau. Une section sans ligne affiche « Aucune donnée »."""
    with _verrou:
        _ecrire(chemin, titre, sous_titre, sections)


def _ecrire(
    chemin: Path,
    titre: str,
    sous_titre: str,
    sections: list[tuple[str, list[str], list[list[str]]]],
) -> None:
    _enregistrer_polices()
    chemin.parent.mkdir(parents=True, exist_ok=True)

    style_titre = ParagraphStyle(
        "Titre", fontName=POLICE_GRAS, fontSize=18, leading=22, spaceAfter=4
    )
    style_sous_titre = ParagraphStyle(
        "SousTitre", fontName=POLICE, fontSize=11, textColor=colors.grey, spaceAfter=16
    )
    style_section = ParagraphStyle(
        "Section", fontName=POLICE_GRAS, fontSize=13, spaceBefore=16, spaceAfter=6
    )
    style_vide = ParagraphStyle("Vide", fontName=POLICE, fontSize=10, textColor=colors.grey)

    elements = [
        Paragraph(_echapper(titre), style_titre),
        Paragraph(_echapper(sous_titre), style_sous_titre),
    ]
    for titre_section, en_tetes, lignes in sections:
        elements.append(Paragraph(_echapper(titre_section), style_section))
        if not lignes:
            elements.append(Paragraph("Aucune donnée.", style_vide))
            continue
        donnees = [en_tetes] + lignes
        tableau = Table(donnees, repeatRows=1, hAlign="LEFT")
        tableau.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), POLICE_GRAS),
                    ("FONTNAME", (0, 1), (-1, -1), POLICE),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6aa3")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d1dc")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f4f6f8")],
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(tableau)
        elements.append(Spacer(1, 4))

    document = SimpleDocTemplate(
        str(chemin),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=titre,
    )
    document.build(elements)


def _echapper(texte: str) -> str:
    """Échappe les caractères spéciaux XML de Platypus (les cellules de tableau le sont déjà
    par ``Table``, seuls les ``Paragraph`` en ont besoin)."""
    return texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
