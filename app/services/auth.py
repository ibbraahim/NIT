"""UC01 · S'authentifier.

- mots de passe hachés par PBKDF2-HMAC-SHA256 (sel aléatoire, 200 000 itérations) ;
- cinq échecs consécutifs verrouillent le compte 15 minutes ;
- un compte inactif est refusé ;
- message d'échec identique quelle que soit la cause ;
- chaque tentative est enregistrée dans ``journal_connexions``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from app.bd.connexion import transaction
from app.bd.depots.utilisateurs import DepotUtilisateurs
from app.contexte import ROLES, Contexte
from app.erreurs import ErreurAuthentification
from app.journal import journal

_log = journal(__name__)

ITERATIONS = 200_000
TAILLE_SEL = 16
MAX_ECHECS = 5
DUREE_VERROUILLAGE = timedelta(minutes=15)

MESSAGE_ECHEC = (
    "Identifiant ou mot de passe incorrect, ou compte indisponible. "
    "Après cinq échecs consécutifs, le compte est verrouillé pendant 15 minutes."
)

# Sel et hash factices : évitent de révéler par le temps de réponse qu'un identifiant n'existe pas.
_SEL_FACTICE = "00" * TAILLE_SEL


def hacher_mot_de_passe(mot_de_passe: str, sel: str | None = None) -> tuple[str, str]:
    """Retourne ``(hash_hex, sel_hex)`` du mot de passe."""
    sel = sel or secrets.token_hex(TAILLE_SEL)
    empreinte = hashlib.pbkdf2_hmac(
        "sha256", mot_de_passe.encode("utf-8"), bytes.fromhex(sel), ITERATIONS
    )
    return empreinte.hex(), sel


def verifier_mot_de_passe(mot_de_passe: str, hash_attendu: str, sel: str) -> bool:
    """Compare en temps constant le mot de passe saisi au hash stocké."""
    calcule, _ = hacher_mot_de_passe(mot_de_passe, sel)
    return hmac.compare_digest(calcule, hash_attendu)


def _maintenant() -> datetime:
    return datetime.now(UTC)


def authentifier(identifiant: str, mot_de_passe: str) -> Contexte:
    """UC01 : authentifie un utilisateur et retourne son contexte.

    Lève :class:`ErreurAuthentification` (message identique quelle que soit la cause).
    """
    identifiant = (identifiant or "").strip()
    mot_de_passe = mot_de_passe or ""
    with transaction() as cur:
        depot = DepotUtilisateurs(cur)
        utilisateur = depot.par_identifiant(identifiant, verrou=True) if identifiant else None
        if utilisateur is None:
            verifier_mot_de_passe(mot_de_passe, "", _SEL_FACTICE)
            depot.journaliser_connexion(None, identifiant or "(vide)", False, "identifiant_inconnu")
            _log.info("Échec de connexion : identifiant inconnu « %s ».", identifiant)
            motif = "identifiant_inconnu"
        else:
            motif = _controler(depot, utilisateur, mot_de_passe)
            depot.journaliser_connexion(utilisateur["id"], identifiant, motif == "succes", motif)
        if motif == "succes":
            sites = frozenset(depot.sites(utilisateur["id"]))
            _log.info("Connexion réussie de « %s ».", utilisateur["identifiant"])
            return Contexte(
                utilisateur_id=utilisateur["id"],
                identifiant=utilisateur["identifiant"],
                role=utilisateur["role"],
                nom_complet=f"{utilisateur['prenom']} {utilisateur['nom']}".strip(),
                sites=sites,
            )
    raise ErreurAuthentification(MESSAGE_ECHEC)


def _controler(depot: DepotUtilisateurs, utilisateur: dict, mot_de_passe: str) -> str:
    """Contrôle verrouillage, activité et mot de passe ; met à jour les compteurs."""
    maintenant = _maintenant()
    verrou = utilisateur["verrouille_jusqu_a"]
    mot_de_passe_ok = verifier_mot_de_passe(
        mot_de_passe, utilisateur["hash_mot_de_passe"], utilisateur["sel"]
    )
    if verrou is not None and verrou > maintenant:
        _log.info("Tentative sur le compte verrouillé « %s ».", utilisateur["identifiant"])
        return "compte_verrouille"
    if not utilisateur["actif"]:
        _log.info("Tentative sur le compte inactif « %s ».", utilisateur["identifiant"])
        return "compte_inactif"
    if utilisateur["role"] not in ROLES:
        return "role_inconnu"
    if not mot_de_passe_ok:
        # Un verrou expiré repart de zéro.
        tentatives = (0 if verrou is not None else utilisateur["tentatives_echouees"]) + 1
        nouveau_verrou = None
        if tentatives >= MAX_ECHECS:
            nouveau_verrou = maintenant + DUREE_VERROUILLAGE
            _log.warning(
                "Compte « %s » verrouillé 15 minutes après %d échecs consécutifs.",
                utilisateur["identifiant"],
                tentatives,
            )
        depot.enregistrer_echec(utilisateur["id"], tentatives, nouveau_verrou)
        return "mot_de_passe_incorrect"
    depot.reinitialiser_tentatives(utilisateur["id"])
    return "succes"
