import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from handlers.message_handler import MessageHandler
from microsoft_agents.hosting.core import TurnContext
from database.db_models import UserSelection


@pytest.fixture
def mock_database():
    db = MagicMock()
    db.get_user_selection = AsyncMock()
    db.update_user_selection = AsyncMock()
    db.update_user_scope = AsyncMock()
    db.clear_user_space_mappings = AsyncMock()
    return db


@pytest.fixture
def mock_turn_context():
    context = MagicMock(spec=TurnContext)
    context.activity = MagicMock()
    context.activity.from_property.id = "user_123"
    context.send_activity = AsyncMock()
    context.delete_activity = AsyncMock()
    context.turn_state = {}
    return context


@pytest.fixture
def message_handler(mock_database):
    with (
        patch("handlers.message_handler.GenieListHandler"),
        patch("handlers.message_handler.FileCardHandler"),
        patch("handlers.message_handler.LlmSummarizer"),
    ):
        handler = MessageHandler(mock_database)
        handler.handle_card_action = AsyncMock()
        handler.handle_genie_question = AsyncMock()
        handler.send_group_selection_card = AsyncMock()
        # Mock the internal list handler method
        handler.genie_list_handler.handle_list_spaces = AsyncMock(
            return_value="list response"
        )
        return handler


async def test_process_message_with_card_action(message_handler, mock_turn_context):
    # Arrange
    mock_turn_context.activity.value = {"action": "select_space"}

    # Act
    await message_handler.process_message(mock_turn_context)

    # Assert
    message_handler.handle_card_action.assert_called_once_with(
        mock_turn_context, "user_123", {"action": "select_space"}
    )


async def test_process_message_list_spaces(
    message_handler, mock_turn_context, monkeypatch
):
    # Arrange
    mock_turn_context.activity.value = None
    mock_turn_context.activity.text = "list genie spaces"
    monkeypatch.setenv("DATABRICKS_TOKEN", "test-token")

    # Act
    await message_handler.process_message(mock_turn_context)

    # Assert
    message_handler.genie_list_handler.handle_list_spaces.assert_called_once_with(
        user_id="user_123"
    )
    mock_turn_context.send_activity.assert_any_call("list response")


async def test_process_message_genie_question_with_selection(
    message_handler, mock_turn_context, mock_database
):
    # Arrange
    mock_turn_context.activity.value = None
    mock_turn_context.activity.text = "what are the sales?"

    user_sel = UserSelection(user_id="user_123", space_id="space_456")
    mock_database.get_user_selection.return_value = user_sel

    # Act
    await message_handler.process_message(mock_turn_context)

    # Assert
    message_handler.handle_genie_question.assert_called_once_with(
        mock_turn_context, "user_123", "what are the sales?", user_sel
    )


async def test_process_message_genie_question_no_selection(
    message_handler, mock_turn_context, mock_database
):
    # Arrange
    mock_turn_context.activity.value = None
    mock_turn_context.activity.text = "what are the sales?"
    mock_database.get_user_selection.return_value = None

    # Act
    await message_handler.process_message(mock_turn_context)

    # Assert
    message_handler.handle_genie_question.assert_not_called()
    mock_turn_context.send_activity.assert_called_once_with(
        "Please select a Genie space first by typing 'list genie spaces'."
    )


async def test_handle_card_action_select_space(mock_database, mock_turn_context):
    with (
        patch("handlers.message_handler.GenieListHandler"),
        patch("handlers.message_handler.FileCardHandler"),
        patch("handlers.message_handler.LlmSummarizer"),
    ):
        handler = MessageHandler(mock_database)
        handler.handle_space_selection = AsyncMock()

        await handler.handle_card_action(
            mock_turn_context,
            "user_123",
            {"action": "select_space", "space_id": "s1", "space_name": "Space 1"},
        )

        handler.handle_space_selection.assert_called_once_with(
            mock_turn_context, "user_123", "s1", "Space 1"
        )


async def test_handle_space_selection(mock_database, mock_turn_context):
    with (
        patch("handlers.message_handler.GenieListHandler"),
        patch("handlers.message_handler.FileCardHandler"),
        patch("handlers.message_handler.LlmSummarizer"),
    ):
        handler = MessageHandler(mock_database)

        await handler.handle_space_selection(
            mock_turn_context, "user_123", "s1", "Space 1"
        )

        mock_database.update_user_selection.assert_called_once_with(
            user_id="user_123",
            space_id="s1",
            space_name="Space 1",
            conversation_id=None,
        )
        mock_turn_context.send_activity.assert_called_once_with(
            "✅ Selected space: **Space 1**. You can now ask questions!"
        )
