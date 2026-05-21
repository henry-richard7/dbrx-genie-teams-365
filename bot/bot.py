"""
This module contains the core Bot logic for Microsoft Teams integration.

It handles incoming messages, user authorization, multi-tenant group resolution,
and orchestrates responses using various handlers.
"""

from os import environ
import logging
import aiohttp

from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.hosting.teams import TeamsActivityHandler, TeamsInfo
from microsoft_agents.activity import (
    ChannelAccount,
)

from handlers.file_card_handler import FileCardHandler
from handlers.message_handler import MessageHandler
from database.database import Database
from utils.user_group import UserGroup

logger = logging.getLogger(__name__)


class TeamsGenieBot(TeamsActivityHandler):
    """The main Microsoft 365 Agents Class.

    This class handles Microsoft Teams activities such as member addition,
    file consent, and incoming messages.

    Attributes:
        database (Database): The SQLite database interface for storing user state.
        message_handler (MessageHandler): The handler for processing incoming chat messages.
        file_card_handler (FileCardHandler): The handler for processing Excel file consent events.
        user_group (UserGroup): The utility for determining user security groups from Entra ID.
    """

    def __init__(self):
        """Initializes the TeamsGenieBot and sets up its associated handlers and utilities."""
        super().__init__()
        self.database = Database()
        self.message_handler = MessageHandler(self.database)
        self.file_card_handler = FileCardHandler()
        self.user_group = UserGroup()
        self.session = None

    async def close(self):
        """Clean up background resources and sessions."""
        if self.session and not self.session.closed:
            await self.session.close()
        await self.user_group.close()

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ):
        """Handles activities when new members are added to a conversation.

        Args:
            members_added (list[ChannelAccount]): A list of members added to the conversation.
            turn_context (TurnContext): The context object for this turn.
        """
        logger.info(
            f"on_members_added_activity triggered. Members added: {[m.id for m in members_added]}"
        )
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                logger.debug(f"Sending welcome message to new member: {member.id}")
                await turn_context.send_activity("Welcome to Databricks Genie Bot!")

    async def on_teams_file_consent(
        self, turn_context: TurnContext, file_consent_card_response: dict
    ):
        """Handles user responses to file consent cards in Teams.

        This method acts as a router, redirecting to the accept or decline handler
        based on the user's interaction with the file consent card.

        Args:
            turn_context (TurnContext): The context object for this turn.
            file_consent_card_response (dict): The dictionary containing the user's response.
        """
        action = file_consent_card_response.get("action")
        logger.info(f"on_teams_file_consent triggered with action: {action}")
        if action == "accept":
            await self.on_teams_file_consent_accept(
                turn_context, file_consent_card_response
            )
        elif action == "decline":
            await self.on_teams_file_consent_decline(
                turn_context, file_consent_card_response
            )
        else:
            logger.warning(f"Unknown file consent action received: {action}")

    async def on_teams_file_consent_accept(
        self,
        turn_context: TurnContext,
        file_consent_card_response: dict,
    ):
        """Processes the acceptance of a file consent request.

        Decodes the file bytes from the card's context and uploads the file to the
        provided upload URL via an HTTP PUT request.

        Args:
            turn_context (TurnContext): The context object for this turn.
            file_consent_card_response (dict): The payload containing file bytes and upload URLs.
        """
        logger.info("on_teams_file_consent_accept triggered.")
        await turn_context.delete_activity(turn_context.activity.reply_to_id)

        context = file_consent_card_response["context"]
        file_name = context.get("filename", "unknown")
        file_id = context.get("file_id")

        if not file_id or file_id not in FileCardHandler._pending_files:
            logger.error(
                f"File accept received but file_id '{file_id}' not found in cache."
            )
            await self.file_card_handler._file_upload_failed(
                turn_context,
                "File data not found. It may have expired — please ask your question again.",
            )
            return

        # Retrieve and immediately evict the cached bytes to free memory
        file_bytes = FileCardHandler._pending_files.pop(file_id)
        file_size = len(file_bytes)
        logger.debug(f"Retrieved {file_size} bytes for file '{file_name}' from cache.")

        headers = {
            "Content-Length": f"{file_size}",
            "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
        }

        try:
            logger.debug(f"Uploading file {file_name} with size {file_size} bytes.")
            if not self.session or self.session.closed:
                logger.debug("Initializing new aiohttp ClientSession for upload.")
                self.session = aiohttp.ClientSession()
            async with self.session.put(
                file_consent_card_response["uploadInfo"]["uploadUrl"],
                data=file_bytes,
                headers=headers,
            ) as response:
                if response.status in [200, 201]:
                    logger.info(
                        f"File {file_name} uploaded successfully. Status: {response.status}"
                    )
                    await self.file_card_handler._file_upload_complete(
                        turn_context, file_consent_card_response
                    )
                else:
                    logger.warning(
                        f"File upload failed. Status: {response.status}. Response: {await response.text()}"
                    )
                    await self.file_card_handler._file_upload_failed(
                        turn_context, "Unable to upload file."
                    )
        except Exception as e:
            logger.error(f"Error uploading file {file_name}: {e}", exc_info=True)
            await self.file_card_handler._file_upload_failed(
                turn_context, "Unable to upload file due to an error."
            )

    async def on_teams_file_consent_decline(
        self,
        turn_context: TurnContext,
        file_consent_card_response: dict,
    ):
        """Processes the decline of a file consent request.

        Sends a confirmation message to the user acknowledging that the file upload
        was declined and will not proceed.

        Args:
            turn_context (TurnContext): The context object for this turn.
            file_consent_card_response (dict): The payload containing the file context.
        """
        logger.info("on_teams_file_consent_decline triggered.")
        await turn_context.delete_activity(turn_context.activity.reply_to_id)

        context = file_consent_card_response["context"]
        file_name = context.get("filename", "unknown")
        file_id = context.get("file_id")

        # Free cached bytes so they don't linger in memory indefinitely
        if file_id:
            FileCardHandler._pending_files.pop(file_id, None)
            logger.debug(f"Evicted cached bytes for file_id '{file_id}' on decline.")

        logger.debug(f"User declined upload for file: {file_name}")
        reply = turn_context.activity.create_reply(
            text=f"Declined. We won't upload file <b>{file_name}</b>.",
        )

        await turn_context.send_activity(reply)

    async def on_message_activity(self, turn_context: TurnContext):
        """Handles incoming message activities from users.

        Validates user credentials against global settings or Entra ID security groups.
        If the user is authorized, it delegates message processing to the MessageHandler.

        Args:
            turn_context (TurnContext): The context object containing the message payload.
        """
        logger.info("on_message_activity triggered.")
        has_global_token = bool(environ.get("DATABRICKS_TOKEN"))
        has_global_oauth = bool(
            environ.get("DATABRICKS_CLIENT_ID")
            and environ.get("DATABRICKS_CLIENT_SECRET")
        )

        if has_global_token or has_global_oauth:
            # If global Databricks credentials are provided, bypass group-based access control.
            logger.debug(
                "Global Databricks credentials found, bypassing group access control."
            )
            await self.message_handler.process_message(turn_context)
            return

        try:
            logger.debug(
                f"Fetching member info for user ID: {turn_context.activity.from_property.id}"
            )
            members = await TeamsInfo.get_member(
                turn_context, turn_context.activity.from_property.id
            )
        except Exception as e:
            logger.error(f"Failed to retrieve member info: {e}", exc_info=True)
            await turn_context.send_activity("Error: Could not retrieve user profile.")
            return

        user_email = members.email
        logger.debug(f"Retrieving user groups for email: {user_email}")
        user_group_ids = await self.user_group.get_user_group_ids(user_email)

        logger.debug(
            f"Querying security group mappings for group IDs: {user_group_ids}"
        )
        user_groups = await self.database.get_security_group_mapping(user_group_ids)

        if not user_groups:
            logger.warning(
                f"User {user_email} is not part of any configured security group."
            )
            await turn_context.send_activity(
                "Sorry, you're not part of any security group for accessing Databricks. If you believe this is an error, please contact your administrator."
            )
            return

        turn_context.turn_state["user_groups"] = user_groups

        user_id = turn_context.activity.from_property.id
        user_selection = await self.database.get_user_selection(user_id)
        selected_group = None
        if user_selection and getattr(user_selection, "user_group_id", None):
            for group in user_groups:
                if group.group_id == user_selection.user_group_id:
                    selected_group = group
                    break

        if selected_group:
            logger.info(
                f"User mapped to {len(user_groups)} groups. Setting creds to previously selected group: {selected_group.group_name or selected_group.group_id}"
            )
            turn_context.turn_state["databricks_creds"] = selected_group
        elif len(user_groups) == 1:
            logger.info(
                f"User mapped to 1 group. Setting default creds to: {user_groups[0].group_name or user_groups[0].group_id}"
            )
            turn_context.turn_state["databricks_creds"] = user_groups[0]
        else:
            logger.info(
                f"User mapped to {len(user_groups)} groups. Prompts will occur in message handler."
            )

        logger.debug("Delegating message processing to message_handler.")
        await self.message_handler.process_message(turn_context)
