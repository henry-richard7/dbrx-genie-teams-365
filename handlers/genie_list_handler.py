"""Module for fetching and displaying available Databricks Genie spaces.

This module builds the Adaptive Cards required to present users with a list of
Genie spaces they can interact with, complete with description formatting and
selection buttons.
"""

from microsoft_agents.hosting.core import MessageFactory, CardFactory
from microsoft_agents.activity import Activity

from modules.genie import Genie
from modules.AdaptiveCardTemplate import AdaptiveCardTemplate
from database.database import Database


class GenieListHandler:
    """A handler for querying and displaying available Databricks Genie Spaces.

    Attributes:
        db (Database): The database interface used to fetch or cache user space mappings.
    """

    def __init__(self, database: Database):
        """Initializes the GenieListHandler.

        Args:
            database (Database): The instantiated Database class.
        """
        self.db = database

    async def handle_list_spaces(
        self,
        user_id: str,
        client_id: str = None,
        client_secret: str = None,
        scope_name: str = None,
    ) -> Activity:
        """Handles the request to fetch and render available Genie spaces.

        If spaces are not cached in the database, it queries the Databricks API
        using the provided credentials and stores them. It then builds an Adaptive Card
        with inline buttons allowing the user to select a space.

        Args:
            user_id (str): The Microsoft Teams user ID.
            client_id (str, optional): The OAuth Client ID for Databricks. Defaults to None.
            client_secret (str, optional): The OAuth Client Secret for Databricks. Defaults to None.
            scope_name (str, optional): The name of the current scope/group (for display purposes). Defaults to None.

        Returns:
            Activity: A Microsoft Teams message activity containing the rendered Adaptive Card.
        """
        try:
            existing_mappings = await self.db.get_user_space_mappings(user_id)

            if not existing_mappings:
                genie_api = Genie(client_id=client_id, client_secret=client_secret)
                spaces = await genie_api.get_spaces()

                if not spaces:
                    return MessageFactory.text(
                        "❌ No Genie spaces available at the moment."
                    )

                # Store spaces in database for the user
                for space in spaces:
                    await self.db.add_user_space_mapping(
                        user_id=user_id,
                        space_id=space.space_id,
                        space_name=space.title,
                        description=space.description,
                    )

                existing_mappings = await self.db.get_user_space_mappings(user_id)

            card_template_genie_list = AdaptiveCardTemplate()

            card_template_genie_list.add_text(
                content=f"🔍 Available Genie Spaces{f' for **{scope_name}**' if scope_name else ''}",
                is_title=True,
                color="Accent",
            )
            card_template_genie_list.add_text(
                content="Here are the data analysis spaces you can work with:",
                is_title=False,
            )

            # Add each space as a container with button and description
            for space in existing_mappings:

                space_container = {
                    "type": "Container",
                    "items": [
                        {
                            "type": "ActionSet",
                            "actions": [
                                {
                                    "type": "Action.Submit",
                                    "title": space.space_name,
                                    "style": "positive",
                                    "iconUrl": "icon:DataUsage",
                                    "data": {
                                        "action": "select_space",
                                        "space_name": space.space_name,
                                        "space_id": space.space_id,
                                    },
                                }
                            ],
                            "horizontalAlignment": "Left",
                        },
                        {
                            "type": "TextBlock",
                            "text": (
                                f"\n**Description:** {space.description}\n"
                                if space.description
                                else ""
                            ),
                            "wrap": True,
                        },
                    ],
                    "separator": True,
                    "rtl": False,
                    "style": "emphasis",
                }

                card_template_genie_list.add_item(space_container)

            card_template_genie_list.add_text(
                content="💡 **How to use:**", is_title=True
            )
            card_template_genie_list.add_text(
                content="- Click any space button above to select it.\n- Once selected, you can ask questions about your data.",
                is_title=False,
            )

            # Add footer actions
            footer_container = {
                "type": "Container",
                "items": [
                    {
                        "type": "ActionSet",
                        "actions": [
                            {
                                "type": "Action.Submit",
                                "title": "🔄 Refresh Spaces",
                                "iconUrl": "icon:Refresh",
                                "data": {"action": "refresh_spaces"},
                            },
                            {
                                "type": "Action.Submit",
                                "title": "❓ Help",
                                "iconUrl": "icon:Help",
                                "data": {"action": "show_help"},
                            },
                        ],
                        "horizontalAlignment": "Left",
                    }
                ],
                "horizontalAlignment": "Left",
                "style": "default",
                "spacing": "Large",
            }

            card_template_genie_list.add_item(footer_container)

            # Create the card attachment
            attachment = CardFactory.adaptive_card(
                card_template_genie_list.get_adaptive_card()
            )

            # Create message activity with the card
            reply = MessageFactory.attachment(attachment)
            return reply

        except Exception as e:

            # Fallback error card with new format
            error_card_template = AdaptiveCardTemplate()

            error_card_template.add_text(
                content="❌ Failed to retrieve available spaces",
                color="Attention",
                is_title=True,
            )
            error_card_template.add_text(
                content="❌ Failed to retrieve available spaces", color="Attention"
            )
            error_card_template.add_text(
                content="I encountered an issue while fetching the Genie spaces. This could be due to:",
                spacing="Medium",
            )
            error_card_template.add_text(
                content=f"{str(e)}",
                spacing="Medium",
            )

            error_card_template.add_item(
                {
                    "type": "Container",
                    "items": [
                        {
                            "type": "ActionSet",
                            "actions": [
                                {
                                    "type": "Action.Submit",
                                    "title": "🔄 Try Again",
                                    "style": "positive",
                                    "iconUrl": "icon:Refresh",
                                    "data": {"action": "retry_spaces"},
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
