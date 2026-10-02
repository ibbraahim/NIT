"""Tableau triable : texte long jamais perdu (colonne élargie, défilement, info-bulle)."""

from __future__ import annotations

import pytest

from app.gui.widgets.tableau_triable import Colonne, TableauTriable

pytestmark = pytest.mark.gui


@pytest.fixture
def tableau(application):
    import tkinter as tk

    cadre = tk.Frame(application.racine, width=400, height=200)
    cadre.pack_propagate(False)
    cadre.pack()
    tableau = TableauTriable(
        cadre,
        [Colonne("tache", "Tâche", 120), Colonne("message", "Message", 200)],
        hauteur=6,
    )
    tableau.pack(fill="both", expand=True)
    tableau.charger(
        [
            {"id": 1, "tache": "import", "message": "x" * 150},
            {"id": 2, "tache": "kpi", "message": "court"},
        ]
    )
    application.racine.update()
    return tableau


def test_une_colonne_au_texte_long_est_elargie_et_le_tableau_defile(tableau):
    assert int(tableau.arbre.column("message", "width")) > 200
    debut, fin = tableau.arbre.xview()
    assert fin < 1.0  # une partie du contenu est hors de la zone visible : on peut défiler
    tableau.arbre.xview_moveto(1.0)
    assert tableau.arbre.xview()[1] == 1.0


def test_l_info_bulle_donne_le_texte_complet_d_une_cellule_rognee(tableau):
    tableau._afficher_info_cellule(("1", "#2"), 100, 100)
    assert tableau._info_cellule is not None
    tableau._masquer_info_cellule()
    assert tableau._info_cellule is None
    # Cellule courte : pas d'info-bulle
    tableau._afficher_info_cellule(("2", "#2"), 100, 100)
    assert tableau._info_cellule is None
