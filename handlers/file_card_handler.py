"""Module for handling file uploads and downloads in the Teams bot.

This module provides the `FileCardHandler` which builds the UI and logic for
sending and receiving file consent cards to export large query results as Excel files.
"""

import base64
from datetime import datetime
from io import BytesIO

from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.activity import (
    Attachment,
    ActivityTypes,
    ChannelAccount,
    ConversationAccount,
    Activity,
)
from microsoft_agents.activity.teams import (
    FileConsentCard,
    FileConsentCardResponse,
    FileInfoCard,
)


class FileCardHandler:
    """A handler class that manages file uploads and downloads in Microsoft Teams.

    It creates and processes FileConsentCards, allowing the bot to send large
    Databricks SQL query results as Excel file attachments directly in the chat.
    """

    async def _file_upload_failed(self, turn_context: TurnContext, error: str):
        """Sends an error message to the user if a file upload fails.

        Args:
            turn_context (TurnContext): The context object for this turn.
            error (str): The error message describing the failure.
        """
        reply = turn_context.activity.create_reply(
            text=f"<b>File upload failed.</b> Error: <pre>{error}</pre>",
        )
        await turn_context.send_activity(reply)

    async def _file_upload_complete(
        self,
        turn_context: TurnContext,
        file_consent_card_response: dict,
    ):
        """Sends a FileInfoCard to the user after a successful file upload.

        This allows the user to click and view/download the file within the Teams client.

        Args:
            turn_context (TurnContext): The context object for this turn.
            file_consent_card_response (dict): The upload payload returned by Teams.
        """

        upload_info = file_consent_card_response.get("uploadInfo")

        download_card = FileInfoCard(
            unique_id=upload_info.get("uniqueId"),
            file_type=upload_info.get("fileType"),
            etag=upload_info.get("etag", ""),
        )

        as_attachment = Attachment(
            # content=download_card.serialize(),
            content=download_card,
            # content_type=ContentType.FILE_INFO_CARD,
            content_type="application/vnd.microsoft.teams.card.file.info",
            name=upload_info.get("name"),
            content_url=upload_info.get("contentUrl"),
        )

        reply_activity = turn_context.activity.create_reply(
            text="<b>File uploaded.</b> Your file is ready to download"
        )
        reply_activity.attachments = [as_attachment]

        await turn_context.send_activity(reply_activity)

    async def send_file_card(
        self,
        turn_context: TurnContext,
        filename: str,
        file_size: int,
        file_bytes: BytesIO,
    ):
        """Generates and sends a FileConsentCard to prompt the user for download permission.

        Args:
            turn_context (TurnContext): The context object for this turn.
            filename (str): The name of the file to be sent (e.g., 'results.xlsx').
            file_size (int): The size of the file in bytes.
            file_bytes (BytesIO): The in-memory buffer containing the file data.
        """
        base_64_encoded_bytes = base64.b64encode(file_bytes.getvalue()).decode("utf-8")
        consent_context = {"filename": filename, "file_bytes": base_64_encoded_bytes}

        file_card = FileConsentCard(
            description="I want to send the result of your query as Excel flile.",
            size_in_bytes=file_size,
            accept_context=consent_context,
            decline_context=consent_context,
        )

        as_attachment = Attachment(
            # content=file_card.serialize(),
            content=file_card,
            # content_type=ContentType.FILE_CONSENT_CARD,
            content_type="application/vnd.microsoft.teams.card.file.consent",
            name=filename,
        )

        reply_activity = turn_context.activity.create_reply()
        reply_activity.attachments = [as_attachment]

        await turn_context.send_activity(reply_activity)
