"""Écriture de rapports PDF simples (titre, sections, tableaux), en français.

Police DejaVu Sans embarquée (``ressources/polices``) : contrairement aux polices de base du
PDF, elle couvre tous les caractères typographiques français (guillemets « », œ, etc.).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app import ACCROCHE
from app.config import DOSSIER_IMAGES, DOSSIER_POLICES

#: Couleur d'accent de marque Workly (milieu du dégradé — voir app.gui.style).
COULEUR_ACCENT_MARQUE = colors.HexColor("#4C6CF0")

#: Dégradé de marque à 5 accents (mêmes teintes que app.gui.style.COULEURS_DEGRADE_MARQUE,
#: dupliquées ici pour que ce module reste indépendant de Tkinter/app.gui).
COULEURS_DEGRADE_MARQUE = ["#22D3EE", "#2FA8F5", "#4C6CF0", "#7B4AE2", "#B24AE2"]

#: Palette des graphiques du rapport (réel, RL, RN — mêmes couleurs que l'écran Comparaison,
#: reprises ici en dur pour que ce module reste indépendant de Tkinter/app.gui).
COULEUR_REEL = "#1f4e79"
COULEUR_RL = "#e07b00"
COULEUR_RN = "#2e7d32"


@dataclass
class SectionRapport:
    """Une section du rapport : un titre, et l'un de ``texte`` (paragraphe ou puces), de
    ``tableau`` (en-têtes, lignes) ou d'``image`` (PNG, voir :func:`graphique_png`)."""

    titre: str
    texte: list[str] | None = None
    tableau: tuple[list[str], list[list[str]]] | None = None
    image: BytesIO | None = None


def graphique_png(dates: list[date], series: list[tuple[str, list[float], str]]) -> BytesIO:
    """PNG d'un graphique en ligne à plusieurs séries (rendu Agg, sans dépendance à Tkinter
    ni à un affichage : utilisable depuis les tâches automatiques comme depuis l'écran).

    ``series`` : liste de ``(libellé, valeurs, couleur)``, les valeurs manquantes étant
    ``float("nan")`` (laisse un trou dans la ligne plutôt que de la relier à tort)."""
    figure = Figure(figsize=(7.2, 3.2), dpi=130)
    axe = figure.add_subplot(111)
    for libelle_serie, valeurs, couleur in series:
        axe.plot(dates, valeurs, marker="o", markersize=3, color=couleur, label=libelle_serie)
    axe.set_ylabel("Heures")
    axe.legend(fontsize=8, loc="upper left")
    axe.tick_params(axis="x", labelrotation=30, labelsize=7)
    figure.tight_layout()
    tampon = BytesIO()
    FigureCanvasAgg(figure).print_png(tampon)
    tampon.seek(0)
    return tampon


def _barre_degradee(largeur: float, hauteur: float, etapes: int = 40) -> Table:
    """Barre en dégradé de marque à 5 accents : reportlab ne sait pas peindre un dégradé
    continu, on juxtapose donc ``etapes`` bandes de couleur interpolées (même principe que les
    « plusieurs teintes juxtaposées » évoqué dans app.gui.style pour les surfaces PDF)."""

    def _hex_vers_rgb(couleur: str) -> tuple[int, int, int]:
        couleur = couleur.lstrip("#")
        return tuple(int(couleur[i : i + 2], 16) for i in (0, 2, 4))

    def _couleur_a(t: float) -> colors.Color:
        segments = len(COULEURS_DEGRADE_MARQUE) - 1
        position = min(max(t, 0.0), 1.0) * segments
        indice = min(int(position), segments - 1)
        local = position - indice
        debut = _hex_vers_rgb(COULEURS_DEGRADE_MARQUE[indice])
        fin = _hex_vers_rgb(COULEURS_DEGRADE_MARQUE[indice + 1])
        rgb = tuple(debut[i] + (fin[i] - debut[i]) * local for i in range(3))
        return colors.Color(*(v / 255 for v in rgb))

    barre = Table(
        [[""] * etapes],
        colWidths=[largeur / etapes] * etapes,
        rowHeights=[hauteur],
        hAlign="CENTER",
    )
    barre.setStyle(
        TableStyle(
            [("BACKGROUND", (i, 0), (i, 0), _couleur_a(i / (etapes - 1))) for i in range(etapes)]
            + [
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return barre


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
    sections: list[SectionRapport],
) -> None:
    """Écrit un PDF : titre, sous-titre, puis une suite de :class:`SectionRapport` (texte,
    tableau ou image). Un tableau sans ligne, ou une image absente, affiche « Aucune
    donnée »."""
    with _verrou:
        _ecrire(chemin, titre, sous_titre, sections)


def _ecrire(
    chemin: Path,
    titre: str,
    sous_titre: str,
    sections: list[SectionRapport],
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
        *_page_de_garde(titre, sous_titre),
        Paragraph(_echapper(titre), style_titre),
        Paragraph(_echapper(sous_titre), style_sous_titre),
    ]
    style_puce = ParagraphStyle("Puce", fontName=POLICE, fontSize=10, leading=14)

    for section in sections:
        elements.append(Paragraph(_echapper(section.titre), style_section))
        if section.texte is not None:
            if not section.texte:
                elements.append(Paragraph("Aucune donnée.", style_vide))
                continue
            elements.append(
                ListFlowable(
                    [ListItem(Paragraph(_echapper(ligne), style_puce)) for ligne in section.texte],
                    bulletType="bullet",
                    leftIndent=14,
                )
            )
            elements.append(Spacer(1, 4))
            continue
        if section.image is not None:
            image = Image(section.image, width=17 * cm, height=17 * cm * 3.2 / 7.2)
            image.hAlign = "LEFT"
            elements.append(image)
            elements.append(Spacer(1, 4))
            continue
        en_tetes, lignes = section.tableau or ([], [])
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
                    ("BACKGROUND", (0, 0), (-1, 0), COULEUR_ACCENT_MARQUE),
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


def _page_de_garde(titre: str, sous_titre: str) -> list:
    """Page de garde Workly : logo, accroche, titre et sous-titre du rapport, sur sa propre
    page (avant le contenu, qui répète titre et sous-titre pour rester lisible seule)."""
    chemin_logo = DOSSIER_IMAGES / "logo_workly_horizontal.png"
    style_accroche = ParagraphStyle(
        "Accroche",
        fontName=POLICE,
        fontSize=12,
        textColor=COULEUR_ACCENT_MARQUE,
        alignment=TA_CENTER,
        spaceAfter=48,
    )
    style_titre_garde = ParagraphStyle(
        "TitreGarde",
        fontName=POLICE_GRAS,
        fontSize=22,
        leading=27,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    style_sous_titre_garde = ParagraphStyle(
        "SousTitreGarde",
        fontName=POLICE,
        fontSize=12,
        textColor=colors.grey,
        alignment=TA_CENTER,
    )
    elements: list = [Spacer(1, 5 * cm)]
    if chemin_logo.exists():
        image = Image(str(chemin_logo), width=8 * cm, height=4 * cm)
        image.hAlign = "CENTER"
        elements.append(image)
    elements.append(Spacer(1, 0.6 * cm))
    elements.append(Paragraph(_echapper(ACCROCHE), style_accroche))
    elements.append(_barre_degradee(9 * cm, 0.18 * cm))
    elements.append(Spacer(1, 0.9 * cm))
    elements.append(Paragraph(_echapper(titre), style_titre_garde))
    elements.append(Paragraph(_echapper(sous_titre), style_sous_titre_garde))
    elements.append(PageBreak())
    return elements


def _echapper(texte: str) -> str:
    """Échappe les caractères spéciaux XML de Platypus (les cellules de tableau le sont déjà
    par ``Table``, seuls les ``Paragraph`` en ont besoin)."""
    return texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
