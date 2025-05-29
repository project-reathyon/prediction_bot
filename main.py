import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
# Import escape_markdown from telegram.helpers
from telegram.helpers import escape_markdown
from dotenv import load_dotenv
from model import get_top_predictions
from scheduler import can_predict_today, register_prediction
from loguru import logger

# Import Flask for the web server
from flask import Flask, request

# Load environment variables from .env file (for local development)
# On Render, these are set directly in the environment variables configuration.
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set in environment variables. Bot cannot start.")
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set in environment variables.")

# --- Render Specific: Get the port and webhook URL from environment variables ---
# Render provides the PORT environment variable. Default to 8443 if not found.
PORT = int(os.environ.get("PORT", "8443"))
# WEBHOOK_URL must be set in Render's environment variables.
# It should be your Render service's URL (e.g., https://your-service-name.onrender.com/)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL is not set. The bot will try to run in polling mode if not started by Gunicorn, but this is not recommended for Render Web Services.")

# Define league names (for user-friendly responses)
LEAGUE_NAMES = {
    "premier": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "all": "All Leagues"
}

# --- Safe logger to track user activity ---
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
    # Add more conditions for other update types if relevant

    logger.info(f"[{chat_info}] {user_info}: {msg_text}")

# --- Telegram Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, welcoming the user."""
    await log_user_activity(update)
    welcome_message = (
        "👋 *Welcome to the Football Prediction Bot\\!* ⚽\n\n" # Escaped '!'
        "I can help you get daily top football predictions\\.\n\n" # Escaped '.'
        "Use /predict to see today's top matches and predictions\\.\n" # Escaped '.'
        "Use /help to see all available commands and learn more\\.\n\n" # Escaped '.'
        "Let's get started\\!" # Escaped '!'
    )
    # Using MarkdownV2 for consistency and better formatting
    await update.message.reply_text(welcome_message, parse_mode="MarkdownV2")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command, providing a list of commands."""
    await log_user_activity(update)
    help_text = (
        "📋 \\*Available Commands:\\*\n" # Escaped '*'
        "• /start – Get a welcome message and introduction to the bot\n"
        "• /predict – Show today’s top football predictions\n"
        "• /help – Display this help message\n\n"
        "Stay tuned for more features\\!" # Escaped '!'
    )
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /predict command, showing daily football predictions."""
    await log_user_activity(update)

    if not can_predict_today():
        await update.message.reply_text("⚠️ \\*Daily Prediction Limit Reached\\!\\* ⚠️\n\n"
                                        "To ensure fair usage and optimal performance, I can only provide "
                                        "predictions once per day globally\\\\. Please try again tomorrow\\\\! "
                                        "Thank you for your understanding\\\\.",
                                        parse_mode="MarkdownV2")
        return

    predictions = get_top_predictions()
    register_prediction()

    if not predictions:
        await update.message.reply_text("🗓️ \\*No predictions available for today yet\\!\\* 🗓️\n\n"
                                        "Please check back later or tomorrow\\\\.",
                                        parse_mode="MarkdownV2")
        return

    msg_parts = ["⚽ \\*Today's Top Football Predictions:\\* ⚽\n\n```"] # Escaped '*'
    for i, p in enumerate(predictions):
        label = p.get('label', 'N/A')
        confidence = p.get('confidence', 'N/A')
        # Escape characters in the prediction label and confidence using escape_markdown
        escaped_label = escape_markdown(str(label), version=2)
        escaped_confidence = escape_markdown(str(confidence), version=2)
        msg_parts.append(f"{i+1}\\. {escaped_label} \\(Confidence\\: {escaped_confidence}\\%\\)") # Escaped '.', '(', ')', ':' and '%'
    msg_parts.append("```\n\n")

    keyboard = [
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="premier")],
        [InlineKeyboardButton("🇪🇸 La Liga", callback_data="laliga")],
        [InlineKeyboardButton("🇮🇹 Serie A", callback_data="seriea")],
        [InlineKeyboardButton("✨ Show All Predictions", callback_data="all")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Join message parts and escape final sentence
    final_sentence = "Select a league below to see more details (if available):"
    escaped_final_sentence = escape_markdown(final_sentence, version=2)
    full_message = "".join(msg_parts) + escaped_final_sentence

    await update.message.reply_text(
        full_message,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard button presses."""
    query = update.callback_query
    await log_user_activity(update)
    await query.answer() # Always answer the callback query to remove the loading animation.

    league_code = query.data
    league_name = LEAGUE_NAMES.get(league_code, "Unknown League")

    if league_code == "all":
        response_text = "\\*Showing All Available Predictions\\!\\* ✨\n" \
                        "This feature is under development\\\\. For now, the initial prediction message " \
                        "already displays the top predictions across all leagues\\\\."
    else:
        response_text = f"📊 \\*Predictions for {escape_markdown(league_name, version=2)} coming soon\\!\\* 📊\n" \
                        "This feature is currently under development\\\\. Please check back later for " \
                        "league-specific predictions\\\\."

    await query.edit_message_text(
        response_text,
        parse_mode="MarkdownV2"
    )

# --- Handle all unexpected errors gracefully ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs errors and sends a user-friendly message."""
    logger.error("Exception while handling update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            # Corrected message with escaped characters for MarkdownV2
            await update.effective_message.reply_text(
                "🚨 \\*Oops\\! Something went wrong\\\\.* 🚨\n" # Escaped '!', '.' and '*'
                "I've logged the error and our team will look into it\\\\. Please try again later\\\\.", # Escaped '.'
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            # This is the line that's causing the current error, but it's trying to log the error itself.
            # We already changed this in the previous full code update, so if you copied it, this should be fine.
            # Let's ensure the message itself is escaped here too, just in case.
            error_message_for_log = escape_markdown(str(e), version=2) # Escape any special chars in the error itself
            logger.error(f"Failed to send error message to user: {error_message_for_log}", exc_info=True)
    else:
        logger.warning("Error occurred, but couldn't send message back to user due to missing update.message.")


# --- Main bot application setup ---
# Build the Application instance
app = ApplicationBuilder().token(TOKEN).build()

# Initialize the application asynchronously and set webhook.
# This part MUST be run before any handlers are added or updates processed,
# especially with webhooks.
async def initialize_and_set_webhook():
    await app.initialize()
    logger.info("Telegram Application initialized.")

    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook set successfully to {WEBHOOK_URL}.")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}", exc_info=True)
    else:
        logger.warning("WEBHOOK_URL not set. Skipping webhook setup. Bot will not receive updates unless started in polling mode.")

# Run the initialization and webhook setup when the script starts
asyncio.run(initialize_and_set_webhook())

# Register handlers for your bot commands and callbacks
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("predict", predict))
app.add_handler(CallbackQueryHandler(handle_button))
app.add_error_handler(error_handler)


# --- Flask Webhook Endpoint ---
# Create a Flask app instance. This is what Hypercorn will run.
flask_app = Flask(__name__)

@flask_app.post("/")
async def webhook_handler():
    """
    Handles incoming Telegram updates via webhook.
    This function receives POST requests from Telegram's servers.
    """
    try:
        request_json = request.get_json(force=True)
        logger.info(f"Received webhook update: {request_json}")

        update = Update.de_json(request_json, app.bot)
        await app.process_update(update)

        return "ok"
    except Exception as e:
        logger.error(f"Error processing webhook update in webhook_handler: {e}", exc_info=True)
        return "error", 500

# This `if __name__ == "__main__":` block is primarily for local testing
# and ensures that Hypercorn can import `flask_app` without automatically running it.
if __name__ == "__main__":
    logger.info("Bot setup complete. Ready to receive webhooks.")
    logger.info("Note: For production (e.g., Render), use Hypercorn to run 'main:flask_app'.")
    # For local development/testing without Hypercorn, you could uncomment this:
    # flask_app.run(host="0.0.0.0", port=PORT, debug=True)
    # However, this line is typically *not* run when deployed with Hypercorn.
    # Hypercorn imports this file and directly calls `flask_app`.
