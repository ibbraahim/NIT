"""Fenêtre de résultat d'un import de fichier (UC04/UC05), commune aux deux onglets.

Affiche les lignes valides, rejetées et les avertissements ; boutons « Enregistrer les
lignes valides », « Exporter le rapport d'erreurs », « Annuler ».
"""

from __future__ import annotations

from pathlib import Path
from tkinter import ttk

from app.gui.widgets.bouton import Bouton
from app.gui.widgets.dialogues import (
    DialogueBase,
    afficher_erreur,
    choisir_fichier_a_enregistrer,
    informer,
)
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.services.donnees import exporter_rapport_erreurs
from app.services.qualite import ResultatControleQualite


class DialogueResultatImport(DialogueBase):
    """Fenêtre de résultat d'un import ; ``resultat`` est ``"enregistrer"`` ou ``None``."""

    def __init__(
        self,
        parent,
        titre: str,
        resultat: ResultatControleQualite,
        colonnes_valides: list[Colonne],
        nom_fichier_erreurs: str,
    ) -> None:
        super().__init__(parent, titre, redimensionnable=True)
        self.controle = resultat
        self.nom_fichier_erreurs = nom_fichier_erreurs

        ttk.Label(
            self.corps,
            style="Section.TLabel",
            text=f"{len(resultat.valides)} ligne(s) valide(s) · {len(resultat.rejets)} "
            f"rejetée(s) · {len(resultat.avertissements)} avertissement(s)",
        ).pack(anchor="w", pady=(0, 8))

        onglets = ttk.Notebook(self.corps)
        onglets.pack(fill="both", expand=True)

        cadre_valides = ttk.Frame(onglets, padding=8)
        onglets.add(cadre_valides, text=f"Lignes valides ({len(resultat.valides)})")
        tableau_valides = TableauTriable(cadre_valides, colonnes_valides, hauteur=14)
        tableau_valides.pack(fill="both", expand=True)
        tableau_valides.charger(
            [{"_id": i, **v} for i, v in enumerate(resultat.valides)],
            cle_id="_id",
            message_vide="Aucune ligne valide.",
        )

        cadre_rejets = ttk.Frame(onglets, padding=8)
        onglets.add(cadre_rejets, text=f"Rejets ({len(resultat.rejets)})")
        tableau_rejets = TableauTriable(
            cadre_rejets,
            [
                Colonne("ligne", "Ligne", 70, "e"),
                Colonne("colonne", "Colonne", 200),
                Colonne("raison", "Raison", 500),
            ],
            hauteur=14,
        )
        tableau_rejets.pack(fill="both", expand=True)
        tableau_rejets.charger(
            [
                {"_id": i, "ligne": r.ligne, "colonne": r.colonne, "raison": r.raison}
                for i, r in enumerate(resultat.rejets)
            ],
            cle_id="_id",
            etiquettes=lambda _l: "rouge",
            message_vide="Aucune ligne rejetée.",
        )

        cadre_avert = ttk.Frame(onglets, padding=8)
        onglets.add(cadre_avert, text=f"Avertissements ({len(resultat.avertissements)})")
        tableau_avert = TableauTriable(
            cadre_avert,
            [
                Colonne("ligne", "Ligne", 70, "e"),
                Colonne("colonne", "Colonne", 200),
                Colonne("message", "Message", 500),
            ],
            hauteur=14,
        )
        tableau_avert.pack(fill="both", expand=True)
        tableau_avert.charger(
            [
                {"_id": i, "ligne": a.ligne, "colonne": a.colonne, "message": a.message}
                for i, a in enumerate(resultat.avertissements)
            ],
            cle_id="_id",
            etiquettes=lambda _l: "orange",
            message_vide="Aucun avertissement.",
        )
        if resultat.avertissements:
            onglets.select(cadre_avert if not resultat.rejets else cadre_rejets)
        elif resultat.rejets:
            onglets.select(cadre_rejets)

        self.b_annuler = Bouton(self.barre_boutons, "Annuler", lambda: self.fermer(None))
        self.b_annuler.pack(side="right", padx=(8, 0))
        self.b_exporter = Bouton(
            self.barre_boutons, "Exporter le rapport d'erreurs", self._exporter
        )
        self.b_exporter.pack(side="right", padx=(8, 0))
        self.b_exporter.activer(
            bool(resultat.rejets or resultat.avertissements),
            "Aucun rejet ni avertissement à exporter.",
        )
        self.b_enregistrer = Bouton(
            self.barre_boutons,
            "Enregistrer les lignes valides",
            lambda: self.fermer("enregistrer"),
            primaire=True,
        )
        self.b_enregistrer.pack(side="right", padx=(8, 0))
        self.b_enregistrer.activer(bool(resultat.valides), "Aucune ligne valide à enregistrer.")
        self.bind("<Return>", lambda _e: None)  # évite d'enregistrer par mégarde depuis un tableau

    def _exporter(self) -> None:
        chemin = choisir_fichier_a_enregistrer(
            self,
            self.nom_fichier_erreurs,
            "Exporter le rapport d'erreurs",
            [("Classeur Excel", "*.xlsx")],
        )
        if chemin is None:
            return
        try:
            exporter_rapport_erreurs(
                chemin.with_suffix(".xlsx"), self.controle.rejets, self.controle.avertissements
            )
        except Exception as exc:  # noqa: BLE001 - message français, trace au journal
            afficher_erreur(self, f"Impossible d'exporter le rapport : {exc}")
            return
        informer(self, f"Rapport d'erreurs exporté : {Path(chemin).with_suffix('.xlsx').name}")


def ouvrir_resultat_import(
    parent,
    titre: str,
    resultat: ResultatControleQualite,
    colonnes_valides: list[Colonne],
    nom_fichier_erreurs: str,
) -> bool:
    """Ouvre la fenêtre de résultat ; retourne ``True`` si l'utilisateur a demandé
    l'enregistrement des lignes valides."""
    return (
        DialogueResultatImport(
            parent, titre, resultat, colonnes_valides, nom_fichier_erreurs
        ).afficher()
        == "enregistrer"
    )
