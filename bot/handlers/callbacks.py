import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from core import TeaSession
from core.tea_factors import get_factor
from services import TeaWorkflowService
from services.storage import InMemorySessionRepository
from bot.keyboards import FACTOR_PREFIX, TEA_PREFIX
from bot.rendering import safe_clear_markup, send_sequence

logger = logging.getLogger(__name__)
router = Router()

OTHER_PROMPT_MESSAGE = "Опишите своими словами — учту как есть."


def _session_for(callback: CallbackQuery, session_repository: InMemorySessionRepository) -> TeaSession:
    user = callback.from_user
    chat_id = callback.message.chat.id if callback.message else user.id
    return session_repository.get_or_create(
        user_id=user.id,
        chat_id=chat_id,
        telegram_username=user.username,
        telegram_first_name=user.first_name,
    )


@router.callback_query(F.data.startswith(f"{FACTOR_PREFIX}:"))
async def handle_factor_choice(
    callback: CallbackQuery,
    session_repository: InMemorySessionRepository,
    workflow: TeaWorkflowService,
) -> None:
    await callback.answer()
    if callback.message is None or not callback.data:
        return

    try:
        _, field_name, choice = callback.data.split(":", 2)
    except ValueError:
        return

    session = _session_for(callback, session_repository)
    await safe_clear_markup(callback.message)

    if choice == "other":
        session.pending_field = field_name
        await callback.message.answer(OTHER_PROMPT_MESSAGE)
        return

    factor = get_factor(field_name)
    if factor is None:
        return
    try:
        option = factor.options[int(choice)]
    except (ValueError, IndexError):
        return

    async def notify(text: str) -> None:
        await callback.message.answer(text)

    try:
        texts = await workflow.process_factor_choice(session, field_name, option.value, on_progress=notify)
    except Exception:
        logger.exception("Failed to process factor choice callback")
        await callback.message.answer(
            "Сейчас не получилось обработать выбор. Попробуйте, пожалуйста, ещё раз через пару минут."
        )
        return

    await send_sequence(callback.message, session, texts)


@router.callback_query(F.data.startswith(f"{TEA_PREFIX}:"))
async def handle_tea_choice(
    callback: CallbackQuery,
    session_repository: InMemorySessionRepository,
    workflow: TeaWorkflowService,
) -> None:
    await callback.answer()
    if callback.message is None or not callback.data:
        return

    choice = callback.data.split(":", 1)[1]
    session = _session_for(callback, session_repository)
    await safe_clear_markup(callback.message)

    async def notify(text: str) -> None:
        await callback.message.answer(text)

    try:
        if choice == "more":
            texts = await workflow.process_more(session, on_progress=notify)
        else:
            texts = await workflow.process_selection(session, int(choice))
    except Exception:
        logger.exception("Failed to process tea choice callback")
        await callback.message.answer(
            "Сейчас не получилось обработать выбор. Попробуйте, пожалуйста, ещё раз через пару минут."
        )
        return

    await send_sequence(callback.message, session, texts)
