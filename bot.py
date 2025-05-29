import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    # Added ConversationHandler and MessageHandler for future improvements
    # and better bot flow, though not immediately used in current fixes.
    # Also added Filters for message handling.
    # Filters are in telegram.ext.filters, not directly in telegram.ext
    # So, will add it later when introducing it for improvements.
)
from dotenv import load_dotenv
from model import get_top_predictions
from scheduler import can_predict_today, register_prediction
from loguru import logger

# Load env vars
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    # Changed ValueError to a more specific error for clarity and easier debugging.
    # Also, added a logger.error to ensure this critical issue is logged.
    logger.error("TELEGRAM_BOT_TOKEN is not set in environment variables. Bot cannot start.")
    raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set in environment variables.")

# Define league names (for user-friendly responses)
LEAGUE_NAMES = {
    "premier": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    # Added "all" for a potential "show all predictions" button later.
    "all": "All Leagues"
}

# Safe logger - Renamed for clarity, now handles different update types gracefully.
async def log_user_activity(update: Update):
    """Logs incoming requests from users."""
    user = update.effective_user
    chat = update.effective_chat
    # Defensive programming: ensure user and chat exist.
    if not user or not chat:
        logger.warning("Received an update without an effective user or chat.")
        return

    user_info = f"@{user.username}" if user.username else f"User ID: {user.id}"
    chat_info = f"Chat ID: {chat.id}"

    msg_text = "No message text" # Default value

    if update.message:
        msg_text = update.message.text
    elif update.callback_query:
        msg_text = update.callback_query.data
    elif update.edited_message: # Log edited messages as well
        msg_text = update.edited_message.text
    elif update.channel_post: # Log channel posts if the bot is in a channel
        msg_text = update.channel_post.text
    elif update.edited_channel_post: # Log edited channel posts
        msg_text = update.edited_channel_post.text
    # Add more conditions for other update types if relevant (e.g., photos, documents)

    logger.info(f"[{chat_info}] {user_info}: {msg_text}")


# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, welcoming the user."""
    await log_user_activity(update)
    # Using markdown_v2 for richer formatting and better control over escaped characters.
    # Added more descriptive welcome message.
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
    # Using MarkdownV2 for consistency and better formatting.
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /predict command, showing daily football predictions."""
    await log_user_activity(update)

    # Consider per-user prediction limits if this is a premium feature,
    # otherwise, a global limit might be too restrictive.
    # For now, sticking to the original logic, but this is an area for improvement.
    if not can_predict_today():
        # Changed message to be more user-friendly and informative.
        await update.message.reply_text("⚠️ *Daily Prediction Limit Reached!* ⚠️\n\n"
                                        "To ensure fair usage and optimal performance, I can only provide "
                                        "predictions once per day globally\\. Please try again tomorrow\\! "
                                        "Thank you for your understanding\\.",
                                        parse_mode="MarkdownV2")
        return

    predictions = get_top_predictions()
    register_prediction() # Register the prediction *after* fetching it successfully.

    if not predictions:
        # Handle cases where no predictions are available.
        await update.message.reply_text("🗓️ *No predictions available for today yet\\!* 🗓️\n\n"
                                        "Please check back later or tomorrow\\.",
                                        parse_mode="MarkdownV2")
        return

    # Improved message formatting for predictions. Using code block for predictions for clarity.
    msg_parts = ["⚽ *Today's Top Football Predictions:* ⚽\n\n```"]
    for i, p in enumerate(predictions):
        # Ensure 'label' and 'confidence' keys exist to prevent KeyError.
        label = p.get('label', 'N/A')
        confidence = p.get('confidence', 'N/A')
        msg_parts.append(f"{i+1}. {label} (Confidence: {confidence}%)")
    msg_parts.append("```\n\n")

    # Added a "Show All" button, assuming `get_top_predictions` can be filtered later.
    # This also helps to demonstrate a more complete keyboard.
    keyboard = [
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="premier")],
        [InlineKeyboardButton("🇪🇸 La Liga", callback_data="laliga")],
        [InlineKeyboardButton("🇮🇹 Serie A", callback_data="seriea")],
        [InlineKeyboardButton("✨ Show All Predictions", callback_data="all")], # New button
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Joining the message parts.
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
    await query.answer() # Always answer the callback query to remove the loading animation.

    league_code = query.data
    league_name = LEAGUE_NAMES.get(league_code, "Unknown League")

    # This is a placeholder. In a real bot, you'd fetch predictions *specifically* for that league.
    # For now, just a friendly message.
    if league_code == "all":
        response_text = "✨ *Showing All Available Predictions!* ✨\n" \
                        "This feature is under development\\. For now, the initial prediction message " \
                        "already displays the top predictions across all leagues\\."
    else:
        response_text = f"📊 *Predictions for {league_name} coming soon\\!* 📊\n" \
                        "This feature is currently under development\\. Please check back later for " \
                        "league-specific predictions\\."

    # Using edit_message_text to update the original message, which is a better UX.
    # Ensure parse_mode is set.
    await query.edit_message_text(
        response_text,
        parse_mode="MarkdownV2"
    )

# Handle all unexpected errors gracefully
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs errors and sends a user-friendly message."""
    logger.error(msg="Exception while handling update:", exc_info=context.error)

    # Check if update is an instance of Update and has a message attribute before trying to reply.
    if isinstance(update, Update) and update.effective_message:
        try:
            # Provide a more specific error message based on the user's last action, if possible.
            await update.effective_message.reply_text(
                "🚨 *Oops! Something went wrong\\.* 🚨\n"
                "I've logged the error and our team will look into it\\. Please try again later\\.",
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
    else:
        logger.warning("Error occurred, but couldn't send message back to user due to missing update.message.")


# Build and start bot
app = ApplicationBuilder().token(TOKEN).build()

# Register handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("predict", predict))
app.add_handler(CallbackQueryHandler(handle_button))
app.add_error_handler(error_handler)

if __name__ == "__main__":
    logger.info("Starting Football Prediction Bot...")
    app.run_polling()
