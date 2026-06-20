"""
Utility for resolving Databricks credentials and managing tokens.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

from microsoft_agents.hosting.core import TurnContext, MessageFactory, CardFactory
from microsoft_agents.activity import OAuthCard, CardAction, ActionTypes, Attachment

from database.database import Database
from config import DefaultConfig
from utils.bot_utils import BotUtilities
from utils.encryption import TokenEncryptor
from handlers.oauth_handler import OAuthHandler
from modules.AdaptiveCardTemplate import AdaptiveCardTemplate

logger = logging.getLogger(__name__)
CONFIG = DefaultConfig()
ENCRYPTOR = TokenEncryptor(CONFIG.TOKEN_ENCRYPTION_KEY)


class CredentialResolver:
    """Isolates the logic for resolving Databricks credentials (M2M or U2M)."""

    def __init__(self, database: Database, user_state=None):
        self.database = database
        self.user_state = user_state

    async def get_user_token_dict(self, turn_context: TurnContext, user_id: str) -> dict | None:
        if CONFIG.USE_CONTEXT and self.user_state:
            prop = self.user_state.create_property("UserTokenProperty")
            token_data = await prop.get(turn_context, {})
            if not token_data or not token_data.get("access_token"):
                out_of_band_token = await BotUtilities.get_out_of_band_token_from_storage(self.user_state, turn_context, user_id)
                if out_of_band_token and out_of_band_token.get("access_token"):
                    await prop.set(turn_context, out_of_band_token)
                    token_data = out_of_band_token
            return token_data if token_data and token_data.get("access_token") else None
        else:
            ut = await self.database.get_user_token(user_id)
            if ut and ut.access_token:
                return {
                    "access_token": ut.access_token,
                    "refresh_token": ut.refresh_token,
                    "expires_at": ut.expires_at.isoformat() if ut.expires_at else None
                }
            return None

    async def set_user_token_dict(self, turn_context: TurnContext, user_id: str, token_data: dict):
        if CONFIG.USE_CONTEXT and self.user_state:
            prop = self.user_state.create_property("UserTokenProperty")
            await prop.set(turn_context, token_data)
        else:
            expires_at_val = token_data.get("expires_at")
            expires_at = datetime.fromisoformat(expires_at_val) if isinstance(expires_at_val, str) else expires_at_val
            await self.database.save_user_token(
                user_id,
                token_data.get("access_token"),
                token_data.get("refresh_token"),
                expires_at
            )

    async def delete_user_token(self, turn_context: TurnContext, user_id: str):
        if CONFIG.USE_CONTEXT and self.user_state:
            prop = self.user_state.create_property("UserTokenProperty")
            await prop.delete(turn_context)
        else:
            await self.database.delete_user_token(user_id)

    async def check_and_refresh_token(self, turn_context: TurnContext, user_id: str, token_data: dict) -> dict | None:
        expires_at_val = token_data.get("expires_at")
        refresh_token_val = token_data.get("refresh_token")
        access_token_val = token_data.get("access_token")

        access_token_val = ENCRYPTOR.decrypt(access_token_val)
        refresh_token_val = ENCRYPTOR.decrypt(refresh_token_val)

        if not expires_at_val:
            return {"token": access_token_val}

        try:
            expires_at = datetime.fromisoformat(expires_at_val) if isinstance(expires_at_val, str) else expires_at_val
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if datetime.now(timezone.utc) >= expires_at:
                oauth_handler = OAuthHandler()
                logger.info(f"Refreshing expired token for user {user_id}")
                
                new_token = await oauth_handler.refresh_token(refresh_token_val)
                
                expires_in = new_token.get("expires_in", 3600)
                new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                
                token_data["access_token"] = ENCRYPTOR.encrypt(new_token["access_token"])
                token_data["refresh_token"] = ENCRYPTOR.encrypt(new_token.get("refresh_token", refresh_token_val))
                token_data["expires_at"] = new_expires_at.isoformat()
                
                await self.set_user_token_dict(turn_context, user_id, token_data)
                return {"token": new_token["access_token"]}
            return {"token": access_token_val}
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            await self.delete_user_token(turn_context, user_id)
            return None

    async def send_group_selection_card(self, turn_context: TurnContext, user_groups: list):
        """Generates an Adaptive Card to allow a user to pick a group context."""
        logger.debug("Generating group selection Adaptive Card.")
        card_template = AdaptiveCardTemplate()
        card_template.add_text("🔐 Select Authorization Scope", is_title=True, color="Accent")
        card_template.add_text(
            "It looks like your Azure Active Directory user is a member of multiple Databricks Service Principal groups. "
            "Please select which environment/scope you want to execute queries against for this session:"
        )

        choices = []
        for i, group in enumerate(user_groups):
            choices.append(
                {
                    "title": group.group_name or f"Group ID: {group.group_id}",
                    "value": str(i),
                }
            )

        card_template.add_item(
            {
                "type": "Input.ChoiceSet",
                "id": "group_index",
                "style": "compact",
                "isMultiSelect": False,
                "choices": choices,
            }
        )

        card_template.add_item(
            {
                "type": "ActionSet",
                "actions": [
                    {
                        "type": "Action.Submit",
                        "title": "Set Scope",
                        "data": {"action": "select_group"},
                    }
                ],
            }
        )

        attachment = CardFactory.adaptive_card(card_template.get_adaptive_card())
        await turn_context.send_activity(MessageFactory.attachment(attachment))

    async def get_databricks_credentials_kwargs(
        self,
        turn_context: TurnContext,
        send_prompt: bool = True,
        force_prompt: bool = False,
    ) -> dict | None:
        user_id = turn_context.activity.from_property.id

        has_global_token = bool(os.environ.get("DATABRICKS_TOKEN"))
        has_global_oauth = bool(
            os.environ.get("DATABRICKS_CLIENT_ID")
            and os.environ.get("DATABRICKS_CLIENT_SECRET")
        )

        if has_global_token or has_global_oauth:
            return {}  # Global credentials implicitly used

        token_data = await self.get_user_token_dict(turn_context, user_id)
        if token_data and token_data.get("access_token"):
            return await self.check_and_refresh_token(turn_context, user_id, token_data=token_data)

        oauth_handler = OAuthHandler()
        if not oauth_handler.is_configured() and getattr(CONFIG, "CONNECTION_NAME", None):
            try:
                token_response = await turn_context.adapter.get_user_token(
                    turn_context, CONFIG.CONNECTION_NAME, magic_code=None
                )
                if token_response and token_response.token:
                    return {"token": token_response.token}
            except Exception as e:
                logger.debug(f"Azure Bot OAuth token not found: {e}")

        user_groups = turn_context.turn_state.get("user_groups", [])
        if force_prompt and len(user_groups) > 1:
            logger.info("User is in multiple groups and force_prompt is true, prompting for scope selection.")
            await self.send_group_selection_card(turn_context, user_groups)
            return None

        creds = turn_context.turn_state.get("databricks_creds")
        if creds:
            if self.user_state:
                prompt_ref_prop = self.user_state.create_property("OAuthCardReference")
                prompt_ref = await prompt_ref_prop.get(turn_context)
                activity_id = prompt_ref.get("activityId") or prompt_ref.get("activity_id") if prompt_ref else None
                if activity_id:
                    try:
                        await turn_context.delete_activity(activity_id)
                    except Exception as e:
                        logging.warning(f"Could not delete OAuth card: {e}")
                    await prompt_ref_prop.delete(turn_context)
                    
            return {
                "client_id": creds.databricks_client_id,
                "client_secret": creds.databricks_client_secret,
                "scope_name": creds.group_name or creds.group_id,
            }

        if send_prompt:
            if oauth_handler.is_configured():
                auth_url = oauth_handler.get_auth_url(state=user_id)
                card_template = AdaptiveCardTemplate()
                card_template.add_text("🔐 Login to Databricks", is_title=True, color="Accent")
                card_template.add_text("Please log in to your Databricks account to continue.")
                card_template.add_item({
                    "type": "ActionSet",
                    "actions": [{"type": "Action.OpenUrl", "title": "Sign In", "url": auth_url}],
                })
                attachment = CardFactory.adaptive_card(card_template.get_adaptive_card())
                response = await turn_context.send_activity(MessageFactory.attachment(attachment))
                if self.user_state and response and response.id:
                    prompt_ref_prop = self.user_state.create_property("OAuthCardReference")
                    ref = turn_context.activity.get_conversation_reference()
                    ref.activity_id = response.id
                    await prompt_ref_prop.set(turn_context, ref.model_dump(mode="json", by_alias=True, exclude_none=True))

            elif getattr(CONFIG, "CONNECTION_NAME", None):
                sign_in_link = await turn_context.adapter.get_oauth_sign_in_link(turn_context, CONFIG.CONNECTION_NAME)
                oauth_card = OAuthCard(
                    text="Please log in to your Databricks account to continue.",
                    connection_name=CONFIG.CONNECTION_NAME,
                    buttons=[CardAction(title="Sign In", type=ActionTypes.signin, value=sign_in_link)],
                )
                attachment = Attachment(content_type="application/vnd.microsoft.card.oauth", content=oauth_card)
                response = await turn_context.send_activity(MessageFactory.attachment(attachment))
                if self.user_state and response and response.id:
                    prompt_ref_prop = self.user_state.create_property("OAuthCardReference")
                    ref = turn_context.activity.get_conversation_reference()
                    ref.activity_id = response.id
                    await prompt_ref_prop.set(turn_context, ref.model_dump(mode="json", by_alias=True, exclude_none=True))
            else:
                if len(user_groups) > 1:
                    await self.send_group_selection_card(turn_context, user_groups)
                else:
                    logger.error("Could not determine access scope or OAuth config.")
                    await turn_context.send_activity("Error: OAuth is not configured. Please contact administrator.")
        else:
            logger.error("Credentials not found.")
            await turn_context.send_activity("Error: Credentials not found.")

        return None
