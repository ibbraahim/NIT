"""Requêtes sur les utilisateurs, leurs sites et le journal des connexions."""

from __future__ import annotations

from datetime import datetime

from app.bd.depots.base import Depot

COLONNES = """u.id, u.identifiant, u.nom, u.prenom, u.email, u.role::text AS role, u.actif,
              u.tentatives_echouees, u.verrouille_jusqu_a, u.date_creation"""


class DepotUtilisateurs(Depot):
    """Accès à ``utilisateurs``, ``utilisateurs_sites`` et ``journal_connexions``."""

    def par_identifiant(self, identifiant: str, verrou: bool = False) -> dict | None:
        """Utilisateur (avec hash et sel) par identifiant, insensible à la casse."""
        requete = f"""SELECT {COLONNES}, u.hash_mot_de_passe, u.sel FROM utilisateurs u
                      WHERE lower(u.identifiant) = lower(%s)"""
        return self._un(requete + (" FOR UPDATE" if verrou else ""), (identifiant,))

    def par_id(self, utilisateur_id: int) -> dict | None:
        return self._un(f"SELECT {COLONNES} FROM utilisateurs u WHERE u.id = %s", (utilisateur_id,))

    def lister(self) -> list[dict]:
        return self._tous(f"""SELECT {COLONNES},
                       COALESCE(string_agg(s.nom, ', ' ORDER BY s.nom), '') AS sites_libelle,
                       COALESCE(array_agg(s.id) FILTER (WHERE s.id IS NOT NULL), '{{}}') AS sites
                FROM utilisateurs u
                LEFT JOIN utilisateurs_sites us ON us.utilisateur_id = u.id
                LEFT JOIN sites s ON s.id = us.site_id
                GROUP BY u.id ORDER BY u.nom, u.prenom""")

    def creer(
        self,
        identifiant: str,
        nom: str,
        prenom: str,
        email: str,
        hash_mdp: str,
        sel: str,
        role: str,
        actif: bool = True,
    ) -> int:
        ligne = self._un(
            """INSERT INTO utilisateurs
                   (identifiant, nom, prenom, email, hash_mot_de_passe, sel, role, actif)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (identifiant, nom, prenom, email, hash_mdp, sel, role, actif),
        )
        return ligne["id"]

    def modifier(self, utilisateur_id: int, nom: str, prenom: str, email: str, role: str) -> None:
        self._executer(
            "UPDATE utilisateurs SET nom = %s, prenom = %s, email = %s, role = %s WHERE id = %s",
            (nom, prenom, email, role, utilisateur_id),
        )

    def definir_actif(self, utilisateur_id: int, actif: bool) -> None:
        self._executer("UPDATE utilisateurs SET actif = %s WHERE id = %s", (actif, utilisateur_id))

    def definir_mot_de_passe(self, utilisateur_id: int, hash_mdp: str, sel: str) -> None:
        self._executer(
            """UPDATE utilisateurs SET hash_mot_de_passe = %s, sel = %s,
                      tentatives_echouees = 0, verrouille_jusqu_a = NULL WHERE id = %s""",
            (hash_mdp, sel, utilisateur_id),
        )

    def enregistrer_echec(
        self, utilisateur_id: int, tentatives: int, verrou: datetime | None
    ) -> None:
        self._executer(
            "UPDATE utilisateurs SET tentatives_echouees = %s, verrouille_jusqu_a = %s WHERE id = %s",
            (tentatives, verrou, utilisateur_id),
        )

    def reinitialiser_tentatives(self, utilisateur_id: int) -> None:
        self._executer(
            "UPDATE utilisateurs SET tentatives_echouees = 0, verrouille_jusqu_a = NULL WHERE id = %s",
            (utilisateur_id,),
        )

    def compter_administrateurs_actifs(self, sauf_id: int | None = None) -> int:
        ligne = self._un(
            """SELECT count(*) AS n FROM utilisateurs
               WHERE role = 'administrateur' AND actif AND id <> COALESCE(%s, -1)""",
            (sauf_id,),
        )
        return ligne["n"]

    def sites(self, utilisateur_id: int) -> list[int]:
        return [
            ligne["site_id"]
            for ligne in self._tous(
                "SELECT site_id FROM utilisateurs_sites WHERE utilisateur_id = %s ORDER BY site_id",
                (utilisateur_id,),
            )
        ]

    def definir_sites(self, utilisateur_id: int, sites: list[int]) -> None:
        self._executer(
            "DELETE FROM utilisateurs_sites WHERE utilisateur_id = %s", (utilisateur_id,)
        )
        for site_id in sorted(set(sites)):
            self._executer(
                "INSERT INTO utilisateurs_sites (utilisateur_id, site_id) VALUES (%s, %s)",
                (utilisateur_id, site_id),
            )

    def utilisateurs_du_site(self, site_id: int, role: str) -> list[dict]:
        """Utilisateurs actifs d'un rôle rattachés à un site."""
        return self._tous(
            f"""SELECT {COLONNES} FROM utilisateurs u
                JOIN utilisateurs_sites us ON us.utilisateur_id = u.id
                WHERE us.site_id = %s AND u.role = %s AND u.actif ORDER BY u.id""",
            (site_id, role),
        )

    def journaliser_connexion(
        self, utilisateur_id: int | None, identifiant_saisi: str, succes: bool, motif: str
    ) -> None:
        self._executer(
            """INSERT INTO journal_connexions (utilisateur_id, identifiant_saisi, succes, motif)
               VALUES (%s, %s, %s, %s)""",
            (utilisateur_id, identifiant_saisi[:200], succes, motif),
        )

    def dernieres_connexions(self, utilisateur_id: int, limite: int = 10) -> list[dict]:
        return self._tous(
            """SELECT date_connexion, succes, motif FROM journal_connexions
               WHERE utilisateur_id = %s ORDER BY date_connexion DESC LIMIT %s""",
            (utilisateur_id, limite),
        )
