"""Tableau (``ttk.Treeview``) triable par clic sur l'en-tête de colonne."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from tkinter import ttk

from app.gui.degrades import melanger
from app.gui.style import COULEURS, COULEURS_STATUT, COULEURS_STATUT_CLAIR, a_chaque_theme
from app.utils.format_fr import formater_date, formater_date_heure, formater_nombre

#: Étape de pulsation (toutes les ~800 ms) des lignes taguées « rouge » (alertes ouvertes
#: critiques) : un ton médian entre le fond pâle habituel et le rouge plein, pour une pulsation
#: perceptible mais douce, jamais agressive.
_ROUGE_PULSATION: list[str] = [""]
_DELAI_PULSATION_MS = 800

#: Étiquettes de ligne : le fond pâle donne la lecture d'ensemble ; le texte (donc la puce « ● »
#: ajoutée devant le statut par les écrans appelants) reprend la couleur pleine du statut, un
#: Treeview ne sachant colorer qu'un seul aplat de texte par ligne (pas de couleur par caractère).
ETIQUETTES: dict[str, dict] = {}


@a_chaque_theme
def _etiquettes_du_theme() -> None:
    _ROUGE_PULSATION[0] = melanger(COULEURS_STATUT_CLAIR["rouge"], COULEURS_STATUT["rouge"], 0.25)
    ETIQUETTES.clear()
    for statut in ("rouge", "orange", "vert"):
        ETIQUETTES[statut] = {
            "background": COULEURS_STATUT_CLAIR[statut],
            "foreground": COULEURS_STATUT[statut],
        }
    ETIQUETTES["gris"] = {"foreground": COULEURS["gris"]}
    ETIQUETTES["inactif"] = {"foreground": COULEURS["desactive"]}
    ETIQUETTES["gras"] = {"font": ("", 10, "bold")}


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

    ETIQUETTES = ETIQUETTES

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
        self.arbre.configure(
            yscrollcommand=self._defilement_auto(defil_v, "ns", 0, 1),
            xscrollcommand=self._defilement_auto(defil_h, "ew", 1, 0),
        )
        self.arbre.grid(row=0, column=0, sticky="nsew")
        defil_v.grid(row=0, column=1, sticky="ns")
        defil_h.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.message_vide = ttk.Label(self, text="", style="Aide.TLabel")
        self._pulsation_allumee = False
        self._id_pulsation: str | None = None
        self.bind("<Destroy>", self._arreter_pulsation, add="+")
        self._pulser()

    @staticmethod
    def _defilement_auto(barre: ttk.Scrollbar, cote: str, ligne: int, colonne: int):
        """Commande de défilement qui masque la barre tant que tout le contenu est visible."""

        def _commande(debut: str, fin: str) -> None:
            barre.set(debut, fin)
            if float(debut) <= 0.0 and float(fin) >= 1.0:
                barre.grid_remove()
            else:
                barre.grid(row=ligne, column=colonne, sticky=cote)

        return _commande

    # --- Pulsation des alertes rouges ---------------------------------------
    def _pulser(self) -> None:
        """Fait alterner doucement, toutes les ~800 ms, le fond des lignes taguées « rouge »
        (alertes ouvertes critiques) entre son ton pâle habituel et un ton médian plus soutenu
        — attire l'œil sans clignotement agressif."""
        if not self.arbre.winfo_exists():
            return
        self._pulsation_allumee = not self._pulsation_allumee
        couleur = _ROUGE_PULSATION[0] if self._pulsation_allumee else COULEURS_STATUT_CLAIR["rouge"]
        self.arbre.tag_configure("rouge", background=couleur)
        self._id_pulsation = self.after(_DELAI_PULSATION_MS, self._pulser)

    def _arreter_pulsation(self, _evenement=None) -> None:
        if self._id_pulsation is not None:
            self.after_cancel(self._id_pulsation)
            self._id_pulsation = None

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
