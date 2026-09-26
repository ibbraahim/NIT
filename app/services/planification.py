"""UC11 · Générer les prévisions de ressources (RL et RN) — UC12 · Élaborer le plan de
charge (inclut UC11) — UC13 · Simuler un scénario (étend UC12) — UC14 · Valider le plan de
charge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.bd.connexion import transaction
from app.bd.depots.historique import DepotHistorique
from app.bd.depots.modeles import DepotModeles
from app.bd.depots.plans import DepotPlansCharge, DepotScenarios
from app.bd.depots.previsions import DepotPrevisionsVolume
from app.bd.depots.previsions_ressources import DepotPrevisionsRessources
from app.bd.depots.referentiels import DepotReferentiels
from app.contexte import Contexte
from app.erreurs import ConflitMiseAJour, DonneesInvalides, OperationImpossible
from app.journal import journal
from app.libelles import METHODES_COURTES, STATUTS_PLAN
from app.ml import prediction, preparation
from app.ml.entrainement import LIBELLES_METHODES, METHODES
from app.services import modeles as service_modeles
from app.services.droits import verifier_droit, verifier_site
from app.utils import validation
from app.utils.dates import jours_semaine, lundi_de
from app.utils.format_fr import formater_date
from app.utils.progression import Progression, signaler

_log = journal(__name__)

HORIZONS_VALIDES = (7, 14, 28)
TAILLE_FENETRE_MOBILE = 7
STATUTS_MODIFIABLES = ("brouillon", "rejete")


# =====================================================================
# UC11 · Générer les prévisions de ressources
# =====================================================================
@dataclass
class ResumeGenerationPrevisions:
    """Résultat de :func:`generer_previsions`."""

    nb_lignes: int = 0
    avertissements: list[str] = field(default_factory=list)


def generer_previsions(
    ctx: Contexte,
    site_id: int,
    zone_id: int | None = None,
    horizon_jours: int = 7,
    progression: Progression | None = None,
) -> ResumeGenerationPrevisions:
    """UC11 : calcule, avec RL et RN, les heures, l'effectif et les équipements nécessaires
    pour chaque date de l'horizon. Une date sans volume prévu est ignorée et signalée."""
    verifier_droit(ctx, "UC11")
    verifier_site(ctx, site_id)
    if horizon_jours not in HORIZONS_VALIDES:
        raise ValueError(f"Horizon invalide : « {horizon_jours} » jours.")

    resume = ResumeGenerationPrevisions()
    debut = date.today() + timedelta(days=1)
    dates_horizon = [debut + timedelta(days=i) for i in range(horizon_jours)]

    with transaction() as cur:
        ref = DepotReferentiels(cur)
        zones = [ref.zone(zone_id)] if zone_id is not None else ref.lister_zones(site_id)
        zones = [z for z in zones if z is not None]
        depot_volume = DepotPrevisionsVolume(cur)
        depot_historique = DepotHistorique(cur)
        depot_modeles = DepotModeles(cur)
        depot_previsions = DepotPrevisionsRessources(cur)

        horodatage = datetime.now()
        lignes_a_inserer: list[dict] = []
        etapes = max(len(zones) * len(METHODES), 1)
        etape = 0
        for zone in zones:
            volumes_zone = {
                p["date_jour"]: p
                for p in depot_volume.lister([site_id], zone["id"], debut, dates_horizon[-1])
            }
            dates_disponibles = [d for d in dates_horizon if d in volumes_zone]
            if len(dates_disponibles) < len(dates_horizon):
                resume.avertissements.append(
                    f"Zone « {zone['nom']} » : volume prévu manquant pour "
                    f"{len(dates_horizon) - len(dates_disponibles)} date(s) (ignorées)."
                )
            if not dates_disponibles:
                etape += len(METHODES)
                continue
            historique_recent = depot_historique.dernieres_lignes(
                site_id, zone["id"], dates_disponibles[0], TAILLE_FENETRE_MOBILE
            )

            for methode in METHODES:
                etape += 1
                signaler(
                    progression,
                    etape / etapes,
                    f"Zone « {zone['nom']} » — {LIBELLES_METHODES[methode]}…",
                )
                version_heures = depot_modeles.version_active(
                    site_id, zone["id"], methode, "heures"
                )
                version_eqp = depot_modeles.version_active(
                    site_id, zone["id"], methode, "equipements"
                )
                if version_heures is None or version_eqp is None:
                    resume.avertissements.append(
                        f"Zone « {zone['nom']} » : aucun modèle actif pour "
                        f"{LIBELLES_METHODES[methode]} ; méthode ignorée."
                    )
                    continue

                variables_actives = version_heures["parametres"]["variables_actives"]
                dates_completes = [h["date_jour"] for h in historique_recent] + dates_disponibles
                volumes_completes = [h["volume_traite"] for h in historique_recent] + [
                    volumes_zone[d]["volume_prevu"] for d in dates_disponibles
                ]
                pics_completes = [h["indicateur_pic"] for h in historique_recent] + [
                    volumes_zone[d]["indicateur_pic"] for d in dates_disponibles
                ]
                x_complet = preparation.construire_variables(
                    dates_completes, volumes_completes, pics_completes, variables_actives
                )
                x_horizon = x_complet.iloc[len(historique_recent) :].reset_index(drop=True)
                masque = preparation.lignes_utilisables(x_horizon).to_numpy()
                dates_valides = [
                    d for d, garder in zip(dates_disponibles, masque, strict=True) if garder
                ]
                if not dates_valides:
                    resume.avertissements.append(
                        f"Zone « {zone['nom']} », {LIBELLES_METHODES[methode]} : historique "
                        "insuffisant pour calculer la moyenne mobile ; méthode ignorée."
                    )
                    continue
                x_valide = x_horizon[masque].reset_index(drop=True)

                pipeline_heures = service_modeles.charger_pipeline(version_heures["chemin_fichier"])
                pipeline_eqp = service_modeles.charger_pipeline(version_eqp["chemin_fichier"])
                pred_heures = prediction.predire(
                    pipeline_heures,
                    x_valide,
                    version_heures["metriques"]["quantile_bas"],
                    version_heures["metriques"]["quantile_haut"],
                )
                pred_eqp = prediction.predire(
                    pipeline_eqp,
                    x_valide,
                    version_eqp["metriques"]["quantile_bas"],
                    version_eqp["metriques"]["quantile_haut"],
                )

                for i, jour in enumerate(dates_valides):
                    heures = float(pred_heures["prediction"].iloc[i])
                    lignes_a_inserer.append(
                        {
                            "site_id": site_id,
                            "zone_id": zone["id"],
                            "date_jour": jour,
                            "modele_version_id": version_heures["id"],
                            "modele_version_equipements_id": version_eqp["id"],
                            "methode": methode,
                            "volume_prevu": volumes_zone[jour]["volume_prevu"],
                            "heures": heures,
                            "effectif": prediction.heures_vers_effectif(
                                heures, zone["duree_poste_heures"]
                            ),
                            "equipements": prediction.arrondi_entier_superieur(
                                pred_eqp["prediction"].iloc[i]
                            ),
                            "ic_bas": float(pred_heures["ic_bas"].iloc[i]),
                            "ic_haut": float(pred_heures["ic_haut"].iloc[i]),
                            "ic_bas_equipements": float(pred_eqp["ic_bas"].iloc[i]),
                            "ic_haut_equipements": float(pred_eqp["ic_haut"].iloc[i]),
                            "date_generation": horodatage,
                        }
                    )
        resume.nb_lignes = depot_previsions.inserer_plusieurs(lignes_a_inserer)
        signaler(progression, 1.0, "Génération terminée.")
    _log.info(
        "Prévisions de ressources générées par %s (site %s) : %d ligne(s), " "%d avertissement(s).",
        ctx.identifiant,
        site_id,
        resume.nb_lignes,
        len(resume.avertissements),
    )
    return resume


def lister_previsions_ressources(
    ctx: Contexte, site_id: int, zone_id: int | None = None, horizon_jours: int = 7
) -> list[dict]:
    """Prévisions RL et RN, une ligne par zone et par date (écran Prévisions)."""
    verifier_droit(ctx, "lecture_previsions")
    verifier_site(ctx, site_id)
    debut = date.today() + timedelta(days=1)
    fin = debut + timedelta(days=horizon_jours - 1)
    with transaction() as cur:
        lignes = DepotPrevisionsRessources(cur).dernieres(site_id, zone_id, debut, fin)
        depot_modeles = DepotModeles(cur)
        methodes_retenues: dict[int, str | None] = {}
        pivot: dict[tuple, dict] = {}
        for ligne in lignes:
            if ligne["zone_id"] not in methodes_retenues:
                retenue = depot_modeles.version_retenue_pour_plan(
                    site_id, ligne["zone_id"], "heures"
                )
                methodes_retenues[ligne["zone_id"]] = retenue["methode"] if retenue else None
            cle = (ligne["zone_id"], ligne["date_jour"])
            base = pivot.setdefault(
                cle,
                {
                    "zone_id": ligne["zone_id"],
                    "zone": ligne["zone"],
                    "date_jour": ligne["date_jour"],
                    "volume_prevu": ligne["volume_prevu"],
                    "modele_actif": None,
                },
            )
            suffixe = METHODES_COURTES[ligne["methode"]].lower()
            base[f"heures_{suffixe}"] = ligne["heures"]
            base[f"effectif_{suffixe}"] = ligne["effectif"]
            base[f"equipements_{suffixe}"] = ligne["equipements"]
            base[f"ic_bas_{suffixe}"] = ligne["ic_bas"]
            base[f"ic_haut_{suffixe}"] = ligne["ic_haut"]
            if methodes_retenues[ligne["zone_id"]] == ligne["methode"]:
                base["modele_actif"] = METHODES_COURTES[ligne["methode"]]
    return sorted(pivot.values(), key=lambda l: (l["date_jour"], l["zone"]))


# =====================================================================
# UC12 · Élaborer le plan de charge (inclut UC11)
# =====================================================================
def _plan_modifiable(plan: dict) -> None:
    if plan["statut"] not in STATUTS_MODIFIABLES:
        raise OperationImpossible(
            f"Le plan de la semaine du {formater_date(plan['semaine'])} est "
            f"{STATUTS_PLAN[plan['statut']].lower()} ; il ne peut plus être modifié."
        )


def proposer_plan_charge(ctx: Contexte, site_id: int, semaine: date) -> dict:
    """UC12 : propose, à partir des prévisions de la méthode retenue, l'effectif, l'intérim
    et les équipements de chaque zone et chaque jour de la semaine."""
    verifier_droit(ctx, "UC12")
    verifier_site(ctx, site_id)
    lundi = lundi_de(semaine)
    jours = jours_semaine(lundi)
    avertissements: list[str] = []

    with transaction() as cur:
        depot_plans = DepotPlansCharge(cur)
        plan_existant = depot_plans.plan_semaine(site_id, lundi)
        if plan_existant is not None:
            _plan_modifiable(plan_existant)

        ref = DepotReferentiels(cur)
        zones = ref.lister_zones(site_id)
        depot_modeles = DepotModeles(cur)
        depot_previsions = DepotPrevisionsRessources(cur)
        capacites = {
            (c["zone_id"], c["date_jour"]): c
            for c in ref.capacites(site_id, lundi, lundi + timedelta(days=6))
        }
        dispo_equipements: dict[tuple, dict[str, int]] = {}
        for d in ref.equipements_disponibles(site_id, lundi, lundi + timedelta(days=6)):
            if d["type"] is not None:
                dispo_equipements.setdefault((d["zone_id"], d["date_jour"]), {})[d["type"]] = d[
                    "disponibles"
                ]

        lignes: list[dict] = []
        methode_choisie: str | None = None
        for zone in zones:
            retenue = depot_modeles.version_retenue_pour_plan(site_id, zone["id"], "heures")
            methode_zone = retenue["methode"] if retenue else None
            if methode_zone is None:
                avertissements.append(
                    f"Zone « {zone['nom']} » : aucun modèle retenu pour le plan (écran Modèles)."
                )
            else:
                methode_choisie = methode_choisie or methode_zone
            for jour in jours:
                prevision = (
                    depot_previsions.derniere_ligne(site_id, zone["id"], jour, methode_zone)
                    if methode_zone
                    else None
                )
                if methode_zone and prevision is None:
                    avertissements.append(
                        f"Zone « {zone['nom']} », {formater_date(jour)} : aucune prévision "
                        "disponible (écran Prévisions)."
                    )
                besoin_heures = prevision["heures"] if prevision else 0.0
                besoin_effectif = prevision["effectif"] if prevision else 0
                besoin_equipements = prevision["equipements"] if prevision else 0
                capacite = capacites.get((zone["id"], jour))
                capacite_effectif = (
                    max(capacite["effectif_planifie"] - capacite["absences_prevues"], 0)
                    if capacite
                    else 0
                )
                capacite_equipements = dispo_equipements.get((zone["id"], jour), {}).get(
                    zone["type_equipement_principal"], 0
                )
                lignes.append(
                    {
                        "zone_id": zone["id"],
                        "date_jour": jour,
                        "besoin_heures": besoin_heures,
                        "besoin_effectif": besoin_effectif,
                        "besoin_equipements": besoin_equipements,
                        "effectif_planifie": min(besoin_effectif, capacite_effectif),
                        "interim_planifie": max(besoin_effectif - capacite_effectif, 0),
                        "equipements_planifies": min(besoin_equipements, capacite_equipements),
                        "capacite_effectif": capacite_effectif,
                        "capacite_equipements": capacite_equipements,
                        "commentaire": "",
                    }
                )

        if plan_existant is None:
            plan_id = depot_plans.creer_plan(site_id, lundi, methode_choisie, ctx.utilisateur_id)
        else:
            plan_id = plan_existant["id"]
            depot_plans.mettre_a_jour_plan(
                plan_id, statut="brouillon", methode=methode_choisie, commentaire=""
            )
        depot_plans.remplacer_lignes(plan_id, lignes)
    _log.info(
        "Plan de charge proposé par %s pour le site %s, semaine du %s.",
        ctx.identifiant,
        site_id,
        lundi,
    )
    return {"plan_id": plan_id, "avertissements": avertissements}


def lire_plan_charge(ctx: Contexte, site_id: int, semaine: date) -> dict | None:
    """Plan de charge d'une semaine (écran Plan de charge), ou ``None`` s'il n'existe pas
    encore (seul « Proposer le plan » est alors disponible)."""
    verifier_droit(ctx, "lecture_plan")
    verifier_site(ctx, site_id)
    lundi = lundi_de(semaine)
    with transaction() as cur:
        depot = DepotPlansCharge(cur)
        plan = depot.plan_semaine(site_id, lundi)
        if plan is None:
            return None
        lignes = depot.lignes(plan["id"])
    return {"plan": plan, "lignes": lignes}


def _en_depassement(ligne: dict) -> bool:
    """Une case où le besoin dépasse la capacité (colorée en rouge dans la grille)."""
    return (
        ligne["besoin_effectif"] > ligne["capacite_effectif"]
        or ligne["besoin_equipements"] > ligne["capacite_equipements"]
    )


def adequation_ligne(ligne: dict) -> float | None:
    """Adéquation planifié / nécessaire (%), pour la coloration orange (95–105 %).

    Sans aucun besoin, ``None`` (rien à comparer) si rien n'est planifié non plus, mais un
    sureffectif total (infini) si du personnel reste malgré tout planifié.
    """
    planifie = ligne["effectif_planifie"] + ligne["interim_planifie"]
    if ligne["besoin_effectif"] <= 0:
        return None if planifie <= 0 else float("inf")
    return planifie / ligne["besoin_effectif"] * 100


def statut_couleur_ligne(ligne: dict) -> str | None:
    """Statut visuel d'une case de la grille (écran Plan de charge) : ``"rouge"`` si le
    besoin dépasse la capacité, ``"orange"`` si l'adéquation est hors de 95–105 %, sinon
    ``None``."""
    if _en_depassement(ligne):
        return "rouge"
    adequation = adequation_ligne(ligne)
    if adequation is not None and not (95 <= adequation <= 105):
        return "orange"
    return None


def _valider_lignes_saisies(lignes: list[dict]) -> tuple[list[dict], dict[str, str]]:
    erreurs: dict[str, str] = {}
    propres = []
    for ligne in lignes:
        cle = f"{ligne['zone_id']}_{ligne['date_jour']}"
        try:
            propres.append(
                {
                    "zone_id": ligne["zone_id"],
                    "date_jour": ligne["date_jour"],
                    "effectif_planifie": int(
                        validation.nombre(
                            ligne["effectif_planifie"], "Effectif planifié", 0, 10_000, entier=True
                        )
                    ),
                    "interim_planifie": int(
                        validation.nombre(
                            ligne["interim_planifie"], "Intérim planifié", 0, 10_000, entier=True
                        )
                    ),
                    "equipements_planifies": int(
                        validation.nombre(
                            ligne["equipements_planifies"],
                            "Équipements planifiés",
                            0,
                            1_000,
                            entier=True,
                        )
                    ),
                    "commentaire": (ligne.get("commentaire") or "").strip(),
                }
            )
        except ValueError as exc:
            erreurs[cle] = str(exc)
    return propres, erreurs


def enregistrer_brouillon_plan(
    ctx: Contexte,
    plan_id: int,
    lignes: list[dict],
    date_maj_attendue: datetime | None = None,
) -> None:
    """UC12 : enregistre les ajustements du planificateur (le plan reste en brouillon).

    ``date_maj_attendue`` porte le verrouillage optimiste : si elle est fournie et ne
    correspond plus à la date de dernière modification en base, quelqu'un d'autre a modifié
    le plan entre-temps et l'enregistrement est refusé plutôt que d'écraser silencieusement
    son travail (``ConflitMiseAJour``).
    """
    verifier_droit(ctx, "UC12")
    with transaction() as cur:
        depot = DepotPlansCharge(cur)
        plan = depot.plan(plan_id)
        if plan is None:
            raise OperationImpossible("Plan de charge introuvable.")
        verifier_site(ctx, plan["site_id"])
        _plan_modifiable(plan)
        if date_maj_attendue is not None and plan["date_maj"] != date_maj_attendue:
            raise ConflitMiseAJour()
        propres, erreurs = _valider_lignes_saisies(lignes)
        if erreurs:
            raise DonneesInvalides("Certaines cellules du plan sont invalides.", erreurs)
        depot.mettre_a_jour_plan(
            plan_id, statut="brouillon" if plan["statut"] == "rejete" else plan["statut"]
        )
        depot.mettre_a_jour_lignes(plan_id, propres)
    _log.info("Brouillon du plan n° %s enregistré par %s.", plan_id, ctx.identifiant)


def soumettre_plan(ctx: Contexte, plan_id: int) -> None:
    """UC12 : soumet le plan pour validation ; chaque case en dépassement doit être commentée."""
    verifier_droit(ctx, "UC12")
    with transaction() as cur:
        depot = DepotPlansCharge(cur)
        plan = depot.plan(plan_id)
        if plan is None:
            raise OperationImpossible("Plan de charge introuvable.")
        verifier_site(ctx, plan["site_id"])
        if plan["statut"] != "brouillon":
            raise OperationImpossible("Seul un plan en brouillon peut être soumis.")
        lignes = depot.lignes(plan_id)
        manquants = [l for l in lignes if _en_depassement(l) and not l["commentaire"].strip()]
        if manquants:
            raise DonneesInvalides(
                "Une case où le besoin dépasse la capacité doit être commentée avant de "
                "soumettre le plan.",
                {
                    f"{l['zone_id']}_{l['date_jour']}": "Un commentaire est obligatoire (le besoin dépasse la capacité)."
                    for l in manquants
                },
            )
        depot.mettre_a_jour_plan(
            plan_id, statut="soumis", soumis_par=ctx.utilisateur_id, date_soumission=datetime.now()
        )
    _log.info("Plan de charge n° %s soumis par %s.", plan_id, ctx.identifiant)


# =====================================================================
# UC13 · Simuler un scénario (étend UC12)
# =====================================================================
def _valider_hypotheses(hypotheses: dict) -> dict:
    erreurs: dict[str, str] = {}
    resultat: dict = {}
    try:
        resultat["variation_volume_pct"] = validation.nombre(
            hypotheses.get("variation_volume_pct", 0), "Variation du volume (%)", -100, 500
        )
    except ValueError as exc:
        erreurs["variation_volume_pct"] = str(exc)
    try:
        resultat["taux_absence_pct"] = validation.nombre(
            hypotheses.get("taux_absence_pct", 0), "Taux d'absence (%)", 0, 100
        )
    except ValueError as exc:
        erreurs["taux_absence_pct"] = str(exc)
    resultat["equipements_indisponibles"] = {}
    for type_eqp, valeur in (hypotheses.get("equipements_indisponibles") or {}).items():
        try:
            resultat["equipements_indisponibles"][type_eqp] = int(
                validation.nombre(valeur, "Équipements indisponibles", 0, 1_000, entier=True)
            )
        except ValueError as exc:
            erreurs[f"equipements_{type_eqp}"] = str(exc)
    if erreurs:
        raise DonneesInvalides("Certaines hypothèses sont invalides.", erreurs)
    return resultat


def _pour_json(ligne: dict) -> dict:
    return {**ligne, "date_jour": ligne["date_jour"].isoformat()}


def simuler_scenario(ctx: Contexte, plan_id: int, hypotheses: dict) -> dict:
    """UC13 : recalcule le plan sous des hypothèses, sans le modifier. Le scénario est
    toujours enregistré."""
    verifier_droit(ctx, "UC13")
    hyp = _valider_hypotheses(hypotheses)
    with transaction() as cur:
        depot_plans = DepotPlansCharge(cur)
        plan = depot_plans.plan(plan_id)
        if plan is None:
            raise OperationImpossible("Plan de charge introuvable.")
        verifier_site(ctx, plan["site_id"])
        lignes = depot_plans.lignes(plan_id)
        ref = DepotReferentiels(cur)
        zones = {z["id"]: z for z in ref.lister_zones(plan["site_id"], inclure_inactives=True)}

        facteur_volume = 1 + hyp["variation_volume_pct"] / 100
        apres = []
        for ligne in lignes:
            zone = zones.get(ligne["zone_id"], {})
            duree_poste = zone.get("duree_poste_heures", 7.5)
            besoin_heures = ligne["besoin_heures"] * facteur_volume
            besoin_effectif = math.ceil(besoin_heures / duree_poste - 1e-9) if duree_poste else 0
            besoin_equipements = math.ceil(ligne["besoin_equipements"] * facteur_volume - 1e-9)
            capacite_effectif = max(
                round(ligne["capacite_effectif"] * (1 - hyp["taux_absence_pct"] / 100)), 0
            )
            indispo = hyp["equipements_indisponibles"].get(
                zone.get("type_equipement_principal", ""), 0
            )
            capacite_equipements = max(ligne["capacite_equipements"] - indispo, 0)
            apres.append(
                {
                    "zone_id": ligne["zone_id"],
                    "date_jour": ligne["date_jour"],
                    "besoin_heures": besoin_heures,
                    "besoin_effectif": besoin_effectif,
                    "besoin_equipements": besoin_equipements,
                    "effectif_planifie": min(besoin_effectif, capacite_effectif),
                    "interim_planifie": max(besoin_effectif - capacite_effectif, 0),
                    "equipements_planifies": min(besoin_equipements, capacite_equipements),
                    "capacite_effectif": capacite_effectif,
                    "capacite_equipements": capacite_equipements,
                    "commentaire": ligne["commentaire"],
                }
            )
        resultats = {
            "avant": [_pour_json(l) for l in lignes],
            "apres": [_pour_json(l) for l in apres],
        }
        scenario_id = DepotScenarios(cur).creer(plan_id, hyp, resultats, ctx.utilisateur_id)
    _log.info(
        "Scénario n° %s simulé par %s pour le plan n° %s.", scenario_id, ctx.identifiant, plan_id
    )
    return {"scenario_id": scenario_id, "avant": lignes, "apres": apres}


def appliquer_scenario(ctx: Contexte, scenario_id: int) -> None:
    """UC13 : applique les valeurs simulées au plan de charge."""
    verifier_droit(ctx, "UC13")
    with transaction() as cur:
        depot_scenarios = DepotScenarios(cur)
        scenario = depot_scenarios.scenario(scenario_id)
        if scenario is None:
            raise OperationImpossible("Scénario introuvable.")
        depot_plans = DepotPlansCharge(cur)
        plan = depot_plans.plan(scenario["plan_id"])
        if plan is None:
            raise OperationImpossible("Plan de charge introuvable.")
        verifier_site(ctx, plan["site_id"])
        _plan_modifiable(plan)
        lignes = [
            {**ligne, "date_jour": date.fromisoformat(ligne["date_jour"])}
            for ligne in scenario["resultats"]["apres"]
        ]
        depot_plans.remplacer_lignes(plan["id"], lignes)
        if plan["statut"] == "rejete":
            depot_plans.mettre_a_jour_plan(plan["id"], statut="brouillon")
        depot_scenarios.marquer_applique(scenario_id)
    _log.info(
        "Scénario n° %s appliqué au plan n° %s par %s.",
        scenario_id,
        scenario["plan_id"],
        ctx.identifiant,
    )


def lister_scenarios(ctx: Contexte, plan_id: int) -> list[dict]:
    verifier_droit(ctx, "lecture_plan")
    with transaction() as cur:
        return DepotScenarios(cur).lister(plan_id)


# =====================================================================
# UC14 · Valider le plan de charge
# =====================================================================
def valider_plan(ctx: Contexte, plan_id: int) -> None:
    """UC14 : valide un plan soumis ; il devient la référence du KPI d'adéquation."""
    verifier_droit(ctx, "UC14")
    with transaction() as cur:
        depot = DepotPlansCharge(cur)
        plan = depot.plan(plan_id)
        if plan is None:
            raise OperationImpossible("Plan de charge introuvable.")
        verifier_site(ctx, plan["site_id"])
        if plan["statut"] != "soumis":
            raise OperationImpossible("Seul un plan soumis peut être validé.")
        depot.mettre_a_jour_plan(
            plan_id, statut="valide", valide_par=ctx.utilisateur_id, date_validation=datetime.now()
        )
    _log.info("Plan de charge n° %s validé par %s.", plan_id, ctx.identifiant)


def rejeter_plan(ctx: Contexte, plan_id: int, commentaire: str) -> None:
    """UC14 : rejette un plan soumis ; le commentaire est obligatoire."""
    verifier_droit(ctx, "UC14")
    try:
        commentaire = validation.obligatoire(commentaire, "Commentaire du rejet")
    except ValueError as exc:
        raise DonneesInvalides(str(exc), {"commentaire": str(exc)}) from None
    with transaction() as cur:
        depot = DepotPlansCharge(cur)
        plan = depot.plan(plan_id)
        if plan is None:
            raise OperationImpossible("Plan de charge introuvable.")
        verifier_site(ctx, plan["site_id"])
        if plan["statut"] != "soumis":
            raise OperationImpossible("Seul un plan soumis peut être rejeté.")
        depot.mettre_a_jour_plan(plan_id, statut="rejete", commentaire=commentaire)
    _log.info("Plan de charge n° %s rejeté par %s.", plan_id, ctx.identifiant)
