"""Lecture de la configuration (config.ini)."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app import RACINE
from app.erreurs import ErreurConfiguration

CHEMIN_CONFIG_DEFAUT = RACINE / "config.ini"

DOSSIER_JOURNAUX = RACINE / "journaux"
DOSSIER_RAPPORTS = RACINE / "rapports"
DOSSIER_MODELES = RACINE / "modeles_enregistres"
DOSSIER_ENTREES_HISTORIQUE = RACINE / "entrees" / "historique"
DOSSIER_ENTREES_TRAITES = RACINE / "entrees" / "traites"
DOSSIER_RESSOURCES = RACINE / "ressources"
DOSSIER_POLICES = DOSSIER_RESSOURCES / "polices"
DOSSIER_MODELES_FICHIERS = DOSSIER_RESSOURCES / "modeles_fichiers"


@dataclass(frozen=True)
class ConfigBaseDonnees:
    """Paramètres de connexion PostgreSQL."""

    hote: str
    port: int
    base: str
    utilisateur: str
    mot_de_passe: str
    base_administration: str = "postgres"
    pool_min: int = 1
    pool_max: int = 8

    def avec_base(self, base: str) -> ConfigBaseDonnees:
        """Retourne une copie pointant vers une autre base (base de test, par exemple)."""
        return ConfigBaseDonnees(
            self.hote,
            self.port,
            base,
            self.utilisateur,
            self.mot_de_passe,
            self.base_administration,
            self.pool_min,
            self.pool_max,
        )


@dataclass(frozen=True)
class Configuration:
    """Configuration complète de l'application."""

    base_de_donnees: ConfigBaseDonnees
    devise: str = "MAD"
    niveau_journal: str = "INFO"


def charger_configuration(chemin: Path | None = None) -> Configuration:
    """Lit ``config.ini`` et retourne la configuration.

    Le chemin peut être forcé par la variable d'environnement ``PLANIF_CONFIG``.
    Lève :class:`ErreurConfiguration` avec un message français si le fichier
    est absent ou incomplet.
    """
    chemin = chemin or Path(os.environ.get("PLANIF_CONFIG", CHEMIN_CONFIG_DEFAUT))
    if not chemin.is_file():
        raise ErreurConfiguration(
            f"Le fichier de configuration « {chemin.name} » est introuvable. "
            "Copiez config.exemple.ini en config.ini puis renseignez les paramètres de connexion."
        )
    lecteur = configparser.ConfigParser()
    try:
        lecteur.read(chemin, encoding="utf-8")
        section = lecteur["base_de_donnees"]
        bd = ConfigBaseDonnees(
            hote=section["hote"],
            port=int(section.get("port", "5432")),
            base=section["base"],
            utilisateur=section["utilisateur"],
            mot_de_passe=section["mot_de_passe"],
            base_administration=section.get("base_administration", "postgres"),
            pool_min=int(section.get("pool_min", "1")),
            pool_max=int(section.get("pool_max", "8")),
        )
    except (KeyError, ValueError, configparser.Error) as exc:
        raise ErreurConfiguration(
            "Le fichier config.ini est incomplet : la section [base_de_donnees] doit contenir "
            "hote, port, base, utilisateur et mot_de_passe."
        ) from exc
    application = lecteur["application"] if lecteur.has_section("application") else {}
    return Configuration(
        base_de_donnees=bd,
        devise=application.get("devise", "MAD"),
        niveau_journal=application.get("niveau_journal", "INFO").upper(),
    )


@lru_cache(maxsize=1)
def configuration() -> Configuration:
    """Configuration chargée une seule fois (mise en cache)."""
    return charger_configuration()
