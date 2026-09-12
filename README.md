# 🧞‍♂️ Databricks Genie Teams Bot

<div align="center">
  <p><strong>A production-ready Microsoft Teams chatbot integrating Databricks Genie, FastAPI, and AI for real-time data analytics.</strong></p>
  <p>
    <a href="https://www.orcarouter.ai/ref/ref_0a1e6a219c956b889037"><img src="https://img.shields.io/badge/Built%20with-OrcaRouter-0070f3?style=flat-square&logo=openai&logoColor=white" alt="Built with OrcaRouter" /></a>
  </p>
</div>

Welcome to the **Databricks Genie Teams Bot** repository. This powerful, production-ready **Microsoft Teams chatbot** interfaces seamlessly with **Databricks Genie** to deliver natural language data analytics, AI-driven insights, and rich data visualizations directly within your enterprise Teams chat. 

Built using modern Python frameworks like **FastAPI**, **AsyncIO**, and **SQLModel**, this enterprise chatbot handles multi-tenant, large-scale data interactions securely and asynchronously. Whether you need generative AI summaries, automated SQL execution, or interactive Adaptive Cards, this bot is the perfect bridge between Microsoft 365 and your Databricks ecosystem.

---

## 🌟 Key Features

*   **🗣️ Natural Language Data Analytics**: Ask complex questions about your data in plain English (e.g., *"What were our top 5 products by revenue last quarter?"*) and let the bot generate the SQL.
*   **📊 Rich Adaptive Cards & Dynamic Charts**: Automatically visualizes Databricks query results with interactive charts (Vertical Bars, Grouped Bars, Donuts, Stacked Horizontal Bars) and structured UI data tables. 
*   **🧠 AI Chatbot Summarization & Insights**: Uses Databricks-hosted or OpenAI-compatible LLMs (e.g., OpenAI, [OrcaRouter](https://www.orcarouter.ai/ref/ref_0a1e6a219c956b889037) for multi-model routing, vLLM, Ollama) to automatically generate concise summaries and "Next Best Actions" based on the data.
*   **📂 Distributed Excel Export for Big Data**: Automatically converts large SQL datasets (>100 rows) into downloadable Excel files to bypass Microsoft Teams payload limits. Temporarily caches data payloads natively in Bot Framework state (via S3, MinIO, or memory) to prevent node memory exhaustion (only if `USE_CONTEXT` is enabled; otherwise, falls back to local application memory caching).
*   **🔐 Multi-Tenant Scoped Access Control (Azure AD)**: Dynamically resolves user credentials using Microsoft Entra ID (Azure AD) security groups. Users query Databricks using authorized Service Principals (M2M) or interactive Custom OAuth (U2M).
*   **🔒 Encrypted Credentials & Security**: User OAuth access tokens and refresh tokens are securely encrypted at rest.
*   **☁️ Distributed State Storage**: Optional scalable S3-compatible backend (AWS S3, MinIO), Azure Cosmos DB, or Azure Blob Storage for distributed Microsoft Bot Framework conversational state management.
*   **🚀 Highly Scalable API Backend**: Built with `FastAPI` and `aiosqlite`/`asyncio` to handle concurrent enterprise users without blocking.

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
*   **Python 3.13+**
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

# Server settings
PORT=3978
DEBUG=true

# Optional: Azure Bot Service OAuth Connection Name
AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__GRAPH__SETTINGS__AZUREBOTOAUTHCONNECTIONNAME=<Your_Connection_Name>
```

### Databricks & Database Settings
```ini
# Databricks Genie Host (e.g. https://your-workspace.cloud.databricks.com)
DATABRICKS_HOST=<Workspace_Url>

# Databricks Account Host and ID for Account-Level Auth (Optional, but recommended for U2M)
DATABRICKS_ACCOUNT_HOST=https://accounts.cloud.databricks.com
DATABRICKS_ACCOUNT_ID=<Your_Databricks_Account_ID>

# Optional: Enable visual Adaptive Card charts generated by LLM (active / inactive)
ENABLE_CHARTS=active

# Optional: Enable AI Insights to summarize the query response
GET_AI_INSIGHTS=true

# OpenAI-Compatible LLM Settings (e.g., Databricks, OpenAI, OrcaRouter, vLLM, Ollama)
# To use OrcaRouter (Get an API key via referral: https://www.orcarouter.ai/ref/ref_0a1e6a219c956b889037):
# OPENAI_BASE_URL=https://api.orcarouter.ai/v1
# OPENAI_MODEL_NAME=orcarouter/auto
# OPENAI_API_KEY=your_orcarouter_api_key
OPENAI_MODEL_NAME=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your_api_key_here

# Optional: Global Databricks Token/OAuth (If not using Entra ID scoped credentials)
DATABRICKS_TOKEN=<Personal_Access_Token>
DATABRICKS_CLIENT_ID=<Databricks M2M Oauth Client ID>
DATABRICKS_CLIENT_SECRET=<Databricks M2M Oauth Client Secret>

# Optional: User-Interactive Custom OAuth 
DATABRICKS_OAUTH_CLIENT_ID=<Your Custom OAuth App Client ID>
DATABRICKS_OAUTH_CLIENT_SECRET=<Your Custom OAuth App Client Secret>
OAUTH_REDIRECT_URI=<Your Bot Domain>/api/oauth/callback

# Optional: Database Connection String (Defaults to a local SQLite file: teams_genie_bot.db)
# Set this to a PostgreSQL or Azure SQL connection string for multi-pod production scaling!
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname

# Optional: State Storage Settings
USE_CONTEXT=false
STORAGE=s3 # Set to 's3', 'cosmos', or 'blob' if USE_CONTEXT is true and you want distributed state

# If STORAGE=s3
S3_BUCKET_NAME=your_s3_bucket
S3_ENDPOINT_URL=http://localhost:9000 # Omit for real AWS S3
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_REGION=us-east-1
S3_KEY_PREFIX=agent-state/
S3_DISABLE_SIGNING=false # Set to true to apply path-style addressing and non-chunked signing (e.g. for MinIO / custom S3)

# If STORAGE=cosmos
COSMOS_DB_ENDPOINT=https://your-cosmos-db-account.documents.azure.com:443/
COSMOS_DB_KEY=your-cosmos-db-primary-or-secondary-key # Omit to use Azure Managed Identity
COSMOS_DB_DATABASE=BotStateDb
COSMOS_DB_CONTAINER=BotStateContainer
COSMOS_DB_DISABLE_SSL=false # Set to true when using local Cosmos DB Emulator

# If STORAGE=blob
AZURE_BLOB_CONTAINER=bot-state
AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=... # Omit to use Azure Managed Identity
AZURE_BLOB_URL=https://your-account.blob.core.windows.net

# Optional: Token Encryption Settings
TOKEN_ENCRYPTION_KEY=your_generated_fernet_key_here
```

### 🔐 Setting up Databricks OAuth via Azure Security Groups (M2M)

This bot is designed for enterprise multi-tenant environments. Instead of using a single global Databricks Personal Access Token, it uses **Databricks OAuth for Service Principals** tied to your Azure active directory:

1.  **Create Security Groups in Azure**: In Microsoft Entra ID (Azure AD), create security groups for different sets of users (e.g., `Finance-Data-Access`, `Marketing-Data-Access`).
2.  **Create Databricks Service Principals**: In your Databricks workspace, create a Service Principal for each environment and generate its OAuth Client ID and Secret.
3.  **Map in Database**: Insert records into the `SecurityGroupMapping` database table mapping the Azure AD Group Object ID to the corresponding Databricks Service Principal's OAuth credentials.
4.  **How it Works**: When a user messages the bot, the Microsoft Graph API dynamically resolves their group memberships. The bot matches these against the `SecurityGroupMapping` table, granting them scoped Databricks access through the exact Service Principal they are authorized to use.

### 🔐 Setting up Interactive User-Specific Custom OAuth (U2M)

Alternatively, if you want users to explicitly authenticate with their own Databricks accounts (User-to-Machine flow), the bot supports a full interactive OAuth flow:

1. **Create Custom OAuth App**: In your Databricks Account Console, create a Custom OAuth Application and register the callback URL (e.g., `https://your-bot-domain.com/api/oauth/callback`).
2. **Configure Environment Variables**: Set `DATABRICKS_OAUTH_CLIENT_ID` and `OAUTH_REDIRECT_URI` in your `.env`. For **Account-Level Auth** (recommended), set `DATABRICKS_ACCOUNT_HOST` and `DATABRICKS_ACCOUNT_ID` instead of `DATABRICKS_HOST`. The `DATABRICKS_OAUTH_CLIENT_SECRET` is only required if the app was created as a confidential client.
3. **How it Works**: When a user messages the bot, they will be presented with an Adaptive Login Card. They authenticate directly via the Databricks login portal. If Account-Level Auth is used, the bot will dynamically prompt the user to select their specific Databricks Workspace from a list. The bot securely caches their `access_token` and `refresh_token` in the database, automatically renewing the tokens behind the scenes when they expire.

---

## 🚀 Running the Bot

1. **Install Dependencies**:
   It is highly recommended to use `uv` to manage python dependencies:
   ```bash
   uv sync
   ```
   Alternatively, you can install the dependencies via `pip`:
   ```bash
   pip install .
   ```

2. **Start the Server**:
   ```bash
   uv run python main.py
   ```
   The bot will start using Uvicorn on the configured port.

3. **Run the Test Suite**:
   ```bash
   uv run pytest -v
   ```
   This will execute all asynchronous and mocked API tests to verify codebase integrity.

---

## 🤖 User Guide & Interaction Flow

The interaction flow depends on how the bot's authentication is configured. When a user first interacts with the bot (e.g., by typing **`list genie spaces`**), one of the following authentication scenarios occurs:

### Scenario 1: Interactive Custom OAuth (User-to-Machine / U2M)
*(Triggered if `DATABRICKS_OAUTH_CLIENT_ID` is set)*
1. **Login Prompt**: The bot responds with a "Login to Databricks" Adaptive Card.
2. **Authentication**: The user clicks "Sign In", logs into Databricks in their browser, and authorizes the application. The bot securely encrypts and caches the resulting tokens.
3. **Workspace Selection (Account-Level Auth Only)**: If `DATABRICKS_ACCOUNT_HOST` is used instead of a single `DATABRICKS_HOST`, the bot dynamically fetches the workspaces the user has access to and prompts them to select one.
4. **Listing Spaces**: Once authenticated (and workspace selected), the bot fetches and displays the available Genie Spaces.

```mermaid
sequenceDiagram
    actor User as Teams User
    participant Bot as Teams Genie Bot
    participant Auth as Databricks OAuth
    participant DB as Database
    participant Genie as Genie API

    User->>Bot: "list genie spaces"
    Bot->>DB: Check for User Token
    DB-->>Bot: No Token Found
    Bot-->>User: Sends Login Adaptive Card
    User->>Auth: Authenticates via Browser
    Auth-->>Bot: OAuth Callback with Tokens
    Bot->>DB: Encrypt & Save Tokens
    
    opt Account-Level Auth Enabled
        Bot->>Genie: Fetch Available Workspaces
        Genie-->>Bot: List of Workspaces
        Bot-->>User: Workspace Selection Card
        User->>Bot: Selects Workspace
        Bot->>DB: Save Workspace Preference
    end
    
    Bot->>Genie: Fetch Genie Spaces
    Genie-->>Bot: List of Spaces
    Bot-->>User: Sends Genie Spaces Adaptive Card
```

### Scenario 2: Entra ID Security Group Scoping (Machine-to-Machine / M2M)
*(Triggered if global `DATABRICKS_TOKEN`, global `DATABRICKS_CLIENT_ID`, and U2M OAuth are NOT configured)*
1. **Group Resolution**: The bot queries Microsoft Graph API to find the user's Azure AD group memberships.
2. **Scope Selection**: 
   - If the user belongs to *multiple* mapped security groups, the bot sends an Adaptive Card asking them to select an "Access Scope" (e.g., Finance-Dev vs. Finance-Prod).
   - If the user belongs to only *one* mapped group, it silently defaults to that scope.
3. **Listing Spaces**: The bot uses the M2M Service Principal tied to the selected scope to fetch the Genie Spaces.

```mermaid
sequenceDiagram
    actor User as Teams User
    participant Bot as Teams Genie Bot
    participant Graph as MS Graph API
    participant DB as Database
    participant Genie as Genie API

    User->>Bot: "list genie spaces"
    Bot->>Graph: Fetch User's Azure AD Groups
    Graph-->>Bot: Returns List of Group Object IDs
    Bot->>DB: Match Group IDs to M2M Scopes
    
    alt Multiple Scopes Found
        Bot-->>User: Sends Scope Selection Card
        User->>Bot: Selects Scope
        Bot->>DB: Save Scope Preference
    end
    
    Bot->>Genie: Fetch Spaces (using matched M2M token)
    Genie-->>Bot: List of Spaces
    Bot-->>User: Sends Genie Spaces Adaptive Card
```

### Scenario 3: Global Authentication
*(Triggered if `DATABRICKS_TOKEN` or global M2M client ID/secret is configured and no advanced auth is set)*
1. **Listing Spaces**: The bot skips all user prompts and immediately fetches the Genie Spaces using the globally configured service principal or PAT.

```mermaid
sequenceDiagram
    actor User as Teams User
    participant Bot as Teams Genie Bot
    participant Genie as Genie API

    User->>Bot: "list genie spaces"
    Note over Bot, Genie: Uses global token/M2M credentials
    Bot->>Genie: Fetch Spaces
    Genie-->>Bot: List of Spaces
    Bot-->>User: Sends Genie Spaces Adaptive Card
```

---

### Asking Questions

Once the authentication flow is complete and the spaces are listed:
1. **Select a Space**: Click on one of the available Databricks Genie spaces returned in the Adaptive Card.
2. **Ask Questions**: Type your query naturally! 
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
*   **`storages/`**:
    *   **`s3_storage.py`**: Custom S3-compatible backend implementation for the Bot Framework's `Storage` protocol, enabling scalable state caching.
    *   **Azure Cosmos DB**: Natively supported via `microsoft-agents-storage-cosmos`.
    *   **Azure Blob Storage**: Natively supported via `microsoft-agents-storage-blob`.
*   **`database/`**:
    *   `database.py`: Handles async SQL connection pooling via `sqlalchemy.ext.asyncio`.
    *   `db_models.py`: Defines the `SQLModel` schemas for the bot.
*   **`utils/`**:
    *   `llm_summarizer.py`: Orchestrates the `ChatOpenAI` calls to the Databricks Model Serving endpoint. Includes resilient fallback logic for rate limits.
    *   `user_group.py`: Handles OAuth flow with Microsoft Graph to determine Entra ID group memberships.
    *   `encryption.py`: Provides symmetric encryption using Fernet for secure token storage.

---

## 🗄️ Database Models

The bot uses SQLModel to manage four core tables that track user sessions, multi-tenant access, and auditing:

1.  **`GenieSpace`**: Caches the Databricks Genie spaces accessible to a user. This prevents hitting the Databricks API repeatedly when a user lists their spaces.
2.  **`UserSelection`**: Acts as the active session tracker. It stores the `user_id` along with the currently selected `space_id`, the active `conversation_id` for continuous chat threads, and the chosen `user_group_id` for scoping credentials.
3.  **`SecurityGroupMapping`**: A configuration table mapping Microsoft Entra ID (Azure AD) security group Object IDs to specific Databricks Service Principal credentials (`databricks_client_id` and `databricks_client_secret`). This ensures strict data segregation across different enterprise groups.
4.  **`GenieAuditLog`**: An auditing table (`genie_audit_logs`) that logs user queries, Databricks SQL responses, execution times, and session context to monitor usage and exceptions.
5.  **`UserToken`**: Stores and auto-refreshes Databricks custom OAuth access and refresh tokens per user for interactive authentication flows.

---

## 🤝 Contributing

Contributions are heavily encouraged! When submitting Pull Requests, please ensure:
1. You have documented any new functions using **Google-style docstrings**.
2. You handle exceptions gracefully, keeping the end-user experience in mind.
3. You maintain the `async` nature of the codebase to preserve scalability.
