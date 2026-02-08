import os
import discord
from discord.ext import commands
import logging

if os.getenv("ENABLE_UPDATE") != "true":
    logging.info("更新は無効化されています")
    return

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logging.info("Bot starting...")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.close()  # Actions用：起動確認したら終了

bot.run(TOKEN)
