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
