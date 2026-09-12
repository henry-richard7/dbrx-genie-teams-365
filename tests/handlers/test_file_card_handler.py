import pytest
from handlers.file_card_handler import FileCardHandler


@pytest.mark.asyncio
async def test_file_card_handler_temp_disk_save_and_get_delete(monkeypatch):
    monkeypatch.setenv("USE_CONTEXT", "false")
    handler = FileCardHandler(storage=None)

    file_id = "test_uuid_123"
    test_bytes = b"sample_excel_content"

    # Save to temp disk
    await handler._save_file_bytes(file_id, test_bytes)

    temp_path = handler._get_temp_file_path(file_id)
    assert temp_path.exists()
    assert temp_path.read_bytes() == test_bytes

    # Get and delete upon download
    retrieved = await handler._get_and_delete_file_bytes(file_id)
    assert retrieved == test_bytes

    # Ensure file is removed from disk
    assert not temp_path.exists()


@pytest.mark.asyncio
async def test_file_card_handler_temp_disk_delete_on_decline(monkeypatch):
    monkeypatch.setenv("USE_CONTEXT", "false")
    handler = FileCardHandler(storage=None)

    file_id = "test_uuid_456"
    test_bytes = b"declined_excel_content"

    await handler._save_file_bytes(file_id, test_bytes)
    temp_path = handler._get_temp_file_path(file_id)
    assert temp_path.exists()

    # Delete upon decline
    await handler._delete_file_bytes(file_id)
    assert not temp_path.exists()
