import pytest
import json
from unittest.mock import MagicMock, patch
from utils.llm_summarizer import LlmSummarizer


def test_dataframe_to_text():
    # Arrange
    columns = [{"name": "product"}, {"name": "sales"}]
    data = [["apple", 100], ["banana", 150]]

    # Act
    result = LlmSummarizer.dataframe_to_text(columns, data)

    # Assert
    assert "| product | sales |" in result
    assert "| apple | 100 |" in result
    assert "| banana | 150 |" in result


def test_dataframe_to_text_empty():
    assert LlmSummarizer.dataframe_to_text([], []) == ""


@pytest.fixture
def mock_chat_openai():
    with patch("utils.llm_summarizer.ChatOpenAI") as mock:
        yield mock


def test_summarize_success(mock_chat_openai, monkeypatch):
    # Arrange
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    summarizer = LlmSummarizer()

    # Mock the LLM response
    mock_instance = MagicMock()
    mock_chat_openai.return_value = mock_instance

    mock_response = MagicMock()
    mock_response.content = (
        '```json\n{"text": "Summary text", "chart": "Chart.VerticalBar"}\n```'
    )
    mock_instance.invoke.return_value = mock_response

    columns = [{"name": "col1"}]
    data = [["val1"]]
    question = "What is this?"

    # Act
    result = summarizer.summarize(columns, data, question)

    # Assert
    assert result["text"] == "Summary text"
    assert result["chart"] == "Chart.VerticalBar"
    mock_instance.invoke.assert_called_once()


def test_summarize_rate_limit(mock_chat_openai, monkeypatch):
    # Arrange
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    summarizer = LlmSummarizer()

    # Mock the LLM response throwing an exception
    mock_instance = MagicMock()
    mock_chat_openai.return_value = mock_instance
    mock_instance.invoke.side_effect = Exception("Rate limit reached")

    # Act
    result = summarizer.summarize([{"name": "col1"}], [["val1"]], "test")

    # Assert
    assert "AI Insights Unavailable" in result["text"]
    assert result["chart"] is None
