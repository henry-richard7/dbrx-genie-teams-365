"""
S3 Storage implementation for Microsoft Agents SDK.

This module provides the S3Storage class which implements the Storage protocol
for persisting bot state in AWS S3 or compatible object storage services.
"""
import asyncio
import json
import logging
import os
from threading import Lock
from typing import TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from microsoft_agents.hosting.core import Storage
from microsoft_agents.hosting.core.storage.store_item import StoreItem
from microsoft_agents.hosting.core.storage._type_aliases import JSON

logger = logging.getLogger(__name__)

StoreItemT = TypeVar("StoreItemT", bound=StoreItem)


class S3Storage(Storage):
    """
    S3-compatible storage for Microsoft Agents SDK (microsoft_agents.hosting.core).

    Compatible with: AWS S3, MinIO, Cloudflare R2, Backblaze B2, DigitalOcean Spaces, etc.

    Usage:
        storage = S3Storage(
            bucket_name="my-agent-state",
            endpoint_url="http://localhost:9000",   # omit for real AWS S3
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
            region_name="us-east-1",
            key_prefix="agent-state/",              # optional namespace prefix
            disable_signing=False,                  # True for path-style & non-chunked signing
        )
    """

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str = "us-east-1",
        key_prefix: str = "",
        create_bucket_if_not_exists: bool = True,
    ):
        """Initializes the S3Storage instance.
        
        Args:
            bucket_name (str): The name of the S3 bucket.
            endpoint_url (str | None): Custom endpoint URL (e.g. for MinIO).
            aws_access_key_id (str | None): AWS access key ID.
            aws_secret_access_key (str | None): AWS secret access key.
            region_name (str): AWS region name. Defaults to "us-east-1".
            key_prefix (str): Prefix to prepend to all keys. Defaults to "".
            create_bucket_if_not_exists (bool): If True, attempts to create the bucket if missing.
            disable_signing (bool | None): If True, applies path-style addressing and disables payload
                chunked signing (s3v4). If None, reads from S3_DISABLE_SIGNING environment variable.
        """
        self._bucket = bucket_name
        self._prefix = key_prefix
        self._lock = Lock()

        disable_signing = os.getenv("S3_DISABLE_SIGNING", "false").lower() in ("true", "1", "yes")

        client_kwargs = {
            "endpoint_url": endpoint_url,
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
            "region_name": region_name,
        }

        # Only apply path-style and non-chunked signing if requested in .env
        if disable_signing:
            client_kwargs["config"] = Config(
                signature_version="s3v4",
                s3={
                    "addressing_style": "path",
                    "payload_signing_enabled": False
                }
            )

        self._s3 = boto3.client("s3", **client_kwargs)

        if create_bucket_if_not_exists:
            self._ensure_bucket()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_bucket(self) -> None:
        """Ensures the target S3 bucket exists, creating it if necessary."""
        try:
            self._s3.head_bucket(Bucket=self._bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                self._s3.create_bucket(Bucket=self._bucket)
                logger.info("S3Storage: created bucket '%s'", self._bucket)
            else:
                raise

    def _s3_key(self, key: str) -> str:
        """Namespace the storage key under the optional prefix."""
        import urllib.parse
        safe_key = urllib.parse.quote(key, safe='/-')
        return f"{self._prefix}{safe_key}"

    def _get_object(self, key: str) -> JSON | None:
        """Retrieves an object from S3 by key.
        
        Args:
            key (str): The storage key.
            
        Returns:
            JSON | None: The parsed JSON object, or None if the key doesn't exist.
        """
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=self._s3_key(key))
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise

    def _put_object(self, key: str, data: JSON) -> None:
        """Writes a JSON object to S3.
        
        Args:
            key (str): The storage key.
            data (JSON): The data to serialize and store.
        """
        self._s3.put_object(
            Bucket=self._bucket,
            Key=self._s3_key(key),
            Body=json.dumps(data, default=str).encode("utf-8"),
            ContentType="application/json",
        )

    def _delete_object(self, key: str) -> None:
        """Deletes an object from S3.
        
        Args:
            key (str): The storage key to delete.
        """
        self._s3.delete_object(Bucket=self._bucket, Key=self._s3_key(key))

    # ------------------------------------------------------------------
    # Storage protocol implementation
    # ------------------------------------------------------------------

    async def read(
        self, keys: list[str], *, target_cls: type[StoreItemT] = None, **kwargs
    ) -> dict[str, StoreItemT]:
        """Reads multiple keys from S3 storage asynchronously.
        
        Args:
            keys (list[str]): The list of keys to read.
            target_cls (type[StoreItemT], optional): The class type to deserialize into.
            
        Returns:
            dict[str, StoreItemT]: A dictionary mapping keys to their retrieved objects.
        """
        if not keys:
            raise ValueError("S3Storage.read(): keys are required.")

        loop = asyncio.get_event_loop()
        result: dict[str, StoreItemT] = {}

        def _sync_read():
            with self._lock:
                for key in keys:
                    if not key:
                        raise ValueError("S3Storage.read(): key cannot be empty.")
                    data = self._get_object(key)
                    if data is not None:
                        if target_cls:
                            try:
                                result[key] = target_cls.from_json_to_store_item(data)
                            except AttributeError as e:
                                raise TypeError(
                                    f"S3Storage.read(): could not deserialize '{key}' "
                                    f"into {target_cls}. Error: {e}"
                                )
                        else:
                            result[key] = data

        await loop.run_in_executor(None, _sync_read)
        return result

    async def write(self, changes: dict[str, StoreItem]) -> None:
        """Writes multiple items to S3 storage asynchronously.
        
        Args:
            changes (dict[str, StoreItem]): A dictionary of items to store, keyed by storage key.
        """
        if not changes:
            raise ValueError("S3Storage.write(): changes cannot be None.")

        loop = asyncio.get_event_loop()

        def _sync_write():
            with self._lock:
                for key, item in changes.items():
                    if not key:
                        raise ValueError("S3Storage.write(): key cannot be empty.")
                    if hasattr(item, "store_item_to_json"):
                        self._put_object(key, item.store_item_to_json())
                    else:
                        self._put_object(key, item)

        await loop.run_in_executor(None, _sync_write)

    async def delete(self, keys: list[str]) -> None:
        """Deletes multiple keys from S3 storage asynchronously.
        
        Args:
            keys (list[str]): The list of keys to delete.
        """
        if not keys:
            raise ValueError("S3Storage.delete(): keys are required.")

        loop = asyncio.get_event_loop()

        def _sync_delete():
            with self._lock:
                for key in keys:
                    if not key:
                        raise ValueError("S3Storage.delete(): key cannot be empty.")
                    self._delete_object(key)

        await loop.run_in_executor(None, _sync_delete)
