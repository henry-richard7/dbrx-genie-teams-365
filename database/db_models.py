from sqlmodel import Column, SQLModel, Field, TEXT
from typing import Optional


class GenieSpace(SQLModel, table=True):
    """Represents a Databricks Genie Space mapping for a user.

    Attributes:
        user_id (str): The Microsoft Teams user ID (Primary Key).
        space_id (str): The unique identifier for the Genie Space (Primary Key).
        space_name (str): The human-readable name of the Genie Space.
        description (Optional[str]): An optional description of the space.
    """
    user_id: str = Field(
        default=None, max_length=255, sa_column=Column(TEXT, primary_key=True)
    )
    space_id: str = Field(default=None, primary_key=True, max_length=255)
    space_name: str = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)


class UserSelection(SQLModel, table=True):
    """Represents the active selected scope and context for a user.

    Attributes:
        user_id (str): The Microsoft Teams user ID (Primary Key).
        space_id (Optional[str]): The ID of the currently selected Genie Space.
        space_name (Optional[str]): The name of the currently selected Genie Space.
        conversation_id (Optional[str]): The active conversation ID in Databricks Genie.
        user_group_id (Optional[str]): The selected security group ID for Databricks credentials.
    """
    user_id: str = Field(default=None, primary_key=True, max_length=255)
    space_id: Optional[str] = Field(default=None, max_length=255)
    space_name: Optional[str] = Field(default=None, max_length=255)
    conversation_id: Optional[str] = Field(default=None, max_length=255)
    user_group_id: Optional[str] = Field(default=None, max_length=255)


class SecurityGroupMapping(SQLModel, table=True):
    """Represents a mapping between an Entra ID security group and Databricks credentials.

    Attributes:
        group_id (str): The Microsoft Entra ID group Object ID (Primary Key).
        group_name (str): The human-readable name of the group.
        databricks_client_id (Optional[str]): The OAuth client ID for the group.
        databricks_client_secret (Optional[str]): The OAuth client secret for the group.
    """
    group_id: str = Field(default=None, primary_key=True, max_length=255)
    group_name: str = Field(default=None, max_length=255)
    databricks_client_id: Optional[str] = Field(default=None, max_length=255)
    databricks_client_secret: Optional[str] = Field(default=None, max_length=255)
