import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand

from config import settings
from handlers import root_router


async def on_startup(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Welcome and open the Mini App"),
            BotCommand(command="help", description="Commands and tips"),
            BotCommand(command="app", description="Show the Mini App button"),
        ]
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(root_router)
    dp.startup.register(on_startup)

    try:
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        logging.error(
            "Telegram rejected BOT_TOKEN (Unauthorized). "
            "Open @BotFather → API Token → copy into bot/.env as BOT_TOKEN=… "
            "and backend/.env as TELEGRAM_BOT_TOKEN=… then restart."
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(main())
