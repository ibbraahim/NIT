"""Création et initialisation de la base de données.

Utilisation :

    python -m app.bd.init_bd                 crée la base, les tables, le catalogue des KPI,
                                             les cibles par défaut et le compte administrateur
    python -m app.bd.init_bd --demo          ajoute les données de démonstration
    python -m app.bd.init_bd --reinitialiser supprime puis recrée la base (confirmation demandée)

Le mot de passe administrateur est demandé en console (ou lu dans la variable
d'environnement ``PLANIF_MOT_DE_PASSE_ADMIN`` pour une installation automatisée).
"""

from __future__ import annotations

import getpass
import os
import sys
from datetime import date
from pathlib import Path

from psycopg2 import sql

from app.bd import connexion as bd
from app.bd.catalogue_kpi import CATALOGUE, objectifs_par_defaut
from app.bd.depots.parametres import DepotParametres
from app.bd.depots.utilisateurs import DepotUtilisateurs
from app.config import ConfigBaseDonnees, configuration
from app.erreurs import ErreurApplication
from app.journal import configurer_journal, journal
from app.services.auth import hacher_mot_de_passe
from app.utils import validation
from app.utils.cli import AnalyseurFrancais

_log = journal(__name__)
CHEMIN_SCHEMA = Path(__file__).with_name("schema.sql")


def base_existe(config: ConfigBaseDonnees) -> bool:
    """Vrai si la base configurée existe sur le serveur."""
    connexion = bd.connexion_administration(config)
    try:
        with connexion.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config.base,))
            return cur.fetchone() is not None
    finally:
        connexion.close()


def supprimer_base(config: ConfigBaseDonnees) -> None:
    """Supprime la base (les connexions ouvertes sont d'abord fermées)."""
    bd.fermer_pool()
    connexion = bd.connexion_administration(config)
    try:
        with connexion.cursor() as cur:
            cur.execute(
                """SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                   WHERE datname = %s AND pid <> pg_backend_pid()""",
                (config.base,),
            )
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(config.base)))
    finally:
        connexion.close()
    _log.info("Base « %s » supprimée.", config.base)


def creer_base(config: ConfigBaseDonnees) -> None:
    """Crée la base vide (encodage UTF-8)."""
    connexion = bd.connexion_administration(config)
    try:
        with connexion.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(
                    sql.Identifier(config.base)
                )
            )
    finally:
        connexion.close()
    _log.info("Base « %s » créée.", config.base)


def creer_schema(config: ConfigBaseDonnees) -> None:
    """Exécute ``schema.sql`` puis insère le catalogue des KPI et les cibles par défaut."""
    bd.definir_configuration(config)
    with bd.transaction() as cur:
        cur.execute(CHEMIN_SCHEMA.read_text(encoding="utf-8"))
        inserer_catalogue_kpi(cur)
        DepotParametres(cur).ecrire("donnees_demonstration", "non")
        DepotParametres(cur).ecrire("date_initialisation", date.today().isoformat())


def inserer_catalogue_kpi(cur) -> None:
    """Insère les 20 KPI et leurs objectifs généraux par défaut."""
    ids: dict[str, int] = {}
    for ordre, kpi in enumerate(CATALOGUE, start=1):
        cur.execute(
            """INSERT INTO kpi_definitions (code, libelle, famille, formule, unite, sens,
                                            par_methode, ordre)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                kpi.code,
                kpi.libelle,
                kpi.famille,
                kpi.formule,
                kpi.unite,
                kpi.sens,
                kpi.par_methode,
                ordre,
            ),
        )
        ids[kpi.code] = cur.fetchone()["id"]
    sens = {kpi.code: kpi.sens for kpi in CATALOGUE}
    for obj in objectifs_par_defaut():
        cur.execute(
            """INSERT INTO objectifs_kpi (kpi_id, periodicite, sens, valeur_cible, seuil_orange,
                                          seuil_rouge, valeur_min, valeur_max, seuils_relatifs,
                                          date_debut_validite)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, DATE '2000-01-01')""",
            (
                ids[obj.code],
                obj.periodicite,
                sens[obj.code],
                obj.valeur_cible,
                obj.seuil_orange,
                obj.seuil_rouge,
                obj.valeur_min,
                obj.valeur_max,
                obj.seuils_relatifs,
            ),
        )


def creer_administrateur(identifiant: str, mot_de_passe: str) -> int:
    """Crée le compte administrateur initial."""
    identifiant = validation.identifiant(identifiant)
    validation.mot_de_passe(mot_de_passe)
    hash_mdp, sel = hacher_mot_de_passe(mot_de_passe)
    with bd.transaction() as cur:
        return DepotUtilisateurs(cur).creer(
            identifiant, "Administrateur", "", "", hash_mdp, sel, "administrateur"
        )


def initialiser(
    config: ConfigBaseDonnees,
    mot_de_passe_admin: str,
    identifiant_admin: str = "admin",
    reinitialiser: bool = False,
    demo: bool = False,
    date_reference: date | None = None,
    afficher=print,
) -> None:
    """Crée la base complète ; ``demo=True`` ajoute les données de démonstration."""
    validation.mot_de_passe(mot_de_passe_admin)
    if base_existe(config):
        if not reinitialiser:
            raise ErreurApplication(
                f"La base « {config.base} » existe déjà. "
                "Relancez avec --reinitialiser pour la supprimer et la recréer."
            )
        supprimer_base(config)
        afficher(f"Base « {config.base} » supprimée.")
    creer_base(config)
    afficher(f"Base « {config.base} » créée.")
    try:
        creer_schema(config)
        afficher("Tables, catalogue des KPI et cibles par défaut créés.")
        creer_administrateur(identifiant_admin, mot_de_passe_admin)
        afficher(f"Compte administrateur « {identifiant_admin} » créé.")
    except Exception:
        # Une base à moitié créée est supprimée pour pouvoir relancer proprement.
        supprimer_base(config)
        raise
    if demo:
        from app.demo.generateur import generer_demonstration

        generer_demonstration(date_reference=date_reference, afficher=afficher)
        afficher("Données de démonstration générées.")


def _demander_mot_de_passe(demo: bool) -> str:
    depuis_env = os.environ.get("PLANIF_MOT_DE_PASSE_ADMIN")
    if depuis_env:
        return depuis_env
    if demo:
        from app.demo.generateur import lire_comptes_demo

        compte = next(c for c in lire_comptes_demo() if c["role"] == "administrateur")
        print("Mode démonstration : mot de passe administrateur de démonstration (voir README).")
        return compte["mot_de_passe"]
    while True:
        premier = getpass.getpass("Mot de passe du compte administrateur : ")
        try:
            validation.mot_de_passe(premier)
        except ValueError as exc:
            print(exc)
            continue
        if getpass.getpass("Confirmez le mot de passe : ") == premier:
            return premier
        print("Les deux saisies sont différentes. Recommencez.")


def principal(arguments: list[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    analyseur = AnalyseurFrancais(
        prog="python -m app.bd.init_bd",
        description="Crée et initialise la base de données de l'application.",
    )
    analyseur.add_argument(
        "--demo", action="store_true", help="ajoute les données de démonstration"
    )
    analyseur.add_argument(
        "--reinitialiser", action="store_true", help="supprime puis recrée la base si elle existe"
    )
    analyseur.add_argument(
        "--oui", action="store_true", help="ne demande pas de confirmation avant suppression"
    )
    analyseur.add_argument(
        "--identifiant-admin",
        default="admin",
        help="identifiant du compte administrateur (défaut : admin)",
    )
    analyseur.add_argument(
        "--date-reference",
        default=None,
        help="date du jour simulée pour la démonstration (JJ/MM/AAAA)",
    )
    options = analyseur.parse_args(arguments)
    configurer_journal()
    try:
        config = configuration().base_de_donnees
        if options.reinitialiser and not options.oui and base_existe(config):
            reponse = input(
                f"La base « {config.base} » va être supprimée définitivement. "
                "Tapez OUI pour confirmer : "
            )
            if reponse.strip() != "OUI":
                print("Opération abandonnée.")
                return 1
        date_reference = (
            validation.date_saisie(options.date_reference, "Date de référence")
            if options.date_reference
            else None
        )
        initialiser(
            config,
            _demander_mot_de_passe(options.demo),
            options.identifiant_admin,
            options.reinitialiser,
            options.demo,
            date_reference,
        )
    except ErreurApplication as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - toute erreur est traduite en français
        _log.exception("Échec de l'initialisation : %s", exc)
        print(
            "Erreur inattendue pendant l'initialisation. Consultez journaux/application.log.",
            file=sys.stderr,
        )
        return 1
    finally:
        bd.fermer_pool()
    print("Initialisation terminée.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
