import logging
import asyncio
from databricks.sdk import AccountClient
from microsoft_agents.hosting.core import TurnContext, MessageFactory, CardFactory
from modules.AdaptiveCardTemplate import AdaptiveCardTemplate
from database.database import Database

logger = logging.getLogger(__name__)

class WorkspaceListHandler:
    def __init__(self, database: Database, user_state=None, conversation_state=None):
        self.database = database
        self.user_state = user_state
        self.conversation_state = conversation_state

    async def handle_list_workspaces(self, turn_context: TurnContext, user_id: str, client_id: str = None, client_secret: str = None, token: str = None, account_host: str = None, account_id: str = None):
        """Lists accessible workspaces for the user and sends an Adaptive Card for selection."""
        if not account_host or not account_id:
            logger.warning("Account-level auth not configured, cannot list workspaces.")
            await turn_context.send_activity("❌ Account-level authentication is not configured.")
            return

        try:
            logger.info("Fetching workspace list from Databricks Account")
            
            def fetch_workspaces():
                client = AccountClient(
                    host=account_host, 
                    account_id=account_id, 
                    client_id=client_id, 
                    client_secret=client_secret, 
                    token=token
                )
                return list(client.workspaces.list())
                
            workspaces = await asyncio.to_thread(fetch_workspaces)
            
            card_template = AdaptiveCardTemplate()
            card_template.add_text("🏢 Select a Databricks Workspace", is_title=True, color="Accent")
            card_template.add_text("Please choose a workspace to use for Genie Spaces:")

            if not workspaces:
                card_template.add_text("You do not have access to any workspaces in this account, or your token lacks permissions to list them. You can enter your workspace URL manually:")
            else:
                for ws in workspaces[:10]: # Limit to 10
                    # Fallback construct host from deployment_name
                    host = f"https://{ws.deployment_name}.cloud.databricks.com" if ws.deployment_name else ""
                    
                    if host:
                        card_template.add_item({
                            "type": "ActionSet",
                            "actions": [{
                                "type": "Action.Submit",
                                "title": ws.workspace_name or f"Workspace {ws.workspace_id}",
                                "data": {
                                    "action": "select_workspace",
                                    "workspace_id": str(ws.workspace_id),
                                    "workspace_name": ws.workspace_name,
                                    "workspace_host": host
                                }
                            }]
                        })
                
                card_template.add_text("If your workspace isn't listed or the URL cannot be constructed, you can enter it manually below:")

            # Manual entry fallback
            card_template.add_item({
                "type": "Input.Text",
                "id": "manual_workspace_host",
                "placeholder": "https://adb-123456789.12.azuredatabricks.net"
            })
            card_template.add_item({
                "type": "ActionSet",
                "actions": [{
                    "type": "Action.Submit",
                    "title": "Use Manual Workspace URL",
                    "data": {
                        "action": "select_workspace",
                        "workspace_name": "Manual Workspace"
                    }
                }]
            })

            attachment = CardFactory.adaptive_card(card_template.get_adaptive_card())
            await turn_context.send_activity(MessageFactory.attachment(attachment))

        except Exception as e:
            logger.error(f"Failed to list workspaces: {e}", exc_info=True)
            await turn_context.send_activity(f"❌ Error listing workspaces: {str(e)}")
