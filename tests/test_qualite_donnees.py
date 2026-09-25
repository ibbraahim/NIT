"""UC06 · Contrôler la qualité des données — chaque règle de rejet et d'avertissement.

Données construites à la main (pas de base de données) : un site « Site test » avec une
zone « Réception » (durée de poste 7,5 h).
"""

from datetime import date, timedelta

import pytest

from app.services.qualite import ContexteValidation, controler_qualite

AUJOURD_HUI = date(2026, 3, 12)  # jeudi


def contexte(reference: list[float] | None = None, aujourd_hui: date = AUJOURD_HUI):
    return ContexteValidation(
        sites={"site test": {"id": 1, "actif": True}},
        zones={(1, "réception"): {"id": 10, "actif": True, "duree_poste_heures": 7.5}},
        valeurs_reference=lambda *_: reference or [],
        aujourd_hui=aujourd_hui,
    )


def ligne_historique(**remplacements) -> dict:
    base = {
        "site": "Site test",
        "zone": "Réception",
        "date": "09/03/2026",
        "volume_traite": "1250,5",
        "effectif_present": "10",
        "heures_travaillees": "75",
        "heures_sup": "5",
        "heures_interim": "0",
        "heures_absence": "0",
        "heures_inactives": "3",
        "equipements_mobilises": "4",
        "heures_usage_equipement": "28",
        "heures_disponibles_equipement": "30",
        "heures_panne_equipement": "0",
        "cout_rh": "3487,50",
        "commandes_a_temps": "118",
        "commandes_totales": "120",
        "indicateur_pic": "Non",
    }
    base.update(remplacements)
    return base


def ligne_prevision(**remplacements) -> dict:
    base = {
        "site": "Site test",
        "zone": "Réception",
        "date": "20/03/2026",
        "volume_prevu": "1750",
        "indicateur_pic": "Oui",
    }
    base.update(remplacements)
    return base


def rejet_colonnes(resultat) -> set[str]:
    return {r.colonne for r in resultat.rejets}


# ---------------------------------------------------------------------
# Ligne valide de référence
# ---------------------------------------------------------------------
def test_ligne_historique_valide():
    resultat = controler_qualite("historique", [ligne_historique()], contexte())
    assert not resultat.rejets and not resultat.avertissements
    (valeurs,) = resultat.valides
    assert valeurs["site_id"] == 1 and valeurs["zone_id"] == 10
    assert valeurs["date"] == date(2026, 3, 9)
    assert valeurs["volume_traite"] == 1250.5
    assert valeurs["effectif_present"] == 10 and isinstance(valeurs["effectif_present"], int)


def test_champs_optionnels_par_defaut():
    minimale = {
        "site": "Site test",
        "zone": "Réception",
        "date": "09/03/2026",
        "volume_traite": "1000",
        "effectif_present": "8",
        "heures_travaillees": "60",
    }
    resultat = controler_qualite("historique", [minimale], contexte())
    assert not resultat.rejets
    (valeurs,) = resultat.valides
    assert valeurs["heures_sup"] == 0.0
    assert valeurs["equipements_mobilises"] == 0
    assert valeurs["indicateur_pic"] is False


def test_ligne_prevision_valide():
    resultat = controler_qualite("prevision", [ligne_prevision()], contexte())
    assert not resultat.rejets
    (valeurs,) = resultat.valides
    assert valeurs["volume_prevu"] == 1750.0 and valeurs["indicateur_pic"] is True


# ---------------------------------------------------------------------
# Rejets
# ---------------------------------------------------------------------
def test_champ_obligatoire_manquant():
    resultat = controler_qualite("historique", [ligne_historique(volume_traite=None)], contexte())
    assert rejet_colonnes(resultat) == {"volume_traite"}
    assert "obligatoire" in resultat.rejets[0].raison


def test_valeur_negative_rejetee():
    resultat = controler_qualite("historique", [ligne_historique(heures_sup="-5")], contexte())
    assert rejet_colonnes(resultat) == {"heures_sup"}
    assert "négatif" in resultat.rejets[0].raison


def test_site_inconnu():
    resultat = controler_qualite("historique", [ligne_historique(site="Site fantôme")], contexte())
    assert rejet_colonnes(resultat) == {"site"}


def test_zone_inconnue():
    resultat = controler_qualite("historique", [ligne_historique(zone="Expédition")], contexte())
    assert rejet_colonnes(resultat) == {"zone"}


def test_zone_inactive_traitee_comme_inconnue():
    ctx = ContexteValidation(
        sites={"site test": {"id": 1, "actif": True}},
        zones={(1, "réception"): {"id": 10, "actif": False, "duree_poste_heures": 7.5}},
    )
    resultat = controler_qualite("historique", [ligne_historique()], ctx)
    assert rejet_colonnes(resultat) == {"zone"}


def test_doublon_dans_le_fichier():
    lignes = [ligne_historique(), ligne_historique(volume_traite="2000")]
    resultat = controler_qualite("historique", lignes, contexte())
    assert len(resultat.valides) == 1
    assert resultat.rejets == [
        type(resultat.rejets[0])(
            2, "date", "Doublon : site, zone et date déjà présents dans ce fichier."
        )
    ]


def test_heures_travaillees_excessives():
    # effectif 10 x durée de poste 7,5 x 1,5 = 112,5 : 120 dépasse la limite.
    resultat = controler_qualite(
        "historique", [ligne_historique(heures_travaillees="120")], contexte()
    )
    assert rejet_colonnes(resultat) == {"heures_travaillees"}


def test_heures_travaillees_a_la_limite_acceptees():
    resultat = controler_qualite(
        "historique", [ligne_historique(heures_travaillees="112,5")], contexte()
    )
    assert not resultat.rejets


def test_heures_usage_superieures_aux_disponibles():
    resultat = controler_qualite(
        "historique",
        [ligne_historique(heures_usage_equipement="35", heures_disponibles_equipement="30")],
        contexte(),
    )
    assert rejet_colonnes(resultat) == {"heures_usage_equipement"}


def test_heures_inactives_superieures_aux_travaillees():
    resultat = controler_qualite(
        "historique",
        [ligne_historique(heures_inactives="80", heures_travaillees="75")],
        contexte(),
    )
    assert rejet_colonnes(resultat) == {"heures_inactives"}


def test_commandes_a_temps_superieures_au_total():
    resultat = controler_qualite(
        "historique",
        [ligne_historique(commandes_a_temps="130", commandes_totales="120")],
        contexte(),
    )
    assert rejet_colonnes(resultat) == {"commandes_a_temps"}


def test_plusieurs_erreurs_sur_une_ligne():
    resultat = controler_qualite(
        "historique",
        [ligne_historique(volume_traite=None, heures_sup="-1")],
        contexte(),
    )
    assert rejet_colonnes(resultat) == {"volume_traite", "heures_sup"}
    assert len(resultat.valides) == 0


@pytest.mark.parametrize("brut", ["abc", "12,5,3"])
def test_nombre_invalide(brut):
    resultat = controler_qualite("historique", [ligne_historique(volume_traite=brut)], contexte())
    assert rejet_colonnes(resultat) == {"volume_traite"}
    assert "nombre" in resultat.rejets[0].raison


def test_entier_non_entier_rejete():
    resultat = controler_qualite(
        "historique", [ligne_historique(effectif_present="10,5")], contexte()
    )
    assert rejet_colonnes(resultat) == {"effectif_present"}
    assert "entier" in resultat.rejets[0].raison


@pytest.mark.parametrize(
    "valeur,attendu",
    [("Oui", True), ("vrai", True), ("1", True), ("Non", False), ("faux", False), ("0", False)],
)
def test_conversion_booleenne(valeur, attendu):
    resultat = controler_qualite(
        "historique", [ligne_historique(indicateur_pic=valeur)], contexte()
    )
    assert resultat.valides[0]["indicateur_pic"] is attendu


def test_booleen_invalide_rejete():
    resultat = controler_qualite(
        "historique", [ligne_historique(indicateur_pic="peut-être")], contexte()
    )
    assert rejet_colonnes(resultat) == {"indicateur_pic"}


def test_date_invalide_rejetee():
    resultat = controler_qualite("historique", [ligne_historique(date="31/02/2026")], contexte())
    assert rejet_colonnes(resultat) == {"date"}


# ---------------------------------------------------------------------
# UC05 : refus des dates passées
# ---------------------------------------------------------------------
def test_prevision_date_passee_rejetee():
    hier = (AUJOURD_HUI - timedelta(days=1)).strftime("%d/%m/%Y")
    resultat = controler_qualite(
        "prevision", [ligne_prevision(date=hier)], contexte(aujourd_hui=AUJOURD_HUI)
    )
    assert rejet_colonnes(resultat) == {"date"}
    assert "passée" in resultat.rejets[0].raison


def test_prevision_aujourdhui_accepte():
    aujourdhui = AUJOURD_HUI.strftime("%d/%m/%Y")
    resultat = controler_qualite(
        "prevision", [ligne_prevision(date=aujourdhui)], contexte(aujourd_hui=AUJOURD_HUI)
    )
    assert not resultat.rejets


def test_historique_date_passee_acceptee():
    # UC04 enregistre du réalisé : les dates passées sont normales, pas rejetées.
    resultat = controler_qualite(
        "historique", [ligne_historique(date="01/01/2020")], contexte(aujourd_hui=AUJOURD_HUI)
    )
    assert not resultat.rejets


# ---------------------------------------------------------------------
# Avertissement : écart de plus de 3 écarts-types
# ---------------------------------------------------------------------
def test_avertissement_valeur_inhabituelle():
    reference = [1000.0, 1010.0, 990.0, 1005.0, 995.0, 1000.0, 1002.0, 998.0]
    resultat = controler_qualite(
        "historique", [ligne_historique(volume_traite="5000")], contexte(reference=reference)
    )
    assert not resultat.rejets  # accepté quand même
    assert len(resultat.valides) == 1
    assert len(resultat.avertissements) == 1
    assert resultat.avertissements[0].colonne == "volume_traite"


def test_pas_avertissement_valeur_normale():
    reference = [1000.0, 1010.0, 990.0, 1005.0, 995.0, 1000.0, 1002.0, 998.0]
    resultat = controler_qualite(
        "historique", [ligne_historique(volume_traite="1003")], contexte(reference=reference)
    )
    assert not resultat.avertissements


def test_pas_assez_d_historique_pas_d_avertissement():
    # Moins de 8 valeurs de référence : le contrôle est ignoré (pas assez d'historique).
    resultat = controler_qualite(
        "historique",
        [ligne_historique(volume_traite="99999")],
        contexte(reference=[1000.0, 1010.0, 990.0]),
    )
    assert not resultat.avertissements


def test_avertissement_sur_prevision_pic_annonce():
    # Rejoue la situation du lundi : un pic de +40 % prévu est signalé, pas rejeté.
    reference = [1000.0] * 8
    resultat = controler_qualite(
        "prevision", [ligne_prevision(volume_prevu="1400")], contexte(reference=reference)
    )
    assert not resultat.rejets
    assert len(resultat.avertissements) == 1
