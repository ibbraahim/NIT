"""Tâches automatiques : APScheduler (``BackgroundScheduler``) et journalisation dans
``journal_taches``.

Chaque tâche s'exécute au nom du contexte système (``CONTEXTE_SYSTEME``, acteur « Planificateur
de tâches »), pour chaque site : UC08 (réentraînement hebdomadaire — ne change jamais le modèle
actif, docs/plan.md), UC20 (rapprochement réel/prévu quotidien), UC16/17 (KPI du jour), UC21
(dérive de modèle), UC18 (alertes) et UC23 (rapport hebdomadaire). UC18 et UC23 s'appuient sur
les KPI et le réel déjà à jour : elles sont donc programmées après les tâches dont elles
dépendent.
"""

from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
from apscheduler.triggers.cron import CronTrigger

from app.bd.connexion import transaction
from app.bd.depots.parametres_modele import DepotParametresModele
from app.bd.depots.referentiels import DepotReferentiels
from app.bd.depots.taches import DepotTaches
from app.contexte import CONTEXTE_SYSTEME
from app.journal import journal
from app.services import alertes, comparaison, kpi, modeles, rapports
from app.services.modeles import DEFAUT_PARAMETRES

_log = journal(__name__)

JOURS_CRON = {
    "lundi": "mon",
    "mardi": "tue",
    "mercredi": "wed",
    "jeudi": "thu",
    "vendredi": "fri",
    "samedi": "sat",
    "dimanche": "sun",
}


def _sites() -> list[dict]:
    with transaction() as cur:
        return DepotReferentiels(cur).lister_sites()


# =====================================================================
# Tâches
# =====================================================================
def tache_entrainer_modeles() -> str:
    """UC08 : réentraîne chaque zone de chaque site ; n'active jamais la nouvelle version."""
    resumes = [modeles.entrainer_modeles(CONTEXTE_SYSTEME, site["id"]) for site in _sites()]
    nb_versions = sum(len(r.versions) for r in resumes)
    nb_avertissements = sum(len(r.avertissements) for r in resumes)
    return (
        f"{nb_versions} version(s) entraînée(s) sur {len(resumes)} site(s), "
        f"{nb_avertissements} avertissement(s)."
    )


def tache_comparer_realise() -> str:
    """UC20 : rapproche les prévisions de la semaine écoulée au réel, pour chaque site."""
    sites = _sites()
    nb = sum(
        comparaison.comparer_realise(CONTEXTE_SYSTEME, site["id"])["nb_traites"] for site in sites
    )
    return f"{nb} prévision(s) rapprochée(s) sur {len(sites)} site(s)."


def tache_calculer_kpi() -> str:
    """UC16/17 : calcule et compare les KPI du jour, pour chaque site."""
    sites = _sites()
    nb = sum(
        len(kpi.comparer_kpi_cibles(CONTEXTE_SYSTEME, site["id"], None, "jour")) for site in sites
    )
    return f"{nb} valeur(s) de KPI calculée(s) sur {len(sites)} site(s)."


def tache_detecter_derive() -> str:
    """UC21 : détecte les dérives de modèle, pour chaque site."""
    sites = _sites()
    nb = sum(len(comparaison.detecter_derive(CONTEXTE_SYSTEME, site["id"])) for site in sites)
    return f"{nb} alerte(s) de dérive émise(s) ou confirmée(s) sur {len(sites)} site(s)."


def tache_emettre_alertes() -> str:
    """UC18 : sous-effectifs, sureffectifs, pénuries d'équipements et seuils de KPI dépassés,
    pour chaque site."""
    sites = _sites()
    nb = sum(len(alertes.emettre_alertes(CONTEXTE_SYSTEME, site["id"])) for site in sites)
    return f"{nb} alerte(s) émise(s) ou confirmée(s) sur {len(sites)} site(s)."


def tache_generer_rapport() -> str:
    """UC23 : rapport de performance hebdomadaire, pour chaque site."""
    sites = _sites()
    for site in sites:
        rapports.generer_rapport(CONTEXTE_SYSTEME, site["id"], "semaine")
    return f"{len(sites)} rapport(s) généré(s)."


TACHES: dict[str, Callable[[], str]] = {
    "entrainer_modeles": tache_entrainer_modeles,
    "comparer_realise": tache_comparer_realise,
    "calculer_kpi": tache_calculer_kpi,
    "detecter_derive": tache_detecter_derive,
    "emettre_alertes": tache_emettre_alertes,
    "generer_rapport": tache_generer_rapport,
}


def executer_tache(nom: str) -> str:
    """Exécute une tâche en journalisant début, fin, statut et message dans
    ``journal_taches``. Renvoie le message ; relève l'exception d'origine en cas d'échec."""
    if nom not in TACHES:
        raise ValueError(
            f"Tâche inconnue : « {nom} ». Tâches disponibles : {', '.join(sorted(TACHES))}."
        )
    with transaction() as cur:
        tache_id = DepotTaches(cur).demarrer(nom)
    try:
        message = TACHES[nom]()
    except Exception as exc:  # noqa: BLE001 - le détail va au journal, l'appelant relève l'erreur
        with transaction() as cur:
            DepotTaches(cur).terminer(tache_id, "echec", str(exc))
        _log.exception("Tâche « %s » en échec.", nom)
        raise
    with transaction() as cur:
        DepotTaches(cur).terminer(tache_id, "succes", message)
    _log.info("Tâche « %s » terminée : %s", nom, message)
    return message


def _configuration_modeles() -> dict:
    """Lecture directe (hors service : UC07 est réservé à l'administrateur) de la
    configuration d'entraînement, pour son jour et son heure de réentraînement."""
    with transaction() as cur:
        dernier = DepotParametresModele(cur).dernier()
    return {**DEFAUT_PARAMETRES, **dernier["configuration"]} if dernier else DEFAUT_PARAMETRES


# =====================================================================
# Planificateur (écran Administration : Démarrer / Suspendre / Voir le journal)
# =====================================================================
class Planificateur:
    """Enveloppe autour d'APScheduler : les tâches sont programmées à la construction, mais
    ne s'exécutent qu'une fois le planificateur démarré."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._programmer()

    def _programmer(self) -> None:
        config = _configuration_modeles()
        jour = JOURS_CRON.get(config["jour_reentrainement"], "mon")
        heure_str, _, minute_str = config["heure_reentrainement"].partition(":")
        heure, minute = int(heure_str or 3), int(minute_str or 0)
        self._scheduler.add_job(
            lambda: executer_tache("entrainer_modeles"),
            CronTrigger(day_of_week=jour, hour=heure, minute=minute),
            id="entrainer_modeles",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("comparer_realise"),
            CronTrigger(hour=2, minute=0),
            id="comparer_realise",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("calculer_kpi"),
            CronTrigger(hour=2, minute=15),
            id="calculer_kpi",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("detecter_derive"),
            CronTrigger(hour=2, minute=20),
            id="detecter_derive",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("emettre_alertes"),
            CronTrigger(hour=2, minute=30),
            id="emettre_alertes",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("generer_rapport"),
            CronTrigger(day_of_week="mon", hour=3, minute=0),
            id="generer_rapport",
            replace_existing=True,
        )

    @property
    def est_actif(self) -> bool:
        """Vrai si le planificateur exécute ses tâches (pas à l'arrêt ni suspendu)."""
        return self._scheduler.state == STATE_RUNNING

    def demarrer(self) -> None:
        if self._scheduler.state == STATE_STOPPED:
            self._scheduler.start()
            _log.info("Planificateur de tâches démarré.")
        elif self._scheduler.state == STATE_PAUSED:
            self._scheduler.resume()
            _log.info("Planificateur de tâches repris.")

    def suspendre(self) -> None:
        if self._scheduler.state == STATE_RUNNING:
            self._scheduler.pause()
            _log.info("Planificateur de tâches suspendu.")

    def arreter(self) -> None:
        """Arrêt complet, appelé à la fermeture de l'application."""
        if self._scheduler.state != STATE_STOPPED:
            self._scheduler.shutdown(wait=False)
            _log.info("Planificateur de tâches arrêté.")

    def prochaines_executions(self) -> list[tuple[str, str | None]]:
        """(identifiant de tâche, date/heure ISO de la prochaine exécution ou ``None``)."""
        return [
            (job.id, job.next_run_time.isoformat() if job.next_run_time else None)
            for job in self._scheduler.get_jobs()
        ]
