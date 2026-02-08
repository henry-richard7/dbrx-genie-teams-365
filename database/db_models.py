from sqlmodel import Column, SQLModel, Field, TEXT
from typing import Optional


class GenieSpace(SQLModel, table=True):
    user_id: str = Field(
        default=None, max_length=255, sa_column=Column(TEXT, primary_key=True)
    )
    space_id: str = Field(default=None, primary_key=True, max_length=255)
    space_name: str = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)


class UserSelection(SQLModel, table=True):
    user_id: str = Field(default=None, primary_key=True, max_length=255)
    space_id: Optional[str] = Field(default=None, max_length=255)
    space_name: Optional[str] = Field(default=None, max_length=255)
    conversation_id: Optional[str] = Field(default=None, max_length=255)


class SecurityGroupMapping(SQLModel, table=True):
    group_id: str = Field(default=None, primary_key=True, max_length=255)
    group_name: str = Field(default=None, max_length=255)
    databricks_client_id: Optional[str] = Field(default=None, max_length=255)
    databricks_client_secret: Optional[str] = Field(default=None, max_length=255)
