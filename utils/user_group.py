import aiohttp
from dotenv import load_dotenv
from os import environ

load_dotenv()


class UserGroup:

    async def get_user_group_ids(self, email_id: str) -> list[str]:
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

        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=token_data) as token_response:
                token_data = await token_response.json()
                access_token = token_data["access_token"]

        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://graph.microsoft.com/v1.0/users/{email_id}/transitiveMemberOf"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                group_ids = [
                    item["id"]
                    for item in data.get("value", [])
                    if item["@odata.type"] == "#microsoft.graph.group"
                ]
                return group_ids
