"""Générateur du jeu de démonstration « Plateforme Casablanca » (graine 42).

Lot 1 : référentiels (site, zones, équipements), comptes de démonstration,
capacités de personnel (même planning chaque semaine) et coûts horaires.
Les lots suivants ajoutent l'historique, les prévisions et les plans.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import date, timedelta

from app.bd.connexion import transaction
from app.bd.depots.parametres import DepotParametres
from app.bd.depots.referentiels import DepotReferentiels
from app.bd.depots.utilisateurs import DepotUtilisateurs
from app.config import DOSSIER_RESSOURCES
from app.journal import journal
from app.services.auth import hacher_mot_de_passe
from app.utils.dates import lundi_de

_log = journal(__name__)

GRAINE = 42
NOM_SITE = "Plateforme Casablanca"
ADRESSE_SITE = "Zone logistique (adresse fictive de démonstration), Casablanca"
DUREE_POSTE = 7.5
MOIS_HISTORIQUE = 18
FICHIER_COMPTES = DOSSIER_RESSOURCES / "demo" / "comptes_demo.csv"

#: (nom, type d'équipement principal, préfixe de code, nombre d'équipements, effectif planifié)
ZONES_DEMO = [
    ("Réception", "chariot_elevateur", "CE", 4, 10),
    ("Stockage", "chariot_elevateur", "CE", 4, 8),
    ("Préparation", "transpalette_electrique", "TP", 5, 16),
    ("Expédition", "transpalette_electrique", "TP", 5, 8),
]

#: Coûts horaires de démonstration (MAD).
COUTS_DEMO = {"interne": 45.0, "heures_sup": 56.25, "interim": 58.0}

#: Jours ouvrés : lundi (0) à samedi (5) ; le dimanche la plateforme est fermée.
JOURS_OUVRES = {0, 1, 2, 3, 4, 5}


def date_debut_historique(date_reference: date) -> date:
    """Premier jour de l'historique : 18 mois avant la date de référence."""
    mois = date_reference.year * 12 + date_reference.month - 1 - MOIS_HISTORIQUE
    return date(mois // 12, mois % 12 + 1, 1)


def semaine_demonstration(date_reference: date) -> date:
    """Lundi de la semaine suivant la date de référence."""
    return lundi_de(date_reference) + timedelta(days=7)


def lire_comptes_demo() -> list[dict]:
    """Comptes de démonstration (un par rôle), lus dans ``ressources/demo``."""
    with FICHIER_COMPTES.open(encoding="utf-8") as fichier:
        return list(csv.DictReader(fichier, delimiter=";"))


def generer_demonstration(
    date_reference: date | None = None, afficher: Callable[[str], None] = print
) -> dict:
    """Génère l'ensemble du jeu de démonstration et retourne ses identifiants clés."""
    date_reference = date_reference or date.today()
    resultat = generer_referentiels(date_reference)
    afficher(f"Référentiels de démonstration créés ({NOM_SITE}).")
    _log.info("Jeu de démonstration généré (date de référence %s).", date_reference)
    return resultat


def generer_referentiels(date_reference: date) -> dict:
    """Site, zones, équipements, comptes, capacités et coûts de démonstration."""
    with transaction() as cur:
        ref = DepotReferentiels(cur)
        site_id = ref.creer_site(NOM_SITE, ADRESSE_SITE)
        zones: dict[str, int] = {}
        compteurs = {"CE": 0, "TP": 0}
        for nom, type_eqp, prefixe, nombre, _effectif in ZONES_DEMO:
            zone_id = ref.creer_zone(site_id, nom, type_eqp, DUREE_POSTE)
            zones[nom] = zone_id
            for _ in range(nombre):
                compteurs[prefixe] += 1
                ref.creer_equipement(
                    site_id, zone_id, type_eqp, f"{prefixe}-{compteurs[prefixe]:02d}", "disponible"
                )

        # Capacité volontairement identique d'une semaine à l'autre.
        debut = date_debut_historique(date_reference)
        fin = semaine_demonstration(date_reference) + timedelta(days=27)
        jour = debut
        while jour <= fin:
            for nom, _type, _prefixe, _nombre, effectif in ZONES_DEMO:
                ouvert = jour.weekday() in JOURS_OUVRES
                ref.enregistrer_capacite(site_id, zones[nom], jour, effectif if ouvert else 0, 0)
            jour += timedelta(days=1)

        for categorie, taux in COUTS_DEMO.items():
            ref.enregistrer_cout(categorie, taux, "MAD", debut)

        utilisateurs = DepotUtilisateurs(cur)
        comptes = {}
        for compte in lire_comptes_demo():
            hash_mdp, sel = hacher_mot_de_passe(compte["mot_de_passe"])
            existant = utilisateurs.par_identifiant(compte["identifiant"])
            if existant:
                utilisateurs.definir_mot_de_passe(existant["id"], hash_mdp, sel)
                utilisateurs.modifier(
                    existant["id"], compte["nom"], compte["prenom"], compte["email"], compte["role"]
                )
                utilisateur_id = existant["id"]
            else:
                utilisateur_id = utilisateurs.creer(
                    compte["identifiant"],
                    compte["nom"],
                    compte["prenom"],
                    compte["email"],
                    hash_mdp,
                    sel,
                    compte["role"],
                )
            if compte["role"] != "administrateur":
                utilisateurs.definir_sites(utilisateur_id, [site_id])
            comptes[compte["identifiant"]] = utilisateur_id

        parametres = DepotParametres(cur)
        parametres.ecrire("donnees_demonstration", "oui")
        parametres.ecrire("date_reference_demonstration", date_reference.isoformat())
    return {"site_id": site_id, "zones": zones, "comptes": comptes}
