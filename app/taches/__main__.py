"""Exécution manuelle des tâches automatiques.

Utilisation :

    python -m app.taches lister                  liste les tâches disponibles
    python -m app.taches executer <nom_tache>     exécute une tâche et journalise le résultat
    python -m app.taches serveur                  point d'accès HTTP pour une plateforme
                                                  d'automatisation (jeton WORKLY_TOKEN_TACHES)
"""

from __future__ import annotations

import sys

from app.journal import configurer_journal, journal
from app.utils.cli import AnalyseurFrancais

_log = journal(__name__)


def principal(arguments: list[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    analyseur = AnalyseurFrancais(
        prog="python -m app.taches", description="Exécute une tâche automatique de l'application."
    )
    sous_analyseurs = analyseur.add_subparsers(dest="commande")
    sous_analyseurs.add_parser("lister", help="liste les tâches disponibles")
    executer = sous_analyseurs.add_parser("executer", help="exécute une tâche")
    executer.add_argument("nom_tache", help="nom de la tâche à exécuter")
    serveur = sous_analyseurs.add_parser("serveur", help="démarre le point d'accès HTTP")
    serveur.add_argument("--hote", default="127.0.0.1", help="adresse d'écoute (défaut : locale)")
    serveur.add_argument("--port", type=int, default=8765, help="port d'écoute (défaut : 8765)")
    options = analyseur.parse_args(arguments)

    configurer_journal()
    from app.bd.connexion import fermer_pool
    from app.taches.planificateur import TACHES, executer_tache

    try:
        if options.commande == "serveur":
            from app.taches.serveur import servir

            servir(options.hote, options.port)
            return 0
        if options.commande in (None, "lister"):
            print("Tâches disponibles :")
            for nom in sorted(TACHES):
                print(f"  - {nom}")
            return 0
        try:
            message = executer_tache(options.nom_tache)
        except ValueError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001 - toute erreur est traduite en français
            _log.exception("Échec de la tâche « %s » : %s", options.nom_tache, exc)
            print(
                f"Erreur : la tâche « {options.nom_tache} » a échoué. "
                "Consultez journaux/application.log.",
                file=sys.stderr,
            )
            return 1
        print(message)
        return 0
    finally:
        fermer_pool()


if __name__ == "__main__":
    sys.exit(principal())
