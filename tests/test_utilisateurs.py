"""UC02 · Gérer les utilisateurs et les rôles (dépôts et services sur base de test)."""

from __future__ import annotations

import pytest

from app.erreurs import AccesRefuse, DonneesInvalides, OperationImpossible
from app.services import admin

pytestmark = pytest.mark.integration


def _site(ctx):
    return admin.enregistrer_site(ctx, "Site test", "Adresse")


def test_creer_lister_modifier(ctx_admin):
    site_id = _site(ctx_admin)
    uid = admin.creer_utilisateur(
        ctx_admin,
        "j.dupont",
        "Dupont",
        "Jean",
        "jean@example.com",
        "planificateur",
        "Motdepasse1",
        [site_id],
    )
    utilisateurs = admin.lister_utilisateurs(ctx_admin)
    cree = next(u for u in utilisateurs if u["id"] == uid)
    assert cree["identifiant"] == "j.dupont"
    assert cree["role"] == "planificateur"
    assert cree["sites"] == [site_id]
    assert cree["actif"] is True

    admin.modifier_utilisateur(
        ctx_admin, uid, "Dupont", "Jean-Marc", "jm@example.com", "responsable", [site_id]
    )
    modifie = next(u for u in admin.lister_utilisateurs(ctx_admin) if u["id"] == uid)
    assert modifie["prenom"] == "Jean-Marc"
    assert modifie["email"] == "jm@example.com"
    assert modifie["role"] == "responsable"


def test_creer_refuse_hors_administrateur(ctx_admin):
    site_id = _site(ctx_admin)
    from app.bd.connexion import transaction
    from app.bd.depots.utilisateurs import DepotUtilisateurs
    from app.services import auth

    with transaction() as cur:
        h, s = auth.hacher_mot_de_passe("Planif2026!")
        depot = DepotUtilisateurs(cur)
        uid = depot.creer("planif", "P", "P", "", h, s, "planificateur")
        depot.definir_sites(uid, [site_id])
    ctx_planif = auth.authentifier("planif", "Planif2026!")

    with pytest.raises(AccesRefuse):
        admin.creer_utilisateur(ctx_planif, "x", "X", "X", "", "planificateur", "Motdepasse1", [])


def test_creer_identifiant_deja_utilise(ctx_admin):
    admin.creer_utilisateur(
        ctx_admin, "j.dupont", "Dupont", "Jean", "", "planificateur", "Motdepasse1", []
    )
    with pytest.raises(DonneesInvalides) as erreur:
        admin.creer_utilisateur(
            ctx_admin, "J.DUPONT", "Autre", "Personne", "", "responsable", "Motdepasse2", []
        )
    assert "identifiant" in erreur.value.erreurs


def test_creer_champs_invalides_signales(ctx_admin):
    with pytest.raises(DonneesInvalides) as erreur:
        admin.creer_utilisateur(ctx_admin, "ab", "", "", "pas-un-email", "inconnu", "court", [])
    for champ in ("identifiant", "nom", "prenom", "email", "role", "mot_de_passe"):
        assert champ in erreur.value.erreurs


def test_administrateur_sans_site_voit_tout(ctx_admin):
    site_id = _site(ctx_admin)
    uid = admin.creer_utilisateur(
        ctx_admin, "a.deux", "Deux", "Admin", "", "administrateur", "Motdepasse1", [site_id]
    )
    cree = next(u for u in admin.lister_utilisateurs(ctx_admin) if u["id"] == uid)
    assert cree["sites"] == []  # les sites ne s'appliquent pas à un administrateur


def test_desactiver_reactiver(ctx_admin):
    uid = admin.creer_utilisateur(
        ctx_admin, "j.dupont", "Dupont", "Jean", "", "planificateur", "Motdepasse1", []
    )
    admin.activer_utilisateur(ctx_admin, uid, False)
    assert admin.lister_utilisateurs(ctx_admin)[-1]["actif"] is False
    admin.activer_utilisateur(ctx_admin, uid, True)
    utilisateurs = admin.lister_utilisateurs(ctx_admin)
    assert next(u for u in utilisateurs if u["id"] == uid)["actif"] is True


def test_desactiver_son_propre_compte_refuse(ctx_admin):
    with pytest.raises(OperationImpossible):
        admin.activer_utilisateur(ctx_admin, ctx_admin.utilisateur_id, False)


def test_changer_le_role_du_dernier_administrateur_refuse(ctx_admin):
    """``modifier_utilisateur`` n'a pas la restriction « pas son propre compte » de
    ``activer_utilisateur`` : c'est le seul moyen de tester la règle du dernier
    administrateur sans la confondre avec celle-là."""
    with pytest.raises(OperationImpossible):
        admin.modifier_utilisateur(
            ctx_admin, ctx_admin.utilisateur_id, "Admin", "Compte", "", "planificateur", []
        )

    # Avec un second administrateur actif, changer le rôle du premier est permis.
    uid2 = admin.creer_utilisateur(
        ctx_admin, "a.deux", "Deux", "Admin", "", "administrateur", "Motdepasse1", []
    )
    admin.modifier_utilisateur(
        ctx_admin, ctx_admin.utilisateur_id, "Admin", "Compte", "", "planificateur", []
    )
    utilisateurs = admin.lister_utilisateurs(ctx_admin)
    assert next(u for u in utilisateurs if u["id"] == ctx_admin.utilisateur_id)["role"] == (
        "planificateur"
    )
    assert next(u for u in utilisateurs if u["id"] == uid2)["role"] == "administrateur"


def test_reinitialiser_mot_de_passe(ctx_admin):
    from app.erreurs import ErreurAuthentification
    from app.services import auth

    uid = admin.creer_utilisateur(
        ctx_admin, "j.dupont", "Dupont", "Jean", "", "planificateur", "Motdepasse1", []
    )
    admin.reinitialiser_mot_de_passe(ctx_admin, uid, "Nouveaumdp2")
    ctx = auth.authentifier("j.dupont", "Nouveaumdp2")
    assert ctx.identifiant == "j.dupont"
    with pytest.raises(ErreurAuthentification):
        auth.authentifier("j.dupont", "Motdepasse1")


def test_reinitialiser_mot_de_passe_trop_court_refuse(ctx_admin):
    uid = admin.creer_utilisateur(
        ctx_admin, "j.dupont", "Dupont", "Jean", "", "planificateur", "Motdepasse1", []
    )
    with pytest.raises(DonneesInvalides):
        admin.reinitialiser_mot_de_passe(ctx_admin, uid, "court")


def test_utilisateur_introuvable(ctx_admin):
    with pytest.raises(OperationImpossible):
        admin.modifier_utilisateur(ctx_admin, 999999, "X", "X", "", "planificateur", [])
    with pytest.raises(OperationImpossible):
        admin.activer_utilisateur(ctx_admin, 999999, False)
    with pytest.raises(OperationImpossible):
        admin.reinitialiser_mot_de_passe(ctx_admin, 999999, "Motdepasse1")
