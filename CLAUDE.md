# CLAUDE.md — Workly (Planification · Ressources · Performance)

Ce fichier décrit l'application pour qu'un assistant (ou un développeur) puisse la comprendre,
la faire évoluer ou la reconstruire à l'identique. Détails complémentaires : `README.md`,
`docs/plan.md` (cadrage initial : arborescence, schéma SQL, écrans, décisions), `docs/automatisation_plateforme.md`
(pilotage externe des tâches), `docs/workflow_automation_workly.bpmn` et `docs/workflow_workly.bpmn` (BPMN 2.0).

## 1. Objet

Application de bureau qui traduit une **prévision de volume** en **ressources nécessaires**
(heures de main-d'œuvre, effectifs, équipements) par site, zone et jour, pour le sous-processus
**2.3.3 « Ressources humaines et équipements »** (métier 2 « Prévision et planification »,
sous-métier 2.3 « Planification des capacités », référentiel CSCMP), dans un contexte de
plateforme logistique (devise par défaut : MAD).

Scénario fil rouge, rejoué par le jeu de démonstration et décrit dans l'écran « À propos » :
un lundi matin, la prévision annonce un pic de +40 % jeudi, mais le planning reste celui de la
semaine précédente et deux chariots élévateurs sont en maintenance. L'application confronte
besoin et capacité, alerte à temps, puis mesure a posteriori la fiabilité des prévisions et la
performance (KPI, rapports, bloc « Bottom line »).

## 2. Stack et conventions

- **Python ≥ 3.11** (CI en 3.12), **Tkinter / ttk**, **PostgreSQL ≥ 13**, `psycopg2-binary`
  (pool `ThreadedConnectionPool`), pandas, numpy, scikit-learn, joblib, matplotlib, reportlab
  (PDF, police DejaVu fournie), openpyxl (Excel), APScheduler 3.x (`<4`), tkcalendar, babel, PIL.
- **Tout en français** : interface, messages d'erreur, journaux, commits, docstrings, et
  **identifiants sans accents** (`tests/test_langue.py` le vérifie, ainsi qu'aucun texte
  d'interface resté en anglais). Formats français : dates `JJ/MM/AAAA`, nombres `1 250,5`,
  pourcentages `12,3 %` (`app/utils/format_fr.py`) ; noms de fichiers générés en `AAAA-MM-JJ`.
- Style : `black` et `ruff` (ligne de 100 caractères, `py311`), config dans `pyproject.toml`.
- Marqueurs pytest : `integration` (base PostgreSQL de test), `gui` (affichage ; `xvfb-run -a` sous Linux).
- Requêtes SQL 100 % paramétrées, une transaction par cas d'utilisation.
- Fichiers non versionnés : `config.ini`, `preferences.json`, `journaux/*`, `rapports/*`,
  `sauvegardes/*`, `modeles_enregistres/*`, `entrees/{historique,previsions,traites}/*`
  (dossiers conservés par `.gitkeep`).

## 3. Architecture (3 couches strictement séparées)

```
app/bd/         schéma PostgreSQL (schema.sql), connexion, init_bd, catalogue_kpi.py, un dépôt par domaine (SQL seulement)
app/services/   logique métier, un module par paquet de cas d'utilisation ; droits vérifiés à chaque appel (Contexte)
app/gui/        Tkinter : une vue par écran (gui/vues/), widgets réutilisables (gui/widgets/), thèmes (style.py)
app/ml/         préparation des variables, entraînement, prédiction (scikit-learn)
app/taches/     tâches automatiques (planificateur APScheduler, CLI, serveur HTTP, notifications, sauvegarde)
app/demo/       générateur du jeu de démonstration (graine 42, reproductible)
app/utils/      format_fr, dates, validation, fichiers_excel, fichiers_pdf, cli, progression…
```

Règles : les services n'importent **jamais** Tkinter ; l'interface n'exécute **jamais** de SQL.
Chaque service reçoit un `Contexte` (utilisateur, rôle, sites ; `app/contexte.py`) ; les tâches
automatiques utilisent un contexte « système » (acteur « Planificateur de tâches ») limité à
ses droits (ex. `reconduction_capacites`). Erreurs métier en français dans `app/erreurs.py`.
Un entraînement ne change **jamais** le modèle actif : l'activation reste une décision de l'administrateur.

## 4. Rôles et écrans

Rôles : `planificateur`, `responsable` (d'exploitation), `direction`, `administrateur`.
Comptes de démonstration (`ressources/demo/comptes_demo.csv`) : `admin/Admin2026!`,
`planif/Planif2026!`, `resp/Resp2026!`, `direction/Direction2026!`.

| Écran | Cas d'utilisation | Rôles |
|---|---|---|
| Connexion | UC01 | tous |
| Données (historique d'activité, prévisions de volume ; saisie + import CSV/Excel) | UC04, UC05, UC06 | planificateur |
| Modèles (paramètres, entraînement, activation de version) | UC07–UC10 | administrateur |
| Prévisions | UC11 | planificateur (génère), responsable (lecture) |
| Plan de charge (proposer, simuler un scénario, soumettre, valider/rejeter) | UC12–UC14 | planificateur, responsable |
| Comparaison réel / prévu | UC20, UC21 | responsable |
| KPI et cibles | UC15–UC17 | responsable |
| Alertes (prendre en charge, clôturer) | UC18, UC19 | planificateur, responsable |
| Tableau de bord (+ bloc Bottom line) | UC22 | planificateur, responsable, direction |
| Rapports (PDF + Excel) | UC23, UC24 | responsable |
| Administration (utilisateurs, sites/zones, équipements, capacités et coûts, tâches) | UC02, UC03 | administrateur |
| À propos (menu Aide) | — | tous |

Boutons non autorisés : non affichés ; boutons inutilisables : grisés avec info-bulle. Les
libellés exacts des boutons sont listés dans `docs/plan.md` §3 (rappel : « Enregistrer »/« Annuler »
pour les saisies, « Oui »/« Non » pour les confirmations, « Fermer » pour l'information).
Deux thèmes (sombre par défaut, clair) basculables par le bouton soleil/lune ; choix mémorisé
dans `preferences.json`. Les cartes arrondies, boutons en pilule, pastilles, icônes et cartes
d'indicateurs en dégradé sont des images PIL (`gui/formes.py`, `icones.py`, `indicateurs.py`) ;
palette dans `gui/style.py` (sombre : navy `#0C1124`, surface `#141A33`, texte `#F2F4FF`). Logo dans `ressources/images/`.

## 5. Données (PostgreSQL)

`app/bd/schema.sql` crée types ENUM, tables, contraintes et index ; `init_bd` insère aussi le
catalogue des 20 KPI. Tables principales : `utilisateurs`, `utilisateurs_sites`,
`journal_connexions`, `sites`, `zones`, `equipements`, `indisponibilites_equipements`,
`capacites_personnel`, `couts_horaires`, `historique_activite`, `previsions_volume`,
`parametres_modele`, `modeles_versions`, `previsions_ressources`, `comparaisons_realise`,
`plans_charge`, `plans_charge_lignes`, `scenarios`, `kpi_definitions`, `objectifs_kpi`,
`kpi_valeurs`, `alertes`, `rapports`, `journal_taches`, `parametres_application`, plus les
tables du bottom line (`app/bd/depots/bottom_line.py`). Le schéma complet et ses contraintes
sont décrits dans `docs/plan.md` §2 (à jour du schéma réel : lire `schema.sql` en cas de doute).
`methode_prevision` = `regression_lineaire`, `reseau_neurones`, `gradient_boosting` (les bases
anciennes sont migrées automatiquement à l'ouverture).

Les 20 KPI (formules et cibles dans `app/bd/catalogue_kpi.py`) : précision (`MAE_H`, `RMSE_H`,
`MAPE_H`, `BIAIS_H`, `COUV_IC`, `TAUX_VICTOIRE`), ressources humaines (`ADEQUATION`,
`TAUX_SOUS_CHARGE`, `TAUX_HS`, `TAUX_INTERIM`, `TAUX_ABSENTEISME`, `PRODUCTIVITE`),
équipements (`TAUX_DISPO_EQP`, `TAUX_UTIL_EQP`, `ECART_EQP`, `JOURS_PENURIE`), coûts
(`COUT_UNITE`, `ECART_COUT`), service (`TAUX_A_TEMPS`, `DELAI_ANTICIPATION`). Statuts : vert / orange / rouge / gris.

## 6. Prévision (app/ml)

Trois méthodes entraînées et comparées sur les mêmes données : régression linéaire (RL),
réseau de neurones (RN), gradient boosting (GB). Variables : jour de semaine (one-hot),
sin/cos du mois, moyenne mobile 7 jours **décalée** (J-7…J-1, sans fuite), indicateur de pic.
Découpage chronologique 80/20, scaler ajusté sur l'apprentissage seul (`Pipeline`), modèles
sauvegardés en joblib dans `modeles_enregistres/`. Métriques : MAE, RMSE, MAPE, biais,
couverture de l'intervalle de confiance (IC par quantiles des résidus). Sorties : heures, effectif, équipements
par zone et jour. Taux de victoire d'une méthode = part des jours où son erreur est strictement la plus faible.
Deux niveaux d'activation : `actif` (version par site/zone/méthode/cible, utilisée par UC11) et
`retenue_pour_plan` (méthode utilisée par UC12/UC21). Hors démo, UC11/UC12 refusent tant qu'aucune version n'est activée.

## 7. Règles métier à connaître

- Plateforme ouverte du lundi au samedi ; dimanche fermé (volume nul, exclu du MAPE).
- Heures planifiées = (effectif planifié + intérim planifié) × durée de poste.
- Capacité d'équipements d'un jour = équipements actifs de la zone, hors `hors_service` et hors indisponibilités à cette date.
- Alertes de sous/sureffectif portent sur le **plan validé** : sous-effectif J+1–J+2 = rouge, J+3–J+7 = orange ;
  sureffectif contrôlé sur J+1…J+14 ; alertes dédupliquées par clé tant qu'elles ne sont pas résolues ; clôture avec action menée obligatoire.
- Seuil de dérive par défaut : MAPE hebdomadaire > 10 % (alerte `derive_modele`).
- Connexion : sel + hachage, verrouillage après tentatives échouées, journal des connexions.
- **Bottom line** (`app/services/bottom_line.py`) : pour chaque jour/zone, besoin réel comparé au plan « sans Workly »
  (réel du même jour de la semaine précédente) et « avec Workly » (prévision de la méthode retenue) ; heures manquantes
  valorisées au taux d'heures sup, heures en trop au taux interne ; pénalités de retard, ROI, temps manuel évité.
- Démo (`init_bd --demo`, `--date-reference AAAA-MM-JJ`) : sous-prévision du pic de jeudi, sureffectif du mardi suivant,
  pénurie de chariots, plans « statu quo » validés, rétro-prévisions sur le passé, rapport généré.

## 8. Tâches automatiques (12)

`sauvegarde_base` (pg_dump, 14 copies), `import_historique`, `import_previsions_volume`,
`capacites_semaine`, `comparaison_quotidienne`, `kpi_quotidiens`, `alertes_capacite`,
`previsions_quotidiennes` (J+1…J+14), `rapport_quotidien`, `hebdomadaire` (réentraînement ; ne change jamais
le modèle actif), `mensuel`, `annuel`. Journalisées dans `journal_taches`, visibles dans Administration → Tâches.
Fréquences par défaut et détail : `README.md` § « Tâches automatiques ».

- CLI : `python -m app.taches lister | executer <nom> | serveur`.
- Serveur HTTP (`app/taches/serveur.py`, défaut `127.0.0.1:8765`, refuse de démarrer sans `WORKLY_TOKEN_TACHES`) :
  `GET /sante`, `GET /taches`, `POST /taches/<nom>`, `GET /aujourdhui`, `POST /taches-du-jour`, `POST /cycle-nocturne`,
  `POST /alerte?etape=`, `POST /test-mail` ; authentification `Authorization: Bearer <jeton>` ; une seule tâche à la fois (409).
- Pipeline unique piloté par une plateforme externe (Fusion AI Automation / n8n), horaires en UTC : cron 00:30 →
  santé → P1 sauvegarde → P2 import historique → P3 import prévisions → P4 comparaison → P5 KPI → P6 alertes →
  P7 prévisions → P8 rapport → P9 tâches du jour (dimanche, lundi, 1er du mois, 1er janvier) ; surveillance `/sante`
  toutes les 10 min ; échec d'étape → `POST /alerte` puis arrêt (sauf sauvegarde). Voir `docs/automatisation_plateforme.md`.
- Alertes e-mail SMTP (`app/taches/notifications.py`) par variables d'environnement : `WORKLY_SMTP_UTILISATEUR`,
  `WORKLY_SMTP_MOT_DE_PASSE` (mot de passe d'application), `WORKLY_ALERTE_DESTINATAIRE`, `WORKLY_SMTP_HOTE`, `WORKLY_SMTP_PORT`.
  Autres : `WORKLY_SAUVEGARDES_CONSERVEES`, `WORKLY_PG_DUMP`.
- Windows : `scripts/configurer_alertes.ps1` (une fois), `scripts/demarrer_workly.ps1` (serveur + ngrok),
  `scripts/installer_demarrage_auto.ps1` (démarrage à l'ouverture de session).

## 9. Commandes utiles

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp config.exemple.ini config.ini                  # puis renseigner hôte, base, utilisateur, mot de passe
python -m app.bd.init_bd [--demo] [--reinitialiser] [--date-reference AAAA-MM-JJ]
python -m app                                     # lancer l'application
xvfb-run -a python -m pytest                      # tests (base <nom_base>_test créée puis supprimée)
black --check . && ruff check .                   # format et style (exigés par la CI)
```

PostgreSQL : `CREATE ROLE planif_app LOGIN CREATEDB PASSWORD '…';` avant la première initialisation.
CI GitHub (`.github/workflows/tests.yml`) : PostgreSQL 16, Python 3.12, `python3-tk` + `xvfb`, black, ruff, pytest.

## 10. Façon de travailler attendue

- Avancer par lots, avec à la fin de chacun `pytest`, `black --check`, `ruff`, puis un commit en français.
- Les tests couvrent formules KPI, services, droits, écrans, thèmes, langue, et un **test d'acceptation** rejouant
  le scénario du lundi matin (`tests/test_generateur_demo.py`).
- Les choix par défaut non fixés par l'énoncé d'origine sont consignés dans `docs/plan.md` § « Questions et points discutables ».
- Le cahier des charges d'origine (`prompt_claude_code_app_2.3.3.md`) et les cas d'utilisation UC01–UC24 ne sont
  pas dans le dépôt : pour une reconstruction fidèle, les fournir à l'assistant en plus de ce fichier.
