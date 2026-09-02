import pytest
from microsoft_agents.hosting.core import UserState, MemoryStorage, TurnContext
from microsoft_agents.activity import Activity, ChannelAccount, ConversationAccount
from microsoft_agents.hosting.fastapi import CloudAdapter

@pytest.mark.asyncio
async def test_memory_storage_user_state():
    storage = MemoryStorage()
    user_state = UserState(storage)
    tc = TurnContext(CloudAdapter(), Activity(type='message', channel_id='msteams', from_property=ChannelAccount(id='123'), conversation=ConversationAccount(id='conv1')))
    
    prop = user_state.create_property('UserTokenProperty')
    await prop.set(tc, {'access_token': 'ABC'})
    await user_state.save(tc)
    
    value = await prop.get(tc)
    assert value == {'access_token': 'ABC'}


def test_s3_storage_disable_signing_explicit_true():
    from storages.s3_storage import S3Storage

    storage = S3Storage(
        bucket_name="test-bucket",
        endpoint_url="http://localhost:9000",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        create_bucket_if_not_exists=False,
        disable_signing=True,
    )
    assert storage._s3.meta.config.signature_version == "s3v4"
    assert storage._s3.meta.config.s3 == {
        "addressing_style": "path",
        "payload_signing_enabled": False,
    }


def test_s3_storage_disable_signing_explicit_false():
    from storages.s3_storage import S3Storage

    storage = S3Storage(
        bucket_name="test-bucket",
        endpoint_url="http://localhost:9000",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        create_bucket_if_not_exists=False,
        disable_signing=False,
    )
    assert storage._s3.meta.config.s3 is None or storage._s3.meta.config.s3.get("payload_signing_enabled") is not False


def test_s3_storage_disable_signing_from_env(monkeypatch):
    from storages.s3_storage import S3Storage

    monkeypatch.setenv("S3_DISABLE_SIGNING", "true")
    storage = S3Storage(
        bucket_name="test-bucket",
        endpoint_url="http://localhost:9000",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        create_bucket_if_not_exists=False,
    )
    assert storage._s3.meta.config.signature_version == "s3v4"
    assert storage._s3.meta.config.s3 == {
        "addressing_style": "path",
        "payload_signing_enabled": False,
    }

