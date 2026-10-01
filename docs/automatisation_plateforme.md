# Piloter les tâches automatiques depuis une plateforme d'automatisation

Ce document donne, pas à pas, ce qu'il faut créer dans une plateforme d'automatisation
(déclencheurs, nœuds, outils) pour exécuter la partie automatique de Workly à la place du
planificateur interne. Les noms de blocs sont génériques : chaque plateforme les appelle un peu
différemment (voir le tableau de correspondance en fin de document).

## 1. Architecture

```
Plateforme (déclencheur planifié)
        │  HTTPS + jeton secret
        ▼
Point d'accès Workly  (python -m app.taches serveur)
        │  executer_tache()  → journal_taches
        ▼
PostgreSQL + services de l'application
```

La plateforme ne touche jamais la base : elle appelle le point d'accès, qui exécute la même
fonction que le planificateur interne (même journalisation, visible dans Administration →
Tâches).

## 2. Préparer le point d'accès (une fois)

1. Générer un jeton secret (32 caractères au minimum) :
   ```
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Le déclarer et démarrer le serveur.
   - Windows (PowerShell) :
     ```
     $env:WORKLY_TOKEN_TACHES = "<jeton>"
     python -m app.taches serveur
     ```
   - Linux / macOS :
     ```
     WORKLY_TOKEN_TACHES="<jeton>" python -m app.taches serveur
     ```
   Options : `--hote` (défaut `127.0.0.1`, écoute locale seulement) et `--port` (défaut `8765`).
   Le serveur refuse de démarrer sans jeton.
3. Rendre l'adresse joignable depuis la plateforme :
   - application sur un serveur : ouvrir le port derrière un proxy HTTPS (Caddy, Nginx) ;
   - application sur un poste : un tunnel, par exemple
     `cloudflared tunnel --url http://127.0.0.1:8765` (ou ngrok) ; l'adresse publique obtenue
     devient `URL_WORKLY` ci-dessous. Ne jamais exposer PostgreSQL.
4. Vérifier :
   ```
   curl <URL_WORKLY>/sante                                   → {"ok": true}
   curl -H "Authorization: Bearer <jeton>" <URL_WORKLY>/taches
   ```
5. **Suspendre le planificateur interne** (Administration → Tâches → « Suspendre le
   planificateur »), sinon chaque tâche s'exécute deux fois.

## 3. Variables et secrets à créer dans la plateforme

| Nom | Type | Valeur |
|---|---|---|
| `URL_WORKLY` | variable | adresse publique du point d'accès, sans `/` final |
| `TOKEN_WORKLY` | **secret** | le jeton de l'étape 2 |
| `DESTINATAIRE_ALERTE` | variable | adresse mail ou canal (Teams, Slack) qui reçoit les échecs |

## 4. Points d'accès

| Appel | Effet | Réponses |
|---|---|---|
| `GET /sante` | vivacité (sans jeton) | 200 `{"ok": true}` |
| `GET /taches` | liste des 10 tâches et du cycle nocturne | 200, 401 |
| `POST /taches/<nom>` | exécute une tâche | 200 succès, 500 échec, 404 inconnue, 401 jeton, 409 déjà en cours |
| `POST /cycle-nocturne` | enchaîne import → comparaison → KPI → alertes → prévisions → rapport, s'arrête à la première erreur | 200 ou 500 avec `etape_en_echec` |

Toutes les requêtes `POST` portent l'en-tête `Authorization: Bearer {{TOKEN_WORKLY}}`. Corps de
réponse : `{"tache", "statut": "succes"|"echec", "message" | "erreur", "duree_s"}`.

## 4 bis. Alertes par e-mail envoyées par Workly

Quand une tâche échoue (quel que soit son déclencheur : plateforme, planificateur interne ou
ligne de commande), Workly envoie un e-mail par SMTP. Réglages, par variables d'environnement
(sans elles, la notification est simplement désactivée) :

| Variable | Rôle |
|---|---|
| `WORKLY_SMTP_UTILISATEUR` | compte d'envoi (obligatoire), par exemple l'adresse Gmail |
| `WORKLY_SMTP_MOT_DE_PASSE` | **mot de passe d'application** Gmail (obligatoire) |
| `WORKLY_ALERTE_DESTINATAIRE` | adresse qui reçoit les alertes (défaut : le compte d'envoi) |
| `WORKLY_SMTP_HOTE`, `WORKLY_SMTP_PORT` | défaut `smtp.gmail.com`, `587` (STARTTLS) |

`POST /test-mail` (avec le jeton) envoie un e-mail de test. Ce mécanisme ne couvre pas le cas
où le serveur Workly lui-même est injoignable : la plateforme doit alors prévenir par son propre
canal.

## 5. Scénarios à construire

Fuseau horaire de tous les déclencheurs : celui du site (par exemple `Africa/Casablanca`).
Réglages communs de chaque nœud « Requête HTTP » : méthode `POST`, **délai d'attente de 30
minutes** (le réentraînement et les prévisions sont longs), en-tête d'authentification,
réponse lue en JSON, **aucune relance automatique** sur un code 500 (une tâche qui a échoué doit
être regardée, pas rejouée à l'aveugle) ; une relance unique est acceptable seulement sur une
erreur réseau (connexion refusée, délai dépassé avant réponse).

### Scénario 1 — « Workly · Cycle nocturne » (le plus important)

| # | Nœud | Réglage |
|---|---|---|
| 1 | **Déclencheur planifié (cron)** | `0 1 * * *` — tous les jours à 01:00 |
| 2 | **Requête HTTP** | `POST {{URL_WORKLY}}/cycle-nocturne` |
| 3 | **Condition** | `statut = "succes"` ? |
| 4 (non) | **Notification** (mail / Teams) | objet « Workly : échec à l'étape {{etape_en_echec}} » ; corps : réponse JSON complète |
| 5 (oui) | **Fin** (ou journal de la plateforme) | rien d'autre |

Gestion d'erreur : brancher le chemin « erreur » du nœud 2 (connexion impossible, délai) sur le
même nœud de notification 4, avec le texte « Point d'accès Workly injoignable ».

Variante détaillée (une vue par étape dans la plateforme) : remplacer le nœud 2 par six nœuds
HTTP en série, chacun suivi de la même condition ; en cas d'échec, tous renvoient vers la
notification. Ordre et décalage d'origine :

| Ordre | Appel | Heure d'origine |
|---|---|---|
| 1 | `POST /taches/import_historique` | 01:00 |
| 1 bis | `POST /taches/import_previsions_volume` | 01:10 |
| 2 | `POST /taches/comparaison_quotidienne` | 01:30 |
| 3 | `POST /taches/kpi_quotidiens` | 01:45 |
| 4 | `POST /taches/alertes_capacite` | 01:50 |
| 5 | `POST /taches/previsions_quotidiennes` | 02:00 |
| 6 | `POST /taches/rapport_quotidien` | 06:00 |

Le rapport quotidien est mieux placé dans un scénario à part à 06:00 (voir 2 ci-dessous) si le
cycle nocturne ne doit pas attendre jusqu'au matin ; dans ce cas, retirer `rapport_quotidien`
de la chaîne (appeler les cinq premières tâches une à une, et non `/cycle-nocturne`).

### Scénario 2 — « Workly · Rapport quotidien »

| # | Nœud | Réglage |
|---|---|---|
| 1 | Déclencheur cron | `0 6 * * *` |
| 2 | Requête HTTP | `POST {{URL_WORKLY}}/taches/rapport_quotidien` |
| 3 | Condition | `statut = "succes"` ? sinon notification d'échec |

### Scénario 3 — « Workly · Hebdomadaire »

Cron `0 3 * * 1` (lundi 03:00) ; appel `POST /taches/hebdomadaire` (réentraînement des modèles,
KPI et rapport de la semaine). Le réentraînement ne change jamais le modèle actif : l'activation
reste une décision humaine (écran Modèles). Si le jour ou l'heure sont modifiés dans
Modèles → Paramètres, modifier aussi ce cron.

### Scénario 4 — « Workly · Mensuel »

Cron `0 4 1 * *` ; appel `POST /taches/mensuel`.

### Scénario 5 — « Workly · Annuel »

Cron `0 5 1 1 *` ; appel `POST /taches/annuel`.

### Scénario 6 — « Workly · Surveillance » (recommandé)

| # | Nœud | Réglage |
|---|---|---|
| 1 | Déclencheur cron | `*/10 * * * *` |
| 2 | Requête HTTP | `GET {{URL_WORKLY}}/sante`, délai 10 s |
| 3 | Condition (chemin erreur ou code ≠ 200) | notification « Point d'accès Workly injoignable » ; limiter à un message par heure |

## 6. Dépôt de fichiers (historique et prévisions de volume)

La tâche `import_historique` lit le dossier `entrees/historique/`, et `import_previsions_volume`
le dossier `entrees/previsions/`, de la machine qui fait tourner Workly. Si les fichiers arrivent ailleurs (mail, partage, stockage en ligne), ajouter en tête du
scénario 1 un nœud « récupérer le fichier » (pièce jointe d'un mail, dossier surveillé,
stockage) puis le déposer dans ce dossier (nœud « écrire un fichier » ou copie réseau) avant
l'appel HTTP. Un fichier traité est déplacé dans `entrees/traites/`.

## 7. Contrôles après mise en service

1. Lancer chaque scénario à la main (« Exécuter maintenant ») et vérifier la réponse JSON.
2. Ouvrir Workly → Administration → Tâches → « Voir le journal » : une ligne par exécution,
   acteur « Planificateur de tâches ».
3. Casser volontairement le jeton : le scénario doit notifier et la tâche ne doit pas partir
   (réponse 401).
4. Vérifier le lendemain matin que les alertes, KPI et prévisions du jour sont présents.

## 8. Correspondance des noms de blocs

| Bloc générique | Noms usuels selon la plateforme |
|---|---|
| Déclencheur planifié (cron) | Schedule, Cron, Recurring job, Scheduled trigger, Timer |
| Requête HTTP | HTTP Request, Webhook call, API call, REST action |
| Condition | IF, Condition, Branch, Router, Filter |
| Gestion d'erreur | Error handler, On failure, Catch, Fallback route |
| Notification | Email, Slack, Teams, Notify |
| Variable / secret | Variables, Credentials, Secrets, Environment |
| Attente (non utilisée ici) | Wait, Delay, Sleep |
