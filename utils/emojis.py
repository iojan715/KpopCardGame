import discord

def get_emoji(guild: discord.Guild, emoji_name: str) -> str:

    emoji = discord.utils.get(guild.emojis, name=emoji_name)
    return str(emoji) if emoji else "❔"