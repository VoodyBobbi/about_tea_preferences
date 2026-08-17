"""Статичный каталог анкеты подбора чая.

Живёт в core, потому что нужен и services/workflow.py (бизнес-логика:
какое поле следующее, как построить поисковый запрос), и bot/keyboards.py
(рендер кнопок) — а core не зависит ни от services, ни от bot, что и
позволяет обоим слоям опираться на один источник правды без циклических
импортов.

Порядок факторов и тексты вариантов соответствуют таблице, утверждённой
для сценария. Вес (weight) — как в таблице; используется как для справки,
так и для приоритизации факторов при построении поискового запроса
(services/workflow.py берёт в запрос в первую очередь факторы с весом ★★★★+).

Анкета сокращена с исходных 11 факторов до 7: оставлены только весом ≥4
(goal, taste, caffeine_level, fermentation, strength, aroma,
health_restrictions) — то есть ровно то же множество, что уже отдельно
выделено ниже в HIGH_WEIGHT_FIELDS для поискового запроса. Убраны
leaf_size, brew_method, special_wishes (вес ≤3) и experience (вес не был
указан в исходной таблице вообще) — как более низкоприоритетные и
добавляющие вопросы без сильного влияния на итоговый подбор.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.schemas import TeaTicket


@dataclass(frozen=True)
class FactorOption:
    value: str  # что сохраняется в тикет и уходит в историю/оператору
    label: str  # текст на кнопке (может быть короче value)


@dataclass(frozen=True)
class TeaFactor:
    field: str
    question: str
    weight: int
    options: tuple[FactorOption, ...] = field(default_factory=tuple)
    allow_other: bool = True


PROFILE_QUESTIONS: dict[str, str] = {
    "name": "Здравствуйте! Я чайный консультант этого магазина 🍵 Как вас зовут?",
    "contact": "Оставьте, пожалуйста, контакт для связи: телефон или Telegram.",
    "delivery_address": "Подскажите, пожалуйста, адрес доставки.",
}

TEA_FACTORS: tuple[TeaFactor, ...] = (
    TeaFactor(
        field="goal",
        question="Что для вас сейчас важнее всего в чае — какая у него должна быть цель?",
        weight=5,
        allow_other=True,
        options=(
            FactorOption("Общее бодрящее настроение", "☀️ Бодрость и энергия"),
            FactorOption("Снижение стресса и тревоги", "🍃 Снижение стресса и тревоги"),
            FactorOption("Улучшение пищеварения", "🌿 Улучшение пищеварения"),
            FactorOption("Поддержка иммунитета", "🛡️ Поддержка иммунитета"),
            FactorOption("Улучшение концентрации и фокуса", "🎯 Концентрация и фокус"),
            FactorOption("Снижение веса / контроль аппетита", "⚖️ Контроль веса и аппетита"),
            FactorOption("Снижение давления", "❤️ Снижение давления"),
            FactorOption("Снижение холестерина", "🫀 Снижение холестерина"),
            FactorOption("Антиоксидантная защита", "✨ Антиоксидантная защита"),
            FactorOption("Для сна (расслабление)", "🌙 Для сна и расслабления"),
            FactorOption(
                "Для диабета / контроль сахара (слабый эффект)",
                "🩸 Контроль сахара",
            ),
        ),
    ),
    TeaFactor(
        field="taste",
        question="Какой вкус вам ближе всего?",
        weight=5,
        allow_other=True,
        options=(
            FactorOption("Цитрусовые / фруктовые", "🍊 Цитрусовые / фруктовые"),
            FactorOption("Ягодные", "🍓 Ягодные"),
            FactorOption("Цветочные", "🌸 Цветочные"),
            FactorOption("Травяные / пряные", "🌿 Травяные / пряные"),
            FactorOption("Ореховые / шоколадные", "🌰 Ореховые / шоколадные"),
            FactorOption("Дымные / древесные", "🔥 Дымные / древесные"),
            FactorOption("Молочные / сливочные", "🥛 Молочные / сливочные"),
            FactorOption("Нейтральный / чистый", "◻️ Нейтральный / чистый"),
            FactorOption("Терпкий / вяжущий (для крепкого чая)", "Терпкий / вяжущий"),
            FactorOption("Сладкий (с добавками)", "🍯 Сладкий (с добавками)"),
        ),
    ),
    TeaFactor(
        field="caffeine_level",
        question="Какой уровень кофеина вам подходит (по ощущениям)?",
        weight=4,
        allow_other=False,
        options=(
            FactorOption("Очень сильный (кофеин-мафия)", "☕☕☕ Очень сильный"),
            FactorOption("Сильный (нормальный чай)", "☕☕ Сильный"),
            FactorOption("Средний", "☕ Средний"),
            FactorOption("Лёгкий (максимум L-теанин)", "🍵 Лёгкий"),
            FactorOption("Почти нет (очень мягкий)", "💧 Почти нет"),
        ),
    ),
    TeaFactor(
        field="fermentation",
        question="Какая степень ферментации вам ближе?",
        weight=4,
        allow_other=False,
        options=(
            FactorOption(
                "Максимально ферментированный (чёрный, пуэр, выдержанный улун)",
                "Максимально ферментированный",
            ),
            FactorOption("Средний (улун)", "Средний (улун)"),
            FactorOption("Минимальная ферментация (зелёный, белый)", "Минимальная ферментация"),
            FactorOption("Ничего не важно / любые", "Не важно / любые"),
        ),
    ),
    TeaFactor(
        field="strength",
        question="Насколько крепким должен быть вкус в чашке?",
        weight=4,
        allow_other=False,
        options=(
            FactorOption("Сильный (яркий, выдержанный)", "Сильный, яркий"),
            FactorOption("Средний (сбалансированный)", "Средний, сбалансированный"),
            FactorOption("Лёгкий (мягкий, нежный)", "Лёгкий, мягкий"),
            FactorOption("Нейтральный / чистый", "Нейтральный / чистый"),
        ),
    ),
    TeaFactor(
        field="aroma",
        question="А какой аромат предпочитаете?",
        weight=4,
        allow_other=False,
        options=(
            FactorOption("Сильный ароматизированный", "Сильный ароматизированный"),
            FactorOption("Средний", "Средний"),
            FactorOption("Лёгкий ароматизированный", "Лёгкий ароматизированный"),
            FactorOption("Нейтральный / чистый", "Нейтральный / чистый"),
        ),
    ),
    TeaFactor(
        field="health_restrictions",
        question="Есть ли ограничения по здоровью или аллергии, которые стоит учесть?",
        weight=4,
        allow_other=True,
        options=(
            FactorOption("Нет ограничений", "✅ Нет ограничений"),
            FactorOption(
                "Проблемы с сердцем / давлением (нельзя сильный кофеин)",
                "Сердце / давление",
            ),
            FactorOption("Проблемы с желудком (избегать терпких)", "Проблемы с желудком"),
            FactorOption("Аллергия на кофеин / теанин", "Аллергия на кофеин/теанин"),
            FactorOption("Беременность", "Беременность"),
        ),
    ),
)

_FACTORS_BY_FIELD: dict[str, TeaFactor] = {factor.field: factor for factor in TEA_FACTORS}

# Полный порядок сбора: сначала профиль клиента, затем анкета из 7 факторов.
FIELD_ORDER: tuple[str, ...] = ("name", "contact", "delivery_address") + tuple(
    factor.field for factor in TEA_FACTORS
)

# Факторы с весом ★★★★ и выше — используются для приоритизации в поисковом запросе.
HIGH_WEIGHT_FIELDS: tuple[str, ...] = tuple(
    factor.field for factor in TEA_FACTORS if factor.weight >= 4
)


def get_factor(field_name: str) -> TeaFactor | None:
    return _FACTORS_BY_FIELD.get(field_name)


def is_button_field(field_name: str) -> bool:
    return field_name in _FACTORS_BY_FIELD


def question_for(field_name: str) -> str:
    if field_name in PROFILE_QUESTIONS:
        return PROFILE_QUESTIONS[field_name]
    factor = _FACTORS_BY_FIELD.get(field_name)
    if factor is not None:
        return factor.question
    return "Расскажите, пожалуйста, подробнее."


def next_missing_field(ticket: "TeaTicket") -> str | None:
    for field_name in FIELD_ORDER:
        if not getattr(ticket, field_name, None):
            return field_name
    return None
