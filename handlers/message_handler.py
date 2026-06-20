"""
Message routing and handling module.

This module processes incoming chat messages from Teams, delegates them to the 
Genie API or other handlers based on user action, and maintains session context.
"""
import asyncio
from datetime import datetime, timezone
from io import BytesIO
import os
import logging

from thefuzz import fuzz
from microsoft_agents.hosting.core import TurnContext, MessageFactory, CardFactory
from microsoft_agents.hosting.teams import TeamsInfo
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
from utils.chart_card_generator import AdaptiveCardChartGenerator
from utils.credential_resolver import CredentialResolver
from utils.excel_generator import ExcelGenerator

from config import DefaultConfig

COMMAND_LIST_SPACES = "list genie spaces"
logger = logging.getLogger(__name__)
CONFIG = DefaultConfig()

from utils.encryption import TokenEncryptor
ENCRYPTOR = TokenEncryptor(CONFIG.TOKEN_ENCRYPTION_KEY)

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

    def __init__(self, database: Database, user_state=None, conversation_state=None):
        self.database = database
        self.user_state = user_state
        self.conversation_state = conversation_state
        self.genie_list_handler = GenieListHandler(
            database, user_state, conversation_state
        )
        self.file_card_handler = FileCardHandler(storage=self.user_state._storage if self.user_state else None)
        self.llm_summarizer = LlmSummarizer()
        self.chart_card_generator = AdaptiveCardChartGenerator()
        self.credential_resolver = CredentialResolver(database, user_state)

    async def _get_user_selection_dict(self, turn_context: TurnContext, user_id: str) -> dict:
        if CONFIG.USE_CONTEXT and self.user_state:
            prop = self.user_state.create_property("UserSelectionProperty")
            return await prop.get(turn_context, {})
        else:
            sel = await self.database.get_user_selection(user_id)
            return sel.model_dump() if sel else {}

    async def _set_user_selection_dict(self, turn_context: TurnContext, user_id: str, selection_dict: dict):
        if CONFIG.USE_CONTEXT and self.user_state:
            prop = self.user_state.create_property("UserSelectionProperty")
            selection_dict["user_id"] = user_id
            await prop.set(turn_context, selection_dict)
        else:
            await self.database.update_user_selection(
                user_id=user_id,
                space_id=selection_dict.get("space_id", ""),
                space_name=selection_dict.get("space_name", ""),
                workspace_host=selection_dict.get("workspace_host"),
                conversation_id=selection_dict.get("conversation_id")
            )

    async def _clear_space_cache(self, turn_context: TurnContext, user_id: str):
        """Helper to clear the cached Genie Space mappings.
        
        Args:
            turn_context (TurnContext): The context object for the current turn.
            user_id (str): The Microsoft Teams user ID.
        """
        logger.debug(f"Clearing cached spaces for user {user_id}")
        if CONFIG.USE_CONTEXT and self.user_state:
            space_mappings_prop = self.user_state.create_property("GenieSpaceMappingsProperty")
            await space_mappings_prop.delete(turn_context)
        else:
            await self.database.clear_user_space_mappings(user_id)

    async def _refresh_and_send_spaces(self, turn_context: TurnContext, user_id: str, creds_kwargs: dict, workspace_host: str = None):
        """Helper to fetch space list and send as activity, wrapping in typing indicator.
        
        Args:
            turn_context (TurnContext): The context object for the current turn.
            user_id (str): The Microsoft Teams user ID.
            creds_kwargs (dict): Credentials to pass to the list spaces handler.
            workspace_host (str): Optional workspace host to list spaces from.
        """
        list_spaces_kwargs = {
            "turn_context": turn_context,
            "user_id": user_id,
            "workspace_host": workspace_host,
            **creds_kwargs,
        }
        response = await BotUtilities.keep_typing_while(
            turn_context,
            self.genie_list_handler.handle_list_spaces,
            **list_spaces_kwargs,
        )
        await turn_context.send_activity(response)

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

        elif action == "select_workspace":
            workspace_name = action_data.get("workspace_name")
            workspace_host = action_data.get("workspace_host") or action_data.get("manual_workspace_host")
            
            if not workspace_host:
                await turn_context.send_activity("❌ Invalid workspace host. Please try again.")
                return
                
            logger.debug(f"Action 'select_workspace': {workspace_name}, host={workspace_host}")
            
            selection_dict = await self._get_user_selection_dict(turn_context, user_id)
            selection_dict["workspace_host"] = workspace_host
            selection_dict["space_id"] = ""
            selection_dict["space_name"] = ""
            selection_dict["conversation_id"] = ""
            await self._set_user_selection_dict(turn_context, user_id, selection_dict)
                
            await turn_context.delete_activity(turn_context.activity.reply_to_id)
            await turn_context.send_activity(f"✅ Selected workspace: **{workspace_name or workspace_host}**.")
            
            turn_context.activity.text = "list genie spaces"
            turn_context.activity.value = None
            await self.process_message(turn_context)

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
                    f"User {user_id} successfully selected group: {selected_group.group_name or selected_group.group_id}"
                )

                # Clear cached spaces to ensure we fetch for the new scope
                await self._clear_space_cache(turn_context, user_id)

                creds_kwargs = {
                    "client_id": selected_group.databricks_client_id,
                    "client_secret": selected_group.databricks_client_secret,
                    "scope_name": selected_group.group_name or selected_group.group_id,
                }
                await self._refresh_and_send_spaces(turn_context, user_id, creds_kwargs)
            else:
                logger.warning(
                    f"Invalid group selection. Index: {group_index}, User groups len: {len(user_groups) if user_groups else 0}"
                )
                await turn_context.send_activity("❌ Invalid group selection.")

        elif action == "refresh_spaces":
            logger.debug("Handling 'refresh_spaces' action.")
            await turn_context.delete_activity(turn_context.activity.reply_to_id)
            await self._clear_space_cache(turn_context, user_id)

            creds_kwargs = await self.credential_resolver.get_databricks_credentials_kwargs(
                turn_context, send_prompt=False
            )
            if creds_kwargs is None:
                return

            selection_dict = await self._get_user_selection_dict(turn_context, user_id)
            workspace_host = selection_dict.get("workspace_host")

            await self._refresh_and_send_spaces(turn_context, user_id, creds_kwargs, workspace_host)

        elif action == "retry_spaces":
            creds_kwargs = await self.credential_resolver.get_databricks_credentials_kwargs(
                turn_context, send_prompt=False
            )
            if creds_kwargs is None:
                return
            
            selection_dict = await self._get_user_selection_dict(turn_context, user_id)
            workspace_host = selection_dict.get("workspace_host")
                    
            await self._refresh_and_send_spaces(turn_context, user_id, creds_kwargs, workspace_host)

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
        selection_dict = await self._get_user_selection_dict(turn_context, user_id)
        selection_dict["space_id"] = space_id
        selection_dict["space_name"] = space_name
        selection_dict["conversation_id"] = None
        await self._set_user_selection_dict(turn_context, user_id, selection_dict)
        logger.debug("User selection updated.")
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
        creds_kwargs = await self.credential_resolver.get_databricks_credentials_kwargs(
            turn_context, send_prompt=True
        )
        if creds_kwargs is None:
            return

        start_time = datetime.now(timezone.utc)
        user_name = getattr(turn_context.activity.from_property, "name", None)
        try:
            members = await TeamsInfo.get_member(turn_context, user_id)
            user_email = members.email
        except Exception:
            user_email = None

        scope_name = creds_kwargs.get("scope_name")
        sql_query = None
        exception_str = None

        try:
            client_id = creds_kwargs.get("client_id")
            client_secret = creds_kwargs.get("client_secret")
            token = creds_kwargs.get("token")

            if not client_id and not client_secret and not token:
                logger.debug("Using global Databricks credentials to initialize Genie.")
                genie = Genie(workspace_host=getattr(user_selection, "workspace_host", None))
            else:
                genie = Genie(
                    client_id=client_id, client_secret=client_secret, token=token, workspace_host=getattr(user_selection, "workspace_host", None)
                )
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
                exception_str = response_data["error"]
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
                selection_dict = await self._get_user_selection_dict(turn_context, user_id)
                selection_dict["conversation_id"] = new_conversation_id
                await self._set_user_selection_dict(turn_context, user_id, selection_dict)
                user_selection.conversation_id = new_conversation_id

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
                data_dict = genie_response.get("data", {})
                if not isinstance(data_dict, dict):
                    data_dict = {}

                data_array = data_dict.get("data_array", [])
                row_count = data_dict.get("row_count", 0)
                
                if row_count > 0 and len(data_array) > 0:
                    # Generate summary
                    try:
                        if os.environ.get("GET_AI_INSIGHTS", "true").lower() == "true":
                            logger.debug("Generating summary from data via llm_summarizer.")

                            summary_result = await asyncio.to_thread(
                                self.llm_summarizer.summarize,
                                genie_response["columns"]["columns"],
                                data_array,
                                question,
                                creds_kwargs.get("client_id"),
                                creds_kwargs.get("client_secret"),
                            )

                            if isinstance(summary_result, dict):
                                summary_text = summary_result.get("text", "")
                                chart_type = summary_result.get("chart")
                            else:
                                summary_text = str(summary_result)
                                chart_type = None

                            summary_card.add_text(summary_text)
                        else:
                            logger.debug("AI insights are disabled via GET_AI_INSIGHTS.")

                        # Generate chart card via dedicated LLM agent when charts are enabled
                        if os.environ.get("ENABLE_CHARTS", "inactive").lower() == "active":
                            try:
                                logger.debug(
                                    "Requesting chart Adaptive Card from AdaptiveCardChartGenerator."
                                )
                                # Slice to top 15 rows for readability; LLM handles schema selection
                                chart_data_slice = data_array[:15]
                                chart_card = await asyncio.to_thread(
                                    self.chart_card_generator.generate_chart_card,
                                    genie_response["columns"]["columns"],
                                    chart_data_slice,
                                    creds_kwargs.get("client_id"),
                                    creds_kwargs.get("client_secret"),
                                )
                                if chart_card:
                                    logger.debug(
                                        f"Chart card generated. Chart type: "
                                        f"{chart_card.get('body', [{}])[0].get('type', 'unknown')}"
                                    )
                            except Exception as ce:
                                logger.error(
                                    f"Failed to generate chart card: {ce}", exc_info=True
                                )
                                chart_card = None
                    except Exception as e:
                        logger.error(f"Failed to generate summary: {e}", exc_info=True)
                else:
                    logger.info("No results returned by Genie (row_count is 0 or missing).")
                    summary_card.add_text("No results were found for your query.")

                logger.debug(f"Data row count: {row_count}")

                if row_count < 100:
                    logger.debug("Row count < 100, creating table Adaptive Card.")
                    table_card = AdaptiveCardTemplate()
                    # Pass a dict that guarantees 'data_array' exists to avoid KeyError downstream
                    table_card.add_query_result_table(
                        genie_response["columns"], {"data_array": data_array}
                    )
                else:
                    # For large datasets, we add a button to download the results as CSV/Excel
                    # Generate Excel in memory to avoid disk I/O
                    logger.debug("Row count >= 100, preparing Excel file for upload.")
                    sending_excel = True

                    # Create the dataframe
                    logger.debug("Creating Polars DataFrame.")

                    filename, excel_buffer = ExcelGenerator.generate_excel_from_data(
                        data_array, genie_response["columns"]["columns"]
                    )

            if "query" in genie_response:
                logger.debug("Adding SQL query to table Adaptive Card.")
                if table_card is None:
                    table_card = AdaptiveCardTemplate()
                table_card.add_sql_code(genie_response["query"])
                sql_query = genie_response["query"]

            logger.debug("Sending Summary Adaptive Card response to user.")
            summary_attachment = CardFactory.adaptive_card(
                summary_card.get_adaptive_card()
            )
            await turn_context.send_activity(
                MessageFactory.attachment(summary_attachment)
            )

            if chart_card:
                logger.debug("Sending Chart Adaptive Card response to user.")
                # chart_card is a raw dict produced by AdaptiveCardChartGenerator
                chart_attachment = CardFactory.adaptive_card(chart_card)
                await turn_context.send_activity(
                    MessageFactory.attachment(chart_attachment)
                )

            if table_card:
                logger.debug("Sending Table Adaptive Card response to user.")
                table_attachment = CardFactory.adaptive_card(
                    table_card.get_adaptive_card()
                )
                await turn_context.send_activity(
                    MessageFactory.attachment(table_attachment)
                )

            if sending_excel:
                logger.info(f"Sending Excel file card for {filename}")
                await self.file_card_handler.send_file_card(
                    turn_context,
                    filename=filename,
                    file_size=excel_buffer.getbuffer().nbytes,
                    file_bytes=excel_buffer,
                )
        except Exception as e:
            exception_str = str(e)
            raise e
        finally:
            end_time = datetime.now(timezone.utc)
            try:
                # If U2M is used, we don't need to log locally because Databricks Query History logs the user's identity natively.
                is_u2m = bool(creds_kwargs.get("token"))
                if not is_u2m:
                    await self.database.add_query_log(
                        user_id=user_id,
                        question=question,
                        user_name=user_name,
                        user_email=user_email,
                        scope_name=scope_name,
                        workspace_host=getattr(user_selection, "workspace_host", None),
                        space_name=user_selection.space_name,
                        space_id=user_selection.space_id,
                        conversation_id=user_selection.conversation_id,
                        sql_query=sql_query,
                        start_time=start_time,
                        end_time=end_time,
                        exception=exception_str,
                    )
                else:
                    logger.debug("Skipping GenieAuditLog insertion because U2M OAuth natively logs user identity in Databricks.")
            except Exception as db_err:
                logger.error(f"Failed to save query log: {db_err}", exc_info=True)

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
            group_name = group.group_name or getattr(
                group, "name", f"Scope {index + 1}"
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

                if fuzz.partial_ratio(text, "list workspaces") >= 80:
                    logger.debug("Text matches 'list workspaces' command.")
                    creds_kwargs = await self.credential_resolver.get_databricks_credentials_kwargs(
                        turn_context, send_prompt=True, force_prompt=True
                    )
                    if creds_kwargs is None:
                        return
                    from handlers.workspace_list_handler import WorkspaceListHandler
                    handler = WorkspaceListHandler(self.database, self.user_state, self.conversation_state)
                    await handler.handle_list_workspaces(
                        turn_context, 
                        user_id, 
                        account_host=CONFIG.DATABRICKS_ACCOUNT_HOST,
                        account_id=CONFIG.DATABRICKS_ACCOUNT_ID,
                        **creds_kwargs
                    )
                elif fuzz.partial_ratio(text, COMMAND_LIST_SPACES) >= 70:
                    # Use fuzzy matching to allow for minor typos
                    logger.debug(
                        f"Text matches '{COMMAND_LIST_SPACES}' command. Fuzzy ratio: {fuzz.partial_ratio(text, COMMAND_LIST_SPACES)}"
                    )
                    creds_kwargs = await self.credential_resolver.get_databricks_credentials_kwargs(
                        turn_context, send_prompt=True, force_prompt=True
                    )
                    if creds_kwargs is None:
                        return
                    list_spaces_kwargs = {
                        "turn_context": turn_context,
                        "user_id": user_id,
                        **creds_kwargs,
                    }

                    # Always clear the cache on explicit user request so newly added
                    # Genie spaces are visible immediately without a manual refresh.
                    await self._clear_space_cache(turn_context, user_id)

                    selection_dict = await self._get_user_selection_dict(turn_context, user_id)
                    workspace_host = selection_dict.get("workspace_host")

                    logger.debug("Calling GenieListHandler to fetch spaces.")
                    await self._refresh_and_send_spaces(turn_context, user_id, creds_kwargs, workspace_host)
                else:
                    # Check if user has a space selected
                    logger.debug("Checking if user has an active Genie space selected.")
                    selection_dict = await self._get_user_selection_dict(turn_context, user_id)
                    user_selection = UserSelection(**selection_dict) if selection_dict else None
                    if user_selection and user_selection.space_id:
                        logger.info(
                            f"User has selected scope {user_selection.space_id}. Delegating to handle_genie_question."
                        )
                        await self.handle_genie_question(
                            turn_context, user_id, text, user_selection
                        )
                    else:
                        logger.info(
                            "User requested a question but has no scope selected."
                        )
                        await turn_context.send_activity(
                            "Please select a Genie space first by typing 'list genie spaces'."
                        )
        except Exception as e:
            logger.error(f"Unexpected error in process_message: {e}", exc_info=True)
            await turn_context.send_activity(
                "❌ I'm sorry, I encountered an unexpected error while processing your request. Please try again later."
            )
