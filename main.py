"""
The main module to run Teams Genie Bot
"""

import pathlib
from os import environ
from dotenv import load_dotenv
from aiohttp.web import Application, Request, Response, run_app

from microsoft_agents.activity import load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import CloudAdapter, jwt_authorization_decorator
from microsoft_agents.hosting.core import Authorization, MemoryStorage, UserState

from bot.bot import TeamsGenieBot
from config import DefaultConfig

load_dotenv()

CONFIG = DefaultConfig()

agents_sdk_config = load_configuration_from_env(environ)

STORAGE = MemoryStorage()
CONNECTION_MANAGER = MsalConnectionManager(**agents_sdk_config)
ADAPTER = CloudAdapter(connection_manager=CONNECTION_MANAGER)
AUTHORIZATION = Authorization(STORAGE, CONNECTION_MANAGER, **agents_sdk_config)

USER_STATE = UserState(STORAGE)


def create_agent():
    """
    Create the appropriate agent based on configuration.
    """
    return TeamsGenieBot()


# Create the agent based on configuration
AGENT = create_agent()


# Listen for incoming requests on /api/messages
@jwt_authorization_decorator
async def messages(req: Request) -> Response:
    """
    Handles Teams Messages.
    """
    adapter: CloudAdapter = req.app["adapter"]
    return await adapter.process(req, AGENT)


APP = Application()
APP.router.add_post("/api/messages", messages)

# Add static file handling for CSS, JS, etc.
static_path = pathlib.Path(__file__).parent / "public"
if static_path.exists():
    APP.router.add_static("/public", static_path)

APP["agent_configuration"] = CONFIG
APP["adapter"] = ADAPTER

if __name__ == "__main__":
    try:
        PORT = CONFIG.PORT
        print(f"\nServer listening on port {PORT} for appId {CONFIG.CLIENT_ID}")
        run_app(APP, host="localhost", port=PORT)
    except Exception as error:
        raise error
