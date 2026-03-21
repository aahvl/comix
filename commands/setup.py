import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os

from backend.supabase_client import wallet_exists, create_wallet
from backend.crypto import generate_wallet
from backend.security import hash_pin, decrypt

TIMEOUT = 120
PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 6
BRAND_COLOR = 0x5865F2
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
WARN_COLOR = 0xFEE75C
INFO_COLOR = 0x00B0F4
NEUTRAL_COLOR = 0x2C2F33


def _embed_welcome() -> discord.Embed:
    e = discord.Embed(
        title="👋 Welcome to Comix!",
        description=(
            "# Secure Discord Crypto Wallet\n\n"
            "Let's set up your Litecoin & Solana wallets in just a few steps.\n\n"
            "**📋 What You'll Do:**\n"
            "+ ✅ Generate your crypto wallets\n"
            "+ ✅ Backup your 12-word recovery phrase\n"
            "+ ✅ Set a PIN to secure your account\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Everything stays encrypted & private.**\n\n"
            "**Ready to begin?** Type `confirm`\n"
            "**Or skip?** Type `cancel`"
        ),
        color=BRAND_COLOR,
    )
    e.set_footer(text="⏱️ You have 2 minutes to respond • 🔒 All data is encrypted")
    return e


def _embed_seed(seed_phrase: str) -> discord.Embed:
    words = seed_phrase.split()
    # Display words clearly in a numbered list
    numbered = "\n".join(f"**{i+1:2d}.** `{word}`" for i, word in enumerate(words))

    e = discord.Embed(
        title="🔐 Your Seed Phrase",
        description=(
            f"```\n{numbered}\n```\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**⚠️ CRITICAL - KEEP THIS SAFE:**\n\n"
            "- **NEVER share** these words with anyone\n"
            "- **NEVER type** them on websites\n"
            "- **ANYONE** with these 12 words owns your entire wallet\n\n"
            "✅ **WHAT YOU MUST DO:**\n"
            "- Write them down on paper (keep offline)\n"
            "- Store in a safe place (vault, safe, etc.)\n"
            "- We will NEVER ask you for this again\n\n"
            "**Type `confirm` once you've secured it**"
        ),
        color=WARN_COLOR,
    )
    e.set_footer(text="🔒 This is your ONLY backup. Screenshot it if you need to, but keep it secure!")
    return e


def _embed_pin_prompt() -> discord.Embed:
    e = discord.Embed(
        title="🔐 Create Your PIN",
        description=(
            f"# Choose a {PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} Digit PIN\n\n"
            "Your PIN protects sensitive actions like transfers and withdrawals.\n\n"
            "**🔒 Security Tips:**\n"
            "+ Use random numbers (not your birthday)\n"
            "+ Never share it with anyone\n"
            "+ We never see or store your PIN\n"
            "+ Only you can unlock your wallet\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Type your PIN now:** (numbers only)"
        ),
        color=INFO_COLOR,
    )
    e.set_footer(text="🤐 Your PIN is hashed with bcrypt for maximum security")
    return e


def _embed_pin_confirm() -> discord.Embed:
    e = discord.Embed(
        title="🔐 Confirm Your PIN",
        description=(
            "# Enter Your PIN Again\n\n"
            "Make sure you type the exact same PIN you just created.\n\n"
            "**Type your PIN to confirm:**"
        ),
        color=INFO_COLOR,
    )
    e.set_footer(text="✅ Double-checking to ensure you remember it correctly")
    return e


def _embed_success(ltc_address: str, sol_address: str) -> discord.Embed:
    e = discord.Embed(
        title="✅ Wallet Successfully Created!",
        description=(
            "# 🎉 Welcome to Comix!\n\n"
            "Your crypto wallets are now ready to use.\n\n"
            "**🪙 Litecoin Address:**\n"
            f"`{ltc_address}`\n\n"
            "**◎ Solana Address:**\n"
            f"`{sol_address}`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**✅ Setup Complete:**\n"
            "+ Wallets generated & encrypted\n"
            "+ Seed phrase backed up (offline)\n"
            "+ PIN protection activated\n\n"
            "**📱 Next Steps:**\n"
            "Use `/wallet` to check your balance\n"
            "Use `/send` to transfer crypto\n"
            "Use `/receive` to get your addresses"
        ),
        color=SUCCESS_COLOR,
    )
    e.set_thumbnail(url="https://cdn.discordapp.com/emojis/1076925839850512464.png")
    e.set_footer(text="🔐 Your funds are encrypted and only you can access them. Never share your seed phrase!")
    return e


def _embed_error(msg: str) -> discord.Embed:
    e = discord.Embed(
        title="❌ Setup Failed",
        description=(
            f"# Oops! Something went wrong\n\n"
            f"**Error:** {msg}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Try Again:**\n"
            "No changes were made. Just restart with `/setup`"
        ),
        color=ERROR_COLOR,
    )
    e.set_footer(text="💡 If this keeps happening, check our support docs")
    return e


def _embed_cancelled() -> discord.Embed:
    e = discord.Embed(
        title="❌ Setup Cancelled",
        description=(
            "# Setup Cancelled\n\n"
            "No problem! No changes were made to your account.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Want to try again?**\n"
            "Just type `/setup` whenever you're ready!"
        ),
        color=NEUTRAL_COLOR,
    )
    e.set_footer(text="💙 We'll be here whenever you need us!")
    return e


def _embed_timeout() -> discord.Embed:
    e = discord.Embed(
        title="⏰ Setup Timed Out",
        description=(
            "# Time's Up!\n\n"
            "You didn't respond in 2 minutes, so we cancelled the setup.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**No worries!**\n"
            "Start over with `/setup` and take your time."
        ),
        color=ERROR_COLOR,
    )
    e.set_footer(text="⏱️ Next time you have a bit more time to respond!")
    return e


def _embed_already_exists() -> discord.Embed:
    e = discord.Embed(
        title="✅ Wallet Already Exists",
        description=(
            "You already have a Comix wallet. No need to create another one.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Your Options:\n"
            "+ Use /dashboard to check your balance, send, receive, and use settings"
        ),
        color=SUCCESS_COLOR,
    )
    e.set_footer(text="💙 Your wallet is secure and ready to use!")
    return e


async def _run_setup_in_dm(bot: commands.Bot, user: discord.User) -> None:
    dm = user.dm_channel or await user.create_dm()

    print(f"[SETUP] Checking if wallet exists for user {user.id}...")
    try:
        exists = await wallet_exists(str(user.id))
        if exists:
            print(f"[SETUP] ℹ️ User {user.id} already has a wallet")
            await dm.send(embed=_embed_already_exists())
            return
    except Exception as e:
        print(f"[SETUP] ⚠️ Failed to check wallet existence: {e}")

    def check(m: discord.Message) -> bool:
        """Validate message is from user in this DM."""
        return m.author.id == user.id and m.channel.id == dm.id

    await dm.send(embed=_embed_welcome())

    try:
        msg = await bot.wait_for('message', check=check, timeout=TIMEOUT)
    except asyncio.TimeoutError:
        await dm.send(embed=_embed_timeout())
        return

    if msg.content.strip().lower() != 'confirm':
        await dm.send(embed=_embed_cancelled())
        return

    gen_msg = await dm.send(embed=discord.Embed(
        title="⚙️ Generating Wallets",
        description="🚀 Creating your Litecoin & Solana wallets...\n\nThis takes about 5-10 seconds.",
        color=INFO_COLOR,
    ))

    try:
        wallet_data = await asyncio.to_thread(generate_wallet)
    except Exception as e:
        await dm.send(embed=_embed_error(f'Failed to generate wallet: {e}'))
        return

    plain_seed = decrypt(wallet_data['seed_phrase'])


    seed_msg = await dm.send(embed=_embed_seed(plain_seed))
    
    async def delete_seed_later():
        await asyncio.sleep(300)
        try:
            await seed_msg.delete()
            print(f"[SETUP] 🗑️ Auto-deleted seed phrase for user {user.id}")
        except Exception as e:
            print(f"[SETUP] ⚠️ Failed to delete seed message: {e}")
    
    asyncio.create_task(delete_seed_later())

    try:
        msg = await bot.wait_for('message', check=check, timeout=TIMEOUT)
    except asyncio.TimeoutError:
        await dm.send(embed=_embed_timeout())
        return

    if msg.content.strip().lower() != 'confirm':
        await dm.send(embed=_embed_cancelled())
        return

    await dm.send(embed=_embed_pin_prompt())

    try:
        msg = await bot.wait_for('message', check=check, timeout=TIMEOUT)
    except asyncio.TimeoutError:
        await dm.send(embed=_embed_timeout())
        return

    pin_input = msg.content.strip()

    if not pin_input.isdigit():
        await dm.send(embed=_embed_error('PIN must be numeric. Please start setup again.'))
        return

    if not (PIN_MIN_LENGTH <= len(pin_input) <= PIN_MAX_LENGTH):
        await dm.send(embed=_embed_error(f'PIN must be {PIN_MIN_LENGTH}–{PIN_MAX_LENGTH} digits.'))
        return

    await dm.send(embed=_embed_pin_confirm())

    try:
        msg = await bot.wait_for('message', check=check, timeout=TIMEOUT)
    except asyncio.TimeoutError:
        await dm.send(embed=_embed_timeout())
        return

    if msg.content.strip() != pin_input:
        await dm.send(embed=_embed_error('PINs do not match. Please start setup again.'))
        return

    try:
        await create_wallet(
            user_id=str(user.id),
            username=str(user),
            pin_hash=hash_pin(pin_input),
            seed_phrase=wallet_data['seed_phrase'],
            ltc_address=wallet_data['ltc_address'],
            ltc_private_key=wallet_data['ltc_private_key'],
            sol_address=wallet_data['sol_address'],
            sol_private_key=wallet_data['sol_private_key'],
        )
        print(f"[SETUP] ✅ Wallet saved for user {user.id}")
    except Exception as e:
        print(f"[SETUP] ❌ Failed to save wallet: {str(e)}")
        await dm.send(embed=_embed_error(f'Database error: {str(e)}'))
        return

    await dm.send(embed=_embed_success(
        ltc_address=wallet_data['ltc_address'],
        sol_address=wallet_data['sol_address'],
    ))


class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name='setup',
        description='Create your Comix Wallet, first time setup.'
    )
    async def setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await _run_setup_in_dm(self.bot, interaction.user)


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
