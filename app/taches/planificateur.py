"""Tâches automatiques : APScheduler (``BackgroundScheduler``) et journalisation dans
``journal_taches``.

Neuf tâches, exécutées au nom du contexte système (``CONTEXTE_SYSTEME``, acteur « Planificateur
de tâches »), pour chaque site :

- ``import_historique`` (01:00) — UC04 (import) + UC06, sur les fichiers déposés dans
  ``entrees/historique/``, déplacés ensuite vers ``entrees/traites/``.
- ``comparaison_quotidienne`` (01:30) — UC20 puis UC21 (la dérive s'appuie sur le réel qui
  vient d'être rapproché).
- ``kpi_quotidiens`` (01:45) — UC17 (jour), qui inclut UC16.
- ``alertes_capacite`` (01:50) — UC18, sur le plan de charge validé et les KPI du jour déjà
  calculés (dont les seuils de KPI dépassés, UC17 → UC18).
- ``previsions_quotidiennes`` (02:00) — UC11 sur J+1 à J+14, RL et RN.
- ``rapport_quotidien`` (06:00) — UC23 (jour) + export PDF.
- ``hebdomadaire`` (lundi, heure configurable via UC07 — jour_reentrainement/
  heure_reentrainement, par défaut lundi 03:00) — UC08 (ne change jamais le modèle actif,
  docs/plan.md), puis UC17 (semaine) et UC23 (semaine).
- ``mensuel`` (1er du mois, 04:00) — UC17 (mois), UC23 (mois).
- ``annuel`` (1er janvier, 05:00) — UC17 (année), UC23 (année).

L'ordre à l'intérieur de chaque tâche, et l'ordre des tâches entre elles, respecte les
dépendances : une tâche qui s'appuie sur un résultat (KPI, réel rapproché) est programmée après
la tâche qui le produit.
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
from app.config import DOSSIER_ENTREES_HISTORIQUE, DOSSIER_ENTREES_TRAITES
from app.contexte import CONTEXTE_SYSTEME
from app.erreurs import ErreurApplication
from app.journal import journal
from app.services import alertes, comparaison, donnees, kpi, modeles, planification, rapports
from app.services.modeles import DEFAUT_PARAMETRES
from app.utils.fichiers_excel import EXTENSIONS_PRISES_EN_CHARGE

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

#: Fréquence des tâches à horaire fixe (tableau de l'écran Administration, onglet Tâches).
#: ``hebdomadaire`` n'y figure pas : son jour et son heure sont configurables (UC07).
FREQUENCES_FIXES = {
    "import_historique": "Chaque jour à 01:00",
    "comparaison_quotidienne": "Chaque jour à 01:30",
    "kpi_quotidiens": "Chaque jour à 01:45",
    "alertes_capacite": "Chaque jour à 01:50",
    "previsions_quotidiennes": "Chaque jour à 02:00",
    "rapport_quotidien": "Chaque jour à 06:00",
    "mensuel": "Le 1er de chaque mois à 04:00",
    "annuel": "Le 1er janvier à 05:00",
}


def _sites() -> list[dict]:
    with transaction() as cur:
        return DepotReferentiels(cur).lister_sites()


# =====================================================================
# Blocs partagés (un même cas d'utilisation sert plusieurs tâches)
# =====================================================================
def _entrainer_modeles() -> tuple[int, int, int]:
    """UC08 : réentraîne chaque zone de chaque site ; n'active jamais la nouvelle version."""
    sites = _sites()
    resumes = [modeles.entrainer_modeles(CONTEXTE_SYSTEME, site["id"]) for site in sites]
    nb_versions = sum(len(r.versions) for r in resumes)
    nb_avertissements = sum(len(r.avertissements) for r in resumes)
    return len(sites), nb_versions, nb_avertissements


def _comparer_realise() -> tuple[int, int]:
    """UC20 : rapproche les prévisions au réel, pour chaque site."""
    sites = _sites()
    nb = sum(
        comparaison.comparer_realise(CONTEXTE_SYSTEME, site["id"])["nb_traites"] for site in sites
    )
    return len(sites), nb


def _detecter_derive() -> tuple[int, int]:
    """UC21 : détecte les dérives de modèle, pour chaque site."""
    sites = _sites()
    nb = sum(len(comparaison.detecter_derive(CONTEXTE_SYSTEME, site["id"])) for site in sites)
    return len(sites), nb


def _calculer_kpi(periodicite: str) -> tuple[int, int]:
    """UC16/17 : calcule et compare les KPI de la période, pour chaque site."""
    sites = _sites()
    nb = sum(
        len(kpi.comparer_kpi_cibles(CONTEXTE_SYSTEME, site["id"], None, periodicite))
        for site in sites
    )
    return len(sites), nb


def _generer_rapports(periodicite: str, format_rapport: str = "pdf_excel") -> int:
    """UC23 : rapport de performance de la période, pour chaque site."""
    sites = _sites()
    for site in sites:
        rapports.generer_rapport(
            CONTEXTE_SYSTEME, site["id"], periodicite, format_rapport=format_rapport
        )
    return len(sites)


# =====================================================================
# Les neuf tâches automatiques
# =====================================================================
def tache_import_historique() -> str:
    """UC04 (import) + UC06 : importe chaque fichier déposé dans ``entrees/historique/``, puis
    le déplace vers ``entrees/traites/``. Un fichier illisible est laissé en place, pour
    inspection, sans empêcher le traitement des autres."""
    fichiers = sorted(
        f
        for f in DOSSIER_ENTREES_HISTORIQUE.glob("*")
        if f.suffix.lower() in EXTENSIONS_PRISES_EN_CHARGE
    )
    total_valides = total_rejetees = total_avertissements = echecs = 0
    for fichier in fichiers:
        try:
            resultat = donnees.importer_historique(CONTEXTE_SYSTEME, fichier)
        except ErreurApplication as exc:
            echecs += 1
            _log.warning("Fichier « %s » illisible, laissé en place : %s", fichier.name, exc)
            continue
        if resultat.valides:
            donnees.enregistrer_lignes_historique(CONTEXTE_SYSTEME, resultat.valides)
        total_valides += len(resultat.valides)
        total_rejetees += len(resultat.rejets)
        total_avertissements += len(resultat.avertissements)
        DOSSIER_ENTREES_TRAITES.mkdir(parents=True, exist_ok=True)
        fichier.rename(DOSSIER_ENTREES_TRAITES / fichier.name)
    message = (
        f"{len(fichiers) - echecs} fichier(s) traité(s) : {total_valides} ligne(s) "
        f"valide(s), {total_rejetees} rejetée(s), {total_avertissements} avertissement(s)"
    )
    return message + (f", {echecs} fichier(s) illisible(s)." if echecs else ".")


def tache_comparaison_quotidienne() -> str:
    """UC20 puis UC21, pour chaque site."""
    nb_sites, nb_rapproches = _comparer_realise()
    _, nb_derives = _detecter_derive()
    return (
        f"{nb_rapproches} prévision(s) rapprochée(s), {nb_derives} alerte(s) de dérive "
        f"émise(s) ou confirmée(s), sur {nb_sites} site(s)."
    )


def tache_kpi_quotidiens() -> str:
    """UC17 (jour), qui inclut UC16, pour chaque site."""
    nb_sites, nb = _calculer_kpi("jour")
    return f"{nb} valeur(s) de KPI calculée(s) sur {nb_sites} site(s)."


def tache_alertes_capacite() -> str:
    """UC18 : sous-effectifs, sureffectifs, pénuries d'équipements et seuils de KPI dépassés,
    sur J+1 à J+7, pour chaque site."""
    sites = _sites()
    nb = sum(len(alertes.emettre_alertes(CONTEXTE_SYSTEME, site["id"])) for site in sites)
    return f"{nb} alerte(s) émise(s) ou confirmée(s) sur {len(sites)} site(s)."


def tache_previsions_quotidiennes() -> str:
    """UC11 : prévisions de ressources RL et RN de J+1 à J+14, pour chaque site (toutes
    zones)."""
    sites = _sites()
    total_lignes = total_avertissements = 0
    for site in sites:
        resume = planification.generer_previsions(CONTEXTE_SYSTEME, site["id"], None, 14)
        total_lignes += resume.nb_lignes
        total_avertissements += len(resume.avertissements)
    return (
        f"{total_lignes} ligne(s) de prévision générée(s) sur {len(sites)} site(s), "
        f"{total_avertissements} avertissement(s)."
    )


def tache_rapport_quotidien() -> str:
    """UC23 (jour) + export PDF, pour chaque site."""
    nb = _generer_rapports("jour", "pdf")
    return f"{nb} rapport(s) quotidien(s) généré(s)."


def tache_hebdomadaire() -> str:
    """UC08, puis UC17 (semaine) et UC23 (semaine), pour chaque site."""
    nb_sites, nb_versions, nb_avertissements = _entrainer_modeles()
    _, nb_kpi = _calculer_kpi("semaine")
    _generer_rapports("semaine")
    return (
        f"{nb_versions} version(s) entraînée(s) sur {nb_sites} site(s) "
        f"({nb_avertissements} avertissement(s)), {nb_kpi} valeur(s) de KPI (semaine), "
        f"{nb_sites} rapport(s) hebdomadaire(s) généré(s)."
    )


def tache_mensuel() -> str:
    """UC17 (mois) et UC23 (mois), pour chaque site."""
    nb_sites, nb_kpi = _calculer_kpi("mois")
    _generer_rapports("mois")
    return f"{nb_kpi} valeur(s) de KPI (mois), {nb_sites} rapport(s) mensuel(s) généré(s)."


def tache_annuel() -> str:
    """UC17 (année) et UC23 (année), pour chaque site."""
    nb_sites, nb_kpi = _calculer_kpi("annee")
    _generer_rapports("annee")
    return f"{nb_kpi} valeur(s) de KPI (année), {nb_sites} rapport(s) annuel(s) généré(s)."


TACHES: dict[str, Callable[[], str]] = {
    "import_historique": tache_import_historique,
    "comparaison_quotidienne": tache_comparaison_quotidienne,
    "kpi_quotidiens": tache_kpi_quotidiens,
    "alertes_capacite": tache_alertes_capacite,
    "previsions_quotidiennes": tache_previsions_quotidiennes,
    "rapport_quotidien": tache_rapport_quotidien,
    "hebdomadaire": tache_hebdomadaire,
    "mensuel": tache_mensuel,
    "annuel": tache_annuel,
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
    configuration d'entraînement, pour le jour et l'heure de la tâche ``hebdomadaire``."""
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
        self._scheduler.add_job(
            lambda: executer_tache("import_historique"),
            CronTrigger(hour=1, minute=0),
            id="import_historique",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("comparaison_quotidienne"),
            CronTrigger(hour=1, minute=30),
            id="comparaison_quotidienne",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("kpi_quotidiens"),
            CronTrigger(hour=1, minute=45),
            id="kpi_quotidiens",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("alertes_capacite"),
            CronTrigger(hour=1, minute=50),
            id="alertes_capacite",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("previsions_quotidiennes"),
            CronTrigger(hour=2, minute=0),
            id="previsions_quotidiennes",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("rapport_quotidien"),
            CronTrigger(hour=6, minute=0),
            id="rapport_quotidien",
            replace_existing=True,
        )
        config = _configuration_modeles()
        jour = JOURS_CRON.get(config["jour_reentrainement"], "mon")
        heure_str, _, minute_str = config["heure_reentrainement"].partition(":")
        heure, minute = int(heure_str or 3), int(minute_str or 0)
        self._scheduler.add_job(
            lambda: executer_tache("hebdomadaire"),
            CronTrigger(day_of_week=jour, hour=heure, minute=minute),
            id="hebdomadaire",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("mensuel"),
            CronTrigger(day=1, hour=4, minute=0),
            id="mensuel",
            replace_existing=True,
        )
        self._scheduler.add_job(
            lambda: executer_tache("annuel"),
            CronTrigger(month=1, day=1, hour=5, minute=0),
            id="annuel",
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
        """(identifiant de tâche, date/heure ISO de la prochaine exécution ou ``None``).

        Tant que le planificateur n'a jamais été démarré, APScheduler n'a pas encore calculé
        ``next_run_time`` (l'attribut n'existe alors pas sur le job)."""
        resultat = []
        for job in self._scheduler.get_jobs():
            prochaine = getattr(job, "next_run_time", None)
            resultat.append((job.id, prochaine.isoformat() if prochaine else None))
        return resultat

    def frequences(self) -> dict[str, str]:
        """Libellé français de la fréquence de chaque tâche (tableau de l'écran
        Administration, onglet Tâches)."""
        config = _configuration_modeles()
        jour = config["jour_reentrainement"].capitalize()
        heure = config["heure_reentrainement"]
        return {**FREQUENCES_FIXES, "hebdomadaire": f"Chaque {jour} à {heure}"}
