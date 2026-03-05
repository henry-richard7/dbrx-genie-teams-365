"""
The main module to run Teams Genie Bot
"""

import uvicorn
from os import environ
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from microsoft_agents.activity import load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.fastapi import (
    CloudAdapter,
    JwtAuthorizationMiddleware,
    start_agent_process,
)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.
    """
    # on startup
    await AGENT.database.create_tables()
    yield
    # on shutdown
    await AGENT.database.close()


# Listen for incoming requests on /api/messages
app = FastAPI(title="Authorization Agent Sample", version="1.0.0", lifespan=lifespan)
app.state.agent_configuration = (
    CONNECTION_MANAGER.get_default_connection_configuration()
)
app.add_middleware(JwtAuthorizationMiddleware)


@app.post("/api/messages")
async def messages(req: Request):
    """
    Handles Teams Messages.
    """
    # adapter: CloudAdapter = req.app["adapter"]
    # return await adapter.process(req, AGENT)
    return await start_agent_process(
        req,
        AGENT,
        adapter=ADAPTER,
    )


if __name__ == "__main__":
    port = int(environ.get("PORT", 3978))
    uvicorn.run(app, host="0.0.0.0", port=port)
