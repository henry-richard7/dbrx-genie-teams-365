from typing import Dict, List, Optional, Tuple, Any
import asyncio
from os import environ
import logging

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import GenieAPI
from dotenv import load_dotenv


from utils.sync_lru_cache_async import sync_lru_cache_async

load_dotenv()

logger = logging.getLogger(__name__)


class Genie:
    """Wrapper class for interacting with the Databricks Genie API.

    Handles authentication, workspace client initialization, space fetching,
    and asynchronous querying to the Databricks Genie service.

    Attributes:
        workspace_client (WorkspaceClient): The Databricks SDK workspace client.
        genie_api (GenieAPI): The Databricks Genie API client.
    """

    def __init__(self, client_id: str = None, client_secret: str = None):
        """Initializes the Genie wrapper.

        Args:
            client_id (str, optional): Overrides the default OAuth client ID.
            client_secret (str, optional): Overrides the default OAuth client secret.
        """
        self._databricks_host = environ.get("DATABRICKS_HOST")
        self._databricks_token = environ.get("DATABRICKS_TOKEN")
        self._genie_api = None
        self._workspace_client = None
        self._client_id = client_id or environ.get("DATABRICKS_CLIENT_ID")
        self._client_secret = client_secret or environ.get("DATABRICKS_CLIENT_SECRET")

    @property
    def workspace_client(self) -> WorkspaceClient:
        """Lazy initialization of the Databricks Workspace client.

        Returns:
            WorkspaceClient: The authenticated Databricks WorkspaceClient.
        """
        if self._workspace_client is None:
            if self._databricks_token:
                self._workspace_client = WorkspaceClient(
                    host=self._databricks_host, token=self._databricks_token
                )
            else:
                self._workspace_client = WorkspaceClient(
                    host=self._databricks_host,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                )
        return self._workspace_client

    @property
    def genie_api(self) -> GenieAPI:
        """Lazy initialization of the Databricks Genie API.

        Returns:
            GenieAPI: The configured Genie API interface.
        """
        if self._genie_api is None:
            self._genie_api = GenieAPI(self.workspace_client.api_client)
        return self._genie_api

    async def ask_genie(
        self, question: str, space_id: str, conversation_id: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """Submits a natural language query to a Databricks Genie space.

        Handles both creating new conversations and appending to existing ones.
        Waits for the Genie engine to process the query and retrieves the results.

        Args:
            question (str): The natural language query to ask.
            space_id (str): The unique ID of the Genie space to query.
            conversation_id (Optional[str]): The ID of an existing conversation. Defaults to None.

        Returns:
            Tuple[dict, Optional[str]]: A tuple containing the response dictionary and the conversation ID.
        """
        try:
            loop = asyncio.get_running_loop()

            # Handle conversation continuation vs new conversation
            if conversation_id is not None:
                # Continue existing conversation
                initial_message = await loop.run_in_executor(
                    None,
                    self.genie_api.create_message_and_wait,
                    space_id,
                    conversation_id,
                    question,
                )
            else:
                # Start new conversation
                initial_message = await loop.run_in_executor(
                    None, self.genie_api.start_conversation_and_wait, space_id, question
                )
                conversation_id = initial_message.conversation_id

            # Process query results if available
            query_result = await self._get_query_result(space_id, initial_message, loop)

            # Get message content
            message_content = await loop.run_in_executor(
                None,
                self.genie_api.get_message,
                space_id,
                initial_message.conversation_id,
                initial_message.message_id,
            )

            # Format response based on content type
            response_data = await self._format_response(
                query_result, message_content, loop
            )

            return {"response": response_data, "conversation_id": conversation_id}

        except Exception as e:
            logger.error("Failed in Asking question Genie", exc_info=True)
            return {"error": "An error occurred while processing your request."}

    async def _get_query_result(
        self, space_id: str, initial_message: Any, loop
    ) -> Optional[Any]:
        """Fetches the query execution results from an executed Genie message.

        Args:
            space_id (str): The Genie space ID.
            initial_message (Any): The initial message response object.
            loop (asyncio.AbstractEventLoop): The running asyncio event loop.

        Returns:
            Optional[Any]: The query result object, or None if unavailable.
        """
        if initial_message.query_result is None or not initial_message.attachments:
            return None

        try:
            return await loop.run_in_executor(
                None,
                self.genie_api.get_message_attachment_query_result,
                space_id,
                initial_message.conversation_id,
                initial_message.message_id,
                initial_message.attachments[0].attachment_id,
            )
        except Exception as e:
            logger.warning(f"Failed to get query result: {str(e)}", exc_info=True)
            return None

    async def _format_response(
        self, query_result: Any, message_content: Any, loop
    ) -> Dict[str, Any]:
        """Formats the Genie response into a structured dictionary.

        Args:
            query_result (Any): The execution query results from Databricks SQL.
            message_content (Any): The message content from the Genie API.
            loop (asyncio.AbstractEventLoop): The running asyncio event loop.

        Returns:
            Dict[str, Any]: A formatted dictionary containing either SQL data or text response.
        """
        if query_result and query_result.statement_response:
            return await self._format_query_response(
                query_result, message_content, loop
            )

        # Handle text attachments
        if message_content.attachments:
            for attachment in message_content.attachments:
                if attachment.text and attachment.text.content:
                    return {"message": attachment.text.content}

        # Fallback to message content
        return {"message": message_content.content or "No response available"}

    async def _format_query_response(
        self, query_result: Any, message_content: Any, loop
    ) -> Dict[str, Any]:
        """Formats a SQL query result response.

        Args:
            query_result (Any): The execution query results.
            message_content (Any): The message content payload.
            loop (asyncio.AbstractEventLoop): The running asyncio event loop.

        Returns:
            Dict[str, Any]: A dictionary containing column schema, data array, and query context.
        """
        try:
            results = await loop.run_in_executor(
                None,
                self.workspace_client.statement_execution.get_statement,
                query_result.statement_response.statement_id,
            )

            query_description = self._extract_query_description(message_content)

            return {
                "columns": results.manifest.schema.as_dict(),
                "data": results.result.as_dict(),
                "query_description": query_description.get("query_description", ""),
                "query": query_description.get("query", ""),
            }
        except Exception as e:
            logger.error(f"Error formatting query response: {str(e)}")
            return {"message": "Query executed but results could not be formatted"}

    @staticmethod
    def _extract_query_description(message_content: Any) -> dict:
        """Extracts the underlying SQL query and description from a Genie message.

        Args:
            message_content (Any): The message content from the Genie API.

        Returns:
            dict: A dictionary containing 'query_description' and 'query'.
        """
        for attachment in message_content.attachments:
            if attachment.query and attachment.query.description:
                return {
                    "query_description": attachment.query.description,
                    "query": attachment.query.query,
                }
        return {}

    @sync_lru_cache_async(maxsize=1)
    async def get_spaces(self) -> List[Any]:
        """Retrieves a list of all accessible Genie spaces.

        This method is cached to prevent redundant API calls across multiple interactions.

        Returns:
            List[Any]: A list of available Genie space objects.
        """
        try:
            loop = asyncio.get_running_loop()
            spaces_response = await loop.run_in_executor(
                None, self.genie_api.list_spaces
            )
            return spaces_response.spaces or []
        except Exception as e:
            logger.error(f"Error getting spaces: {str(e)}", exc_info=True)
            return []
