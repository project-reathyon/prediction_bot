# First, update your requirements.txt
# Add 'Flask' to it:
# python-telegram-bot
# python-dotenv
# loguru
# Flask  <-- ADD THIS LINE

# Now, update your main.py

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
from dotenv import load_dotenv
from model import get_top_predictions
from scheduler import can_predict_today, register_prediction
from loguru import logger

# Import Flask for the web server
from flask import Flask, request

# Load env vars
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set in environment variables. Bot cannot start.")
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set in environment variables.")

# --- Render Specific: Get the port and webhook URL from environment variables ---
PORT = int(os.environ.get("PORT", "8443")) # Render provides a PORT env var
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") # You'll set this on Render


# Define league names (for user-friendly responses)
LEAGUE_NAMES = {
    "premier": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "all": "All Leagues"
}

# Safe logger - Renamed for clarity, now handles different update types gracefully.
async def log_user_activity(update: Update):
    """Logs incoming requests from users."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        logger.warning("Received an update without an effective user or chat.")
        return

    user_info = f"@{user.username}" if user.username else f"User ID: {user.id}"
    chat_info = f"Chat ID: {chat.id}"

    msg_text = "No message text"

    if update.message:
        msg_text = update.message.text
    elif update.callback_query:
        msg_text = update.callback_query.data
    elif update.edited_message:
        msg_text = update.edited_message.text
    elif update.channel_post:
        msg_text = update.channel_post.text
    elif update.edited_channel_post:
        msg_text = update.edited_channel_post.text

    logger.info(f"[{chat_info}] {user_info}: {msg_text}")


# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, welcoming the user."""
    await log_user_activity(update)
    welcome_message = (
        "👋 *Welcome to the Football Prediction Bot!* ⚽\n\n"
        "I can help you get daily top football predictions.\n\n"
        "Use /predict to see today's top matches and predictions.\n"
        "Use /help to see all available commands and learn more.\n\n"
        "Let's get started!"
    )
    await update.message.reply_text(welcome_message, parse_mode="MarkdownV2")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command, providing a list of commands."""
    await log_user_activity(update)
    help_text = (
        "📋 *Available Commands:*\n"
        "• /start – Get a welcome message and introduction to the bot\n"
        "• /predict – Show today’s top football predictions\n"
        "• /help – Display this help message\n\n"
        "Stay tuned for more features!"
    )
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /predict command, showing daily football predictions."""
    await log_user_activity(update)

    if not can_predict_today():
        await update.message.reply_text("⚠️ *Daily Prediction Limit Reached!* ⚠️\n\n"
                                        "To ensure fair usage and optimal performance, I can only provide "
                                        "predictions once per day globally\\. Please try again tomorrow\\! "
                                        "Thank you for your understanding\\.",
                                        parse_mode="MarkdownV2")
        return

    predictions = get_top_predictions()
    register_prediction()

    if not predictions:
        await update.message.reply_text("🗓️ *No predictions available for today yet\\!* 🗓️\n\n"
                                        "Please check back later or tomorrow\\.",
                                        parse_mode="MarkdownV2")
        return

    msg_parts = ["⚽ *Today's Top Football Predictions:* ⚽\n\n```"]
    for i, p in enumerate(predictions):
        label = p.get('label', 'N/A')
        confidence = p.get('confidence', 'N/A')
        msg_parts.append(f"{i+1}. {label} (Confidence: {confidence}%)")
    msg_parts.append("```\n\n")

    keyboard = [
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="premier")],
        [InlineKeyboardButton("🇪🇸 La Liga", callback_data="laliga")],
        [InlineKeyboardButton("🇮🇹 Serie A", callback_data="seriea")],
        [InlineKeyboardButton("✨ Show All Predictions", callback_data="all")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    full_message = "".join(msg_parts) + "Select a league below to see more details (if available):"

    await update.message.reply_text(
        full_message,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard button presses."""
    query = update.callback_query
    await log_user_activity(update)
    await query.answer()

    league_code = query.data
    league_name = LEAGUE_NAMES.get(league_code, "Unknown League")

    if league_code == "all":
        response_text = "✨ *Showing All Available Predictions!* ✨\n" \
                        "This feature is under development\\. For now, the initial prediction message " \
                        "already displays the top predictions across all leagues\\."
    else:
        response_text = f"📊 *Predictions for {league_name} coming soon\\!* 📊\n" \
                        "This feature is currently under development\\. Please check back later for " \
                        "league-specific predictions\\."

    await query.edit_message_text(
        response_text,
        parse_mode="MarkdownV2"
    )

# Handle all unexpected errors gracefully
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs errors and sends a user-friendly message."""
    logger.error(msg="Exception while handling update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "🚨 *Oops! Something went wrong\\.* 🚨\n"
                "I've logged the error and our team will look into it\\. Please try again later\\.",
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
    else:
        logger.warning("Error occurred, but couldn't send message back to user due to missing update.message.")


# --- Main bot application setup ---
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("predict", predict))
app.add_handler(CallbackQueryHandler(handle_button))
app.add_error_handler(error_handler)

# --- Webhook setup using Flask ---
flask_app = Flask(__name__)

@flask_app.post("/")
async def webhook_handler():
    """Handle incoming Telegram updates via webhook."""
    # Convert incoming request body to Telegram Update object
    update = Update.de_json(request.get_json(force=True), app.bot)
    # Process the update with the bot's application
    await app.process_update(update)
    return "ok"

if __name__ == "__main__":
    logger.info("Starting Football Prediction Bot...")

    if WEBHOOK_URL:
        # Set up the webhook with Telegram
        logger.info(f"Setting webhook to {WEBHOOK_URL}")
        # Use app.bot.set_webhook() inside an async context
        # This requires running the Flask app to create the event loop
        # A simple way to do this is to set it up before starting the Flask app.
        import asyncio
        async def setup_webhook():
            await app.bot.set_webhook(url=WEBHOOK_URL)
            logger.info("Webhook set successfully.")
        asyncio.run(setup_webhook())

        # Start the Flask web server
        flask_app.run(host="0.0.0.0", port=PORT)
    else:
        # Fallback to polling for local development or if WEBHOOK_URL isn't set
        logger.warning("WEBHOOK_URL not set. Running in polling mode. This is not recommended for Render Web Services.")
        app.run_polling()
