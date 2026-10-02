from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Windows Server may use a legacy console code page (for example cp1252).
# Keep command-line diagnostics Unicode-safe even when bot/chat names contain emoji.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass

os.environ.setdefault('PYTHONUTF8', '1')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from app.services.shopee import ShopeeAffiliateClient  # noqa: E402
from app.services.telegram_bot import TelegramPublisher  # noqa: E402


async def main(kind):
    if kind == 'shopee':
        c = ShopeeAffiliateClient()
        rows = await c.search_products('oferta', 1, 1)
        return {'ok': True, 'detail': f'Shopee conectada. Retorno de teste: {len(rows)} produto(s).'}
    if kind == 'telegram':
        p = TelegramPublisher()
        me = await p.get_me()
        chat = await p.get_target_chat()
        return {
            'ok': True,
            'detail': f"Bot @{me.get('username') or me.get('first_name')} conectado ao destino {chat.get('title') or chat.get('username') or chat.get('id')}.",
        }
    return {'ok': False, 'detail': 'Teste desconhecido'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('kind')
    args = ap.parse_args()
    try:
        print(json.dumps(asyncio.run(main(args.kind)), ensure_ascii=True))
    except Exception as e:
        print(json.dumps({'ok': False, 'detail': str(e)}, ensure_ascii=True))
