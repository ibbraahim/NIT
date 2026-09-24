"""Formatage français : dates, nombres, pourcentages, montants, périodes."""

from datetime import date, datetime

import pytest

from app.utils import dates
from app.utils.format_fr import (
    formater_date,
    formater_date_heure,
    formater_date_longue,
    formater_entier,
    formater_jour_court,
    formater_montant,
    formater_nombre,
    formater_pourcentage,
    lire_date,
    lire_nombre,
)


def test_date_courte():
    assert formater_date(date(2026, 3, 12)) == "12/03/2026"
    assert formater_date(None) == "—"


def test_date_heure():
    assert formater_date_heure(datetime(2026, 3, 12, 8, 5)) == "12/03/2026 08:05"


def test_date_longue():
    assert formater_date_longue(date(2026, 3, 12)) == "jeudi 12 mars 2026"
    assert formater_date_longue(date(2026, 2, 1)) == "dimanche 1er février 2026"
    assert formater_date_longue(date(2026, 8, 15), avec_jour=False) == "15 août 2026"


def test_jour_court():
    assert formater_jour_court(date(2026, 9, 28)) == "lun. 28/09"


@pytest.mark.parametrize(
    ("valeur", "decimales", "attendu"),
    [
        (1250.5, 1, "1 250,5"),
        (1234567.891, 2, "1 234 567,89"),
        (0, 1, "0,0"),
        (-1250.5, 1, "-1 250,5"),
        (999, 0, "999"),
        (1000, 0, "1 000"),
        (-0.04, 1, "0,0"),
        (float("nan"), 1, "—"),
        (None, 1, "—"),
    ],
)
def test_nombres(valeur, decimales, attendu):
    assert formater_nombre(valeur, decimales) == attendu


def test_nombre_sans_zeros():
    assert formater_nombre(1250.0, 2, supprimer_zeros=True) == "1 250"
    assert formater_nombre(7.5, 2, supprimer_zeros=True) == "7,5"
    assert formater_entier(12500) == "12 500"


def test_pourcentages():
    assert formater_pourcentage(12.345) == "12,3 %"
    assert formater_pourcentage(100) == "100,0 %"
    assert formater_pourcentage(2.5, signe=True) == "+2,5 %"
    assert formater_pourcentage(-2.5, signe=True) == "-2,5 %"
    assert formater_pourcentage(None) == "—"


def test_montants():
    assert formater_montant(1250.5) == "1 250,50 MAD"
    assert formater_montant(10, "EUR", 0) == "10 EUR"


def test_lecture_nombres():
    assert lire_nombre("1 250,5") == 1250.5
    assert lire_nombre("1250.5") == 1250.5
    assert lire_nombre("1 250,5") == 1250.5
    with pytest.raises(ValueError, match="n'est pas un nombre valide"):
        lire_nombre("abc")


def test_lecture_dates():
    assert lire_date("12/03/2026") == date(2026, 3, 12)
    assert lire_date("2026-03-12") == date(2026, 3, 12)
    with pytest.raises(ValueError, match="JJ/MM/AAAA"):
        lire_date("31/02/2026")


def test_semaine_commence_le_lundi():
    jeudi = date(2026, 3, 12)
    assert dates.lundi_de(jeudi) == date(2026, 3, 9)
    assert dates.lundi_de(date(2026, 3, 15)) == date(2026, 3, 9)  # dimanche
    assert dates.jours_semaine(date(2026, 3, 9))[-1] == date(2026, 3, 15)


@pytest.mark.parametrize(
    ("periodicite", "debut", "fin"),
    [
        ("jour", date(2026, 3, 12), date(2026, 3, 12)),
        ("semaine", date(2026, 3, 9), date(2026, 3, 15)),
        ("mois", date(2026, 3, 1), date(2026, 3, 31)),
        ("annee", date(2026, 1, 1), date(2026, 12, 31)),
    ],
)
def test_bornes_periodes(periodicite, debut, fin):
    assert dates.bornes_periode(date(2026, 3, 12), periodicite) == (debut, fin)


def test_decalage_periodes():
    assert dates.decaler_periode(date(2026, 1, 15), "mois", -1) == date(2025, 12, 1)
    assert dates.decaler_periode(date(2026, 12, 15), "mois", 1) == date(2027, 1, 1)
    assert dates.decaler_periode(date(2026, 3, 12), "semaine", 1) == date(2026, 3, 16)
    assert dates.fin_periode(date(2028, 2, 10), "mois") == date(2028, 2, 29)


def test_libelles_periodes():
    assert dates.libelle_periode(date(2026, 3, 12), "mois") == "mars 2026"
    assert dates.libelle_periode(date(2026, 3, 12), "annee") == "année 2026"
    assert dates.libelle_periode(date(2026, 3, 12), "semaine").startswith("semaine du 09/03/2026")
