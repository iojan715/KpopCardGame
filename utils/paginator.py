import discord
from discord.ext import commands
from discord import app_commands
import csv
import os
import string
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from datetime import datetime


class Paginator:
    def __init__(self, embeds: list, embeds_per_page: int = 4, custom_view_factory=None):
        self.embeds = embeds
        self.current_page = 0
        self.embeds_per_page = embeds_per_page
        self.total_pages = (len(self.embeds) + self.embeds_per_page - 1) // self.embeds_per_page
        self.custom_view_factory = custom_view_factory  # 👈 Nuevo

    async def start(self, interaction: discord.Interaction):
        embeds = self.get_current_embeds()
        await interaction.response.send_message(
            embeds=embeds,
            view=self.get_view(),
            ephemeral=True
        )

    def get_view(self):
        if self.custom_view_factory:
            return self.custom_view_factory(self)
        view = discord.ui.View()
        view.add_item(PreviousButton(self))
        view.add_item(NextButton(self))
        return view

    def get_current_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page_embeds = self.embeds[start:end]

        total_items = len(self.embeds)
        page_number_embed = discord.Embed(
            description=f"### Total: {total_items}\nPage: {self.current_page + 1} / {self.total_pages}",
            color=discord.Color.dark_gray()
        )
        page_embeds.insert(0, page_number_embed)

        return page_embeds

    async def update(self, interaction: discord.Interaction):
        embeds = self.get_current_embeds()
        await interaction.response.edit_message(
            embeds=embeds,
            view=self.get_view()
        )


class PreviousButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="⬅️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page - 1) % self.paginator.total_pages
        await self.paginator.update(interaction)


class NextButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="➡️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page + 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

