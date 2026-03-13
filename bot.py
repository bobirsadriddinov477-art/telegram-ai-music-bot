import os
import asyncio
import logging
import sqlite3
from contextlib import closing
from typing import Optional

import replicate
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")
if not REPLICATE_API_TOKEN:
    raise RuntimeError("REPLICATE_API_TOKEN topilmadi")

os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

MODEL = "meta/musicgen:671ac645ce5e552c63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
DB_PATH = "bot_data.db"

START_COINS = 30
MUSIC_PRICE = 10

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                coins INTEGER NOT NULL DEFAULT 30,
                total_generations INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def get_or_create_user(user_id: int, username: Optional[str], first_name: Optional[str]):
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, coins, total_generations)
                VALUES (?, ?, ?, ?, 0)
                """,
                (user_id, username, first_name, START_COINS),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        return row


def get_user(user_id: int):
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def update_user_info(user_id: int, username: Optional[str], first_name: Optional[str]):
    with closing(get_db()) as conn:
        conn.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
            """,
            (username, first_name, user_id),
        )
        conn.commit()


def try_spend_coins(user_id: int, amount: int) -> bool:
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT coins FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            return False

        if row["coins"] < amount:
            return False

        conn.execute(
            "UPDATE users SET coins = coins - ? WHERE user_id = ?",
            (amount, user_id),
        )
        conn.commit()
        return True


def refund_coins(user_id: int, amount: int):
    with closing(get_db()) as conn:
        conn.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id),
        )
        conn.commit()


def increment_generation(user_id: int):
    with closing(get_db()) as conn:
        conn.execute(
            """
            UPDATE users
            SET total_generations = total_generations + 1
            WHERE user_id = ?
            """,
            (user_id,),
        )
        conn.commit()


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎵 Create Music", callback_data="create_music")],
            [
                InlineKeyboardButton("🪙 Balance", callback_data="balance"),
                InlineKeyboardButton("ℹ Help", callback_data="help"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_prompt")],
        ]
    )


def build_prompt_help():
    return (
        "🎼 Menga prompt yuboring.\n\n"
        "Misollar:\n"
        "• cinematic piano with emotional strings\n"
        "• dark trap beat with hard 808 and bell melody\n"
        "• relaxing lofi beat with rain and soft piano\n\n"
        "Bekor qilish uchun: ❌ Cancel"
    )


def get_output_url(output) -> Optional[str]:
    if output is None:
        return None

    if isinstance(output, str):
        return output

    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, str):
            return first
        if hasattr(first, "url"):
            return first.url()

    if hasattr(output, "url"):
        return output.url()

    return None


async def generate_music(prompt: str):
    input_data = {
        "prompt": prompt,
        "model_version": "stereo-large",
        "output_format": "mp3",
        "normalization_strategy": "peak",
    }

    output = await asyncio.to_thread(
        replicate.run,
        MODEL,
        input=input_data,
    )
    return output


async def animated_status(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    frames = [
        "🎵 Musiqa yaratilmoqda",
        "🎵 Musiqa yaratilmoqda.",
        "🎵 Musiqa yaratilmoqda..",
        "🎵 Musiqa yaratilmoqda...",
        "🎧 AI composing",
        "🎼 Melody building",
        "🥁 Beat layering",
        "🎹 Finalizing track",
    ]
    i = 0
    try:
        while True:
            text = frames[i % len(frames)]
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                )
            except Exception:
                pass

            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_AUDIO)
            except Exception:
                pass

            i += 1
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        raise


async def send_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str):
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=main_menu_keyboard(),
    )


async def show_balance(chat_id: int, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    user = get_user(user_id)
    text = (
        "🪙 Sizning balansingiz\n\n"
        f"Coin: {user['coins']}\n"
        f"Yaratilgan music soni: {user['total_generations']}\n"
        f"1 ta music narxi: {MUSIC_PRICE} coin\n\n"
        f"Boshlang‘ich bonus: {START_COINS} coin"
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=main_menu_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username, user.first_name)
    update_user_info(user.id, user.username, user.first_name)

    context.user_data["waiting_for_prompt"] = False

    text = (
        "Salom! Men AI Music Botman 🎵\n\n"
        f"Boshlang‘ich balans: {db_user['coins']} coin\n"
        f"1 ta music generatsiya narxi: {MUSIC_PRICE} coin\n"
        "Pastdagi tugmalardan foydalaning."
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_prompt"] = False
    await send_main_menu(update.effective_chat.id, context, "📍 Asosiy menyu:")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ Bot qanday ishlaydi:\n\n"
        "1. 🎵 Create Music ni bosing\n"
        "2. Prompt yuboring\n"
        f"3. Har bir generatsiya {MUSIC_PRICE} coin yechadi\n"
        "4. Audio tayyor bo‘lsa sizga yuboraman\n\n"
        f"Yangi userga {START_COINS} coin beriladi."
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    get_or_create_user(user.id, user.username, user.first_name)
    update_user_info(user.id, user.username, user.first_name)

    data = query.data

    if data == "create_music":
        context.user_data["waiting_for_prompt"] = True
        await query.message.reply_text(build_prompt_help(), reply_markup=main_menu_keyboard())
        return

    if data == "balance":
        context.user_data["waiting_for_prompt"] = False
        await show_balance(query.message.chat_id, context, user.id)
        return

    if data == "help":
        context.user_data["waiting_for_prompt"] = False
        await query.message.reply_text(
            "ℹ Bot qanday ishlaydi:\n\n"
            "1. 🎵 Create Music ni bosing\n"
            "2. Prompt yuboring\n"
            f"3. Har bir generatsiya {MUSIC_PRICE} coin yechadi\n"
            "4. Audio tayyor bo‘lsa sizga yuboraman\n\n"
            f"Yangi userga {START_COINS} coin beriladi.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "cancel_prompt":
        context.user_data["waiting_for_prompt"] = False
        await query.message.reply_text(
            "❌ Prompt yuborish bekor qilindi.",
            reply_markup=main_menu_keyboard(),
        )
        return


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.strip()

    get_or_create_user(user.id, user.username, user.first_name)
    update_user_info(user.id, user.username, user.first_name)

    reserved_texts = {
        "/menu",
        "menu",
        "🎵 create music",
        "🪙 balance",
        "ℹ help",
        "❌ cancel",
        "help",
        "balance",
        "create music",
        "cancel",
    }

    if text.lower() in {"/menu", "menu"}:
        context.user_data["waiting_for_prompt"] = False
        await send_main_menu(update.effective_chat.id, context, "📍 Asosiy menyu:")
        return

    if context.user_data.get("waiting_for_prompt") and text.lower() in reserved_texts:
        await update.message.reply_text(
            "⚠ Hozir men sizdan musiqa prompti kutyapman.\n"
            "Masalan: cinematic piano with emotional strings\n\n"
            "Bekor qilish uchun ❌ Cancel ni bosing.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not context.user_data.get("waiting_for_prompt"):
        await update.message.reply_text(
            "Kerakli bo‘limni tanlang.",
            reply_markup=main_menu_keyboard(),
        )
        return

    user_row = get_user(user.id)
    if user_row["coins"] < MUSIC_PRICE:
        context.user_data["waiting_for_prompt"] = False
        await update.message.reply_text(
            "❌ Coin yetarli emas.\n\n"
            f"Sizda: {user_row['coins']} coin\n"
            f"Kerak: {MUSIC_PRICE} coin\n\n"
            "To‘lov tizimini keyingi bosqichda ulaymiz.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not try_spend_coins(user.id, MUSIC_PRICE):
        context.user_data["waiting_for_prompt"] = False
        await update.message.reply_text(
            "❌ Coin yechishda xatolik bo‘ldi.",
            reply_markup=main_menu_keyboard(),
        )
        return

    context.user_data["waiting_for_prompt"] = False

    status_msg = await update.message.reply_text("🎵 Musiqa yaratilmoqda")
    anim_task = asyncio.create_task(
        animated_status(context, update.effective_chat.id, status_msg.message_id)
    )

    try:
        audio_output = await generate_music(text)
        audio_url = get_output_url(audio_output)

        anim_task.cancel()
        try:
            await anim_task
        except asyncio.CancelledError:
            pass

        if not audio_url:
            refund_coins(user.id, MUSIC_PRICE)
            await status_msg.edit_text("❌ Audio link olinmadi. Coin qaytarildi.")
            await send_main_menu(update.effective_chat.id, context, "Asosiy menyu:")
            return

        increment_generation(user.id)
        current_user = get_user(user.id)

        await status_msg.edit_text("✅ Musiqa tayyor! Yuboryapman...")
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.UPLOAD_AUDIO,
        )
        await update.message.reply_audio(
            audio=audio_url,
            caption=(
                "🎧 Tayyor!\n"
                f"🪙 Qolgan coin: {current_user['coins']}\n"
                f"💸 Sarflandi: {MUSIC_PRICE} coin"
            ),
        )
        await send_main_menu(
            update.effective_chat.id,
            context,
            "Yana music yaratish uchun tugmani bosing.",
        )

    except Exception as e:
        logger.exception("Music generation error: %s", e)

        anim_task.cancel()
        try:
            await anim_task
        except asyncio.CancelledError:
            pass

        refund_coins(user.id, MUSIC_PRICE)

        await status_msg.edit_text(
            "❌ Xatolik yuz berdi.\n"
            "Coin qaytarildi."
        )
        await send_main_menu(update.effective_chat.id, context, "Asosiy menyu:")


def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()