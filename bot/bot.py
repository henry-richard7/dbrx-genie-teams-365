"""
This module contains the Bot logic.
"""

import base64
import logging
import aiohttp

from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.hosting.teams import TeamsActivityHandler
from microsoft_agents.activity import (
    ChannelAccount,
)

from handlers.file_card_handler import FileCardHandler
from handlers.message_handler import MessageHandler
from database.database import Database

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

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Welcome to Databricks Genie Bot!")

    async def on_teams_file_consent(
        self, turn_context: TurnContext, file_consent_card_response: dict
    ):
        """
        Override to handle dictionary response.
        """
        action = file_consent_card_response.get("action")
        if action == "accept":
            await self.on_teams_file_consent_accept(
                turn_context, file_consent_card_response
            )
        elif action == "decline":
            await self.on_teams_file_consent_decline(
                turn_context, file_consent_card_response
            )

    async def on_teams_file_consent_accept(
        self,
        turn_context: TurnContext,
        file_consent_card_response: dict,
    ):
        await turn_context.delete_activity(turn_context.activity.reply_to_id)

        file_name = file_consent_card_response["context"]["filename"]
        file_bytes = base64.b64decode(
            file_consent_card_response["context"]["file_bytes"]
        )
        file_size = len(file_bytes)

        headers = {
            "Content-Length": f"{file_size}",
            "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
        }

        async with aiohttp.ClientSession() as session:
            response = await session.put(
                file_consent_card_response["uploadInfo"]["uploadUrl"],
                data=file_bytes,
                headers=headers,
            )

        if response.status in [200, 201]:
            await self.file_card_handler._file_upload_complete(
                turn_context, file_consent_card_response
            )
        else:
            await self.file_card_handler._file_upload_failed(
                turn_context, "Unable to upload file."
            )

    async def on_teams_file_consent_decline(
        self,
        turn_context: TurnContext,
        file_consent_card_response: dict,
    ):
        """
        The user declined the file upload.
        """
        await turn_context.delete_activity(turn_context.activity.reply_to_id)

        context = file_consent_card_response["context"]
        reply = turn_context.activity.create_reply(
            text=f"Declined. We won't upload file <b>{context['filename']}</b>.",
        )

        await turn_context.send_activity(reply)

    async def on_message_activity(self, turn_context: TurnContext):
        await self.message_handler.process_message(turn_context)
