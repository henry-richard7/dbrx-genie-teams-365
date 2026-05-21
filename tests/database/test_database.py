import pytest
import pytest_asyncio
from database.database import Database
from database.db_models import UserSelection, GenieSpace, SecurityGroupMapping


@pytest_asyncio.fixture
async def memory_db():
    # Initialize with an in-memory SQLite database for testing
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_tables()
    yield db
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
