"""Tableau (``ttk.Treeview``) triable par clic sur l'en-tête de colonne."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from tkinter import ttk

from app.gui.style import COULEURS, COULEURS_STATUT_CLAIR
from app.utils.format_fr import formater_date, formater_date_heure, formater_nombre


@dataclass
class Colonne:
    """Description d'une colonne : clé dans les lignes, titre, largeur, format."""

    cle: str
    titre: str
    largeur: int = 110
    alignement: str = "w"
    formateur: Callable[[object], str] | None = None
    etirable: bool = True


def _texte(valeur, formateur) -> str:
    if formateur is not None:
        return formateur(valeur)
    if valeur is None:
        return "—"
    if isinstance(valeur, bool):
        return "Oui" if valeur else "Non"
    if isinstance(valeur, datetime):
        return formater_date_heure(valeur)
    if isinstance(valeur, date):
        return formater_date(valeur)
    if isinstance(valeur, float):
        return formater_nombre(valeur, 2, supprimer_zeros=True)
    if isinstance(valeur, int):
        return formater_nombre(valeur, 0)
    return str(valeur)


def _cle_tri(valeur):
    """Clé de tri homogène : les valeurs vides en dernier, nombres, dates puis texte."""
    if valeur is None:
        return (2, 0, "")
    if isinstance(valeur, bool):
        return (0, int(valeur), "")
    if isinstance(valeur, (int, float)):
        return (0, float(valeur), "")
    if isinstance(valeur, datetime):
        return (0, valeur.timestamp(), "")
    if isinstance(valeur, date):
        return (0, valeur.toordinal(), "")
    try:
        return (0, float(valeur), "")
    except (TypeError, ValueError):
        return (1, 0, str(valeur).lower())


class TableauTriable(ttk.Frame):
    """Tableau avec barres de défilement, tri par en-tête et couleurs de ligne.

    Les lignes sont des dictionnaires ; la clé ``cle_id`` sert d'identifiant.
    Une ligne peut porter une clé ``_parent`` (identifiant de la ligne parente)
    pour afficher une arborescence (sites → zones).
    """

    ETIQUETTES = {
        "rouge": {"background": COULEURS_STATUT_CLAIR["rouge"]},
        "orange": {"background": COULEURS_STATUT_CLAIR["orange"]},
        "vert": {"background": COULEURS_STATUT_CLAIR["vert"]},
        "gris": {"foreground": COULEURS["gris"]},
        "inactif": {"foreground": COULEURS["desactive"]},
        "gras": {"font": ("", 10, "bold")},
    }

    def __init__(
        self,
        parent,
        colonnes: list[Colonne],
        hauteur: int = 12,
        selection_multiple: bool = False,
        arborescence: bool = False,
        largeur_arbre: int = 220,
        titre_arbre: str = "",
    ) -> None:
        super().__init__(parent)
        self.colonnes = colonnes
        self._lignes: dict[str, dict] = {}
        self._tri: tuple[str, bool] | None = None
        self.arborescence = arborescence
        self.arbre = ttk.Treeview(
            self,
            columns=[c.cle for c in colonnes],
            show="tree headings" if arborescence else "headings",
            height=hauteur,
            selectmode="extended" if selection_multiple else "browse",
        )
        if arborescence:
            self.arbre.heading("#0", text=titre_arbre, command=lambda: self.trier("#0"))
            self.arbre.column("#0", width=largeur_arbre, stretch=True)
        for colonne in colonnes:
            self.arbre.heading(
                colonne.cle, text=colonne.titre, command=lambda c=colonne.cle: self.trier(c)
            )
            self.arbre.column(
                colonne.cle,
                width=colonne.largeur,
                anchor=colonne.alignement,
                stretch=colonne.etirable,
                minwidth=40,
            )
        for nom, options in self.ETIQUETTES.items():
            self.arbre.tag_configure(nom, **options)
        defil_v = ttk.Scrollbar(self, orient="vertical", command=self.arbre.yview)
        defil_h = ttk.Scrollbar(self, orient="horizontal", command=self.arbre.xview)
        self.arbre.configure(yscrollcommand=defil_v.set, xscrollcommand=defil_h.set)
        self.arbre.grid(row=0, column=0, sticky="nsew")
        defil_v.grid(row=0, column=1, sticky="ns")
        defil_h.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.message_vide = ttk.Label(self, text="", style="Aide.TLabel")

    # --- Chargement -------------------------------------------------------
    def charger(
        self,
        lignes: list[dict],
        cle_id: str = "id",
        etiquettes: Callable[[dict], tuple[str, ...] | str | None] | None = None,
        texte_arbre: Callable[[dict], str] | None = None,
        message_vide: str = "Aucune donnée à afficher.",
    ) -> None:
        """Remplace le contenu du tableau (la sélection est conservée si possible)."""
        selection = set(self.arbre.selection())
        ouverts = {
            iid for iid in self._lignes if self.arbre.exists(iid) and self.arbre.item(iid, "open")
        }
        self.arbre.delete(*self.arbre.get_children())
        self._lignes.clear()
        for ligne in lignes:
            iid = str(ligne[cle_id])
            parent = str(ligne["_parent"]) if ligne.get("_parent") is not None else ""
            if parent and not self.arbre.exists(parent):
                parent = ""
            tags = etiquettes(ligne) if etiquettes else None
            if isinstance(tags, str):
                tags = (tags,)
            self.arbre.insert(
                parent,
                "end",
                iid=iid,
                text=texte_arbre(ligne) if texte_arbre else "",
                values=[_texte(ligne.get(c.cle), c.formateur) for c in self.colonnes],
                tags=tags or (),
                open=iid in ouverts or not ouverts,
            )
            self._lignes[iid] = ligne
        if self._tri is not None:
            cle, decroissant = self._tri
            self._appliquer_tri(cle, decroissant)
        conserver = [iid for iid in selection if self.arbre.exists(iid)]
        if conserver:
            self.arbre.selection_set(conserver)
        if lignes:
            self.message_vide.place_forget()
        else:
            self.message_vide.configure(text=message_vide)
            self.message_vide.place(relx=0.5, rely=0.5, anchor="center")

    # --- Tri --------------------------------------------------------------
    def trier(self, cle: str) -> None:
        """Trie sur la colonne ``cle`` ; un second clic inverse l'ordre."""
        decroissant = self._tri is not None and self._tri[0] == cle and not self._tri[1]
        self._tri = (cle, decroissant)
        self._appliquer_tri(cle, decroissant)

    def _appliquer_tri(self, cle: str, decroissant: bool) -> None:
        def valeur(iid: str):
            ligne = self._lignes.get(iid, {})
            if cle == "#0":
                return self.arbre.item(iid, "text")
            return ligne.get(cle)

        def trier_niveau(parent: str) -> None:
            enfants = list(self.arbre.get_children(parent))
            enfants.sort(key=lambda iid: _cle_tri(valeur(iid)), reverse=decroissant)
            for position, iid in enumerate(enfants):
                self.arbre.move(iid, parent, position)
                trier_niveau(iid)

        trier_niveau("")
        for colonne in self.colonnes:
            fleche = (" ▼" if decroissant else " ▲") if colonne.cle == cle else ""
            self.arbre.heading(colonne.cle, text=colonne.titre + fleche)

    # --- Sélection --------------------------------------------------------
    def ligne_selectionnee(self) -> dict | None:
        selection = self.arbre.selection()
        return self._lignes.get(selection[0]) if selection else None

    def lignes_selectionnees(self) -> list[dict]:
        return [self._lignes[iid] for iid in self.arbre.selection() if iid in self._lignes]

    def selectionner(self, identifiant) -> None:
        iid = str(identifiant)
        if self.arbre.exists(iid):
            self.arbre.selection_set(iid)
            self.arbre.see(iid)

    def lignes(self) -> list[dict]:
        return list(self._lignes.values())

    def sur_selection(self, rappel: Callable[[], None]) -> None:
        self.arbre.bind("<<TreeviewSelect>>", lambda _e: rappel(), add="+")

    def sur_double_clic(self, rappel: Callable[[dict], None]) -> None:
        def _gerer(evenement) -> None:
            iid = self.arbre.identify_row(evenement.y)
            if iid and iid in self._lignes:
                rappel(self._lignes[iid])

        self.arbre.bind("<Double-1>", _gerer, add="+")
