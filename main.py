import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
# Corrected ParseMode import for python-telegram-bot v20+
from telegram.constants import ParseMode
from dotenv import load_dotenv
from model import get_top_predictions
from scheduler import can_predict_today, register_prediction
from loguru import logger

# Import Flask for the web server
from flask import Flask, request

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set in environment variables. Bot cannot start.")
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set in environment variables.")

PORT = int(os.environ.get("PORT", "8443"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL is not set. The bot will try to run in polling mode if not started by Gunicorn/Hypercorn.")

LEAGUE_NAMES = {
    "premier": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "all": "All Leagues"
}

# --- Handler function definitions MUST come before they are registered ---

# --- Safe logger to track user activity ---
async def log_user_activity(update: Update):
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

# --- Telegram Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_user_activity(update)
    welcome_message = (
        "👋 <b>Welcome to the Football Prediction Bot!</b> ⚽\n\n"
        "I can help you get daily top football predictions.\n\n"
        "Use /predict to see today's top matches and predictions.\n"
        "Use /help to see all available commands and learn more.\n\n"
        "Let's get started!"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_user_activity(update)
    help_text = (
        "📋 <b>Available Commands:</b>\n"
        "• /start – Get a welcome message and introduction to the bot\n"
        "• /predict – Show today’s top football predictions\n"
        "• /help – Display this help message\n\n"
        "Stay tuned for more features!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_user_activity(update)
    if not can_predict_today():
        await update.message.reply_text("⚠️ <b>Daily Prediction Limit Reached!</b> ⚠️\n\n"
                                        "To ensure fair usage and optimal performance, I can only provide "
                                        "predictions once per day globally. Please try again tomorrow! "
                                        "Thank you for your understanding.",
                                        parse_mode=ParseMode.HTML)
        return

    predictions = get_top_predictions() # Assume this function is defined elsewhere
    register_prediction() # Assume this function is defined elsewhere

    if not predictions:
        await update.message.reply_text("🗓️ <b>No predictions available for today yet!</b> 🗓️\n\n"
                                        "Please check back later or tomorrow.",
                                        parse_mode=ParseMode.HTML)
        return

    msg_parts = ["⚽ <b>Today's Top Football Predictions:</b> ⚽\n\n<pre><code>"]
    for i, p in enumerate(predictions):
        label = p.get('label', 'N/A')
        confidence = p.get('confidence', 'N/A')
        # Ensuring confidence is formatted nicely if it's a number
        try:
            confidence_str = f"{float(confidence):.2f}" if isinstance(confidence, (float, int)) else str(confidence)
        except ValueError:
            confidence_str = str(confidence)
        msg_parts.append(f"{i+1}. {label} (Confidence: {confidence_str}%)")
    msg_parts.append("</code></pre>\n\n")

    keyboard = [
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="premier")],
        [InlineKeyboardButton("🇪🇸 La Liga", callback_data="laliga")],
        [InlineKeyboardButton("🇮🇹 Serie A", callback_data="seriea")],
        [InlineKeyboardButton("✨ Show All Predictions", callback_data="all")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    final_sentence = "Select a league below to see more details (if available):"
    full_message = "".join(msg_parts) + final_sentence
    await update.message.reply_text(
        full_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await log_user_activity(update) # Log after answering to ensure responsiveness
    league_code = query.data
    league_name = LEAGUE_NAMES.get(league_code, "Unknown League")

    if league_code == "all":
        response_text = "✨ <b>Showing All Available Predictions!</b> ✨\n" \
                        "This feature is under development. For now, the initial prediction message " \
                        "already displays the top predictions across all leagues."
    else:
        response_text = f"📊 <b>Predictions for {league_name} coming soon!</b> 📊\n" \
                        "This feature is currently under development. Please check back later for " \
                        "league-specific predictions."
    await query.edit_message_text(
        response_text,
        parse_mode=ParseMode.HTML
    )

# --- Handle all unexpected errors gracefully ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "🚨 <b>Oops! Something went wrong.</b> 🚨\n"
                "I've logged the error and our team will look into it. Please try again later.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}", exc_info=True)
    elif isinstance(update, Update) and update.callback_query: # Handle errors in callbacks too
        try:
            await update.callback_query.message.reply_text(
                 "🚨 <b>Oops! Something went wrong with that action.</b> 🚨\n"
                "I've logged the error. Please try again later.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user after callback query error: {e}", exc_info=True)
    else:
        logger.warning("Error occurred, but couldn't send message back to user due to missing update.message or update.callback_query.")


# --- Initialize the Telegram Application globally ---
# We build the application here.
app = ApplicationBuilder().token(TOKEN).build()

# The actual initialization and webhook setting will happen when Hypercorn starts.

# --- Register handlers for your bot commands and callbacks ---
# These are now registered AFTER the functions are defined
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("predict", predict))
app.add_handler(CallbackQueryHandler(handle_button))
app.add_error_handler(error_handler)


# --- Flask Webhook Endpoint ---
flask_app = Flask(__name__)

# This is where we handle the application lifecycle (initialize, set_webhook)
# within the Hypercorn's event loop.
@flask_app.before_serving
async def startup_event():
    """Initializes the PTB application and sets the webhook before Hypercorn starts serving requests."""
    logger.info("Running startup event for PTB Application.")
    # Ensure an event loop is available for PTB's async operations during startup
    # This might not be strictly necessary if Hypercorn sets one up, but can be a safeguard
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    await app.initialize()
    logger.info("Telegram Application initialized.")
    if WEBHOOK_URL:
        try:
            await app.bot.set_webhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)
            logger.info(f"Webhook set successfully to {WEBHOOK_URL}.")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}", exc_info=True)
    else:
        logger.warning("WEBHOOK_URL not set. Skipping webhook setup. Bot will not receive updates via webhook.")

@flask_app.post("/")
async def webhook_handler():
    try:
        request_json = await request.get_json(force=True) # Use await for async flask
        # logger.debug(f"Received webhook update (raw): {request_json}") # DEBUG level if too verbose
        update = Update.de_json(request_json, app.bot)
        # logger.debug(f"Deserialized update: {update}") # DEBUG level
        await app.process_update(update)
        return "ok", 200
    except Exception as e:
        logger.error(f"Error processing webhook update in webhook_handler: {e}", exc_info=True)
        return "error", 500

# We don't run flask_app.run() or asyncio.run() here because Hypercorn manages the server.
if __name__ == "__main__":
    logger.info("Bot script executed. Hypercorn should manage the Flask application and PTB lifecycle.")
    # For local testing without Hypercorn and WEBHOOK_URL set, you might add polling:
    # if not WEBHOOK_URL:
    #     logger.info("WEBHOOK_URL not found, attempting to run in polling mode for local testing.")
    #     # PTB's Application.run_polling() needs to be run in an asyncio event loop.
    #     # However, Flask's development server (flask_app.run()) is not async by default
    #     # and mixing it with PTB's asyncio polling directly here can be complex.
    #     # It's generally better to decide on one deployment strategy (webhook or polling)
    #     # or use different entry points/configurations for them.
    #     # The current setup is primarily for webhook with Hypercorn.
    #     # If you absolutely need to run polling from this script directly:
    #     # async def main_polling():
    #     #     await app.initialize()
    #     #     await app.start()
    #     #     await app.updater.start_polling() # For older PTB versions with Updater
    #     #     # For PTB v20+ Application
    #     #     await app.run_polling()
    #     #
    #     # if not WEBHOOK_URL:
    #     #    asyncio.run(main_polling())
    # else:
    #    logger.info("WEBHOOK_URL is set. Assuming server (like Hypercorn) will run the app.")
    pass
