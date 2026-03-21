import discord
from backend.supabase_client import wallet_exists

async def ensure_wallet(interaction: discord.Interaction) -> bool:
    """
    Call this at the top of every command.
    If the user has no wallet, redirect them to /setup and return False.
    The calling command should immediately return if this returns False.
    """
    if not await wallet_exists(str(interaction.user.id)):
        embed = discord.Embed(
            title="👋 Welcome to Comix Wallet",
            description=(
                "Looks like you don't have a wallet yet.\n\n"
                "Run **/setup** to create your wallet and get started — "
                "it only takes a minute."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Don't worry, it's free to create a wallet and you can delete it anytime.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return True
