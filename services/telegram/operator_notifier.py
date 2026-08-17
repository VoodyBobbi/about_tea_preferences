from aiogram import Bot

from core import Settings, TeaSession
from services.telegram.ticket_formatter import format_ticket_for_operator


class OperatorNotifier:
    def __init__(self, bot: Bot, settings: Settings) -> None:
        self._bot = bot
        self._settings = settings

    async def send_ticket(self, session: TeaSession) -> None:
        text = format_ticket_for_operator(session.ticket, session.telegram_username)
        await self._bot.send_message(self._settings.operator_chat_id, text)
