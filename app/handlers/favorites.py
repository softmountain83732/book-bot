#app/handlers/favorites.py
import logging

from datetime import datetime, timezone

from html import escape



from bson import ObjectId

from bson.errors import InvalidId

from pymongo.errors import DuplicateKeyError, PyMongoError

from telegram import (

    InlineKeyboardButton,

    InlineKeyboardMarkup,

    Update,

)

from telegram.error import TelegramError

from telegram.ext import (

    Application,

    CallbackQueryHandler,

    CommandHandler,

    ContextTypes,

)



from app.database.mongo import get_database
from app.services.channel_service import format_semester

from app.keyboards.favorites import (

    PAGE_SIZE,

    favorite_book_detail_keyboard,

    favorites_list_keyboard,

)

from app.keyboards.main_menu import get_main_menu





logger = logging.getLogger(__name__)





STATUS_LABELS = {

    "Available": "🟢 ရောင်းရန်ရှိ",

    "Pending": "🟠 ဝယ်ယူရန် ညှိနှိုင်းနေဆဲ",

    "Sold": "✅ ရောင်းထွက်သွားပြီ",

    "Cancelled": "⚫ ရောင်းချမှု ပယ်ဖျက်ထားသည်",

}





def format_price(book: dict) -> str:

    if book.get("is_negotiable"):

        return "ဈေးညှိနှိုင်း"



    price = book.get("price")



    if isinstance(price, (int, float)):

        return f"{price:,.0f} MMK"



    return "ဈေးနှုန်း မသတ်မှတ်ထားပါ"





async def safe_edit(

    query,

    text: str,

    reply_markup: InlineKeyboardMarkup | None = None,

) -> None:

    """Safely edit the current Favorites message."""



    try:

        await query.edit_message_text(

            text=text,

            reply_markup=reply_markup,

            parse_mode="HTML",

        )



    except TelegramError as exc:

        if "message is not modified" in str(exc).lower():

            return



        logger.warning("Could not edit Favorites message: %s", exc)



        if query.message:

            try:

                await query.message.reply_text(

                    text=text,

                    reply_markup=reply_markup,

                    parse_mode="HTML",

                )

            except TelegramError:

                logger.exception(

                    "Could not send Favorites fallback message."

                )





async def save_favorite(

    query,

    context: ContextTypes.DEFAULT_TYPE,

    raw_book_id: str,

) -> None:

    """Save an available listing for the current user."""



    user = query.from_user



    try:

        book_id = ObjectId(raw_book_id)



    except (InvalidId, TypeError):

        await query.answer(

            "စာအုပ် ID မမှန်ကန်ပါ။",

            show_alert=True,

        )

        return



    db = get_database()



    user_record = await db.users.find_one({

        "_id": user.id,

    })



    if user_record is None:

        await query.answer(

            "Bot Private Chat မှာ /start အရင်နှိပ်ပါ။",

            show_alert=True,

        )

        return



    book = await db.books.find_one({

        "_id": book_id,

        "status": "Available",

        "admin_hidden": {"$ne": True},

    })



    if book is None:

        await query.answer(

            "ဒီစာအုပ်ကို လက်ရှိ သိမ်းထားလို့ မရတော့ပါဘူး။",

            show_alert=True,

        )

        return



    if book.get("seller_id") == user.id:

        await query.answer(

            "ကိုယ့်စာအုပ်ကို Favorites ထဲ ထည့်စရာမလိုပါဘူး။",

            show_alert=True,

        )

        return



    now = datetime.now(timezone.utc)



    try:

        result = await db.favorites.update_one(

            {

                "user_id": user.id,

                "book_id": book_id,

            },

            {

                "$setOnInsert": {

                    "user_id": user.id,

                    "book_id": book_id,

                    "created_at": now,

                }

            },

            upsert=True,

        )



    except DuplicateKeyError:

        await query.answer(

            "❤️ ဒီစာအုပ်ကို သိမ်းထားပြီးပါပြီ။",

            show_alert=True,

        )

        return



    except PyMongoError:

        logger.exception(

            "Could not save favorite book %s for user %s.",

            book_id,

            user.id,

        )



        await query.answer(

            "စာအုပ်ကို သိမ်းရာမှာ အမှားဖြစ်သွားပါတယ်။",

            show_alert=True,

        )

        return



    if result.upserted_id is None:

        await query.answer(

            "❤️ ဒီစာအုပ်ကို Favorites ထဲမှာ သိမ်းထားပြီးပါပြီ။",

            show_alert=True,

        )

        return



    await query.answer("❤️ Favorites ထဲ သိမ်းထားပြီးပါပြီ။")



    try:

        await context.bot.send_message(

            chat_id=user.id,

            text=(

                "❤️ <b>Favorites ထဲ သိမ်းထားပြီးပါပြီ။</b>\n\n"

                f"📚 စာအုပ်: {escape(str(book.get('title', 'Untitled')))}\n\n"

                "Main Menu → သိမ်းထားသောစာအုပ်များ ကနေ "

                "ပြန်ကြည့်နိုင်ပါတယ်။"

            ),

            parse_mode="HTML",

        )



    except TelegramError:

        # Saving has succeeded in MongoDB; the private message is optional.

        logger.info(

            "Could not send favorite confirmation to user %s.",

            user.id,

            exc_info=True,

        )





async def show_favorites(

    query,

    user_id: int,

    offset: int,

) -> None:

    """Display currently available saved books, newest first."""



    offset = max(0, offset)

    db = get_database()



    try:

        cursor = (

            db.favorites.find({"user_id": user_id})

            .sort("created_at", -1)

        )



        saved_ids = []



        async for favorite in cursor:

            book_id = favorite.get("book_id")



            if isinstance(book_id, ObjectId):

                saved_ids.append(book_id)



        if not saved_ids:

            await safe_edit(

                query,

                "❤️ <b>သိမ်းထားသောစာအုပ်များ</b>\n\n"

                "Favorites ထဲမှာ စာအုပ်မရှိသေးပါဘူး။\n\n"

                "Channel ထဲက စာအုပ်တွေအောက်ရှိ "

                "“❤️ သိမ်းထားမည်” ကို နှိပ်ပြီး သိမ်းထားနိုင်ပါတယ်။",

                favorites_list_keyboard(

                    books=[],

                    offset=0,

                    total=0,

                ),

            )

            return



        cursor = db.books.find({

            "_id": {"$in": saved_ids},

            "status": "Available",

            "admin_hidden": {"$ne": True},

        })



        books_by_id = {}



        async for book in cursor:

            books_by_id[book["_id"]] = book



        # Preserve the original save order.

        available_books = [

            books_by_id[book_id]

            for book_id in saved_ids

            if book_id in books_by_id

        ]



        total = len(available_books)



        if total == 0:

            await safe_edit(

                query,

                "❤️ <b>သိမ်းထားသောစာအုပ်များ</b>\n\n"

                "လက်ရှိ ရောင်းရန်ရှိတဲ့ Favorites မရှိပါဘူး။\n"

                "အရင်သိမ်းထားတဲ့စာအုပ်တွေ ရောင်းထွက်သွားနိုင်ပါတယ်။",

                favorites_list_keyboard(

                    books=[],

                    offset=0,

                    total=0,

                ),

            )

            return



        if offset >= total:

            offset = ((total - 1) // PAGE_SIZE) * PAGE_SIZE



        page_books = available_books[offset:offset + PAGE_SIZE]

        page_number = offset // PAGE_SIZE + 1

        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE



        lines = [

            "❤️ <b>သိမ်းထားသောစာအုပ်များ</b>",

            "",

            f"📚 ရောင်းရန်ရှိသော Favorites: <b>{total}</b>",

            f"📄 စာမျက်နှာ: <b>{page_number}/{total_pages}</b>",

            "",

        ]



        for index, book in enumerate(page_books, start=offset + 1):

            title = escape(str(book.get("title", "Untitled")))

            major = escape(str(book.get("major", "N/A")))

            year = escape(str(book.get("year", "N/A")))

            semester = escape(format_semester(book.get("year"), book.get("semester", "N/A")))

            price = escape(format_price(book))



            lines.extend([

                f"<b>{index}. {title}</b>",

                f"🎓 {major} | Year {year} | Semester {semester}",

                f"💰 {price}",

                "",

            ])



        lines.append("အသေးစိတ်ကြည့်ရန် စာအုပ်ကို ရွေးချယ်ပါ။")



        await safe_edit(

            query,

            "\n".join(lines),

            favorites_list_keyboard(

                books=page_books,

                offset=offset,

                total=total,

            ),

        )



    except Exception:

        logger.exception(

            "Could not load favorites for user %s.",

            user_id,

        )



        await safe_edit(

            query,

            "Favorites စာရင်းကို ရယူရာမှာ အမှားဖြစ်သွားပါတယ်။",

            get_main_menu(),

        )





async def show_favorite_detail(

    query,

    user_id: int,

    raw_book_id: str,

    offset: int,

) -> None:

    """Display a saved book's details."""



    try:

        book_id = ObjectId(raw_book_id)



    except (InvalidId, TypeError):

        await safe_edit(

            query,

            "စာအုပ် ID မမှန်ကန်ပါ။",

            get_main_menu(),

        )

        return



    db = get_database()



    favorite = await db.favorites.find_one({

        "user_id": user_id,

        "book_id": book_id,

    })



    if favorite is None:

        await safe_edit(

            query,

            "ဒီစာအုပ်ကို Favorites ထဲမှာ မတွေ့ပါဘူး။",

            favorites_list_keyboard([], 0, 0),

        )

        return



    book = await db.books.find_one({

        "_id": book_id,

    })



    if book is None:

        await safe_edit(

            query,

            "ဒီစာအုပ်ကို ရှာမတွေ့တော့ပါ။ Favorites ထဲက ဖယ်ရှားနိုင်ပါတယ်။",

            favorite_book_detail_keyboard(

                book_id=str(book_id),

                offset=offset,

                available=False,

            ),

        )

        return



    status = book.get("status", "Unknown")

    available = (

        status == "Available"

        and not book.get("admin_hidden")

    )



    status_text = STATUS_LABELS.get(

        status,

        escape(status),

    )



    title = escape(str(book.get("title", "Untitled")))

    major = escape(str(book.get("major", "N/A")))

    year = escape(str(book.get("year", "N/A")))

    semester = escape(format_semester(book.get("year"), book.get("semester", "N/A")))

    condition = escape(str(book.get("condition", "N/A")))

    price = escape(format_price(book))



    text = (

        "❤️ <b>Favorite Book Details</b>\n\n"

        f"<b>{title}</b>\n\n"

        f"🎓 Major: {major}\n"

        f"📖 Year: {year}\n"

        f"📑 Semester: {semester}\n"

        f"💰 ဈေးနှုန်း: {price}\n"

        f"📝 အခြေအနေ: {condition}\n"

        f"📌 Status: {status_text}\n"

    )



    if not available:

        text += (

            "\n⚠️ ဒီစာအုပ်ကို လက်ရှိ ဝယ်ယူလို့မရပါဘူး။\n"

            "Favorites ထဲကနေ ဖယ်ရှားနိုင်ပါတယ်။"

        )



    await safe_edit(

        query,

        text,

        favorite_book_detail_keyboard(

            book_id=str(book_id),

            offset=offset,

            available=available,

        ),

    )





async def remove_favorite(

    query,

    user_id: int,

    raw_book_id: str,

    offset: int,

) -> None:

    """Remove a saved book and refresh the list."""



    try:

        book_id = ObjectId(raw_book_id)



    except (InvalidId, TypeError):

        await safe_edit(

            query,

            "စာအုပ် ID မမှန်ကန်ပါ။",

            favorites_list_keyboard([], 0, 0),

        )

        return



    db = get_database()



    try:

        result = await db.favorites.delete_one({

            "user_id": user_id,

            "book_id": book_id,

        })



    except PyMongoError:

        logger.exception(

            "Could not remove favorite %s for user %s.",

            book_id,

            user_id,

        )



        await safe_edit(

            query,

            "Favorites ထဲက ဖယ်ရှားရာမှာ အမှားဖြစ်သွားပါတယ်။",

            favorites_list_keyboard([], 0, 0),

        )

        return



    if result.deleted_count == 0:

        await safe_edit(

            query,

            "ဒီစာအုပ်ကို Favorites ထဲမှာ မတွေ့ပါဘူး။",

            favorites_list_keyboard([], 0, 0),

        )

        return



    await show_favorites(

        query,

        user_id=user_id,

        offset=offset,

    )





async def favorites_command(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE,

) -> None:

    """Provide a /favorites command entry point."""



    message = update.effective_message



    if message is None:

        return



    await message.reply_text(

        "❤️ <b>သိမ်းထားသောစာအုပ်များ</b>\n\n"

        "အောက်က Button ကို နှိပ်ပြီး Favorites ထဲကစာအုပ်တွေကို ကြည့်ပါ။",

        reply_markup=InlineKeyboardMarkup([

            [

                InlineKeyboardButton(

                    "❤️ Favorites ဖွင့်မည်",

                    callback_data="favorites:list:0",

                )

            ]

        ]),

        parse_mode="HTML",

    )





async def favorites_callback(

    update: Update,

    context: ContextTypes.DEFAULT_TYPE,

) -> None:

    """Route favorite saving, listing, details and removal."""



    query = update.callback_query

    user = update.effective_user



    if query is None or query.data is None or user is None:

        return



    data = query.data

    parts = data.split(":")



    # A save action originates from a channel listing.

    if data.startswith("favorite:add:"):

        await save_favorite(

            query,

            context,

            data.removeprefix("favorite:add:"),

        )

        return



    await query.answer()



    if data in ("menu:favorites", "favorites:exit"):

        if data == "favorites:exit":

            await safe_edit(

                query,

                "🎓 <b>University Book Marketplace</b>\n\n"

                "လုပ်ဆောင်လိုသော Menu ကို ရွေးချယ်ပါ။",

                get_main_menu(),

            )

        else:

            await show_favorites(

                query,

                user_id=user.id,

                offset=0,

            )

        return



    # favorites:list:<offset>

    if len(parts) == 3 and parts[:2] == ["favorites", "list"]:

        try:

            offset = int(parts[2])

        except ValueError:

            offset = 0



        await show_favorites(

            query,

            user_id=user.id,

            offset=max(0, offset),

        )

        return



    # favorites:book:<book_id>:<offset>

    if len(parts) == 4 and parts[:2] == ["favorites", "book"]:

        try:

            offset = int(parts[3])

        except ValueError:

            offset = 0



        await show_favorite_detail(

            query,

            user_id=user.id,

            raw_book_id=parts[2],

            offset=max(0, offset),

        )

        return



    # favorites:remove:<book_id>:<offset>

    if len(parts) == 4 and parts[:2] == ["favorites", "remove"]:

        try:

            offset = int(parts[3])

        except ValueError:

            offset = 0



        await remove_favorite(

            query,

            user_id=user.id,

            raw_book_id=parts[2],

            offset=max(0, offset),

        )

        return





def register_favorites_handlers(

    application: Application,

) -> None:

    application.add_handler(

        CommandHandler("favorites", favorites_command)

    )



    application.add_handler(

        CallbackQueryHandler(

            favorites_callback,

            pattern=r"^(?:menu:favorites|favorite:add:|favorites:)",

        )

    )
