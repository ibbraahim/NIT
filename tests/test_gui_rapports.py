"""Test de fumée de l'écran Rapports (UC23, UC24)."""

from __future__ import annotations

import time
from datetime import date

import pytest

from app.services import admin
from tests.conftest import connecter

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def test_generer_puis_exporter(application, tmp_path, monkeypatch):
    import app.gui.vues.rapports as vr

    connecter(application, "admin")
    site_id = admin.lister_sites(application.contexte)[0]["id"]
    application.se_deconnecter()
    connecter(application, "resp")
    application.naviguer("rapports")
    application.racine.update()
    vue = application.vues["rapports"]

    vue.site.definir(site_id)
    vue.periodicite.definir("semaine")
    vue.date_reference.definir(date.today())
    vue.format.definir("pdf_excel")
    vue.actualiser_donnees()
    application.racine.update()
    assert not vue.tableau.lignes()

    vue.generer()
    # Écriture PDF + Excel (polices, mise en page) : plus lent que les autres traitements de
    # fond, et sensible à la charge du système sous une suite de tests complète ; large marge
    # pour ne jamais laisser le fil de fond orphelin (il continuerait de tourner pendant les
    # tests suivants).
    for _ in range(1200):
        application.racine.update()
        if vue.tableau.lignes() or application.erreurs:
            break
        time.sleep(0.05)

    assert application.erreurs == []
    lignes = vue.tableau.lignes()
    assert len(lignes) == 1
    assert lignes[0]["formats_disponibles"] == "PDF + Excel"
    assert lignes[0]["genere_par_libelle"] == "resp"

    vue.tableau.selectionner(lignes[0]["id"])
    application.racine.update()
    vue._sur_selection()
    assert vue.b_exporter_pdf.est_actif
    assert vue.b_exporter_excel.est_actif

    destination_pdf = tmp_path / "rapport.pdf"
    monkeypatch.setattr(vr, "choisir_fichier_a_enregistrer", lambda *a, **k: destination_pdf)
    vue.exporter_pdf()
    application.racine.update()
    assert application.erreurs == []
    assert destination_pdf.is_file()

    destination_excel = tmp_path / "rapport.xlsx"
    monkeypatch.setattr(vr, "choisir_fichier_a_enregistrer", lambda *a, **k: destination_excel)
    vue.exporter_excel()
    application.racine.update()
    assert application.erreurs == []
    assert destination_excel.is_file()
