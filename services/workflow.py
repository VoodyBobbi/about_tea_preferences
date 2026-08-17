import logging
from typing import Awaitable, Callable

from core import TeaOption, TeaSession, TeaTicket
from core.tea_factors import HIGH_WEIGHT_FIELDS, next_missing_field, question_for
from services.assistant import TeaAssistant
from services.search import TavilyTeaSearchClient, TeaSearchError
from services.telegram import OperatorNotifier

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]

MAX_SEARCH_ATTEMPTS = 3
MAX_OPTIONS_SHOWN = 6

SEARCH_STARTING_MESSAGE = (
    "Спасибо! Все данные собрал — ищу для вас подходящие варианты чая, "
    "это может занять несколько секунд..."
)
SEARCH_FAILED_MESSAGE = (
    "Не получилось выполнить поиск чая — похоже, техническая заминка. "
    "Напишите, пожалуйста, что-нибудь ещё раз, и я попробую снова — "
    "заново ничего заполнять не нужно."
)
NOTHING_FOUND_MESSAGE = (
    "Пока не нашлось ни одного варианта. Попробуйте, пожалуйста, ещё раз чуть позже — "
    "напишите что угодно, и я повторю поиск."
)
ALREADY_BEST_EFFORT_MESSAGE = (
    "Это уже все варианты, которые удалось найти близко к вашим пожеланиям — "
    "новых, к сожалению, больше нет."
)
PLEASE_USE_BUTTONS_MESSAGE = "Пожалуйста, выберите чай на кнопках выше — или нажмите «Найти ещё 🔎»."
STALE_STATE_MESSAGE = (
    "Похоже, эти варианты уже неактуальны. Если хотите оформить заявку заново — напишите /reset."
)
REPEAT_NOTHING_NEW_NOTE = (
    " Это те же ближайшие варианты, что и раньше, — принципиально новых пока не нашлось."
)
WEAK_MATCH_NOTE = (
    " Стопроцентного совпадения по всем пожеланиям не нашлось, но вот ближайшие по духу варианты."
)


def final_client_message(tea_name: str) -> str:
    return (
        f"Отлично, «{tea_name}» — прекрасный выбор! Я передал заявку менеджеру, "
        f"он свяжется с вами, чтобы согласовать доставку. Спасибо!"
    )


class TeaWorkflowService:
    def __init__(
        self,
        assistant: TeaAssistant,
        search_client: TavilyTeaSearchClient,
        notifier: OperatorNotifier,
    ) -> None:
        self._assistant = assistant
        self._search_client = search_client
        self._notifier = notifier

    async def process_text(
        self,
        session: TeaSession,
        message_text: str,
        on_progress: ProgressCallback | None = None,
    ) -> list[str]:
        if session.stage == "submitted":
            session.reset()

        self._prefill_contact(session)

        if session.stage == "awaiting_selection":
            return [PLEASE_USE_BUTTONS_MESSAGE]

        pending = session.pending_field or next_missing_field(session.ticket)
        session.pending_field = pending

        if pending is None:
            # Анкета была полностью заполнена ранее, но поиск не завершился успехом
            # (например, упал Tavily) — пробуем снова с того же места.
            session.add_user_message(message_text)
            return await self._run_search(session, on_progress)

        question = question_for(pending)
        history = session.recent_history()

        turn = await self._assistant.collect_field(
            ticket=session.ticket,
            pending_field=pending,
            pending_question=question,
            user_message=message_text,
            history=history,
        )

        session.add_user_message(message_text)
        session.started = True
        session.add_assistant_message(turn.reply)

        if not turn.collected_value:
            return [turn.reply]

        setattr(session.ticket, pending, turn.collected_value)
        session.pending_field = next_missing_field(session.ticket)

        if session.pending_field is None:
            return [turn.reply, *await self._run_search(session, on_progress)]

        return [turn.reply]

    async def process_factor_choice(
        self,
        session: TeaSession,
        field_name: str,
        value: str,
        on_progress: ProgressCallback | None = None,
    ) -> list[str]:
        if session.stage != "collecting" or session.pending_field != field_name:
            return [STALE_STATE_MESSAGE]

        setattr(session.ticket, field_name, value)
        session.add_assistant_message(f"Выбрано: {value}")
        session.pending_field = next_missing_field(session.ticket)

        if session.pending_field is None:
            return await self._run_search(session, on_progress)

        return [question_for(session.pending_field)]

    async def process_selection(self, session: TeaSession, option_index: int) -> list[str]:
        if session.stage != "awaiting_selection" or not (0 <= option_index < len(session.shown_options)):
            return [STALE_STATE_MESSAGE]

        selected = session.shown_options[option_index]
        session.ticket.selected_tea = selected
        session.stage = "submitted"

        await self._notifier.send_ticket(session)

        text = final_client_message(selected.name)
        session.add_assistant_message(text)
        logger.info("Tea ticket submitted for user_id=%s", session.user_id)
        return [text]

    async def process_more(
        self, session: TeaSession, on_progress: ProgressCallback | None = None
    ) -> list[str]:
        if session.stage != "awaiting_selection":
            return [STALE_STATE_MESSAGE]
        if not session.allow_more_search:
            return [ALREADY_BEST_EFFORT_MESSAGE]

        return await self._run_search(session, on_progress)

    async def close(self) -> None:
        await self._assistant.close()
        await self._search_client.close()

    async def _run_search(
        self, session: TeaSession, on_progress: ProgressCallback | None
    ) -> list[str]:
        if on_progress is not None:
            await on_progress(SEARCH_STARTING_MESSAGE)

        query = self._build_query(session.ticket)
        try:
            hits = await self._search_client.search(query)
        except TeaSearchError:
            # Технический сбой (после исчерпанных ретраев внутри клиента) попытку НЕ
            # тратит — это наша инфраструктурная проблема, а не решение клиента.
            # stage остаётся "collecting", профиль уже полон -> следующее сообщение
            # клиента (любое) повторит попытку поиска с того же места.
            return [SEARCH_FAILED_MESSAGE]

        # А вот состоявшийся запрос — попытка потрачена, даже если результата нет:
        # иначе "Найти ещё" не имело бы предела при пустых ответах Tavily.
        session.search_attempts += 1
        session.allow_more_search = session.search_attempts < MAX_SEARCH_ATTEMPTS

        if not hits:
            return [NOTHING_FOUND_MESSAGE]

        fresh_hits = [hit for hit in hits if hit.url not in session.seen_urls]
        is_repeat_with_nothing_new = not fresh_hits
        used_hits = (fresh_hits or hits)[:MAX_OPTIONS_SHOWN]

        recommendation = await self._assistant.generate_recommendations(session.ticket, used_hits)

        options: list[TeaOption] = []
        for item in recommendation.options[:MAX_OPTIONS_SHOWN]:
            if 0 <= item.source_index < len(used_hits):
                hit = used_hits[item.source_index]
                options.append(
                    TeaOption(name=item.name, description=item.description, source_url=hit.url)
                )

        if not options:
            return [NOTHING_FOUND_MESSAGE]

        session.shown_options = options
        session.seen_urls.extend(option.source_url for option in options)
        session.stage = "awaiting_selection"

        # is_compromise от LLM — семантическая оценка ("похоже, себе не идеальные
        # совпадения"), is_repeat_with_nothing_new — структурный факт от Python
        # ("новых url физически не нашлось"). Приписку показываем максимум одну,
        # структурная точнее и информативнее там, где сработали оба сигнала сразу.
        intro = recommendation.intro
        if is_repeat_with_nothing_new:
            intro += REPEAT_NOTHING_NEW_NOTE
        elif recommendation.is_compromise:
            intro += WEAK_MATCH_NOTE

        session.add_assistant_message(intro)
        return [intro]

    @staticmethod
    def _prefill_contact(session: TeaSession) -> None:
        if session.ticket.contact:
            return
        if session.telegram_username:
            session.ticket.contact = f"@{session.telegram_username}"

    @staticmethod
    def _build_query(ticket: TeaTicket) -> str:
        priority_values = [
            getattr(ticket, field_name) for field_name in HIGH_WEIGHT_FIELDS if getattr(ticket, field_name)
        ]
        keywords = " ".join(value.lower() for value in priority_values)
        parts = ["купить чай", keywords, "интернет магазин"]

        restrictions = (ticket.health_restrictions or "").lower()
        if restrictions and restrictions != "нет ограничений":
            parts.append(f"подходит если {restrictions}")

        return " ".join(part for part in parts if part).strip()
