"""Module for handling file uploads and downloads in the Teams bot.

This module provides the `FileCardHandler` which builds the UI and logic for
sending and receiving file consent cards to export large query results as Excel files.
"""

import logging
from datetime import datetime
from io import BytesIO
from uuid import uuid4
import base64
import time

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


from pathlib import Path
import tempfile

from config import DefaultConfig

logger = logging.getLogger(__name__)
CONFIG = DefaultConfig()


class FileCacheStoreItem:
    """Wrapper to satisfy the Bot Framework StoreItem interface."""
    def __init__(self, data: dict = None, **kwargs):
        self.data = data or kwargs

    def store_item_to_json(self) -> dict:
        return self.data
        
    @staticmethod
    def from_json_to_store_item(json_data: dict) -> "FileCacheStoreItem":
        return FileCacheStoreItem(json_data)



class FileCardHandler:
    """A handler class that manages file uploads and downloads in Microsoft Teams.

    It creates and processes FileConsentCards, allowing the bot to send large
    Databricks SQL query results as Excel file attachments directly in the chat.

    When distributed storage (USE_CONTEXT) is disabled, file bytes are saved to a
    dedicated temp directory on disk keyed by UUID, preventing memory accumulation,
    and are immediately deleted once the user accepts the upload or declines.
    """

    _TEMP_DIR = Path(tempfile.gettempdir()) / "teams_genie_bot_files"
    _FILE_TTL_SECONDS = 3600  # 1 hour

    def __init__(self, storage=None):
        """Initializes the FileCardHandler.
        
        Args:
            storage: The Bot Framework Storage instance (e.g. S3Storage) used for distributed caching.
        """
        self.storage = storage

    @classmethod
    def _get_temp_file_path(cls, file_id: str) -> Path:
        """Returns the filesystem Path for a given file_id."""
        return cls._TEMP_DIR / f"pending_file_{file_id}.bin"

    @classmethod
    def _cleanup_expired_files(cls):
        """Cleans up expired temporary files older than _FILE_TTL_SECONDS."""
        if not cls._TEMP_DIR.exists():
            return
        current_time = time.time()
        try:
            for f in cls._TEMP_DIR.glob("pending_file_*.bin"):
                try:
                    if current_time - f.stat().st_mtime > cls._FILE_TTL_SECONDS:
                        f.unlink(missing_ok=True)
                except OSError:
                    pass
        except Exception as e:
            logger.warning(f"FileCardHandler: Error during expired temp file cleanup: {e}")

    async def _save_file_bytes(self, file_id: str, file_bytes: bytes):
        """Saves file bytes either to Bot Framework Storage (if USE_CONTEXT is true) or to temp disk."""
        if CONFIG.USE_CONTEXT and self.storage:
            encoded = base64.b64encode(file_bytes).decode('utf-8')
            await self.storage.write({
                f"file_{file_id}": FileCacheStoreItem({
                    'bytes': encoded,
                    'timestamp': time.time()
                })
            })
        else:
            self._cleanup_expired_files()
            try:
                self._TEMP_DIR.mkdir(parents=True, exist_ok=True)
                temp_path = self._get_temp_file_path(file_id)
                temp_path.write_bytes(file_bytes)
                logger.debug(f"Saved pending file '{file_id}' to temp file: {temp_path}")
            except Exception as e:
                logger.error(f"Failed to write temp file for file_id '{file_id}': {e}", exc_info=True)

    async def _get_and_delete_file_bytes(self, file_id: str) -> bytes | None:
        """Retrieves file bytes from storage/temp disk and immediately deletes them to free space."""
        if CONFIG.USE_CONTEXT and self.storage:
            data = await self.storage.read([f"file_{file_id}"], target_cls=FileCacheStoreItem)
            if f"file_{file_id}" in data:
                file_data = data[f"file_{file_id}"]
                if hasattr(file_data, "store_item_to_json"):
                    encoded = file_data.store_item_to_json().get('bytes')
                elif isinstance(file_data, dict):
                    encoded = file_data.get('bytes')
                elif hasattr(file_data, "data"):
                    encoded = file_data.data.get('bytes')
                else:
                    encoded = None
                    
                await self.storage.delete([f"file_{file_id}"])
                return base64.b64decode(encoded) if encoded else None
            return None
        else:
            temp_path = self._get_temp_file_path(file_id)
            if temp_path.exists():
                try:
                    data = temp_path.read_bytes()
                    temp_path.unlink(missing_ok=True)
                    logger.debug(f"Retrieved and removed temp file for download: {temp_path}")
                    return data
                except Exception as e:
                    logger.error(f"Failed to read/delete temp file {temp_path}: {e}", exc_info=True)
                    return None
            return None

    async def _delete_file_bytes(self, file_id: str):
        """Deletes file bytes from storage or temp disk."""
        if CONFIG.USE_CONTEXT and self.storage:
            await self.storage.delete([f"file_{file_id}"])
        else:
            temp_path = self._get_temp_file_path(file_id)
            temp_path.unlink(missing_ok=True)
            logger.debug(f"Deleted temp file for file_id '{file_id}': {temp_path}")

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
            content=download_card,
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

        The file bytes are stored in the class-level :attr:`_pending_files` cache under
        a UUID key. Only the UUID is sent in the card context, keeping the payload
        small and avoiding ``413 Request Entity Too Large`` errors from Teams.

        Args:
            turn_context (TurnContext): The context object for this turn.
            filename (str): The name of the file to be sent (e.g., 'results.xlsx').
            file_size (int): The size of the file in bytes.
            file_bytes (BytesIO): The in-memory buffer containing the file data.
        """
        import time
        file_id = str(uuid4())
        
        # Cache raw bytes — retrieved on accept, discarded on accept/decline
        await self._save_file_bytes(file_id, file_bytes.getvalue())

        # Lightweight context — only a UUID reference, no encoded payload
        consent_context = {"filename": filename, "file_id": file_id}

        file_card = FileConsentCard(
            description="I want to send the result of your query as an Excel file.",
            size_in_bytes=file_size,
            accept_context=consent_context,
            decline_context=consent_context,
        )

        as_attachment = Attachment(
            content=file_card,
            content_type="application/vnd.microsoft.teams.card.file.consent",
            name=filename,
        )

        reply_activity = turn_context.activity.create_reply()
        reply_activity.attachments = [as_attachment]

        await turn_context.send_activity(reply_activity)
