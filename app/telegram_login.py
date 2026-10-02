import asyncio
from pathlib import Path
from telethon import TelegramClient
from app.config import settings


async def main():
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit("Preencha TELEGRAM_API_ID e TELEGRAM_API_HASH no .env")
    Path(settings.telegram_session_path).parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(settings.telegram_session_path, settings.telegram_api_id, settings.telegram_api_hash)
    await client.start(phone=settings.telegram_phone or None)
    me = await client.get_me()
    print(f"Login OK: {getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')})")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
