# Plan de réalisation — Planification RH et équipements (CSCMP 2.3.3)

> Document de cadrage à valider avant le développement (étape 1 du déroulé).
> Référence : `prompt_claude_code_app_2.3.3.md`. Les écarts et les points discutables sont listés en section 6.

---

## 1. Arborescence des fichiers

```
app/
  __init__.py                    version de l'application (« 1.0.0 »)
  __main__.py                    python -m app : démarre la fenêtre de connexion
  config.py                      lecture et validation de config.ini (message français si absent/incomplet)
  journal.py                     journalisation fichier journaux/application.log (messages en français)
  erreurs.py                     exceptions métier en français (ErreurMetier, AccesRefuse, DonneesInvalides, ErreurBaseDonnees…)
  contexte.py                    Contexte d'exécution (utilisateur, rôle, sites) + contexte « systeme » des tâches
  bd/
    connexion.py                 pool psycopg2 (ThreadedConnectionPool), gestionnaire de transaction
    schema.sql                   création complète de la base (types, tables, contraintes, index)
    donnees_initiales.sql        catalogue des 20 KPI et cibles par défaut
    init_bd.py                   python -m app.bd.init_bd [--demo] [--reinitialiser]
    depots/
      utilisateurs.py  referentiels.py  historique.py  previsions.py  plans.py
      kpi.py  alertes.py  rapports.py  modeles.py  taches.py  parametres.py
  services/                      une fonction publique par cas d'utilisation, droits vérifiés ici
    auth.py            UC01 authentifier
    admin.py           UC02 (gerer_utilisateur…), UC03 (gerer_site, gerer_zone, gerer_equipement,
                       declarer_indisponibilite, enregistrer_capacites, enregistrer_couts…)
    donnees.py         UC04 importer_historique / saisir_historique, UC05 importer_previsions_volume /
                       saisir_prevision_volume, UC06 controler_qualite
    modeles.py         UC07 parametrer_modeles, UC08 entrainer_modeles, UC09 evaluer_modele, UC10 changer_modele_actif
    planification.py   UC11 generer_previsions, UC12 elaborer_plan_charge, UC13 simuler_scenario, UC14 valider_plan
    kpi.py             UC15 definir_cible, UC16 calculer_kpi, UC17 comparer_kpi_cibles, règles de statut
    alertes.py         UC18 emettre_alertes, UC19 traiter_alerte
    comparaison.py     UC20 comparer_realise, UC21 detecter_derive
    reporting.py       UC22 consulter_tableau_bord, UC23 generer_rapport
    export.py          UC24 exporter_rapport (PDF reportlab, Excel openpyxl) + exports Excel des écrans
  ml/
    preparation.py     construction des variables (one-hot jour, sin/cos mois, moyenne mobile 7 j décalée)
    entrainement.py    découpage chronologique 80/20, RL et RN, évaluation, sauvegarde joblib
    prediction.py      prédiction ponctuelle + IC par quantiles des résidus
  taches/
    planificateur.py   APScheduler (BackgroundScheduler) + écriture dans journal_taches
    definitions.py     les 9 tâches et leurs enchaînements
    __main__.py        python -m app.taches executer <nom_tache> | lister
  demo/
    generateur.py      jeu de démonstration reproductible (graine 42)
  gui/
    style.py                   unique feuille de style ttk (couleurs, polices, statuts vert/orange/rouge/gris)
    fenetre_principale.py      bandeau, menu par rôle + compteur d'alertes, barre d'état, zone de contenu
    connexion.py               écran 1
    vues/
      tableau_bord.py  donnees.py  previsions.py  plan_charge.py  comparaison.py
      kpi_cibles.py  alertes.py  rapports.py  modeles.py  administration.py  a_propos.py
    widgets/
      tableau_triable.py  tuile_kpi.py  selecteur_periode.py  graphique.py
      dialogues.py      boîtes personnalisées (Oui / Non / Annuler / Fermer), saisie de commentaire
      champs.py         champs avec validation (cadre rouge + message sous le champ), info-bulles
      taches_fond.py    exécution en thread + barre de progression + « Annuler »
  utils/
    format_fr.py   dates (JJ/MM/AAAA, « jeudi 12 mars 2026 »), nombres (1 250,5), pourcentages (12,3 %), devise
    dates.py       lundi de la semaine, bornes jour/semaine/mois/année, horizons
    validation.py  validateurs de saisie (nombres, dates, obligatoires)
ressources/
  polices/DejaVuSans.ttf, DejaVuSans-Bold.ttf
  modeles_fichiers/modele_historique_activite.csv, modele_previsions_volume.csv
modeles_enregistres/   rapports/   journaux/   entrees/historique/   entrees/traites/
tests/
  conftest.py (fixtures base <nom_base>_test créée / supprimée), test_format_fr.py, test_kpi_formules.py,
  test_kpi_statuts.py, test_qualite_donnees.py, test_ml.py, test_ressources.py, test_alertes.py,
  test_droits.py, test_depots.py, test_scenario_demo.py, test_gui_fumee.py, test_langue.py
docs/
  plan.md (ce document), bilan.md (fin de projet)
README.md   requirements.txt   config.exemple.ini   pyproject.toml (black, ruff, pytest)
```

---

## 2. Schéma de base de données (PostgreSQL 13+)

**Types ENUM**
- `role_utilisateur` : planificateur, responsable, direction, administrateur
- `statut_equipement` : disponible, maintenance, hors_service
- `categorie_cout` : interne, heures_sup, interim
- `methode_prevision` : regression_lineaire, reseau_neurones
- `cible_modele` : heures, equipements
- `statut_version` : retenue, non_retenue
- `statut_plan` : brouillon, soumis, valide, rejete
- `periodicite` : jour, semaine, mois, annee
- `sens_kpi` : hausse, baisse, plage, information
- `famille_kpi` : precision, rh, equipements, couts, service
- `statut_kpi` : vert, orange, rouge, gris
- `type_alerte` : seuil_kpi, sous_effectif, sureffectif, penurie_equipement, derive_modele
- `niveau_alerte` : orange, rouge
- `statut_alerte` : ouverte, en_cours, resolue
- `format_rapport` : pdf, excel, pdf_excel
- `statut_tache` : en_cours, succes, echec

**Tables** (toutes avec `id … GENERATED ALWAYS AS IDENTITY PRIMARY KEY`, FK, `CHECK (… >= 0)`, pourcentages `BETWEEN 0 AND 100`)

| Table | Colonnes principales | Contraintes / index |
|---|---|---|
| `utilisateurs` | identifiant, nom, prenom, email, hash_mot_de_passe, sel, role, actif, tentatives_echouees, verrouille_jusqu_a, date_creation | unique(identifiant) |
| `utilisateurs_sites` | utilisateur_id, site_id | PK composite |
| `journal_connexions` | utilisateur_id (nullable), identifiant_saisi, date, succes | index(date) |
| `sites` | nom, adresse, actif | unique(nom) |
| `zones` | site_id, nom, type_equipement_principal, duree_poste_heures, actif | unique(site_id, nom), CHECK durée > 0 |
| `equipements` | site_id, zone_id, type, code, statut, actif | unique(site_id, code) |
| `indisponibilites_equipements` | equipement_id, date_debut, date_fin, motif | CHECK fin ≥ début, index(dates) |
| `capacites_personnel` | site_id, zone_id, date, effectif_planifie, absences_prevues (voir Q2) | unique(site_id, zone_id, date) |
| `couts_horaires` | categorie, taux, devise, date_debut | unique(categorie, date_debut) |
| `historique_activite` | site_id, zone_id, date, volume_traite, effectif_present, heures_travaillees, heures_sup, heures_interim, heures_absence, heures_inactives, equipements_mobilises, heures_usage_equipement, heures_disponibles_equipement, heures_panne_equipement, cout_rh, commandes_a_temps, commandes_totales, indicateur_pic, source, date_maj | unique(site_id, zone_id, date), CHECK commandes_a_temps ≤ commandes_totales |
| `previsions_volume` | site_id, zone_id, date, volume_prevu, indicateur_pic, source, date_maj | unique(site_id, zone_id, date) |
| `parametres_modele` | configuration JSONB, date, auteur_id | la plus récente fait foi |
| `modeles_versions` | methode, site_id, zone_id, cible, chemin_fichier, metriques JSONB (mae, rmse, mape, biais, couverture, residus_test), coefficients JSONB, parametres JSONB, statut, actif, retenue_pour_plan (voir Q3), date_entrainement | index unique partiel : une seule version active par (site, zone, méthode, cible) |
| `previsions_ressources` | site_id, zone_id, date, modele_version_id, methode, volume_prevu, heures, effectif, equipements, ic_bas, ic_haut, ic_bas_equipements, ic_haut_equipements, date_generation | unique(site_id, zone_id, date, methode, date_generation), index(site, zone, date) |
| `comparaisons_realise` | prevision_id, heures_reelles, equipements_reels, ecart_absolu, ecart_relatif, ecart_equipements, dans_ic, comparable, date_calcul | unique(prevision_id) |
| `plans_charge` | site_id, semaine (lundi), statut, commentaire, cree_par, soumis_par, valide_par, date_creation, date_soumission, date_validation | unique(site_id, semaine), CHECK semaine = lundi |
| `plans_charge_lignes` | plan_id, zone_id, date, besoin_heures, besoin_effectif, besoin_equipements, effectif_planifie, interim_planifie, equipements_planifies, capacite_effectif, capacite_equipements, commentaire | unique(plan_id, zone_id, date) |
| `scenarios` | plan_id, hypotheses JSONB, resultats JSONB, applique, auteur_id, date | |
| `kpi_definitions` | code, libelle, famille, formule, unite, sens, par_methode | unique(code) |
| `objectifs_kpi` | kpi_id, site_id NULL, zone_id NULL, periodicite, sens, valeur_cible, seuil_orange, seuil_rouge, valeur_min, valeur_max, date_debut_validite, date_fin_validite | index(kpi_id, periodicite) |
| `kpi_valeurs` | kpi_id, site_id, zone_id NULL, periodicite, date_debut_periode, methode NULL, valeur, cible, statut, date_calcul | unique NULLS NOT DISTINCT impossible en PG13 → index unique sur `COALESCE(zone_id,0)`, `COALESCE(methode::text,'')` |
| `alertes` | type, niveau, kpi_id NULL, site_id, zone_id NULL, date_concernee, cle_deduplication, message, statut, assigne_a, assigne_responsable, action_menee, pris_en_charge_par, date_creation, date_maj, date_prise_en_charge, date_resolution | index unique partiel sur cle_deduplication WHERE statut <> 'resolue' ; CHECK action_menee non vide si résolue |
| `rapports` | periodicite, date_debut, date_fin, site_id, format, chemin_pdf, chemin_excel, contenu JSONB, genere_par (FK nullable), genere_par_systeme, date_generation | index(site, periodicite) |
| `journal_taches` | tache, debut, fin, statut, message | index(tache, debut) |
| `parametres_application` | cle, valeur | pour le drapeau « données de démonstration » et la dernière synchronisation |

---

## 3. Écrans et boutons (exactement ceux du prompt)

| # | Écran (fichier) | Rôles | Boutons |
|---|---|---|---|
| — | Bandeau commun | tous | « Se déconnecter » |
| 1 | Connexion (`gui/connexion.py`) | tous | « Se connecter » (Entrée), « Quitter » |
| 2 | Tableau de bord (`tableau_bord.py`) | tous | « ◀ Période précédente », « Période suivante ▶ », « Actualiser » |
| 3 | Données (`donnees.py`) — onglets Historique d'activité / Prévisions de volume | planificateur | « Enregistrer », « Effacer le formulaire », « Importer un fichier… », « Télécharger le modèle de fichier » ; fenêtre de résultat : « Enregistrer les lignes valides », « Exporter le rapport d'erreurs », « Annuler » |
| 4 | Prévisions (`previsions.py`) | planificateur (génère), responsable (lecture) | « Générer les prévisions », « Exporter en Excel » |
| 5 | Plan de charge (`plan_charge.py`) | planificateur, responsable (lecture + validation) | « ◀ Semaine précédente », « Semaine suivante ▶ » ; planificateur : « Proposer le plan », « Simuler un scénario… », « Enregistrer le brouillon », « Soumettre pour validation » ; responsable : « Valider le plan », « Rejeter le plan… » ; fenêtre scénario : « Calculer », « Appliquer au plan », « Fermer » |
| 6 | Comparaison réel / prévu (`comparaison.py`) | responsable | « Lancer la comparaison », « Exporter en Excel » |
| 7 | KPI et cibles (`kpi_cibles.py`) | responsable | Suivi : « Calculer et comparer maintenant » ; Cibles : « Ajouter une cible », « Modifier la cible », « Supprimer la cible » ; fenêtre : « Enregistrer », « Annuler » |
| 8 | Alertes (`alertes.py`) | planificateur, responsable | « Prendre en charge », « Clôturer l'alerte… », « Actualiser » |
| 9 | Rapports (`rapports.py`) | responsable | « Générer le rapport », « Exporter en PDF », « Exporter en Excel », « Ouvrir le rapport sélectionné », « Ouvrir le dossier des rapports » |
| 10 | Modèles (`modeles.py`) | administrateur | Paramètres : « Enregistrer les paramètres », « Rétablir les valeurs par défaut » ; Entraînement : « Entraîner maintenant » (+ « Annuler » pendant l'exécution), « Activer la version sélectionnée » |
| 11 | Administration (`administration.py`) | administrateur | Utilisateurs : « Ajouter », « Modifier », « Désactiver / Réactiver », « Réinitialiser le mot de passe » ; Sites et zones : « Ajouter un site », « Ajouter une zone », « Modifier », « Désactiver » ; Équipements : « Ajouter », « Modifier », « Déclarer une indisponibilité… », « Désactiver » ; Capacités et coûts : « Enregistrer », « Copier la semaine précédente » ; Tâches : « Exécuter la tâche sélectionnée », « Démarrer le planificateur » / « Suspendre le planificateur », « Voir le journal » |
| 12 | À propos (`a_propos.py`, menu « Aide ») | tous | « Fermer » |

Écran d'accueil : Tableau de bord (planificateur, responsable, direction), Modèles (administrateur).
Boutons non autorisés : non affichés. Boutons inutilisables dans l'état courant : grisés + info-bulle explicative.

---

## 4. Ordre des lots

1. **Socle** — config, journal, pool, `schema.sql`, `init_bd`, formatage français, UC01, UC03 (services + onglets Sites et zones / Équipements / Capacités et coûts de l'Administration), fenêtre principale, navigation par rôle, À propos (squelette), dialogues personnalisés.
2. **Données** — UC04, UC05, UC06, écran Données, modèles CSV.
3. **Modèles** — UC07–UC10, `ml/`, écran Modèles, générateur de démonstration (historique, référentiels, comptes).
4. **Prévision et planification** — UC11–UC14, écrans Prévisions et Plan de charge ; la démo génère prévisions et plan.
5. **Comparaison et KPI** — UC15–UC17, UC20, UC21, écrans Comparaison et KPI et cibles.
6. **Alertes** — UC18, UC19, écran Alertes, compteur dans le menu.
7. **Restitution** — UC22–UC24, écrans Tableau de bord et Rapports (PDF DejaVu, Excel).
8. **Automatisation et finitions** — tâches APScheduler + CLI, UC02 et Administration complète, À propos final, test d'acceptation, test de langue, test de fumée GUI, README, bilan.

À la fin de chaque lot : `pytest`, `black --check`, `ruff`, commit en français sur la branche de travail, résumé en 5 lignes.

---

## 5. Choix techniques notables

- **Contexte d'exécution** : chaque fonction de service reçoit un `Contexte` (utilisateur, rôle, sites). Les tâches automatiques utilisent un contexte `systeme` (acteur « Planificateur de tâches ») limité à ses cas d'utilisation.
- **Transaction par cas d'utilisation** ; requêtes 100 % paramétrées.
- **Prévisions sans fuite** : la moyenne mobile 7 jours est calculée sur J-7…J-1 uniquement ; les tests vérifient qu'aucune ligne de test n'influence l'apprentissage (scaler ajusté sur l'apprentissage seul via `Pipeline`).
- **Heures planifiées** (KPI ADEQUATION, alertes de capacité) = (effectif planifié + intérim planifié) × durée de poste.
- **Capacité d'équipements d'une date** = équipements actifs de la zone, hors `hors_service`, hors ceux couverts par une indisponibilité à cette date.
- **Graphiques** : pas de barre d'outils matplotlib (ses info-bulles sont en anglais).
- **Boîtes de fichiers Tk** : `msgcat::mclocale fr` pour franciser les sélecteurs de fichiers sous Linux ; sous Windows/macOS, les boîtes natives suivent la langue du système.

---

## 6. Questions et points discutables

**Q1 — Documents joints absents.** `docs/cas_utilisation_2.3.3.md` et le diagramme ne sont pas dans le dépôt. Je travaille uniquement à partir du prompt, sauf si vous les ajoutez.

**Q2 — « Absences connues ».** UC12 soustrait les absences connues de la capacité, mais aucune table ne les porte. Je propose une colonne `absences_prevues` (en nombre de personnes) dans `capacites_personnel`, saisie dans l'onglet « Capacités et coûts ». Pas de nouvel écran ni bouton.

**Q3 — « Modèle actif » : deux niveaux.** UC11 utilise les deux méthodes, UC12 et UC21 utilisent « le modèle actif ». Je propose :
- `actif` : version active par (site, zone, méthode, cible), utilisée par UC11 ;
- `retenue_pour_plan` : méthode active par (site, zone), utilisée par UC12, UC21 et la colonne « Modèle actif (coché) ».
UC10 (« Activer la version sélectionnée ») active la version et fait de sa méthode la méthode retenue. Comme un entraînement ne change jamais le modèle actif, **en dehors de la démo, UC11/UC12 refusent tant qu'aucune version n'est activée** (message invitant à passer par l'écran Modèles). `init_bd --demo` active les versions via UC10, au nom du compte `admin`, avec trace.

**Q4 — Semaine de démonstration, « mardi suivant » et alertes.** Les alertes de sous- et sureffectif portent sur le **plan validé**. Je propose que la démo crée, pour la semaine de démonstration et la suivante, un plan **validé « statu quo »** (planifié = même planning que la semaine précédente, validé par `resp`), ce qui reproduit la situation et déclenche les alertes. Le « mardi suivant » est le **mardi de la semaine qui suit la semaine de démonstration**. Comme ce mardi peut tomber au-delà de J+7, je propose de contrôler le **sureffectif sur J+1 à J+14** (le prompt ne fixe pas d'horizon pour le sureffectif). Le sous-effectif garde J+1–J+2 = rouge, J+3–J+7 = orange. Le niveau de l'alerte du jeudi dépend donc du jour où la démo est initialisée. En option : `init_bd --demo --date-reference AAAA-MM-JJ` pour rejouer exactement « un lundi matin ».

**Q5 — Rétro-prévisions de démonstration.** Pour que UC20, UC21, les KPI de précision et le taux de victoire aient de la matière, la démo écrit des prévisions de volume et de ressources **sur le passé** (période de test des modèles). La règle « refuser les dates passées » de UC05 s'applique aux saisies et imports des utilisateurs, pas au générateur.

**Q6 — Jours ouvrés.** Je propose : plateforme ouverte du lundi au samedi, dimanche fermé (volume nul, exclu du MAPE). À confirmer, ou ouverture 7 j/7.

**Q7 — Boutons des boîtes de dialogue non listées.** Certaines actions ouvrent une fenêtre de saisie non décrite (rejet du plan, clôture d'alerte, commentaire d'une case rouge, formulaires Ajouter/Modifier de l'administration, indisponibilité). Je propose d'utiliser partout les boutons déjà prévus par le prompt : « Enregistrer » / « Annuler » pour les saisies, « Oui » / « Non » pour les confirmations, « Fermer » pour les informations. Le tableau de bord ouvre une alerte (double-clic) en basculant sur l'écran Alertes, avec l'alerte sélectionnée.

**Q8 — Définitions à confirmer.**
- `TAUX_SOUS_CHARGE` : « heures payées » = heures travaillées (qui incluent heures sup et intérim) ; les heures d'absence ne sont pas comptées comme payées.
- `ECART_COUT` : coût du plan validé = heures internes planifiées × taux `interne` + heures d'intérim planifiées × taux `interim`.
- Répartition des équipements de démo : 4 chariots en Réception, 4 en Stockage, 5 transpalettes en Préparation, 5 en Expédition. Les 2 chariots en maintenance sont en Réception.
- Seuil de dérive par défaut : MAPE hebdomadaire > 10 %.

**Points signalés (appliqués tels quels)**
- Le réentraînement hebdomadaire automatique ne change jamais le modèle actif : sans intervention de l'administrateur, il n'améliore pas les prévisions utilisées. Appliqué conformément au prompt.
- Les noms de fichiers générés utilisent `AAAA-MM-JJ` (imposé), alors que l'affichage utilise `JJ/MM/AAAA`.
- Le prompt parle de tables « minimales ». J'ajoute `parametres_application` (drapeau de démo, dernière synchronisation) et quelques colonnes techniques (clé de déduplication des alertes, statut des versions de modèle).
- Environnement de développement : le Python 3.11 du conteneur n'a pas Tkinter. J'utiliserai `python3-tk` avec Python 3.12, qui reste compatible avec l'exigence « 3.11 ou plus récent », et `xvfb-run` pour les tests d'interface. PostgreSQL 16 est disponible localement pour les tests d'intégration.
