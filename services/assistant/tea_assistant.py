import asyncio
import json
import logging

import httpx

from core import (
    DialogueMessage,
    FieldTurn,
    RecommendationOption,
    RecommendationTurn,
    SearchHit,
    Settings,
    TeaTicket,
)
from services.assistant.prompts import (
    FIELD_COLLECTION_PROMPT,
    FIELD_TURN_SCHEMA,
    RECOMMENDATION_PROMPT,
    RECOMMENDATION_SCHEMA,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}

# Ассистент теперь работает как эксперт-собеседник (вопросы о чае, "другое" в анкете),
# а не только как строгий парсер JSON — поэтому температура чуть выше, чем в исходном
# support-боте (там было 0.2). Валидность структуры ответа всё равно гарантирует
# response_format=json_schema (strict), от температуры это почти не зависит.
ASSISTANT_TEMPERATURE = 0.3


class TeaAssistant:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.openai_base_url,
            timeout=httpx.Timeout(45.0, connect=12.0),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def collect_field(
        self,
        ticket: TeaTicket,
        pending_field: str,
        pending_question: str,
        user_message: str,
        history: list[DialogueMessage],
    ) -> FieldTurn:
        payload = {
            "model": self._settings.openai_model,
            "temperature": ASSISTANT_TEMPERATURE,
            "messages": [
                {"role": "system", "content": FIELD_COLLECTION_PROMPT},
                {
                    "role": "user",
                    "content": self._build_field_prompt(
                        ticket=ticket,
                        pending_field=pending_field,
                        pending_question=pending_question,
                        user_message=user_message,
                        history=history,
                    ),
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": FIELD_TURN_SCHEMA},
        }

        try:
            response = await self._post_with_retries(payload)
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return FieldTurn.model_validate(json.loads(content))
        except Exception:
            logger.exception("collect_field: falling back to plain retry reply")
            return FieldTurn(
                reply="Не расслышал, повторите, пожалуйста, ещё раз своими словами.",
                collected_value=None,
            )

    async def generate_recommendations(
        self,
        ticket: TeaTicket,
        search_results: list[SearchHit],
    ) -> RecommendationTurn:
        payload = {
            "model": self._settings.openai_model,
            "temperature": ASSISTANT_TEMPERATURE,
            "messages": [
                {"role": "system", "content": RECOMMENDATION_PROMPT},
                {
                    "role": "user",
                    "content": self._build_recommendation_prompt(ticket, search_results),
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": RECOMMENDATION_SCHEMA},
        }

        try:
            response = await self._post_with_retries(payload)
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            turn = RecommendationTurn.model_validate(json.loads(content))
            # Модель формально не обязана уложиться в лимит — подстрахуемся на всякий случай.
            turn.options = turn.options[:6]
            return turn
        except Exception:
            logger.exception("generate_recommendations: falling back to plain listing")
            return self._fallback_recommendations(search_results)

    async def close(self) -> None:
        await self._client.aclose()

    async def _post_with_retries(self, payload: dict) -> httpx.Response:
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                response = await self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if status_code not in RETRYABLE_STATUS_CODES or attempt == 3:
                    raise
            except httpx.RequestError as exc:
                last_error = exc
                if attempt == 3:
                    break

            await asyncio.sleep(0.75 * attempt)

        assert last_error is not None
        raise last_error

    @staticmethod
    def _build_field_prompt(
        ticket: TeaTicket,
        pending_field: str,
        pending_question: str,
        user_message: str,
        history: list[DialogueMessage],
    ) -> str:
        ticket_json = json.dumps(ticket.model_dump(exclude={"selected_tea"}), ensure_ascii=False, indent=2)
        history_json = json.dumps(
            [message.model_dump() for message in history], ensure_ascii=False, indent=2
        )
        return (
            f"pending_field: {pending_field}\n"
            f"pending_question: {pending_question}\n"
            f"ticket_so_far:\n{ticket_json}\n\n"
            f"recent_history:\n{history_json}\n\n"
            f"latest_user_message:\n{user_message}"
        )

    @staticmethod
    def _build_recommendation_prompt(ticket: TeaTicket, search_results: list[SearchHit]) -> str:
        ticket_json = json.dumps(ticket.model_dump(exclude={"selected_tea"}), ensure_ascii=False, indent=2)
        results_json = json.dumps(
            [
                {"index": i, "title": hit.title, "content": hit.content}
                for i, hit in enumerate(search_results)
            ],
            ensure_ascii=False,
            indent=2,
        )
        return f"ticket:\n{ticket_json}\n\nsearch_results:\n{results_json}"

    @staticmethod
    def _fallback_recommendations(search_results: list[SearchHit]) -> RecommendationTurn:
        options = [
            RecommendationOption(
                source_index=i,
                name=hit.title[:80],
                description="Похоже по описанию на то, что вы искали — уточните детали у оператора.",
            )
            for i, hit in enumerate(search_results[:6])
        ]
        return RecommendationTurn(
            intro="Вот что удалось найти для вас:",
            is_compromise=True,
            options=options,
        )
