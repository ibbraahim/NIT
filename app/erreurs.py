"""Exceptions métier de l'application.

Tous les messages portés par ces exceptions sont en français et destinés à
être affichés tels quels à l'utilisateur. La trace technique, elle, ne va
que dans le fichier journal.
"""


class ErreurApplication(Exception):
    """Erreur générique dont le message est affichable à l'utilisateur."""

    message_defaut = "Une erreur inattendue s'est produite. Consultez le journal de l'application."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message_defaut
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ErreurConfiguration(ErreurApplication):
    """Fichier config.ini absent ou incomplet."""

    message_defaut = "Le fichier config.ini est absent ou incomplet."


class ErreurBaseDonnees(ErreurApplication):
    """Problème de connexion ou d'exécution SQL."""

    message_defaut = (
        "Impossible de se connecter à la base de données. Vérifiez le fichier config.ini."
    )


class AccesRefuse(ErreurApplication):
    """L'utilisateur n'a pas le droit d'exécuter ce cas d'utilisation."""

    message_defaut = "Vous n'avez pas les droits nécessaires pour effectuer cette action."


class ErreurAuthentification(ErreurApplication):
    """Échec d'authentification (message volontairement identique quelle que soit la cause)."""

    message_defaut = "Identifiant ou mot de passe incorrect."


class DonneesInvalides(ErreurApplication):
    """Saisie ou données refusées par une règle métier.

    ``erreurs`` associe éventuellement un nom de champ à son message, pour
    permettre à l'interface d'encadrer le champ fautif.
    """

    message_defaut = "Les données saisies sont invalides."

    def __init__(self, message: str | None = None, erreurs: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.erreurs = erreurs or {}


class OperationImpossible(ErreurApplication):
    """Action refusée dans l'état courant (ex. désactiver le dernier administrateur)."""

    message_defaut = "Cette action est impossible dans l'état actuel."


class OperationAnnulee(ErreurApplication):
    """Traitement long interrompu par l'utilisateur."""

    message_defaut = "Traitement annulé par l'utilisateur."


class ConflitMiseAJour(ErreurApplication):
    """Un autre utilisateur a modifié la même ressource entre la lecture et l'enregistrement."""

    message_defaut = (
        "Ce plan a été modifié par quelqu'un d'autre entre-temps. "
        "La semaine a été rechargée ; vérifiez vos saisies avant de les enregistrer à nouveau."
    )
