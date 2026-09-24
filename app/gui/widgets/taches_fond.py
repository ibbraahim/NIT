"""Exécution des traitements longs dans un fil séparé, sans figer l'interface.

Une fenêtre modale affiche une barre de progression et, si le traitement le
permet, un bouton « Annuler ». Le résultat est transmis au fil de l'interface
par une file consultée périodiquement (``after``).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from app.erreurs import ErreurApplication, OperationAnnulee
from app.gui.widgets.dialogues import DialogueBase, afficher_erreur, informer
from app.journal import journal
from app.utils.progression import Progression

_log = journal(__name__)


class FenetreProgression(DialogueBase):
    """Fenêtre de progression (message, barre, bouton « Annuler » facultatif)."""

    def __init__(
        self, parent, titre: str, message: str, annulable: bool, progression: Progression
    ) -> None:
        super().__init__(parent, titre)
        self.progression = progression
        self.message = ttk.Label(self.corps, text=message, wraplength=420, width=60)
        self.message.pack(anchor="w")
        self.barre = ttk.Progressbar(self.corps, mode="indeterminate", length=420, maximum=100)
        self.barre.pack(fill="x", pady=(10, 0))
        self.barre.start(12)
        self._indeterminee = True
        self.bouton_annuler = None
        if annulable:
            self.bouton_annuler = self.ajouter_bouton("Annuler", self.demander_annulation)
        self.protocol("WM_DELETE_WINDOW", self.demander_annulation if annulable else lambda: None)
        self.unbind("<Escape>")

    def mettre_a_jour(self, fraction: float | None, texte: str) -> None:
        if texte:
            self.message.configure(text=texte)
        if fraction is None:
            return
        if self._indeterminee:
            self.barre.stop()
            self.barre.configure(mode="determinate")
            self._indeterminee = False
        self.barre["value"] = max(0.0, min(1.0, fraction)) * 100

    def demander_annulation(self) -> None:
        self.progression.annuler()
        self.message.configure(text="Annulation en cours…")
        if self.bouton_annuler is not None:
            self.bouton_annuler.state(["disabled"])


def executer_en_fond(
    parent: tk.Misc,
    traitement: Callable[[Progression], object],
    sur_succes: Callable[[object], None] | None = None,
    titre: str = "Traitement en cours",
    message: str = "Veuillez patienter…",
    annulable: bool = False,
    message_succes: str | None = None,
    sur_fin: Callable[[], None] | None = None,
) -> None:
    """Lance ``traitement(progression)`` dans un fil et affiche sa progression.

    Les erreurs sont affichées en français ; la trace va dans le journal.
    """
    file: queue.Queue = queue.Queue()
    progression = Progression(lambda f, t: file.put(("progression", f, t)))
    fenetre = FenetreProgression(parent, titre, message, annulable, progression)
    fenetre.update_idletasks()
    maitre = parent.winfo_toplevel()
    fenetre.geometry(
        f"+{maitre.winfo_rootx() + max((maitre.winfo_width() - fenetre.winfo_reqwidth()) // 2, 0)}"
        f"+{maitre.winfo_rooty() + max((maitre.winfo_height() - fenetre.winfo_reqheight()) // 3, 0)}"
    )
    fenetre.deiconify()
    try:
        fenetre.grab_set()
    except tk.TclError:
        pass

    def travailler() -> None:
        try:
            file.put(("succes", traitement(progression), None))
        except BaseException as exc:  # noqa: BLE001 - transmis au fil de l'interface
            file.put(("erreur", exc, None))

    def terminer() -> None:
        try:
            fenetre.grab_release()
        except tk.TclError:
            pass
        fenetre.destroy()
        if sur_fin is not None:
            sur_fin()

    def consulter() -> None:
        try:
            while True:
                genre, valeur, texte = file.get_nowait()
                if genre == "progression":
                    fenetre.mettre_a_jour(valeur, texte)
                    continue
                terminer()
                if genre == "succes":
                    if sur_succes is not None:
                        sur_succes(valeur)
                    if message_succes:
                        informer(parent, message_succes)
                elif isinstance(valeur, OperationAnnulee):
                    informer(parent, valeur.message)
                elif isinstance(valeur, ErreurApplication):
                    afficher_erreur(parent, valeur.message)
                else:
                    _log.error(
                        "Erreur inattendue dans un traitement long : %r", valeur, exc_info=valeur
                    )
                    afficher_erreur(
                        parent,
                        "Le traitement a échoué de façon inattendue. "
                        "Consultez le journal de l'application.",
                    )
                return
        except queue.Empty:
            pass
        fenetre.after(100, consulter)

    threading.Thread(target=travailler, name=f"traitement-{titre}", daemon=True).start()
    fenetre.after(100, consulter)
