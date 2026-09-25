"""UC18 · Émettre une alerte — UC19 · Traiter une alerte."""

from __future__ import annotations

from app.bd.connexion import transaction
from app.bd.depots.alertes import DepotAlertes
from app.contexte import Contexte
from app.services.droits import a_le_droit


def compter_alertes_ouvertes(ctx: Contexte) -> int:
    """Nombre d'alertes non résolues visibles (compteur du menu « Alertes »)."""
    if not a_le_droit(ctx, "lecture_alertes"):
        return 0
    sites = None if ctx.voit_tous_les_sites else sorted(ctx.sites)
    with transaction() as cur:
        return DepotAlertes(cur).compter_ouvertes(sites)


def lister_alertes_ouvertes(
    ctx: Contexte, site_id: int, type_alerte: str | None = None
) -> list[dict]:
    """Alertes ouvertes ou en cours d'un site (bandeau de dérive de l'écran Modèles, UC21 ;
    futur écran Alertes, UC18/UC19)."""
    if not a_le_droit(ctx, "lecture_alertes") or not ctx.peut_voir_site(site_id):
        return []
    with transaction() as cur:
        return DepotAlertes(cur).ouvertes(site_id, type_alerte)
