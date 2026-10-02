"""Evolution API v2 adapter. Credentials stay on the server; no implicit retries."""
import html
import re
from urllib.parse import quote
import httpx
from app.config import settings


class DeliveryUncertain(RuntimeError):
    """Provider may have accepted the message. Human reconciliation is required."""


class WhatsAppPublisher:
    @property
    def configured(self):
        return bool(settings.evolution_url and settings.evolution_api_key and settings.evolution_instance)

    async def request(self, method, path, payload=None):
        if not self.configured:
            raise RuntimeError('Configure EVOLUTION_URL, EVOLUTION_API_KEY e EVOLUTION_INSTANCE no servidor')
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(method, settings.evolution_url.rstrip('/') + '/' + path,
                headers={'apikey': settings.evolution_api_key}, json=payload)
        if response.status_code >= 400:
            # Do not expose credentials, response bodies or internal URLs in the dashboard.
            raise RuntimeError(f'Evolution retornou HTTP {response.status_code}')
        return response.json()

    def path(self, route):
        return route + '/' + quote(settings.evolution_instance, safe='')

    async def status(self):
        if not self.configured:
            return {'configured': False, 'state': 'not_configured'}
        data = await self.request('GET', self.path('instance/connectionState'))
        return {'configured': True, 'state': (data.get('instance') or {}).get('state', 'unknown')}

    async def connect(self):
        data = await self.request('GET', self.path('instance/connect'))
        return {'base64': data.get('base64') or (data.get('qrcode') or {}).get('base64'),
                'pairingCode': data.get('pairingCode')}

    async def groups(self):
        data = await self.request('GET', self.path('group/fetchAllGroups') + '?getParticipants=false')
        if not isinstance(data, list):
            raise RuntimeError('Resposta inesperada ao listar grupos Evolution')
        return [{'id': x['id'], 'name': x.get('subject') or x['id'], 'size': x.get('size')}
                for x in data if str(x.get('id', '')).endswith('@g.us')]

    async def publish(self, group, caption, affiliate_url, image_url=None):
        if not re.fullmatch(r'[0-9-]+@g\.us', group):
            raise ValueError('Destino WhatsApp precisa ser um grupo válido')
        text = html.unescape(re.sub(r'<[^>]+>', '', caption))
        if affiliate_url not in text:
            text += '\n' + affiliate_url
        payload = {'number': group, 'text': text, 'linkPreview': True}
        route = 'message/sendText'
        if image_url:
            payload = {'number': group, 'mediatype': 'image', 'mimetype': 'image/jpeg',
                       'caption': text, 'media': image_url, 'fileName': 'oferta.jpg'}
            route = 'message/sendMedia'
        # Any failure after the request begins is conservatively ambiguous. Never
        # fallback to text: a timeout could mean the photo was already delivered.
        try:
            data = await self.request('POST', self.path(route), payload)
            mid = (data.get('key') or {}).get('id')
            if not mid:
                raise RuntimeError('Resposta sem identificador de mensagem')
            return {'message_id': mid}
        except Exception as exc:
            raise DeliveryUncertain('Envio WhatsApp sem confirmação; confira o grupo antes de liberar nova tentativa') from exc
