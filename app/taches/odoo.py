"""Connexion à Odoo (ERP) par son API externe XML-RPC, sans bibliothèque supplémentaire.

Workly lit Odoo lui-même : l'orchestrateur (Fusion, n8n) se contente de déclencher la tâche par
HTTP, comme pour toutes les autres. Tout se règle par variables d'environnement (jamais dans le
dépôt) ; sans elles, la connexion est simplement désactivée.

    WORKLY_ODOO_URL           adresse d'Odoo, par exemple https://monentreprise.odoo.com
    WORKLY_ODOO_BASE          nom de la base Odoo (pour Odoo en ligne : le préfixe de l'adresse)
    WORKLY_ODOO_UTILISATEUR   identifiant de connexion (adresse e-mail)
    WORKLY_ODOO_CLE           clé API (Odoo > Préférences > Sécurité du compte > Nouvelle clé API)
"""

from __future__ import annotations

import os
import socket
import xmlrpc.client

from app.journal import journal

_log = journal(__name__)

DELAI_ODOO_S = 20


class ErreurOdoo(Exception):
    """Odoo injoignable, identifiants refusés ou réponse inattendue."""


def configuration() -> dict | None:
    """Réglages lus dans l'environnement, ou ``None`` si la connexion n'est pas configurée."""
    url = os.environ.get("WORKLY_ODOO_URL", "").strip().rstrip("/")
    base = os.environ.get("WORKLY_ODOO_BASE", "").strip()
    utilisateur = os.environ.get("WORKLY_ODOO_UTILISATEUR", "").strip()
    cle = os.environ.get("WORKLY_ODOO_CLE", "")
    if not (url and base and utilisateur and cle):
        return None
    return {"url": url, "base": base, "utilisateur": utilisateur, "cle": cle}


def _proxy(url: str, service: str) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/{service}", allow_none=True)


def tester_connexion() -> dict:
    """Vérifie l'adresse, la base et la clé API ; renvoie la version d'Odoo et le nombre de
    commandes de vente visibles. Lève ``ErreurOdoo`` avec un message lisible, sans jamais
    écrire la clé."""
    reglages = configuration()
    if reglages is None:
        raise ErreurOdoo(
            "Odoo non configuré : définissez WORKLY_ODOO_URL, WORKLY_ODOO_BASE, "
            "WORKLY_ODOO_UTILISATEUR et WORKLY_ODOO_CLE."
        )
    ancien_delai = socket.getdefaulttimeout()
    socket.setdefaulttimeout(DELAI_ODOO_S)
    try:
        version = _proxy(reglages["url"], "common").version()
        uid = _proxy(reglages["url"], "common").authenticate(
            reglages["base"], reglages["utilisateur"], reglages["cle"], {}
        )
        if not uid:
            raise ErreurOdoo(
                "Identifiants refusés : vérifiez la base, l'utilisateur et la clé API."
            )
        commandes = _proxy(reglages["url"], "object").execute_kw(
            reglages["base"], uid, reglages["cle"], "sale.order", "search_count", [[]]
        )
    except ErreurOdoo:
        raise
    except xmlrpc.client.Fault as exc:
        raise ErreurOdoo(f"Odoo a refusé la requête : {exc.faultString.splitlines()[-1]}") from exc
    except (OSError, xmlrpc.client.ProtocolError) as exc:
        raise ErreurOdoo(f"Odoo injoignable à l'adresse {reglages['url']} ({exc}).") from exc
    finally:
        socket.setdefaulttimeout(ancien_delai)
    _log.info("Connexion Odoo réussie (version %s).", version.get("server_version"))
    return {
        "version": version.get("server_version", "inconnue"),
        "base": reglages["base"],
        "commandes_vente": commandes,
    }
