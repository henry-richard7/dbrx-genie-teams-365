import os
from .db_models import UserSelection, GenieSpace, SecurityGroupMapping, GenieAuditLog
from sqlmodel import select, delete, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Database:
    """A wrapper class for SQLite database interactions using SQLModel and async SQLAlchemy.

    Provides methods to manage database tables, read/write user configuration,
    Genie space mappings, and security group resolution for multi-tenant access.
    """

    def __init__(self, db_url: str = None):
        """Initializes the Database instance and async engine.

        Args:
            db_url (str, optional): The database connection URL. If not provided, it reads from the environment variable 'DATABASE_URL', defaulting to the local SQLite DB.
        """
        if db_url is None:
            db_url = os.environ.get(
                "DATABASE_URL", "sqlite+aiosqlite:///teams_genie_bot.db"
            )
        logger.debug(f"Initializing Database with URL: {db_url}")
        self.engine = create_async_engine(db_url)

    async def create_tables(self):
        """Creates all database tables defined by SQLModel if they do not exist."""
        logger.info("Creating database tables if they do not exist.")
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.debug("Database tables created successfully.")

    async def close(self):
        """Disposes of the database engine to close connections cleanly."""
        logger.info("Closing database engine.")
        await self.engine.dispose()
        logger.debug("Database engine closed.")

    async def get_user_space_mappings(self, user_id: str) -> List[GenieSpace]:
        """Retrieves all Genie Space mappings associated with a specific user.

        Args:
            user_id (str): The Microsoft Teams user ID.

        Returns:
            List[GenieSpace]: A list of mapped GenieSpace instances.
        """
        logger.debug(f"Fetching space mappings for user: {user_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(GenieSpace).where(GenieSpace.user_id == user_id)
            results = await session.exec(statement)
            mappings = results.all()
            logger.debug(f"Found {len(mappings)} mappings for user: {user_id}")
            return mappings

    async def add_user_space_mapping(
        self, user_id: str, space_id: str, space_name: str, description: str = None
    ) -> GenieSpace:
        """Adds a new Genie Space mapping for a user.

        Args:
            user_id (str): The Microsoft Teams user ID.
            space_id (str): The Databricks Genie Space ID.
            space_name (str): The human-readable name of the space.
            description (str, optional): A description of the space. Defaults to None.

        Returns:
            GenieSpace: The created GenieSpace instance.
        """
        logger.debug(
            f"Adding space mapping for user {user_id}: {space_name} ({space_id})"
        )
        async with AsyncSession(self.engine) as session:
            mapping = GenieSpace(
                user_id=user_id,
                space_id=space_id,
                space_name=space_name,
                description=description,
            )
            session.add(mapping)
            await session.commit()
            await session.refresh(mapping)
            logger.info(
                f"Successfully added mapping for space {space_id} to user {user_id}"
            )
            return mapping

    async def add_user_space_mappings_bulk(
        self, user_id: str, spaces: list[dict]
    ) -> None:
        """Adds multiple Genie Space mappings for a user in a single DB round-trip.

        Args:
            user_id (str): The Microsoft Teams user ID.
            spaces (list[dict]): A list of dicts with keys 'space_id', 'space_name', 'description'.
        """
        logger.debug(f"Bulk-inserting {len(spaces)} space mappings for user {user_id}")
        async with AsyncSession(self.engine) as session:
            mappings = [
                GenieSpace(
                    user_id=user_id,
                    space_id=s["space_id"],
                    space_name=s["space_name"],
                    description=s.get("description"),
                )
                for s in spaces
            ]
            session.add_all(mappings)
            await session.commit()
            logger.info(
                f"Successfully bulk-inserted {len(mappings)} space mappings for user {user_id}"
            )

    async def clear_user_space_mappings(self, user_id: str) -> int:
        """Removes all stored Genie Space mappings for a specific user.

        Args:
            user_id (str): The Microsoft Teams user ID.

        Returns:
            int: The number of mappings deleted.
        """
        logger.debug(f"Clearing all active space mappings for user: {user_id}")
        async with AsyncSession(self.engine) as session:
            # Count first so we can report how many were deleted
            count_stmt = select(GenieSpace).where(GenieSpace.user_id == user_id)
            count_result = await session.exec(count_stmt)
            count = len(count_result.all())

            # Single bulk DELETE — eliminates N individual round-trips
            delete_stmt = delete(GenieSpace).where(GenieSpace.user_id == user_id)
            await session.exec(delete_stmt)
            await session.commit()
            logger.info(f"Cleared {count} space mappings for user {user_id}")
            return count

    async def add_user_selection(
        self, user_id: str, space_id: str, space_name: str, conversation_id: str
    ) -> UserSelection:
        """Adds a new active user selection for a Genie Space.

        Args:
            user_id (str): The Microsoft Teams user ID.
            space_id (str): The selected Genie Space ID.
            space_name (str): The selected Genie Space name.
            conversation_id (str): The active conversation ID for context.

        Returns:
            UserSelection: The created UserSelection record.
        """
        logger.debug(
            f"Adding user selection for {user_id}: {space_name} (Conversation: {conversation_id})"
        )
        async with AsyncSession(self.engine) as session:
            selection = UserSelection(
                user_id=user_id,
                space_id=space_id,
                space_name=space_name,
                conversation_id=conversation_id,
            )
            session.add(selection)
            await session.commit()
            await session.refresh(selection)
            logger.info(f"Successfully added user selection for {user_id}")
            return selection

    async def update_user_scope(
        self, user_id: str, user_group_id: str
    ) -> UserSelection | None:
        """Updates the security group scope for a user's selection.

        Args:
            user_id (str): The Microsoft Teams user ID.
            user_group_id (str): The new security group ID.

        Returns:
            UserSelection | None: The updated UserSelection, or None if not found.
        """
        logger.debug(f"Updating user scope for {user_id} to group: {user_group_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(UserSelection).where(UserSelection.user_id == user_id)
            result = await session.exec(statement)
            selection = result.first()
            if selection:
                selection.user_group_id = user_group_id
                session.add(selection)
                await session.commit()
                await session.refresh(selection)
                logger.info(f"Successfully updated scope for user {user_id}")
                return selection

        logger.warning(
            f"Failed to update scope for user {user_id}: Selection not found."
        )
        return None

    async def get_user_selection(self, user_id: str) -> UserSelection | None:
        """Retrieves the active user selection and context state.

        Args:
            user_id (str): The Microsoft Teams user ID.

        Returns:
            UserSelection | None: The user's active selection, or None if empty.
        """
        logger.debug(f"Fetching current user selection for: {user_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(UserSelection).where(UserSelection.user_id == user_id)
            result = await session.exec(statement)
            selection = result.first()
            if selection:
                logger.debug(
                    f"Found active selection for user {user_id}: {selection.space_name}"
                )
            else:
                logger.debug(f"No active selection found for user {user_id}")
            return selection

    async def update_user_selection(
        self, user_id: str, space_id: str, space_name: str, conversation_id: str
    ) -> UserSelection:
        """Updates an existing user selection, or creates one if it doesn't exist.

        Args:
            user_id (str): The Microsoft Teams user ID.
            space_id (str): The new Genie Space ID.
            space_name (str): The new Genie Space name.
            conversation_id (str): The new conversation ID.

        Returns:
            UserSelection: The updated or newly created UserSelection record.
        """
        logger.debug(
            f"Updating user selection for {user_id} -> {space_name} (Space: {space_id}, Conv: {conversation_id})"
        )
        async with AsyncSession(self.engine) as session:
            statement = select(UserSelection).where(UserSelection.user_id == user_id)
            result = await session.exec(statement)
            selection = result.first()
            if selection:
                logger.debug(f"Modifying existing selection row for user {user_id}")
                selection.space_id = space_id
                selection.space_name = space_name
                selection.conversation_id = conversation_id
            else:
                logger.debug(
                    f"No existing selection row for user {user_id}, instantiating a new one."
                )
                selection = UserSelection(
                    user_id=user_id,
                    space_id=space_id,
                    space_name=space_name,
                    conversation_id=conversation_id,
                )

            session.add(selection)
            await session.commit()
            await session.refresh(selection)
            logger.info(f"User selection saved/updated for user {user_id}")
            return selection

    async def get_security_group_mapping(
        self, group_id: list[str]
    ) -> list[SecurityGroupMapping]:
        """Fetches Databricks credentials associated with a list of security group IDs.

        Args:
            group_id (list[str]): A list of Microsoft Entra ID group Object IDs.

        Returns:
            list[SecurityGroupMapping]: The matching security group configurations.
        """
        logger.debug(f"Fetching security group mappings for group IDs: {group_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(SecurityGroupMapping).where(
                SecurityGroupMapping.group_id.in_(group_id)
            )
            result = await session.exec(statement)
            mappings = result.all()
            logger.debug(f"Found {len(mappings)} configured security group mappings.")
            return mappings

    async def get_scope_details(
        self, user_group_id: str
    ) -> SecurityGroupMapping | None:
        """Retrieves Databricks credentials for a single security group ID.

        Args:
            user_group_id (str): The Microsoft Entra ID group Object ID.

        Returns:
            SecurityGroupMapping | None: The security group config, or None if not found.
        """
        logger.debug(f"Fetching scope details for single group ID: {user_group_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(SecurityGroupMapping).where(
                SecurityGroupMapping.group_id == user_group_id
            )
            result = await session.exec(statement)
            mapping = result.first()
            if mapping:
                logger.debug(f"Found scope details for {user_group_id}")
            else:
                logger.warning(f"No scope details found for group ID {user_group_id}")
            return mapping

    async def add_query_log(
        self,
        user_id: str,
        question: str,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None,
        scope_name: Optional[str] = None,
        space_name: Optional[str] = None,
        space_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        sql_query: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        exception: Optional[str] = None,
    ) -> GenieAuditLog:
        """Logs a user query activity to the genie_audit_logs table.

        Args:
            user_id (str): The Microsoft Teams user ID.
            question (str): The question asked.
            user_name (str, optional): The name of the user.
            user_email (str, optional): The email of the user.
            scope_name (str, optional): The scope/security group name.
            space_name (str, optional): The name of the Genie space.
            space_id (str, optional): The ID of the Genie space.
            conversation_id (str, optional): The ID of the Genie conversation.
            sql_query (str, optional): The generated SQL query.
            start_time (datetime, optional): The time execution started.
            end_time (datetime, optional): The time execution ended.
            exception (str, optional): Exception details if any error occurred.

        Returns:
            GenieAuditLog: The saved GenieAuditLog entry.
        """
        logger.debug(f"Adding query log for user {user_id}: '{question}'")
        async with AsyncSession(self.engine) as session:
            log_entry = GenieAuditLog(
                user_id=user_id,
                question=question,
                user_name=user_name,
                user_email=user_email,
                scope_name=scope_name,
                space_name=space_name,
                space_id=space_id,
                conversation_id=conversation_id,
                sql_query=sql_query,
                start_time=start_time,
                end_time=end_time,
                exception=exception,
            )
            session.add(log_entry)
            await session.commit()
            await session.refresh(log_entry)
            logger.info(f"Successfully logged query for user {user_id}")
            return log_entry
