# 🧞‍♂️ Databricks Genie Teams Bot

A powerful, production-ready Microsoft Teams bot that interfaces seamlessly with Databricks Genie. It provides natural language data analytics, AI-driven insights, and rich data visualizations directly within your Teams chat. Built on FastAPI, AsyncIO, and SQLModel, this bot handles multi-tenant, enterprise-scale data interactions securely and asynchronously.

---

## 🌟 Key Features

*   **🗣️ Natural Language Queries**: Ask questions about your data in plain English (e.g., *"What were our top 5 products by revenue last quarter?"*).
*   **📊 Rich Adaptive Cards & Dynamic Charts**: Automatically visualizes query results with interactive charts (Vertical Bars, Grouped Bars, Donuts, Stacked Horizontal Bars) and structured data tables.
*   **🧠 AI Summarization & Insights**: Uses Databricks-hosted LLMs to automatically generate concise summaries and "Next Best Actions" based on the data.
*   **📂 Excel Export**: Automatically converts large datasets (>100 rows) into downloadable Excel files to bypass Teams payload limits.
*   **🔐 Multi-Tenant Scoped Access Control**: Dynamically resolves user credentials using Microsoft Entra ID (Azure AD) security groups. Users only query Databricks using the service principals they are explicitly authorized for.
*   **🚀 Highly Scalable & Asynchronous**: Built with `FastAPI` and `aiosqlite`/`asyncio` to handle concurrent users without blocking.

---

## 🏗️ Architecture Overview

The bot serves as an intelligent middleware between Microsoft Teams and your Databricks ecosystem. It dynamically routes user queries, handles scope permissions, triggers SQL execution via Genie, and augments the results using LLMs.

```mermaid
sequenceDiagram
    actor User as Teams User
    participant Bot as Teams Genie Bot
    participant DB as Database
    participant Auth as Graph API
    participant Genie as Genie API
    participant LLM as LLM Endpoint

    User->>Bot: "What were our top 5 products?"
    
    Note over Bot, Auth: 1. Authentication & State
    Bot->>DB: Get User Scope & Session
    DB-->>Bot: Selected Space
    Bot->>Auth: Resolve Entra ID Groups
    Auth-->>Bot: Service Principal Credentials
    
    Note over Bot, LLM: 2. Databricks Ecosystem
    Bot->>Genie: Execute NL Query
    Genie-->>Bot: Generated SQL & Raw Data
    Bot->>LLM: Analyze Raw Data
    LLM-->>Bot: AI Insights & Chart Type
    
    Note over Bot, User: 3. UI Generation
    Bot->>Bot: Assemble Adaptive Card
    Bot-->>User: Reply with Summary, Chart, & Table
```

---

## 📋 Prerequisites

To run this bot, you will need:
*   **Python 3.10+**
*   A **Databricks Workspace** with Genie enabled.
*   A **Microsoft Teams App Registration** (Azure Bot Service).
*   **Microsoft Graph API** permissions (`GroupMember.Read.All`, `User.Read.All`) granted to your app for user group resolution.

---

## 🛠️ Configuration & Setup

Create a `.env` file in the root directory with the following variables:

### Azure & Teams Bot Settings
```ini
# Microsoft App Registration Details
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID=<Your_Tenant_ID>
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID=<Your_App_Client_ID>
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET=<Your_App_Client_Secret>

# Server Port (default: 3978)
PORT=3978
```

### Databricks & Database Settings
```ini
# LLM Endpoint for summarizing the SQL output (default: databricks-qwen3-next-80b-a3b-instruct)
DATABRICKS_LLM_ENDPOINT=databricks-qwen3-next-80b-a3b-instruct

# Optional: Global Databricks Token (If not using Entra ID scoped credentials)
# DATABRICKS_TOKEN=<Personal_Access_Token>
# DATABRICKS_HOST=<Workspace_Url>

# Optional: Database Connection String (Defaults to a local SQLite file)
# Set this to a PostgreSQL or Azure SQL connection string for multi-pod production scaling!
# DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
```

---

## 🚀 Running the Bot

1. **Install Dependencies**:
   It is recommended to use a virtual environment or `uv`.
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Server**:
   ```bash
   python main.py
   ```
   The bot will start using Uvicorn on the configured port.

---

## 🤖 User Guide & Interaction Flow

1. **Listing Spaces**: 
   Start by typing **`list genie spaces`** in the Teams chat. (The bot uses fuzzy matching, so variations like "show spaces" will also work).
2. **Scope Selection**: 
   If your Microsoft account belongs to multiple security groups mapped to different Databricks environments, the bot will prompt you to select which scope/credentials you want to use for this session.
3. **Select a Space**: 
   Click on one of the available Databricks Genie spaces returned in the Adaptive Card.
4. **Ask Questions**: 
   Type your query naturally! 
   *   *Example: "Show me the top 10 customers by revenue this year."*
   *   The bot will reply with a 3-part card:
       1. An **AI Summary** of the trends.
       2. A **Dynamic Chart** visualizing the data.
       3. A **Data Table** (or an Excel file attachment if the result set is > 100 rows).

---

## 📂 Developer Guide & Code Structure

The repository is highly modular and utilizes Google-style docstrings across all modules to ensure maintainability.

*   **`main.py`**: The FastAPI entry point. Handles `uvicorn` startup, database lifecycle events, and the core Azure Bot Framework HTTP routing.
*   **`bot/bot.py`**: The `TeamsActivityHandler` implementation. Captures incoming messages and routes them to the `MessageHandler`.
*   **`handlers/`**: The core business logic.
    *   `message_handler.py`: Routes text inputs, manages conversational state, and triggers the AI insights pipeline.
    *   `genie_list_handler.py`: Responsible for fetching and displaying accessible Genie spaces.
    *   `file_card_handler.py`: Manages the MS Teams file consent workflow for exporting massive datasets to Excel.
*   **`modules/`**:
    *   `genie.py`: The wrapper around the Databricks SDK (`WorkspaceClient` and `GenieAPI`).
    *   `AdaptiveCardTemplate.py`: A utility factory for dynamically generating complex JSON Adaptive Cards (Tables, Code Blocks, Charts).
*   **`database/`**:
    *   `database.py`: Handles async SQL connection pooling via `sqlalchemy.ext.asyncio`.
    *   `db_models.py`: Defines the `SQLModel` schemas for tracking user sessions and space mappings.
*   **`utils/`**:
    *   `llm_summarizer.py`: Orchestrates the `ChatOpenAI` calls to the Databricks Model Serving endpoint. Includes resilient fallback logic for rate limits.
    *   `user_group.py`: Handles OAuth flow with Microsoft Graph to determine Entra ID group memberships.

---

## 🤝 Contributing

Contributions are heavily encouraged! When submitting Pull Requests, please ensure:
1. You have documented any new functions using **Google-style docstrings**.
2. You handle exceptions gracefully, keeping the end-user experience in mind.
3. You maintain the `async` nature of the codebase to preserve scalability.
