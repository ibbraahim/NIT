# Planification RH et équipements — CSCMP 2.3.3

Application de bureau (Python, Tkinter, PostgreSQL) qui traduit la prévision de volume en
ressources nécessaires — heures de main-d'œuvre, effectifs et équipements — par site, zone et
jour, pour le sous-processus **2.3.3 Ressources humaines et équipements** (métier 2 « Prévision
et planification », sous-métier 2.3 « Planification des capacités » du référentiel CSCMP).

Un lundi matin, sur une plateforme logistique : la prévision de la demande annonce un pic de
+40 % jeudi, mais le planning reste celui de la semaine précédente et deux chariots élévateurs
sont en maintenance. L'application est née pour combler ce maillon manquant : traduire une
prévision de volume déjà connue en heures, effectifs et équipements, confronter ce besoin à la
capacité planifiée, alerter à temps, puis mesurer a posteriori la fiabilité des prévisions et la
performance. Le scénario complet est raconté dans l'écran « À propos » (menu Aide) et rejoué
par le jeu de données de démonstration.

## Installation

1. **PostgreSQL 13 ou plus récent.** Installez le serveur, puis créez un rôle autorisé à créer
   des bases :

   ```sql
   CREATE ROLE planif_app LOGIN CREATEDB PASSWORD 'votre_mot_de_passe';
   ```

2. **Python 3.11 ou plus récent** avec Tkinter (sous Debian/Ubuntu : `sudo apt install python3-tk`).

3. **Dépendances :**

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows : .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Configuration :** copiez `config.exemple.ini` en `config.ini` et renseignez l'hôte, le port,
   le nom de la base, l'utilisateur et le mot de passe.

5. **Création de la base :**

   ```bash
   python -m app.bd.init_bd            # base vide + compte administrateur (mot de passe demandé)
   python -m app.bd.init_bd --demo     # avec les données de démonstration
   ```

   `--reinitialiser` supprime puis recrée une base existante (confirmation demandée) ;
   `--date-reference AAAA-MM-JJ` rejoue la démonstration comme si ce jour était aujourd'hui.

6. **Lancement :** `python -m app`

## Comptes de démonstration

Créés par `python -m app.bd.init_bd --demo` (fichier `ressources/demo/comptes_demo.csv`) :

| Identifiant | Rôle | Mot de passe |
|---|---|---|
| `admin` | Administrateur | `Admin2026!` |
| `planif` | Planificateur | `Planif2026!` |
| `resp` | Responsable d'exploitation | `Resp2026!` |
| `direction` | Direction | `Direction2026!` |

## Écrans

| Écran | Cas d'utilisation | Rôles |
|---|---|---|
| Connexion | UC01 | tous |
| Données | UC04, UC05, UC06 | planificateur |
| Modèles | UC07, UC08, UC09, UC10 | administrateur |
| Prévisions | UC11 | planificateur (génère), responsable (lecture) |
| Plan de charge | UC12, UC13, UC14 | planificateur, responsable |
| Comparaison réel / prévu | UC20 | responsable |
| KPI et cibles | UC15, UC16, UC17 | responsable |
| Alertes | UC18, UC19 | planificateur, responsable |
| Tableau de bord | UC22 | planificateur, responsable, direction |
| Rapports | UC23, UC24 | responsable |
| Administration | UC02, UC03, tâches automatiques | administrateur |
| À propos | — | tous (menu Aide) |

Les 20 KPI (précision des prévisions, ressources humaines, équipements, coûts, service) et
leurs formules exactes sont catalogués dans `app/bd/catalogue_kpi.py` ; les choix par défaut
non explicitement fixés par l'énoncé sont documentés dans `docs/plan.md` (section « Questions et
points discutables »).

## Tâches automatiques

Six tâches, journalisées dans `journal_taches` et visibles depuis Administration → Tâches
(`app/taches/planificateur.py`) :

| Tâche | Cas d'utilisation | Fréquence par défaut |
|---|---|---|
| `entrainer_modeles` | UC08 (ne change jamais le modèle actif) | hebdomadaire (jour/heure configurables) |
| `comparer_realise` | UC20 | quotidienne, 02:00 |
| `calculer_kpi` | UC16, UC17 | quotidienne, 02:15 |
| `detecter_derive` | UC21 | quotidienne, 02:20 |
| `emettre_alertes` | UC18 | quotidienne, 02:30 |
| `generer_rapport` | UC23 | hebdomadaire, lundi 03:00 |

Démarrage et suspension se font depuis l'écran Administration (bouton « Démarrer le
planificateur » / « Suspendre le planificateur ») ; l'état s'affiche dans la barre du bas.
Exécution manuelle, sans passer par l'interface :

```bash
python -m app.taches lister                    # tâches disponibles
python -m app.taches executer <nom_tache>       # exécute et journalise le résultat
```

## Tests

```bash
python -m pytest                    # tests unitaires et d'intégration (base <nom_base>_test)
xvfb-run -a python -m pytest        # sous Linux sans affichage, pour les tests d'interface
```

La base de test `<nom_base>_test` est créée puis supprimée automatiquement. `tests/test_langue.py`
vérifie qu'aucun identifiant n'est accentué et qu'aucun texte d'interface n'est resté en anglais ;
`tests/test_generateur_demo.py` rejoue bout en bout le scénario du lundi matin (historique,
prévisions, plan de charge, comparaisons, KPI, alertes et rapport) et sert de test d'acceptation.

## Architecture

Trois couches strictement séparées (les services n'importent jamais Tkinter, l'interface
n'exécute jamais de SQL) :

```
app/bd/          schéma PostgreSQL, connexion, un dépôt par domaine (SQL uniquement)
app/services/    logique métier : un module par paquet de cas d'utilisation, droits vérifiés
                 à chaque appel via un Contexte (utilisateur, rôle, sites)
app/gui/         Tkinter : un écran par onglet de navigation, widgets réutilisables
app/ml/          préparation des variables, entraînement et prédiction (scikit-learn)
app/taches/      tâches automatiques (APScheduler) et leur CLI
app/demo/        générateur du jeu de démonstration (graine fixe, reproductible)
```

Le détail des choix d'architecture, du schéma de base de données et des décisions par défaut
documentées au fil du projet se trouve dans `docs/plan.md`.

## État du projet

Les 24 cas d'utilisation et les 12 écrans sont implémentés. Le jeu de démonstration reproduit,
de bout en bout, la situation du lundi matin décrite dans l'écran À propos : sous-prévision du
pic de jeudi, sureffectif du mardi suivant, pénurie de chariots élévateurs, KPI et alertes
correspondants, rapport de performance généré. La suite de tests (`python -m pytest`) couvre les
formules, les services, les écrans et le scénario complet.
