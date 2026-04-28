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
        cancel = {"cancel": False}
        result = None

        async def keep_typing():
            while not cancel["cancel"]:
                await turn_context.send_activity(Activity(type=ActivityTypes.typing))
                await asyncio.sleep(10)

        async def executor():
            nonlocal result
            result = await func(*args, **kwargs)
            cancel["cancel"] = True

        await asyncio.gather(
            keep_typing(),
            executor(),
        )

        return result
