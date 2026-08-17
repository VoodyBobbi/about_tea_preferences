from core import TeaTicket

# Ровно те поля, что нужны оператору по сценарию: источник, название чая, адрес,
# имя клиента, контакт в Telegram. Остальные 7 факторов анкеты в это сообщение
# сознательно не включены (сценарий требует только этот набор) — при желании их
# легко добавить отдельным блоком "для справки" здесь же.


def format_ticket_for_operator(ticket: TeaTicket, telegram_username: str | None) -> str:
    selected = ticket.selected_tea
    username = f"@{telegram_username}" if telegram_username else "-"

    lines = [
        "=== НОВАЯ ЗАЯВКА: ПОДБОР ЧАЯ ===",
        "",
        f"Чай: {selected.name if selected else '-'}",
        f"Источник (не для клиента): {selected.source_url if selected else '-'}",
        "",
        f"Имя клиента: {ticket.name or '-'}",
        f"Контакт: {ticket.contact or '-'}",
        f"Telegram: {username}",
        f"Адрес доставки: {ticket.delivery_address or '-'}",
        "",
        "=== КОНЕЦ ===",
    ]
    return "\n".join(lines)
