from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text
from typing import Optional
from datetime import datetime


class GenieSpace(SQLModel, table=True):
    """Represents a Databricks Genie Space mapping for a user."""

    # Primary Keys MUST have a strict length limit to be indexable
    user_id: str = Field(default=None, primary_key=True, max_length=255)
    space_id: str = Field(default=None, primary_key=True, max_length=255)
    
    # All other strings set to MAX size
    space_name: str = Field(default=None, sa_column=Column(Text))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))


class UserSelection(SQLModel, table=True):
    """Represents the active selected scope and context for a user."""

    # Primary Key
    user_id: str = Field(default=None, primary_key=True, max_length=255)
    
    # All other strings set to MAX size
    space_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    space_name: Optional[str] = Field(default=None, sa_column=Column(Text))
    conversation_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    user_group_id: Optional[str] = Field(default=None, sa_column=Column(Text))


class SecurityGroupMapping(SQLModel, table=True):
    """Represents a mapping between an Entra ID security group and Databricks credentials."""

    # Primary Key
    group_id: str = Field(default=None, primary_key=True, max_length=255)
    
    # All other strings set to MAX size
    group_name: str = Field(default=None, sa_column=Column(Text))
    databricks_client_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    databricks_client_secret: Optional[str] = Field(default=None, sa_column=Column(Text))


class GenieAuditLog(SQLModel, table=True):
    __tablename__ = "genie_audit_logs"
    """Represents a log entry for a user's question and the generated response/metadata."""

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # All other strings set to MAX size
    user_name: Optional[str] = Field(default=None, sa_column=Column(Text))
    user_email: Optional[str] = Field(default=None, sa_column=Column(Text))
    user_id: str = Field(sa_column=Column(Text))
    scope_name: Optional[str] = Field(default=None, sa_column=Column(Text))
    space_name: Optional[str] = Field(default=None, sa_column=Column(Text))
    space_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    conversation_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    question: str = Field(sa_column=Column(Text))
    sql_query: Optional[str] = Field(default=None, sa_column=Column(Text))
    start_time: Optional[datetime] = Field(default=None)
    end_time: Optional[datetime] = Field(default=None)
    exception: Optional[str] = Field(default=None, sa_column=Column(Text))