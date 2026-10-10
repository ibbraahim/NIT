"""Point d'accès HTTP des tâches automatiques (jeton, routes, exécution réelle)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import UTC
from http.server import ThreadingHTTPServer

import pytest

from app.taches import serveur

pytestmark = pytest.mark.integration

JETON = "jeton-de-test-0123456789"


@pytest.fixture
def adresse():
    http = ThreadingHTTPServer(("127.0.0.1", 0), serveur.fabriquer_gestionnaire(JETON))
    fil = threading.Thread(target=http.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{http.server_address[1]}"
    http.shutdown()
    http.server_close()


def appeler(adresse, chemin, methode="GET", jeton=JETON):
    requete = urllib.request.Request(adresse + chemin, method=methode)
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            return reponse.status, json.loads(reponse.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_sante_sans_jeton(adresse):
    assert appeler(adresse, "/sante", jeton=None) == (200, {"ok": True})


def test_jeton_obligatoire_et_verifie(adresse):
    assert appeler(adresse, "/taches", jeton=None)[0] == 401
    assert appeler(adresse, "/taches", jeton="mauvais")[0] == 401
    assert appeler(adresse, "/taches/kpi_quotidiens", "POST", jeton="mauvais")[0] == 401


def test_liste_des_taches(adresse):
    code, corps = appeler(adresse, "/taches")
    assert code == 200
    assert len(corps["taches"]) == 12
    assert corps["cycle_nocturne"][0] == "import_historique"


def test_tache_et_route_inconnues(adresse):
    assert appeler(adresse, "/taches/inexistante", "POST")[0] == 404
    assert appeler(adresse, "/nimporte", "POST")[0] == 404


def test_execution_reelle_d_une_tache(adresse, demo_referentiels):
    code, corps = appeler(adresse, "/taches/kpi_quotidiens", "POST")
    assert code == 200
    assert corps["statut"] == "succes"
    assert "KPI" in corps["message"]


def test_echec_renvoie_500_sans_detail_interne(adresse, monkeypatch):
    from app.taches import planificateur

    def casse():
        raise RuntimeError("secret interne")

    monkeypatch.setitem(planificateur.TACHES, "kpi_quotidiens", casse)
    monkeypatch.setattr(planificateur, "executer_tache", lambda nom: planificateur.TACHES[nom]())
    code, corps = appeler(adresse, "/taches/kpi_quotidiens", "POST")
    assert code == 500
    assert corps["statut"] == "echec"
    assert "secret interne" not in json.dumps(corps)


def test_cycle_s_arrete_a_la_premiere_erreur(adresse, monkeypatch):
    appelees = []

    def faux(nom):
        appelees.append(nom)
        return {"tache": nom, "statut": "echec" if nom == "kpi_quotidiens" else "succes"}

    monkeypatch.setattr(serveur, "executer_et_mesurer", faux)
    code, corps = appeler(adresse, "/cycle-nocturne", "POST")
    assert code == 500
    assert corps["etape_en_echec"] == "kpi_quotidiens"
    assert appelees == [
        "import_historique",
        "import_previsions_volume",
        "comparaison_quotidienne",
        "kpi_quotidiens",
    ]


def test_une_seule_tache_a_la_fois(adresse):
    assert serveur._verrou.acquire(blocking=False)
    try:
        code, corps = appeler(adresse, "/taches/kpi_quotidiens", "POST")
    finally:
        serveur._verrou.release()
    assert code == 409
    assert corps["statut"] == "occupe"


def test_refus_de_demarrer_sans_jeton(monkeypatch):
    monkeypatch.delenv(serveur.VARIABLE_JETON, raising=False)
    with pytest.raises(SystemExit):
        serveur.servir()
    monkeypatch.setenv(serveur.VARIABLE_JETON, "court")
    with pytest.raises(SystemExit):
        serveur.servir()


def test_route_test_mail(adresse, monkeypatch):
    from app.taches import notifications

    envoyes = []
    monkeypatch.setattr(
        notifications, "envoyer", lambda sujet, corps: envoyes.append(sujet) or True
    )
    assert appeler(adresse, "/test-mail", "POST", jeton=None)[0] == 401
    code, corps = appeler(adresse, "/test-mail", "POST")
    assert code == 200 and corps["envoye"] is True
    assert envoyes == ["Workly : e-mail de test"]

    monkeypatch.setattr(notifications, "envoyer", lambda sujet, corps: False)
    assert appeler(adresse, "/test-mail", "POST")[0] == 500


def test_route_test_odoo(adresse, monkeypatch):
    from app.taches import odoo

    monkeypatch.setattr(
        odoo, "tester_connexion", lambda: {"version": "17.0", "base": "b", "commandes_vente": 3}
    )
    assert appeler(adresse, "/test-odoo", "POST", jeton=None)[0] == 401
    code, corps = appeler(adresse, "/test-odoo", "POST")
    assert code == 200 and corps["statut"] == "succes" and corps["commandes_vente"] == 3

    def refuse():
        raise odoo.ErreurOdoo("Identifiants refusés")

    monkeypatch.setattr(odoo, "tester_connexion", refuse)
    code, corps = appeler(adresse, "/test-odoo", "POST")
    assert code == 500 and corps["statut"] == "echec" and "refusés" in corps["erreur"]


def test_aujourdhui_drapeaux_de_date():
    from datetime import datetime

    dimanche = serveur.aujourdhui(datetime(2026, 10, 4, 0, 30, tzinfo=UTC))
    assert dimanche["jour_semaine"] == "dimanche" and dimanche["est_dimanche"]
    assert not dimanche["est_lundi"] and not dimanche["est_premier_du_mois"]
    premier_janvier = serveur.aujourdhui(datetime(2027, 1, 1, 0, 30, tzinfo=UTC))
    assert premier_janvier["est_premier_du_mois"] and premier_janvier["est_premier_janvier"]
    assert serveur.aujourdhui(datetime(2026, 10, 5, tzinfo=UTC))["est_lundi"]
    assert serveur.aujourdhui(datetime(2026, 11, 1, tzinfo=UTC))["est_premier_janvier"] is False


def test_aujourdhui_exige_le_jeton_et_repond(adresse):
    assert appeler(adresse, "/aujourdhui", jeton=None)[0] == 401
    code, corps = appeler(adresse, "/aujourdhui")
    assert code == 200 and "jour_semaine" in corps


def test_alerte_envoie_un_mail_au_nom_nettoye(adresse, monkeypatch):
    envois = []
    import app.taches.notifications as notifications

    monkeypatch.setattr(
        notifications, "envoyer", lambda sujet, corps: envois.append((sujet, corps)) or True
    )
    code, corps = appeler(adresse, "/alerte?etape=KPI%20du%20jour%0D%0ABcc:x@y.z", "POST")
    assert code == 200 and corps["envoye"] is True
    sujet, _ = envois[0]
    assert "\n" not in sujet and "\r" not in sujet
    assert "KPI du jour" in sujet
    assert appeler(adresse, "/alerte?etape=x", "POST", jeton=None)[0] == 401


def test_alerte_sans_messagerie_configuree_repond_echec(adresse, monkeypatch):
    import app.taches.notifications as notifications

    monkeypatch.setattr(notifications, "envoyer", lambda sujet, corps: False)
    code, corps = appeler(adresse, "/alerte?etape=import", "POST")
    assert code == 500 and corps["statut"] == "echec"


@pytest.mark.parametrize(
    ("jour", "attendu"),
    [
        ((2026, 10, 7), []),  # un mercredi ordinaire : rien
        ((2026, 10, 4), ["capacites_semaine"]),  # dimanche
        ((2026, 10, 12), ["hebdomadaire"]),  # lundi
        ((2026, 11, 1), ["capacites_semaine", "mensuel"]),  # dimanche 1er novembre
        ((2026, 6, 1), ["hebdomadaire", "mensuel"]),  # lundi 1er juin : jamais en parallèle
        ((2027, 1, 1), ["mensuel", "annuel"]),  # vendredi 1er janvier
    ],
)
def test_taches_dues_selon_la_date(jour, attendu):
    from datetime import UTC, datetime

    assert serveur.taches_dues(datetime(*jour, 0, 30, tzinfo=UTC)) == attendu


def test_taches_du_jour_s_arrete_a_la_premiere_erreur(adresse, monkeypatch):

    appelees = []

    def faux(nom):
        appelees.append(nom)
        return {"tache": nom, "statut": "echec" if nom == "hebdomadaire" else "succes"}

    monkeypatch.setattr(serveur, "executer_et_mesurer", faux)
    monkeypatch.setattr(
        serveur,
        "taches_dues",
        lambda maintenant=None: ["hebdomadaire", "mensuel"],
    )
    code, corps = appeler(adresse, "/taches-du-jour", "POST")
    assert code == 500 and corps["etape_en_echec"] == "hebdomadaire"
    assert appelees == ["hebdomadaire"]  # le mensuel n'est pas lancé


def test_taches_du_jour_sans_tache_due_reussit(adresse, monkeypatch):
    monkeypatch.setattr(serveur, "taches_dues", lambda maintenant=None: [])
    code, corps = appeler(adresse, "/taches-du-jour", "POST")
    assert code == 200 and corps == {"statut": "succes", "taches_dues": [], "etapes": []}
    assert appeler(adresse, "/taches-du-jour", "POST", jeton=None)[0] == 401


def test_nuit_enchaine_dans_l_ordre_et_s_arrete_a_la_premiere_erreur(monkeypatch):
    from datetime import UTC, datetime

    appelees = []

    def faux(nom):
        appelees.append(nom)
        return {"tache": nom, "statut": "echec" if nom == "alertes_capacite" else "succes"}

    monkeypatch.setattr(serveur, "executer_et_mesurer", faux)
    resultat = serveur.executer_nuit(datetime(2026, 10, 4, 0, 30, tzinfo=UTC))
    assert resultat["statut"] == "echec" and resultat["etape_en_echec"] == "alertes_capacite"
    assert appelees == [
        "sauvegarde_base",
        "import_historique",
        "import_previsions_volume",
        "comparaison_quotidienne",
        "kpi_quotidiens",
        "alertes_capacite",
    ]


def test_nuit_complete_ajoute_les_taches_du_jour_sans_l_hebdomadaire(monkeypatch):
    from datetime import UTC, datetime

    appelees = []
    monkeypatch.setattr(
        serveur,
        "executer_et_mesurer",
        lambda nom: appelees.append(nom) or {"tache": nom, "statut": "succes"},
    )
    # Lundi 1er juin 2026 : l'hebdomadaire a son propre horaire, seul le mensuel s'ajoute.
    resultat = serveur.executer_nuit(datetime(2026, 6, 1, 0, 30, tzinfo=UTC))
    assert resultat["statut"] == "succes"
    assert appelees[0] == "sauvegarde_base" and appelees[-2:] == ["rapport_quotidien", "mensuel"]
    assert "hebdomadaire" not in appelees


def test_bilan_exige_le_jeton(adresse):
    assert appeler(adresse, "/bilan", jeton=None)[0] == 401


def test_bilan_base_vierge_signale_une_nuit_incomplete(adresse, bd_vierge):
    code, corps = appeler(adresse, "/bilan")
    assert code == 200
    assert corps["statut_global"] == "incomplet"
    assert corps["etapes_nuit_manquantes"][0] == "sauvegarde_base"
    assert corps["dernieres_executions"] == [] and corps["echecs_recents"] == []
    assert len(corps["jamais_executees"]) == 12


def test_bilan_apres_une_nuit_reussie_puis_un_echec(adresse, bd_vierge):
    from app.bd.connexion import transaction
    from app.bd.depots.taches import DepotTaches

    with transaction() as cur:
        depot = DepotTaches(cur)
        for nom in ("sauvegarde_base", *serveur.CYCLE_NOCTURNE):
            depot.terminer(depot.demarrer(nom), "succes", f"{nom} ok")
    code, corps = appeler(adresse, "/bilan")
    assert corps["statut_global"] == "succes" and corps["etapes_nuit_manquantes"] == []
    assert [d["tache"] for d in corps["dernieres_executions"]][0] == "sauvegarde_base"

    with transaction() as cur:
        depot = DepotTaches(cur)
        depot.terminer(depot.demarrer("kpi_quotidiens"), "echec", "x" * 500)
    code, corps = appeler(adresse, "/bilan")
    assert corps["statut_global"] == "echec" and corps["nb_echecs_24h"] == 1
    echec = corps["echecs_recents"][0]
    assert echec["tache"] == "kpi_quotidiens" and len(echec["message"]) == 300


def test_route_connaissances(adresse):
    assert appeler(adresse, "/connaissances?question=x", jeton=None)[0] == 401
    assert appeler(adresse, "/connaissances")[0] == 400
    code, corps = appeler(adresse, "/connaissances?question=erreur+401+jeton&k=2")
    assert code == 200
    assert corps["passages"][0]["section"].startswith("Erreur HTTP 401")
    assert len(corps["passages"]) <= 2


def test_bilan_avec_connaissances(adresse, bd_vierge):
    code, corps = appeler(adresse, "/bilan?connaissances=1")
    assert code == 200
    assert corps["statut_global"] == "incomplet"
    assert corps["connaissances"], "une nuit incomplète doit ramener des passages"
    assert "connaissances" not in appeler(adresse, "/bilan")[1]
