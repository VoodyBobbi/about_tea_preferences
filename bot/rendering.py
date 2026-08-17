from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from core import TeaSession
from core.tea_factors import get_factor
from bot.keyboards import factor_keyboard, tea_options_keyboard


async def send_sequence(target: Message, session: TeaSession, texts: list[str]) -> None:
    """Отправляет тексты по очереди; клавиатуру (если нужна для текущего состояния
    сессии) прикрепляет только к последнему сообщению."""
    if not texts:
        return

    last_index = len(texts) - 1
    for index, text in enumerate(texts):
        keyboard = _keyboard_for_session(session) if index == last_index else None
        await target.answer(text, reply_markup=keyboard)


async def safe_clear_markup(message: Message) -> None:
    """Убирает клавиатуру у уже отвеченного сообщения. Молча игнорирует ошибку,
    если сообщение уже было изменено (например, из-за двойного нажатия)."""
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


def _keyboard_for_session(session: TeaSession) -> InlineKeyboardMarkup | None:
    if session.stage == "awaiting_selection":
        return tea_options_keyboard(session.shown_options, allow_more=session.allow_more_search)

    if session.stage == "collecting" and session.pending_field:
        factor = get_factor(session.pending_field)
        if factor is not None:
            return factor_keyboard(factor)

    return None
