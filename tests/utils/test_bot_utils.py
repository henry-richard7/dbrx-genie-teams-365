import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from utils.bot_utils import BotUtilities
from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.activity import ActivityTypes

@pytest.mark.asyncio
async def test_keep_typing_while():
    # Arrange
    mock_turn_context = AsyncMock(spec=TurnContext)
    
    # We will test the functionality by patching asyncio.sleep inside bot_utils
    # We need to yield control back to the event loop so gather can run the executor
    original_sleep = asyncio.sleep
    async def mock_sleep(seconds):
        await original_sleep(0.01) # Yield control
        
    with patch("utils.bot_utils.asyncio.sleep", new=mock_sleep):
        
        async def slow_task():
            await original_sleep(0.05) # take a little longer so typing fires
            return "done"
            
        # Act
        result = await BotUtilities.keep_typing_while(mock_turn_context, slow_task)
        
        # Assert
        assert result == "done"
        mock_turn_context.send_activity.assert_awaited()
        # Verify it sent a typing activity
        activity = mock_turn_context.send_activity.call_args[0][0]
        assert activity.type == ActivityTypes.typing
