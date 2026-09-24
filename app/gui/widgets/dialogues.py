"""Boîtes de dialogue personnalisées, entièrement en français.

Elles remplacent ``tkinter.messagebox`` (dont les boutons suivent la langue du
système) : boutons « Oui », « Non », « Annuler », « Fermer », « Enregistrer ».
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, ttk

from app.erreurs import DonneesInvalides, ErreurApplication
from app.gui.style import COULEURS
from app.gui.widgets.champs import appliquer_erreurs
from app.journal import journal

_log = journal(__name__)

ICONES = {"information": "ℹ", "question": "?", "erreur": "✖", "avertissement": "⚠"}
COULEURS_ICONES = {
    "information": COULEURS["primaire"],
    "question": COULEURS["primaire"],
    "erreur": COULEURS["rouge"],
    "avertissement": COULEURS["orange"],
}


class DialogueBase(tk.Toplevel):
    """Fenêtre modale centrée sur son parent ; ``resultat`` est renvoyé à la fermeture."""

    def __init__(self, parent: tk.Misc, titre: str, redimensionnable: bool = False) -> None:
        super().__init__(parent)
        self.withdraw()
        self.title(titre)
        self.configure(background=COULEURS["fond"])
        self.resizable(redimensionnable, redimensionnable)
        maitre = parent.winfo_toplevel()
        self.transient(maitre)
        self.resultat = None
        self.protocol("WM_DELETE_WINDOW", self.fermer)
        self.bind("<Escape>", lambda _e: self.fermer())
        self.corps = ttk.Frame(self, padding=16)
        self.corps.pack(fill="both", expand=True)
        self.barre_boutons = ttk.Frame(self, padding=(16, 0, 16, 14))
        self.barre_boutons.pack(fill="x", side="bottom")

    def ajouter_bouton(
        self, texte: str, commande: Callable[[], None], primaire: bool = False, defaut: bool = False
    ) -> ttk.Button:
        bouton = ttk.Button(
            self.barre_boutons,
            text=texte,
            command=commande,
            style="Primaire.TButton" if primaire else "TButton",
        )
        bouton.pack(side="right", padx=(8, 0))
        if defaut:
            self.bind("<Return>", lambda _e: commande())
            bouton.focus_set()
        return bouton

    def afficher(self):
        """Affiche la fenêtre de façon modale et attend sa fermeture."""
        self.update_idletasks()
        maitre = self.master.winfo_toplevel()
        largeur, hauteur = self.winfo_reqwidth(), self.winfo_reqheight()
        x = maitre.winfo_rootx() + max((maitre.winfo_width() - largeur) // 2, 0)
        y = maitre.winfo_rooty() + max((maitre.winfo_height() - hauteur) // 3, 0)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()
        return self.resultat

    def fermer(self, resultat=None) -> None:
        self.resultat = resultat
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class DialogueMessage(DialogueBase):
    """Message avec icône et boutons choisis parmi Oui / Non / Annuler / Fermer."""

    def __init__(
        self,
        parent,
        titre: str,
        message: str,
        genre: str = "information",
        boutons: tuple[tuple[str, object], ...] = (("Fermer", None),),
        details: str = "",
    ) -> None:
        super().__init__(parent, titre)
        ttk.Label(
            self.corps,
            text=ICONES.get(genre, ""),
            font=("", 22, "bold"),
            foreground=COULEURS_ICONES.get(genre),
        ).grid(row=0, column=0, sticky="n", padx=(0, 14))
        ttk.Label(self.corps, text=message, wraplength=440, justify="left").grid(
            row=0, column=1, sticky="w"
        )
        if details:
            ttk.Label(
                self.corps, text=details, style="Aide.TLabel", wraplength=440, justify="left"
            ).grid(row=1, column=1, sticky="w", pady=(8, 0))
        # Les boutons sont empilés de droite à gauche : on les ajoute en ordre inverse.
        for index, (texte, valeur) in enumerate(reversed(boutons)):
            self.ajouter_bouton(
                texte,
                lambda v=valeur: self.fermer(v),
                primaire=index == len(boutons) - 1,
                defaut=index == len(boutons) - 1,
            )


def informer(parent, message: str, titre: str = "Information", details: str = "") -> None:
    """Message d'information (bouton « Fermer »)."""
    DialogueMessage(parent, titre, message, "information", details=details).afficher()


def avertir(parent, message: str, titre: str = "Attention") -> None:
    """Message d'avertissement (bouton « Fermer »)."""
    DialogueMessage(parent, titre, message, "avertissement").afficher()


def afficher_erreur(parent, message: str, titre: str = "Erreur") -> None:
    """Message d'erreur en français (bouton « Fermer »)."""
    DialogueMessage(parent, titre, message, "erreur").afficher()


def confirmer(parent, message: str, titre: str = "Confirmation", details: str = "") -> bool:
    """Question fermée : « Oui » (vrai) ou « Non » (faux)."""
    resultat = DialogueMessage(
        parent, titre, message, "question", (("Oui", True), ("Non", False)), details
    ).afficher()
    return bool(resultat)


def demander_oui_non_annuler(parent, message: str, titre: str = "Confirmation") -> bool | None:
    """« Oui » (vrai), « Non » (faux) ou « Annuler » (``None``)."""
    return DialogueMessage(
        parent, titre, message, "question", (("Oui", True), ("Non", False), ("Annuler", None))
    ).afficher()


class DialogueSaisieTexte(DialogueBase):
    """Saisie d'un texte (commentaire, action menée) avec « Enregistrer » / « Annuler »."""

    def __init__(
        self,
        parent,
        titre: str,
        libelle: str,
        obligatoire: bool = True,
        valeur: str = "",
        message: str = "",
    ) -> None:
        super().__init__(parent, titre, redimensionnable=True)
        from app.gui.widgets.champs import ChampTexteLong

        if message:
            ttk.Label(self.corps, text=message, wraplength=460, justify="left").pack(
                anchor="w", pady=(0, 8)
            )
        self.champ = ChampTexteLong(self.corps, libelle, hauteur=5, largeur=56)
        self.champ.definir(valeur)
        self.champ.pack(fill="both", expand=True)
        self.obligatoire = obligatoire
        self.ajouter_bouton("Annuler", lambda: self.fermer(None))
        self.ajouter_bouton("Enregistrer", self._valider, primaire=True)
        self.champ.focus()

    def _valider(self) -> None:
        texte = self.champ.valeur()
        if self.obligatoire and not texte:
            self.champ.signaler_erreur("Ce champ est obligatoire.")
            return
        self.fermer(texte)


def saisir_texte(
    parent, titre: str, libelle: str, obligatoire: bool = True, valeur: str = "", message: str = ""
) -> str | None:
    """Retourne le texte saisi, ou ``None`` si l'utilisateur annule."""
    return DialogueSaisieTexte(parent, titre, libelle, obligatoire, valeur, message).afficher()


class DialogueFormulaire(DialogueBase):
    """Formulaire générique « Enregistrer » / « Annuler ».

    ``construire(corps)`` crée les champs et retourne ``{nom: champ}`` ;
    ``enregistrer(valeurs)`` appelle le service. Une :class:`DonneesInvalides`
    encadre en rouge les champs fautifs ; toute autre erreur est affichée.
    """

    def __init__(
        self,
        parent,
        titre: str,
        construire: Callable[[ttk.Frame], dict[str, object]],
        enregistrer: Callable[[dict], object],
        valeurs: dict | None = None,
    ) -> None:
        super().__init__(parent, titre)
        self.champs = construire(self.corps)
        for nom, valeur in (valeurs or {}).items():
            if nom in self.champs and valeur is not None and hasattr(self.champs[nom], "definir"):
                self.champs[nom].definir(valeur)
        self.message_general = ttk.Label(self.corps, text="", style="Erreur.TLabel", wraplength=460)
        self.message_general.grid(row=99, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self._enregistrer = enregistrer
        self.ajouter_bouton("Annuler", lambda: self.fermer(None))
        self.ajouter_bouton("Enregistrer", self._valider, primaire=True)
        premier = next(iter(self.champs.values()), None)
        if premier is not None and hasattr(premier, "focus"):
            premier.focus()

    def valeurs(self) -> dict:
        return {nom: champ.valeur() for nom, champ in self.champs.items()}

    def _valider(self) -> None:
        try:
            valeurs = self.valeurs()
        except ValueError as exc:
            self.message_general.configure(text=str(exc))
            return
        try:
            resultat = self._enregistrer(valeurs)
        except DonneesInvalides as exc:
            appliquer_erreurs(self.champs, exc.erreurs)
            self.message_general.configure(text=exc.message)
            return
        except ErreurApplication as exc:
            appliquer_erreurs(self.champs, {})
            self.message_general.configure(text=exc.message)
            return
        except Exception as exc:  # noqa: BLE001 - message français, trace au journal
            _log.exception("Erreur inattendue dans un formulaire : %s", exc)
            self.message_general.configure(
                text="Erreur inattendue. Consultez le journal de l'application."
            )
            return
        self.fermer(resultat if resultat is not None else True)


# ---------------------------------------------------------------------
# Sélecteurs de fichiers (textes Tk francisés via msgcat)
# ---------------------------------------------------------------------
TYPES_IMPORT = [
    ("Fichiers CSV ou Excel", "*.csv *.xlsx"),
    ("Fichiers CSV", "*.csv"),
    ("Classeurs Excel", "*.xlsx"),
    ("Tous les fichiers", "*"),
]


def franciser_tk(racine: tk.Misc) -> None:
    """Passe les textes internes de Tk (sélecteurs de fichiers) en français."""
    try:
        racine.tk.call("package", "require", "msgcat")
        racine.tk.call("::msgcat::mclocale", "fr")
    except tk.TclError:
        _log.warning("Impossible de passer les boîtes de fichiers Tk en français.")


def choisir_fichier_a_ouvrir(
    parent, titre: str = "Choisir un fichier", types=TYPES_IMPORT
) -> Path | None:
    chemin = filedialog.askopenfilename(parent=parent, title=titre, filetypes=types)
    return Path(chemin) if chemin else None


def choisir_fichier_a_enregistrer(
    parent,
    nom_propose: str,
    titre: str = "Enregistrer sous",
    types=None,
    dossier: Path | None = None,
) -> Path | None:
    extension = Path(nom_propose).suffix
    types = types or [(f"Fichiers {extension.upper().lstrip('.')}", f"*{extension}")]
    chemin = filedialog.asksaveasfilename(
        parent=parent,
        title=titre,
        initialfile=nom_propose,
        defaultextension=extension,
        filetypes=types,
        initialdir=str(dossier) if dossier else None,
    )
    return Path(chemin) if chemin else None


def executer_action(parent, action: Callable[[], object], succes: str | None = None):
    """Exécute un appel de service ; affiche l'erreur en français s'il échoue.

    Retourne le résultat de l'action, ou ``None`` en cas d'erreur.
    """
    try:
        resultat = action()
    except ErreurApplication as exc:
        afficher_erreur(parent, exc.message)
        return None
    except Exception as exc:  # noqa: BLE001 - message français, trace au journal
        _log.exception("Erreur inattendue : %s", exc)
        afficher_erreur(
            parent,
            "Une erreur inattendue s'est produite. " "Consultez le journal de l'application.",
        )
        return None
    if succes:
        informer(parent, succes)
    return resultat if resultat is not None else True
