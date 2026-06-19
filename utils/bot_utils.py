"""
Utility classes for bot handlers.
"""

import asyncio
from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.activity import Activity, ActivityTypes

from typing import Any

class BotUtilities:
    """Shared utility methods for bot handlers.

    Provides common functionality required across various bot components,
    such as managing long-running processes while providing user feedback.
    """

    @staticmethod
    async def keep_typing_while(_turn_context: TurnContext, _func, *args, **kwargs) -> Any:
        """Sends typing indicators while a long-running function executes.

        This ensures that Microsoft Teams does not timeout and the user knows the bot
        is still processing their request.

        Args:
            _turn_context (TurnContext): The context object for the current turn.
            _func (Callable): The asynchronous function to execute.
            *args (Any): Variable length argument list to pass to the function.
            **kwargs (Any): Arbitrary keyword arguments to pass to the function.

        Returns:
            Any: The result returned by the executed function.
        """

        async def keep_typing():
            try:
                while True:
                    await _turn_context.send_activity(
                        Activity(type=ActivityTypes.typing)
                    )
                    await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(keep_typing())

        try:
            result = await _func(*args, **kwargs)
            return result
        finally:
            typing_task.cancel()

    @staticmethod
    def create_error_activity(title: str, message: str, retry_action: dict = None) -> Activity:
        """Creates an Adaptive Card error message activity.
        
        Args:
            title (str): The main error heading.
            message (str): Detailed error text.
            retry_action (dict, optional): A dictionary representing the retry button action.
                Example: {"title": "🔄 Try Again", "action": "retry_spaces"}
                
        Returns:
            Activity: The generated message activity containing the error card.
        """
        from modules.AdaptiveCardTemplate import AdaptiveCardTemplate
        from microsoft_agents.hosting.core import CardFactory, MessageFactory
        
        error_card_template = AdaptiveCardTemplate()
        
        error_card_template.add_text(
            content=title,
            color="Attention",
            is_title=True,
        )
        error_card_template.add_text(
            content=title, color="Attention"
        )
        error_card_template.add_text(
            content=message,
            spacing="Medium",
        )
        
        if retry_action:
            error_card_template.add_item(
                {
                    "type": "Container",
                    "items": [
                        {
                            "type": "ActionSet",
                            "actions": [
                                {
                                    "type": "Action.Submit",
                                    "title": retry_action.get("title", "🔄 Try Again"),
                                    "style": "positive",
                                    "iconUrl": "icon:Refresh",
                                    "data": {"action": retry_action.get("action")},
                                }
                            ],
                            "horizontalAlignment": "Left",
                        }
                    ],
                    "spacing": "Medium",
                },
            )
            
        error_attachment = CardFactory.adaptive_card(
            error_card_template.get_adaptive_card()
        )
        return MessageFactory.attachment(error_attachment)

    @staticmethod
    async def get_out_of_band_token_from_storage(user_state, turn_context: TurnContext, user_id: str) -> dict:
        """Retrieves an OAuth token written directly to S3, bypassing the stale UserState cache.
        
        Args:
            user_state (UserState): The UserState accessor.
            turn_context (TurnContext): The current turn context.
            user_id (str): The Microsoft Teams user ID.
            
        Returns:
            dict: The UserTokenProperty from storage, or empty dict.
        """
        channel_id = turn_context.activity.channel_id or "msteams"
        state_key = f"{channel_id}/users/{user_id}"
        from microsoft_agents.hosting.core.state.agent_state import CachedAgentState
        user_state_dict = await user_state._storage.read([state_key], target_cls=CachedAgentState)
        state_obj = user_state_dict.get(state_key)
        if state_obj and state_obj.state:
            return state_obj.state.get("UserTokenProperty", {})
        return {}
