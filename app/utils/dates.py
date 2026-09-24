"""Calculs de dates : semaines commençant le lundi, bornes de périodes, horizons."""

from __future__ import annotations

from datetime import date, timedelta

from app.utils.format_fr import formater_date, formater_mois

PERIODICITES = ("jour", "semaine", "mois", "annee")
LIBELLES_PERIODICITES = {"jour": "Jour", "semaine": "Semaine", "mois": "Mois", "annee": "Année"}


def lundi_de(jour: date) -> date:
    """Lundi de la semaine contenant ``jour``."""
    return jour - timedelta(days=jour.weekday())


def jours_semaine(lundi: date) -> list[date]:
    """Les 7 dates de la semaine commençant au lundi donné."""
    return [lundi + timedelta(days=i) for i in range(7)]


def debut_periode(jour: date, periodicite: str) -> date:
    """Premier jour de la période (jour, semaine, mois ou année) contenant ``jour``."""
    if periodicite == "jour":
        return jour
    if periodicite == "semaine":
        return lundi_de(jour)
    if periodicite == "mois":
        return jour.replace(day=1)
    if periodicite == "annee":
        return jour.replace(month=1, day=1)
    raise ValueError(f"Périodicité inconnue : « {periodicite} ».")


def fin_periode(jour: date, periodicite: str) -> date:
    """Dernier jour (inclus) de la période contenant ``jour``."""
    debut = debut_periode(jour, periodicite)
    if periodicite == "jour":
        return debut
    if periodicite == "semaine":
        return debut + timedelta(days=6)
    if periodicite == "mois":
        suivant = date(debut.year + (debut.month == 12), debut.month % 12 + 1, 1)
        return suivant - timedelta(days=1)
    return date(debut.year, 12, 31)


def bornes_periode(jour: date, periodicite: str) -> tuple[date, date]:
    """(début, fin) inclusifs de la période contenant ``jour``."""
    return debut_periode(jour, periodicite), fin_periode(jour, periodicite)


def decaler_periode(jour: date, periodicite: str, pas: int) -> date:
    """Début de la période située ``pas`` périodes avant (négatif) ou après (positif)."""
    debut = debut_periode(jour, periodicite)
    if periodicite == "jour":
        return debut + timedelta(days=pas)
    if periodicite == "semaine":
        return debut + timedelta(weeks=pas)
    if periodicite == "mois":
        index = debut.year * 12 + debut.month - 1 + pas
        return date(index // 12, index % 12 + 1, 1)
    return date(debut.year + pas, 1, 1)


def libelle_periode(jour: date, periodicite: str) -> str:
    """Libellé lisible : « 12/03/2026 », « semaine du 09/03/2026 », « mars 2026 », « année 2026 »."""
    debut = debut_periode(jour, periodicite)
    if periodicite == "jour":
        return formater_date(debut)
    if periodicite == "semaine":
        return (
            f"semaine du {formater_date(debut)} au {formater_date(fin_periode(debut, 'semaine'))}"
        )
    if periodicite == "mois":
        return formater_mois(debut)
    return f"année {debut.year}"


def plage_dates(debut: date, fin: date) -> list[date]:
    """Toutes les dates de ``debut`` à ``fin`` inclus."""
    return [debut + timedelta(days=i) for i in range((fin - debut).days + 1)]


def horizon(depart: date, nb_jours: int) -> list[date]:
    """Dates J+1 à J+nb_jours à partir de ``depart``."""
    return [depart + timedelta(days=i) for i in range(1, nb_jours + 1)]
