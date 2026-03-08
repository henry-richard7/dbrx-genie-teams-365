from .db_models import UserSelection, GenieSpace, SecurityGroupMapping
from sqlmodel import select, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_url: str = "sqlite+aiosqlite:///teams_genie_bot.db"):
        logger.debug(f"Initializing Database with URL: {db_url}")
        self.engine = create_async_engine(db_url)

    async def create_tables(self):
        logger.info("Creating database tables if they do not exist.")
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.debug("Database tables created successfully.")

    async def close(self):
        logger.info("Closing database engine.")
        await self.engine.dispose()
        logger.debug("Database engine closed.")

    async def get_user_space_mappings(self, user_id: str) -> List[GenieSpace]:
        logger.debug(f"Fetching space mappings for user: {user_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(GenieSpace).where(GenieSpace.user_id == user_id)
            results = await session.exec(statement)
            mappings = results.all()
            logger.debug(f"Found {len(mappings)} mappings for user: {user_id}")
            return mappings

    async def add_user_space_mapping(
        self, user_id: str, space_id: str, space_name: str, description: str = None
    ):
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

    async def clear_user_space_mappings(self, user_id: str):
        logger.debug(f"Clearing all active space mappings for user: {user_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(GenieSpace).where(GenieSpace.user_id == user_id)
            results = await session.exec(statement)
            mappings = results.all()
            for mapping in mappings:
                await session.delete(mapping)
            await session.commit()
            logger.info(f"Cleared {len(mappings)} space mappings for user {user_id}")
            return len(mappings)

    async def add_user_selection(
        self, user_id: str, space_id: str, space_name: str, conversation_id: str
    ):
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

    async def update_user_scope(self, user_id: str, user_group_id: str):
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

    async def get_user_selection(self, user_id: str) -> UserSelection:
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
    ):
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
        logger.debug(f"Fetching security group mappings for group IDs: {group_id}")
        async with AsyncSession(self.engine) as session:
            statement = select(SecurityGroupMapping).where(
                SecurityGroupMapping.group_id.in_(group_id)
            )
            result = await session.exec(statement)
            mappings = result.all()
            logger.debug(f"Found {len(mappings)} configured security group mappings.")
            return mappings

    async def get_scope_details(self, user_group_id: str) -> SecurityGroupMapping:
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
