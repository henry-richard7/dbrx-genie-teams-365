import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlmodel import SQLModel
from database.database import Database
from database.db_models import UserSelection, GenieSpace, SecurityGroupMapping, GenieAuditLog


@pytest_asyncio.fixture
async def memory_db():
    # Initialize with an in-memory SQLite database for testing
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_tables()
    yield db
    async with db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await db.close()


@pytest.mark.asyncio
async def test_add_and_get_user_selection(memory_db: Database):
    # Act
    await memory_db.add_user_selection("user123", "space1", "My Space", "conv1")
    selection = await memory_db.get_user_selection("user123")

    # Assert
    assert selection is not None
    assert selection.user_id == "user123"
    assert selection.space_id == "space1"
    assert selection.space_name == "My Space"
    assert selection.conversation_id == "conv1"


@pytest.mark.asyncio
async def test_update_user_selection(memory_db: Database):
    # Arrange
    await memory_db.add_user_selection("user123", "space1", "My Space", "conv1")

    # Act
    await memory_db.update_user_selection("user123", "space2", "New Space", "conv2")
    selection = await memory_db.get_user_selection("user123")

    # Assert
    assert selection is not None
    assert selection.space_id == "space2"
    assert selection.space_name == "New Space"
    assert selection.conversation_id == "conv2"


@pytest.mark.asyncio
async def test_user_space_mappings(memory_db: Database):
    # Act
    await memory_db.add_user_space_mapping("user123", "space1", "Space 1")
    await memory_db.add_user_space_mapping("user123", "space2", "Space 2")

    mappings = await memory_db.get_user_space_mappings("user123")

    # Assert
    assert len(mappings) == 2
    assert mappings[0].space_id == "space1"
    assert mappings[1].space_id == "space2"

    # Act - Clear
    await memory_db.clear_user_space_mappings("user123")
    mappings_after = await memory_db.get_user_space_mappings("user123")

    # Assert - Clear
    assert len(mappings_after) == 0


@pytest.mark.asyncio
async def test_add_query_log(memory_db: Database):
    # Arrange
    user_id = "user123"
    question = "how many customers do we have?"
    user_name = "Alice Cooper"
    user_email = "alice@example.com"
    scope_name = "Admin Group"
    space_name = "Customer Space"
    space_id = "space_cust_001"
    conversation_id = "conv_12345"
    sql_query = "SELECT COUNT(*) FROM customers"
    start_time = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2026, 5, 21, 12, 0, 5, tzinfo=timezone.utc)
    exception = None

    # Act
    log_entry = await memory_db.add_query_log(
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

    # Assert
    assert log_entry is not None
    assert log_entry.id is not None
    assert log_entry.user_id == user_id
    assert log_entry.question == question
    assert log_entry.user_name == user_name
    assert log_entry.user_email == user_email
    assert log_entry.scope_name == scope_name
    assert log_entry.space_name == space_name
    assert log_entry.space_id == space_id
    assert log_entry.conversation_id == conversation_id
    assert log_entry.sql_query == sql_query
    # SQLModel/SQLite might return naive/tz-aware datetime depending on drivers. Let's compare naive equivalents.
    assert log_entry.start_time.replace(tzinfo=None) == start_time.replace(tzinfo=None)
    assert log_entry.end_time.replace(tzinfo=None) == end_time.replace(tzinfo=None)
    assert log_entry.exception == exception

    # Query from database directly to verify persistence
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    async with AsyncSession(memory_db.engine) as session:
        statement = select(GenieAuditLog).where(GenieAuditLog.user_id == user_id)
        results = await session.exec(statement)
        retrieved_log = results.first()

    assert retrieved_log is not None
    assert retrieved_log.id == log_entry.id
    assert retrieved_log.question == question
    assert retrieved_log.sql_query == sql_query

