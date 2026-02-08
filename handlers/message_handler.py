import asyncio

from thefuzz import fuzz
from microsoft_agents.hosting.core import TurnContext, MessageFactory, CardFactory

from modules.genie import Genie
from modules.AdaptiveCardTemplate import AdaptiveCardTemplate
from utils.bot_utils import BotUtilities
from handlers.genie_list_handler import GenieListHandler
from database.database import Database, UserSelection

COMMAND_LIST_SPACES = "list genie spaces"


class MessageHandler:
    """This handler processes incoming messages and routes them to the appropriate logic."""

    def __init__(self):
        self.genie_list_handler = GenieListHandler()

    async def handle_card_action(
        self, turn_context: TurnContext, user_id: str, action_data: dict
    ):
        """Handle actions from adaptive card buttons."""
        action = action_data.get("action")

        if action == "select_space":
            space_name = action_data.get("space_name")
            space_id = action_data.get("space_id")
            if space_name and space_id:
                await self.handle_space_selection(
                    turn_context, user_id, space_id, space_name
                )
            elif not space_name:
                await turn_context.send_activity("❌ Invalid space selection.")

        elif action == "refresh_spaces":
            await turn_context.delete_activity(turn_context.activity.reply_to_id)
            await Database().clear_user_space_mappings(
                user_id
            )  # Clear cached spaces for the user

            # Fetch spaces again
            response = await BotUtilities.keep_typing_while(
                turn_context,
                self.genie_list_handler.handle_list_spaces,
                user_id=user_id,
            )
            await turn_context.send_activity(response)

        elif action == "retry_spaces":
            # Retry fetching spaces
            response = await BotUtilities.keep_typing_while(
                turn_context,
                self.genie_list_handler.handle_list_spaces,
                user_id=user_id,
            )
            await turn_context.send_activity(response)

        elif action == "show_help":
            help_message = (
                "🤖 **Databricks Genie Bot Help**\n\n"
                "**Available Commands:**\n"
                "• `list genie spaces` - Show available Genie spaces\n\n"
                "**How to use:**\n"
                "1. Select a Genie space from the list\n"
                "2. Ask questions about your data in natural language\n"
                "3. Get AI-powered insights and visualizations\n\n"
                "**Examples:**\n"
                "• 'Show me sales trends for the last quarter'\n"
                "• 'What are the top performing products?'\n"
                "• 'Create a chart of monthly revenue'\n\n"
                "**Need more help?** Contact your administrator."
            )
            await turn_context.send_activity(help_message)

        else:
            await turn_context.send_activity("❌ Unknown action. Please try again.")

    async def handle_space_selection(
        self, turn_context: TurnContext, user_id: str, space_id: str, space_name: str
    ):
        """Save the user's space selection."""
        await Database().update_user_selection(
            user_id=user_id,
            space_id=space_id,
            space_name=space_name,
            conversation_id=None,
        )
        await turn_context.send_activity(
            f"✅ Selected space: **{space_name}**. You can now ask questions!"
        )

    async def handle_genie_question(
        self,
        turn_context: TurnContext,
        user_id: str,
        question: str,
        user_selection: UserSelection,
    ):
        """Handle natural language questions to Genie."""
        genie = Genie()

        async def ask():
            return await genie.ask_genie(
                question=question,
                space_id=user_selection.space_id,
                conversation_id=user_selection.conversation_id,
            )

        response_data = await BotUtilities.keep_typing_while(turn_context, ask)

        if "error" in response_data:
            await turn_context.send_activity(f"❌ {response_data['error']}")
            return

        # Update conversation_id if changed
        new_conversation_id = response_data.get("conversation_id")
        if (
            new_conversation_id
            and new_conversation_id != user_selection.conversation_id
        ):
            await Database().update_user_selection(
                user_id,
                user_selection.space_id,
                user_selection.space_name,
                new_conversation_id,
            )

        # Process response
        genie_response = response_data.get("response", {})

        # If it's just text
        if "message" in genie_response and not genie_response.get("data"):
            await turn_context.send_activity(genie_response["message"])
            return

        # Create Adaptive Card for data response
        card = AdaptiveCardTemplate()
        card.add_text(question, is_title=True, color="Accent")

        if "query_description" in genie_response:
            card.add_text(genie_response["query_description"])

        if "data" in genie_response and "columns" in genie_response:
            card.add_query_result_table(
                genie_response["columns"], genie_response["data"]
            )

        if "query" in genie_response:
            card.add_sql_code(genie_response["query"])

        attachment = CardFactory.adaptive_card(card.get_adaptive_card())
        await turn_context.send_activity(MessageFactory.attachment(attachment))

    async def process_message(self, turn_context: TurnContext):
        user_id = turn_context.activity.from_property.id
        if (
            turn_context.activity.value is not None
        ):  # This indicates a card action response
            await self.handle_card_action(
                turn_context, user_id, turn_context.activity.value
            )
            return
        else:
            # This is a regular message, process commands
            text = turn_context.activity.text.strip().lower()

            if (
                fuzz.partial_ratio(text, COMMAND_LIST_SPACES) >= 70
            ):  # Use fuzzy matching to allow for minor typos
                response = await BotUtilities.keep_typing_while(
                    turn_context,
                    self.genie_list_handler.handle_list_spaces,
                    user_id=user_id,
                )
                await turn_context.send_activity(response)
            else:
                # Check if user has a space selected
                user_selection = await Database().get_user_selection(user_id)
                if user_selection and user_selection.space_id:
                    await self.handle_genie_question(
                        turn_context, user_id, text, user_selection
                    )
                else:
                    await turn_context.send_activity(
                        "Please select a Genie space first by typing 'list genie spaces'."
                    )
