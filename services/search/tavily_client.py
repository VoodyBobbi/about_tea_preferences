import asyncio
import logging

import httpx

from core import Settings
from core.schemas import SearchHit

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


class TeaSearchError(Exception):
    """Поиск чая не удался после всех повторных попыток."""


class TavilyTeaSearchClient:
    """Тонкая обёртка над Tavily Search API (POST /search), без официального SDK —
    так же, как и остальной проект ходит к внешним API напрямую через httpx."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.tavily_base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "Authorization": f"Bearer {settings.tavily_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def search(self, query: str, max_results: int | None = None) -> list[SearchHit]:
        payload = {
            "query": query,
            "search_depth": "advanced",
            "topic": "general",
            "max_results": max_results or self._settings.tavily_max_results,
        }

        try:
            response = await self._post_with_retries(payload)
            data = response.json()
        except Exception as exc:
            logger.exception("Tavily search failed")
            raise TeaSearchError("Не удалось выполнить поиск чая") from exc

        hits: list[SearchHit] = []
        for item in data.get("results", []):
            url = item.get("url")
            title = item.get("title")
            if not url or not title:
                continue
            hits.append(SearchHit(title=title, url=url, content=item.get("content") or ""))
        return hits

    async def close(self) -> None:
        await self._client.aclose()

    async def _post_with_retries(self, payload: dict) -> httpx.Response:
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                response = await self._client.post("/search", json=payload)
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
