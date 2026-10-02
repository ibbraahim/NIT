# Workly — Planification · Ressources · Performance

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

## Apparence

Deux thèmes : **sombre** (par défaut, dans l'esprit de la marque) et **clair**. Le bouton
soleil / lune de l'en-tête bascule de l'un à l'autre, et le choix est mémorisé dans
`preferences.json` (fichier local, non versionné).

Tkinter ne sait ni arrondir un cadre, ni peindre un dégradé, ni porter une ombre : les cartes à
coins arrondis, les boutons en pilule, les pastilles de statut, les icônes, les cases à cocher
et les cartes d'indicateurs en dégradé sont de petites images générées avec PIL
(`app/gui/formes.py`, `app/gui/icones.py`, `app/gui/indicateurs.py`) aux couleurs du thème
courant ; la palette des deux thèmes est définie dans `app/gui/style.py` et les widgets de
l'interface (carte, navigation, onglets en pilules, cartes d'indicateurs, tracés) dans
`app/gui/widgets/`. Les graphiques (anneau, jauge, barres arrondies, aires en dégradé) sont
tracés avec matplotlib dans ces mêmes couleurs.

## Méthodes de prévision

Trois méthodes sont entraînées, évaluées et comparées sur les mêmes données (scikit-learn,
`app/ml/entrainement.py`) : la **régression linéaire** (RL), le **réseau de neurones** (RN) et le
**gradient boosting** (GB, arbres de décision boostés). Chacune produit des heures, un effectif et
des équipements par zone et par jour, avec un intervalle de confiance. L'écran Modèles règle leurs
hyperparamètres ; l'activation d'une version, et le choix de la méthode retenue pour le plan de
charge, restent une décision de l'administrateur (jamais automatique). Le taux de victoire d'une
méthode est la part des jours où son erreur est strictement la plus faible face aux deux autres.

Les bases créées avant l'ajout du gradient boosting sont migrées automatiquement à l'ouverture
(nouvelle valeur du type `methode_prevision`), sans réinitialisation.

## Bottom line : l'impact de Workly

Le tableau de bord du **responsable** et de la **direction** se termine par un bloc « Bottom
line — l'impact de Workly » (filtres site, zone et période du tableau de bord). Il chiffre ce que
Workly change par rapport à un planning reconduit chaque semaine :

| Volet | Contenu |
|---|---|
| Ressources humaines et heures | heures de travail mal allouées (déficit couvert en heures sup., heures payées inutilisées) et postes-jours évités, sans / avec Workly |
| Coûts | coût des heures sup., des heures inutilisées et pénalités de retard, sans / avec Workly ; gain net |
| Délais | commandes en retard évitées et taux de service estimé |
| Système d'alertes | alertes émises et traitées, délais de prise en charge et de résolution, part des alertes émises avant la date concernée |
| Équipements et service | pénuries d'équipement traitées à l'avance et coût évité |
| ROI et automatisation | gain annualisé, retour sur investissement, délai de rentabilisation, tâches automatiques exécutées et temps manuel évité |
| Graphiques | anneau des commandes en retard évitées, jauge du taux de service, indices « sans Workly = 100 » (coût, gaspillage, heures sup., pénalités), gain cumulé jour après jour, gain par zone, répartition du gain |

Méthode (`app/services/bottom_line.py`) : pour chaque jour et chaque zone, le **besoin réel**
(heures travaillées moins heures inactives) est comparé au plan « sans Workly » (le réel du même
jour de la semaine précédente) et au plan « avec Workly » (prévision d'heures de la méthode
retenue pour le plan). Les heures manquantes sont
valorisées au taux d'heures supplémentaires, les heures en trop au taux interne (coûts horaires de
l'onglet Administration → Capacités et coûts).

Cinq paramètres de valorisation se règlent dans la même carte « Paramètres du bottom line » :
pénalité par commande en retard, part des commandes retardées par heure manquante, coût d'un
jour de pénurie, coût de mise en place (pour le ROI) et temps manuel évité par tâche automatique.

## Tâches automatiques

Neuf tâches, journalisées dans `journal_taches` et visibles depuis Administration → Tâches
(`app/taches/planificateur.py`) :

| Tâche | Cas d'utilisation | Fréquence par défaut |
|---|---|---|
| `import_historique` | UC04 (import), UC06 | quotidienne, 01:00 |
| `comparaison_quotidienne` | UC20, UC21 | quotidienne, 01:30 |
| `kpi_quotidiens` | UC16, UC17 (jour) | quotidienne, 01:45 |
| `alertes_capacite` | UC18 | quotidienne, 01:50 |
| `previsions_quotidiennes` | UC11 (J+1 à J+14) | quotidienne, 02:00 |
| `rapport_quotidien` | UC23 (jour) | quotidienne, 06:00 |
| `hebdomadaire` | UC08 (ne change jamais le modèle actif), UC17 (semaine), UC23 (semaine) | hebdomadaire (jour/heure configurables, par défaut lundi 03:00) |
| `mensuel` | UC17 (mois), UC23 (mois) | 1er du mois, 04:00 |
| `annuel` | UC17 (année), UC23 (année) | 1er janvier, 05:00 |

Démarrage et suspension se font depuis l'écran Administration (bouton « Démarrer le
planificateur » / « Suspendre le planificateur ») ; l'état s'affiche dans la barre du bas.
Exécution manuelle, sans passer par l'interface :

```bash
python -m app.taches lister                    # tâches disponibles
python -m app.taches executer <nom_tache>       # exécute et journalise le résultat
python -m app.taches serveur                    # point d'accès HTTP (jeton WORKLY_TOKEN_TACHES)
```

Pour piloter ces tâches depuis une plateforme d'automatisation externe, voir
`docs/automatisation_plateforme.md` (déclencheurs, nœuds, secrets et scénarios).

## Tests

```bash
python -m pytest                    # tests unitaires et d'intégration (base <nom_base>_test)
xvfb-run -a python -m pytest        # sous Linux sans affichage, pour les tests d'interface
```

La base de test `<nom_base>_test` est créée puis supprimée automatiquement. `tests/test_langue.py`
vérifie qu'aucun identifiant n'est accentué et qu'aucun texte d'interface n'est resté en anglais ;
`tests/test_generateur_demo.py` rejoue bout en bout le scénario du lundi matin (historique,
prévisions, plan de charge, comparaisons, KPI, alertes et rapport) et sert de test d'acceptation.

## Sauvegarde et restauration

La base contient les plans validés et l'historique : elle doit être sauvegardée régulièrement,
indépendamment de tout code applicatif.

**Sauvegarde** (produit un fichier compressé, sans bloquer les utilisateurs connectés) :

```bash
pg_dump --host=<hote> --port=<port> --username=planif_app --format=custom \
    --file=planification_233_$(date +%Y%m%d).dump planification_233
```

**Restauration** vers une base vide (existante ou recréée avec `python -m app.bd.init_bd`,
sans `--demo`) :

```bash
pg_restore --host=<hote> --port=<port> --username=planif_app --dbname=planification_233 \
    --clean --if-exists planification_233_20260101.dump
```

`--clean --if-exists` supprime les objets existants avant de les recréer à partir de la
sauvegarde ; sans base vide au préalable, retirez ces deux options pour ne restaurer que ce qui
manque. Le mot de passe est demandé interactivement, ou fourni via la variable d'environnement
`PGPASSWORD`.

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
