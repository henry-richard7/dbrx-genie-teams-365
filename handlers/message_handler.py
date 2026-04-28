import asyncio
from io import BytesIO
import os
import logging

from thefuzz import fuzz
from microsoft_agents.hosting.core import TurnContext, MessageFactory, CardFactory
import polars
from uuid import uuid4

from modules.genie import Genie
from modules.AdaptiveCardTemplate import AdaptiveCardTemplate
from utils.bot_utils import BotUtilities
from handlers.genie_list_handler import GenieListHandler
from handlers.file_card_handler import FileCardHandler
from database.database import Database
from database.db_models import UserSelection
from utils.llm_summarizer import LlmSummarizer

COMMAND_LIST_SPACES = "list genie spaces"
logger = logging.getLogger(__name__)


class MessageHandler:
    """Processes incoming messages from Teams and routes them to the appropriate logic.

    This class handles the core interaction flow: resolving commands, processing
    button clicks (Adaptive Card actions), querying Databricks Genie spaces,
    and rendering responses as Adaptive Cards.

    Attributes:
        database (Database): The database interface for managing state.
        genie_list_handler (GenieListHandler): The handler for space listing.
        file_card_handler (FileCardHandler): The handler for file downloads.
        llm_summarizer (LlmSummarizer): The utility for generating AI summaries.
    """

    def __init__(self, database: Database):
        self.database = database
        self.genie_list_handler = GenieListHandler(database)
        self.file_card_handler = FileCardHandler()
        self.llm_summarizer = LlmSummarizer()

    async def _get_databricks_credentials_kwargs(self, turn_context: TurnContext, send_prompt: bool = True, force_prompt: bool = False) -> dict | None:
        """Helper to resolve Databricks credentials. Returns a dict of kwargs or None if missing."""
        has_global_token = bool(os.environ.get("DATABRICKS_TOKEN"))
        has_global_oauth = bool(os.environ.get("DATABRICKS_CLIENT_ID") and os.environ.get("DATABRICKS_CLIENT_SECRET"))
        
        if has_global_token or has_global_oauth:
            return {} # Global credentials implicitly used

        user_groups = turn_context.turn_state.get("user_groups", [])

        if force_prompt and len(user_groups) > 1:
            logger.info("User is in multiple groups and force_prompt is true, prompting for scope selection.")
            await self.send_group_selection_card(turn_context, user_groups)
            return None

        creds = turn_context.turn_state.get("databricks_creds")
        if creds:
            return {
                "client_id": creds.databricks_client_id,
                "client_secret": creds.databricks_client_secret,
                "scope_name": getattr(creds, "group_name", creds.group_id)
            }
        
        if send_prompt:
            if len(user_groups) > 1:
                logger.info("User is in multiple groups, prompting for scope selection.")
                await self.send_group_selection_card(turn_context, user_groups)
            else:
                logger.error("Could not determine access scope.")
                await turn_context.send_activity("Error: Could not determine access scope. Please try `list genie spaces` again.")
        else:
            logger.error("Credentials not found.")
            await turn_context.send_activity("Error: Credentials not found.")
        
        return None

    async def handle_card_action(
        self, turn_context: TurnContext, user_id: str, action_data: dict
    ):
        """Processes button clicks and form submissions from Adaptive Cards.

        Args:
            turn_context (TurnContext): The context object for the current turn.
            user_id (str): The Microsoft Teams user ID.
            action_data (dict): The payload returned from the Adaptive Card action.
        """
        action = action_data.get("action")
        logger.info(
            f"handle_card_action triggered for user: {user_id}, action: {action}"
        )

        if action == "select_space":
            space_name = action_data.get("space_name")
            space_id = action_data.get("space_id")
            logger.debug(
                f"Action 'select_space' details: name={space_name}, id={space_id}"
            )
            if space_name and space_id:
                await self.handle_space_selection(
                    turn_context, user_id, space_id, space_name
                )
            elif not space_name:
                logger.warning("Invalid space selection: missing space_name")
                await turn_context.send_activity("❌ Invalid space selection.")

        elif action == "select_group":
            logger.debug("Handling 'select_group' action.")
            await turn_context.delete_activity(turn_context.activity.reply_to_id)
            group_index = action_data.get("group_index")
            user_groups = turn_context.turn_state.get("user_groups", [])

            if user_groups and 0 <= group_index < len(user_groups):
                selected_group = user_groups[group_index]
                turn_context.turn_state["databricks_creds"] = selected_group
                await self.database.update_user_scope(user_id, selected_group.group_id)
                logger.info(
                    f"User {user_id} successfully selected group: {getattr(selected_group, 'group_name', selected_group.group_id)}"
                )

                # Clear cached spaces to ensure we fetch for the new scope
                logger.debug(f"Clearing cached spaces for user {user_id}")
                await self.database.clear_user_space_mappings(user_id)

                response = await BotUtilities.keep_typing_while(
                    turn_context,
                    self.genie_list_handler.handle_list_spaces,
                    user_id=user_id,
                    client_id=selected_group.databricks_client_id,
                    client_secret=selected_group.databricks_client_secret,
                    scope_name=getattr(
                        selected_group, "group_name", selected_group.group_id
                    ),
                )
                await turn_context.send_activity(response)
            else:
                logger.warning(
                    f"Invalid group selection. Index: {group_index}, User groups len: {len(user_groups) if user_groups else 0}"
                )
                await turn_context.send_activity("❌ Invalid group selection.")

        elif action == "refresh_spaces":
            logger.debug("Handling 'refresh_spaces' action.")
            await turn_context.delete_activity(turn_context.activity.reply_to_id)
            logger.debug(f"Clearing cached spaces for user {user_id}")
            await self.database.clear_user_space_mappings(
                user_id
            )  # Clear cached spaces for the user

            creds_kwargs = await self._get_databricks_credentials_kwargs(turn_context, send_prompt=False)
            if creds_kwargs is None:
                return
            list_spaces_kwargs = {"user_id": user_id, **creds_kwargs}

            response = await BotUtilities.keep_typing_while(
                turn_context,
                self.genie_list_handler.handle_list_spaces,
                **list_spaces_kwargs,
            )
            await turn_context.send_activity(response)

        elif action == "retry_spaces":
            creds_kwargs = await self._get_databricks_credentials_kwargs(turn_context, send_prompt=False)
            if creds_kwargs is None:
                return
            list_spaces_kwargs = {"user_id": user_id, **creds_kwargs}

            response = await BotUtilities.keep_typing_while(
                turn_context,
                self.genie_list_handler.handle_list_spaces,
                **list_spaces_kwargs,
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
        """Saves the user's selected Databricks Genie Space and updates context.

        Args:
            turn_context (TurnContext): The context object for the current turn.
            user_id (str): The Microsoft Teams user ID.
            space_id (str): The ID of the selected space.
            space_name (str): The name of the selected space.
        """
        logger.info(
            f"handle_space_selection triggered for user: {user_id}, space: {space_name} ({space_id})"
        )
        await self.database.update_user_selection(
            user_id=user_id,
            space_id=space_id,
            space_name=space_name,
            conversation_id=None,
        )
        logger.debug("User selection updated in database.")
        await turn_context.delete_activity(turn_context.activity.reply_to_id)
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
        """Executes a natural language query against the selected Genie space.

        Retrieves the results from Databricks, uses the LLM to summarize them,
        generates charts if applicable, and sends the response back to Teams
        as a series of Adaptive Cards.

        Args:
            turn_context (TurnContext): The context object for the current turn.
            user_id (str): The Microsoft Teams user ID.
            question (str): The natural language query submitted by the user.
            user_selection (UserSelection): The user's active context state.
        """
        logger.info(
            f"handle_genie_question triggered for user: {user_id}, question: '{question}'"
        )
        creds_kwargs = await self._get_databricks_credentials_kwargs(turn_context, send_prompt=True)
        if creds_kwargs is None:
            return
            
        client_id = creds_kwargs.get("client_id")
        client_secret = creds_kwargs.get("client_secret")
        
        if not client_id and not client_secret:
            logger.debug("Using global Databricks credentials to initialize Genie.")
            genie = Genie()
        else:
            genie = Genie(client_id=client_id, client_secret=client_secret)
        sending_excel = False

        async def ask():
            logger.debug(
                f"Sending question to Genie. Space ID: {user_selection.space_id}, Conversation ID: {user_selection.conversation_id}"
            )
            return await genie.ask_genie(
                question=question,
                space_id=user_selection.space_id,
                conversation_id=user_selection.conversation_id,
            )

        logger.debug("Waiting for Genie response...")
        response_data = await BotUtilities.keep_typing_while(turn_context, ask)

        if "error" in response_data:
            logger.warning(f"Genie returned an error: {response_data['error']}")
            await turn_context.send_activity(f"❌ {response_data['error']}")
            return

        # Update conversation_id if changed
        new_conversation_id = response_data.get("conversation_id")
        if (
            new_conversation_id
            and new_conversation_id != user_selection.conversation_id
        ):
            logger.debug(
                f"Updating conversation ID for user {user_id} to {new_conversation_id}"
            )
            await self.database.update_user_selection(
                user_id,
                user_selection.space_id,
                user_selection.space_name,
                new_conversation_id,
            )

        # Process response
        genie_response = response_data.get("response", {})
        logger.debug("Processing Genie response.")

        # If it's just text
        if "message" in genie_response and not genie_response.get("data"):
            await turn_context.send_activity(genie_response["message"])
            return

        # Create Adaptive Card for summary response
        summary_card = AdaptiveCardTemplate()
        summary_card.add_text(question.title(), is_title=True, color="Accent")

        if "query_description" in genie_response:
            summary_card.add_text(genie_response["query_description"])

        table_card = None
        chart_card = None

        if "data" in genie_response and "columns" in genie_response:
            # Generate summary
            try:
                logger.debug("Generating summary from data via llm_summarizer.")

                client_id = None
                client_secret = None
                has_global_token = bool(os.environ.get("DATABRICKS_TOKEN"))
                has_global_oauth = bool(os.environ.get("DATABRICKS_CLIENT_ID") and os.environ.get("DATABRICKS_CLIENT_SECRET"))
                if not (has_global_token or has_global_oauth):
                    # user's scope dbrx_creds should be defined from earlier in handle_genie_question
                    dbrx_creds = getattr(
                        turn_context.turn_state, "get", lambda x, y=None: None
                    )("databricks_creds")
                    if dbrx_creds:
                        client_id = dbrx_creds.databricks_client_id
                        client_secret = dbrx_creds.databricks_client_secret

                summary_result = await asyncio.to_thread(
                    self.llm_summarizer.summarize,
                    genie_response["columns"]["columns"],
                    genie_response["data"]["data_array"],
                    question,
                    client_id,
                    client_secret,
                )
                
                if isinstance(summary_result, dict):
                    summary_text = summary_result.get("text", "")
                    chart_type = summary_result.get("chart")
                else:
                    summary_text = str(summary_result)
                    chart_type = None

                summary_card.add_text(summary_text)

                # Add chart if enabled and recommended
                if chart_type and os.environ.get("ENABLE_CHARTS", "inactive").lower() == "active":
                    try:
                        logger.debug(f"Attempting to render chart: {chart_type}")
                        chart_card = AdaptiveCardTemplate()
                        # Slice data to top 15 rows for charts to improve readability
                        chart_data = {"data_array": genie_response["data"]["data_array"][:15]}
                        if chart_type == "Chart.VerticalBar":
                            chart_card.add_vertical_bar_chart(chart_data, genie_response["columns"])
                        elif chart_type == "Chart.Donut":
                            chart_card.add_donut_chart(chart_data, genie_response["columns"])
                        elif chart_type == "Chart.VerticalBar.Grouped":
                            chart_card.add_grouped_bar_chart(chart_data, genie_response["columns"])
                        elif chart_type == "Chart.HorizontalBar.Stacked":
                            chart_card.add_stacked_horizontal_bar_chart(chart_data, genie_response["columns"])
                    except Exception as ce:
                        logger.error(f"Failed to render chart {chart_type}: {ce}", exc_info=True)
                        chart_card = None
            except Exception as e:
                logger.error(f"Failed to generate summary: {e}", exc_info=True)

            row_count = genie_response["data"]["row_count"]
            logger.debug(f"Data row count: {row_count}")

            if row_count < 100:
                logger.debug("Row count < 100, creating table Adaptive Card.")
                table_card = AdaptiveCardTemplate()
                table_card.add_query_result_table(
                    genie_response["columns"], genie_response["data"]
                )
            else:
                # For large datasets, we add a button to download the results as CSV/Excel
                # Generate Excel in memory to avoid disk I/O
                logger.debug("Row count >= 100, preparing Excel file for upload.")
                sending_excel = True

                # Create the dataframe
                logger.debug("Creating Polars DataFrame.")
                df = polars.DataFrame(
                    data=genie_response["data"]["data_array"],
                    schema=[
                        col["name"] for col in genie_response["columns"]["columns"]
                    ],
                    orient="row",
                )

                # Write to in-memory buffer
                excel_buffer = BytesIO()
                df.write_excel(excel_buffer)
                excel_buffer.seek(0)

                filename = f"{uuid4()}.xlsx"

        if "query" in genie_response:
            logger.debug("Adding SQL query to table Adaptive Card.")
            if table_card is None:
                table_card = AdaptiveCardTemplate()
            table_card.add_sql_code(genie_response["query"])

        logger.debug("Sending Summary Adaptive Card response to user.")
        summary_attachment = CardFactory.adaptive_card(summary_card.get_adaptive_card())
        await turn_context.send_activity(MessageFactory.attachment(summary_attachment))

        if chart_card:
            logger.debug("Sending Chart Adaptive Card response to user.")
            chart_attachment = CardFactory.adaptive_card(chart_card.get_adaptive_card())
            await turn_context.send_activity(MessageFactory.attachment(chart_attachment))

        if table_card:
            logger.debug("Sending Table Adaptive Card response to user.")
            table_attachment = CardFactory.adaptive_card(table_card.get_adaptive_card())
            await turn_context.send_activity(MessageFactory.attachment(table_attachment))

        if sending_excel:
            logger.info(f"Sending Excel file card for {filename}")
            await self.file_card_handler.send_file_card(
                turn_context,
                filename=filename,
                file_size=excel_buffer.getbuffer().nbytes,
                file_bytes=excel_buffer,
            )

    async def send_group_selection_card(
        self, turn_context: TurnContext, user_groups: list
    ):
        """Sends an Adaptive Card asking the user to select an active security group scope.

        Args:
            turn_context (TurnContext): The context object for the current turn.
            user_groups (list): A list of SecurityGroupMapping objects the user belongs to.
        """
        card_template = AdaptiveCardTemplate()
        card_template.add_text(
            content="🔐 Select Access Scope",
            is_title=True,
            color="Accent",
        )
        card_template.add_text(
            content="You are a member of multiple groups. Please select which scope you want to use:",
            is_title=False,
        )

        for index, group in enumerate(user_groups):
            group_name = getattr(
                group, "group_name", getattr(group, "name", f"Scope {index + 1}")
            )

            card_template.add_item(
                {
                    "type": "ActionSet",
                    "actions": [
                        {
                            "type": "Action.Submit",
                            "title": group_name,
                            "data": {
                                "action": "select_group",
                                "group_index": index,
                            },
                        }
                    ],
                }
            )

        attachment = CardFactory.adaptive_card(card_template.get_adaptive_card())
        await turn_context.send_activity(MessageFactory.attachment(attachment))

    async def process_message(self, turn_context: TurnContext):
        """The main entry point for processing incoming messages.

        Routes the message based on whether it is an Adaptive Card action (button click)
        or a natural language message. For text, it handles commands like 'list genie spaces'
        or delegates to `handle_genie_question`.

        Args:
            turn_context (TurnContext): The context object for the current turn.
        """
        try:
            user_id = turn_context.activity.from_property.id
            logger.info(f"process_message triggered for user: {user_id}")
            if (
                turn_context.activity.value is not None
            ):  # This indicates a card action response
                logger.debug(
                    "Message contains 'value' payload. Delegating to handle_card_action."
                )
                await self.handle_card_action(
                    turn_context, user_id, turn_context.activity.value
                )
                return
            else:
                # This is a regular message, process commands
                text = turn_context.activity.text.strip().lower()
                logger.debug(f"Processing regular text message: '{text}'")

                if fuzz.partial_ratio(text, COMMAND_LIST_SPACES) >= 70:
                    # Use fuzzy matching to allow for minor typos
                    logger.debug(
                        f"Text matches '{COMMAND_LIST_SPACES}' command. Fuzzy ratio: {fuzz.partial_ratio(text, COMMAND_LIST_SPACES)}"
                    )
                    creds_kwargs = await self._get_databricks_credentials_kwargs(turn_context, send_prompt=True, force_prompt=True)
                    if creds_kwargs is None:
                        return
                    list_spaces_kwargs = {"user_id": user_id, **creds_kwargs}

                    logger.debug("Calling GenieListHandler to fetching spaces.")
                    response = await BotUtilities.keep_typing_while(
                        turn_context,
                        self.genie_list_handler.handle_list_spaces,
                        **list_spaces_kwargs,
                    )
                    await turn_context.send_activity(response)
                else:
                    # Check if user has a space selected
                    logger.debug("Checking if user has an active Genie space selected.")
                    user_selection = await self.database.get_user_selection(user_id)
                    if user_selection and user_selection.space_id:
                        logger.info(
                            f"User has selected scope {user_selection.space_id}. Delegating to handle_genie_question."
                        )
                        await self.handle_genie_question(
                            turn_context, user_id, text, user_selection
                        )
                    else:
                        logger.info("User requested a question but has no scope selected.")
                        await turn_context.send_activity(
                            "Please select a Genie space first by typing 'list genie spaces'."
                        )
        except Exception as e:
            logger.error(f"Unexpected error in process_message: {e}", exc_info=True)
            await turn_context.send_activity("❌ I'm sorry, I encountered an unexpected error while processing your request. Please try again later.")
