import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from backend.supabase_client import test_connection

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN environment variable is not set. Set it in .env or Environment variables.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

EXTENSIONS = [
    "commands.setup",
    "commands.dashboard",
]

@bot.event
async def on_ready():
    print(f"[OK] Logged in as {bot.user} (ID: {bot.user.id})")
    
    print("[STARTUP] Testing Supabase connection...")
    try:
        is_connected = await test_connection()
        if is_connected:
            print("[STARTUP] [OK] Supabase connection verified")
        else:
            print("[STARTUP] [WARN] Supabase connection test failed")
    except Exception as e:
        print(f"[STARTUP] [ERROR] Supabase connection error: {e}")
    
    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] Synced {len(synced)} commands")
    except Exception as e:
        print(f"[ERROR] Failed to sync commands: {e}")

async def main():
    async with bot:
        for ext in EXTENSIONS:
            try:
                await bot.load_extension(ext)
                print(f"[OK] Loaded extension: {ext}")
            except Exception as e:
                print(f"[ERROR] Failed to load extension {ext}: {e}")
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())