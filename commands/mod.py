import discord, random, string
from datetime import timezone, datetime
from discord.ext import commands
from discord import app_commands
from utils.language import get_user_language
from utils.localization import get_translation
from db.connection import get_pool

class ModGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="mod", description="Comandos para moderación")

    @app_commands.command(name="bug_reward", description="Entregar recompensa a un jugador por reporte de error")
    @app_commands.describe(
        user="Jugador que reportó el error",
        level="Nivel del error",
        tier="Grado del impacto dentro del nivel (1-3)",
        message ="Descripcion del error resuelto"
    )
    @app_commands.choices(
        level=[
            app_commands.Choice(name="🟢 Menor", value="minor"),
            app_commands.Choice(name="🟡 Moderado", value="moderate"),
            app_commands.Choice(name="🔴 Importante", value="important"),
            app_commands.Choice(name="🔥 Crítico", value="critical"),
        ],
        tier=[
            app_commands.Choice(name="Tier 1", value=1),
            app_commands.Choice(name="Tier 2", value=2),
            app_commands.Choice(name="Tier 3", value=3),
        ]
    )
    async def bug_reward(self, interaction: discord.Interaction, user: discord.User, level: app_commands.Choice[str], tier: app_commands.Choice[int], message:str):
        language = await get_user_language(interaction.user.id)

        # Créditos base por nivel
        base_credits = {
            "minor": 1000,
            "moderate": 3000,
            "important": 6000,
            "critical": 10000
        }
        
        credit_mult = {
            "minor": 1,
            "moderate": 2,
            "important": 3,
            "critical": 5
        }
        
        packs = {
            "minor": "GFT",
            "moderate": "SPP",
            "important": "HLV",
            "critical": "STR"
        }
        packs_names = {
            "minor": "Gift Pack",
            "moderate": "Support Pack",
            "important": "High Level Pack",
            "critical": "Star Pack"
        }
        
        redeemables = {
            "minor": "DISCN",
            "moderate": "RECRT",
            "important": "TCONT",
            "critical": "CONTR"
        }
        redeemables_names = {
            "minor": "Discount",
            "moderate": "Recruitment",
            "important": "Tactical Contract",
            "critical": "Contract"
        }

        # Bonus por tier
        tier_bonus = {
            1: 0,
            2: 1000,
            3: 2000
        }
        pack_id = packs[level.value]
        reward_credits = base_credits[level.value] + tier_bonus[tier.value] * credit_mult[level.value]

        redeemable_id = redeemables[level.value]
        
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                reward_credits, user.id
            )
            
            while True:
                new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                exists = await conn.fetchval("SELECT 1 FROM players_packs WHERE unique_id = $1", new_id)
                if not exists:
                    break
            now = datetime.now(timezone.utc)
            await conn.execute(
                """
                INSERT INTO players_packs (pack_id, unique_id, user_id, buy_date)
                VALUES ($1, $2, $3, $4)""",
                pack_id, new_id, user.id, now 
            )
            
            await conn.execute("""
                INSERT INTO user_redeemables (user_id, redeemable_id, quantity)
                VALUES ($1, $2, 1)
                ON CONFLICT (user_id, redeemable_id)
                DO UPDATE SET quantity = user_redeemables.quantity + 1
            """, user.id, redeemable_id)
            
            

        embed = discord.Embed(
            title="🎁 Recompensa por reporte de error",
            description=f"",
            color=discord.Color.orange()
        )
        embed.add_field(name="💵 Dinero otorgado", value=f"{reward_credits:,}", inline=False)
        embed.add_field(name="📦 Pack entregado", value=packs_names[level.value], inline=True)
        embed.add_field(name="🎫 Cupón recibido", value=redeemables_names[level.value], inline=True)
        embed.set_footer(text="¡Tu ayuda mejora el juego para todos!")

        await interaction.response.send_message(
            content=f"## Gracias a {user.mention} por reportar un error de nivel **{level.name}**:\n**Arreglado:** _{message}_",
            embed=embed, ephemeral=False)
        
        




async def setup(bot):
    bot.tree.add_command(ModGroup())