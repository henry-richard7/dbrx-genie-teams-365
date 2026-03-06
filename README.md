# Databricks Genie Teams Bot 🧞‍♂️

A powerful Microsoft Teams bot that interfaces with Databricks Genie to provide natural language data analytics, AI-driven insights, and seamless data visualization directly within your chat.

## 🌟 Features

- **Natural Language Queries**: Ask questions about your data in plain English (e.g., _"What were the sales last week?"_).
- **Genie Spaces Integration**: Browse and select from available Databricks Genie spaces directly in Teams.
- **AI Summarization**: Automatically generates concise summaries and "Next Best Actions" using Databricks-hosted LLMs.
- **Rich Visualizations**: Displays query results in formatted Adaptive Cards.
- **Excel Export**: Automatically converts large datasets (>100 rows) into downloadable Excel files.
- **Scoped Access Control**: Supports dynamic credential loading based on user security groups (Microsoft Entra ID) for secure, multi-tenant data access.

## 📋 Prerequisites

- Python 3.10+
- A Databricks Workspace with Genie enabled.
- Microsoft Teams App Registration (Azure Bot Service).
- Microsoft Graph API permissions (for user group resolution).

## 🛠 Configuration

Create a `.env` file in the root directory with the following configurations:

### Azure / Teams Bot Settings

```ini
# Azure AD App Registration details
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID=<Your_Tenant_ID>
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID=<Your_App_Client_ID>
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET=<Your_App_Client_Secret>

# Optional: Port configuration (default: 3978)
PORT=3978
```

### Databricks Settings

```ini
# LLM Endpoint for summarization (default: databricks-qwen3-next-80b-a3b-instruct)
DATABRICKS_LLM_ENDPOINT=databricks-qwen3-next-80b-a3b-instruct

# Optional: Global Databricks Token (if not using scoped credentials)
# DATABRICKS_TOKEN=<Personal_Access_Token>
# DATABRICKS_HOST=<Workspace_Url>
```

## 🚀 Running the Bot

1. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Server**:
   ```bash
   python main.py
   ```
   The bot will start on port `3978` (or the port defined in `.env`).

## 🤖 Usage

### Basic Commands

- **`list genie spaces`**: Lists all available Genie spaces you have access to.
  - _Note_: The bot uses fuzzy matching, so "show genie spaces" also works.

### Interaction Flow

1. **Select Scope**: If you belong to multiple security groups mapped to different Databricks service principals, the bot will ask you to select a scope.
2. **Select Space**: Click on a space from the list provided by the bot.
3. **Ask Questions**: Type your query naturally.
   - **Small Results**: Displayed directly in the chat as a table.
   - **Large Results**: Provided as a downloadable Excel file.
   - **Insights**: Every response includes an AI-generated summary and recommendation.

## 📂 Project Structure

- **`main.py`**: Entry point, FastAPI app, and Bot Adapter setup.
- **`handlers/`**: Contains logic for processing messages, file uploads, and Genie interactions.
- **`utils/llm_summarizer.py`**: Handles LLM interaction for summarizing data trends.
- **`database/`**: Manages user state and space mappings.
- **`modules/`**: Core Genie API and Adaptive Card templates.

## 🤝 Contributing

Contributions are welcome! Please ensure you update tests and documentation as appropriate.
