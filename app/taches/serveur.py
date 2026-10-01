"""Point d'accès HTTP des tâches automatiques, pour les orchestrateurs externes.

Une plateforme d'automatisation (déclencheur planifié + appel HTTP) pilote les tâches sans
toucher à la base : elle appelle ce petit serveur, qui exécute la tâche demandée avec la même
fonction que le planificateur interne (``executer_tache``, donc la même journalisation dans
``journal_taches``). Sécurité : jeton secret obligatoire (variable ``WORKLY_TOKEN_TACHES``),
écoute locale par défaut, une seule tâche à la fois.

Routes (le jeton se passe en ``Authorization: Bearer <jeton>``) :

    GET  /sante               {"ok": true}                          (sans jeton)
    GET  /taches              liste des tâches
    POST /taches/<nom>        exécute une tâche
    POST /test-mail           envoie un e-mail de test (voir app/taches/notifications.py)
    POST /cycle-nocturne      import → comparaison → KPI → alertes → prévisions → rapport,
                              arrêt à la première erreur
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.journal import journal

_log = journal(__name__)

VARIABLE_JETON = "WORKLY_TOKEN_TACHES"
LONGUEUR_MIN_JETON = 16
CYCLE_NOCTURNE = (
    "import_historique",
    "import_previsions_volume",
    "comparaison_quotidienne",
    "kpi_quotidiens",
    "alertes_capacite",
    "previsions_quotidiennes",
    "rapport_quotidien",
)

_verrou = threading.Lock()


def executer_et_mesurer(nom: str) -> dict:
    """Exécute une tâche et renvoie son résultat sous forme de dictionnaire JSON."""
    from app.taches.planificateur import executer_tache

    debut = time.monotonic()
    try:
        message = executer_tache(nom)
    except Exception as exc:  # noqa: BLE001 - le détail est au journal, pas dans la réponse
        _log.exception("Échec de la tâche « %s » appelée par HTTP : %s", nom, exc)
        return {
            "tache": nom,
            "statut": "echec",
            "erreur": f"La tâche « {nom} » a échoué. Consultez journaux/application.log.",
            "duree_s": round(time.monotonic() - debut, 2),
        }
    return {
        "tache": nom,
        "statut": "succes",
        "message": message,
        "duree_s": round(time.monotonic() - debut, 2),
    }


def executer_cycle() -> dict:
    """Enchaîne les tâches du cycle nocturne ; s'arrête à la première qui échoue."""
    etapes = []
    for nom in CYCLE_NOCTURNE:
        resultat = executer_et_mesurer(nom)
        etapes.append(resultat)
        if resultat["statut"] != "succes":
            return {"statut": "echec", "etape_en_echec": nom, "etapes": etapes}
    return {"statut": "succes", "etapes": etapes}


def fabriquer_gestionnaire(jeton: str):
    class Gestionnaire(BaseHTTPRequestHandler):
        server_version = "WorklyTaches/1.0"

        def log_message(self, format, *args):  # noqa: A002 - signature imposée
            _log.info("HTTP %s", format % args)

        def _repondre(self, code: int, corps: dict) -> None:
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def _autorise(self) -> bool:
            recu = self.headers.get("Authorization", "")
            attendu = f"Bearer {jeton}"
            return hmac.compare_digest(recu.encode("utf-8"), attendu.encode("utf-8"))

        def _executer_exclusif(self, travail) -> None:
            if not _verrou.acquire(blocking=False):
                self._repondre(409, {"statut": "occupe", "erreur": "Une tâche est déjà en cours."})
                return
            try:
                resultat = travail()
            finally:
                _verrou.release()
            self._repondre(200 if resultat["statut"] == "succes" else 500, resultat)

        def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
            if self.path == "/sante":
                self._repondre(200, {"ok": True})
                return
            if not self._autorise():
                self._repondre(401, {"erreur": "Jeton manquant ou invalide."})
                return
            if self.path == "/taches":
                from app.taches.planificateur import TACHES

                self._repondre(200, {"taches": sorted(TACHES), "cycle_nocturne": CYCLE_NOCTURNE})
                return
            self._repondre(404, {"erreur": "Route inconnue."})

        def do_POST(self) -> None:  # noqa: N802
            if not self._autorise():
                self._repondre(401, {"erreur": "Jeton manquant ou invalide."})
                return
            if self.path == "/test-mail":
                from app.taches.notifications import envoyer

                envoye = envoyer(
                    "Workly : e-mail de test",
                    "Si vous lisez ce message, les alertes par e-mail de Workly fonctionnent.",
                )
                self._repondre(
                    200 if envoye else 500,
                    {"statut": "succes" if envoye else "echec", "envoye": envoye},
                )
                return
            if self.path == "/cycle-nocturne":
                self._executer_exclusif(executer_cycle)
                return
            if self.path.startswith("/taches/"):
                from app.taches.planificateur import TACHES

                nom = self.path.removeprefix("/taches/")
                if nom not in TACHES:
                    self._repondre(404, {"erreur": f"Tâche inconnue : « {nom} »."})
                    return
                self._executer_exclusif(lambda: executer_et_mesurer(nom))
                return
            self._repondre(404, {"erreur": "Route inconnue."})

    return Gestionnaire


def servir(hote: str = "127.0.0.1", port: int = 8765) -> None:
    """Démarre le serveur (bloquant) ; refuse de démarrer sans jeton suffisamment long."""
    jeton = os.environ.get(VARIABLE_JETON, "")
    if len(jeton) < LONGUEUR_MIN_JETON:
        raise SystemExit(
            f"Erreur : définissez la variable d'environnement {VARIABLE_JETON} "
            f"({LONGUEUR_MIN_JETON} caractères au minimum) avant de démarrer le serveur."
        )
    serveur = ThreadingHTTPServer((hote, port), fabriquer_gestionnaire(jeton))
    _log.info("Serveur des tâches à l'écoute sur http://%s:%s", hote, port)
    print(f"Serveur des tâches à l'écoute sur http://{hote}:{port} (Ctrl+C pour arrêter)")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
