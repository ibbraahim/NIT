"""Outil RAG : recherche dans la base de connaissances d'exploitation."""

from __future__ import annotations

from app.taches import connaissances


def sections(question, k=3):
    return [p["section"] for p in connaissances.rechercher(question, k)]


def test_la_base_est_decoupee_en_sections():
    base = connaissances.charger()
    titres = [t for t, _ in base.passages]
    assert len(titres) >= 25
    assert "Tâche sauvegarde_base" in titres


def test_une_tache_en_echec_retrouve_sa_section():
    assert sections("la tâche kpi_quotidiens a échoué")[0] == "Tâche kpi_quotidiens"
    assert sections("pg_dump introuvable")[0] == "Tâche sauvegarde_base"


def test_une_erreur_http_retrouve_sa_section():
    assert sections("erreur 401 jeton manquant")[0] == "Erreur HTTP 401 sur le point d'accès"
    assert sections("timeout of 120ms")[0].startswith("Délai dépassé")


def test_nuit_incomplete_retrouve_la_cause():
    assert "Statut incomplet : la nuit n'a pas tourné" in sections("nuit incomplète, PC éteint")


def test_question_sans_rapport_ne_renvoie_rien():
    assert connaissances.rechercher("zzzz qqqq") == []


def test_question_depuis_le_bilan():
    assert connaissances.question_depuis_bilan({"statut_global": "succes"}) == ""
    question = connaissances.question_depuis_bilan(
        {
            "statut_global": "echec",
            "etapes_nuit_manquantes": ["rapport_quotidien"],
            "echecs_recents": [{"tache": "kpi_quotidiens", "message": "connexion refusée"}],
        }
    )
    assert "kpi_quotidiens" in question and "rapport_quotidien" in question


def test_bilan_en_echec_ramene_la_section_de_la_tache():
    bilan = {
        "statut_global": "echec",
        "etapes_nuit_manquantes": [],
        "echecs_recents": [{"tache": "kpi_quotidiens", "message": "connexion refusée"}],
    }
    titres = [p["section"] for p in connaissances.connaissances_pour_bilan(bilan)]
    assert "Tâche kpi_quotidiens" in titres
    assert connaissances.connaissances_pour_bilan({"statut_global": "succes"}) == []


def test_connaissances_du_bilan_cote_serveur():
    from app.taches import serveur

    resultat = serveur._connaissances_du_bilan(
        {"statut_global": "incomplet", "etapes_nuit_manquantes": ["sauvegarde_base"]}
    )
    assert resultat["connaissances"]
    assert serveur._connaissances_du_bilan({"statut_global": "succes"}) == {"connaissances": []}
