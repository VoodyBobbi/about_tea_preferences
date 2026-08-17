from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core import TeaOption
from core.tea_factors import TeaFactor

OTHER_BUTTON_LABEL = "✍️ Другое (напишу сам)"
FIND_MORE_LABEL = "🔎 Найти ещё варианты"

# Telegram callback_data ограничен 64 байтами. Кодируем позицию варианта, а не сам
# текст — это компактно и полностью исключает риск превышения лимита на длинных
# кириллических формулировках.
FACTOR_PREFIX = "tf"
TEA_PREFIX = "tea"


def factor_keyboard(factor: TeaFactor) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, option in enumerate(factor.options):
        builder.button(text=option.label, callback_data=f"{FACTOR_PREFIX}:{factor.field}:{index}")
    if factor.allow_other:
        builder.button(text=OTHER_BUTTON_LABEL, callback_data=f"{FACTOR_PREFIX}:{factor.field}:other")

    long_labels = any(len(option.label) > 28 for option in factor.options)
    builder.adjust(1 if long_labels else 2)
    return builder.as_markup()


def tea_options_keyboard(options: list[TeaOption], allow_more: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, option in enumerate(options):
        builder.button(text=option.name[:60], callback_data=f"{TEA_PREFIX}:{index}")
    if allow_more:
        builder.button(text=FIND_MORE_LABEL, callback_data=f"{TEA_PREFIX}:more")

    builder.adjust(1)
    return builder.as_markup()
