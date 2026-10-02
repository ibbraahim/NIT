"""Sauvegarde quotidienne de la base : purge, secrets, erreurs, recherche de pg_dump."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from app.erreurs import ErreurApplication
from app.taches import sauvegarde


@pytest.fixture
def faux_pg_dump(monkeypatch):
    """Remplace pg_dump : écrit le fichier demandé et mémorise l'appel."""
    appels = []

    def faux(commande, **options):
        appels.append((commande, options))
        Path(commande[commande.index("--file") + 1]).write_bytes(b"x" * 2048)
        return subprocess.CompletedProcess(commande, 0, "", "")

    monkeypatch.setattr(sauvegarde, "trouver_pg_dump", lambda: "pg_dump")
    monkeypatch.setattr(sauvegarde.subprocess, "run", faux)
    return appels


def test_sauvegarde_ecrit_un_fichier_et_cache_le_mot_de_passe(tmp_path, faux_pg_dump):
    message = sauvegarde.sauvegarder_base(tmp_path, datetime(2026, 10, 2, 0, 30, 5))
    assert (tmp_path / "workly_20261002_003005.dump").is_file()
    assert "workly_20261002_003005.dump" in message
    commande, options = faux_pg_dump[0]
    assert options["env"]["PGPASSWORD"]  # transmis par l'environnement du processus...
    assert options["env"]["PGPASSWORD"] not in " ".join(commande)  # ...jamais en argument


def test_purge_ne_garde_que_les_copies_les_plus_recentes(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKLY_SAUVEGARDES_CONSERVEES", "3")
    for jour in range(1, 6):
        (tmp_path / f"workly_2026100{jour}_000000.dump").write_bytes(b"x")
    (tmp_path / "autre_fichier.txt").write_text("à ne pas toucher")
    assert sauvegarde.purger(tmp_path, 3) == 2
    restants = sorted(f.name for f in tmp_path.iterdir())
    assert restants == [
        "autre_fichier.txt",
        "workly_20261003_000000.dump",
        "workly_20261004_000000.dump",
        "workly_20261005_000000.dump",
    ]


def test_echec_de_pg_dump_leve_une_erreur_sans_laisser_de_fichier(tmp_path, monkeypatch):
    def echec(commande, **options):
        Path(commande[commande.index("--file") + 1]).write_bytes(b"partiel")
        return subprocess.CompletedProcess(commande, 1, "", "mot de passe incorrect")

    monkeypatch.setattr(sauvegarde, "trouver_pg_dump", lambda: "pg_dump")
    monkeypatch.setattr(sauvegarde.subprocess, "run", echec)
    with pytest.raises(ErreurApplication, match="a échoué"):
        sauvegarde.sauvegarder_base(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_pg_dump_introuvable_donne_un_message_clair(monkeypatch):
    monkeypatch.delenv("WORKLY_PG_DUMP", raising=False)
    monkeypatch.setenv("ProgramFiles", "/chemin/inexistant")
    monkeypatch.setattr(sauvegarde.shutil, "which", lambda _nom: None)
    with pytest.raises(ErreurApplication, match="WORKLY_PG_DUMP"):
        sauvegarde.trouver_pg_dump()


def test_variable_pg_dump_prioritaire(tmp_path, monkeypatch):
    exe = tmp_path / "pg_dump.exe"
    exe.write_text("")
    monkeypatch.setenv("WORKLY_PG_DUMP", str(exe))
    assert sauvegarde.trouver_pg_dump() == str(exe)
