"""
Module for handling file upload to teams bot.
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
    """
    A handler class that handles file upload and download in teams.
    """

    async def _file_upload_failed(self, turn_context: TurnContext, error: str):
        reply = turn_context.activity.create_reply(
            text=f"<b>File upload failed.</b> Error: <pre>{error}</pre>",
        )
        await turn_context.send_activity(reply)

    async def _file_upload_complete(
        self,
        turn_context: TurnContext,
        file_consent_card_response: dict,
    ):
        """
        The file was uploaded, so display a FileInfoCard so the user can view the
        file in Teams.
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
