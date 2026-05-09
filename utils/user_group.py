import aiohttp
from dotenv import load_dotenv
from os import environ

load_dotenv()


class UserGroup:
    """Utility class for retrieving user security groups from Microsoft Entra ID (Azure AD).

    This class handles authentication with the Microsoft Graph API using
    client credentials and fetches all transitive group memberships for a user.
    """

    def __init__(self):
        self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_user_group_ids(self, email_id: str) -> list[str]:
        """Fetches the Entra ID security group Object IDs for a given user.

        Authenticates against Microsoft Graph API using the service connection settings
        and retrieves all groups the user is a transitive member of.

        Args:
            email_id (str): The email address (User Principal Name) of the user.

        Returns:
            list[str]: A list of Entra ID group Object IDs.
        """
        token_url = f"https://login.microsoftonline.com/{environ.get('CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID')}/oauth2/v2.0/token"
        token_data = {
            "grant_type": "client_credentials",
            "client_id": environ.get(
                "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID"
            ),
            "client_secret": environ.get(
                "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET"
            ),
            "scope": "https://graph.microsoft.com/.default",
        }

        async with self.session.post(token_url, data=token_data) as token_response:
            token_data = await token_response.json()
            access_token = token_data["access_token"]

        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://graph.microsoft.com/v1.0/users/{email_id}/transitiveMemberOf"

        async with self.session.get(url, headers=headers) as response:
            data = await response.json()
            group_ids = [
                item["id"]
                for item in data.get("value", [])
                if item["@odata.type"] == "#microsoft.graph.group"
            ]
            return group_ids
