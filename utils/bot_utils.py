"""
Utility classes for bot handlers.
"""

import asyncio
from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.activity import Activity, ActivityTypes


class BotUtilities:
    """Shared utility methods for bot handlers.

    Provides common functionality required across various bot components,
    such as managing long-running processes while providing user feedback.
    """

    @staticmethod
    async def keep_typing_while(turn_context: TurnContext, func, *args, **kwargs):
        """Sends typing indicators while a long-running function executes.

    This ensures that Microsoft Teams does not timeout and the user knows the bot
    is still processing their request.

    Args:
        turn_context (TurnContext): The context object for the current turn.
        func (Callable): The asynchronous function to execute.
        *args: Variable length argument list to pass to the function.
        **kwargs: Arbitrary keyword arguments to pass to the function.

    Returns:
        Any: The result returned by the executed function.
    """
        async def keep_typing():
            try:
                while True:
                    await turn_context.send_activity(Activity(type=ActivityTypes.typing))
                    await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(keep_typing())
        
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            typing_task.cancel()
