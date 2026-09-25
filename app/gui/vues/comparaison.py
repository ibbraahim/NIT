"""Écran 6 — Comparaison réel / prévu (UC20) : responsable."""

from __future__ import annotations

from datetime import date, timedelta
from tkinter import ttk

from app.gui.vues.base import Vue
from app.gui.widgets.bouton import Bouton
from app.gui.widgets.champs import ChampDate, ChampListe
from app.gui.widgets.dialogues import informer
from app.gui.widgets.tableau_triable import Colonne, TableauTriable
from app.gui.widgets.taches_fond import executer_en_fond
from app.libelles import METHODES, METHODES_COURTES
from app.services import admin, comparaison
from app.services.droits import a_le_droit
from app.utils.format_fr import formater_booleen, formater_nombre, formater_pourcentage

OPTION_TOUTES_METHODES = (None, "Toutes les méthodes")
OPTIONS_METHODE = [OPTION_TOUTES_METHODES] + list(METHODES.items())

COLONNES_TABLEAU = [
    Colonne("date_jour", "Date", 100, "center"),
    Colonne("zone", "Zone", 120),
    Colonne("methode_libelle", "Méthode", 80, "center"),
    Colonne(
        "heures_prevues", "Heures prévues", 110, "e", formateur=lambda v: formater_nombre(v, 1)
    ),
    Colonne(
        "heures_reelles", "Heures réelles", 110, "e", formateur=lambda v: formater_nombre(v, 1)
    ),
    Colonne("ecart_absolu", "Écart (h)", 90, "e", formateur=lambda v: formater_nombre(v, 1)),
    Colonne(
        "ecart_relatif",
        "Écart (%)",
        90,
        "e",
        formateur=lambda v: formater_pourcentage(v, 1, signe=True),
    ),
    Colonne("dans_ic", "Dans l'IC", 90, "center", formateur=formater_booleen),
    Colonne("equipements_prevus", "Équip. prévus", 100, "e"),
    Colonne("equipements_reels", "Équip. réels", 100, "e"),
    Colonne(
        "ecart_equipements", "Écart équip.", 100, "e", formateur=lambda v: formater_nombre(v, 1)
    ),
]


def _etiquette(ligne: dict) -> str | None:
    if not ligne["comparable"]:
        return "gris"
    return "vert" if ligne["dans_ic"] else "rouge"


class VueComparaison(Vue):
    """Filtres Site/Zone/Méthode/Période, rapprochement (UC20) et tableau des écarts."""

    titre = "Comparaison réel / prévu"
    sous_titre = "Rapprochement des prévisions RL et RN au réalisé"

    def construire(self) -> None:
        self.peut_comparer = a_le_droit(self.ctx, "UC20")
        barre = ttk.Frame(self.contenu)
        barre.pack(fill="x", pady=(0, 10))
        self.site = ChampListe(barre, "Site", largeur=24)
        self.site.pack(side="left")
        self.site.sur_changement(self._sur_changement_site)
        self.zone = ChampListe(barre, "Zone", largeur=20)
        self.zone.pack(side="left", padx=(16, 0))
        self.zone.sur_changement(self.actualiser_donnees)
        self.methode = ChampListe(barre, "Méthode", options=OPTIONS_METHODE, largeur=20)
        self.methode.pack(side="left", padx=(16, 0))
        self.methode.sur_changement(self.actualiser_donnees)

        barre2 = ttk.Frame(self.contenu)
        barre2.pack(fill="x", pady=(0, 10))
        aujourdhui = date.today()
        self.date_debut = ChampDate(barre2, "Du")
        self.date_debut.definir(aujourdhui - timedelta(days=27))
        self.date_debut.pack(side="left")
        self.date_debut.sur_changement(self.actualiser_donnees)
        self.date_fin = ChampDate(barre2, "Au")
        self.date_fin.definir(aujourdhui - timedelta(days=1))
        self.date_fin.pack(side="left", padx=(16, 0))
        self.date_fin.sur_changement(self.actualiser_donnees)

        boutons = ttk.Frame(barre2)
        boutons.pack(side="left", padx=(24, 0), pady=(14, 0))
        self.b_comparer = Bouton(boutons, "Comparer le réalisé", self.comparer, primaire=True)
        self.b_comparer.pack(side="left")
        if not self.peut_comparer:
            self.b_comparer.pack_forget()

        corps = ttk.Frame(self.contenu)
        corps.pack(fill="both", expand=True)
        self.tableau = TableauTriable(corps, COLONNES_TABLEAU, hauteur=16)
        self.tableau.pack(fill="both", expand=True)

    def actualiser(self) -> None:
        sites = self.executer(lambda: admin.lister_sites(self.ctx)) or []
        self.site.definir_options([(s["id"], s["nom"]) for s in sites])
        self._sur_changement_site()

    def _sur_changement_site(self) -> None:
        site_id = self.site.valeur()
        zones = (
            self.executer(lambda: admin.lister_zones(self.ctx, site_id)) or []
            if site_id is not None
            else []
        )
        self.zone.definir_options(
            [(None, "Toutes les zones")] + [(z["id"], z["nom"]) for z in zones], conserver=False
        )
        self.actualiser_donnees()

    def _periode(self) -> tuple[date, date] | None:
        try:
            return self.date_debut.valeur(), self.date_fin.valeur()
        except ValueError:
            return None

    def actualiser_donnees(self) -> None:
        site_id, zone_id, methode = self.site.valeur(), self.zone.valeur(), self.methode.valeur()
        periode = self._periode()
        self.b_comparer.activer(
            self.peut_comparer and site_id is not None, "Choisissez d'abord un site."
        )
        if site_id is None or periode is None:
            self.tableau.charger([], message_vide="Choisissez un site.")
            return
        debut, fin = periode
        lignes = (
            self.executer(
                lambda: comparaison.lister_comparaisons(
                    self.ctx, site_id, zone_id, debut, fin, methode
                )
            )
            or []
        )
        for ligne in lignes:
            ligne["methode_libelle"] = METHODES_COURTES.get(ligne["methode"], ligne["methode"])
        self.tableau.charger(
            lignes,
            cle_id="prevision_id",
            etiquettes=_etiquette,
            message_vide="Aucun rapprochement pour cette période. Utilisez « Comparer le "
            "réalisé » une fois l'historique de la période connu.",
        )

    def comparer(self) -> None:
        site_id, zone_id = self.site.valeur(), self.zone.valeur()
        periode = self._periode()
        if site_id is None or periode is None:
            return
        debut, fin = periode

        def traiter(_progression):
            return comparaison.comparer_realise(self.ctx, site_id, zone_id, debut, fin)

        def succes(resultat):
            self.actualiser_donnees()
            informer(
                self,
                f"{resultat['nb_traites']} prévision(s) rapprochée(s), dont "
                f"{resultat['nb_comparables']} avec un réel connu.",
                "Comparaison terminée",
            )

        executer_en_fond(
            self,
            traiter,
            succes,
            titre="Comparaison réel / prévu",
            message="Rapprochement des prévisions au réalisé…",
        )
