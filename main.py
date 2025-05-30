import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, # Explicitly import Application for type hinting if needed later
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode
from dotenv import load_dotenv
from model import get_top_predictions # Assuming these are correctly in model.py
from scheduler import can_predict_today, register_prediction # Assuming these are correctly in scheduler.py
from loguru import logger

# Import Flask for the web server
from flask import Flask, request

# Import WsgiToAsgi for wrapping Flask app
from asgiref.wsgi import WsgiToAsgi

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set in environment variables. Bot cannot start.")
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set in environment variables.")

PORT = int(os.environ.get("PORT", "8443"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not WEBHOOK_URL:
    logger.warning("WEBHOOK_URL is not set. Webhook setup will be skipped.")

LEAGUE_NAMES = {
    "premier": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "all": "All Leagues"
}

# --- Telegram Bot handler function definitions ---
async def log_user_activity(update: Update):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        logger.warning("Received an update without an effective user or chat.")
        return
    user_info = f"@{user.username}" if user.username else f"User ID: {user.id}"
    chat_info = f"Chat ID: {chat.id}"
    msg_text = "No message text"
    if update.message: msg_text = update.message.text
    elif update.callback_query: msg_text = update.callback_query.data
    elif update.edited_message: msg_text = update.edited_message.text
    elif update.channel_post: msg_text = update.channel_post.text
    elif update.edited_channel_post: msg_text = update.edited_channel_post.text
    logger.info(f"[{chat_info}] {user_info}: {msg_text}")

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
    predictions = get_top_predictions()
    register_prediction()
    if not predictions:
        await update.message.reply_text("🗓️ <b>No predictions available for today yet!</b> 🗓️\n\n"
                                        "Please check back later or tomorrow.",
                                        parse_mode=ParseMode.HTML)
        return
    msg_parts = ["⚽ <b>Today's Top Football Predictions:</b> ⚽\n\n<pre><code>"]
    for i, p in enumerate(predictions):
        label = p.get('label', 'N/A')
        confidence = p.get('confidence', 'N/A')
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
    await update.message.reply_text(full_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await log_user_activity(update)
    league_code = query.data
    league_name = LEAGUE_NAMES.get(league_code, "Unknown League")
    if league_code == "all":
        response_text = "✨ <b>Showing All Available Predictions!</b> ✨\nThis feature is under development. For now, the initial prediction message already displays the top predictions across all leagues."
    else:
        response_text = f"📊 <b>Predictions for {league_name} coming soon!</b> 📊\nThis feature is currently under development. Please check back later for league-specific predictions."
    await query.edit_message_text(response_text, parse_mode=ParseMode.HTML)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "🚨 <b>Oops! Something went wrong.</b> 🚨\nI've logged the error and our team will look into it. Please try again later.",
                parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}", exc_info=True)
    elif isinstance(update, Update) and update.callback_query:
        try:
            await update.callback_query.message.reply_text(
                 "🚨 <b>Oops! Something went wrong with that action.</b> 🚨\nI've logged the error. Please try again later.",
                parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send error message to user after callback query error: {e}", exc_info=True)
    else:
        logger.warning("Error occurred, but couldn't send message back to user due to missing update info.")

# --- Initialize the Telegram Application ---
# This is your main PTB application instance
ptb_application: Application = ApplicationBuilder().token(TOKEN).build()

# --- Register handlers for your bot commands and callbacks ---
ptb_application.add_handler(CommandHandler("start", start))
ptb_application.add_handler(CommandHandler("help", help_command))
ptb_application.add_handler(CommandHandler("predict", predict))
ptb_application.add_handler(CallbackQueryHandler(handle_button))
ptb_application.add_error_handler(error_handler)

# --- Flask Web Application Instance ---
# This is your Flask app, we'll give it a distinct name for clarity
_actual_flask_app = Flask(__name__)

# --- Flask Webhook Endpoint ---
@_actual_flask_app.post("/") # Use the specific Flask app instance for routing
async def webhook_handler(): # Flask supports async route handlers when run with ASGI
    try:
        request_json = await request.get_json(force=True)
        update = Update.de_json(request_json, ptb_application.bot) # Use ptb_application.bot
        await ptb_application.process_update(update) # Use ptb_application.process_update
        return "ok", 200
    except Exception as e:
        logger.error(f"Error processing webhook update in webhook_handler: {e}", exc_info=True)
        return "error", 500

# --- ASGI Lifespan Events for PTB Initialization and Shutdown ---
async def run_ptb_startup_tasks():
    """Initializes the PTB application and sets the webhook."""
    logger.info("Running PTB startup tasks.")
    await ptb_application.initialize() # Initialize the PTB application
    logger.info("Telegram Application initialized.")
    if WEBHOOK_URL:
        try:
            await ptb_application.bot.set_webhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)
            logger.info(f"Webhook set successfully to {WEBHOOK_URL}.")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}", exc_info=True)
            # Depending on severity, you might want to raise an error here
            # to prevent the app from starting if webhook setup is critical.
    else:
        logger.warning("WEBHOOK_URL not set. Skipping webhook setup. Bot will not receive updates via webhook.")

async def run_ptb_shutdown_tasks():
    """Shuts down the PTB application."""
    logger.info("Running PTB shutdown tasks.")
    await ptb_application.shutdown()
    logger.info("Telegram Application shut down.")

# --- ASGI Wrapper Application ---
class ASGIAppWithLifespan:
    def __init__(self, flask_wsgi_app):
        self.flask_asgi_app = WsgiToAsgi(flask_wsgi_app)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    try:
                        await run_ptb_startup_tasks()
                        await send({'type': 'lifespan.startup.complete'})
                    except Exception as e:
                        logger.error(f"Error during PTB startup tasks: {e}", exc_info=True)
                        await send({'type': 'lifespan.startup.failed', 'message': str(e)})
                elif message['type'] == 'lifespan.shutdown':
                    try:
                        await run_ptb_shutdown_tasks()
                        await send({'type': 'lifespan.shutdown.complete'})
                    except Exception as e:
                        logger.error(f"Error during PTB shutdown tasks: {e}", exc_info=True)
                        await send({'type': 'lifespan.shutdown.failed', 'message': str(e)})
                    return # Important to return after shutdown
        elif scope['type'] == 'http':
            await self.flask_asgi_app(scope, receive, send)
        # You could add other scope types like 'websocket' if needed

# This 'application' is the ASGI app that Hypercorn should run.
# Your Hypercorn command should be: hypercorn main:application --bind 0.0.0.0:${PORT}
application = ASGIAppWithLifespan(_actual_flask_app)


if __name__ == "__main__":
    logger.info(
        "Bot script executed. Hypercorn should manage the ASGI 'application' object and its lifecycle."
    )
    # This script is designed to be run by an ASGI server like Hypercorn.
    # For local testing without Hypercorn (e.g., with polling if WEBHOOK_URL is not set),
    # you would need a different execution block here, potentially involving asyncio.run()
    # and ptb_application.run_polling(). However, that would bypass the Flask/webhook setup.
    # Example for polling (mutually exclusive with webhook setup):
    # async def main_polling():
    #     await ptb_application.initialize()
    #     # await ptb_application.bot.delete_webhook() # If switching from webhook to polling
    #     logger.info("Starting bot in polling mode...")
    #     await ptb_application.run_polling(allowed_updates=Update.ALL_TYPES)

    # if not WEBHOOK_URL and TOKEN:
    #     logger.info("WEBHOOK_URL not found, attempting to run in polling mode for local testing.")
    #     asyncio.run(main_polling())
    # else:
    #     logger.info("WEBHOOK_URL is set or TOKEN is missing. Polling mode not started.")
    pass
