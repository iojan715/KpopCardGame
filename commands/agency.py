import discord, asyncio, random, string
from discord.ext import commands
from discord import app_commands
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from datetime import datetime

LANGUAGES = {
    "en": "English",
    "es": "Español"
}


async def refresh_profile_view(interaction: discord.Interaction, user_id: int, owner: bool):
    pool = get_pool()
    async with pool.acquire() as conn:
        user_data = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        level_data = await conn.fetchrow("SELECT * FROM level_rewards WHERE level = $1", user_data["level"] + 1)

    lang_name = LANGUAGES.get(user_data["language"], user_data["language"])
    embed = discord.Embed(title=f"🏢 Agencia: {user_data['agency_name'] or 'Sin nombre'}", color=discord.Color.blue())
    embed.add_field(name="Créditos", value=f"{user_data['credits']:,} 💰", inline=True)
    embed.add_field(name="Nivel", value=f"{user_data['level']} ({user_data['xp']} XP)", inline=True)
    embed.add_field(name="Idioma", value=lang_name, inline=True)
    if owner:
        embed.add_field(name="Banco", value=f"{user_data['bank']:,} 🏦", inline=True)

    view = AgencyView(user_data, level_data, user_id, owner)
    await interaction.response.edit_message(embed=embed, view=view, content="")


class AgencyView(discord.ui.View):
    def __init__(self, user_data: dict, level_data: dict, user_id: int, owner: bool):
        super().__init__(timeout=60)
        self.user_data = user_data
        self.level_data = level_data
        self.user_id = user_id
        self.owner = owner

        if self.owner:
            self.add_item(ChangeNameButton(user_data, owner))
            self.add_item(ChangeLanguageButton(owner))
            self.add_item(ToggleNotificationsButton(user_data, owner))
            self.add_item(LevelUpButton(user_data, level_data, owner))


class ChangeNameButton(discord.ui.Button):
    def __init__(self, user_data, owner):
        super().__init__(label="Cambiar nombre", style=discord.ButtonStyle.primary)
        self.user_data = user_data
        self.owner = owner

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ChangeNameModal(self.user_data, self.owner))

class ChangeNameModal(discord.ui.Modal, title="Cambiar nombre de agencia"):
    def __init__(self, user_data, owner):
        super().__init__()
        self.user_data = user_data
        self.owner = owner
        self.new_name = discord.ui.TextInput(label="Nuevo nombre", max_length=32, required=True)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=f"¿Confirmas cambiar el nombre de la agencia a **{self.new_name.value}** por 5000 créditos?",
            view=ConfirmNameChangeView(self.new_name.value.strip(), self.user_data["user_id"], self.owner),
            embed=None
        )

class ConfirmNameChangeView(discord.ui.View):
    def __init__(self, new_name: str, user_id: int, owner: bool):
        super().__init__(timeout=30)
        self.new_name = new_name
        self.user_id = user_id
        self.owner = owner

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = get_pool()
        async with pool.acquire() as conn:
            credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", self.user_id)
            if credits < 5000:
                await interaction.response.edit_message(content="❌ No tienes suficientes créditos.", view=None)
                return
            await conn.execute("""
                UPDATE users SET agency_name = $1, credits = credits - 5000
                WHERE user_id = $2
            """, self.new_name, self.user_id)

        await refresh_profile_view(interaction, self.user_id, self.owner)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await refresh_profile_view(interaction, self.user_id, self.owner)


class ChangeLanguageButton(discord.ui.Button):
    def __init__(self, owner):
        super().__init__(label="Cambiar idioma", style=discord.ButtonStyle.secondary)
        self.owner = owner

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="🌐 Selecciona tu idioma preferido:",
            view=LanguageSelectView(interaction.user.id, self.owner),
            embed=None
        )

class LanguageSelectView(discord.ui.View):
    def __init__(self, user_id: int, owner: bool):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.owner = owner
        self.add_item(LanguageButton("English", "en", user_id, owner))
        self.add_item(LanguageButton("Español", "es", user_id, owner))

class LanguageButton(discord.ui.Button):
    def __init__(self, label: str, lang_code: str, user_id: int, owner: bool):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.lang_code = lang_code
        self.user_id = user_id
        self.owner = owner

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        await pool.execute("UPDATE users SET language = $1 WHERE user_id = $2", self.lang_code, self.user_id)
        await refresh_profile_view(interaction, self.user_id, self.owner)


class ToggleNotificationsButton(discord.ui.Button):
    def __init__(self, user_data, owner):
        state = user_data["notifications"]
        style = discord.ButtonStyle.success if state else discord.ButtonStyle.danger
        label = "Notificaciones activadas" if state else "Notificaciones desactivadas"
        super().__init__(label=label, style=style)
        self.user_id = user_data["user_id"]
        self.owner = owner

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            current = await conn.fetchval("SELECT notifications FROM users WHERE user_id = $1", self.user_id)
            await conn.execute("UPDATE users SET notifications = $1 WHERE user_id = $2", not current, self.user_id)

        await refresh_profile_view(interaction, self.user_id, self.owner)


class LevelUpButton(discord.ui.Button):
    def __init__(self, user_data, level_data, owner):
        super().__init__(label="Subir de nivel", style=discord.ButtonStyle.success, disabled=user_data['xp']<level_data['xp_needed'])
        self.user_data = user_data
        self.level_data = level_data
        self.owner = owner

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        if self.user_data['xp'] < self.level_data['xp_needed']:
            user_id = self.user_data['user_id']
            await refresh_profile_view(interaction, user_id, self.owner)
            return
            
        lvl_desc = f"## Recompensas:\n**Créditos:** {format(self.level_data['credits'],',')}"
        if self.level_data['pack']:
            print("p")
            async with pool.acquire() as conn:
                pack_data = await conn.fetchrow("SELECT * FROM packs WHERE pack_id = $1", self.level_data['pack'])
            lvl_desc += f"\n**Pack:** {pack_data['name']}"
        if self.level_data['redeemable']:
            print("a")
            async with pool.acquire() as conn:
                red_data = await conn.fetchrow("SELECT * FROM redeemables WHERE redeemable_id = $1", self.level_data['redeemable'])
            lvl_desc += f"\n**Redeemable:** {red_data['name']}"
        if self.level_data['badge']:
            print("b")
            async with pool.acquire() as conn:
                badge_data = await conn.fetchrow("SELECT * FROM badges WHERE badge_id = $1", self.level_data['badge'])
            lvl_desc += f"\n**Badge:** {badge_data['name']}"
        embed = discord.Embed(
            title=f"🎓 ¿Deseas subir al nivel {self.level_data['level']} por {self.level_data['xp_needed']} XP?",
            description=lvl_desc
            )
        
        await interaction.response.edit_message(
            embed=embed,
            view=LevelConfirmView(self.user_data["user_id"], self.level_data, self.owner)
        )

class LevelConfirmView(discord.ui.View):
    def __init__(self, user_id: int, level_data: dict, owner: bool):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.level_data = level_data
        self.owner = owner

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Subir nivel y restar XP
                await conn.execute("""
                    UPDATE users
                    SET xp = xp - $1, level = level + 1, credits = credits + $2
                    WHERE user_id = $3
                """, self.level_data["xp_needed"], self.level_data["credits"], self.user_id)

                # 2. Entregar pack si hay
                if self.level_data["pack"]:
                    new_uid = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    await conn.execute("""
                        INSERT INTO players_packs (unique_id, user_id, pack_id, buy_date)
                        VALUES ($1, $2, $3, $4)
                    """, new_uid, self.user_id, self.level_data["pack"], datetime.utcnow())

                # 3. Entregar redeemable
                if self.level_data["redeemable"]:
                    exists = await conn.fetchval("""
                        SELECT quantity FROM user_redeemables
                        WHERE user_id = $1 AND redeemable_id = $2
                    """, self.user_id, self.level_data["redeemable"])
                    if exists is not None:
                        await conn.execute("""
                            UPDATE user_redeemables
                            SET quantity = quantity + 1, last_updated = $3
                            WHERE user_id = $1 AND redeemable_id = $2
                        """, self.user_id, self.level_data["redeemable"], datetime.utcnow())
                    else:
                        await conn.execute("""
                            INSERT INTO user_redeemables (user_id, redeemable_id, quantity)
                            VALUES ($1, $2, 1)
                        """, self.user_id, self.level_data["redeemable"])

                # 4. Entregar badge si no la tiene
                if self.level_data["badge"]:
                    badge_exists = await conn.fetchval("""
                        SELECT 1 FROM user_badges
                        WHERE user_id = $1 AND badge_id = $2
                    """, self.user_id, self.level_data["badge"])
                    if not badge_exists:
                        await conn.execute("""
                            INSERT INTO user_badges (user_id, badge_id)
                            VALUES ($1, $2)
                        """, self.user_id, self.level_data["badge"])

        await refresh_profile_view(interaction, self.user_id, self.owner)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await refresh_profile_view(interaction, self.user_id, self.owner)



class AgencyCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Consulta y configura tu perfil de agencia.")
    @app_commands.describe(user="User")
    async def profile(self, interaction: discord.Interaction, user: discord.User = None):
        user_id = interaction.user.id
        owner = True
        if user and user.id != interaction.user.id:
            owner = False
            user_id = user.id

        pool = get_pool()
        async with pool.acquire() as conn:
            user_data = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user_data:
                return await interaction.response.send_message("❌ Este usuario no está registrado.", ephemeral=True)
            level_data = await conn.fetchrow("SELECT * FROM level_rewards WHERE level = $1", user_data["level"] + 1)

        lang_name = LANGUAGES.get(user_data["language"], user_data["language"])
        embed = discord.Embed(title=f"🏢 Agencia: {user_data['agency_name'] or 'Sin nombre'}", color=discord.Color.blue())
        embed.add_field(name="Créditos", value=f"{user_data['credits']:,} 💰", inline=True)
        embed.add_field(name="Nivel", value=f"{user_data['level']} ({user_data['xp']} XP)", inline=True)
        embed.add_field(name="Idioma", value=lang_name, inline=True)
        if owner:
            embed.add_field(name="Banco", value=f"{user_data['bank']:,} 🏦", inline=True)

        view = AgencyView(user_data, level_data, user_id, owner)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AgencyCommand(bot))
