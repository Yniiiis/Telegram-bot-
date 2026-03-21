from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from config import settings

router = Router(name="common")


def _webapp_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Open music app",
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ],
        resize_keyboard=True,
    )


WELCOME_TEXT = (
    "Welcome — listen to music right inside Telegram.\n\n"
    "Tap the button below to open the Mini App. "
    "You can search tracks, build playlists, and save favorites."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=_webapp_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Commands</b>\n"
        "/start — welcome and open the app\n"
        "/help — this message\n"
        "/app — show the Mini App button again",
        reply_markup=_webapp_keyboard(),
    )


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    await message.answer("Open the music Mini App:", reply_markup=_webapp_keyboard())


@router.message(F.text == "Open music app")
async def webapp_button_label(message: Message) -> None:
    """Keyboard sends this text; Web App opens from the button — reply with a hint."""
    await message.answer(
        "Use the same button — it launches the Mini App. "
        "If nothing opens, update <code>WEBAPP_URL</code> in the bot config (HTTPS required).",
        reply_markup=_webapp_keyboard(),
    )
