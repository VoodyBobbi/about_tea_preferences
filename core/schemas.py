import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MessageRole = Literal["user", "assistant"]
SessionStage = Literal["collecting", "awaiting_selection", "submitted"]

# Поля тикета, которые заполняются только текстом (не кнопками).
PROFILE_FIELDS: tuple[str, ...] = ("name", "contact", "delivery_address")

# Поля анкеты из 7 факторов (кнопочный опрос, вес >=4). Порядок и имена
# согласованы с каталогом факторов в core/tea_factors.py — там же лежат
# вопросы и варианты.
SURVEY_FIELDS: tuple[str, ...] = (
    "goal",
    "taste",
    "caffeine_level",
    "fermentation",
    "strength",
    "aroma",
    "health_restrictions",
)

TICKET_TEXT_FIELDS: tuple[str, ...] = PROFILE_FIELDS + SURVEY_FIELDS


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


class SearchHit(BaseModel):
    """Один сырой результат веб-поиска (до обработки ассистентом)."""

    title: str
    url: str
    content: str = ""


class TeaOption(BaseModel):
    """Готовый к показу клиенту вариант чая: название + описание + скрытый источник."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_url: str = Field(min_length=1)

    @field_validator("name", "description", mode="before")
    @classmethod
    def _clean(cls, value: str) -> str:
        return _clean_text(value) or value


class TeaTicket(BaseModel):
    """Данные, которые бот собирает о клиенте, его предпочтениях и итоговом выборе."""

    model_config = ConfigDict(validate_assignment=True)

    # профиль клиента
    name: str | None = None
    contact: str | None = None
    delivery_address: str | None = None

    # анкета из 7 факторов (см. core/tea_factors.py)
    goal: str | None = None
    taste: str | None = None
    caffeine_level: str | None = None
    fermentation: str | None = None
    strength: str | None = None
    aroma: str | None = None
    health_restrictions: str | None = None

    # результат подбора
    selected_tea: TeaOption | None = None

    @field_validator(*TICKET_TEXT_FIELDS, mode="before")
    @classmethod
    def _clean_field(cls, value: str | None) -> str | None:
        return _clean_text(value)

    def merge(self, other: "TeaTicket") -> None:
        """Накладывает непустые текстовые поля other поверх текущего тикета."""
        for field_name in TICKET_TEXT_FIELDS:
            value = getattr(other, field_name)
            if value not in (None, ""):
                setattr(self, field_name, value)

    def profile_complete(self) -> bool:
        """Все 10 текстовых полей (профиль + анкета) заполнены — можно искать чай."""
        return all(getattr(self, field_name) for field_name in TICKET_TEXT_FIELDS)

    def is_complete(self) -> bool:
        """Заявка готова к отправке оператору: клиент подтвердил выбор конкретного чая.

        Это единственный порог готовности — profile_complete() лишь открывает
        возможность поиска, а не сам факт готовности заявки.
        """
        return self.selected_tea is not None


class DialogueMessage(BaseModel):
    role: MessageRole
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("Dialogue message cannot be empty")
        return cleaned


class FieldTurn(BaseModel):
    """Ответ ассистента при сборе одного свободнотекстового поля (имя/контакт/адрес/
    'другое' по фактору) либо ответе на произвольный вопрос о чае."""

    reply: str = Field(min_length=1)
    collected_value: str | None = None


class RecommendationOption(BaseModel):
    source_index: int
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class RecommendationTurn(BaseModel):
    """Ответ ассистента, превращающий сырые результаты поиска в предложения клиенту."""

    intro: str = Field(min_length=1)
    is_compromise: bool = False
    options: list[RecommendationOption] = Field(default_factory=list)


class TeaSession(BaseModel):
    user_id: int
    chat_id: int
    telegram_username: str | None = None
    telegram_first_name: str | None = None

    started: bool = False
    stage: SessionStage = "collecting"
    pending_field: str | None = None

    ticket: TeaTicket = Field(default_factory=TeaTicket)
    history: list[DialogueMessage] = Field(default_factory=list)

    shown_options: list[TeaOption] = Field(default_factory=list)
    seen_urls: list[str] = Field(default_factory=list)
    search_attempts: int = 0
    allow_more_search: bool = True

    def add_user_message(self, text: str) -> None:
        self._append_history("user", text)

    def add_assistant_message(self, text: str) -> None:
        self._append_history("assistant", text)

    def recent_history(self, limit: int = 8) -> list[DialogueMessage]:
        return list(self.history[-limit:])

    @property
    def last_assistant_message(self) -> str | None:
        for message in reversed(self.history):
            if message.role == "assistant":
                return message.text
        return None

    def reset(self) -> None:
        self.started = False
        self.stage = "collecting"
        self.pending_field = None
        self.ticket = TeaTicket()
        self.history = []
        self.shown_options = []
        self.seen_urls = []
        self.search_attempts = 0
        self.allow_more_search = True

    def _append_history(self, role: MessageRole, text: str) -> None:
        self.history.append(DialogueMessage(role=role, text=text))
        if len(self.history) > 20:
            self.history = self.history[-20:]
