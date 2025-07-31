import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, button, Button

from utils.localization import get_translation
from utils.language import get_user_language

HELP_TOPICS = [
    "tutorial", "profile", "packs", "cards", "idols", "rarities",
    "items", "groups", "inventory", "credits", "redeem", "collections",
    "presentations", "songs", "sections", "energy", "score_and_hype",
    "skills", "performance_cards",
    "faq", "support",
    ]

[
 "popularity", 
 "market", "trade", 
 "concerts", "events", 
]

class HelpGuide(commands.Cog):
    """Cog para /help con paginación mediante botones."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Mostrar la guía de ayuda por temas")
    @app_commands.describe(
        topic="Tema de ayuda a consultar",
        page="Número de página del tema"
    )
    @app_commands.choices(
        topic=[app_commands.Choice(name=topic.title().replace("_"," "), value=topic) for topic in HELP_TOPICS]
    )
    async def help(
        self,
        interaction: discord.Interaction,
        topic: app_commands.Choice[str],
        page: int = 1
    ):
        # 1) idioma del usuario
        lang = await get_user_language(interaction.user.id)

        # 2) buscar la primera página válida ≤ page
        valid_page = None
        for p in range(page, 0, -1):
            key = f"help.{topic.value}_{p}"
            text = get_translation(lang, key)
            if not text.startswith(f"[Missing translation: {key}]"):
                valid_page = p
                valid_text = text
                break

        if valid_page is None:
            await interaction.response.send_message(
                f"❌ No hay páginas disponibles para **{topic.value.title()}**.",
                ephemeral=True
            )
            return

        # 3) prefacio si se ajustó
        if valid_page != page:
            notice = (
                f"⚠️ La página **{page}** no existe para **{topic.value.title()}**. "
                f"Mostrando la última disponible (**{valid_page}**).\n\n"
            )
            valid_text = notice + valid_text

        # 4) enviar con vista de paginación
        view = HelpPaginator(topic.value, lang, valid_page)
        await interaction.response.send_message(valid_text, view=view, ephemeral=True)


MAX_SCAN = 20

class HelpPaginator(View):
    def __init__(self, topic: str, lang: str, start_page: int):
        super().__init__(timeout=None)
        self.topic = topic
        self.lang = lang
        self.pages = [
            p for p in range(1, MAX_SCAN + 1)
            if not get_translation(lang, f"help.{topic}_{p}")
                   .startswith(f"[Missing translation: help.{topic}_{p}]")
        ]
        self.current = start_page if start_page in self.pages else self.pages[-1]

    async def update_message(self, interaction: discord.Interaction):
        key = f"help.{self.topic}_{self.current}"
        text = get_translation(self.lang, key)
        await interaction.response.edit_message(content=text, view=self)

    @button(label="⬅️ Anterior", style=discord.ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: Button):
        idx = self.pages.index(self.current)
        self.current = self.pages[idx - 1] if idx > 0 else self.pages[-1]
        await self.update_message(interaction)

    @button(label="Siguiente ➡️", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: Button):
        idx = self.pages.index(self.current)
        self.current = self.pages[idx + 1] if idx < len(self.pages) - 1 else self.pages[0]
        await self.update_message(interaction)



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpGuide(bot))
