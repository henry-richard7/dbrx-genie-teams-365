"""
This module contains the Bot logic.
"""

import base64
import logging
import requests

from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.hosting.teams import TeamsActivityHandler
from microsoft_agents.activity.teams import (
    FileConsentCardResponse,
)
from microsoft_agents.activity import (
    ChannelAccount,
)

from handlers.message_handler import MessageHandler
from database.database import Database

# from Modules.Genie import Genie
# from Modules.database import DatabaseManager

# from Bot.Handlers.message_handler import MessageHandler
# from Bot.Handlers.file_card_handler import FileCardHandler
# from Utils.bot_utils import BotUtilities

logger = logging.getLogger(__name__)


class TeamsGenieBot(TeamsActivityHandler):
    """
    The main Microsoft 365 Agents Class
    """

    def __init__(self):
        super().__init__()
        self.message_handler = MessageHandler()
        self.database = Database()
        # self.genie_api = Genie()
        # self.db = DatabaseManager()``

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Welcome to Databricks Genie Bot!")

    async def on_message_activity(self, turn_context: TurnContext):
        await self.database.create_tables()
        await self.message_handler.process_message(turn_context)
