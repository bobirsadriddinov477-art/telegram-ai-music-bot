import os
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_TOKEN = os.getenv("REPLICATE_TOKEN")

menu_keyboard = [
    ["🎵 Create Music"],
    ["💰 Balance", "ℹ Help"]
]

reply_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_prompt"] = False
    await update.message.reply_text(
        "Salom! Men AI Music Botman 🎵\nKerakli bo‘limni tanlang:",
        reply_markup=reply_markup
    )


def generate_music(prompt):

    url = "https://api.replicate.com/v1/predictions"

    headers = {
        "Authorization": f"Token {REPLICATE_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {
        "version": "671ac645ce5e5528c14b3a51f7b19e9c81b190e0b8c1ff717a8ba4c8988e85b7",
        "input": {
            "prompt": prompt
        }
    }

    response = requests.post(url, headers=headers, json=data)

    return response.json()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "🎵 Create Music":
        context.user_data["waiting_for_prompt"] = True
        await update.message.reply_text("Menga prompt yuboring")

    elif context.user_data.get("waiting_for_prompt"):

        context.user_data["waiting_for_prompt"] = False

        await update.message.reply_text("⏳ Musiqa yaratilmoqda...")

        result = generate_music(text)

        await update.message.reply_text("AI generation boshlandi 🚀")

    elif text == "💳 Balance":
        await update.message.reply_text("Balans: 0 kredit")

    elif text == "ℹ️ Help":
        await update.message.reply_text("Prompt yuboring va AI musiqa yaratiladi")

    else:
        await update.message.reply_text("Kerakli tugmani tanlang")


app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()