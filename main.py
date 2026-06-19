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
from microsoft_agents.hosting.core import (
    Authorization,
    MemoryStorage,
    UserState,
    ConversationState,
)

from bot.bot import TeamsGenieBot
from config import DefaultConfig

from storages.s3_storage import S3Storage

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

if environ.get("STORAGE") == "s3":
    STORAGE = S3Storage(
        bucket_name=environ.get("S3_BUCKET_NAME"),
        endpoint_url=environ.get("S3_ENDPOINT_URL"),  # None → real AWS S3
        aws_access_key_id=environ.get("S3_ACCESS_KEY_ID"),  # None → use IAM role
        aws_secret_access_key=environ.get("S3_SECRET_ACCESS_KEY"),
        region_name=environ.get("S3_REGION", "us-east-1"),
        key_prefix=environ.get("S3_KEY_PREFIX", ""),
    )
else:
    STORAGE = MemoryStorage()

USER_STATE = UserState(STORAGE)
CONVERSATION_STATE = ConversationState(STORAGE)
CONNECTION_MANAGER = MsalConnectionManager(**agents_sdk_config)
ADAPTER = CloudAdapter(connection_manager=CONNECTION_MANAGER)
AUTHORIZATION = Authorization(STORAGE, CONNECTION_MANAGER, **agents_sdk_config)

AGENT = TeamsGenieBot(user_state=USER_STATE, conversation_state=CONVERSATION_STATE)

from contextlib import asynccontextmanager
from typing import AsyncIterator

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Handles startup and shutdown events for the FastAPI application.

    This context manager ensures that database tables are created when the app starts
    and that the database connection is cleanly closed when the app shuts down.

    Args:
        app (FastAPI): The FastAPI application instance.

    Yields:
        None: Yields nothing.
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
from starlette.types import ASGIApp, Scope, Receive, Send


class ExemptJwtMiddleware:
    """
    Middleware to selectively bypass JWT authorization for specific routes.
    
    This middleware wraps `JwtAuthorizationMiddleware` but intercepts requests to 
    the `/api/oauth` endpoints, allowing them to pass through without token validation
    since they handle the OAuth callback flow which is unauthenticated.
    """
    
    def __init__(self, app: ASGIApp):
        """
        Initializes the middleware.
        
        Args:
            app (ASGIApp): The ASGI application.
        """
        self.app = app
        self.jwt_middleware = JwtAuthorizationMiddleware(app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """
        Processes an incoming ASGI request.
        
        Args:
            scope (Scope): The ASGI scope.
            receive (Receive): The ASGI receive callable.
            send (Send): The ASGI send callable.
        """
        if scope["type"] == "http" and scope["path"].startswith("/api/oauth"):
            await self.app(scope, receive, send)
            return
        await self.jwt_middleware(scope, receive, send)


app.add_middleware(ExemptJwtMiddleware)


from starlette.responses import Response

@app.post("/api/messages")
async def messages(req: Request) -> Response:
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
from utils.encryption import TokenEncryptor

OAUTH_HANDLER = OAuthHandler()
ENCRYPTOR = TokenEncryptor(CONFIG.TOKEN_ENCRYPTION_KEY)


from typing import Optional


@app.get("/api/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> HTMLResponse:
    """
    Handles the OAuth callback from Databricks.
    
    This endpoint is invoked by Databricks after a user successfully authenticates.
    It exchanges the authorization code for an access and refresh token, encrypts them,
    and caches them securely in either Bot Framework state or the database.
    
    Args:
        code (Optional[str]): The authorization code returned by Databricks.
        state (Optional[str]): The state parameter used for CSRF protection and context sharing.
        error (Optional[str]): The error code if the authentication failed.
        error_description (Optional[str]): Detailed description of the error if authentication failed.
        
    Returns:
        HTMLResponse: A simple HTML page indicating whether the login succeeded or failed.
    """
    if error:
        logging.error(f"OAuth returned error: {error} - {error_description}")
        return f"<html><body><h2>Login Failed</h2><p>{error_description or error}</p></body></html>"

    if not code or not state:
        return "<html><body><h2>Error</h2><p>Missing code or state.</p></body></html>"
    try:
        if "|" in state:
            channel_id, user_id = state.split("|", 1)
        else:
            channel_id, user_id = "msteams", state

        token_data = await OAUTH_HANDLER.exchange_code(code)

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        from microsoft_agents.hosting.core.state.agent_state import CachedAgentState

        if CONFIG.USE_CONTEXT:
            # We must write directly to STORAGE since we lack a TurnContext here
            state_key = f"{channel_id}/users/{user_id}"
            user_state_dict = await STORAGE.read([state_key], target_cls=CachedAgentState)
            state_obj = user_state_dict.get(state_key, CachedAgentState(state={}))
            
            if not state_obj.state:
                state_obj.state = {}
            
            # Store in the property exactly how UserState Accessor expects
            state_obj.state["UserTokenProperty"] = {
                "user_id": user_id,
                "access_token": ENCRYPTOR.encrypt(access_token),
                "refresh_token": ENCRYPTOR.encrypt(refresh_token) if refresh_token else None,
                "expires_at": expires_at.isoformat(),
            }
            await STORAGE.write({state_key: state_obj})
        else:
            await AGENT.database.save_user_token(
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )

        # Proactively delete the OAuth card if we saved its reference
        try:
            state_key = f"{channel_id}/users/{user_id}"
            user_state_dict = await STORAGE.read([state_key], target_cls=CachedAgentState)
            state_obj = user_state_dict.get(state_key)
            if state_obj and state_obj.state:
                prompt_ref = state_obj.state.get("OAuthCardReference")
                if prompt_ref and ("activityId" in prompt_ref or "activity_id" in prompt_ref):
                    from microsoft_agents.activity import ConversationReference
                    from microsoft_agents.hosting.core.turn_context import TurnContext
                    
                    ref = ConversationReference.model_validate(prompt_ref)
                    
                    async def delete_card(turn_context: TurnContext):
                        try:
                            await turn_context.delete_activity(ref.activity_id)
                        except Exception as e:
                            logging.warning(f"Could not delete OAuth card proactively: {e}")
                            
                    await ADAPTER.continue_conversation(
                        CONFIG.CLIENT_ID,
                        ref.get_continuation_activity(),
                        delete_card
                    )
                    
                    del state_obj.state["OAuthCardReference"]
                    await STORAGE.write({state_key: state_obj})
        except Exception as e:
            logging.error(f"Error proactively deleting OAuth card: {e}")

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
