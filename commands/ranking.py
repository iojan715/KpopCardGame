import discord, random, string
from datetime import timezone, datetime
from discord.ext import commands
from discord import app_commands
from utils.language import get_user_language
from utils.localization import get_translation
from db.connection import get_pool
from commands.starter import version



class RankingGroup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ranking", description="Muestra diferentes rankings del juego.")
    async def ranking(self, interaction: discord.Interaction):
        pool = get_pool()
        embed = await get_ranking_embed(pool, "level")  # default
        view = RankingView(self.bot, pool, interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)



class RankingView(discord.ui.View):
    def __init__(self, bot, pool, interaction):
        super().__init__(timeout=60)  # la view expira en 1 minuto
        self.bot = bot
        self.pool = pool
        self.interaction = interaction

        # Dropdown de selección de ranking
        self.add_item(RankingSelect(bot, pool, interaction))


class RankingSelect(discord.ui.Select):
    def __init__(self, bot, pool, interaction):
        self.bot = bot
        self.pool = pool
        self.interaction = interaction

        options = [
            discord.SelectOption(label="Nivel", value="level", description="Ranking por nivel y XP"),
            discord.SelectOption(label="Créditos", value="credits", description="Ranking por dinero"),
            discord.SelectOption(label="Influencia", value="influence", description="Ranking por influencia total"),
            discord.SelectOption(label="Cartas", value="cards", description="Ranking por cantidad de cartas"),
            discord.SelectOption(label="Grupos", value="groups", description="Ranking por popularidad de grupos"),
        ]

        super().__init__(placeholder="Selecciona un ranking...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        embed = await get_ranking_embed(self.pool, value)
        await interaction.response.edit_message(embed=embed, view=self.view)


async def get_ranking_embed(pool, ranking_type: str):
    async with pool.acquire() as conn:
        if ranking_type == "credits":
            rows = await conn.fetch("""
                SELECT user_id, agency_name, credits 
                FROM users 
                ORDER BY credits DESC 
                LIMIT 10
            """)
            title = "🏦 Ranking de Créditos"
            field = "Créditos"

        elif ranking_type == "level":
            rows = await conn.fetch("""
                SELECT user_id, agency_name, level, xp 
                FROM users 
                ORDER BY level DESC, xp DESC 
                LIMIT 10
            """)
            title = "🎓 Ranking de Nivel"
            field = "Nivel (XP)"

        elif ranking_type == "cards":
            rows = await conn.fetch("""
                SELECT u.user_id, u.agency_name, COUNT(c.unique_id) as total
                FROM users u
                LEFT JOIN user_idol_cards c ON u.user_id = c.user_id
                GROUP BY u.user_id, u.agency_name
                ORDER BY total DESC
                LIMIT 10
            """)
            title = "🃏 Ranking de Cartas"
            field = "Cartas"

        elif ranking_type == "influence":
            rows = await conn.fetch("""
                SELECT u.user_id, u.agency_name, 
                       COALESCE(SUM(g.popularity + g.permanent_popularity),0) as total
                FROM users u
                LEFT JOIN groups g ON u.user_id = g.user_id
                GROUP BY u.user_id, u.agency_name
                ORDER BY total DESC
                LIMIT 10
            """)
            title = "🌟 Ranking de Influencia"
            field = "Influencia"

        elif ranking_type == "groups":
            rows = await conn.fetch("""
                SELECT g.group_id, g.name, g.user_id, (g.popularity + g.permanent_popularity) as total
                FROM groups g
                ORDER BY total DESC
                LIMIT 10
            """)
            title = "👥 Ranking de Grupos"
            field = "Popularidad Total"

    # Crear el embed
    embed = discord.Embed(title=title, color=discord.Color.gold())
    if rows:
        for i, row in enumerate(rows, start=1):
            if i == 1:
                rank_symbol = "🥇"
            elif i == 2:
                rank_symbol = "🥈"
            elif i == 3:
                rank_symbol = "🥉"
            else:
                rank_symbol = f"#{i}"
                
            if ranking_type == "level":
                value = f"{row['level']} ({row['xp']} XP)"
                mention = f"<@{row['user_id']}>"
                name = row["agency_name"]

            elif ranking_type == "groups":
                value = f"{row['total']} {field}"
                mention = f"<@{row['user_id']}>"
                name = row["name"]

            elif ranking_type == "credits":
                value = f"💵 {format(int(row['credits']),',')}"
                mention = f"<@{row['user_id']}>"
                name = row["agency_name"]
            
            else:
                value = f"{row['total'] if 'total' in row else row.get(field.lower(), 0)} {field}"
                mention = f"<@{row['user_id']}>"
                name = row["agency_name"]

            embed.add_field(
                name=f"{rank_symbol} {name}",
                value=f"{mention} — {value}",
                inline=False
            )
    else:
        embed.description = "No hay datos disponibles aún."

    return embed



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RankingGroup(bot))