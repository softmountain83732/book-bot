import logging

from html import escape



from bson import ObjectId

from bson.errors import InvalidId

from telegram import Update, InlineKeyboardMarkup

from telegram.error import TelegramError

from telegram.ext import (

    Application,

    CallbackQueryHandler,

    ContextTypes,

)



from app.config import settings

from app.database.mongo import get_database

from app.keyboards.admin import (

    PAGE_SIZE,

    admin_dashboard_keyboard,

    admin_report_detail_keyboard,

    admin_reports_list_keyboard,

)





logger = logging.getLogger(__name__)





def is_admin(user_id: int | None) -> bool:

    return (

        user_id is not None

        and user_id in settings.admin_telegram_ids

    )





async def safe_edit(

    query,

    text: str,

    reply_markup: InlineKeyboardMarkup | None = None,

) -> None:

    """Safely edit an admin report message."""



    try:

        await query.edit_message_text(

            text=text,

            reply_markup=reply_markup,

            parse_mode="HTML",

        )



    except TelegramError as exc:

        if "message is not modified" in str(exc).lower():

            return



        logger.warning(

            "Could not edit admin report message: %s",

            exc,

        )



        if query.message:

            try:

                await query.message.reply_text(

                    text=text,

                    reply_markup=reply_markup,

                    parse_mode="HTML",

                )

            except TelegramError:

                logger.exception(

                    "Could not send admin report fallback message."

                )





async def show_report_list(

    query,

    filter_slug: str,

    offset: int,

) -> None:

    """Show Open Reports or all report history."""



    if filter_slug not in ("open", "all"):

        filter_slug = "open"



    offset = max(0, offset)



    mongo_query = (

        {"status": "Open"}

        if filter_slug == "open"

        else {}

    )



    try:

        db = get_database()



        total = await db.reports.count_documents(mongo_query)



        if total > 0 and offset >= total:

            offset = ((total - 1) // PAGE_SIZE) * PAGE_SIZE



        cursor = (

            db.reports.find(mongo_query)

            .sort("created_at", -1)

            .skip(offset)

            .limit(PAGE_SIZE)

        )



        reports = []



        async for report in cursor:

            reports.append(report)



    except Exception:

        logger.exception("Could not load admin reports.")



        await safe_edit(

            query,

            "Report စာရင်းကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",

            admin_dashboard_keyboard(),

        )

        return



    label = (

        "🚩 Open Reports"

        if filter_slug == "open"

        else "📜 Report History"

    )



    page_number = offset // PAGE_SIZE + 1

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)



    lines = [

        f"<b>{label}</b>",

        "",

        f"Report စုစုပေါင်း: <b>{total:,}</b>",

        f"စာမျက်နှာ: <b>{page_number}/{total_pages}</b>",

        "",

    ]



    for index, report in enumerate(reports, start=offset + 1):

        title = escape(

            str(report.get("book_title_snapshot", "Unknown listing"))

        )

        reason = escape(

            str(report.get("reason_label", report.get("reason", "Unknown")))

        )

        status = escape(str(report.get("status", "Unknown")))

        report_id = str(report["_id"])



        lines.extend([

            f"<b>{index}. {title}</b>",

            f"အကြောင်းရင်း: {reason}",

            f"Status: {status}",

            f"Report ID: <code>{report_id[-8:]}</code>",

            "",

        ])



    if not reports:

        lines.append("ဒီစာရင်းထဲမှာ Report မရှိပါ။")



    lines.append("အသေးစိတ်စစ်ဆေးရန် Report တစ်ခုကို ရွေးပါ။")



    await safe_edit(

        query,

        "\n".join(lines),

        admin_reports_list_keyboard(

            reports=reports,

            filter_slug=filter_slug,

            offset=offset,

            total=total,

        ),

    )





async def show_report_detail(

    query,

    raw_report_id: str,

    filter_slug: str,

    offset: int,

    notice: str | None = None,

) -> None:

    """Display the report and associated listing information."""



    try:

        report_id = ObjectId(raw_report_id)



    except (InvalidId, TypeError):

        await safe_edit(

            query,

            "Report ID မမှန်ကန်ပါ။",

            admin_dashboard_keyboard(),

        )

        return



    db = get_database()



    report = await db.reports.find_one({

        "_id": report_id,

    })



    if report is None:

        await safe_edit(

            query,

            "ဒီ Report ကို ရှာမတွေ့တော့ပါ။",

            admin_dashboard_keyboard(),

        )

        return



    book_id = report.get("book_id")

    book = None



    if isinstance(book_id, ObjectId):

        book = await db.books.find_one({

            "_id": book_id,

        })



    title = str(

        report.get("book_title_snapshot", "Unknown listing")

    )



    current_status = (

        str(book.get("status", "Unknown"))

        if book

        else "Listing မရှိတော့ပါ"

    )



    current_status_text = escape(current_status)

    title_text = escape(title)

    reason_text = escape(

        str(report.get("reason_label", report.get("reason", "Unknown")))

    )

    report_status = str(report.get("status", "Unknown"))



    reporter_id = report.get("reporter_id", "N/A")

    seller_id = report.get("seller_id", "N/A")



    created_at = report.get("created_at")

    created_text = (

        created_at.strftime("%Y-%m-%d %H:%M UTC")

        if hasattr(created_at, "strftime")

        else "မသိရှိပါ"

    )



    lines = []



    if notice:

        lines.extend([

            f"ℹ️ {escape(notice)}",

            "",

        ])



    lines.extend([

        "🚩 <b>Report Details</b>",

        "",

        f"📚 Listing: <b>{title_text}</b>",

        f"📝 အကြောင်းရင်း: {reason_text}",

        f"📌 Report Status: <b>{escape(report_status)}</b>",

        f"📌 Listing Status: {current_status_text}",

        f"👤 Reporter ID: <code>{reporter_id}</code>",

        f"👤 Seller ID: <code>{seller_id}</code>",

        f"🆔 Report ID: <code>{report_id}</code>",

        f"🕒 တင်သည့်အချိန်: {created_text}",

    ])



    if book:

        lines.append(f"🆔 Book ID: <code>{book['_id']}</code>")



    resolved_by = report.get("resolved_by")



    if resolved_by is not None:

        lines.append(f"Admin ID: <code>{resolved_by}</code>")



    await safe_edit(

        query,

        "\n".join(lines),

        admin_report_detail_keyboard(

            report_id=str(report_id),

            status=report_status,

            filter_slug=filter_slug,

            offset=offset,

            book_id=str(book_id) if isinstance(book_id, ObjectId) else None,

        ),

    )





async def set_report_status(

    query,

    raw_report_id: str,

    target_status: str,

    filter_slug: str,

    offset: int,

    admin_id: int,

) -> None:

    """Resolve or dismiss an Open Report."""



    if target_status not in ("Resolved", "Dismissed"):

        await safe_edit(

            query,

            "Report Status မမှန်ကန်ပါ။",

            admin_dashboard_keyboard(),

        )

        return



    try:

        report_id = ObjectId(raw_report_id)



    except (InvalidId, TypeError):

        await safe_edit(

            query,

            "Report ID မမှန်ကန်ပါ။",

            admin_dashboard_keyboard(),

        )

        return



    db = get_database()



    report = await db.reports.find_one({

        "_id": report_id,

    })



    if report is None:

        await safe_edit(

            query,

            "ဒီ Report ကို ရှာမတွေ့တော့ပါ။",

            admin_dashboard_keyboard(),

        )

        return



    if report.get("status") != "Open":

        await show_report_detail(

            query,

            raw_report_id,

            filter_slug,

            offset,

            notice="ဒီ Report ကို ယခင်က ဖြေရှင်းပြီး သို့မဟုတ် ပယ်ချပြီးဖြစ်ပါတယ်။",

        )

        return



    from datetime import datetime, timezone



    now = datetime.now(timezone.utc)



    result = await db.reports.update_one(

        {

            "_id": report_id,

            "status": "Open",

        },

        {

            "$set": {

                "status": target_status,

                "resolved_by": admin_id,

                "resolved_at": now,

                "updated_at": now,

            }

        },

    )



    if result.modified_count != 1:

        await show_report_detail(

            query,

            raw_report_id,

            filter_slug,

            offset,

            notice="ဒီ Report ရဲ့ Status ကို တစ်ခြားလုပ်ဆောင်ချက်က ပြောင်းထားနိုင်ပါတယ်။",

        )

        return



    notice = (

        "✅ Report ကို ဖြေရှင်းပြီးအဖြစ် မှတ်သားလိုက်ပါပြီ။"

        if target_status == "Resolved"

        else "❎ Report ကို ပယ်ချလိုက်ပါပြီ။"

    )



    await show_report_detail(

        query,

        raw_report_id,

        filter_slug,

        offset,

        notice=notice,

    )





async def admin_reports_callback(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE,

) -> None:

    """Route protected admin report actions."""



    query = update.callback_query

    user = update.effective_user



    if query is None or query.data is None or user is None:

        return



    if not is_admin(user.id):

        await query.answer(

            "⛔ Admin ခွင့်ပြုချက် မရှိပါ။",

            show_alert=True,

        )

        return



    await query.answer()



    parts = query.data.split(":")



    try:

        if len(parts) == 4 and parts[:2] == [

            "adminreports",

            "list",

        ]:

            filter_slug = parts[2]



            try:

                offset = int(parts[3])

            except ValueError:

                offset = 0



            await show_report_list(

                query,

                filter_slug,

                max(0, offset),

            )

            return



        if len(parts) == 5 and parts[:2] == [

            "adminreports",

            "detail",

        ]:

            try:

                offset = int(parts[4])

            except ValueError:

                offset = 0



            await show_report_detail(

                query,

                raw_report_id=parts[2],

                filter_slug=parts[3],

                offset=max(0, offset),

            )

            return



        if len(parts) == 5 and parts[0] == "adminreports":

            action = parts[1]

            raw_report_id = parts[2]

            filter_slug = parts[3]



            try:

                offset = int(parts[4])

            except ValueError:

                offset = 0



            if action == "resolve":

                target_status = "Resolved"

            elif action == "dismiss":

                target_status = "Dismissed"

            else:

                await safe_edit(

                    query,

                    "ဒီ Report Action ကို မသိရှိပါ။",

                    admin_dashboard_keyboard(),

                )

                return



            await set_report_status(

                query,

                raw_report_id=raw_report_id,

                target_status=target_status,

                filter_slug=filter_slug,

                offset=max(0, offset),

                admin_id=user.id,

            )

            return



        await safe_edit(

            query,

            "Admin Report Action မမှန်ကန်ပါ။",

            admin_dashboard_keyboard(),

        )



    except Exception:

        logger.exception(

            "Admin report action failed for Telegram user %s",

            user.id,

        )



        await safe_edit(

            query,

            "Report ကို ကိုင်တွယ်ရာမှာ အမှားဖြစ်သွားပါတယ်။ "

            "Bot Log ကို စစ်ဆေးပါ။",

            admin_dashboard_keyboard(),

        )





def register_admin_reports_handlers(

    application: Application,

) -> None:

    """Register protected admin report-management callbacks."""



    application.add_handler(

        CallbackQueryHandler(

            admin_reports_callback,

            pattern=r"^adminreports:",

        )

    )
