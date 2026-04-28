import pytest
from unittest.mock import MagicMock, patch
from modules.genie import Genie

@pytest.fixture
def mock_workspace_client():
    with patch("modules.genie.WorkspaceClient") as mock:
        yield mock

def test_genie_initialization(monkeypatch):
    # Arrange
    monkeypatch.setenv("DATABRICKS_HOST", "https://test-host")
    monkeypatch.setenv("DATABRICKS_TOKEN", "test-token")
    
    # Act
    genie = Genie()
    
    # Assert
    assert genie._databricks_host == "https://test-host"
    assert genie._databricks_token == "test-token"

def test_genie_lazy_workspace_client(monkeypatch, mock_workspace_client):
    # Arrange
    monkeypatch.setenv("DATABRICKS_HOST", "https://test-host")
    monkeypatch.setenv("DATABRICKS_TOKEN", "test-token")
    
    mock_instance = MagicMock()
    mock_workspace_client.return_value = mock_instance
    
    genie = Genie()
    
    # Act
    client = genie.workspace_client
    
    # Assert
    mock_workspace_client.assert_called_once_with(host="https://test-host", token="test-token")
    assert client == mock_instance
    
    # Calling it again shouldn't re-initialize
    genie.workspace_client
    mock_workspace_client.assert_called_once()
