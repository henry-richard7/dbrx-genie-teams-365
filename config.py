from os import environ
from microsoft_agents.hosting.core import AuthTypes, AgentAuthConfiguration


class DefaultConfig(AgentAuthConfiguration):
    """Configuration class for the Teams Agent.

    This class loads essential configuration settings from environment variables
    for authenticating and integrating the bot with Azure and Microsoft Teams.

    Attributes:
        AUTH_TYPE (str): The authentication type (e.g., client_secret).
        TENANT_ID (str): The Azure Active Directory tenant ID.
        CLIENT_ID (str): The Azure AD app registration client ID.
        CLIENT_SECRET (str): The Azure AD app registration client secret.
        CONNECTION_NAME (str): The OAuth connection name for the bot.
        AGENT_TYPE (str): The type of agent (defaults to 'TeamsHandler').
        PORT (int): The port number for the bot's local server.
    """

    def __init__(self) -> None:
        """Initializes the DefaultConfig with environment variable values."""
        self.AUTH_TYPE = AuthTypes.client_secret
        self.TENANT_ID = "" or environ.get(
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID"
        )
        self.CLIENT_ID = "" or environ.get(
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID"
        )
        self.CLIENT_SECRET = "" or environ.get(
            "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET"
        )
        self.CONNECTION_NAME = "" or environ.get(
            "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__GRAPH__SETTINGS__AZUREBOTOAUTHCONNECTIONNAME"
        )
        self.AGENT_TYPE = environ.get(
            "AGENT_TYPE", "TeamsHandler"
        )  # Default to TeamsHandler
        self.PORT = 3978
