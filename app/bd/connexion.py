"""Pool de connexions psycopg2 et gestion des transactions.

Toutes les requêtes passent par :func:`transaction`, qui fournit un curseur
retournant des dictionnaires, valide en fin de bloc et annule en cas
d'erreur. Les erreurs psycopg2 sont traduites en exceptions françaises ; la
trace technique est écrite dans le journal.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
import psycopg2.errorcodes
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from app.config import ConfigBaseDonnees, configuration
from app.erreurs import DonneesInvalides, ErreurApplication, ErreurBaseDonnees
from app.journal import journal

_log = journal(__name__)
_verrou = threading.Lock()
_pool: ThreadedConnectionPool | None = None
_config_forcee: ConfigBaseDonnees | None = None

MESSAGE_CONNEXION = (
    "Impossible de se connecter à la base de données. Vérifiez le fichier config.ini."
)


def definir_configuration(config: ConfigBaseDonnees | None) -> None:
    """Force la configuration de connexion (utilisé par les tests et ``init_bd``)."""
    global _config_forcee
    fermer_pool()
    _config_forcee = config


def configuration_active() -> ConfigBaseDonnees:
    """Configuration de connexion en vigueur."""
    return _config_forcee or configuration().base_de_donnees


def _parametres(config: ConfigBaseDonnees, base: str | None = None) -> dict:
    return {
        "host": config.hote,
        "port": config.port,
        "dbname": base or config.base,
        "user": config.utilisateur,
        "password": config.mot_de_passe,
        "connect_timeout": 5,
        "application_name": "planification_233",
    }


def _obtenir_pool() -> ThreadedConnectionPool:
    global _pool
    with _verrou:
        if _pool is None:
            config = configuration_active()
            try:
                _pool = ThreadedConnectionPool(
                    config.pool_min, config.pool_max, **_parametres(config)
                )
            except psycopg2.Error as exc:
                _log.exception("Échec de création du pool de connexions : %s", exc)
                raise ErreurBaseDonnees(MESSAGE_CONNEXION) from exc
        return _pool


def fermer_pool() -> None:
    """Ferme toutes les connexions du pool."""
    global _pool
    with _verrou:
        if _pool is not None:
            _pool.closeall()
            _pool = None


def traduire_erreur(exc: psycopg2.Error) -> ErreurApplication:
    """Convertit une erreur psycopg2 en exception au message français."""
    code = getattr(exc, "pgcode", None)
    if isinstance(exc, psycopg2.OperationalError) and code is None:
        return ErreurBaseDonnees(MESSAGE_CONNEXION)
    if code == psycopg2.errorcodes.UNIQUE_VIOLATION:
        return DonneesInvalides("Cet élément existe déjà (doublon refusé par la base).")
    if code == psycopg2.errorcodes.FOREIGN_KEY_VIOLATION:
        return DonneesInvalides(
            "Opération refusée : l'élément référencé est introuvable ou encore utilisé."
        )
    if code == psycopg2.errorcodes.CHECK_VIOLATION:
        return DonneesInvalides("Valeur refusée par une règle de cohérence de la base de données.")
    if code == psycopg2.errorcodes.NOT_NULL_VIOLATION:
        return DonneesInvalides("Une valeur obligatoire est manquante.")
    return ErreurBaseDonnees(
        "Erreur lors de l'accès à la base de données. Consultez le journal de l'application."
    )


@contextmanager
def transaction() -> Iterator[psycopg2.extras.RealDictCursor]:
    """Ouvre une transaction et fournit un curseur à lignes « dictionnaire »."""
    pool = _obtenir_pool()
    try:
        connexion = pool.getconn()
    except psycopg2.Error as exc:
        _log.exception("Impossible d'obtenir une connexion : %s", exc)
        raise ErreurBaseDonnees(MESSAGE_CONNEXION) from exc
    casse = False
    try:
        with connexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as curseur:
            yield curseur
        connexion.commit()
    except psycopg2.Error as exc:
        casse = connexion.closed != 0
        if not casse:
            connexion.rollback()
        _log.exception("Erreur SQL : %s", exc)
        raise traduire_erreur(exc) from exc
    except BaseException:
        if connexion.closed == 0:
            connexion.rollback()
        raise
    finally:
        pool.putconn(connexion, close=casse or connexion.closed != 0)


def connexion_administration(config: ConfigBaseDonnees | None = None, base: str | None = None):
    """Connexion directe en mode autocommit (création / suppression de base)."""
    config = config or configuration_active()
    try:
        connexion = psycopg2.connect(**_parametres(config, base or config.base_administration))
    except psycopg2.Error as exc:
        _log.exception("Connexion d'administration impossible : %s", exc)
        raise ErreurBaseDonnees(MESSAGE_CONNEXION) from exc
    connexion.autocommit = True
    return connexion


def tester_connexion() -> bool:
    """Retourne ``True`` si la base répond."""
    with transaction() as cur:
        cur.execute("SELECT 1 AS ok")
        return cur.fetchone()["ok"] == 1
