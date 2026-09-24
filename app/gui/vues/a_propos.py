"""Écran 12 — À propos (menu « Aide », tous les rôles)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app import NOM_APPLICATION, VERSION
from app.gui.style import COULEURS
from app.gui.widgets.dialogues import DialogueBase

SITUATION = (
    "Un lundi matin, sur une plateforme logistique. La prévision de la demande (2.1.1) annonce "
    "un pic de 40 % pour jeudi, porté par une campagne promotionnelle. Pourtant, le planning des "
    "équipes est le même que la semaine précédente, et deux chariots élévateurs sont en "
    "maintenance.\n"
    "Jeudi arrive. Les camions attendent à quai parce que la réception (4.2) manque de caristes. "
    "Les commandes s'accumulent en préparation (4.4.1 Prélèvement, 4.4.3 Mise à quai et "
    "chargement). Les heures supplémentaires explosent et des intérimaires sont appelés en "
    "urgence, sans formation. À la fin, les engagements de service (6.3.1) ne sont pas tenus.\n"
    "Mardi suivant, c'est l'inverse : le volume est faible, mais toute l'équipe est présente. "
    "Les coûts tournent à vide."
)

PROBLEME = (
    "Ce n'est pas un problème de prévision de la demande : le pic était annoncé. Le maillon qui "
    "manque, c'est la traduction de cette prévision en ressources. Combien d'heures de "
    "main-d'œuvre, combien de préparateurs, combien de chariots, par zone et par jour ? "
    "Aujourd'hui, cette traduction repose sur l'intuition du chef d'équipe et sur des ratios "
    "figés."
)

REPONSE = (
    "L'application traduit le volume prévu en heures, effectifs et équipements par site, zone et "
    "jour, avec deux modèles comparés (régression linéaire et réseau de neurones). Elle confronte "
    "ces besoins à la capacité planifiée, alerte dès le lundi en cas de sous-effectif, de "
    "sureffectif ou de pénurie d'équipements, puis mesure a posteriori la fiabilité des "
    "prévisions et la performance (KPI, rapports)."
)

CARTOGRAPHIE = [
    ("2. Prévision et planification", 0, False),
    ("2.1 Prévision de la demande — 2.1.1 fournit le volume prévu", 1, False),
    ("2.2 S&OP — planification des ventes et des opérations", 1, False),
    (
        "2.3 Planification des capacités : évaluation et ajustement des "
        "ressources nécessaires pour absorber la charge prévue",
        1,
        False,
    ),
    ("2.3.3 Ressources humaines et équipements — objet de cette application", 2, True),
    ("Processus voisins utilisateurs du plan", 0, False),
    ("4.2 Réception et mise en stock", 1, False),
    (
        "4.4 Préparation et expédition des commandes (4.4.1 Prélèvement, "
        "4.4.3 Mise à quai et chargement)",
        1,
        False,
    ),
    ("6.3.1 Définition des engagements de service", 1, False),
]


class FenetreAPropos(DialogueBase):
    """Situation, problème, place du sous-processus 2.3.3 dans le CSCMP, version."""

    def __init__(self, parent) -> None:
        super().__init__(parent, "À propos", redimensionnable=True)
        ttk.Label(self.corps, text=NOM_APPLICATION, style="Titre.TLabel").pack(anchor="w")
        ttk.Label(
            self.corps,
            text=f"Version {VERSION} — projet universitaire de cartographie des "
            "processus Supply Chain (référentiel CSCMP)",
            style="Aide.TLabel",
        ).pack(anchor="w", pady=(0, 10))
        texte = tk.Text(
            self.corps,
            width=96,
            height=28,
            wrap="word",
            relief="flat",
            background=COULEURS["surface"],
            padx=12,
            pady=10,
            borderwidth=0,
        )
        defil = ttk.Scrollbar(self.corps, orient="vertical", command=texte.yview)
        texte.configure(yscrollcommand=defil.set)
        texte.pack(side="left", fill="both", expand=True)
        defil.pack(side="left", fill="y")
        texte.tag_configure(
            "titre", font=("", 12, "bold"), foreground=COULEURS["primaire"], spacing1=10, spacing3=4
        )
        texte.tag_configure("corps", spacing2=2, spacing3=6)
        texte.tag_configure("niveau0", lmargin1=8, lmargin2=8, font=("", 10, "bold"))
        texte.tag_configure("niveau1", lmargin1=28, lmargin2=40)
        texte.tag_configure("niveau2", lmargin1=48, lmargin2=60)
        texte.tag_configure("focus", foreground=COULEURS["rouge"], font=("", 10, "bold"))
        for titre, contenu in (
            ("La situation", SITUATION),
            ("Le problème", PROBLEME),
            ("Ce que fait l'application", REPONSE),
        ):
            texte.insert("end", titre + "\n", "titre")
            texte.insert("end", contenu + "\n", "corps")
        texte.insert("end", "Place dans la cartographie CSCMP\n", "titre")
        for libelle, niveau, focus in CARTOGRAPHIE:
            puce = "▸ " if niveau else ""
            tags = (f"niveau{niveau}", "focus") if focus else (f"niveau{niveau}",)
            texte.insert("end", f"{puce}{libelle}\n", tags)
        texte.configure(state="disabled")
        self.ajouter_bouton("Fermer", self.fermer, primaire=True, defaut=True)
