"""
Utility classes for bot handlers.
"""

import asyncio
from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.activity import Activity, ActivityTypes


class BotUtilities:
    """Shared utility methods for bot handlers."""

    @staticmethod
    async def keep_typing_while(turn_context: TurnContext, func, *args, **kwargs):
        """Sends typing indicators while a long function is running."""
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
