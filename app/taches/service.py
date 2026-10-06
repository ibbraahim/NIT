"""Service sans interface : le planificateur de tâches et, par défaut, le point d'accès HTTP.

Démarré avec ``python -m app.taches planifier`` (ou ``scripts/demarrer_workly.ps1 -Planifier``).
Chaque nuit à 00:30 UTC, la tâche « nuit » enchaîne dans l'ordre : sauvegarde, import, comparaison,
KPI, alertes, prévisions, rapport, puis les tâches périodiques du jour (capacités de la semaine le
dimanche, mensuel le 1er, annuel le 1er janvier). L'hebdomadaire garde son jour et son heure
réglables (UC07). Tout est écrit dans ``journal_taches``.

Le point d'accès HTTP tourne dans le même processus, donc avec le même verrou : un appel de
l'extérieur (route ``/bilan`` en lecture, ou une tâche à la demande) ne chevauche jamais la nuit.

Ne pas démarrer en même temps le planificateur de l'interface graphique (écran Administration,
onglet Tâches) : chaque tâche tournerait deux fois.
"""

from __future__ import annotations

import threading

from app.journal import journal

_log = journal(__name__)


def lancer(hote: str = "127.0.0.1", port: int = 8765, avec_serveur: bool = True) -> None:
    """Démarre le planificateur, puis bloque (serveur HTTP ou simple attente) jusqu'à Ctrl+C."""
    from app.taches.planificateur import Planificateur
    from app.taches.serveur import lire_jeton, servir

    if avec_serveur:
        lire_jeton()  # refuse de démarrer sans jeton, avant de lancer quoi que ce soit
    planificateur = Planificateur(mode_chaine=True)
    planificateur.demarrer()
    for tache, prochaine in sorted(planificateur.prochaines_executions()):
        print(f"Prochaine exécution de « {tache} » : {prochaine} (UTC)")
    _log.info("Service de planification démarré (serveur HTTP : %s).", avec_serveur)
    try:
        if avec_serveur:
            servir(hote, port)
        else:
            print("Planificateur en marche, sans serveur HTTP (Ctrl+C pour arrêter).")
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        planificateur.arreter()
