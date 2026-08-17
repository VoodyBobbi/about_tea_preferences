import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from core.tea_factors import PROFILE_QUESTIONS
from services import TeaWorkflowService
from services.storage import InMemorySessionRepository
from bot.rendering import send_sequence

logger = logging.getLogger(__name__)
router = Router()

GREETING_MESSAGE = PROFILE_QUESTIONS["name"]
RESET_MESSAGE = "Начинаем заново. " + PROFILE_QUESTIONS["name"]
GENERIC_ERROR_MESSAGE = (
    "Сейчас не получилось обработать сообщение. Попробуйте, пожалуйста, ещё раз через пару минут."
)
UNSUPPORTED_MESSAGE = "Я работаю только с текстовыми сообщениями и кнопками — опишите, пожалуйста, текстом."


@router.message(Command("start"))
async def handle_start(message: Message, session_repository: InMemorySessionRepository) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось определить пользователя. Попробуйте ещё раз.")
        return

    session = session_repository.get_or_create(
        user_id=user.id,
        chat_id=message.chat.id,
        telegram_username=user.username,
        telegram_first_name=user.first_name,
    )
    session.reset()
    session.started = True
    session.pending_field = "name"

    if user.username:
        session.ticket.contact = f"@{user.username}"

    session.add_assistant_message(GREETING_MESSAGE)
    await message.answer(GREETING_MESSAGE)


@router.message(Command("reset"))
async def handle_reset(message: Message, session_repository: InMemorySessionRepository) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось сбросить диалог. Попробуйте ещё раз.")
        return

    session_repository.reset(user.id)
    session = session_repository.get_or_create(
        user_id=user.id,
        chat_id=message.chat.id,
        telegram_username=user.username,
        telegram_first_name=user.first_name,
    )
    session.started = True
    session.pending_field = "name"
    if user.username:
        session.ticket.contact = f"@{user.username}"

    session.add_assistant_message(RESET_MESSAGE)
    await message.answer(RESET_MESSAGE)


@router.message(F.text)
async def handle_text_message(
    message: Message,
    session_repository: InMemorySessionRepository,
    workflow: TeaWorkflowService,
) -> None:
    user = message.from_user
    if user is None or not message.text:
        await message.answer("Не удалось обработать сообщение. Попробуйте ещё раз.")
        return

    session = session_repository.get_or_create(
        user_id=user.id,
        chat_id=message.chat.id,
        telegram_username=user.username,
        telegram_first_name=user.first_name,
    )

    async def notify(text: str) -> None:
        # Мгновенное промежуточное сообщение (например, "ищу варианты...") —
        # отправляется сразу, ещё до завершения поиска/LLM-вызова.
        await message.answer(text)

    try:
        texts = await workflow.process_text(session, message.text, on_progress=notify)
    except Exception:
        logger.exception("Failed to process incoming tea message")
        await message.answer(GENERIC_ERROR_MESSAGE)
        return

    await send_sequence(message, session, texts)


@router.message()
async def handle_unsupported_message(message: Message) -> None:
    await message.answer(UNSUPPORTED_MESSAGE)
