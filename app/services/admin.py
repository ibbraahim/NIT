"""UC02 · Gérer les utilisateurs et les rôles — UC03 · Gérer les référentiels.

Un élément de référentiel déjà utilisé est désactivé, jamais supprimé :
aucune fonction de ce module ne supprime de site, de zone ou d'équipement.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.bd.connexion import transaction
from app.bd.depots.referentiels import DepotReferentiels
from app.contexte import Contexte
from app.erreurs import DonneesInvalides, OperationImpossible
from app.journal import journal
from app.libelles import CATEGORIES_COUT, STATUTS_EQUIPEMENT, TYPES_EQUIPEMENT
from app.services.droits import verifier_droit, verifier_site
from app.utils import validation
from app.utils.dates import jours_semaine, lundi_de

_log = journal(__name__)


def _valider(regles: dict[str, callable]) -> dict:
    """Exécute des validateurs ``{champ: lambda}`` et agrège les erreurs par champ."""
    resultats, erreurs = {}, {}
    for champ, regle in regles.items():
        try:
            resultats[champ] = regle()
        except ValueError as exc:
            erreurs[champ] = str(exc)
    if erreurs:
        raise DonneesInvalides(
            "Certains champs sont invalides. Corrigez les champs signalés.", erreurs
        )
    return resultats


# =====================================================================
# Lecture des référentiels (tous rôles, filtrée par sites rattachés)
# =====================================================================
def lister_sites(ctx: Contexte, inclure_inactifs: bool = False) -> list[dict]:
    """Sites visibles par l'utilisateur."""
    verifier_droit(ctx, "lecture_referentiels")
    with transaction() as cur:
        ids = None if ctx.voit_tous_les_sites else sorted(ctx.sites)
        return DepotReferentiels(cur).lister_sites(inclure_inactifs, ids)


def lister_zones(
    ctx: Contexte, site_id: int | None = None, inclure_inactives: bool = False
) -> list[dict]:
    """Zones d'un site (ou de tous les sites visibles)."""
    verifier_droit(ctx, "lecture_referentiels")
    if site_id is not None:
        verifier_site(ctx, site_id)
    with transaction() as cur:
        zones = DepotReferentiels(cur).lister_zones(site_id, inclure_inactives)
    return [z for z in zones if ctx.peut_voir_site(z["site_id"])]


def lister_equipements(
    ctx: Contexte, site_id: int | None = None, inclure_inactifs: bool = False
) -> list[dict]:
    """Équipements d'un site."""
    verifier_droit(ctx, "lecture_referentiels")
    if site_id is not None:
        verifier_site(ctx, site_id)
    with transaction() as cur:
        equipements = DepotReferentiels(cur).lister_equipements(site_id, None, inclure_inactifs)
    return [e for e in equipements if ctx.peut_voir_site(e["site_id"])]


def disponibilite_equipements(ctx: Contexte, site_id: int, debut: date, fin: date) -> list[dict]:
    """Équipements disponibles par zone, type et date."""
    verifier_droit(ctx, "lecture_referentiels")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        return DepotReferentiels(cur).equipements_disponibles(site_id, debut, fin)


# =====================================================================
# UC03 · Sites
# =====================================================================
def enregistrer_site(
    ctx: Contexte, nom: str, adresse: str = "", site_id: int | None = None, actif: bool = True
) -> int:
    """Crée (``site_id`` absent) ou modifie un site."""
    verifier_droit(ctx, "UC03")
    donnees = _valider({"nom": lambda: validation.obligatoire(nom, "Nom du site")})
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        existant = depot.site_par_nom(donnees["nom"])
        if existant and existant["id"] != site_id:
            raise DonneesInvalides(
                "Un site porte déjà ce nom.", {"nom": "Un site porte déjà ce nom."}
            )
        if site_id is None:
            site_id = depot.creer_site(donnees["nom"], (adresse or "").strip())
            _log.info("Site « %s » créé par %s.", donnees["nom"], ctx.identifiant)
        else:
            depot.modifier_site(site_id, donnees["nom"], (adresse or "").strip(), actif)
            _log.info("Site n° %s modifié par %s.", site_id, ctx.identifiant)
        return site_id


def desactiver_site(ctx: Contexte, site_id: int) -> None:
    """Désactive un site et ses zones (jamais de suppression)."""
    verifier_droit(ctx, "UC03")
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        if depot.site(site_id) is None:
            raise OperationImpossible("Site introuvable.")
        depot.desactiver_site(site_id)
    _log.info("Site n° %s désactivé par %s.", site_id, ctx.identifiant)


# =====================================================================
# UC03 · Zones
# =====================================================================
def enregistrer_zone(
    ctx: Contexte,
    site_id: int,
    nom: str,
    type_equipement_principal: str,
    duree_poste_heures: float | str,
    zone_id: int | None = None,
    actif: bool = True,
) -> int:
    """Crée ou modifie une zone (type d'équipement principal, durée de poste)."""
    verifier_droit(ctx, "UC03")
    donnees = _valider(
        {
            "nom": lambda: validation.obligatoire(nom, "Nom de la zone"),
            "type_equipement_principal": lambda: _type_equipement(type_equipement_principal),
            "duree_poste_heures": lambda: validation.nombre(
                duree_poste_heures, "Durée de poste (h)", minimum=0.5, maximum=24
            ),
        }
    )
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        site = depot.site(site_id)
        if site is None:
            raise DonneesInvalides("Site inconnu.", {"site": "Site inconnu."})
        existante = depot.zone_par_nom(site_id, donnees["nom"])
        if existante and existante["id"] != zone_id:
            raise DonneesInvalides(
                "Une zone de ce site porte déjà ce nom.",
                {"nom": "Une zone de ce site porte déjà ce nom."},
            )
        if zone_id is None:
            zone_id = depot.creer_zone(
                site_id,
                donnees["nom"],
                donnees["type_equipement_principal"],
                donnees["duree_poste_heures"],
            )
        else:
            depot.modifier_zone(
                zone_id,
                donnees["nom"],
                donnees["type_equipement_principal"],
                donnees["duree_poste_heures"],
                actif,
            )
    _log.info("Zone « %s » enregistrée par %s.", donnees["nom"], ctx.identifiant)
    return zone_id


def desactiver_zone(ctx: Contexte, zone_id: int) -> None:
    """Désactive une zone (jamais de suppression)."""
    verifier_droit(ctx, "UC03")
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        if depot.zone(zone_id) is None:
            raise OperationImpossible("Zone introuvable.")
        depot.desactiver_zone(zone_id)
    _log.info("Zone n° %s désactivée par %s.", zone_id, ctx.identifiant)


def _type_equipement(valeur: str) -> str:
    if valeur not in TYPES_EQUIPEMENT:
        raise ValueError("Choisissez un type d'équipement dans la liste.")
    return valeur


# =====================================================================
# UC03 · Équipements et indisponibilités
# =====================================================================
def enregistrer_equipement(
    ctx: Contexte,
    site_id: int,
    zone_id: int,
    type_equipement: str,
    code: str,
    statut: str = "disponible",
    equipement_id: int | None = None,
    actif: bool = True,
) -> int:
    """Crée ou modifie un équipement."""
    verifier_droit(ctx, "UC03")

    def _statut() -> str:
        if statut not in STATUTS_EQUIPEMENT:
            raise ValueError("Choisissez un statut dans la liste.")
        return statut

    donnees = _valider(
        {
            "code": lambda: validation.obligatoire(code, "Code").upper(),
            "type": lambda: _type_equipement(type_equipement),
            "statut": _statut,
        }
    )
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        zone = depot.zone(zone_id)
        if zone is None or zone["site_id"] != site_id:
            raise DonneesInvalides(
                "La zone choisie n'appartient pas au site.", {"zone": "Zone invalide pour ce site."}
            )
        if equipement_id is None:
            equipement_id = depot.creer_equipement(
                site_id, zone_id, donnees["type"], donnees["code"], donnees["statut"]
            )
        else:
            depot.modifier_equipement(
                equipement_id, zone_id, donnees["type"], donnees["code"], donnees["statut"], actif
            )
    _log.info("Équipement « %s » enregistré par %s.", donnees["code"], ctx.identifiant)
    return equipement_id


def desactiver_equipement(ctx: Contexte, equipement_id: int) -> None:
    """Désactive un équipement (jamais de suppression)."""
    verifier_droit(ctx, "UC03")
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        if depot.equipement(equipement_id) is None:
            raise OperationImpossible("Équipement introuvable.")
        depot.desactiver_equipement(equipement_id)
    _log.info("Équipement n° %s désactivé par %s.", equipement_id, ctx.identifiant)


def declarer_indisponibilite(
    ctx: Contexte, equipement_id: int, date_debut: date | str, date_fin: date | str, motif: str
) -> int:
    """Déclare une période d'indisponibilité (maintenance, panne…)."""
    verifier_droit(ctx, "UC03")
    donnees = _valider(
        {
            "date_debut": lambda: validation.date_saisie(date_debut, "Date de début"),
            "date_fin": lambda: validation.date_saisie(date_fin, "Date de fin"),
            "motif": lambda: validation.obligatoire(motif, "Motif"),
        }
    )
    if donnees["date_fin"] < donnees["date_debut"]:
        raise DonneesInvalides(
            "La date de fin doit être postérieure ou égale à la date de début.",
            {"date_fin": "La date de fin précède la date de début."},
        )
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        if depot.equipement(equipement_id) is None:
            raise OperationImpossible("Équipement introuvable.")
        identifiant = depot.ajouter_indisponibilite(
            equipement_id, donnees["date_debut"], donnees["date_fin"], donnees["motif"]
        )
    _log.info("Indisponibilité déclarée pour l'équipement n° %s.", equipement_id)
    return identifiant


def lister_indisponibilites(ctx: Contexte, site_id: int, debut: date, fin: date) -> list[dict]:
    """Périodes d'indisponibilité recoupant une plage de dates."""
    verifier_droit(ctx, "lecture_referentiels")
    verifier_site(ctx, site_id)
    with transaction() as cur:
        return DepotReferentiels(cur).lister_indisponibilites(site_id, debut, fin)


# =====================================================================
# UC03 · Capacités de personnel
# =====================================================================
def lire_capacites(ctx: Contexte, site_id: int, jour: date) -> dict[tuple[int, date], dict]:
    """Capacités de la semaine contenant ``jour`` : ``{(zone_id, date): {...}}``."""
    verifier_droit(ctx, "lecture_referentiels")
    verifier_site(ctx, site_id)
    lundi = lundi_de(jour)
    with transaction() as cur:
        lignes = DepotReferentiels(cur).capacites(site_id, lundi, lundi + timedelta(days=6))
    return {(ligne["zone_id"], ligne["date_jour"]): ligne for ligne in lignes}


def enregistrer_capacites(
    ctx: Contexte, site_id: int, capacites: dict[tuple[int, date], tuple[int | str, int | str]]
) -> int:
    """Enregistre ``{(zone_id, date): (effectif_planifie, absences_prevues)}``."""
    verifier_droit(ctx, "UC03")
    erreurs: dict[str, str] = {}
    propres: list[tuple[int, date, int, int]] = []
    for (zone_id, jour), (effectif, absences) in capacites.items():
        cle = f"{zone_id}_{jour.isoformat()}"
        try:
            eff = int(validation.nombre(effectif, "Effectif planifié", 0, 10_000, entier=True))
            abs_ = int(validation.nombre(absences or 0, "Absences prévues", 0, 10_000, entier=True))
            if abs_ > eff:
                raise ValueError("Les absences prévues dépassent l'effectif planifié.")
            propres.append((zone_id, jour, eff, abs_))
        except ValueError as exc:
            erreurs[cle] = str(exc)
    if erreurs:
        raise DonneesInvalides("Certaines capacités sont invalides.", erreurs)
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        zones_site = {z["id"] for z in depot.lister_zones(site_id, True)}
        for zone_id, jour, eff, abs_ in propres:
            if zone_id not in zones_site:
                raise DonneesInvalides("Zone inconnue pour ce site.")
            depot.enregistrer_capacite(site_id, zone_id, jour, eff, abs_)
    _log.info("%d capacités enregistrées par %s.", len(propres), ctx.identifiant)
    return len(propres)


def copier_semaine_precedente(ctx: Contexte, site_id: int, jour: date) -> int:
    """Copie les capacités de la semaine précédente sur la semaine contenant ``jour``."""
    verifier_droit(ctx, "UC03")
    lundi = lundi_de(jour)
    precedent = lundi - timedelta(days=7)
    with transaction() as cur:
        depot = DepotReferentiels(cur)
        sources = depot.capacites(site_id, precedent, precedent + timedelta(days=6))
        if not sources:
            raise OperationImpossible("La semaine précédente ne contient aucune capacité à copier.")
        for ligne in sources:
            depot.enregistrer_capacite(
                site_id,
                ligne["zone_id"],
                ligne["date_jour"] + timedelta(days=7),
                ligne["effectif_planifie"],
                ligne["absences_prevues"],
            )
    _log.info("Capacités copiées vers la semaine du %s par %s.", lundi, ctx.identifiant)
    return len(sources)


def jours_de_la_semaine(jour: date) -> list[date]:
    """Les 7 jours (lundi → dimanche) de la semaine contenant ``jour``."""
    return jours_semaine(lundi_de(jour))


# =====================================================================
# UC03 · Coûts horaires
# =====================================================================
def lister_couts(ctx: Contexte) -> list[dict]:
    """Historique des coûts horaires par catégorie."""
    verifier_droit(ctx, "lecture_referentiels")
    with transaction() as cur:
        return DepotReferentiels(cur).lister_couts()


def enregistrer_cout(
    ctx: Contexte, categorie: str, taux: float | str, devise: str, date_debut: date | str
) -> None:
    """Enregistre un coût horaire applicable à partir d'une date."""
    verifier_droit(ctx, "UC03")

    def _categorie() -> str:
        if categorie not in CATEGORIES_COUT:
            raise ValueError("Catégorie de coût inconnue.")
        return categorie

    def _devise() -> str:
        texte = validation.obligatoire(devise, "Devise").upper()
        if len(texte) != 3 or not texte.isalpha():
            raise ValueError("La devise doit être un code de 3 lettres (ex. MAD, EUR).")
        return texte

    donnees = _valider(
        {
            "categorie": _categorie,
            "taux": lambda: validation.nombre(taux, "Taux horaire", 0, 100_000),
            "devise": _devise,
            "date_debut": lambda: validation.date_saisie(date_debut, "Date de début"),
        }
    )
    with transaction() as cur:
        DepotReferentiels(cur).enregistrer_cout(
            donnees["categorie"], donnees["taux"], donnees["devise"], donnees["date_debut"]
        )
    _log.info("Coût horaire « %s » enregistré par %s.", categorie, ctx.identifiant)


# =====================================================================
# État général de l'application (bandeau de démonstration, barre d'état)
# =====================================================================
def etat_application(ctx: Contexte) -> dict:
    """Drapeau « données de démonstration » et date de dernière synchronisation."""
    verifier_droit(ctx, "lecture_referentiels")
    from app.bd.depots.parametres import DepotParametres

    with transaction() as cur:
        parametres = DepotParametres(cur)
        demo = parametres.lire("donnees_demonstration", "non") == "oui"
        synchro = parametres.lire("derniere_synchronisation")
        cur.execute("SELECT max(date_maj) AS derniere FROM historique_activite")
        derniere_maj = cur.fetchone()["derniere"]
    return {
        "demonstration": demo,
        "derniere_synchronisation": synchro,
        "derniere_mise_a_jour_historique": derniere_maj,
    }
