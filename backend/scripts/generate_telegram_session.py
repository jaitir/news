from __future__ import annotations

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ.get("TELEGRAM_SESSION_STRING", "")

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        if not await client.is_user_authorized():
            phone = input("Telegram phone number in international format: ").strip()
            await client.send_code_request(phone)
            code = input("Telegram login code: ").strip()
            try:
                await client.sign_in(phone=phone, code=code)
            except Exception:
                password = input("Two-step verification password: ").strip()
                await client.sign_in(password=password)

        print("\nTELEGRAM_SESSION_STRING=")
        print(client.session.save())


if __name__ == "__main__":
    asyncio.run(main())
