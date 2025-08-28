import discord, random, string
from datetime import timezone, datetime
from discord.ext import commands
from discord import app_commands
from utils.language import get_user_language
from utils.localization import get_translation
from db.connection import get_pool


class BankGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="bank", description="Comandos para transacciones monetarias")

    @app_commands.command(name="send_credits", description="Enviar creditos a otra agencia")
    @app_commands.describe(
        agency="Jugador que reportó el error",
        amount="Cantidad de créditos a enviar"
    )
    async def send_credits(self, interaction: discord.Interaction, agency:str, amount: int):
        await interaction.response.defer(
            ephemeral=True
        )
        remit_id = interaction.user.id
        pool = get_pool()
        language = await get_user_language(remit_id)
        
        async with pool.acquire() as conn:
            dest_id = await conn.fetchval("SELECT user_id FROM users WHERE agency_name = $1", agency)
            dest_agency = agency
            remit_agency = await conn.fetchval("SELECT agency_name FROM users WHERE user_id = $1", remit_id)
            remit_credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", remit_id)

        if dest_id == remit_id:
            return await interaction.edit_original_response(content="## ❌ No puedes enviarte dinero a ti.")
        
        embed = discord.Embed(
            title=f"¿Seguro que deseas enviar 💵{format(amount,',')} a `{dest_agency}`?",
            description=f"CEO: <@{dest_id}>",
            color=discord.Color.dark_gold()
        )
        fame = int(amount*0.05)
        if fame < 50:
            fame = 50
        embed.add_field(name=f"FAME (5%): 💵`{format(fame,',')}`", value=f"_Fee for Artistic Monetary Exchange_")
        
        embed.set_footer(text=f"Total a pagar: 💵{format(int(amount+fame),',')}")
        
        disabled = False
        if amount*1.05 > remit_credits:
            disabled = True
        
        view = discord.ui.View()
        view.add_item(ConfirmSendCreditsButton(
            remit_id=remit_id,
            dest_id=dest_id,
            amount=amount,
            disabled=disabled
        ))
        
        await interaction.edit_original_response(content="", embed=embed, view=view)
    
    @send_credits.autocomplete("agency")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users ORDER BY register_date DESC")
        return [
            app_commands.Choice(name=f"{row['agency_name']}", value=row['agency_name'])
            for row in rows if current.lower() in f"{row['agency_name'].lower()}"
        ][:25]

# --- send_credits
class ConfirmSendCreditsButton(discord.ui.Button):
    def __init__(
        self,
        remit_id,
        dest_id,
        amount: int,
        disabled
    ):
        super().__init__(
            label="✅",
            style=discord.ButtonStyle.primary,
            disabled=disabled)
        
        self.remit_id = remit_id
        self.dest_id = dest_id
        self.amount = amount
        
    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            dest_agency = await conn.fetchval("SELECT agency_name FROM users WHERE user_id = $1", self.dest_id)
            remit_agency = await conn.fetchval("SELECT agency_name FROM users WHERE user_id = $1", self.remit_id)
            remit_credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", self.remit_id)

            fame = self.amount*0.05
            if fame < 50:
                fame = 50
            
            if self.amount+fame > remit_credits:
                return await interaction.response.edit_message(content="## ❌ No tienes suficientes créditos para enviar",
                                                               embed=None, view=None)
            
            amount_to_pay = self.amount + fame
            
            xp = fame // 100
            
            await conn.execute(
                "UPDATE users SET credits = credits + $1 WHERE user_id = $2", self.amount, self.dest_id)
            await conn.execute(
                "UPDATE users SET credits = credits - $1 WHERE user_id = $2", amount_to_pay, self.remit_id)
            
            xp_gave = ""
            if xp > 0:
                await conn.execute(
                    "UPDATE users SET xp = xp + $1 WHERE user_id = $2",
                    xp, self.remit_id)
                xp_gave = f"\n> XP: `+{int(xp)}`"
            
            dest_notif = await conn.fetchval("SELECT notifications FROM users WHERE user_id = $1", self.dest_id)
            
            if dest_notif:
                dest_user = await interaction.client.fetch_user(self.dest_id)
                try:
                    dm_channel = await dest_user.create_dm()
                    await dm_channel.send(f"## 💵 La agencia `{remit_agency}` te ha enviado 💵`{format(self.amount,',')}`\n> CEO: <@{self.remit_id}>")
                except discord.Forbidden:
                    pass
            
        await interaction.response.edit_message(content=f"## 💵`{format(self.amount,',')}` enviados correctamente a `{dest_agency}`{xp_gave}",
                                                    embed=None, view=None)
        

async def setup(bot):
    bot.tree.add_command(BankGroup())