import discord, random, string
from discord import app_commands
from discord.ext import commands
from db.connection import get_pool
from datetime import datetime, timezone, timedelta
from utils.localization import get_translation
from utils.language import get_user_language
from asyncpg import Pool

version = "?v=253"

class StartView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.language = "en"  # idioma por defecto

    @discord.ui.button(label="New Agency", style=discord.ButtonStyle.primary, custom_id="start_new_agency")
    async def new_agency(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            not_your_button = get_translation("en", "error.not_your_button")
            return await interaction.response.send_message(not_your_button, ephemeral=True)

        await interaction.response.send_modal(NewAgencyModal(self.language))

    @discord.ui.button(label="Set Language", style=discord.ButtonStyle.secondary, custom_id="start_set_language")
    async def set_language(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            not_your_button = get_translation("en", "error.not_your_button")
            return await interaction.response.send_message(not_your_button, ephemeral=True)

        await interaction.response.edit_message(content="Select your language:", view=LanguageView(self))


class LanguageView(discord.ui.View):
    def __init__(self, parent_view: StartView):
        super().__init__(timeout=None)
        self.parent_view = parent_view

    @discord.ui.button(label="EN", style=discord.ButtonStyle.success)
    async def set_en(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.parent_view.language = "en"
        await interaction.response.edit_message(content="Language set to English.\nPlease create your agency to begin:", view=self.parent_view)

    @discord.ui.button(label="ES", style=discord.ButtonStyle.success)
    async def set_es(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.parent_view.language = "es"
        await interaction.response.edit_message(content="Idioma cambiado a Español.\nPor favor crea una nueva agencia para comenzar:", view=self.parent_view)


class NewAgencyModal(discord.ui.Modal, title="Create Your Agency"):
    agency_name = discord.ui.TextInput(label="Agency Name", placeholder="Enter your new agency name", max_length=30)

    def __init__(self, language: str):
        super().__init__()
        self.language = language

    async def on_submit(self, interaction: discord.Interaction):
        pool = await get_pool()
        user_id = interaction.user.id
        agency = self.agency_name.value
        now = datetime.now(timezone.utc)
        credits = 10000

        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, agency_name, credits, register_date, language, last_sponsor)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, user_id, agency, credits, now, self.language, now)
            
            while True:
                p_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                exists = await conn.fetchval("SELECT 1 FROM players_packs WHERE unique_id = $1", p_id)
                if not exists:
                    break
            await conn.execute("""INSERT INTO players_packs (unique_id, user_id, pack_id, buy_date)
                               VALUES ($1, $2, 'STR', $3)
                               """, p_id, user_id, now)

        language = self.language
        welcome = get_translation(language, "start.welcome", agency=agency, credits=credits)
        await interaction.response.send_message(welcome, ephemeral=True)


class StartCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start", description="Begin your journey in the game.")
    async def start(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pool = await get_pool()

        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            

        if user:
            row = user
            user = dict(row)
            agency_name = user["agency_name"]
            language = user["language"]
            dt = int(user["register_date"].timestamp())
            timestamp = f"<t:{dt}:D>"
            agency_info = get_translation(language, "start.agency_info", agency_name=agency_name, timestamp=timestamp)
            await interaction.response.send_message(agency_info, ephemeral=True)
        else:
            view = StartView(interaction)
            await interaction.response.send_message(
                "👋 Welcome! Please create your agency to begin:", view=view, ephemeral=True
            )



class SponsorView(discord.ui.View):
    def __init__(self, user_id: int, accumulated_credits: int, disabled: bool):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.accumulated_credits = accumulated_credits

        self.claim_button = discord.ui.Button(
            label=f"Claim",
            style=discord.ButtonStyle.green,
            disabled=disabled
        )
        self.claim_button.callback = self.claim_callback
        self.add_item(self.claim_button)

    async def claim_callback(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        pool: Pool = get_pool()

        async with pool.acquire() as conn:
            lastrow = await conn.fetchrow("SELECT last_sponsor FROM users WHERE user_id = $1", self.user_id)
            
            elapsed = now - lastrow['last_sponsor']

            hours = int(elapsed.total_seconds() // 3600)
            minutes = int((elapsed.total_seconds() % 3600) // 60)
            total_elapsed_hours = min(168, hours + minutes / 60)
            
            if total_elapsed_hours < 1:
                language = await get_user_language(interaction.user.id)
                await interaction.response.edit_message(content=get_translation(language, "sponsor.wait"),
                                                        view=None,
                                                        embed=None)
                return
            
            total_credits = self.accumulated_credits

            await conn.execute(
                "UPDATE users SET credits = credits + $1, last_sponsor = $2 WHERE user_id = $3",
                total_credits, now, self.user_id
            )
            
            user_data = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", interaction.user.id)
            current_credits = user_data['credits']
            
        language = await get_user_language(interaction.user.id)
        text_claim = get_translation(language, "sponsor.claimed", total_credits=total_credits, current_credits=current_credits)
        await interaction.response.edit_message(content=text_claim, view=None, embed=None)


class SponsorCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sponsor", description="Claim credits by sponsot / Reclama créditos por patrocinio.")
    async def sponsor(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        now = datetime.now(timezone.utc)
        pool: Pool = get_pool()

        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            groups_popularity = await conn.fetch("SELECT popularity, permanent_popularity FROM groups WHERE user_id = $1", user_id)

            if not user:
                error_not_registered = get_translation("en", "error.not_registered")
                await interaction.response.send_message(error_not_registered, ephemeral=True)
                return

            last_sponsor = user["last_sponsor"] or now - timedelta(hours=1)
            elapsed = now - last_sponsor

            hours = int(elapsed.total_seconds() // 3600)
            minutes = int((elapsed.total_seconds() % 3600) // 60)
            total_elapsed_hours = min(168, hours + minutes / 60)

            capped_elapsed = timedelta(hours=min(168, elapsed.total_seconds() / 3600))
            remaining = timedelta(hours=1) - capped_elapsed
            
            extra_influence = 0
            if groups_popularity:
                for group in groups_popularity:
                    extra_influence += group['popularity'] + group['permanent_popularity']
                
            
            influence = extra_influence + user["influence_temp"]
            
            sponsor = 150 + 600*(influence/(influence+200000))

            total_credits = int((total_elapsed_hours * 60) * (sponsor / 60))  # 100 por hora

            # El botón solo se habilita si pasó al menos 1 hora
            can_claim = elapsed >= timedelta(hours=1)

            hours2 = int(remaining.total_seconds() // 3600)
            minutes2 = int((remaining.total_seconds() % 3600) // 60)
            
            if minutes2 < 0 or hours2 < 0:
                hours2 = 0
                minutes2 = 0
            
            language = user["language"]
            
            
            
            title = get_translation(language, "sponsor.title")
            accumulated = get_translation(language, "sponsor.accumulated",
                                          hours=hours, minutes=minutes,
                                          influence=format(influence, ','), hours2=hours2,
                                          minutes2=minutes2, total_credits=format(total_credits, ','),
                                          current_credits=format(user['credits'], ','))
            embed = discord.Embed(
                title=title,
                description=accumulated,
                color=discord.Color.gold()
            )

            view = SponsorView(user_id=user_id, accumulated_credits=total_credits, disabled=not can_claim)

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)




async def setup(bot: commands.Bot):
    await bot.add_cog(StartCommand(bot))
    await bot.add_cog(SponsorCommand(bot))