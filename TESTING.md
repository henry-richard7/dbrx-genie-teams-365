# Testing Guide for Databricks Genie Teams Bot

This project uses `pytest` alongside `pytest-asyncio` and `pytest-mock` to ensure code reliability without depending on live cloud resources during test execution. 

This guide explains how to run tests, write new ones, and mock the external services used by the bot.

## Running Tests

All tests are located in the `tests/` directory.

**Run all tests:**
```bash
uv run pytest -v
```

**Run tests in a specific file:**
```bash
uv run pytest tests/modules/test_genie.py -v
```

**Run a specific test function:**
```bash
uv run pytest tests/modules/test_genie.py::test_genie_lazy_workspace_client -v
```

**Run tests with code coverage (requires `pytest-cov`):**
```bash
uv run pytest --cov=handlers --cov=modules --cov=utils --cov=database -v
```

## Writing Asynchronous Tests

Because the bot uses FastAPI and `asyncio`, most of our functions are asynchronous.

1. **Mark tests as async:** Use the `@pytest.mark.asyncio` decorator for any test that needs to `await` a function.
2. **Configuration:** Our `pyproject.toml` is configured with `asyncio_mode = "auto"`, meaning `pytest-asyncio` will automatically handle test coroutines, but it is best practice to include the decorator.

```python
import pytest

@pytest.mark.asyncio
async def test_my_async_function():
    result = await my_async_function()
    assert result is True
```

## Mocking External Services

The bot interacts heavily with Microsoft Teams (Bot Framework), Databricks SDK, and Langchain (OpenAI). To prevent test flakiness and avoid hitting live endpoints, you must mock these calls using `pytest-mock` (`unittest.mock.patch`).

### 1. Mocking the Databricks WorkspaceClient

When testing modules that hit Databricks (like `modules/genie.py`), intercept the `WorkspaceClient` initialization to prevent it from trying to authenticate.

```python
import pytest
from unittest.mock import MagicMock, patch
from modules.genie import Genie

@pytest.fixture
def mock_workspace_client():
    with patch("modules.genie.WorkspaceClient") as mock:
        yield mock

def test_genie_initialization(mock_workspace_client):
    # Setup mock returns
    mock_instance = MagicMock()
    mock_workspace_client.return_value = mock_instance
    
    genie = Genie()
    client = genie.workspace_client
    
    # Assert it initialized without errors and didn't hit network
    mock_workspace_client.assert_called_once()
```

### 2. Mocking Langchain / LLM Endpoints

When testing the AI summarization logic (`utils/llm_summarizer.py`), you should mock the `invoke` method of `ChatOpenAI`.

```python
import pytest
from unittest.mock import MagicMock, patch
from utils.llm_summarizer import LlmSummarizer

@pytest.fixture
def mock_chat_openai():
    with patch("utils.llm_summarizer.ChatOpenAI") as mock:
        yield mock

def test_summarize_success(mock_chat_openai):
    # 1. Setup the mock
    mock_instance = MagicMock()
    mock_chat_openai.return_value = mock_instance
    
    # 2. Define the fake response
    mock_response = MagicMock()
    mock_response.content = '{"text": "Fake summary", "chart": null}'
    mock_instance.invoke.return_value = mock_response
    
    # 3. Run the method
    summarizer = LlmSummarizer()
    result = summarizer.summarize([{"name": "col"}], [["val"]], "query")
    
    # 4. Assert behavior
    assert result["text"] == "Fake summary"
```

### 3. Testing with a Database

For testing the `Database` class, we use `aiosqlite` with an in-memory database (`sqlite+aiosqlite:///:memory:`). This ensures tests are isolated and extremely fast. A fixture for this is already provided in `tests/database/test_database.py`.

```python
import pytest
import pytest_asyncio
from database.database import Database

@pytest_asyncio.fixture
async def memory_db():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_tables()
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_database_logic(memory_db: Database):
    await memory_db.add_user_selection("user1", "space1", "Name", "conv1")
    selection = await memory_db.get_user_selection("user1")
    assert selection.space_id == "space1"
```

## Adding New Test Files

When creating new test files:
* Place them in the `tests/` directory matching the source folder structure (e.g., `tests/handlers/test_message_handler.py`).
* Prefix your test file name with `test_`.
* Prefix all your test functions with `test_`.
