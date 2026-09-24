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
