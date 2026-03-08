"""
This module contains the Bot logic.
"""

from os import environ
import base64
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
    """
    The main Microsoft 365 Agents Class
    """

    def __init__(self):
        super().__init__()
        self.database = Database()
        self.message_handler = MessageHandler(self.database)
        self.file_card_handler = FileCardHandler()
        self.user_group = UserGroup()

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ):
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
        """
        Override to handle dictionary response.
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
        logger.info("on_teams_file_consent_accept triggered.")
        await turn_context.delete_activity(turn_context.activity.reply_to_id)

        file_name = file_consent_card_response["context"]["filename"]
        logger.debug(f"Decoding file bytes for: {file_name}")
        file_bytes = base64.b64decode(
            file_consent_card_response["context"]["file_bytes"]
        )
        file_size = len(file_bytes)

        headers = {
            "Content-Length": f"{file_size}",
            "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
        }

        try:
            logger.debug(f"Uploading file {file_name} with size {file_size} bytes.")
            if not getattr(self, "session", None) or self.session.closed:
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
        """
        The user declined the file upload.
        """
        logger.info("on_teams_file_consent_decline triggered.")
        await turn_context.delete_activity(turn_context.activity.reply_to_id)

        context = file_consent_card_response["context"]
        file_name = context.get("filename", "unknown")
        logger.debug(f"User declined upload for file: {file_name}")
        reply = turn_context.activity.create_reply(
            text=f"Declined. We won't upload file <b>{file_name}</b>.",
        )

        await turn_context.send_activity(reply)

    async def on_message_activity(self, turn_context: TurnContext):
        logger.info("on_message_activity triggered.")
        if environ.get("DATABRICKS_TOKEN"):
            # If a global Databricks token is provided, bypass group-based access control.
            logger.debug(
                "Global DATABRICKS_TOKEN found, bypassing group access control."
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

        if user_groups:
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
                    f"User mapped to {len(user_groups)} groups. Setting creds to previously selected group: {getattr(selected_group, 'group_name', selected_group.group_id)}"
                )
                turn_context.turn_state["databricks_creds"] = selected_group
            elif len(user_groups) == 1:
                logger.info(
                    f"User mapped to 1 group. Setting default creds to: {getattr(user_groups[0], 'group_name', user_groups[0].group_id)}"
                )
                turn_context.turn_state["databricks_creds"] = user_groups[0]
            else:
                logger.info(
                    f"User mapped to {len(user_groups)} groups. Prompts will occur in message handler."
                )
        else:
            logger.warning(
                f"User {user_email} is not part of any configured security group."
            )
            await turn_context.send_activity(
                "Sorry, you're not part of any security group for accessing Databricks. If you believe this is an error, please contact your administrator."
            )
            return

        logger.debug("Delegating message processing to message_handler.")
        await self.message_handler.process_message(turn_context)
