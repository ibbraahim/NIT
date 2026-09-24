# Planification RH et équipements — CSCMP 2.3.3

Application de bureau (Python, Tkinter, PostgreSQL) qui traduit la prévision de volume en
ressources nécessaires — heures de main-d'œuvre, effectifs et équipements — par site, zone et
jour, pour le sous-processus **2.3.3 Ressources humaines et équipements** (métier 2 « Prévision
et planification », sous-métier 2.3 « Planification des capacités » du référentiel CSCMP).

> Document en cours de rédaction : il sera complété à chaque lot (voir `docs/plan.md`).

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

   `--reinitialiser` supprime puis recrée une base existante (confirmation demandée).

6. **Lancement :** `python -m app`

## Comptes de démonstration

Créés par `python -m app.bd.init_bd --demo` (fichier `ressources/demo/comptes_demo.csv`) :

| Identifiant | Rôle | Mot de passe |
|---|---|---|
| `admin` | Administrateur | `Admin2026!` |
| `planif` | Planificateur | `Planif2026!` |
| `resp` | Responsable d'exploitation | `Resp2026!` |
| `direction` | Direction | `Direction2026!` |

## Tests

```bash
python -m pytest                    # tests unitaires et d'intégration (base <nom_base>_test)
xvfb-run -a python -m pytest        # sous Linux sans affichage, pour les tests d'interface
```

La base de test `<nom_base>_test` est créée puis supprimée automatiquement.
