import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
from model import get_top_predictions
from scheduler import can_predict_today, register_prediction
from loguru import logger

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚽ Welcome to the Football Prediction Bot!")
Use /predict to get today’s top predictions.")

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_predict_today():
        await update.message.reply_text("⚠️ Daily prediction limit reached. Try again tomorrow.")
        return

    predictions = get_top_predictions()
    register_prediction()
    msg = "\n".join([f"✅ {i+1}. {p['label']} (Confidence: {p['confidence']}%)" for i, p in enumerate(predictions)])
    await update.message.reply_text(f"🔝 Today's Top Football Predictions:\n{msg}")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("predict", predict))

if __name__ == "__main__":
    logger.info("Starting bot...")
    app.run_polling()
