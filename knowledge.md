# Databricks Genie Teams Bot - Codebase Knowledge Base

This document serves as a comprehensive guide to the Databricks Genie Teams Bot codebase. It is designed to provide AI agents and developers with deep context regarding the architecture, technical stack, features, directory structure, and database models of the project.

## 1. Project Overview

The **Databricks Genie Teams Bot** is a production-ready Microsoft Teams bot built to provide natural language data analytics, AI-driven insights, and rich data visualizations directly within a Teams chat interface. It acts as intelligent middleware between Microsoft Teams and the Databricks ecosystem, specifically leveraging Databricks Genie for text-to-SQL generation.

### Key Features
*   **Natural Language Queries:** Allows users to ask plain-English questions about data.
*   **Rich Visualizations & Adaptive Cards:** Generates interactive charts (bar, donut, stacked) and data tables using Microsoft Adaptive Cards.
*   **AI Summarization:** Uses Databricks-hosted LLMs (or compatible endpoints like OpenAI) to summarize data and propose "Next Best Actions".
*   **Excel Export:** Automatically generates downloadable Excel files for datasets exceeding 100 rows to bypass Teams API limits.
*   **Multi-Tenant & Scoped Access Control:** Dynamically resolves user credentials using Microsoft Entra ID (Azure AD) security groups, mapping them to scoped Databricks Service Principals. Also supports Interactive User-Specific Custom OAuth (U2M) at both the Workspace-level and Account-level, providing a dynamic workspace selection flow and automated background token refresh.
*   **Scalable & Asynchronous:** Built with FastAPI, AsyncIO, and SQLModel/aiosqlite (or asyncpg for Postgres) to handle concurrent requests without blocking.

## 2. Technology Stack

*   **Language:** Python 3.13+
*   **Web Framework:** FastAPI (with Uvicorn as the ASGI server)
*   **Bot Framework:** Botbuilder (Microsoft Bot Framework SDK)
*   **Database ORM:** SQLModel (SQLAlchemy under the hood)
*   **Database Engines:** SQLite (local via `aiosqlite`), PostgreSQL/Azure SQL (production via `asyncpg`)
*   **Asynchronous Processing:** `asyncio`
*   **Package Management:** `uv`
*   **LLM Integration:** `langchain` / `openai` client (Compatible with Databricks Model Serving)

## 3. Directory Structure & File Roles

The codebase is highly modularized into distinct directories based on their functional responsibilities.

### Root Directory Files
*   **`main.py`**: The FastAPI entry point. It handles app initialization, Uvicorn startup, database lifecycle events, and defines the core HTTP routing for the Bot Framework.
*   **`config.py`**: Handles configuration management and loads environment variables from `.env`.
*   **`pyproject.toml` / `uv.lock`**: Python project configuration and dependency locking managed by `uv`.
*   **`.env` / `.env.example`**: Environment variable definitions for Azure, Teams, Databricks, LLMs, and Database settings.
*   **`README.md`**: Main project documentation.
*   **`CONTRIBUTING.md` / `TESTING.md`**: Guidelines for contributing to and testing the repository.

### `bot/` (Bot Core)
*   **`bot.py`**: Implementation of `TeamsActivityHandler`. Captures incoming messages from MS Teams and routes them to the appropriate conversational handlers (e.g., `MessageHandler`).

### `handlers/` (Business Logic & Conversational Handlers)
*   **`message_handler.py`**: The core router for text inputs. Manages conversational state, interprets user commands, and triggers the AI insights and Databricks execution pipeline.
*   **`genie_list_handler.py`**: Responsible for querying, fetching, and rendering available Databricks Genie spaces as Adaptive Cards to the user.
*   **`file_card_handler.py`**: Manages the MS Teams file consent workflow. Used when exporting large datasets to Excel files and requesting user permission to upload the file to their OneDrive/Sharepoint.

### `modules/` (Core Integrations & UI Factories)
*   **`genie.py`**: A wrapper around the Databricks SDK (`WorkspaceClient` and `GenieAPI`). Handles execution of NL queries against Databricks spaces.
*   **`AdaptiveCardTemplate.py`**: A utility factory responsible for dynamically generating complex JSON Adaptive Cards for MS Teams, including tables, code blocks, and visual charts.

### `storages/` (State Storage)
*   **`s3_storage.py`**: Custom S3-compatible storage backend (AWS S3, MinIO) for Bot Framework's `Storage` protocol, enabling scalable distributed caching of conversational and user state.
*   **Azure Cosmos DB**: Natively supported via `microsoft-agents-storage-cosmos` for enterprise-grade partitioned state storage using Managed Identities.
*   **Azure Blob Storage**: Natively supported via `microsoft-agents-storage-blob` for persistent storage using Managed Identities.

### `database/` (Data Persistence)
*   **`database.py`**: Manages the async SQL connection pool and session lifecycle via `sqlalchemy.ext.asyncio`.
*   **`db_models.py`**: Defines the `SQLModel` schemas representing database tables.

### `utils/` (Helper Utilities)
*   **`llm_summarizer.py`**: Orchestrates LLM calls to Databricks Model Serving or OpenAI. Generates summaries, picks chart types, and handles rate limiting and fallback logic.
*   **`chart_card_generator.py`**: Logic for analyzing dataset responses and translating them into configurations for chart rendering within Adaptive Cards.
*   **`user_group.py`**: Handles OAuth flow with Microsoft Graph API to determine a user's Entra ID (Azure AD) group memberships for scoped Databricks access.
*   **`oauth_handler.py`**: Manages the custom OAuth Authorization Code flow for users authenticating directly with Databricks, including automatic token refresh.
*   **`encryption.py`**: Provides symmetric encryption using Fernet to securely encrypt OAuth tokens at rest.
*   **`bot_utils.py`**: Miscellaneous utility functions used throughout the bot.
*   **`sync_lru_cache_async.py`**: Provides asynchronous caching mechanisms to avoid repetitive expensive calls.

### `tests/`
*   Contains the asynchronous test suite using `pytest`. Verifies codebase integrity and mocks API calls.

## 4. Database Schema (Models)

The application utilizes SQLModel to track user sessions, multi-tenant mappings, and telemetry. The models defined in `db_models.py` typically represent:

1.  **`GenieSpace`**: Caches the Databricks Genie spaces accessible to a user to reduce redundant API calls to Databricks when users request a list of spaces.
2.  **`UserSelection`**: Acts as the active session tracker. Stores `user_id`, active `conversation_id`, the currently selected `space_id`, and `user_group_id` for scoping.
3.  **`SecurityGroupMapping`**: Configuration table that maps Microsoft Entra ID Group Object IDs to specific Databricks Service Principal credentials (`client_id` and `client_secret`). This enforces strict data segregation based on a user's enterprise group.
4.  **`GenieAuditLog`**: Auditing table (`genie_audit_logs`) that records user queries, generated SQL, execution times, and session contexts for monitoring and troubleshooting.
5.  **`UserToken`**: Stores user-specific Databricks Custom OAuth credentials (`access_token`, `refresh_token`, and `expires_at`). These tokens are **encrypted at rest** using Fernet symmetric encryption. The bot automatically uses the refresh token to renew expired access tokens seamlessly before querying Databricks.

### 4.1 User & Session Tracking Mechanics
Because Microsoft Teams is a stateless conversational interface, the bot must reconstruct the user's state and context on every incoming message. This is achieved through a combination of Bot Framework identifiers and Database state management.

1. **Identity Extraction:** Every message sent to the bot contains an `Activity` payload. The bot extracts two critical identifiers from `turn_context.activity`:
   * `aadObjectId`: The immutable, cryptographically guaranteed Azure AD Object ID of the user. This is the ultimate source of truth for *who* the user is, used for Entra ID group resolution.
   * `from_property.id`: The specific Microsoft Teams channel or 1:1 chat user ID. Used for routing messages back.
   * `conversation.id`: A unique ID representing the specific chat thread (a 1:1 chat, a group chat, or a channel thread).
2. **Session Hydration (`UserSelection`):**
   * Before processing any command, the bot performs a database lookup on the `UserSelection` table using the **composite key** of `user_id` (usually mapped to `aadObjectId`) AND `conversation_id`.
   * **Why `conversation_id` is crucial:** A single user might be talking to the bot in a 1:1 chat (analyzing HR data) and simultaneously in a Project Group chat (analyzing Engineering data). Tying the session to the `conversation_id` ensures that the active Databricks environment (`space_id`) and scope (`user_group_id`) remain isolated to the specific thread where they were selected, preventing "context bleed" across different Teams chats.
3. **Continuous State Management:**
   * When a user selects a space or scope, the bot either inserts or updates the record in `UserSelection` for that specific `(user_id, conversation_id)` pair.
   * When the user asks a subsequent natural language question, the bot fetches this record to know exactly which Databricks Service Principal to use and which Genie space to query, providing a seamless, continuous conversational experience without forcing the user to re-authenticate or re-select their space for every question.

### 4.2 Auditing & Telemetry
In an enterprise environment, it is critical to maintain a history of what data was accessed, by whom, and what queries were executed. The bot handles this through the `GenieAuditLog` table.
* **Comprehensive Logging:** Every time a user executes a natural language query against a Genie Space using M2M or Global Auth, a new record is asynchronously inserted into the `genie_audit_logs` table.
* **U2M Bypass:** If the user is authenticated via Interactive Custom OAuth (U2M), the bot *bypasses* the local `GenieAuditLog` insertion. This is because Databricks natively logs the executed SQL queries under the user's actual human identity in the Databricks Query History, making redundant local logging unnecessary.
* **Context Capture:** For M2M queries, the log captures the user's `user_id` (AAD Object ID), the `conversation_id`, the `space_id` that was queried, and the `user_group_id` (the active scope/role).
* **Query Details:** It records both the original natural language question asked by the user and the actual, generated Databricks SQL that was executed against the database.
*   **Performance & Error Tracking:** The table logs the `execution_time_ms` (how long Databricks took to respond) and the `status` (e.g., SUCCESS, ERROR). If an error occurs, the exception message is also captured.
*   **Value:** This data allows administrators to monitor usage patterns, identify slow or failing queries, ensure users are not attempting unauthorized access, and track exactly how AI models are interpreting user prompts into SQL.

### 4.3 Distributed File Caching (Excel Exports)
To bypass Microsoft Teams Adaptive Card size limits and ensure performance, large Databricks SQL responses (>100 rows) are converted into downloadable `.xlsx` Excel files. This requires a secure, two-step file consent flow with the user.
*   **Storage Injection:** To prevent Out-Of-Memory (OOM) crashes on large payloads in multi-pod deployments, the bot does not keep these large byte buffers in local Python dictionary memory. Instead, the `FileCardHandler` injects the native Bot Framework `Storage` provider (such as the custom `S3Storage` backend).
*   **Base64 Offloading:** When a large query completes, the raw Excel bytes are `base64` encoded and written entirely to the configured distributed storage (e.g., AWS S3, MinIO) mapped to a unique `file_<id>` key.
*   **Just-In-Time Delivery & Cleanup:** When the user clicks "Accept" on the Teams file consent card, the bot securely retrieves the `base64` string from S3, decodes it, uploads it to OneDrive/SharePoint via the Bot Framework API, and immediately deletes the payload from S3 to ensure no stale data remains persisted.
*   **Fallback:** If `USE_CONTEXT` is disabled, it safely falls back to storing the bytes locally in a class-level dictionary (`FileCardHandler._pending_files`).

## 5. Multi-Scope Authentication Explained
The bot is designed to serve as a centralized interface for multiple enterprise teams (e.g., HR, Finance, Engineering), each with its own distinct Databricks environments and strict data access privileges. To securely enforce these data boundaries, the bot employs a **Multi-Scope Authentication** model. 

Here is the detailed breakdown of the mechanism:
1. **Authenticated Identity Context:** When a user interacts with the bot, Microsoft Bot Framework provides a cryptographically verified payload containing the user's Microsoft Teams/Azure AD Object ID (`aadObjectId`). This prevents identity spoofing at the transport layer.
2. **Azure AD Group Resolution:** The bot takes this verified `aadObjectId` and queries the Microsoft Graph API to dynamically fetch all Microsoft Entra ID (Azure AD) security groups the user is a member of.
3. **Database Mapping (`SecurityGroupMapping`):** The system cross-references the user's Entra ID group Object IDs against the `SecurityGroupMapping` database table. This table acts as the source of truth, mapping specific Entra ID groups to specific **Databricks Service Principal OAuth Credentials** (`client_id` and `client_secret`).
4. **Dynamic Scoping & Session State:** If a user belongs to multiple mapped groups (e.g., they are in both Finance and HR groups), the bot prompts them to explicitly select an active "scope" (environment) for their current session. This selection is persisted in the `UserSelection` table.
5. **Execution Context Injection:** When a user asks a data question, the bot retrieves the `client_id` and `client_secret` corresponding to their active scope. All Databricks SDK calls (like initializing the `WorkspaceClient`) dynamically use these credentials. This guarantees that users can only query Databricks Genie spaces that their Service Principal is explicitly authorized to view, completely avoiding the use of global, over-privileged static tokens.

### 5.2 Protection Against IDOR & Impersonation
In systems where users can select their scope or workspace, there is a risk of **Insecure Direct Object Reference (IDOR)** or **Impersonation**. This occurs if a malicious user manually modifies their request or database state to specify a `user_group_id` or `space_id` they do not own.

The bot mitigates this through strict server-side validation:
* **No Trust in Client State:** The bot never trusts a user's claim to a group or space. Even if a user somehow manipulates the `UserSelection` table to inject a target `user_group_id` belonging to an executive team, the bot intercepts this.
* **Just-In-Time Authorization:** Before executing *any* Databricks query, the bot re-verifies that the `user_group_id` requested in the `UserSelection` actually exists in the live list of groups returned by the Microsoft Graph API for that specific user's `aadObjectId`.
*   **Access Denied:** If the requested group ID is not found in the user's Graph API results, the bot throws an authorization exception and denies the query, preventing the IDOR attack. Users cannot impersonate other roles or access isolated data spaces.

### 5.3 Interactive User-Specific Custom OAuth (U2M)
For environments where users should authenticate directly with their own Databricks accounts rather than using a Service Principal, the bot supports a full interactive OAuth flow:
1. **Interactive Login**: When users interact with the bot, if they are not authenticated, they receive an Adaptive Login Card with a unique Authorization URL.
2. **Authorization Code Flow**: The user completes the login in their browser. The Databricks Account Console redirects back to the bot's `/api/oauth/callback` endpoint with an authorization code.
3. **Workspace Selection (Account-Level Only)**: If Account-Level authentication is configured (`DATABRICKS_ACCOUNT_HOST` and `DATABRICKS_ACCOUNT_ID`), the bot dynamically fetches the list of available workspaces via the Databricks Account API. It presents these to the user via an Adaptive Card, and the chosen workspace URL is saved to their active session.
4. **Token Exchange & Caching**: The bot exchanges the code for an `access_token` and `refresh_token`. These tokens are encrypted using `TokenEncryptor` and cached alongside an `expires_at` timestamp in the `UserToken` table (or in Bot Framework State memory, which can be backed by S3).
5. **Automated Refresh**: Before making any Databricks SDK calls, the `message_handler` checks the `expires_at` timestamp. If the token is expired, it uses `oauth_handler.refresh_token` to automatically renew it in the background, ensuring continuous access without requiring the user to manually log in every hour.

## 6. Architecture & Request Flow

1.  **Authentication & Scoping:** A user sends a message. The bot determines the authentication path based on its configuration:
    *   **U2M Interactive OAuth:** If `DATABRICKS_OAUTH_CLIENT_ID` is set, the user authenticates directly with Databricks via their browser. The bot caches and auto-refreshes their specific tokens, optionally prompting for Workspace selection if Account-Level Auth is enabled.
    *   **M2M Entra ID Scoping:** If global auth and U2M are NOT configured, the bot queries MS Graph API to resolve the user's Azure AD groups, mapping them to specific Databricks Service Principals via the `SecurityGroupMapping` table. It prompts the user if they belong to multiple mapped groups.
    *   **Global Auth:** Uses a globally configured `DATABRICKS_TOKEN` or Service Principal, bypassing user-specific scoping.
2.  **Genie Execution:** The bot passes the user's plain-English question to the Databricks Genie API using the resolved credentials. Genie executes the text-to-SQL pipeline and returns raw data.
3.  **AI Insights (Optional):** The raw data is sent to an LLM endpoint (via `llm_summarizer.py`) to generate a natural language summary and determine the most appropriate chart type.
4.  **UI Generation:** The `AdaptiveCardTemplate` constructs a rich UI payload containing the summary, dynamic chart, and tabular data.
5.  **Delivery:** The bot replies to the Teams user. If the data exceeds 100 rows, it triggers the `file_card_handler` to negotiate a file upload for an Excel export instead of rendering an massive inline table.

## 6. Setup & Configuration Checklist
- Ensure `uv` is used for package management (`uv sync`).
- Environment variables must be configured in `.env` (Azure AD details, MS Teams Bot ID/Secret, Databricks Host, Database URL, Token Encryption Key, and S3 Storage vars if using distributed state).
- Requires Microsoft Graph API permissions: `GroupMember.Read.All`, `User.Read.All`.
- Can run locally using SQLite/MemoryStorage or scale via PostgreSQL and S3Storage. Start the bot with `uv run python main.py`.
