import discord, random, string, asyncio
from discord.ext import commands
from discord import app_commands
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from datetime import datetime
import uuid

class TradeGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="trade", description="Comandos para el sistema de intercambio")

    @app_commands.command(name="propose", description="Proponer un intercambio a otro jugador")
    @app_commands.describe(
        user="Jugador al que quieres proponerle el intercambio",
        offer_cards="IDs de tus cartas ofrecidas, separadas por coma (ej. IDL001,ACC002)",
        request_cards="IDs de las cartas que quieres, separadas por coma",
        offer_credits="Cantidad de créditos que ofreces (opcional)",
        request_credits="Cantidad de créditos que estás pidiendo (opcional)",
        message="Mensaje opcional para el otro jugador"
    )
    async def propose(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        offer_cards: str=None,
        request_cards: str=None,
        offer_credits: int = 0,
        request_credits: int = 0,
        message: str = ""
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        language = await get_user_language(interaction.user.id)
        
        if not offer_cards and not request_cards and not offer_credits and not request_credits:
            return await interaction.response.send_message("Debes ingresar algo para ofrecer o pedir para iniciar un trade.", ephemeral=True)


        if user.id == interaction.user.id:
            return await interaction.response.send_message(get_translation(language,"trade.error_self_trade"), ephemeral=True)

        
        def extract_unique_ids(raw_input: str) -> list[str]:
            if not raw_input:
                return []
            parts = [x.strip() for x in raw_input.replace(" ", "").split(",") if "." in x]
            return [x.split(".")[1] for x in parts]

        offered = extract_unique_ids(offer_cards)
        requested = extract_unique_ids(request_cards)

        pool = get_pool()
        async with pool.acquire() as conn:
            # Verificar que el usuario tenga las cartas que ofrece (idol o item)
            idol_rows = await conn.fetch("""
                SELECT unique_id FROM user_idol_cards
                WHERE user_id = $1 AND unique_id = ANY($2::TEXT[])
                AND status = 'available' AND is_locked = false
            """, interaction.user.id, offered)

            item_rows = await conn.fetch("""
                SELECT unique_id FROM user_item_cards
                WHERE user_id = $1 AND unique_id = ANY($2::TEXT[])
                AND status = 'available'
            """, interaction.user.id, offered)

            owned_ids = {r["unique_id"] for r in idol_rows + item_rows}
            missing = set(offered) - owned_ids

            if missing:
                return await interaction.response.send_message(
                    get_translation(language, "trade.error_missing_cards") + "\n" +
                    "\n".join(f"- `{card}`" for card in missing),
                    ephemeral=True
                )

            # Verificar créditos disponibles
            if offer_credits > 0:
                row = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", interaction.user.id)
                if not row or row["credits"] < offer_credits:
                    return await interaction.response.send_message(
                        get_translation(language, "trade.error_insufficient_credits"),
                        ephemeral=True
                    )

            
                
        view = discord.ui.View()
        view.add_item(ConfirmTradeProposeButton(to_user=user, offered=offered, requested=requested,
                                                offer_credits=offer_credits, request_credits=request_credits))
        
        embed = discord.Embed(
            title="",
            description="",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(
            "¿Confirmas el envío de esta propuesta de intercambio?",
            view=view,
            ephemeral=True
        )
            
            





# --- /trade propose
class ConfirmTradeProposeButton(discord.ui.Button):
    def __init__(self, to_user: discord.User, offered, requested, offer_credits, request_credits):
        super().__init__(label="Confirmar", emoji="✅", style=discord.ButtonStyle.primary)
        self.to_user = to_user
        self.offered = offered
        self.requested = requested
        self.offer_credits = offer_credits
        self.request_credits = request_credits

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        

        async with pool.acquire() as conn:
            while True:
                # Crear trade_id único
                trade_id = ''.join(random.choices(string.digits, k=5))
                exists_trade = await conn.fetchval("SELECT 1 FROM trades WHERE trade_id = $1", trade_id)
                if not exists_trade:
                    break
            
            # Insertar propuesta
            await conn.execute("""
                INSERT INTO trades (
                    trade_id, from_user, to_user,
                    offer_cards, request_cards,
                    offer_credits, request_credits
                ) VALUES (
                    $1, $2, $3,
                    $4, $5,
                    $6, $7
                )
            """, trade_id, interaction.user.id, self.to_user.id,
                    self.offered, self.requested, self.offer_credits, self.request_credits)
            print(self.to_user.mention)
        
            dm_row = await conn.fetchrow(
                "SELECT notifications FROM users WHERE user_id = $1",
                self.to_user.id
            )
            if dm_row and dm_row["notifications"]:
                try:
                    dm_channel = await self.to_user.create_dm()
                    await dm_channel.send(embed=discord.Embed(
                        title=f"📩 ¡Has recibido una nueva propuesta de intercambio de parte de **{interaction.user.display_name}**!\n",
                        description=f"Usa el comando `/trade list` para revisarla.\n\n🆔 ID del intercambio: `{trade_id}`")
                    )
                except discord.Forbidden:
                    # El usuario tiene los MD desactivados o bloqueó al bot
                    pass
        
        await interaction.response.edit_message(
            content=f"✅ Propuesta enviada a {self.to_user.mention} con ID `{trade_id}`",
            view=None
        )




async def setup(bot):
    bot.tree.add_command(TradeGroup())