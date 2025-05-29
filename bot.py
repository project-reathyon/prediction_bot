import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)
from dotenv import load_dotenv
from model import get_top_predictions
from scheduler import can_predict_today, register_prediction
from loguru import logger

# Load env vars
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables.")

# Define league names (for user-friendly responses)
LEAGUE_NAMES = {
    "premier": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A"
}

# Safe logger
async def log_request(update: Update):
    user = update.effective_user
    if update.message:
        msg_text = update.message.text
    elif update.callback_query:
        msg_text = update.callback_query.data
    else:
        msg_text = "No message text"
    logger.info(f"Request from @{user.username} ({user.id}): {msg_text}")

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_request(update)
    await update.message.reply_text("⚽ Welcome to the Football Prediction Bot!")
    await update.message.reply_text("Use /predict to get today's top predictions.\nUse /help for available commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_request(update)
    help_text = (
        "📋 *Available Commands:*\n"
        "/start – Welcome message\n"
        "/predict – Show today’s top predictions\n"
        "/help – Show this help message\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_request(update)

    if not can_predict_today():
        await update.message.reply_text("⚠️ Daily prediction limit reached. Try again tomorrow.")
        return

    predictions = get_top_predictions()
    register_prediction()
    msg = "\n".join([
        f"✅ {i+1}. {p['label']} (Confidence: {p['confidence']}%)"
        for i, p in enumerate(predictions)
    ])
    keyboard = [
        [InlineKeyboardButton("⚽ Premier League", callback_data="premier")],
        [InlineKeyboardButton("🇪🇸 La Liga", callback_data="laliga")],
        [InlineKeyboardButton("🇮🇹 Serie A", callback_data="seriea")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔝 Today's Top Football Predictions:\n{msg}",
        reply_markup=reply_markup
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await log_request(update)
    await query.answer()

    league_code = query.data
    league_name = LEAGUE_NAMES.get(league_code, "Unknown League")
    await query.edit_message_text(f"📊 Predictions for {league_name} coming soon...")

# Handle all unexpected errors gracefully
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("🚨 An error occurred. Please try again later.")

# Build and start bot
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("predict", predict))
app.add_handler(CallbackQueryHandler(handle_button))
app.add_error_handler(error_handler)

if __name__ == "__main__":
    logger.info("Starting bot...")
    app.run_polling()
