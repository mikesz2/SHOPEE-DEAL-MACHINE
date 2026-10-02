from tests.test_command_center import client
from app.services.whatsapp import WhatsAppPublisher


def test_channel_settings_validate_groups_and_preserve_on_policy_save(client,monkeypatch):
    c,_=client
    async def groups(self):return [{'id':'123@g.us','name':'Meu grupo'}]
    monkeypatch.setattr(WhatsAppPublisher,'groups',groups)
    policy=c.get('/api/settings').json()
    ch={'telegram_publish_enabled':False,'whatsapp_enabled':True,'whatsapp_groups':['123@g.us'],'whatsapp_interval_seconds':30}
    assert c.put('/api/channels',json=ch).status_code==200
    assert c.put('/api/settings',json=policy).status_code==200
    assert c.get('/api/channels').json()['whatsapp_groups']==['123@g.us']
    ch['whatsapp_groups']=['999@g.us']
    assert c.put('/api/channels',json=ch).status_code==422
    ch['whatsapp_groups']=['5511999999']
    assert c.put('/api/channels',json=ch).status_code==422
    ch['whatsapp_groups']=[]
    assert c.put('/api/channels',json=ch).status_code==422


def test_whatsapp_endpoints_require_login(client,monkeypatch):
    from app.config import settings
    c,_=client
    monkeypatch.setattr(settings,'app_require_auth',True)
    assert c.get('/api/whatsapp/groups').status_code==401
    assert c.post('/api/whatsapp/connect').status_code==401
    assert c.get('/api/deliveries').status_code==401
