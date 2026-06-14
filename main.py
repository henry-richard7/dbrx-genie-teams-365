"""
The main module to run Teams Genie Bot.

This module initializes the FastAPI server, configures the Bot Framework adapter
and state storage, and sets up routing for Microsoft Teams activities.
"""

import logging
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
from microsoft_agents.hosting.core import Authorization, MemoryStorage

from bot.bot import TeamsGenieBot
from config import DefaultConfig

load_dotenv()

logging.basicConfig(
    level=(
        logging.DEBUG
        if environ.get("DEBUG", "true").lower() == "true"
        else logging.INFO
    ),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

CONFIG = DefaultConfig()

agents_sdk_config = load_configuration_from_env(environ)

STORAGE = MemoryStorage()
CONNECTION_MANAGER = MsalConnectionManager(**agents_sdk_config)
ADAPTER = CloudAdapter(connection_manager=CONNECTION_MANAGER)
AUTHORIZATION = Authorization(STORAGE, CONNECTION_MANAGER, **agents_sdk_config)

AGENT = TeamsGenieBot()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.

    This context manager ensures that database tables are created when the app starts
    and that the database connection is cleanly closed when the app shuts down.

    Args:
        app (FastAPI): The FastAPI application instance.

    Yields:
        None
    """
    # on startup
    await AGENT.database.create_tables()
    yield
    # on shutdown
    await AGENT.close()
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
    Endpoint for handling incoming Microsoft Teams messages and activities.

    This endpoint receives POST requests from the Azure Bot Framework, processes
    them via the configured adapter, and routes them to the agent.

    Args:
        req (Request): The incoming FastAPI HTTP request containing activity data.

    Returns:
        Response: The HTTP response from the Bot Framework adapter.
    """
    return await start_agent_process(
        req,
        AGENT,
        adapter=ADAPTER,
    )


from fastapi.responses import HTMLResponse
from datetime import datetime, timezone, timedelta
from handlers.oauth_handler import OAuthHandler

OAUTH_HANDLER = OAuthHandler()

@app.get("/api/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str, state: str):
    """
    Handles the OAuth callback from Entra ID.
    """
    try:
        user_id = state
        token_data = await OAUTH_HANDLER.exchange_code(code)
        
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        await AGENT.database.save_user_token(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at
        )
        
        return """
        <html>
            <head><title>Login Successful</title></head>
            <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                <h2>Login Successful!</h2>
                <p>You have successfully authenticated with Databricks.</p>
                <p>You can close this window and return to Microsoft Teams.</p>
            </body>
        </html>
        """
    except Exception as e:
        logging.error(f"Error in OAuth callback: {e}", exc_info=True)
        return f"""
        <html>
            <head><title>Login Failed</title></head>
            <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                <h2>Login Failed</h2>
                <p>There was an error completing your authentication: {str(e)}</p>
                <p>Please try again.</p>
            </body>
        </html>
        """

if __name__ == "__main__":
    port = int(environ.get("PORT", 3978))
    uvicorn.run(app, host="0.0.0.0", port=port)
