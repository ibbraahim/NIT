"""Sauvegarde quotidienne de la base PostgreSQL (``pg_dump``, format compressé).

Un fichier ``workly_AAAAMMJJ_HHMMSS.dump`` est écrit dans ``sauvegardes/`` ; seules les
``WORKLY_SAUVEGARDES_CONSERVEES`` copies les plus récentes (14 par défaut) sont gardées. Le mot de
passe de la base est transmis à ``pg_dump`` par l'environnement du processus, jamais sur la ligne
de commande ni dans les journaux. Pour restaurer :
``pg_restore --clean --if-exists -d <base> sauvegardes/<fichier>.dump``.

``pg_dump`` est cherché dans cet ordre : variable ``WORKLY_PG_DUMP``, le ``PATH``, puis les
dossiers d'installation habituels de PostgreSQL sous Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from app.config import DOSSIER_SAUVEGARDES, configuration
from app.erreurs import ErreurApplication
from app.journal import journal

_log = journal(__name__)

PREFIXE = "workly_"
SUFFIXE = ".dump"
CONSERVEES_DEFAUT = 14
DELAI_MAX_S = 1800


def trouver_pg_dump() -> str:
    """Chemin de ``pg_dump``, ou erreur explicite si PostgreSQL n'est pas trouvé."""
    force = os.environ.get("WORKLY_PG_DUMP", "").strip()
    if force:
        if Path(force).is_file():
            return force
        raise ErreurApplication(f"WORKLY_PG_DUMP pointe vers un fichier introuvable : {force}")
    trouve = shutil.which("pg_dump")
    if trouve:
        return trouve
    for racine in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if racine:
            versions = sorted(Path(racine, "PostgreSQL").glob("*/bin/pg_dump.exe"), reverse=True)
            if versions:
                return str(versions[0])
    raise ErreurApplication(
        "pg_dump est introuvable. Installez les outils PostgreSQL ou renseignez la variable "
        "d'environnement WORKLY_PG_DUMP avec le chemin complet de pg_dump."
    )


def _nombre_a_conserver() -> int:
    try:
        return max(1, int(os.environ.get("WORKLY_SAUVEGARDES_CONSERVEES", CONSERVEES_DEFAUT)))
    except ValueError:
        return CONSERVEES_DEFAUT


def purger(dossier: Path, conserver: int) -> int:
    """Supprime les sauvegardes les plus anciennes ; renvoie le nombre de fichiers supprimés."""
    copies = sorted(dossier.glob(f"{PREFIXE}*{SUFFIXE}"), key=lambda f: f.name, reverse=True)
    for ancienne in copies[conserver:]:
        ancienne.unlink()
    return max(len(copies) - conserver, 0)


def sauvegarder_base(dossier: Path | None = None, maintenant: datetime | None = None) -> str:
    """Sauvegarde la base et purge les anciennes copies. Renvoie un message de synthèse."""
    dossier = dossier or DOSSIER_SAUVEGARDES
    bd = configuration().base_de_donnees
    pg_dump = trouver_pg_dump()
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = (maintenant or datetime.now()).strftime("%Y%m%d_%H%M%S")
    fichier = dossier / f"{PREFIXE}{horodatage}{SUFFIXE}"
    commande = [
        pg_dump,
        "--format=custom",
        "--host",
        bd.hote,
        "--port",
        str(bd.port),
        "--username",
        bd.utilisateur,
        "--file",
        str(fichier),
        bd.base,
    ]
    try:
        resultat = subprocess.run(
            commande,
            env={**os.environ, "PGPASSWORD": bd.mot_de_passe},
            capture_output=True,
            text=True,
            timeout=DELAI_MAX_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        fichier.unlink(missing_ok=True)
        raise ErreurApplication("La sauvegarde de la base a dépassé le délai autorisé.") from exc
    if resultat.returncode != 0 or not fichier.is_file():
        fichier.unlink(missing_ok=True)
        _log.error("pg_dump a échoué (code %s) : %s", resultat.returncode, resultat.stderr.strip())
        raise ErreurApplication(
            "La sauvegarde de la base a échoué. Consultez le journal de l'application."
        )
    supprimees = purger(dossier, _nombre_a_conserver())
    taille_ko = max(fichier.stat().st_size // 1024, 1)
    return (
        f"Sauvegarde « {fichier.name} » créée ({taille_ko} Ko) ; "
        f"{supprimees} ancienne(s) copie(s) supprimée(s)."
    )
