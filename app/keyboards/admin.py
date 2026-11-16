from telegram import InlineKeyboardButton, InlineKeyboardMarkup


PAGE_SIZE = 5

BOOK_FILTERS = {
    "all": "📚 အားလုံး",
    "available": "🟢 Available",
    "pending": "🟠 Pending",
    "sold": "✅ Sold",
    "cancelled": "⚫ Cancelled",
}


def admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📚 စာအုပ်အားလုံး",
                callback_data="admin:books:all:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "🟢 ရောင်းရန်ရှိ",
                callback_data="admin:books:available:0",
            ),
            InlineKeyboardButton(
                "🟠 Pending",
                callback_data="admin:books:pending:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Sold",
                callback_data="admin:books:sold:0",
            ),
            InlineKeyboardButton(
                "⚫ Cancelled",
                callback_data="admin:books:cancelled:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "🚩 Open Reports",
                callback_data="adminreports:list:open:0",
            ),
            InlineKeyboardButton(
                "📜 Report History",
                callback_data="adminreports:list:all:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "🟠 Pending Transactions",
                callback_data="admin:requests:pending:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "📜 Request History",
                callback_data="admin:requests:all:0",
            ),
            InlineKeyboardButton(
                "👥 Users",
                callback_data="admin:users:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Dashboard Refresh",
                callback_data="admin:dashboard",
            ),
        ],
    ])


def admin_book_list_keyboard(
    books: list[dict],
    filter_slug: str,
    offset: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows = []

    for book in books:
        title = str(book.get("title", "Untitled")).strip()

        if len(title) > 36:
            title = title[:33] + "..."

        rows.append([
            InlineKeyboardButton(
                f"📖 {title}",
                callback_data=(
                    f"admin:book:{book['_id']}:"
                    f"{filter_slug}:{offset}"
                ),
            )
        ])

    navigation = []

    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ အရင်",
                callback_data=(
                    f"admin:books:{filter_slug}:"
                    f"{max(0, offset - PAGE_SIZE)}"
                ),
            )
        )

    if offset + PAGE_SIZE < total:
        navigation.append(
            InlineKeyboardButton(
                "နောက် ➡️",
                callback_data=(
                    f"admin:books:{filter_slug}:"
                    f"{offset + PAGE_SIZE}"
                ),
            )
        )

    if navigation:
        rows.append(navigation)

    rows.append([
        InlineKeyboardButton(
            "⬅️ Dashboard",
            callback_data="admin:dashboard",
        )
    ])

    return InlineKeyboardMarkup(rows)


def admin_book_detail_keyboard(
    book_id: str,
    status: str,
    filter_slug: str,
    offset: int,
    admin_hidden: bool = False,
) -> InlineKeyboardMarkup:
    rows = []

    if status in ("Available", "Pending") and not admin_hidden:
        rows.append([
            InlineKeyboardButton(
                "🚫 Listing ကို ဖယ်ရှားမည်",
                callback_data=(
                    f"admin:cancel:{book_id}:"
                    f"{filter_slug}:{offset}"
                ),
            )
        ])

    if status == "Cancelled" and admin_hidden:
        rows.append([
            InlineKeyboardButton(
                "✅ ပြန်လည်ခွင့်ပြုမည်",
                callback_data=(
                    f"admin:restore:{book_id}:"
                    f"{filter_slug}:{offset}"
                ),
            )
        ])

    rows.extend([
        [
            InlineKeyboardButton(
                "⬅️ စာအုပ်စာရင်း",
                callback_data=(
                    f"admin:books:{filter_slug}:{offset}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Dashboard",
                callback_data="admin:dashboard",
            )
        ],
    ])

    return InlineKeyboardMarkup(rows)


def admin_users_keyboard(
    users: list[dict],
    offset: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows = []

    for user in users:
        user_id = user.get("_id")

        display_name = (
            user.get("first_name")
            or user.get("username")
            or str(user_id)
        )

        display_name = str(display_name).strip()

        if len(display_name) > 32:
            display_name = display_name[:29] + "..."

        rows.append([
            InlineKeyboardButton(
                f"👤 {display_name}",
                callback_data=f"admin:user:{user_id}:{offset}",
            )
        ])

    navigation = []

    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ အရင်",
                callback_data=(
                    f"admin:users:{max(0, offset - PAGE_SIZE)}"
                ),
            )
        )

    if offset + PAGE_SIZE < total:
        navigation.append(
            InlineKeyboardButton(
                "နောက် ➡️",
                callback_data=f"admin:users:{offset + PAGE_SIZE}",
            )
        )

    if navigation:
        rows.append(navigation)

    rows.append([
        InlineKeyboardButton(
            "⬅️ Dashboard",
            callback_data="admin:dashboard",
        )
    ])

    return InlineKeyboardMarkup(rows)


def admin_user_detail_keyboard(
    offset: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ User စာရင်း",
                callback_data=f"admin:users:{offset}",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Dashboard",
                callback_data="admin:dashboard",
            )
        ],
    ])


def admin_requests_keyboard(
    requests: list[dict],
    filter_slug: str,
    offset: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows = []

    for request in requests:
        request_id = str(request["_id"])

        rows.append([
            InlineKeyboardButton(
                f"🔎 Request {request_id[-6:]}",
                callback_data=(
                    f"admin:request:{request_id}:"
                    f"{filter_slug}:{offset}"
                ),
            )
        ])

    navigation = []

    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ အရင်",
                callback_data=(
                    f"admin:requests:{filter_slug}:"
                    f"{max(0, offset - PAGE_SIZE)}"
                ),
            )
        )

    if offset + PAGE_SIZE < total:
        navigation.append(
            InlineKeyboardButton(
                "နောက် ➡️",
                callback_data=(
                    f"admin:requests:{filter_slug}:"
                    f"{offset + PAGE_SIZE}"
                ),
            )
        )

    if navigation:
        rows.append(navigation)

    rows.extend([
        [
            InlineKeyboardButton(
                "🟠 Pending",
                callback_data="admin:requests:pending:0",
            ),
            InlineKeyboardButton(
                "📜 အားလုံး",
                callback_data="admin:requests:all:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ Dashboard",
                callback_data="admin:dashboard",
            )
        ],
    ])

    return InlineKeyboardMarkup(rows)


def admin_request_detail_keyboard(
    filter_slug: str,
    offset: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ Request စာရင်း",
                callback_data=(
                    f"admin:requests:{filter_slug}:{offset}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Dashboard",
                callback_data="admin:dashboard",
            )
        ],
    ])


def admin_reports_list_keyboard(
    reports: list[dict],
    filter_slug: str,
    offset: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows = []

    for report in reports:
        report_id = str(report["_id"])

        rows.append([
            InlineKeyboardButton(
                f"🚩 Report {report_id[-6:]}",
                callback_data=(
                    f"adminreports:detail:{report_id}:"
                    f"{filter_slug}:{offset}"
                ),
            )
        ])

    navigation = []

    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ အရင်",
                callback_data=(
                    f"adminreports:list:{filter_slug}:"
                    f"{max(0, offset - PAGE_SIZE)}"
                ),
            )
        )

    if offset + PAGE_SIZE < total:
        navigation.append(
            InlineKeyboardButton(
                "နောက် ➡️",
                callback_data=(
                    f"adminreports:list:{filter_slug}:"
                    f"{offset + PAGE_SIZE}"
                ),
            )
        )

    if navigation:
        rows.append(navigation)

    rows.extend([
        [
            InlineKeyboardButton(
                "🚩 Open Reports",
                callback_data="adminreports:list:open:0",
            ),
            InlineKeyboardButton(
                "📜 History",
                callback_data="adminreports:list:all:0",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Dashboard",
                callback_data="admin:dashboard",
            )
        ],
    ])

    return InlineKeyboardMarkup(rows)


def admin_report_detail_keyboard(
    report_id: str,
    status: str,
    filter_slug: str,
    offset: int,
    book_id: str | None = None,
) -> InlineKeyboardMarkup:
    rows = []

    if status == "Open":
        rows.extend([
            [
                InlineKeyboardButton(
                    "✅ Report ဖြေရှင်းပြီး",
                    callback_data=(
                        f"adminreports:resolve:{report_id}:"
                        f"{filter_slug}:{offset}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❎ Report ပယ်ချမည်",
                    callback_data=(
                        f"adminreports:dismiss:{report_id}:"
                        f"{filter_slug}:{offset}"
                    ),
                )
            ],
        ])

    if book_id:
        rows.append([
            InlineKeyboardButton(
                "📚 Listing ကို စစ်ဆေးမည်",
                callback_data=f"admin:book:{book_id}:all:0",
            )
        ])

    rows.extend([
        [
            InlineKeyboardButton(
                "⬅️ Report စာရင်း",
                callback_data=(
                    f"adminreports:list:{filter_slug}:{offset}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Dashboard",
                callback_data="admin:dashboard",
            )
        ],
    ])

    return InlineKeyboardMarkup(rows)