-- =====================================================================
-- Schéma de la base « Planification RH et équipements — 2.3.3 »
-- Compatible PostgreSQL 13 et plus récent.
-- Convention : tous les pourcentages sont stockés en points (12,3 % → 12.3).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Types énumérés
-- ---------------------------------------------------------------------
CREATE TYPE role_utilisateur AS ENUM ('planificateur', 'responsable', 'direction', 'administrateur');
CREATE TYPE statut_equipement AS ENUM ('disponible', 'maintenance', 'hors_service');
CREATE TYPE categorie_cout AS ENUM ('interne', 'heures_sup', 'interim');
CREATE TYPE methode_prevision AS ENUM ('regression_lineaire', 'reseau_neurones');
CREATE TYPE cible_modele AS ENUM ('heures', 'equipements');
CREATE TYPE statut_version AS ENUM ('retenue', 'non_retenue');
CREATE TYPE statut_plan AS ENUM ('brouillon', 'soumis', 'valide', 'rejete');
CREATE TYPE periodicite AS ENUM ('jour', 'semaine', 'mois', 'annee');
CREATE TYPE sens_kpi AS ENUM ('hausse', 'baisse', 'plage', 'information');
CREATE TYPE famille_kpi AS ENUM ('precision', 'rh', 'equipements', 'couts', 'service');
CREATE TYPE statut_kpi AS ENUM ('vert', 'orange', 'rouge', 'gris');
CREATE TYPE type_alerte AS ENUM ('seuil_kpi', 'sous_effectif', 'sureffectif', 'penurie_equipement', 'derive_modele');
CREATE TYPE niveau_alerte AS ENUM ('orange', 'rouge');
CREATE TYPE statut_alerte AS ENUM ('ouverte', 'en_cours', 'resolue');
CREATE TYPE format_rapport AS ENUM ('pdf', 'excel', 'pdf_excel');
CREATE TYPE statut_tache AS ENUM ('en_cours', 'succes', 'echec');

-- ---------------------------------------------------------------------
-- P1 · Accès et référentiels
-- ---------------------------------------------------------------------
CREATE TABLE sites (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom             VARCHAR(120) NOT NULL,
    adresse         TEXT NOT NULL DEFAULT '',
    actif           BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT sites_nom_unique UNIQUE (nom),
    CONSTRAINT sites_nom_non_vide CHECK (length(trim(nom)) > 0)
);

CREATE TABLE zones (
    id                          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id                     INTEGER NOT NULL REFERENCES sites (id),
    nom                         VARCHAR(120) NOT NULL,
    type_equipement_principal   VARCHAR(60) NOT NULL,
    duree_poste_heures          NUMERIC(4, 2) NOT NULL DEFAULT 7.5,
    actif                       BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT zones_nom_unique UNIQUE (site_id, nom),
    CONSTRAINT zones_duree_poste CHECK (duree_poste_heures > 0 AND duree_poste_heures <= 24),
    CONSTRAINT zones_nom_non_vide CHECK (length(trim(nom)) > 0)
);
CREATE INDEX zones_site_idx ON zones (site_id);

CREATE TABLE utilisateurs (
    id                      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identifiant             VARCHAR(50) NOT NULL,
    nom                     VARCHAR(120) NOT NULL,
    prenom                  VARCHAR(120) NOT NULL DEFAULT '',
    email                   VARCHAR(200) NOT NULL DEFAULT '',
    hash_mot_de_passe       VARCHAR(128) NOT NULL,
    sel                     VARCHAR(64) NOT NULL,
    role                    role_utilisateur NOT NULL,
    actif                   BOOLEAN NOT NULL DEFAULT TRUE,
    tentatives_echouees     INTEGER NOT NULL DEFAULT 0,
    verrouille_jusqu_a      TIMESTAMPTZ,
    date_creation           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT utilisateurs_identifiant_unique UNIQUE (identifiant),
    CONSTRAINT utilisateurs_tentatives CHECK (tentatives_echouees >= 0)
);

CREATE TABLE utilisateurs_sites (
    utilisateur_id  INTEGER NOT NULL REFERENCES utilisateurs (id) ON DELETE CASCADE,
    site_id         INTEGER NOT NULL REFERENCES sites (id),
    PRIMARY KEY (utilisateur_id, site_id)
);
CREATE INDEX utilisateurs_sites_site_idx ON utilisateurs_sites (site_id);

CREATE TABLE journal_connexions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    utilisateur_id      INTEGER REFERENCES utilisateurs (id),
    identifiant_saisi   VARCHAR(200) NOT NULL,
    date_connexion      TIMESTAMPTZ NOT NULL DEFAULT now(),
    succes              BOOLEAN NOT NULL,
    motif               VARCHAR(60) NOT NULL DEFAULT ''
);
CREATE INDEX journal_connexions_date_idx ON journal_connexions (date_connexion);
CREATE INDEX journal_connexions_utilisateur_idx ON journal_connexions (utilisateur_id);

CREATE TABLE equipements (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     INTEGER NOT NULL REFERENCES sites (id),
    zone_id     INTEGER NOT NULL REFERENCES zones (id),
    type        VARCHAR(60) NOT NULL,
    code        VARCHAR(40) NOT NULL,
    statut      statut_equipement NOT NULL DEFAULT 'disponible',
    actif       BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT equipements_code_unique UNIQUE (site_id, code)
);
CREATE INDEX equipements_zone_idx ON equipements (site_id, zone_id);

CREATE TABLE indisponibilites_equipements (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    equipement_id   INTEGER NOT NULL REFERENCES equipements (id),
    date_debut      DATE NOT NULL,
    date_fin        DATE NOT NULL,
    motif           TEXT NOT NULL DEFAULT '',
    CONSTRAINT indisponibilites_dates CHECK (date_fin >= date_debut)
);
CREATE INDEX indisponibilites_dates_idx ON indisponibilites_equipements (equipement_id, date_debut, date_fin);

CREATE TABLE capacites_personnel (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id             INTEGER NOT NULL REFERENCES sites (id),
    zone_id             INTEGER NOT NULL REFERENCES zones (id),
    date_jour           DATE NOT NULL,
    effectif_planifie   INTEGER NOT NULL,
    absences_prevues    INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT capacites_unique UNIQUE (site_id, zone_id, date_jour),
    CONSTRAINT capacites_positives CHECK (effectif_planifie >= 0 AND absences_prevues >= 0),
    CONSTRAINT capacites_absences CHECK (absences_prevues <= effectif_planifie)
);

CREATE TABLE couts_horaires (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    categorie   categorie_cout NOT NULL,
    taux        NUMERIC(10, 2) NOT NULL,
    devise      VARCHAR(3) NOT NULL DEFAULT 'MAD',
    date_debut  DATE NOT NULL,
    CONSTRAINT couts_unique UNIQUE (categorie, date_debut),
    CONSTRAINT couts_taux_positif CHECK (taux >= 0)
);

-- ---------------------------------------------------------------------
-- P2 · Données
-- ---------------------------------------------------------------------
CREATE TABLE historique_activite (
    id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id                         INTEGER NOT NULL REFERENCES sites (id),
    zone_id                         INTEGER NOT NULL REFERENCES zones (id),
    date_jour                       DATE NOT NULL,
    volume_traite                   NUMERIC(12, 2) NOT NULL,
    effectif_present                INTEGER NOT NULL,
    heures_travaillees              NUMERIC(10, 2) NOT NULL,
    heures_sup                      NUMERIC(10, 2) NOT NULL DEFAULT 0,
    heures_interim                  NUMERIC(10, 2) NOT NULL DEFAULT 0,
    heures_absence                  NUMERIC(10, 2) NOT NULL DEFAULT 0,
    heures_inactives                NUMERIC(10, 2) NOT NULL DEFAULT 0,
    equipements_mobilises           INTEGER NOT NULL DEFAULT 0,
    heures_usage_equipement         NUMERIC(10, 2) NOT NULL DEFAULT 0,
    heures_disponibles_equipement   NUMERIC(10, 2) NOT NULL DEFAULT 0,
    heures_panne_equipement         NUMERIC(10, 2) NOT NULL DEFAULT 0,
    cout_rh                         NUMERIC(14, 2) NOT NULL DEFAULT 0,
    commandes_a_temps               INTEGER NOT NULL DEFAULT 0,
    commandes_totales               INTEGER NOT NULL DEFAULT 0,
    indicateur_pic                  BOOLEAN NOT NULL DEFAULT FALSE,
    source                          VARCHAR(20) NOT NULL DEFAULT 'saisie',
    date_maj                        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT historique_unique UNIQUE (site_id, zone_id, date_jour),
    CONSTRAINT historique_positifs CHECK (
        volume_traite >= 0 AND effectif_present >= 0 AND heures_travaillees >= 0
        AND heures_sup >= 0 AND heures_interim >= 0 AND heures_absence >= 0
        AND heures_inactives >= 0 AND equipements_mobilises >= 0
        AND heures_usage_equipement >= 0 AND heures_disponibles_equipement >= 0
        AND heures_panne_equipement >= 0 AND cout_rh >= 0
        AND commandes_a_temps >= 0 AND commandes_totales >= 0
    ),
    CONSTRAINT historique_commandes CHECK (commandes_a_temps <= commandes_totales),
    CONSTRAINT historique_usage CHECK (heures_usage_equipement <= heures_disponibles_equipement),
    CONSTRAINT historique_inactives CHECK (heures_inactives <= heures_travaillees)
);
CREATE INDEX historique_date_idx ON historique_activite (date_jour);

CREATE TABLE previsions_volume (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id         INTEGER NOT NULL REFERENCES sites (id),
    zone_id         INTEGER NOT NULL REFERENCES zones (id),
    date_jour       DATE NOT NULL,
    volume_prevu    NUMERIC(12, 2) NOT NULL,
    indicateur_pic  BOOLEAN NOT NULL DEFAULT FALSE,
    source          VARCHAR(20) NOT NULL DEFAULT 'saisie',
    date_maj        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT previsions_volume_unique UNIQUE (site_id, zone_id, date_jour),
    CONSTRAINT previsions_volume_positif CHECK (volume_prevu >= 0)
);
CREATE INDEX previsions_volume_date_idx ON previsions_volume (date_jour);

-- ---------------------------------------------------------------------
-- P3 · Modèles de prévision
-- ---------------------------------------------------------------------
CREATE TABLE parametres_modele (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    configuration       JSONB NOT NULL,
    date_enregistrement TIMESTAMPTZ NOT NULL DEFAULT now(),
    auteur_id           INTEGER REFERENCES utilisateurs (id)
);

CREATE TABLE modeles_versions (
    id                      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    methode                 methode_prevision NOT NULL,
    site_id                 INTEGER NOT NULL REFERENCES sites (id),
    zone_id                 INTEGER NOT NULL REFERENCES zones (id),
    cible                   cible_modele NOT NULL,
    chemin_fichier          TEXT NOT NULL,
    metriques               JSONB NOT NULL DEFAULT '{}'::jsonb,
    coefficients            JSONB NOT NULL DEFAULT '{}'::jsonb,
    parametres              JSONB NOT NULL DEFAULT '{}'::jsonb,
    nb_lignes_apprentissage INTEGER NOT NULL DEFAULT 0,
    nb_lignes_test          INTEGER NOT NULL DEFAULT 0,
    date_debut_donnees      DATE,
    date_fin_donnees        DATE,
    statut                  statut_version NOT NULL DEFAULT 'retenue',
    actif                   BOOLEAN NOT NULL DEFAULT FALSE,
    retenue_pour_plan       BOOLEAN NOT NULL DEFAULT FALSE,
    date_entrainement       TIMESTAMPTZ NOT NULL DEFAULT now(),
    entraine_par            INTEGER REFERENCES utilisateurs (id),
    CONSTRAINT modeles_versions_retenue CHECK (NOT retenue_pour_plan OR actif),
    CONSTRAINT modeles_versions_actif_retenu CHECK (NOT actif OR statut = 'retenue')
);
-- Une seule version active par site, zone, méthode et cible.
CREATE UNIQUE INDEX modeles_versions_actif_unique
    ON modeles_versions (site_id, zone_id, methode, cible) WHERE actif;
-- Une seule méthode retenue pour le plan par site, zone et cible.
CREATE UNIQUE INDEX modeles_versions_plan_unique
    ON modeles_versions (site_id, zone_id, cible) WHERE retenue_pour_plan;
CREATE INDEX modeles_versions_site_zone_idx ON modeles_versions (site_id, zone_id, date_entrainement);

-- ---------------------------------------------------------------------
-- P4 · Prévision et planification
-- ---------------------------------------------------------------------
CREATE TABLE previsions_ressources (
    id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id                         INTEGER NOT NULL REFERENCES sites (id),
    zone_id                         INTEGER NOT NULL REFERENCES zones (id),
    date_jour                       DATE NOT NULL,
    modele_version_id               INTEGER NOT NULL REFERENCES modeles_versions (id),
    modele_version_equipements_id   INTEGER REFERENCES modeles_versions (id),
    methode                         methode_prevision NOT NULL,
    volume_prevu                    NUMERIC(12, 2) NOT NULL,
    heures                          NUMERIC(10, 2) NOT NULL,
    effectif                        INTEGER NOT NULL,
    equipements                     INTEGER NOT NULL,
    ic_bas                          NUMERIC(10, 2) NOT NULL,
    ic_haut                         NUMERIC(10, 2) NOT NULL,
    ic_bas_equipements              NUMERIC(10, 2),
    ic_haut_equipements             NUMERIC(10, 2),
    date_generation                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT previsions_ressources_unique UNIQUE (site_id, zone_id, date_jour, methode, date_generation),
    CONSTRAINT previsions_ressources_positifs CHECK (
        volume_prevu >= 0 AND heures >= 0 AND effectif >= 0 AND equipements >= 0 AND ic_bas >= 0
    ),
    CONSTRAINT previsions_ressources_ic CHECK (ic_bas <= ic_haut)
);
CREATE INDEX previsions_ressources_recherche_idx
    ON previsions_ressources (site_id, zone_id, date_jour, methode, date_generation DESC);

CREATE TABLE comparaisons_realise (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prevision_id        BIGINT NOT NULL REFERENCES previsions_ressources (id) ON DELETE CASCADE,
    heures_reelles      NUMERIC(10, 2),
    equipements_reels   INTEGER,
    ecart_absolu        NUMERIC(10, 2),
    ecart_relatif       NUMERIC(10, 2),
    ecart_equipements   NUMERIC(10, 2),
    dans_ic             BOOLEAN,
    comparable          BOOLEAN NOT NULL,
    date_calcul         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT comparaisons_unique UNIQUE (prevision_id)
);

CREATE TABLE plans_charge (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id             INTEGER NOT NULL REFERENCES sites (id),
    semaine             DATE NOT NULL,
    statut              statut_plan NOT NULL DEFAULT 'brouillon',
    commentaire         TEXT NOT NULL DEFAULT '',
    methode             methode_prevision,
    cree_par            INTEGER REFERENCES utilisateurs (id),
    soumis_par          INTEGER REFERENCES utilisateurs (id),
    valide_par          INTEGER REFERENCES utilisateurs (id),
    date_creation       TIMESTAMPTZ NOT NULL DEFAULT now(),
    date_maj            TIMESTAMPTZ NOT NULL DEFAULT now(),
    date_soumission     TIMESTAMPTZ,
    date_validation     TIMESTAMPTZ,
    CONSTRAINT plans_charge_unique UNIQUE (site_id, semaine),
    CONSTRAINT plans_charge_lundi CHECK (EXTRACT(ISODOW FROM semaine) = 1),
    CONSTRAINT plans_charge_rejet_commente CHECK (statut <> 'rejete' OR length(trim(commentaire)) > 0)
);

CREATE TABLE plans_charge_lignes (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id                 INTEGER NOT NULL REFERENCES plans_charge (id) ON DELETE CASCADE,
    zone_id                 INTEGER NOT NULL REFERENCES zones (id),
    date_jour               DATE NOT NULL,
    besoin_heures           NUMERIC(10, 2) NOT NULL DEFAULT 0,
    besoin_effectif         INTEGER NOT NULL DEFAULT 0,
    besoin_equipements      INTEGER NOT NULL DEFAULT 0,
    effectif_planifie       INTEGER NOT NULL DEFAULT 0,
    interim_planifie        INTEGER NOT NULL DEFAULT 0,
    equipements_planifies   INTEGER NOT NULL DEFAULT 0,
    capacite_effectif       INTEGER NOT NULL DEFAULT 0,
    capacite_equipements    INTEGER NOT NULL DEFAULT 0,
    commentaire             TEXT NOT NULL DEFAULT '',
    CONSTRAINT plans_lignes_unique UNIQUE (plan_id, zone_id, date_jour),
    CONSTRAINT plans_lignes_positifs CHECK (
        besoin_heures >= 0 AND besoin_effectif >= 0 AND besoin_equipements >= 0
        AND effectif_planifie >= 0 AND interim_planifie >= 0 AND equipements_planifies >= 0
        AND capacite_effectif >= 0 AND capacite_equipements >= 0
    )
);
CREATE INDEX plans_lignes_date_idx ON plans_charge_lignes (zone_id, date_jour);

CREATE TABLE scenarios (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id         INTEGER NOT NULL REFERENCES plans_charge (id) ON DELETE CASCADE,
    hypotheses      JSONB NOT NULL,
    resultats       JSONB NOT NULL,
    applique        BOOLEAN NOT NULL DEFAULT FALSE,
    auteur_id       INTEGER REFERENCES utilisateurs (id),
    date_creation   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- P5 · Cibles, KPI et alertes
-- ---------------------------------------------------------------------
CREATE TABLE kpi_definitions (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR(40) NOT NULL,
    libelle     VARCHAR(160) NOT NULL,
    famille     famille_kpi NOT NULL,
    formule     TEXT NOT NULL,
    unite       VARCHAR(30) NOT NULL DEFAULT '',
    sens        sens_kpi NOT NULL,
    par_methode BOOLEAN NOT NULL DEFAULT FALSE,
    ordre       INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT kpi_definitions_code_unique UNIQUE (code)
);

CREATE TABLE objectifs_kpi (
    id                      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kpi_id                  INTEGER NOT NULL REFERENCES kpi_definitions (id),
    site_id                 INTEGER REFERENCES sites (id),
    zone_id                 INTEGER REFERENCES zones (id),
    periodicite             periodicite NOT NULL,
    sens                    sens_kpi NOT NULL,
    valeur_cible            NUMERIC(14, 4),
    seuil_orange            NUMERIC(14, 4),
    seuil_rouge             NUMERIC(14, 4),
    valeur_min              NUMERIC(14, 4),
    valeur_max              NUMERIC(14, 4),
    -- Seuils exprimés en % de la cible (Productivité, Coût par unité) ;
    -- une cible vide est alors calculée sur les 90 premiers jours d'historique.
    seuils_relatifs         BOOLEAN NOT NULL DEFAULT FALSE,
    date_debut_validite     DATE NOT NULL DEFAULT CURRENT_DATE,
    date_fin_validite       DATE,
    CONSTRAINT objectifs_zone_site CHECK (zone_id IS NULL OR site_id IS NOT NULL),
    CONSTRAINT objectifs_validite CHECK (date_fin_validite IS NULL OR date_fin_validite >= date_debut_validite),
    CONSTRAINT objectifs_plage CHECK (
        sens <> 'plage' OR (valeur_min IS NOT NULL AND valeur_max IS NOT NULL AND valeur_min <= valeur_max
                            AND seuil_orange IS NOT NULL AND seuil_orange >= 0)
    ),
    CONSTRAINT objectifs_seuils CHECK (
        sens NOT IN ('hausse', 'baisse') OR (seuil_orange IS NOT NULL AND seuil_rouge IS NOT NULL)
    )
);
CREATE INDEX objectifs_kpi_recherche_idx ON objectifs_kpi (kpi_id, periodicite, site_id, zone_id);

CREATE TABLE kpi_valeurs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kpi_id              INTEGER NOT NULL REFERENCES kpi_definitions (id),
    site_id             INTEGER NOT NULL REFERENCES sites (id),
    zone_id             INTEGER REFERENCES zones (id),
    periodicite         periodicite NOT NULL,
    date_debut_periode  DATE NOT NULL,
    methode             methode_prevision,
    valeur              NUMERIC(14, 4),
    cible               NUMERIC(14, 4),
    statut              statut_kpi NOT NULL DEFAULT 'gris',
    date_calcul         TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Unicité (KPI, site, zone, périodicité, début de période, méthode), zone et méthode
-- facultatives : NULLS NOT DISTINCT traite les NULL comme égaux entre eux, ce qui rend
-- l'index directement utilisable par ON CONFLICT sans caster l'énuméré ni recourir à des
-- valeurs neutres (nécessaire à partir de PostgreSQL 15).
CREATE UNIQUE INDEX kpi_valeurs_unique ON kpi_valeurs (
    kpi_id, site_id, zone_id, periodicite, date_debut_periode, methode
) NULLS NOT DISTINCT;
CREATE INDEX kpi_valeurs_recherche_idx ON kpi_valeurs (site_id, zone_id, periodicite, date_debut_periode);

CREATE TABLE alertes (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type                    type_alerte NOT NULL,
    niveau                  niveau_alerte NOT NULL,
    kpi_id                  INTEGER REFERENCES kpi_definitions (id),
    site_id                 INTEGER NOT NULL REFERENCES sites (id),
    zone_id                 INTEGER REFERENCES zones (id),
    date_concernee          DATE NOT NULL,
    cle_deduplication       VARCHAR(200) NOT NULL,
    message                 TEXT NOT NULL,
    statut                  statut_alerte NOT NULL DEFAULT 'ouverte',
    assigne_a               INTEGER REFERENCES utilisateurs (id),
    assigne_responsable     INTEGER REFERENCES utilisateurs (id),
    pris_en_charge_par      INTEGER REFERENCES utilisateurs (id),
    resolu_par              INTEGER REFERENCES utilisateurs (id),
    action_menee            TEXT NOT NULL DEFAULT '',
    nb_occurrences          INTEGER NOT NULL DEFAULT 1,
    date_creation           TIMESTAMPTZ NOT NULL DEFAULT now(),
    date_maj                TIMESTAMPTZ NOT NULL DEFAULT now(),
    date_prise_en_charge    TIMESTAMPTZ,
    date_resolution         TIMESTAMPTZ,
    CONSTRAINT alertes_action_obligatoire CHECK (statut <> 'resolue' OR length(trim(action_menee)) > 0),
    CONSTRAINT alertes_occurrences CHECK (nb_occurrences >= 1)
);
-- Une alerte identique déjà ouverte (ou en cours) est mise à jour, pas dupliquée.
CREATE UNIQUE INDEX alertes_deduplication_idx ON alertes (cle_deduplication) WHERE statut <> 'resolue';
CREATE INDEX alertes_recherche_idx ON alertes (site_id, statut, date_concernee);

-- ---------------------------------------------------------------------
-- P7 · Rapports, tâches et paramètres
-- ---------------------------------------------------------------------
CREATE TABLE rapports (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    periodicite         periodicite NOT NULL,
    date_debut          DATE NOT NULL,
    date_fin            DATE NOT NULL,
    site_id             INTEGER NOT NULL REFERENCES sites (id),
    format              format_rapport,
    chemin_pdf          TEXT,
    chemin_excel        TEXT,
    contenu             JSONB NOT NULL DEFAULT '{}'::jsonb,
    genere_par          INTEGER REFERENCES utilisateurs (id),
    genere_par_systeme  BOOLEAN NOT NULL DEFAULT FALSE,
    date_generation     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT rapports_dates CHECK (date_fin >= date_debut),
    CONSTRAINT rapports_auteur CHECK (genere_par IS NOT NULL OR genere_par_systeme)
);
CREATE INDEX rapports_recherche_idx ON rapports (site_id, periodicite, date_debut);

CREATE TABLE journal_taches (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tache       VARCHAR(60) NOT NULL,
    debut       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fin         TIMESTAMPTZ,
    statut      statut_tache NOT NULL DEFAULT 'en_cours',
    message     TEXT NOT NULL DEFAULT '',
    CONSTRAINT journal_taches_dates CHECK (fin IS NULL OR fin >= debut)
);
CREATE INDEX journal_taches_idx ON journal_taches (tache, debut DESC);

CREATE TABLE parametres_application (
    cle     VARCHAR(80) PRIMARY KEY,
    valeur  TEXT NOT NULL
);
