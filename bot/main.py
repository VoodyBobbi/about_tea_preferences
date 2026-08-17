import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.handlers import callbacks, tea_flow
from core import get_settings, setup_logging
from services import TeaWorkflowService
from services.assistant import TeaAssistant
from services.search import TavilyTeaSearchClient
from services.storage import InMemorySessionRepository
from services.telegram import OperatorNotifier

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties())
    session_repository = InMemorySessionRepository()
    assistant = TeaAssistant(settings)
    search_client = TavilyTeaSearchClient(settings)
    notifier = OperatorNotifier(bot, settings)
    workflow = TeaWorkflowService(assistant=assistant, search_client=search_client, notifier=notifier)

    dp = Dispatcher()
    dp.include_router(tea_flow.router)
    dp.include_router(callbacks.router)
    dp["session_repository"] = session_repository
    dp["workflow"] = workflow

    logger.info("Starting tea consultant bot")
    try:
        await dp.start_polling(bot)
    finally:
        await workflow.close()
        await bot.session.close()
