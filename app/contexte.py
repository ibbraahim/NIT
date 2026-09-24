"""Contexte d'exécution transmis à chaque fonction de service."""

from __future__ import annotations

from dataclasses import dataclass, field

ROLES = ("planificateur", "responsable", "direction", "administrateur")
ROLE_SYSTEME = "systeme"

LIBELLES_ROLES = {
    "planificateur": "Planificateur",
    "responsable": "Responsable d'exploitation",
    "direction": "Direction",
    "administrateur": "Administrateur",
    ROLE_SYSTEME: "Planificateur de tâches",
}


@dataclass(frozen=True)
class Contexte:
    """Utilisateur au nom duquel un cas d'utilisation est exécuté."""

    utilisateur_id: int | None
    identifiant: str
    role: str
    nom_complet: str = ""
    sites: frozenset[int] = field(default_factory=frozenset)

    @property
    def est_systeme(self) -> bool:
        """Vrai pour les tâches automatiques (acteur « Planificateur de tâches »)."""
        return self.role == ROLE_SYSTEME

    @property
    def voit_tous_les_sites(self) -> bool:
        """L'administrateur et le système voient tous les sites."""
        return self.role in ("administrateur", ROLE_SYSTEME)

    def peut_voir_site(self, site_id: int | None) -> bool:
        """Vrai si l'utilisateur est rattaché au site (ou voit tout)."""
        return site_id is None or self.voit_tous_les_sites or site_id in self.sites

    @property
    def libelle_role(self) -> str:
        """Libellé français du rôle."""
        return LIBELLES_ROLES.get(self.role, self.role)


CONTEXTE_SYSTEME = Contexte(
    utilisateur_id=None, identifiant="systeme", role=ROLE_SYSTEME, nom_complet="Système"
)
