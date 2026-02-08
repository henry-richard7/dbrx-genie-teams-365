from .db_models import UserSelection, GenieSpace
from sqlmodel import select, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List


class Database:
    def __init__(self, db_url: str = "sqlite+aiosqlite:///teams_genie_bot.db"):
        self.engine = create_async_engine(db_url)

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    async def get_user_space_mappings(self, user_id: str) -> List[GenieSpace]:
        async with AsyncSession(self.engine) as session:
            statement = select(GenieSpace).where(GenieSpace.user_id == user_id)
            results = await session.exec(statement)
            return results.all()

    async def add_user_space_mapping(
        self, user_id: str, space_id: str, space_name: str, description: str = None
    ):
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
            return mapping

    async def clear_user_space_mappings(self, user_id: str):
        async with AsyncSession(self.engine) as session:
            statement = select(GenieSpace).where(GenieSpace.user_id == user_id)
            results = await session.exec(statement)
            mappings = results.all()
            for mapping in mappings:
                await session.delete(mapping)
            await session.commit()
            return len(mappings)

    async def add_user_selection(
        self, user_id: str, space_id: str, space_name: str, conversation_id: str
    ):
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
            return selection

    async def get_user_selection(self, user_id: str) -> UserSelection:
        async with AsyncSession(self.engine) as session:
            statement = select(UserSelection).where(UserSelection.user_id == user_id)
            result = await session.exec(statement)
            return result.first()

    async def update_user_selection(
        self, user_id: str, space_id: str, space_name: str, conversation_id: str
    ):
        async with AsyncSession(self.engine) as session:
            statement = select(UserSelection).where(UserSelection.user_id == user_id)
            result = await session.exec(statement)
            selection = result.first()
            if selection:
                selection.space_id = space_id
                selection.space_name = space_name
                selection.conversation_id = conversation_id
                session.add(selection)
                await session.commit()
                await session.refresh(selection)
                return selection

        return await self.add_user_selection(
            user_id, space_id, space_name, conversation_id
        )
