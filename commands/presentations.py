import discord, json, inspect, math
from discord.ext import commands
from discord import app_commands, ui, Interaction
from datetime import datetime, timezone
from utils.paginator import Paginator, PreviousButton, NextButton
import random
from typing import List
from db.connection import get_pool
from utils.emojis import get_emoji
from utils.language import get_user_language
from utils.localization import get_translation
from commands.starter import version as v

version = v
base_cost = 2500

class PresentationGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="presentation", description="Crear y gestionar presentaciones")

    @app_commands.command(name="list", description="Listar tus presentaciones")
    @app_commands.describe(agency="Agencia")
    async def list_presentations(self, interaction: discord.Interaction, agency: str = None):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        pool = get_pool()

        # 1) Traer las presentaciones del usuario
        base_query = """
                SELECT *
                FROM presentations
                WHERE user_id = $1
                """
        async with pool.acquire() as conn:
            if agency:
                user_id = await conn.fetchval("SELECT user_id FROM users WHERE agency_name = $1", agency)
                base_query += " AND status = 'completed'"
            
            base_query += " ORDER BY presentation_date DESC"
            rows = await conn.fetch(
                base_query,
                user_id
            )

        if not rows:
            return await interaction.response.send_message(
                "❌ No tienes presentaciones guardadas.", ephemeral=True
            )

        STATUS_MAP = {
            "preparation":    ("🛠️", "Preparación"),
            "active":         ("▶️", "En curso"),
            "completed":      ("🎉", "Completada"),
            "finished":       ("⌛", "Finalizada"),
            "cancelled":      ("❌", "Cancelada"),
            "expired":        ("⏰", "Expirada"),
        }
        
        # 2) Crear embeds de vista previa
        embeds = []
        for r in rows:
            async with pool.acquire() as conn:
                group_name = await conn.fetchval("SELECT name FROM groups WHERE group_id = $1", r['group_id'])
                song_name = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", r['song_id'])

            emoji, label = STATUS_MAP.get(r["status"], ("❓", r["status"].capitalize()))
            status = f"{emoji} {label}"
            
            embed = discord.Embed(
                title=f"🎬 Presentación {r['presentation_id']}",
                color=discord.Color.blurple()
            )
            
            ts = int(r['presentation_date'].timestamp())
            
            embed.add_field(name=f"**Tipo:** {r["presentation_type"].capitalize()}", value=f"**Estado:** {status}", inline=False)
            embed.add_field(name=f"**Grupo:** {group_name if group_name else "`n/a`"}", value=f"**Canción:** {song_name if song_name else "`n/a`"}", inline=False)
            embed.add_field(name=f"Creación: <t:{int(r['presentation_date'].timestamp())}:f>", value="", inline=False)
            embeds.append(embed)

        # 3) Arrancar el paginador
        paginator = PresentationListPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=base_query,
            query_params=(user_id,),
            embeds_per_page=3
        )
        await paginator.start()

    @list_presentations.autocomplete("agency")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users ORDER BY register_date DESC")
        return [
            app_commands.Choice(name=f"{row['agency_name']}", value=row['agency_name'])
            for row in rows if current.lower() in f"{row['agency_name'].lower()}"
        ][:25]

    PRESENTATION_CHOICES = [
        app_commands.Choice(name="Live", value="live"),
        app_commands.Choice(name="Practice", value="practice"),
        # futuros tipos se agregarán aquí
    ]

    @app_commands.command(name="create", description="Crear una nueva presentación")
    @app_commands.choices(type=PRESENTATION_CHOICES)
    async def create(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str]
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        pool = get_pool()
        language = await get_user_language(user_id)
        ptype = type.value

        cost = base_cost
        extra_desc = ""
        if ptype == "practice": 
            cost = int(cost * 0.2)
            extra_desc = "\n> ⚠️ Esta presentación no otorgará popularidad ni XP"
        elif ptype == "event":
            cost = 0

        cost_desc = f"💵 {cost}"
        active_discount = False
        async with pool.acquire() as conn:
            user_data = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", user_id)
            
            already_first = await conn.fetchval("SELECT 1 FROM presentations WHERE user_id = $1", user_id)
            
            disc_invitation = await conn.fetchval("SELECT amount FROM user_boosts WHERE user_id = $1 AND boost = 'INVIT'", user_id)
            if disc_invitation and ptype == "live" and already_first:
                if disc_invitation >= 1:
                    active_discount = True
                    cost_desc = "GRATIS"
                    cost = 0
            if not already_first:
                cost = 0
                cost_desc = "Primera Gratis"
                
        if not user_data or user_data["credits"] < cost:
            print(cost)
            await interaction.response.send_message(
                get_translation(language,'presentation.not_enough_credits', cost=cost),
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🎤 ¿Quieres crear una presentación de tipo **{type.name}**?",
            description=f"💸 Costo: **{cost_desc}**{extra_desc}",
            color=discord.Color.dark_blue()
        )
        view = ConfirmCreatePresentationView(user_id, ptype, cost, active_discount)
        await interaction.response.send_message(
            content=f"",
            embed=embed,
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="add_song", description="Asignar una canción a una de tus presentaciones en preparación")
    @app_commands.describe(song="ID de la canción que quieres asignar")
    async def add_song(self, interaction: Interaction, song: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        pool = get_pool()

        async with pool.acquire() as conn:
            song_row = await conn.fetchrow("SELECT * FROM songs WHERE song_id = $1", song)
            if not song_row:
                await interaction.response.send_message("❌ No se encontró ninguna canción con ese ID.", ephemeral=True)
                return

            pres_rows = await conn.fetch("""
                SELECT presentation_id, presentation_date, song_id, group_id
                FROM presentations
                WHERE user_id = $1 AND status = 'preparation'
                ORDER BY presentation_date DESC
            """, user_id)

            if not pres_rows:
                await interaction.response.send_message("❌ No tienes presentaciones en preparación.", ephemeral=True)
                return

            descr = ""
        
            for row in pres_rows:
                song_name = "n/a"
                if row['song_id']:
                    songrow = await conn.fetchrow("SELECT name, original_artist FROM songs WHERE song_id = $1", row['song_id'])
                    song_name = f"{songrow['name']} - {songrow['original_artist']}"
                
                group_name = "n/a"
                if row['group_id']:
                    grouprow = await conn.fetchrow("SELECT name FROM groups WHERE group_id = $1", row['group_id'])
                    group_name = grouprow['name']
                
                descr += f"**ID:** `{row['presentation_id']}`\n> Group: `{group_name}`\n> Song: `{song_name}`\n"
            
        embed = discord.Embed(
            title="Elige a cuál presentación deseas asignar esta canción:",
            description=descr,
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed, view=PresentationAddSongView(interaction, song, pres_rows), ephemeral=True)

    @add_song.autocomplete("song")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM songs")
        return [
            app_commands.Choice(name=f"{row["name"]} - {row['original_artist']}",
                                value=row["song_id"])
            for row in rows if current.lower() in f"{row["name"]} - {row['original_artist']}".lower()
        ][:25] 

    @app_commands.command(name="add_group", description="Asignar un grupo a una de tus presentaciones en preparación")
    async def add_group(self, interaction: Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        pool = get_pool()

        async with pool.acquire() as conn:
            pres_rows = await conn.fetch("""
                SELECT presentation_id, song_id, group_id, presentation_date
                FROM presentations
                WHERE user_id = $1 AND status = 'preparation'
                ORDER BY presentation_date DESC
            """, user_id)

            if not pres_rows:
                await interaction.response.send_message("❌ No tienes presentaciones en preparación.", ephemeral=True)
                return

            descr = ""
            for row in pres_rows:
                song_info = "n/a"
                if row['song_id']:
                    song_row = await conn.fetchrow("SELECT name, original_artist FROM songs WHERE song_id = $1", row['song_id'])
                    song_info = f"{song_row['name']} - {song_row['original_artist']}" if song_row else "n/a"
                
                group_name = "n/a"
                if row['group_id']:
                    group_row = await conn.fetchrow("SELECT name FROM groups WHERE group_id = $1", row['group_id'])
                    group_name = group_row["name"] if group_row else "n/a"

                descr += f"**ID:** `{row['presentation_id']}`\n> Group: `{group_name}`\n> Song: `{song_info}`\n\n"

        embed = discord.Embed(
            title="Selecciona la presentación a la que deseas asignar un grupo:",
            description=descr,
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, view=PresentationAddGroupView(interaction, pres_rows), ephemeral=True)

    @app_commands.command(name="perform", description="Iniciar una presentación en preparación")
    async def perform(self, interaction: Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        pool = get_pool()
        language = await get_user_language(user_id)
        translate = lambda k: get_translation(language, k)

        async with pool.acquire() as conn:
            # Verificar si ya hay una presentación activa
            active_pres = await conn.fetchrow("""
                SELECT presentation_id FROM presentations
                WHERE user_id = $1 AND status = 'active'
                LIMIT 1
            """, user_id)

        if active_pres:
            await show_current_section_view(interaction, active_pres['presentation_id'], edit=False)
            return

        # Buscar presentaciones en preparación
        async with pool.acquire() as conn:
            pres_rows = await conn.fetch("""
                SELECT * FROM presentations
                WHERE user_id = $1 AND status = 'preparation'
                ORDER BY presentation_date DESC
            """, user_id)

        if not pres_rows:
            await interaction.edit_original_response(
                content="❌ No tienes presentaciones en preparación."
            )
            return
        
        embeds = []
        
        for row in pres_rows:
            async with pool.acquire() as conn:
                group_name = await conn.fetchval("SELECT name FROM groups WhERE group_id = $1", row['group_id'])
                song_name = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", row['song_id'])
            
            desc = f"**Tipo:** {row['presentation_type'].capitalize().replace("_"," ")}\n"
            desc += f"**Grupo:** {group_name if group_name else "`n/a`"}\n"
            desc += f"**Canción:** {song_name if song_name else "`n/a`"}"
            
            embed = discord.Embed(
                title=f"Presentación `{row['presentation_id']}`",
                description=desc,
                color=discord.Color.blue()
            )
            embeds.append(embed)

        # Mostrar lista para seleccionar una presentación
        await interaction.edit_original_response(
            content="## 🎬 Selecciona una presentación:",
            embeds=embeds,
            view=PresentationSelectToPerformView(interaction, pres_rows)
        )


# --- list
class PresentationDetailButton(discord.ui.Button):
    def __init__(self, rowdata: dict, paginator: "PresentationListPaginator"):
        super().__init__(
            label=f"Detalles",
            style=discord.ButtonStyle.primary
        )
        self.rowdata = rowdata
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        # Placeholder: aquí iría la vista detallada
        pool = get_pool()
        async with pool.acquire() as conn:
            group_name = await conn.fetchval("SELECT name FROM groups WHERE group_id = $1", self.rowdata['group_id'])
            song_name = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", self.rowdata['song_id'])
        
        STATUS_MAP = {
            "preparation":    ("🛠️", "Preparación"),
            "active":         ("▶️", "En curso"),
            "completed":      ("🎉", "Completada"),
            "finished":       ("⌛", "Finalizada"),
            "cancelled":      ("❌", "Cancelada"),
            "expired":        ("⏰", "Expirada"),
        }
        emoji, label = STATUS_MAP.get(self.rowdata["status"], ("❓", self.rowdata["status"].capitalize()))
        status = f"{emoji} {label}"
            
        embed = discord.Embed(
            title=f"Detalles — {self.rowdata['presentation_id']}",
            description=(
                f"**Tipo:** {self.rowdata['presentation_type'].capitalize()}\n"
                f"**Estado:** {status}\n"
                f"**Grupo:** {group_name if group_name else "`n/a`"}\n"
                f"**Canción:** {song_name if song_name else "`n/a`"}\n"
                f"**Creación:** <t:{int(self.rowdata['presentation_date'].timestamp())}:f>\n"
                f"**Ultima acción:** <t:{int(self.rowdata['last_action'].timestamp())}:f>\n"
                f"**Sección:** `{self.rowdata['current_section']}`\n"
                f"**Puntuación:** `{format(self.rowdata['total_score'],',')}`\n"
                f"**Hype:** `{round(self.rowdata['total_hype'],1)}`\n"
                f"**Popularidad:** `{format(self.rowdata['total_popularity'],',')}`\n"
            ),
            color=discord.Color.gold()
        )
        view = discord.ui.View()
        view.add_item(PublishPracticeButton(rowdata=self.rowdata, paginator=self.paginator))
        # volver atrás
        view.add_item(BackToPresentationListButton(self.paginator))
        await interaction.response.edit_message(embed=embed, view=view)

class PublishPracticeButton(discord.ui.Button):
    def __init__(self, rowdata: dict, paginator: "PresentationListPaginator"):
        super().__init__(label="Publicar práctica", style=discord.ButtonStyle.primary, emoji="📢", disabled=(rowdata['status']!='finished' or rowdata['presentation_type']!='practice'))
        self.rowdata = rowdata
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        # Construir embed de confirmación
        total_score = self.rowdata["total_score"]
        # obtenemos average_score
        pool = get_pool()
        async with pool.acquire() as conn:
            avg = await conn.fetchval(
                "SELECT average_score FROM songs WHERE song_id = $1",
                self.rowdata["song_id"]
            ) or 1.0

        # cálculo al 80%
        raw_pop = 1000 * (total_score / avg)
        popularity = int(raw_pop * 0.8)
        xp = popularity // 10
        r_popularity = f"{format(popularity,',')}"
        
        cost = int(base_cost*0.8)  # 80% restante
        r_cost = f"{format(cost,',')}"

        embed = discord.Embed(
            title="📢 Publicar práctica",
            description=(
                f"Esto te otorgará el 80% de la popularidad generada en la presentación con base en el puntaje. Deberás cubrir el 80% restante del costo de la presentación.\n\n"
                f"> Costo: **`{r_cost}` 💵**\n\nRecibirás:\n"
                f"> **{r_popularity}** de popularidad\n"
                f"> **{xp} XP**\n\n"
                "¿Confirmas?"
            ),
            color=discord.Color.blurple()
        )
        view = ConfirmPublishPracticeView(
            user_id=interaction.user.id,
            presentation_id=self.rowdata["presentation_id"],
            popularity=popularity,
            xp=xp,
            cost=cost,
            paginator=self.paginator
        )
        await interaction.response.edit_message(embed=embed, view=view)
        
class ConfirmPublishPracticeView(discord.ui.View):
    def __init__(self, user_id: int, presentation_id: str, popularity: int, xp: int, cost: int, paginator: "PresentationListPaginator"):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.presentation_id = presentation_id
        self.popularity = popularity
        self.xp = xp
        self.cost = cost
        self.paginator = paginator

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        pool = get_pool()
        async with pool.acquire() as conn:
            # 1) Cobrar 2000 créditos
            await conn.execute(
                "UPDATE users SET credits = credits - $1 WHERE user_id = $2",
                self.cost, self.user_id
            )
            # 2) Otorgar XP
            await conn.execute(
                "UPDATE users SET xp = xp + $1 WHERE user_id = $2",
                self.xp, self.user_id
            )
            # 3) Actualizar presentación a completed y total_popularity
            await conn.execute(
                """
                UPDATE presentations
                SET status = 'completed',
                    total_popularity = total_popularity + $1
                WHERE presentation_id = $2
                """,
                self.popularity, self.presentation_id
            )
            # 4) Añadir popularidad al grupo
            await conn.execute(
                "UPDATE groups SET popularity = popularity + $1 WHERE group_id = (SELECT group_id FROM presentations WHERE presentation_id = $2)",
                self.popularity, self.presentation_id
            )

        # 5) Volver a la lista actualizada
        async with pool.acquire() as conn:
            rows = await conn.fetch(self.paginator.base_query, *self.paginator.query_params)
        if not rows:
            return await interaction.response.edit_message(
                content="⚠️ No se encontraron presentaciones.",
                embed=None, view=None
            )
            
        STATUS_MAP = {
            "preparation":    ("🛠️", "Preparación"),
            "active":         ("▶️", "En curso"),
            "completed":      ("🎉", "Completada"),
            "finished":       ("⌛", "Finalizada"),
            "cancelled":      ("❌", "Cancelada"),
            "expired":        ("⏰", "Expirada"),
        }
        # regenerar embeds
        embeds = []
        for r in rows:
            async with pool.acquire() as conn:
                group_name = await conn.fetchval("SELECT name FROM groups WHERE group_id = $1", r['group_id'])
                song_name = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", r['song_id'])
            
            emoji, label = STATUS_MAP.get(r["status"], ("❓", r["status"].capitalize()))
            status = f"{emoji} {label}"
            
            e = discord.Embed(
                title=f"🎬 Presentación {r['presentation_id']}",
                color=discord.Color.blurple()
            )
            e.add_field(name=f"**Tipo:** {r["presentation_type"].capitalize()}", value=f"**Estado:** {status}", inline=False)
            e.add_field(name=f"**Grupo:** {group_name if group_name else "`n/a`"}", value=f"**Canción:** {song_name if song_name else "`n/a`"}", inline=False)
            e.add_field(name=f"Creación: `{r["presentation_date"].strftime("%Y-%m-%d %H:%M")}`", value="", inline=False)
            e.set_footer(text=f"{r['presentation_id']}")
            embeds.append(e)
        
        new_p = PresentationListPaginator(embeds, rows, interaction, self.paginator.base_query, self.paginator.query_params)
        await new_p.restart(interaction)

    @discord.ui.button(label="✖ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)
        # Simplemente regresamos a la vista de detalles original
        # Repetimos lo mismo que PresentationDetailButton.callback
        await BackToPresentationListButton(self.paginator).callback(interaction)


class BackToPresentationListButton(discord.ui.Button):
    def __init__(self, paginator: "PresentationListPaginator"):
        super().__init__(label="🔙 Volver", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        # re-ejecutar la consulta
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(self.paginator.base_query, *self.paginator.query_params)
        if not rows:
            return await interaction.response.edit_message(
                content="⚠️ No se encontraron presentaciones.",
                embed=None, view=None
            )
            
        STATUS_MAP = {
            "preparation":    ("🛠️", "Preparación"),
            "active":         ("▶️", "En curso"),
            "completed":      ("🎉", "Completada"),
            "finished":       ("⌛", "Finalizada"),
            "cancelled":      ("❌", "Cancelada"),
            "expired":        ("⏰", "Expirada"),
        }
        # regenerar embeds
        embeds = []
        for r in rows:
            async with pool.acquire() as conn:
                group_name = await conn.fetchval("SELECT name FROM groups WHERE group_id = $1", r['group_id'])
                song_name = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", r['song_id'])
            
            emoji, label = STATUS_MAP.get(r["status"], ("❓", r["status"].capitalize()))
            status = f"{emoji} {label}"
            
            e = discord.Embed(
                title=f"🎬 Presentación {r['presentation_id']}",
                color=discord.Color.blurple()
            )
            e.add_field(name=f"**Tipo:** {r["presentation_type"].capitalize()}", value=f"**Estado:** {status}", inline=False)
            e.add_field(name=f"**Grupo:** {group_name if group_name else "`n/a`"}", value=f"**Canción:** {song_name if song_name else "`n/a`"}", inline=False)
            e.add_field(name=f"Creación: <t:{int(r['presentation_date'].timestamp())}:f>", value="", inline=False)
            e.set_footer(text=f"{r['presentation_id']}")
            embeds.append(e)

        new_p = PresentationListPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        await new_p.restart(interaction)

class PresentationListPaginator:
    def __init__(
        self,
        embeds: list[discord.Embed],
        rows: list[dict],
        interaction: discord.Interaction,
        base_query: str,
        query_params: tuple,
        embeds_per_page: int = 3
    ):
        self.all_embeds = embeds
        self.all_rows = rows
        self.interaction = interaction
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(embeds) + embeds_per_page - 1) // embeds_per_page
        self.base_query = base_query
        self.query_params = query_params

    def get_page_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page = self.all_embeds[start:end]
        footer = discord.Embed(
            description=f"Página {self.current_page+1}/{self.total_pages} • Total: {len(self.all_embeds)}",
            color=discord.Color.dark_gray()
        )
        return [footer] + page

    def get_view(self):
        view = discord.ui.View(timeout=120)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        for row in self.all_rows[start:end]:
            view.add_item(PresentationDetailButton(rowdata=row, paginator=self))
        view.add_item(PreviousListPageButton(self))
        view.add_item(NextListPageButton(self))
        return view

    async def start(self):
        await self.interaction.response.send_message(
            embeds=self.get_page_embeds(),
            view=self.get_view(),
            ephemeral=True
        )

    async def restart(self, interaction: discord.Interaction):
        self.current_page = 0
        await interaction.response.edit_message(
            embeds=self.get_page_embeds(),
            view=self.get_view()
        )

    async def update(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embeds=self.get_page_embeds(),
            view=self.get_view()
        )

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await self.update(interaction)

class PreviousListPageButton(discord.ui.Button):
    def __init__(self, paginator: PresentationListPaginator):
        super().__init__(label="⬅️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.previous_page(interaction)

class NextListPageButton(discord.ui.Button):
    def __init__(self, paginator: PresentationListPaginator):
        super().__init__(label="➡️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.next_page(interaction)


# --- create
class ConfirmCreatePresentationView(discord.ui.View):
    def __init__(self, user_id: int, presentation_type: str, cost: int, active_discount:bool):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.presentation_type = presentation_type
        self.cost = cost
        self.active_discount = active_discount

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No puedes confirmar esta acción.", ephemeral=True)
            return

        pool = get_pool()
        presentation_id = str(random.randint(10000, 99999)).zfill(5)
        cost = self.cost

        async with pool.acquire() as conn:
            # Verificar de nuevo que tiene créditos
            user_data = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", self.user_id)
            if not user_data or user_data["credits"] < cost:
                await interaction.response.edit_message(
                    content="❌ No tienes créditos suficientes para crear la presentación.",
                    view=None
                )
                return

            if self.active_discount and self.presentation_type == "live":
                disc_invitation = await conn.fetchval("SELECT amount FROM user_boosts WHERE user_id = $1 AND boost = 'INVIT'", self.user_id)
                if disc_invitation >= 1:
                    cost = 0
                    await conn.execute("UPDATE user_boosts SET amount = amount - 1 WHERE user_id = $1 AND boost = 'INVIT'", self.user_id)
            
            
            await conn.execute("""
                INSERT INTO presentations (presentation_id, owner_id, user_id, presentation_type)
                VALUES ($1, $2, $3, $4)
            """, presentation_id, self.user_id, self.user_id, self.presentation_type)

            await conn.execute("""
                UPDATE users SET credits = credits - $1 WHERE user_id = $2
            """, cost, self.user_id)
            
        desc = "Elige un grupo para usar en la presentación con `/presentation add_group`\n"
        desc += "Elige una canción para presentar con `/presentation add_song`\n"
        desc += "Inicia la presentación cuando tengas todo listo con `/presentation perform`\n\n"
        desc += "_Puedes retomar la presentación si la dejas incompleta en cualquier momento, volviendo a usar `/presentation perform`_"
        
        embed = discord.Embed(
            title=f"✅ Presentación creada exitosamente",
            description=desc,
            color=discord.Color.dark_blue()
        )
        embed.add_field(name="🆔:",value=f"{presentation_id}")

        await interaction.response.edit_message(
            content=f"",
            embed=embed,
            view=None
        )

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No puedes cancelar esta acción.", ephemeral=True)
            return

        await interaction.response.edit_message(content="❌ Acción cancelada.", view=None)


# --- add_song
class PresentationAddSongView(ui.View):
    def __init__(self, interaction: Interaction, song_id: str, presentations: List[dict]):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.song_id = song_id
        self.presentations = presentations

        for pres in presentations:
            self.add_item(PresentationButton(pres['presentation_id'], song_id))

class PresentationButton(ui.Button):
    def __init__(self, presentation_id: str, song_id: str):
        super().__init__(label=presentation_id, style=discord.ButtonStyle.primary)
        self.presentation_id = presentation_id
        self.song_id = song_id

    async def callback(self, interaction: Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            pres = await conn.fetchrow("SELECT can_select_song FROM presentations WHERE presentation_id = $1", self.presentation_id)

            if not pres:
                await interaction.response.edit_message(content="❌ No se encontró la presentación.", view=None)
                return

            if not pres['can_select_song']:
                await interaction.response.edit_message(content="❌ Esta presentación no permite cambiar la canción.", view=None)
                return

            await conn.execute("""
                UPDATE presentations
                SET song_id = $1, last_action = $2
                WHERE presentation_id = $3
            """, self.song_id, datetime.now(timezone.utc), self.presentation_id)

        await interaction.response.edit_message(
            content="## ✅ Canción asignada exitosamente a la presentación.\nAsigna un grupo a tu presentación con `/presentations add_group` o inicia la presentación con `/presentation perform`.",
            view=None, embed=None)

# --- add group
class PresentationAddGroupView(ui.View):
    def __init__(self, interaction: Interaction, presentations):
        super().__init__(timeout=60)
        self.interaction = interaction
        for pres in presentations:
            self.add_item(GroupSelectPresentationButton(pres['presentation_id']))

# paginador de selección de grupo
class GroupSelectionPaginator:
    def __init__(self, interaction: Interaction, presentation_id: str, groups: list, embeds_per_page: int = 1):
        self.interaction = interaction
        self.presentation_id = presentation_id
        self.groups = groups
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(groups) + embeds_per_page - 1) // embeds_per_page

    def get_page_items(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        return self.groups[start:end]

    async def build_embeds_and_view(self):
        embeds = []
        view = discord.ui.View(timeout=300)
        pool = get_pool()

        async with pool.acquire() as conn:
            for row in self.get_page_items():
                members_row = await conn.fetch("SELECT * FROM groups_members WHERE group_id = $1", row['group_id'])

                descr = ""
                for member in members_row:
                    base_row = await conn.fetchrow("SELECT name FROM idol_base WHERE idol_id = $1", member['idol_id'])
                    descr += f"- {base_row['name']} "
                    if member['card_id'] or member['mic_id'] or member['outfit_id'] or member['accessory_id'] or member['consumable_id']:
                        descr += "👤" if member['card_id'] else ""
                        descr += "🎤" if member['mic_id'] else ""
                        descr += "👗" if member['outfit_id'] else ""
                        descr += "🎀" if member['accessory_id'] else ""
                        descr += "🧃" if member['consumable_id'] else ""
                    descr += "\n"

                embed = discord.Embed(
                    title=row["name"],
                    description=descr or "Sin integrantes asignados.",
                    color=discord.Color.purple()
                )
                embeds.append(embed)

                # Botón por grupo (mismo nombre visible)
                view.add_item(GroupAssignButton(self.presentation_id, row["group_id"], row["name"]))

        # Footer de página
        footer = discord.Embed(
            description=f"Página {self.current_page + 1}/{self.total_pages}",
            color=discord.Color.dark_gray()
        )
        embeds.append(footer)

        view.add_item(PreviousPageButton(self))
        view.add_item(NextPageButton(self))

        return embeds, view

    async def start(self):
        embeds, view = await self.build_embeds_and_view()
        await self.interaction.response.edit_message(
            content="🎤 Elige el grupo que quieres asignar a esta presentación:",
            embeds=embeds,
            view=view
        )

    async def update(self, interaction: Interaction):
        embeds, view = await self.build_embeds_and_view()
        await interaction.response.edit_message(embeds=embeds, view=view)

class PreviousPageButton(discord.ui.Button):
    def __init__(self, paginator: GroupSelectionPaginator):
        super().__init__(label="◀️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: Interaction):
        self.paginator.current_page = (self.paginator.current_page - 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class NextPageButton(discord.ui.Button):
    def __init__(self, paginator: GroupSelectionPaginator):
        super().__init__(label="▶️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: Interaction):
        self.paginator.current_page = (self.paginator.current_page + 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class GroupAssignButton(discord.ui.Button):
    def __init__(self, presentation_id: str, group_id: str, name: str):
        super().__init__(label=name, style=discord.ButtonStyle.success)
        self.presentation_id = presentation_id
        self.group_id = group_id

    async def callback(self, interaction: Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE presentations
                SET group_id = $1, last_action = $2
                WHERE presentation_id = $3
            """, self.group_id, datetime.now(timezone.utc), self.presentation_id)

        await interaction.response.edit_message(
            content=f"## ✅ Grupo asignado exitosamente a la presentación `{self.presentation_id}`\nAsigna una canción con `/presentation add_song` o inicia la presentación con `/presentation perform`.",
            embed=None,
            view=None
        )

class GroupSelectPresentationButton(ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label=presentation_id, style=discord.ButtonStyle.primary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            group_rows = await conn.fetch("""
                SELECT group_id, name, popularity
                FROM groups
                WHERE user_id = $1 AND status = 'active'
            """, interaction.user.id)
            

        if not group_rows:
            await interaction.response.edit_message(
                content="❌ No tienes grupos disponibles.",
                view=None,
                embed=None
            )
            return
        
        paginator = GroupSelectionPaginator(interaction, self.presentation_id, group_rows)
        await paginator.start()

class GroupSelectionView(ui.View):
    def __init__(self, presentation_id: str, groups):
        super().__init__(timeout=60)
        self.presentation_id = presentation_id
        for group in groups:
            self.add_item(GroupAssignButton(presentation_id, group["group_id"], group["name"]))

class GroupAssignButton(ui.Button):
    def __init__(self, presentation_id: str, group_id: str, name: str):
        super().__init__(label=name, style=discord.ButtonStyle.success)
        self.presentation_id = presentation_id
        self.group_id = group_id

    async def callback(self, interaction: Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE presentations
                SET group_id = $1, last_action = $2
                WHERE presentation_id = $3
            """, self.group_id, datetime.now(timezone.utc), self.presentation_id)

        await interaction.response.edit_message(
            content=f"✅ Grupo asignado exitosamente a la presentación `{self.presentation_id}`.",
            embed=None,
            view=None
        )

# --- PERFORM

# - start performance
class PresentationSelectToPerformView(ui.View):
    def __init__(self, interaction: Interaction, presentations: List[dict]):
        super().__init__(timeout=60)
        self.interaction = interaction
        for row in presentations:
            self.add_item(PerformPresentationButton(row["presentation_id"]))

class PerformPresentationButton(ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label=f"{presentation_id}", style=discord.ButtonStyle.primary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: Interaction):
        user_id = interaction.user.id
        pool = get_pool()

        # Verificar si ya hay una activa (de nuevo por seguridad)
        async with pool.acquire() as conn:
            already_active = await conn.fetchval("""
                SELECT 1 FROM presentations
                WHERE user_id = $1 AND status = 'active'
            """, user_id)
            presentation = await conn.fetchrow(
                "SELECT * FROM presentations WHERE presentation_id = $1",
                self.presentation_id
            )

            group_name = song_name = "`n/a`"
            if presentation['group_id']:
                group_name = await conn.fetchval(
                    "SELECT name FROM groups WHERE group_id = $1",
                    presentation['group_id'])
                
            if presentation['song_id']:
                song_name = await conn.fetchval(
                    "SELECT name FROM songs WHERE song_id = $1",
                    presentation['song_id'])
        
        desc = f"**Tipo:** {presentation['presentation_type'].capitalize().replace("_"," ")}\n"
        desc += f"**Grupo:** {group_name}\n"
        desc += f"**Canción:** {song_name}"
        
        embed = discord.Embed(
            title=f"🎬 Presentación `{self.presentation_id}`",
            description=desc,
            color=discord.Color.dark_blue()
        )
        
        if already_active:
            await interaction.response.edit_message(
                content="⚠️ Ya tienes una presentación activa.",
                embed=None,
                view=None
            )
            return

        await interaction.response.edit_message(
            content="",
            embed=embed,
            view=ConfirmStartPresentationView(self.presentation_id, user_id)
        )

class ConfirmStartPresentationView(ui.View):
    def __init__(self, presentation_id: str, user_id: int):
        super().__init__(timeout=60)
        self.presentation_id = presentation_id
        self.user_id = user_id

    @ui.button(label="✅ Iniciar", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        if interaction.user.id != self.user_id:
            await interaction.edit_original_response(content="❌ No puedes iniciar esta presentación.")
            return

        pool = get_pool()

        async with pool.acquire() as conn:
            # Obtener info de presentación
            pres = await conn.fetchrow("""
                SELECT group_id, song_id FROM presentations
                WHERE presentation_id = $1
            """, self.presentation_id)

            if not pres or not pres["group_id"] or not pres["song_id"]:
                await interaction.edit_original_response(
                    content="❌ La presentación no tiene grupo y canción asignados.",
                    view=None
                )
                return

            group_id, song_id = pres["group_id"], pres["song_id"]

            # Obtener miembros del grupo
            group_members = await conn.fetch("""
                SELECT * FROM groups_members
                WHERE group_id = $1
            """, group_id)

            for member in group_members:
                # Calcular stats base
                vocal = rap = dance = visual = energy = 0

                if member['card_id']:
                    card_id, unique_id = member['card_id'].split('.')
                    card = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", card_id)

                    vocal += card["vocal"]
                    rap += card["rap"]
                    dance += card["dance"]
                    visual += card["visual"]
                    energy += card["energy"]
                else:
                    card_id = unique_id = None
                    idol = await conn.fetchrow("SELECT * FROM idol_base WHERE idol_id = $1", member['idol_id'])
                    vocal += idol["vocal"]
                    rap += idol["rap"]
                    dance += idol["dance"]
                    visual += idol["visual"]
                    energy += 50

                # Equipamiento adicional
                for item_field in ["mic_id", "outfit_id", "accessory_id", "consumable_id"]:
                    if member[item_field]:
                        item_id, unique_item_id = member[item_field].split(".")
                        item = await conn.fetchrow("""
                            SELECT * FROM cards_item WHERE item_id = $1
                        """, item_id)
                        if item:
                            vocal += item["plus_vocal"]
                            rap += item["plus_rap"]
                            dance += item["plus_dance"]
                            visual += item["plus_visual"]
                            energy += item["plus_energy"]

                            # Reducir durabilidad
                            await conn.execute("""
                                UPDATE user_item_cards
                                SET durability = durability - 1
                                WHERE unique_id = $1
                            """, unique_item_id)
                            
                            items_cero_durability = await conn.fetch("SELECT * FROM user_item_cards WHERE durability < 1")
                            
                            for item in items_cero_durability:
                                field = ""
                                if item['item_id'][:3] == "ACC":
                                    field = "accessory_id"
                                elif item['item_id'][:3] == "MIC":
                                    field = "mic_id"
                                elif item['item_id'][:3] == "FIT":
                                    field = "outfit_id"
                                elif item['item_id'][:3] == "CON":
                                    field = "consumable_id"
                                    
                                await conn.execute(f"""
                                    UPDATE groups_members
                                    SET {field} = $1
                                    WHERE {field} = $2
                                """, None, f"{item['item_id']}.{item['unique_id']}")
                            
                                await conn.execute(f"""
                                    DELETE FROM user_item_cards
                                    WHERE unique_id = $1
                                """, item['unique_id'])


                # Insertar en members
                await conn.execute("""
                    INSERT INTO presentation_members (
                        presentation_id, idol_id, card_id, unique_id, user_id,
                        vocal, rap, dance, visual, max_energy
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """, self.presentation_id, member['idol_id'], card_id, unique_id, member["user_id"],
                     vocal, rap, dance, visual, energy or 50)

            # Insertar sección 1
            await conn.execute("""
                INSERT INTO presentation_sections (presentation_id, section)
                VALUES ($1, 1)
            """, self.presentation_id)

            # Cambiar estado de la presentación
            await conn.execute("""
                UPDATE presentations SET status = 'active', last_action = $2, free_switches = 2, performance_card_uses = 2
                WHERE presentation_id = $1
            """, self.presentation_id, datetime.now(timezone.utc))
            
        await show_current_section_view(interaction, self.presentation_id, edit=True)

class placeholderView(ui.View):
    def __init__(self, presentation_id: str, user_id: int):
        super().__init__(timeout=60)

    @ui.button(label="➕ Grupo", style=discord.ButtonStyle.success)
    async def add_group(self, interaction: Interaction, button: ui.Button):
        pass
    
    @ui.button(label="➕ Canción", style=discord.ButtonStyle.success)
    async def add_song(self, interaction: Interaction, button: ui.Button):
        pass

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(content="❌ Inicio de presentación cancelado.", view=None)




async def show_current_section_view(interaction: discord.Interaction, presentation_id: str, edit: bool = False):
    pool = get_pool()
    guild = interaction.guild
    user_id = interaction.user.id

    async with pool.acquire() as conn:
        # Obtener datos generales de la presentación
        presentation = await conn.fetchrow("""
            SELECT * FROM presentations
            WHERE presentation_id = $1 AND user_id = $2
        """, presentation_id, user_id)

        if not presentation:
            await interaction.edit_original_response(content="❌ No se encontró la presentación.")
            return

        # Obtener nombres de la canción y grupo
        song_name = "n/a"
        group_name = "n/a"

        if presentation['song_id']:
            song_row = await conn.fetchrow("SELECT name, original_artist FROM songs WHERE song_id = $1", presentation['song_id'])
            if song_row:
                song_name = f"{song_row['name']} - {song_row['original_artist']}"

        if presentation['group_id']:
            group_row = await conn.fetchrow("SELECT name FROM groups WHERE group_id = $1", presentation['group_id'])
            if group_row:
                group_name = group_row['name']

        # Detectar idol activo
        active_idol = await conn.fetchrow("""
            SELECT * FROM presentation_members
            WHERE presentation_id = $1 AND current_position = 'active'
        """, presentation_id)

        idol_image_url = None
        active_idol_text = ""

        
        idol_data = None
        if active_idol:
            idol_data = await conn.fetchrow("SELECT name FROM idol_base WHERE idol_id = $1", active_idol['idol_id'])
            card_id = active_idol['card_id']
            if card_id:
                idol_image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}"
                active_idol_text = f"`{card_id}`"
            else:
                active_idol_text = "> Sin carta asignada"
        else:
            active_idol_text = "🔁 Selecciona uno para comenzar."

        embeds = []
        
        # Construir embed
        embed = discord.Embed(
            title=f"🎬 Presentación en curso: {presentation_id}",
            description=f"🎶 **Canción:** {song_name}\n👥 **Grupo:** {group_name}",
            color=discord.Color.orange()
        )

        if presentation['free_switches'] < 0:
            switch_rule = "Forced switch ⚠️"
        elif presentation['free_switches'] == 0:
            switch_rule = "No switches ❌"
        else:
            switch_rule = f"Free switches: {str(presentation['free_switches'])}"
            
        if presentation['performance_card_uses'] > 0:
            p_emoji = presentation['performance_card_uses']
        else:
            p_emoji = "❌"
        
        embed.add_field(name=f"⭐ Total Score: {str(presentation["total_score"])}",
                        value=f"🔥 Total Hype: {str(round(presentation["total_hype"], 1))}",
                        inline=True)
        embed.add_field(name=f"🔁 {switch_rule}", value=f"🎭 P. Cards uses: {p_emoji}", inline=True)

        # Efectos activos (solo si tienen duración > 0)
        if presentation["stage_effect"] and presentation["stage_effect_duration"] > 0:
            embed.add_field(
                name="🌟 Stage Effect",
                value=f"{presentation['stage_effect'].replace("_"," ").capitalize()} ⏳{presentation['stage_effect_duration']}",
                inline=False
            )

        if presentation["support_effect"] and presentation["support_effect_duration"] > 0:
            embed.add_field(
                name="🧃 Support Effect",
                value=f"{presentation['support_effect'].replace("_"," ").capitalize()} ⏳{presentation['support_effect_duration']}",
                inline=False
            )

        # Estado del idol actual
        name_idol = "`n/a`"
        if idol_data:
            name_idol = idol_data['name']
        embed.add_field(name=f"🧑‍🎤 Idol actual: {name_idol}", value=active_idol_text, inline=False)

        if idol_image_url:
            embed.set_thumbnail(url=idol_image_url)
        
        section = await conn.fetchrow(
            "SELECT * FROM song_sections WHERE song_id = $1 AND section_number = $2",
            presentation['song_id'], presentation['current_section'])
        song = await conn.fetchrow("SELECT * FROM songs WHERE song_id = $1", presentation['song_id'])
        

        ps_emoji = get_emoji(guild, "PassiveSkill")
        as_emoji = get_emoji(guild, "ActiveSkill")
        ss_emoji = get_emoji(guild, "SupportSkill")
        us_emoji = get_emoji(guild, "UltimateSkill")

                
        
        # Obtener y mostrar habilidades activas, pasivas y ultimate del idol activo
        if active_idol:
            card=None
            if active_idol["unique_id"]:
                card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", active_idol["unique_id"])
                
            Er = active_idol['max_energy']-active_idol['used_energy']
                            
            energy_left = round(active_idol["max_energy"] - active_idol["used_energy"], 1)
            energy_percent = round((energy_left / active_idol["max_energy"]) * 100, 1)

                
            
            embed.add_field(name=f"**🎤 Vocal: {active_idol['vocal']}**", value=f"**🎶 Rap: {active_idol['rap']}**")
            embed.add_field(name=f"**💃 Dance: {active_idol['dance']}**", value=f"**✨ Visual: {active_idol['visual']}**")
            embed.add_field(name=f"{"🔋" if energy_percent > 60 else ":low_battery:"} Energy: {energy_percent}%", value=f"> ⚡{energy_left}/{active_idol['max_energy']}", inline=True)

            if card:
                # 🟢 Passive Skill (PS)
                if card["p_skill"]:
                    skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1 AND skill_type = 'passive'", card["p_skill"])
                    if skill:
                        passive_name = card["p_skill"].replace("_", " ").capitalize()
                        fulfilled = await apply_passive_skill_if_applicable(
                            conn, active_idol, section, presentation, check_only=True
                        )
                        p_status = "✅" if fulfilled else "❌"
                        embed.add_field(name=ps_emoji, value=f"{passive_name} {p_status}", inline=True)
                        
                # 🔵 Active Skill (AS)
                if card["a_skill"]:
                    active_name = card["a_skill"].replace("_", " ").capitalize()
                    embed.add_field(name=as_emoji, value=active_name, inline=True)
                
                # 🟡 Support Skill (SS)
                if card['s_skill']:
                    s_skill = await conn.fetchval("SELECT energy_cost FROM skills WHERE skill_name = $1", card['s_skill'])
                    support_name = card["s_skill"].replace("_", " ").capitalize()
                    can_use_support = Er >= s_skill
                    s_status = "✅" if can_use_support else "❌"
                    embed.add_field(name=ss_emoji, value=f"{support_name} {s_status}", inline=True)
                    
                # 🔴 Ultimate Skill (US)
                if card["u_skill"]:
                    ult_name = card["u_skill"].replace("_", " ").capitalize()
                    can_use_ult = active_idol["can_ult"]
                    u_status = "✅" if can_use_ult else "❌"
                    embed.add_field(name=us_emoji, value=f"{ult_name} {u_status}", inline=True)

            
        
        section_type = ""        
        if section['type_plus']:
            section_type = section['type_plus'].capitalize().replace("_"," ")
        embed2 = discord.Embed(
            title=f"Sección {section['section_number']}/{song['total_sections']} - *{section['section_type'].replace("_"," ").capitalize()}* ⏳{section['duration']}",
            description=f"> {section_type}\n{section['lyrics'].replace("\\n","\n")}",
            color=discord.Color.orange()
        )
        embed2.add_field(name=f"🎤 Vocal: {section['vocal']}", value=f"🎶 Rap: {section['rap']}")
        embed2.add_field(name=f"💃 Dance: {section['dance']}", value=f"📸 Visual: {section['visual']}")
        embed2.set_footer(text=f"⭐ Puntuación esperada: {section['average_score']}")
        
        embeds.append(embed)
        embeds.append(embed2)
        
        idols_in_group = await conn.fetch("SELECT * FROM presentation_members WHERE presentation_id = $1", presentation_id)
            
    view = discord.ui.View(timeout=120)
    
    # Obtener free_switches
    free_switches = presentation["free_switches"]
    disabled = free_switches < 0 or not idol_data
    
    if len(idols_in_group) == 1:
        disabled = False
    
    view.add_item(BasicActionButton(presentation_id, disabled=disabled))
    
    view.add_item(SwitchIdolButton(presentation_id))
    
    p_card_disabled = True
    if presentation['performance_card_uses'] > 0:
        p_card_disabled = False
    view.add_item(PerformanceCardsButton(presentation_id, disabled=p_card_disabled))
    
    # Verificar si el botón de habilidad activa debe estar habilitado
    
    disabled_active = True
    disabled_support = True
    disabled_ult = True
    async with pool.acquire() as conn:
        if active_idol and active_idol["unique_id"]:
            card = await conn.fetchrow("SELECT a_skill, u_skill, s_skill FROM user_idol_cards WHERE unique_id = $1", active_idol["unique_id"])
            if card and card["a_skill"]:
                disabled_active = False

            if card and card['s_skill']:
                if Er >= s_skill:
                    disabled_support = False
            
            if active_idol['can_ult'] and card and card["u_skill"]:
                disabled_ult = False
    
    disabled_active = disabled_active or disabled
    view.add_item(ActiveSkillPreviewButton(presentation_id, as_emoji, disabled=disabled_active))
    
    disabled_support = disabled_support or disabled
    view.add_item(SupportSkillPreviewButton(presentation_id, ss_emoji, disabled=disabled_support))

    disabled_ult = disabled_ult or disabled
    view.add_item(UltimateSkillPreviewButton(presentation_id, us_emoji, disabled=disabled_ult))


    if edit:
        await interaction.edit_original_response(content="", embeds=embeds, view=view)
    else:
        await interaction.edit_original_response(content="", embeds=embeds, view=view)

# - switch idol
class SwitchIdolView(discord.ui.View):
    def __init__(self, presentation_id: str):
        super().__init__(timeout=120)
        self.add_item(SwitchIdolButton(presentation_id))
        
class SwitchIdolButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="Switch", emoji="🔁", style=discord.ButtonStyle.secondary, row=0)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await show_idol_switch_paginator(interaction, self.presentation_id)

async def show_idol_switch_paginator(interaction: Interaction, presentation_id: str):
    pool = get_pool()
    user_id = interaction.user.id

    async with pool.acquire() as conn:
        idols = await conn.fetch("""
            SELECT * FROM presentation_members
            WHERE presentation_id = $1
            ORDER BY idol_id ASC
        """, presentation_id)

    if not idols:
        await interaction.response.send_message("❌ No hay idols en esta presentación.", ephemeral=True)
        return

    paginator = IdolSwitchPaginator(interaction, presentation_id, idols)
    await paginator.start()

class IdolSwitchPaginator:
    def __init__(self, interaction: Interaction, presentation_id: str, idols: list):
        self.interaction = interaction
        self.presentation_id = presentation_id
        self.idols = idols
        self.page = 0
        self.per_page = 3
        self.total_pages = (len(idols) + self.per_page - 1) // self.per_page

    def get_page_items(self):
        start = self.page * self.per_page
        return self.idols[start:start + self.per_page]

    async def start(self):
        await self.show_page(self.interaction)

    async def show_page(self, interaction: Interaction = None):
        view = discord.ui.View(timeout=60)
        guild = interaction.guild
        embeds = []
        
        ps_emoji = get_emoji(guild, "PassiveSkill")
        as_emoji = get_emoji(guild, "ActiveSkill")
        ss_emoji = get_emoji(guild, "SupportSkill")
        us_emoji = get_emoji(guild, "UltimateSkill")

        for idol in self.get_page_items():
            energy_left = round(idol["max_energy"] - idol["used_energy"], 1)
            energy_percent = round((energy_left / idol["max_energy"]) * 100, 1)

            pool = get_pool()
            async with pool.acquire() as conn:
                idol_data = await conn.fetchrow("SELECT name FROM idol_base WHERE idol_id = $1", idol['idol_id'])

            idol_desc = f"🧑‍🎤 Idol: {idol_data['name']} ({idol['idol_id']}) "
            
            if idol['unique_id']:
                async with pool.acquire() as conn:
                    card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", idol['unique_id'])
                    if card['p_skill']:
                        idol_desc += ps_emoji
                    if card['a_skill']:
                        idol_desc += as_emoji
                    if card['s_skill']:
                        idol_desc += ss_emoji
                    if card['u_skill']:
                        idol_desc += us_emoji
            
            embed = discord.Embed(
                title=idol_desc,
                color=discord.Color.teal()
            )
            embed.add_field(name=f"**🎤 Vocal: {idol['vocal']}**", value=f"**🎶 Rap: {idol['rap']}**")
            embed.add_field(name=f"**💃 Dance: {idol['dance']}**", value=f"**✨ Visual: {idol['visual']}**")
            embed.add_field(name=f"{"🔋" if energy_percent > 60 else ":low_battery:"} Energy: {energy_percent}%", value=f"> ⚡{energy_left}/{idol['max_energy']}", inline=True)
            embed.set_footer(text=f"⭐ Score: {idol['individual_score']}")

            if idol['card_id']:
                embed.set_thumbnail(url= f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{idol['card_id']}.webp{version}")
            
            is_active = idol["current_position"] == "active"
            view.add_item(SelectIdolToSwitchButton(
                self.presentation_id,
                idol,
                idol["idol_id"],
                disabled=is_active
            ))
            embeds.append(embed)

        if self.total_pages > 1:
            view.add_item(IdolPrevButton(self))
            view.add_item(IdolNextButton(self))

        view.add_item(CancelSwitchViewButton(self.presentation_id))
        
        if interaction:
            await interaction.response.edit_message(content="🔁 Elige al idol que deseas activar:", embeds=embeds, view=view)
        else:
            await self.interaction.edit_original_response(content="🔁 Elige al idol que deseas activar:", embeds=embeds, view=view)

    async def update_page(self, interaction: Interaction):
        await self.show_page(interaction)

class CancelSwitchViewButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.danger)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

class IdolPrevButton(discord.ui.Button):
    def __init__(self, paginator: IdolSwitchPaginator):
        super().__init__(label="◀️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: Interaction):
        self.paginator.page = (self.paginator.page - 1) % self.paginator.total_pages
        await self.paginator.update_page(interaction)

class IdolNextButton(discord.ui.Button):
    def __init__(self, paginator: IdolSwitchPaginator):
        super().__init__(label="▶️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: Interaction):
        self.paginator.page = (self.paginator.page + 1) % self.paginator.total_pages
        await self.paginator.update_page(interaction)

class SelectIdolToSwitchButton(discord.ui.Button):
    def __init__(self, presentation_id: str, idol, label_text: str, disabled: bool = False):
        super().__init__(label=label_text, style=discord.ButtonStyle.success, disabled=disabled)
        self.presentation_id = presentation_id
        self.idol = idol

    async def callback(self, interaction: Interaction):
        pool = get_pool()
        guild = interaction.guild
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            current_active = await conn.fetchval("""
                SELECT idol_id FROM presentation_members
                WHERE presentation_id = $1 AND current_position = 'active'
            """, self.presentation_id)

            if self.idol['idol_id'] == current_active:
                embed = discord.Embed(
                    title="❌ Idol ya activo",
                    description="Este idol ya está en posición activa.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(
                    embed=embed,
                    view=ReturnToSectionView(self.presentation_id),
                    ephemeral=True
                )

            pres = await conn.fetchrow("""
                SELECT free_switches FROM presentations
                WHERE presentation_id = $1
            """, self.presentation_id)
            
            idol_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", self.idol['idol_id'])

        if not pres:
            await interaction.response.edit_message(content="❌ Presentación no encontrada.", view=None)
            return

        free = pres["free_switches"]
        energy_cost_info = (
            "🔁 Este cambio costará ⚡5 de energía a ambos idols."
            if free == 0 else "🔁 Este cambio será gratuito."
        )
        
        embed = discord.Embed(
            title=f"¿Deseas colocar a `{idol_name}` como idol principal en esta sección?",
            description=f"",
            color=discord.Color.yellow()
        )
        
        if self.idol['unique_id']:
            async with pool.acquire() as conn:
                card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", self.idol['unique_id'])
                if card['p_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['p_skill'])
                    condition_values = json.loads(skill_data['condition_values'])
                    condition_params = json.loads(skill_data['condition_params'])
                    
                    pcond_score=condition_params.get('score')
                    pcond_score = int(round(pcond_score-1,2)*100) if pcond_score else None
                    pcond_hype=condition_params.get('hype')
                    pcond_hype = int(round(pcond_hype-1,2)*100) if pcond_hype else None
                    cond_energy=condition_values.get("energy")
                    cond_energy = int((cond_energy)*100) if cond_energy else None
                    pcond_extra_cost = condition_params.get("energy")
                    pcond_relative_cost = condition_params.get("energy")
                    pcond_relative_cost = int(round(pcond_relative_cost-1,2)*100) if pcond_relative_cost else None
                    
                    embed.add_field(name=f"**{get_emoji(guild, "PassiveSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                          f"skills.{skill_data['skill_name']}",
                                                          cond_vocal = condition_values.get("vocal"),
                                                          cond_rap = condition_values.get("rap"),
                                                          cond_dance = condition_values.get("dance"),
                                                          cond_visual = condition_values.get("visual"),
                                                          cond_energy = cond_energy,
                                                          cond_stat = condition_values.get("stat"),
                                                          cond_hype = condition_values.get("hype"),
                                                          cond_duration = condition_values.get("duration"),
                                                          pcond_vocal = condition_params.get("vocal"),
                                                          pcond_rap = condition_params.get("rap"),
                                                          pcond_dance = condition_params.get("dance"),
                                                          pcond_visual = condition_params.get("visual"),
                                                          pcond_hype = pcond_hype,
                                                          pcond_score = pcond_score,
                                                          pcond_extra_cost = pcond_extra_cost,
                                                          pcond_relative_cost = pcond_relative_cost,
                                                          pcond_value = condition_params.get("value")
                                                          ))
                if card['a_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['a_skill'])
                    condition_values = json.loads(skill_data['condition_values'])
                    condition_params = json.loads(skill_data['condition_params'])
                    eff_params = json.loads(skill_data['params'])
                    eff = skill_data['effect']
                    cost_type = skill_data['cost_type']
                    lower = higher = relative_cost = extra_cost = ""
                    
                    pcond_energy = condition_params.get("energy")
                    if pcond_energy:
                        pcond_energy *= -1
                    
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = int(round(hype-1,2)*100) if hype else None
                    
                    pcond_score=condition_params.get('score')
                    pcond_score = int(round(pcond_score-1,2)*100) if pcond_score else None
                    pcond_hype=condition_params.get('hype')
                    pcond_hype = int(round(pcond_hype-1,2)*100) if pcond_hype else None
                    cond_energy=condition_values.get("energy")
                    cond_energy = int((cond_energy)*100) if cond_energy else None
                    
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = skill_data['energy_cost']
                    if eff == "boost_lower_stat":
                        lower = eff_params.get("value")
                    if eff == "boost_higher_stat":
                        higher = eff_params.get("value")
                    embed.add_field(name=f"**{get_emoji(guild, "ActiveSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                          f"skills.{skill_data['skill_name']}",
                                                          cond_vocal = condition_values.get("vocal"),
                                                          cond_rap = condition_values.get("rap"),
                                                          cond_dance = condition_values.get("dance"),
                                                          cond_visual = condition_values.get("visual"),
                                                          cond_energy = cond_energy,
                                                          cond_stat = condition_values.get("stat"),
                                                          cond_hype = condition_values.get("hype"),
                                                          cond_duration = condition_values.get("duration"),
                                                          pcond_vocal = condition_params.get("vocal"),
                                                          pcond_rap = condition_params.get("rap"),
                                                          pcond_dance = condition_params.get("dance"),
                                                          pcond_visual = condition_params.get("visual"),
                                                          pcond_energy = pcond_energy,
                                                          pcond_hype = pcond_hype,
                                                          pcond_score = pcond_score,
                                                          pcond_extra_cost = condition_params.get("energy"),
                                                          pcond_value = condition_params.get("value"),
                                                          higher=higher, lower=lower,
                                                          vocal=eff_params.get("vocal"),
                                                          rap=eff_params.get("rap"),
                                                          dance=eff_params.get('dance'),
                                                          visual=eff_params.get('visual'),
                                                          score=score,
                                                          hype=hype,
                                                          relative_cost=relative_cost,
                                                          extra_cost=extra_cost,
                                                          ))
                if card['s_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['s_skill'])
                    effect_data = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", skill_data['effect_id'])
                    if effect_data['hype_mod']:
                        hype = int(round(effect_data['hype_mod']-1,2)*100)
                    if effect_data['score_mod']:
                        score = int(round(effect_data['score_mod']-1,2)*100)
                    if effect_data['relative_cost']:
                        relative = int(round(effect_data['relative_cost']-1,2)*100) 
                    embed.add_field(name=f"**{get_emoji(guild, "SupportSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                          f"skills.{skill_data['skill_name']}",
                                                          duration=skill_data['duration'], energy_cost=int(skill_data['energy_cost']),
                                                          highest = effect_data['highest_stat_mod'], lowest = effect_data['lowest_stat_mod'],
                                                          vocal = effect_data['plus_vocal'], rap = effect_data['plus_rap'],
                                                          dance = effect_data['plus_dance'], visual = effect_data['plus_visual'],
                                                          hype = hype, score = score,
                                                          extra_cost = effect_data['extra_cost'], relative_coost = relative
                                                          ))
                if card['u_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['u_skill'])
                    cost_type = skill_data['cost_type']
                    eff_params = json.loads(skill_data['params'])
                    lower = higher = relative_cost = extra_cost = ""
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = int(skill_data['energy_cost'] * -1)
                        
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = (int(round(hype-1,2)*100)) if hype else None
                    
                    embed.add_field(name=f"**{get_emoji(guild, "UltimateSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                          f"skills.{skill_data['skill_name']}",
                                                          higher=higher, lower=lower,
                                                          vocal=eff_params.get("vocal"),
                                                          rap=eff_params.get("rap"),
                                                          dance=eff_params.get('dance'),
                                                          visual=eff_params.get('visual'),
                                                          score=score,
                                                          hype=hype,
                                                          value=eff_params.get('value'),
                                                          relative_cost=relative_cost,
                                                          extra_cost=extra_cost,
                                                          ))
                    
        embed.set_footer(text=energy_cost_info)

        view = ConfirmSwitchIdolView(self.presentation_id, self.idol['idol_id'], free)
        await interaction.response.edit_message(embed=embed, view=view, content="")

class ConfirmSwitchIdolView(ui.View):
    def __init__(self, presentation_id: str, new_idol_id: str, free_switches: int):
        super().__init__(timeout=60)
        self.presentation_id = presentation_id
        self.new_idol_id = new_idol_id
        self.free_switches = free_switches

    @ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        user_id = interaction.user.id
        pool = get_pool()

        async with pool.acquire() as conn:
            # Obtener actual activo (si hay)
            old_active = await conn.fetchrow("""
                SELECT idol_id FROM presentation_members
                WHERE presentation_id = $1 AND current_position = 'active'
            """, self.presentation_id)

            # Actualizar posiciones
            await conn.execute("""
                UPDATE presentation_members
                SET current_position = 'back'
                WHERE presentation_id = $1 AND current_position = 'active'
            """, self.presentation_id)

            await conn.execute("""
                UPDATE presentation_members
                SET current_position = 'active'
                WHERE presentation_id = $1 AND idol_id = $2
            """, self.presentation_id, self.new_idol_id)

            # Aplicar costo si no hay free switches
            if self.free_switches == 0:
                idols_to_update = [self.new_idol_id]
                if old_active:
                    idols_to_update.append(old_active["idol_id"])

                for idol in idols_to_update:
                    await conn.execute("""
                        UPDATE presentation_members
                        SET used_energy = used_energy + 5
                        WHERE presentation_id = $1 AND idol_id = $2
                    """, self.presentation_id, idol)

            # Si había free_switches, no se descuentan
            await conn.execute("""
                UPDATE presentations
                SET free_switches = free_switches - 1
                WHERE presentation_id = $1 AND free_switches > 0
            """, self.presentation_id)
            await conn.execute("""
                UPDATE presentations
                SET free_switches = free_switches + 1
                WHERE presentation_id = $1 AND free_switches < 0
            """, self.presentation_id)

        # Volver a la pantalla principal
        await show_current_section_view(interaction, self.presentation_id, edit=True)

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

# - Performance Cards
class PerformanceCardsButton(discord.ui.Button):
    def __init__(self, presentation_id: str, disabled: bool):
        super().__init__(label="P. Cards", emoji="🎭", style=discord.ButtonStyle.secondary, row=0, disabled=disabled)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=120)
        view.add_item(ReinforcementCardsButton(self.presentation_id))
        view.add_item(StageCardsButton(self.presentation_id))
        view.add_item(PerformanceCardsCancelButton(self.presentation_id))

        await interaction.response.edit_message(content="Selecciona el tipo de Performance Card:", view=view, embed=None)

class ReinforcementCardsButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="🎯 Reinforcement", style=discord.ButtonStyle.secondary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await show_performance_cards_by_type(interaction, self.presentation_id, "reinforcement")

class StageCardsButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="🎇 Stage Effects", style=discord.ButtonStyle.secondary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await show_performance_cards_by_type(interaction, self.presentation_id, "stage")

class PerformanceCardsCancelButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="", emoji="🔙", style=discord.ButtonStyle.danger, row=1)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

async def show_performance_cards_by_type(interaction: discord.Interaction, presentation_id: str, card_type: str):
    user_id = interaction.user.id
    language = await get_user_language(user_id)
    pool = get_pool()

    async with pool.acquire() as conn:
        if card_type == "reinforcement":
            rows = await conn.fetch("""
                SELECT up.pcard_id, up.quantity, cp.name
                FROM user_performance_cards up
                JOIN cards_performance cp ON up.pcard_id = cp.pcard_id
                WHERE up.user_id = $1 AND cp.pcard_id LIKE 'RNFRC%' AND up.quantity > 0
                ORDER BY cp.pcard_id ASC
            """, user_id)
        else:  # stage
            rows = await conn.fetch("""
                SELECT up.pcard_id, up.quantity, cp.name, cp.effect, cp.duration
                FROM user_performance_cards up
                JOIN cards_performance cp ON up.pcard_id = cp.pcard_id
                WHERE up.user_id = $1 AND cp.pcard_id LIKE 'STAGE%' AND up.quantity > 0
                ORDER BY cp.pcard_id ASC
            """, user_id)

    if not rows:
        await interaction.response.edit_message(content=f"No tienes cartas de tipo {card_type.title()}.", view=None, embed=None)
        return

    pages = [rows[i:i+4] for i in range(0, len(rows), 4)]
    await send_performance_card_page(interaction, presentation_id, pages, 0, card_type, language)

async def send_performance_card_page(interaction, presentation_id, pages, page_index, card_type, language):
    pool = get_pool()
    total = len(pages)
    current_rows = pages[page_index]
    embed = discord.Embed(
        title=f"{'🎯' if card_type == 'reinforcement' else '🎇'} Cartas: {card_type.title()}",
        description=f"Página {page_index + 1} de {len(pages)}",
        color=discord.Color.blue()
    )

    view = discord.ui.View(timeout=120)
    for row in current_rows:
        pcard_id = row["pcard_id"]
        name = row["name"]
        quantity = row["quantity"]

        vocal = rap = dance = visual = hype = score = extra_cost = relative_cost = duration = None

        if card_type == "stage":
            async with pool.acquire() as conn:
                effect_id = row["effect"]
                perf = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", effect_id)
                if perf:
                    vocal = perf["plus_vocal"]
                    rap = perf["plus_rap"]
                    dance = perf["plus_dance"]
                    visual = perf["plus_visual"]
                    hype = int((perf["hype_mod"] - 1) * 100)
                    score = int((perf["score_mod"] - 1) * 100)
                    extra_cost = perf["extra_cost"]
                    relative_cost = int((perf["relative_cost"] - 1) * 100)
                    duration = row["duration"]

        embed.add_field(
            name=f"**{name}** (x{quantity})",
            value=f"> {get_translation(language, f'inventory_description.{pcard_id}', vocal=vocal, rap=rap, dance=dance, visual=visual, hype=hype, score=score, extra_cost=extra_cost, relative_cost=relative_cost, duration=duration)}",
            inline=False
        )
        # Obtener el nombre de la carta
        async with pool.acquire() as conn:
            card_name_row = await conn.fetchrow(
                "SELECT name FROM cards_performance WHERE pcard_id = $1",
                pcard_id
            )
        card_name = card_name_row['name'] if card_name_row else pcard_id

        # Agregar botón con el nombre real
        view.add_item(PerformanceCardPreviewButton(presentation_id, pcard_id, card_type, label=card_name))

    # Navegación
    prev_index = (page_index - 1) % total
    next_index = (page_index + 1) % total

    view.add_item(
        PerformanceCardPageButton(
            presentation_id,
            pages,
            prev_index,
            card_type,
            language,
            "⏪"
        )
    )
    view.add_item(
        PerformanceCardPageButton(
            presentation_id,
            pages,
            next_index,
            card_type,
            language,
            "⏩"
        )
    )

    view.add_item(PerformanceCardsCancelButton(presentation_id))
    await interaction.response.edit_message(embed=embed, view=view)

class PerformanceCardPageButton(discord.ui.Button):
    def __init__(self, presentation_id: str, pages: list, new_index: int, card_type: str, language: str, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=1)
        self.presentation_id = presentation_id
        self.pages = pages
        self.new_index = new_index
        self.card_type = card_type
        self.language = language

    async def callback(self, interaction: discord.Interaction):
        await send_performance_card_page(
            interaction=interaction,
            presentation_id=self.presentation_id,
            pages=self.pages,
            page_index=self.new_index,
            card_type=self.card_type,
            language=self.language
        )

class PerformanceCardPreviewButton(discord.ui.Button):
    def __init__(self, presentation_id: str, card_id: str, card_type: str, label: str):
        super().__init__(label=label, emoji="🎴", style=discord.ButtonStyle.success, row=0)
        self.presentation_id = presentation_id
        self.card_id = card_id
        self.card_type = card_type

    async def callback(self, interaction: discord.Interaction):
        # Placeholder para embed descriptivo
        embed = discord.Embed(
            title="Vista previa de carta",
            description=f"🔍 Carta: `{self.card_id}`\nTipo: `{self.card_type}`\n¿Deseas usarla?",
            color=discord.Color.gold()
        )

        view = discord.ui.View(timeout=60)
        view.add_item(ConfirmUsePerformanceCardButton(self.presentation_id, self.card_id, self.card_type))
        view.add_item(CancelPerformanceCardPreviewButton(self.presentation_id))

        await interaction.response.edit_message(embed=embed, view=view)

class ConfirmUsePerformanceCardButton(discord.ui.Button):
    def __init__(self, presentation_id: str, pcard_id: str, card_type: str):
        super().__init__(label="Usar", emoji="✅", style=discord.ButtonStyle.success)
        self.presentation_id = presentation_id
        self.pcard_id = pcard_id
        self.card_type = card_type

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        pool = get_pool()

        async with pool.acquire() as conn:
            presentation = await conn.fetchrow("SELECT * FROM presentations WHERE presentation_id = $1 AND user_id = $2", self.presentation_id, user_id)
            if not presentation:
                await interaction.edit_original_response(content="❌ No se encontró la presentación.")
                return

            # Verificar usos disponibles
            if presentation["performance_card_uses"] <= 0:
                await interaction.edit_original_response(content="❌ Ya has usado el máximo de cartas de performance en esta sección.")
                return

            # Verificar si el usuario tiene la carta
            user_card = await conn.fetchrow(
                "SELECT quantity FROM user_performance_cards WHERE user_id = $1 AND pcard_id = $2",
                user_id, self.pcard_id
            )
            if not user_card or user_card["quantity"] <= 0:
                await interaction.edit_original_response(content="❌ No tienes esta carta disponible.")
                return

            # Obtener detalles de la carta
            card = await conn.fetchrow("SELECT * FROM cards_performance WHERE pcard_id = $1", self.pcard_id)
            if not card:
                await interaction.edit_original_response(content="❌ No se encontró información sobre esta carta.")
                return

            if self.card_type == "stage":
                # Aplicar stage effect directamente
                await conn.execute("""
                    UPDATE presentations
                    SET stage_effect = $1,
                        stage_effect_duration = $2,
                        used_stage = TRUE,
                        performance_card_uses = performance_card_uses - 1
                    WHERE presentation_id = $3
                """, card["effect"], card["duration"], self.presentation_id)

                await conn.execute("""
                    UPDATE user_performance_cards
                    SET quantity = quantity - 1
                    WHERE user_id = $1 AND pcard_id = $2
                """, user_id, self.pcard_id)

                await show_current_section_view(interaction, self.presentation_id, edit=True)
                return

            elif self.card_type == "reinforcement":
                effect = card["effect"]

                # Marcamos como usada y descontamos 1 por adelantado
                await conn.execute("""
                    UPDATE presentations
                    SET used_reinforcement = TRUE
                    WHERE presentation_id = $1
                """, self.presentation_id)

                # Usos especiales que terminan aquí
                if effect == "group_recovery":
                    await conn.execute("""
                        UPDATE presentation_members
                        SET used_energy = GREATEST(0, used_energy - 5)
                        WHERE presentation_id = $1
                    """, self.presentation_id)

                elif effect == "cooldown_cut":
                    await conn.execute("""
                        UPDATE presentations
                        SET performance_card_uses = performance_card_uses + 2,
                            stage_effect_duration = GREATEST(0, stage_effect_duration - 1),
                            support_effect_duration = GREATEST(0, support_effect_duration - 1)
                        WHERE presentation_id = $1
                    """, self.presentation_id)

                elif effect == "lead_switch":
                    await conn.execute("""
                        UPDATE presentations
                        SET free_switches = free_switches + 1
                        WHERE presentation_id = $1
                    """, self.presentation_id)

                elif effect == "stat_shuffle":
                    section = await conn.fetchrow("""
                        SELECT * FROM presentation_sections
                        WHERE presentation_id = $1
                        ORDER BY section DESC LIMIT 1
                    """, self.presentation_id)
                    if section:
                        fields = ["plus_vocal", "plus_rap", "plus_dance", "plus_visual"]
                        inc, dec = random.sample(fields, 2)
                        await conn.execute(f"""
                            UPDATE presentation_sections
                            SET {inc} = COALESCE({inc}, 0) + 10,
                                {dec} = COALESCE({dec}, 0) - 10
                            WHERE presentation_id = $1 AND section = $2
                        """, self.presentation_id, section["section"])

                elif effect in ["group_dance", "cheering"]:
                    await conn.execute("""
                        UPDATE presentation_members
                        SET current_position = 'grupal', p_type = $1
                        WHERE presentation_id = $2 AND current_position <> 'active'
                    """, effect, self.presentation_id)

                elif effect in ["duet", "high_note", "backup_dance", "harmony", "backup_rap", "adlib", "pose_sync"]:
                    pool = get_pool()
                    async with pool.acquire() as conn:
                        idols = await conn.fetch("""
                            SELECT pm.*, ib.name FROM presentation_members pm
                            JOIN idol_base ib ON pm.idol_id = ib.idol_id
                            WHERE pm.presentation_id = $1
                            ORDER BY pm.id ASC
                        """, self.presentation_id)

                    p = PerformanceIdolPaginator(
                        interaction=interaction,
                        presentation_id=self.presentation_id,
                        pcard_id=self.pcard_id,
                        effect=effect,
                        allow_active=(effect=='solo_recovery'),
                        idols=list(idols),
                        idols_per_page=3
                    )
                    await p.start()
                    return

                elif effect == "solo_recovery":
                    pool = get_pool()
                    async with pool.acquire() as conn:
                        idols = await conn.fetch("""
                            SELECT pm.*, ib.name FROM presentation_members pm
                            JOIN idol_base ib ON pm.idol_id = ib.idol_id
                            WHERE pm.presentation_id = $1
                            ORDER BY pm.id ASC
                        """, self.presentation_id)
                    p = PerformanceIdolPaginator(
                        interaction=interaction,
                        presentation_id=self.presentation_id,
                        pcard_id=self.pcard_id,
                        effect=effect,
                        allow_active=(effect=='solo_recovery'),
                        idols=list(idols),
                        idols_per_page=3
                    )
                    await p.start()
                    return

                # Si no requirió vista, se descuenta cantidad y uso
                await conn.execute("""
                    UPDATE presentations
                    SET performance_card_uses = performance_card_uses - 1
                    WHERE presentation_id = $1
                """, self.presentation_id)

                await conn.execute("""
                    UPDATE user_performance_cards
                    SET quantity = quantity - 1
                    WHERE user_id = $1 AND pcard_id = $2
                """, user_id, self.pcard_id)

                await show_current_section_view(interaction, self.presentation_id, edit=True)
                return

        # Seguridad final (no debería llegar aquí)
        await interaction.edit_original_response(content="❌ Acción no reconocida.")


class PerformanceIdolPaginator:
    def __init__(
        self,
        interaction: discord.Interaction,
        presentation_id: str,
        pcard_id: str,
        effect: str,
        allow_active: bool,
        idols: list[dict],
        idols_per_page: int = 3
    ):
        self.interaction = interaction
        self.presentation_id = presentation_id
        self.pcard_id = pcard_id
        self.effect = effect
        self.allow_active = allow_active
        self.idols = idols
        self.idols_per_page = idols_per_page

        self.current_page = 0
        self.total_pages = (len(idols) + idols_per_page - 1) // idols_per_page

    def get_page_idols(self):
        start = self.current_page * self.idols_per_page
        end = start + self.idols_per_page
        return self.idols[start:end]

    def build_view(self):
        view = discord.ui.View(timeout=120)
        # Botones de selección para cada ídol de esta página
        for idol in self.get_page_idols():
            label = f"{idol['name']} ({idol['idol_id']})"
            disabled = (idol["current_position"] == "active" and not self.allow_active)
            view.add_item(
                ChooseIdolForPerformanceCardButton(
                    presentation_id=self.presentation_id,
                    pcard_id=self.pcard_id,
                    effect=self.effect,
                    idol_id=idol["id"],
                    label=label,
                    disabled=disabled
                )
            )

        # Navegación
        if self.total_pages > 1:
            view.add_item(
                PerformancePrevButton(self)
            )
            view.add_item(
                PerformanceNextButton(self)
            )

        # Cancelar
        view.add_item(
            CancelPerformanceCardPreviewButton(self.presentation_id)
        )
        return view

    def build_embeds(self):
        embeds = []
        page_idols = self.get_page_idols()
        for idol in page_idols:
            embed = discord.Embed(
                title=f"🎤 {idol['name']} ({idol['idol_id']})",
                description=f"Posición: `{idol['current_position']}`",
                color=discord.Color.green()
            )
            # Stats
            embed.add_field(
                name="Stats",
                value=(
                    f"🎶 Vocal: {idol['vocal']}\n"
                    f"🎤 Rap: {idol['rap']}\n"
                    f"💃 Dance: {idol['dance']}\n"
                    f"📸 Visual: {idol['visual']}"
                ),
                inline=False
            )
            # energy %
            energy_left = idol['max_energy'] - idol['used_energy']
            energy_pct = round((energy_left / idol['max_energy']) * 100, 1)
            embed.add_field(
                name="⚡ Energy",
                value=f"{energy_left}/{idol['max_energy']} ({energy_pct}%)",
                inline=False
            )
            embed.set_footer(
                text=(
                    f"Ídol {self.current_page * self.idols_per_page + page_idols.index(idol)+1}"
                    f" de {len(self.idols)} • Página {self.current_page+1}/{self.total_pages}"
                )
            )
            # miniatura
            if idol.get('card_id'):
                embed.set_thumbnail(
                    url=f"https://res.cloudinary.com/.../{idol['card_id']}.webp"
                )
            embeds.append(embed)
        return embeds

    async def start(self):
        embeds = self.build_embeds()
        view = self.build_view()
        await self.interaction.edit_original_response(
            content="🔁 Elige un ídol para aplicar la carta:",
            embeds=embeds,
            view=view
        )

    async def update(self, interaction: discord.Interaction):
        embeds = self.build_embeds()
        view = self.build_view()
        await interaction.response.edit_message(embeds=embeds, view=view)

class PerformancePrevButton(discord.ui.Button):
    def __init__(self, paginator: PerformanceIdolPaginator):
        super().__init__(label="⏪", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page - 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class PerformanceNextButton(discord.ui.Button):
    def __init__(self, paginator: PerformanceIdolPaginator):
        super().__init__(label="⏩", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page + 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class ChooseIdolForPerformanceCardView(discord.ui.View):
    def __init__(self, presentation_id: str, pcard_id: str, effect: str, allow_active: bool, idols: list, page_index: int = 0, idols_per_page: int = 3):
        super().__init__(timeout=120)
        self.presentation_id = presentation_id
        self.pcard_id = pcard_id
        self.effect = effect
        self.allow_active = allow_active
        self.idols = idols  # lista de dicts con info de cada idol
        self.page_index = page_index
        self.idols_per_page = idols_per_page

        self.build_buttons()

    def build_buttons(self):
        self.clear_items()

        # calculamos el slice de ídols a mostrar en esta página
        start = self.page_index * self.idols_per_page
        end = start + self.idols_per_page
        page_idols = self.idols[start:end]

        # fila 1: hasta 3 botones de idols
        for idol in page_idols:
            label = f"{idol['name']} ({idol['idol_id']})"
            disabled = (idol["current_position"] == "active" and not self.allow_active)
            self.add_item(
                ChooseIdolForPerformanceCardButton(
                    presentation_id=self.presentation_id,
                    pcard_id=self.pcard_id,
                    effect=self.effect,
                    idol_id=idol["id"],  # id en presentation_members
                    label=label,
                    disabled=disabled
                )
            )

        # fila 2: botones de paginación
        # “<<” volver a página anterior
        if self.page_index > 0:
            self.add_item(
                ChooseIdolForPerformanceCardPageButton(
                    view=self,
                    new_index=self.page_index - 1,
                    label="⏪",
                )
            )

        # “>>” ir a la siguiente página
        if end < len(self.idols):
            self.add_item(
                ChooseIdolForPerformanceCardPageButton(
                    view=self,
                    new_index=self.page_index + 1,
                    label="⏩",
                )
            )

        # boton cancelar
        self.add_item(
            CancelPerformanceCardPreviewButton(
                presentation_id=self.presentation_id
            )
        )


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        pool = get_pool()
        async with pool.acquire() as conn:
            presentation = await conn.fetchrow("SELECT * FROM presentations WHERE presentation_id = $1", self.presentation_id)
            return presentation and presentation["user_id"] == interaction.user.id

    async def send(self, interaction: discord.Interaction):
        # construimos el embed de la página actual
        start = self.page_index * self.idols_per_page
        end = start + self.idols_per_page
        page_idols = self.idols[start:end]

        desc_lines = []
        for idol in page_idols:
            desc_lines.append(
                f"**{idol['name']}** ({idol['idol_id']}) — Posición: `{idol['current_position']}`"
            )
        description = "\n".join(desc_lines)

        embed = discord.Embed(
            title="🎤 Elige un idol",
            description=description,
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Página {self.page_index+1} de {math.ceil(len(self.idols)/self.idols_per_page)}")

        # reconstruimos los botones
        self.build_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

class ChooseIdolForPerformanceCardPageButton(discord.ui.Button):
    def __init__(self, view: ChooseIdolForPerformanceCardView, new_index: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=2)
        self.view_data = view
        self.new_index = new_index

    async def callback(self, interaction: discord.Interaction):
        new_view = ChooseIdolForPerformanceCardView(
            presentation_id=self.view_data.presentation_id,
            pcard_id=self.view_data.pcard_id,
            effect=self.view_data.effect,
            allow_active=self.view_data.allow_active,
            idols=self.view_data.idols,
            page_index=self.new_index
        )
        await new_view.send(interaction)

class ChooseIdolForPerformanceCardButton(discord.ui.Button):
    def __init__(
        self,
        presentation_id: str,
        pcard_id: str,
        effect: str,
        idol_id: str,
        label: str,
        disabled: bool
    ):
        super().__init__(label=label, style=discord.ButtonStyle.primary, disabled=disabled)
        self.presentation_id = presentation_id
        self.pcard_id = pcard_id
        self.effect = effect
        self.idol_id = idol_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        pool = get_pool()

        async with pool.acquire() as conn:
            # Validar que todavía tiene la carta
            has_card = await conn.fetchval("""
                SELECT quantity FROM user_performance_cards
                WHERE user_id = $1 AND pcard_id = $2
            """, user_id, self.pcard_id)

            if not has_card or has_card <= 0:
                await interaction.response.edit_message(content="❌ Ya no tienes esta carta disponible.", view=None)
                return

            # Aplicar efecto según tipo
            if self.effect == "solo_recovery":
                await conn.execute("""
                    UPDATE presentation_members
                    SET used_energy = GREATEST(0, used_energy - 15)
                    WHERE id = $1
                """, self.idol_id)

            elif self.effect in ["duet", "high_note", "backup_dance", "harmony", "backup_rap", "adlib", "pose_sync"]:
                await conn.execute("""
                    UPDATE presentation_members
                    SET current_position = 'participated', p_type = $1
                    WHERE id = $2
                """, self.effect, self.idol_id)

            # Marcar uso de carta y descontar cantidad
            await conn.execute("""
                UPDATE presentations
                SET performance_card_uses = performance_card_uses - 1
                WHERE presentation_id = $1
            """, self.presentation_id)

            await conn.execute("""
                UPDATE user_performance_cards
                SET quantity = quantity - 1
                WHERE user_id = $1 AND pcard_id = $2
            """, user_id, self.pcard_id)

            await show_current_section_view(interaction, self.presentation_id, edit=True)

class CancelPerformanceCardPreviewButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="Cancelar", emoji="🔙", style=discord.ButtonStyle.secondary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)


# - Funcion reutilizable para calculo de valores, stats, score, hype, etc
async def perform_section_action(conn, presentation_id: str, idol_row, song_section, presentation_row, skill_bonus: dict):
    current_section = presentation_row["current_section"]
    song_id = presentation_row["song_id"]

    Vs, Rs, Ds, Ls = song_section["vocal"], song_section["rap"], song_section["dance"], song_section["visual"]
    Vc, Rc, Dc, Lc = idol_row["vocal"], idol_row["rap"], idol_row["dance"], idol_row["visual"]
    
    members = await conn.fetch(
        "SELECT * FROM presentation_members WHERE presentation_id = $1 AND current_position <> 'back' AND current_position <> 'active'",
        presentation_id
    )
    
    section_bonus_applied = False
    for m in members:
        if m['current_position'] == 'participated':
            Vc += m['vocal'] * 0.4
            Rc += m['rap'] * 0.4
            Dc += m['dance'] * 0.4
            Lc += m['visual'] * 0.4
        elif m['current_position'] == 'grupal':
            Vc += m['vocal'] * 0.1
            Rc += m['rap'] * 0.1
            Dc += m['dance'] * 0.1
            Lc += m['visual'] * 0.1
        
        if not section_bonus_applied and m['p_type'] == song_section['type_plus']:
            Vs += song_section['plus_vocal']
            Rs += song_section['plus_rap'] 
            Ds += song_section['plus_dance'] 
            Ls += song_section['plus_visual']
            section_bonus_applied = True
    
    Vc = int(Vc)
    Rc = int(Rc)
    Dc = int(Dc)
    Lc = int(Lc)
    
    # Overrides por ultimate
    if "override_stat" in skill_bonus:
        for stat, val in skill_bonus["override_stat"].items():
            if stat == "vocal":
                Vs = val
            elif stat == "rap":
                Rs = val
            elif stat == "dance":
                Ds = val
            elif stat == "visual":
                Ls = val
    Vc += skill_bonus.get('vocal', 0)
    Rc += skill_bonus.get('rap', 0)
    Dc += skill_bonus.get("dance", 0)
    Lc += skill_bonus.get("visual", 0)

    duration = song_section["duration"]
    
    restante = max(0, round((idol_row["max_energy"] - idol_row["used_energy"]) / idol_row["max_energy"], 2))
    if skill_bonus.get("override_energy") == "inverse":
        restante = 1 - restante
    if skill_bonus.get("override_energy") == "fixed":
        Er = 1
    else:
        Er = 0.3 + restante * 0.7


    # Stage y Support effects
    effect = None
    if presentation_row["stage_effect"] and presentation_row["stage_effect_duration"] > 0:
        effect = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", presentation_row["stage_effect"])

    s_effect = None
    if presentation_row["support_effect"] and presentation_row["support_effect_duration"] > 0:
        s_effect = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", presentation_row["support_effect"])

    for ef in (effect, s_effect):
        if ef:
            Vs += ef["plus_vocal"]
            Rs += ef["plus_rap"]
            Ds += ef["plus_dance"]
            Ls += ef["plus_visual"]

            stats_section = [("vocal", Vs), ("rap", Rs), ("dance", Ds), ("visual", Ls)]
            if ef["highest_stat_mod"]:
                highest = max(stats_section, key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))
                locals()[f"{highest[0][0].upper()}s"] += ef["highest_stat_mod"]

            if ef["lowest_stat_mod"]:
                lowest = min(stats_section, key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))
                locals()[f"{lowest[0][0].upper()}s"] += ef["lowest_stat_mod"]
    
    H = presentation_row["total_hype"]
    Ph = min(1.2, max(0.8, ((0.4 * H) - 20) / 100 + 1))

    base_energy_cost = duration
    if effect:
        base_energy_cost += effect["extra_cost"]
        base_energy_cost *= effect["relative_cost"]
    if s_effect:
        base_energy_cost += s_effect["extra_cost"]
        base_energy_cost *= s_effect["relative_cost"]

    
    base_energy_cost += skill_bonus.get("extra_cost", 0)
    base_energy_cost *= skill_bonus.get("relative_cost", 1)
    base_energy_cost = round(base_energy_cost,2)
    
    new_used_energy = min(idol_row["max_energy"], idol_row["used_energy"] + base_energy_cost)

    base_score = ((Vc * Vs) + (Rc * Rs) + (Dc * Ds) + (Lc * Ls)) * duration * Er * Ph
    
    base_score *= skill_bonus.get("score", 1)
    if effect: base_score *= effect["score_mod"]
    if s_effect: base_score *= s_effect["score_mod"]
    base_score = int(base_score)

    await conn.execute("""
        INSERT INTO presentation_sections (presentation_id, section, score_got, active_card_id)
        VALUES ($1, $2, $3, $4)
    """, presentation_id, current_section, base_score, idol_row["card_id"])

    await conn.execute("""
        UPDATE presentations SET total_score = total_score + $1 WHERE presentation_id = $2
    """, base_score, presentation_id)

    # Set score to active idol
    await conn.execute("""
        UPDATE presentation_members SET individual_score = individual_score + $1
        WHERE id = $2
    """, base_score, idol_row["id"])

    # Energy consume and regeneration
    await conn.execute("""
        UPDATE presentation_members SET used_energy = used_energy + $1
        WHERE presentation_id = $2 AND current_position <> 'back'
    """, base_energy_cost, presentation_id)

    await conn.execute("""
        UPDATE presentation_members SET used_energy = used_energy - $1
        WHERE presentation_id = $2 AND current_position = 'back'
    """, base_energy_cost * 0.1, presentation_id)

    # Set last positions according to last current positions
    await conn.execute("""
        UPDATE presentation_members SET current_position = 'back', last_position = 'participated'
        WHERE presentation_id = $1 AND current_position = 'participated'
    """, presentation_id)
    
    await conn.execute("""
        UPDATE presentation_members SET current_position = 'back', last_position = 'participated'
        WHERE presentation_id = $1 AND current_position = 'grupal'
    """, presentation_id)

    await conn.execute("""
        UPDATE presentation_members SET last_position = 'active'
        WHERE presentation_id = $1 AND current_position = 'active'
    """, presentation_id)

    await conn.execute("""
        UPDATE presentation_members SET last_position = 'back'
        WHERE presentation_id = $1 AND current_position = 'back'
    """, presentation_id)
    
    # Restore p_type to None
    await conn.execute("""
        UPDATE presentation_members SET p_type = $1
        WHERE presentation_id = $2
    """, None, presentation_id)

    # Set max/min energy
    await conn.execute("UPDATE presentation_members SET used_energy = max_energy WHERE presentation_id = $1 AND used_energy > max_energy", presentation_id)
    await conn.execute("UPDATE presentation_members SET used_energy = 0 WHERE presentation_id = $1 AND used_energy < 0", presentation_id)

    n_members = await conn.fetchval("SELECT COUNT(*) FROM presentation_members WHERE presentation_id = $1", presentation_id)
    avg = await conn.fetchval("SELECT average_score FROM song_sections WHERE song_id = $1 AND section_number = $2", song_id, current_section)
    base_hype = avg * (1 + 0.001 * n_members * ((n_members + 1) / 2))
    Hg = round((1 - base_hype / base_score) * 5 * skill_bonus.get("hype", 1), 2)
    if effect: Hg *= effect["hype_mod"]
    if s_effect: Hg *= s_effect["hype_mod"]

    await conn.execute("UPDATE presentations SET total_hype = LEAST(100, GREATEST(0, total_hype + $1)) WHERE presentation_id = $2", Hg, presentation_id)
    await conn.execute("UPDATE presentation_sections SET hype_got = $1 WHERE presentation_id = $2 AND section = $3", Hg, presentation_id, current_section)

    # Siguiente sección
    next_section = current_section + 1
    total_sections = await conn.fetchval("""
        SELECT total_sections FROM songs WHERE song_id = $1
    """, song_id)

    final = False
    if next_section > total_sections:
        # Termina presentación
        final = True
        return base_score, Hg, final, int(base_hype)

    # Siguiente sección y cambio de regla
    await conn.execute("""
        UPDATE presentations SET current_section = $1 WHERE presentation_id = $2
    """, next_section, presentation_id)

    change_rule = await conn.fetchval("""
        SELECT change_rule FROM song_sections 
        WHERE song_id = $1 AND section_number = $2
    """, song_id, next_section)
    new_duration = await conn.fetchval("""
        SELECT duration FROM song_sections 
        WHERE song_id = $1 AND section_number = $2
    """, song_id, next_section)

    new_switch = {"optional": 1, "forced": -1, "locked": 0}.get(change_rule, 1)

    p_card_uses = 1 + new_duration // 6
    
    await conn.execute("""
        UPDATE presentations SET free_switches = $1, performance_card_uses = $2
        WHERE presentation_id = $3
    """, new_switch, p_card_uses, presentation_id)

    # Reducir duración de efectos
    for field in ["stage_effect_duration", "support_effect_duration"]:
        if presentation_row[field] and presentation_row[field] > 0:
            await conn.execute(f"""
                UPDATE presentations SET {field} = {field} - 1 WHERE presentation_id = $1
            """, presentation_id)

    
    return base_score, Hg, final, int(base_hype)

# - ultimate skill
async def apply_ultimate_skill_if_applicable(conn, idol_row, section_row, presentation_row):
    card_id = idol_row["unique_id"]
    if not card_id:
        return {}

    # Obtener habilidad ultimate
    card = await conn.fetchrow("SELECT u_skill FROM user_idol_cards WHERE unique_id = $1", card_id)
    if not card or not card["u_skill"]:
        return {}

    skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1 AND skill_type = 'ultimate'", card["u_skill"])
    if not skill:
        return {}

    effect = skill["effect"]
    params = json.loads(skill["params"]) if skill["params"] else {}

    if not effect:
        return {}

    # Appliers únicos para ultimate
    effect_appliers = {
        "stat_boost": apply_stat_boost,
        "extra_cost": apply_extra_cost,
        "relative_cost": apply_relative_cost,
        "multi_effect": apply_multi_effect,
        "boost_higher_stat": apply_boost_higher_stat,
        "boost_lower_stat": apply_boost_lower_stat,
        "equals_to_idol_stat": apply_equals_to_idol_stat,
        "inverse_vitality": apply_inverse_vitality,
        "last_breath": apply_last_breath
    }

    apply_func = effect_appliers.get(effect)
    if apply_func:
        if inspect.iscoroutinefunction(apply_func):
            bonus = await apply_func(params, conn, presentation_row, idol_row)
        else:
            bonus = apply_func(params)
    else:
        return {}            

    return bonus

async def apply_equals_to_idol_stat(params, conn, presentation_row, idol_row):
    value = params.get("value")
    print(f"value {value}")
    if not value:
        return {}

    section = await conn.fetchrow("""
        SELECT vocal, rap, dance, visual FROM song_sections
        WHERE song_id = $1 AND section_number = $2
    """, presentation_row["song_id"], presentation_row["current_section"])

    if not section:
        return {}

    if value in ["vocal", "rap", "dance", "visual"]:
        idol_stat = idol_row.get(value)
        print(f"idol stat {idol_stat}")
        return {"override_stat": {value: idol_stat}}

    elif value in ["highest"]:
        section_stats = [("vocal", section["vocal"]), ("rap", section["rap"]),
                         ("dance", section["dance"]), ("visual", section["visual"])]
        highest = max(section_stats, key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))
        lowest = min(section_stats, key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))
        return {"override_stat": {lowest[0]: highest[1]}}

    return {}

async def apply_inverse_vitality(params, conn, presentation_row, idol_row):
    return {"override_energy": "inverse"}

async def apply_last_breath(params, conn, presentation_row, idol_row):
    return {"override_energy": "fixed"}

class UltimateSkillPreviewButton(discord.ui.Button):
    def __init__(self, presentation_id: str, emoji, disabled: bool = False):
        super().__init__(label="Ultimate", emoji=emoji, style=discord.ButtonStyle.danger, disabled=disabled, row=1)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        async with pool.acquire() as conn:
            presentation = await conn.fetchrow("SELECT * FROM presentations WHERE presentation_id = $1", self.presentation_id)
            idol = await conn.fetchrow("SELECT * FROM presentation_members WHERE presentation_id = $1 AND current_position = 'active'", self.presentation_id)

            if not idol or not idol["card_id"]:
                return await interaction.response.send_message("❌ Idol activo sin carta.", ephemeral=True)

            card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", idol["unique_id"])
            if not card or not card["u_skill"]:
                return await interaction.response.send_message("❌ Esta carta no tiene habilidad ultimate.", ephemeral=True)

            skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card["u_skill"])
            if not skill:
                return await interaction.response.send_message("❌ No se encontró la habilidad.", ephemeral=True)

            desc = f"no-description"

            if idol['unique_id']:
                card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", idol['unique_id'])
                
                if card['u_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['u_skill'])
                    cost_type = skill_data['cost_type']
                    eff_params = json.loads(skill_data['params'])
                    lower = higher = relative_cost = extra_cost = ""
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = int(skill_data['energy_cost'] * -1)
                        
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = (int(round(hype-1,2)*100)) if hype else None
                    
                    desc = f"**{get_emoji(guild, "UltimateSkill")} {skill_data['skill_name']}**\n{get_translation(language,
                                                          f"skills.{skill_data['skill_name']}",
                                                          higher=higher, lower=lower,
                                                          vocal=eff_params.get("vocal"),
                                                          rap=eff_params.get("rap"),
                                                          dance=eff_params.get('dance'),
                                                          visual=eff_params.get('visual'),
                                                          score=score,
                                                          hype=hype,
                                                          value=eff_params.get('value'),
                                                          relative_cost=relative_cost,
                                                          extra_cost=extra_cost,
                                                          )}"
         
            
            embed = discord.Embed(
                title="💥 Vista previa de Ultimate Skill",
                description=desc,
                color=discord.Color.red()
            )

            view = discord.ui.View(timeout=60)
            view.add_item(UltimateSkillUseButton(self.presentation_id, skill["skill_name"]))
            view.add_item(UltimateSkillCancelButton(self.presentation_id))
            await interaction.response.edit_message(embed=embed, view=view)

class UltimateSkillCancelButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="Cancelar", emoji="🔙", style=discord.ButtonStyle.secondary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

class UltimateSkillUseButton(discord.ui.Button):
    def __init__(self, presentation_id: str, skill_name: str):
        super().__init__(label="Usar Ultimate", emoji="🚀", style=discord.ButtonStyle.danger)
        self.presentation_id = presentation_id
        self.skill_name = skill_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()
        async with pool.acquire() as conn:
            presentation = await conn.fetchrow("SELECT * FROM presentations WHERE presentation_id = $1", self.presentation_id)
            idol = await conn.fetchrow("SELECT * FROM presentation_members WHERE presentation_id = $1 AND current_position = 'active'", self.presentation_id)
            section = await conn.fetchrow("SELECT * FROM song_sections WHERE song_id = $1 AND section_number = $2", presentation["song_id"], presentation["current_section"])

            bonus = await apply_ultimate_skill_if_applicable(conn, idol, section, presentation)
            passive_bonus = await apply_passive_skill_if_applicable(conn, idol, section, presentation)

            bonus_type = [
                "relative_cost",
                "score",
                "hype"
            ]
            for key, value in passive_bonus.items():
                if key in bonus and key not in bonus_type:
                    bonus[key] += value
                elif key in bonus and key in bonus_type:
                    bonus[key] *= value
                else:
                    bonus[key] = value

            # 👇 Marcar que ya no puede usar Ultimate
            await conn.execute("""
                UPDATE presentation_members
                SET can_ult = FALSE
                WHERE id = $1
            """, idol["id"])

            score, hype, final, base_score = await perform_section_action(conn, self.presentation_id, idol, section, presentation, bonus)

            

            embed = discord.Embed(
                title="🚀 Ultimate Skill usada",
                description=f"Puntuación obtenida: **{format(score,',')}** (de: {format(base_score,',')})\n🔥 Hype ganado: **{hype}**",
                color=discord.Color.red()
            )
            if final:
                is_ephemeral:bool = presentation['presentation_type'] == "practice"
                content = await finalize_presentation(conn, presentation)
                await interaction.edit_original_response(embed=embed, view=None)
                await interaction.followup.send(
                    content=content,
                    ephemeral = is_ephemeral
                )
                return
            
            await interaction.edit_original_response(embed=embed, view=ScoreSummaryView(self.presentation_id))

            
        
# - support skill
class SupportSkillPreviewButton(discord.ui.Button):
    def __init__(self, presentation_id: str, emoji, disabled: bool = False):
        super().__init__(label="Support", emoji=emoji, style=discord.ButtonStyle.success, disabled=disabled, row=1)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        guild = interaction.guild
        language = await get_user_language(interaction.user.id)
        async with pool.acquire() as conn:
            presentation = await conn.fetchrow("SELECT * FROM presentations WHERE presentation_id = $1", self.presentation_id)
            idol = await conn.fetchrow("SELECT * FROM presentation_members WHERE presentation_id = $1 AND current_position = 'active'", self.presentation_id)

            if not idol or not idol["card_id"]:
                return await interaction.response.send_message("❌ Idol activo sin carta.", ephemeral=True)

            card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", idol["unique_id"])
            if not card or not card["s_skill"]:
                return await interaction.response.send_message("❌ Esta carta no tiene habilidad de soporte.", ephemeral=True)

            skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1 AND skill_type = 'support'", card["s_skill"])
            if not skill:
                return await interaction.response.send_message("❌ No se encontró la habilidad.", ephemeral=True)

            energy_cost = skill["energy_cost"]
            energy_available = idol["max_energy"] - idol["used_energy"]

            if energy_available < energy_cost:
                return await interaction.response.send_message(
                    f"⚠️ Energía insuficiente para usar esta habilidad. Necesita {energy_cost}, disponible: {round(energy_available, 2)}",
                    ephemeral=True
                )

            desc = f"no-description"
            
            if idol['unique_id']:
                card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", idol['unique_id'])
                
                if card['s_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['s_skill'])
                    effect_data = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", skill_data['effect_id'])
                    if effect_data['hype_mod']:
                        hype = int(round(effect_data['hype_mod']-1,2)*100)
                    if effect_data['score_mod']:
                        score = int(round(effect_data['score_mod']-1,2)*100)
                    if effect_data['relative_cost']:
                        relative = int(round(effect_data['relative_cost']-1,2)*100)
                    desc = f"**{get_emoji(guild, "SupportSkill")} {skill_data['skill_name']}**\n{get_translation(language,
                                                          f"skills.{skill_data['skill_name']}",
                                                          duration=skill_data['duration'], energy_cost=int(skill_data['energy_cost']),
                                                          highest = effect_data['highest_stat_mod'], lowest = effect_data['lowest_stat_mod'],
                                                          vocal = effect_data['plus_vocal'], rap = effect_data['plus_rap'],
                                                          dance = effect_data['plus_dance'], visual = effect_data['plus_visual'],
                                                          hype = hype, score = score,
                                                          extra_cost = effect_data['extra_cost'], relative_coost = relative
                                                          )}"

            embed = discord.Embed(
                title="🧃 Vista previa de habilidad de soporte",
                description=desc,
                color=discord.Color.teal()
            )

            view = discord.ui.View(timeout=60)
            view.add_item(SupportSkillUseButton(self.presentation_id, skill["skill_name"]))
            view.add_item(SupportSkillCancelButton(self.presentation_id))
            await interaction.response.edit_message(embed=embed, view=view)

class SupportSkillCancelButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="Cancelar", emoji="🔙", style=discord.ButtonStyle.secondary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

class SupportSkillUseButton(discord.ui.Button):
    def __init__(self, presentation_id: str, skill_name: str):
        super().__init__(label="Usar habilidad", emoji="🧃", style=discord.ButtonStyle.success)
        self.presentation_id = presentation_id
        self.skill_name = skill_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()
        user_id = interaction.user.id

        async with pool.acquire() as conn:
            # Verificar presentación
            presentation = await conn.fetchrow("""
                SELECT * FROM presentations
                WHERE presentation_id = $1 AND user_id = $2
            """, self.presentation_id, user_id)

            if not presentation:
                return await interaction.followup.send("❌ No se encontró la presentación.", ephemeral=True)

            # Verificar idol activo
            idol = await conn.fetchrow("""
                SELECT * FROM presentation_members
                WHERE presentation_id = $1 AND current_position = 'active'
            """, self.presentation_id)

            if not idol or not idol["card_id"]:
                return await interaction.followup.send("❌ Idol activo sin carta asignada.", ephemeral=True)

            # Obtener skill de soporte
            skill = await conn.fetchrow("""
                SELECT * FROM skills
                WHERE skill_name = $1 AND skill_type = 'support'
            """, self.skill_name)

            if not skill:
                return await interaction.followup.send("❌ No se encontró la habilidad de soporte.", ephemeral=True)

            effect_id = skill["effect_id"]
            duration = skill["duration"]
            energy_cost = skill["energy_cost"]

            # Verificar energía suficiente
            energia_disponible = idol["max_energy"] - idol["used_energy"]
            if energia_disponible < energy_cost:
                return await interaction.followup.send("❌ Energía insuficiente para usar esta habilidad.", ephemeral=True)

            # Aplicar el efecto de soporte en la presentación
            await conn.execute("""
                UPDATE presentations
                SET support_effect = $1,
                    support_effect_duration = $2
                WHERE presentation_id = $3
            """, effect_id, duration, self.presentation_id)

            # Restar energía del idol
            await conn.execute("""
                UPDATE presentation_members
                SET used_energy = used_energy + $1
                WHERE presentation_id = $2 AND idol_id = $3
            """, energy_cost, self.presentation_id, idol["idol_id"])

        # Volver a mostrar la vista de la sección actual
        await show_current_section_view(interaction, self.presentation_id, edit=True)


# - active skill
def parse_effect_description(skill):
    effects = []

    if skill["effect"] == "stat_boost":
        for stat, value in json.loads(skill["params"]).items():
            if value > 0:
                effects.append(f"+{value} a {stat.capitalize()}")

    elif skill["effect"] == "multi_effect":
        for stat, value in skill["params"].items():
            if value > 0:
                effects.append(f"+{value} a {stat.capitalize()}")

    elif skill["effect"] == "boost_higher_stat":
        effects.append(f"+{skill['params'].get('value', '?')} a la estadística más alta")

    elif skill["effect"] == "boost_lower_stat":
        effects.append(f"+{skill['params'].get('value', '?')} a la estadística más baja")

    if skill["condition_effect"]:
        effects.append("🔸 Tiene efecto adicional si se cumple una condición")

    return "\n".join(effects) if effects else "Sin efecto aparente"

class ActiveSkillPreviewButton(discord.ui.Button):
    def __init__(self, presentation_id: str, emoji, disabled: bool = False):
        super().__init__(label="Active", emoji=emoji, style=discord.ButtonStyle.primary, disabled=disabled, row=1)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        guild = interaction.guild
        language = await get_user_language(interaction.user.id)
        async with pool.acquire() as conn:
            presentation = await conn.fetchrow("SELECT * FROM presentations WHERE presentation_id = $1", self.presentation_id)
            idol = await conn.fetchrow("SELECT * FROM presentation_members WHERE presentation_id = $1 AND current_position = 'active'", self.presentation_id)

            if not idol or not idol["card_id"]:
                return await interaction.response.send_message("❌ Idol activo sin carta.", ephemeral=True)

            card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", idol["unique_id"])
            if not card or not card["a_skill"]:
                return await interaction.response.send_message("❌ Esta carta no tiene habilidad activa.", ephemeral=True)

            skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card["a_skill"])
            if not skill:
                return await interaction.response.send_message("❌ No se encontró la habilidad.", ephemeral=True)

            desc = f"**{skill['skill_name']}**\n{parse_effect_description(skill)}"
            
            if idol['unique_id']:
                card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", idol['unique_id'])
                if card['a_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['a_skill'])
                    condition_values = json.loads(skill_data['condition_values'])
                    condition_params = json.loads(skill_data['condition_params'])
                    eff_params = json.loads(skill_data['params'])
                    eff = skill_data['effect']
                    cost_type = skill_data['cost_type']
                    lower = higher = relative_cost = extra_cost = ""
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = skill_data['energy_cost']
                    if eff == "boost_lower_stat":
                        lower = eff_params.get("value")
                    if eff == "boost_higher_stat":
                        higher = eff_params.get("value")
                        
                    pcond_energy = condition_params.get("energy")
                    if pcond_energy:
                        pcond_energy *= -1
                    
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = int(round(hype-1,2)*100) if hype else None
                    
                    pcond_score=condition_params.get('score')
                    pcond_score = int(round(pcond_score-1,2)*100) if pcond_score else None
                    pcond_hype=condition_params.get('hype')
                    pcond_hype = int(round(pcond_hype-1,2)*100) if pcond_hype else None
                    
                    desc = f"**{get_emoji(guild, "ActiveSkill")} {skill_data['skill_name']}**\n{get_translation(language,
                                                          f"skills.{skill_data['skill_name']}",
                                                          cond_vocal = condition_values.get("vocal"),
                                                          cond_rap = condition_values.get("rap"),
                                                          cond_dance = condition_values.get("dance"),
                                                          cond_visual = condition_values.get("visual"),
                                                          cond_energy = condition_values.get("energy"),
                                                          cond_stat = condition_values.get("stat"),
                                                          cond_hype = condition_values.get("hype"),
                                                          cond_duration = condition_values.get("duration"),
                                                          pcond_vocal = condition_params.get("vocal"),
                                                          pcond_rap = condition_params.get("rap"),
                                                          pcond_dance = condition_params.get("dance"),
                                                          pcond_visual = condition_params.get("visual"),
                                                          pcond_hype = pcond_hype,
                                                          pcond_score = pcond_score,
                                                          pcond_energy = pcond_energy,
                                                          pcond_value = condition_params.get("value"),
                                                          higher=higher, lower=lower,
                                                          vocal=eff_params.get("vocal"),
                                                          rap=eff_params.get("rap"),
                                                          dance=eff_params.get('dance'),
                                                          visual=eff_params.get('visual'),
                                                          score=score,
                                                          hype=hype,
                                                          relative_cost=relative_cost,
                                                          extra_cost=extra_cost,
                                                          )}"

            embed = discord.Embed(
                title="🛠 Vista previa de habilidad activa",
                description=desc,
                color=discord.Color.gold()
            )

            view = discord.ui.View(timeout=60)
            view.add_item(ActiveSkillUseButton(self.presentation_id, skill["skill_name"]))
            view.add_item(ActiveSkillCancelButton(self.presentation_id))
            await interaction.response.edit_message(embed=embed, view=view)

class ActiveSkillCancelButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="Cancelar", emoji="🔙", style=discord.ButtonStyle.danger)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

class ActiveSkillUseButton(discord.ui.Button):
    def __init__(self, presentation_id: str, skill_name: str):
        super().__init__(label="Usar habilidad", emoji="⚡", style=discord.ButtonStyle.success)
        self.presentation_id = presentation_id
        self.skill_name = skill_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()
        async with pool.acquire() as conn:
            presentation = await conn.fetchrow("SELECT * FROM presentations WHERE presentation_id = $1", self.presentation_id)
            idol = await conn.fetchrow("SELECT * FROM presentation_members WHERE presentation_id = $1 AND current_position = 'active'", self.presentation_id)
            section = await conn.fetchrow("SELECT * FROM song_sections WHERE song_id = $1 AND section_number = $2", presentation["song_id"], presentation["current_section"])
            skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", self.skill_name)

            bonus = await apply_active_skill_if_applicable(conn, idol, section, presentation)
            passive_bonus = await apply_passive_skill_if_applicable(conn, idol, section, presentation)
            
            bonus_type = [
                "relative_cost",
                "score",
                "hype"
            ]
            for key, value in passive_bonus.items():
                if key in bonus and key not in bonus_type:
                    bonus[key] += value
                elif key in bonus and key in bonus_type:
                    bonus[key] *= value
                else:
                    bonus[key] = value
            print(bonus)
            
            score, hype, final, base_score = await perform_section_action(conn, self.presentation_id, idol, section, presentation, bonus)

            
    
            embed = discord.Embed(
                title="🎯 Habilidad activa usada",
                description=f"Puntuación obtenida: **{format(score,',')}** (de: {format(base_score,',')})\n🔥 Hype ganado: **{hype}**",
                color=discord.Color.green()
            )
            if final:
                is_ephemeral:bool = presentation['presentation_type'] == "practice"
                content = await finalize_presentation(conn, presentation)
                await interaction.edit_original_response(embed=embed, view=None)
                await interaction.followup.send(
                    content=content,
                    ephemeral = is_ephemeral
                )
                return
            
            await interaction.edit_original_response(embed=embed, view=ScoreSummaryView(self.presentation_id))


async def apply_active_skill_if_applicable(conn, idol_row, section_row, presentation_row):
    card_id = idol_row["unique_id"]
    if not card_id:
        return {}

    # Obtener habilidad activa
    card = await conn.fetchrow("SELECT a_skill FROM user_idol_cards WHERE unique_id = $1", card_id)
    if not card or not card["a_skill"]:
        return {}

    skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1 AND skill_type = 'active'", card["a_skill"])
    if not skill:
        return {}

    bonus = {}
    bonus_type = [
        "relative_cost",
        "hype",
        "score"
    ]
    
    # -----------------------
    # Efectos normales (params)
    # -----------------------
    if skill["effect"] and skill["params"]:
        effect = skill["effect"]
        params = json.loads(skill["params"])

        effect_appliers = {
            "stat_boost": apply_stat_boost,
            "extra_cost": apply_extra_cost,
            "relative_cost": apply_relative_cost,
            "multi_effect": apply_multi_effect,
            "boost_higher_stat": apply_boost_higher_stat,
            "boost_lower_stat": apply_boost_lower_stat
        }

        apply_func = effect_appliers.get(effect)
        if apply_func:
            if inspect.iscoroutinefunction(apply_func):
                partial_bonus = await apply_func(params, conn, presentation_row, idol_row)
            else:
                partial_bonus = apply_func(params)
            for key, value in partial_bonus.items():
                if key in bonus and key not in bonus_type:
                    bonus[key] += value
                elif key in bonus and key in bonus_type:
                    bonus[key] *= value
                else:
                    bonus[key] = value
        else:
            return {}  
        
    # -----------------------
    # Efectos condicionales
    # -----------------------
    if skill["condition"] and skill["condition_effect"]:
        condition = skill["condition"]
        condition_values = json.loads(skill["condition_values"])

        condition_checkers = {
            "section_stat_above": check_section_stat_above,
            "idol_stat_below": check_idol_stat_below,
            "highest_section_stat": check_highest_section_stat,
            "duration_above": check_duration_above,
            "stage_effect_active": check_stage_effect_active,
            "section_stat_below": check_section_stat_below,
            "duration_below": check_duration_below,
            "idol_stat_above": check_idol_stat_above,
            "highest_score": check_highest_score,
            "highest_energy": check_highest_energy,
            "lowest_score": check_lowest_score,
            "lowest_energy": check_lowest_energy,
            "hype_above": check_hype_above,
            "hype_below": check_hype_below,
            "idol_active": check_idol_active,
            "idol_participated": check_idol_participated,
            "same_highest_stat": check_same_highest_stat,
            "solo_act": check_solo_act,
            "stat_above_stat": check_stat_above_stat,
            "stat_higher_than_section": check_stat_higher_than_section,
            "support_effect_active": check_support_effect_active
        }

        
        checker = condition_checkers.get(condition)
        if checker:
            success = await checker(condition_values, idol_row, section_row, presentation_row, conn)
            if success:
                condition_effect = skill["condition_effect"]
                condition_params = json.loads(skill["condition_params"])

                apply_func = effect_appliers.get(condition_effect)
                if apply_func:
                    conditional_bonus = apply_func(condition_params)
                    for key, value in conditional_bonus.items():
                        if key in bonus and key not in bonus_type:
                            bonus[key] += value
                        elif key in bonus and key in bonus_type:
                            bonus[key] *= value
                        else:
                            bonus[key] = value

    # -----------------------
    # Costos de energía
    # -----------------------
    cost_type = skill["cost_type"]
    energy_cost = skill["energy_cost"]

    if cost_type == "relative":
        bonus["relative_cost"] = energy_cost
    elif cost_type == "fixed":
        bonus["extra_cost"] = energy_cost

    return bonus

# - basic action
# CHECKERS
async def check_section_stat_above(condition_values, idol_row, section_row, presentation_row, conn):
    for stat, min_value in condition_values.items():
        if section_row.get(stat, 0) <= min_value:
            return False
    return True

async def check_section_stat_below(condition_values, idol_row, section_row, presentation_row, conn):
    for stat, max_value in condition_values.items():
        if section_row.get(stat, 999) >= max_value:
            return False
    return True

async def check_idol_stat_below(condition_values, idol_row, section_row, presentation_row, conn):
    for stat, max_ratio in condition_values.items():
        if stat == "energy":
            ratio = (idol_row["max_energy"] - idol_row["used_energy"]) / idol_row["max_energy"]
            if ratio >= max_ratio:
                return False
    return True

async def check_idol_stat_above(condition_values, idol_row, section_row, presentation_row, conn):
    for stat, min_ratio in condition_values.items():
        if stat == "energy":
            ratio = (idol_row["max_energy"] - idol_row["used_energy"]) / idol_row["max_energy"]
            if ratio <= min_ratio:
                return False
    return True

async def check_highest_section_stat(condition_values, idol_row, section_row, presentation_row, conn):
    target_stat = condition_values.get("stat")
    if not target_stat:
        return False

    section_stats = {
        "vocal": section_row["vocal"],
        "rap": section_row["rap"],
        "dance": section_row["dance"],
        "visual": section_row["visual"]
    }

    highest = max(section_stats.items(), key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))
    print(f"highest: {highest}")
    return highest[0] == target_stat

async def check_duration_above(condition_values, idol_row, section_row, presentation_row, conn):
    return section_row["duration"] > condition_values.get("duration", 999)

async def check_duration_below(condition_values, idol_row, section_row, presentation_row, conn):
    return section_row["duration"] < condition_values.get("duration", 0)

async def check_highest_score(condition_values, idol_row, section_row, presentation_row, conn):
    """
    Verifica si el idol activo es quien más score individual tiene.
    condition_values puede tener: { "value": true } o { "value": false }
    """
    idol_score = idol_row["individual_score"]
    presentation_id = idol_row["presentation_id"]

    top_score = await conn.fetchval("""
        SELECT MAX(individual_score)
        FROM presentation_members
        WHERE presentation_id = $1
    """, presentation_id)

    return idol_score == top_score if condition_values.get("value", True) else idol_score != top_score

async def check_highest_energy(condition_values, idol_row, section_row, presentation_row, conn):
    """
    Verifica si el idol activo tiene el mayor porcentaje de energía.
    condition_values puede tener: { "value": true } o { "value": false }
    """
    idol_energy = 1 - (idol_row["used_energy"] / idol_row["max_energy"])
    presentation_id = idol_row["presentation_id"]

    rows = await conn.fetch("""
        SELECT used_energy, max_energy
        FROM presentation_members
        WHERE presentation_id = $1
    """, presentation_id)

    top_ratio = max(1 - (row["used_energy"] / row["max_energy"]) for row in rows)

    return idol_energy == top_ratio if condition_values.get("value", True) else idol_energy != top_ratio

async def check_lowest_score(condition_values, idol_row, section_row, presentation_row, conn):
    idol_score = idol_row["individual_score"]
    presentation_id = idol_row["presentation_id"]

    lowest_score = await conn.fetchval("""
        SELECT MIN(individual_score)
        FROM presentation_members
        WHERE presentation_id = $1
    """, presentation_id)

    return idol_score == lowest_score if condition_values.get("value", True) else idol_score != lowest_score

async def check_lowest_energy(condition_values, idol_row, section_row, presentation_row, conn):
    idol_energy = 1 - (idol_row["used_energy"] / idol_row["max_energy"])
    presentation_id = idol_row["presentation_id"]

    rows = await conn.fetch("""
        SELECT used_energy, max_energy
        FROM presentation_members
        WHERE presentation_id = $1
    """, presentation_id)

    lowest_ratio = min(1 - (r["used_energy"] / r["max_energy"]) for r in rows)

    return idol_energy == lowest_ratio if condition_values.get("value", True) else idol_energy != lowest_ratio

async def check_hype_above(condition_values, idol_row, section_row, presentation_row, conn):
    required = condition_values.get("hype")
    current_hype = presentation_row["total_hype"]

    return current_hype > required

async def check_hype_below(condition_values, idol_row, section_row, presentation_row, conn):
    required = condition_values.get("hype")
    current_hype = presentation_row["total_hype"]

    return current_hype < required

async def check_idol_active(condition_values, idol_row, section_row, presentation_row, conn):
    expected = condition_values.get("value", True)
    return idol_row.get("last_position") == "active" if expected else idol_row.get("last_position") != "active"

async def check_idol_participated(condition_values, idol_row, section_row, presentation_row, conn):
    expected = condition_values.get("value", True)
    participated = idol_row.get("last_position") in ["participated", "active"]
    return participated == expected

async def check_same_highest_stat(condition_values, idol_row, section_row, presentation_row, conn):
    expected = condition_values.get("value", True)  # Se espera True o False

    idol_stats = {
        "vocal": idol_row["vocal"],
        "rap": idol_row["rap"],
        "dance": idol_row["dance"],
        "visual": idol_row["visual"]
    }
    highest_idol = max(idol_stats.items(), key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))[0]

    section_stats = {
        "vocal": section_row["vocal"],
        "rap": section_row["rap"],
        "dance": section_row["dance"],
        "visual": section_row["visual"]
    }
    highest_section = max(section_stats.items(), key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))[0]

    return (highest_idol == highest_section) == expected

async def check_solo_act(condition_values, idol_row, section_row, presentation_row, conn):
    if idol_row.get("last_position") != "active":
        return False

    idol_energy_ratio = 1 - (idol_row["used_energy"] / idol_row["max_energy"])

    rows = await conn.fetch("""
        SELECT used_energy, max_energy FROM presentation_members
        WHERE presentation_id = $1
    """, idol_row["presentation_id"])

    highest_ratio = max(1 - (r["used_energy"] / r["max_energy"]) for r in rows)

    return idol_energy_ratio == highest_ratio

async def check_stat_above_stat(condition_values, idol_row, section_row, presentation_row, conn):
    stat1 = condition_values.get("higher")
    stat2 = condition_values.get("lower")

    if stat1 == stat2 or stat1 not in section_row or stat2 not in section_row:
        return False

    return section_row[stat1] > section_row[stat2]

async def check_stat_higher_than_section(condition_values, idol_row, section_row, presentation_row, conn):
    stat = condition_values.get("stat")

    if stat not in ["vocal", "rap", "dance", "visual"]:
        return False

    return idol_row[stat] > section_row[stat]

async def check_stage_effect_active(condition_values, idol_row, section_row, presentation_row, conn):
    expected = condition_values.get("value", False)
    return bool(presentation_row["stage_effect_duration"]) > 0 if expected else presentation_row["stage_effect_duration"] <= 0

async def check_support_effect_active(condition_values, idol_row, section_row, presentation_row, conn):
    expected = condition_values.get("value", False)
    return bool(presentation_row["support_effect_duration"]) > 0 if expected else presentation_row["support_effect_duration"] <= 0



# EFFECTS
def apply_stat_boost(effect_values, conn=None, presentation_row=None, idol_row=None):
    return {
        "vocal": effect_values.get("vocal", 0),
        "rap": effect_values.get("rap", 0),
        "dance": effect_values.get("dance", 0),
        "visual": effect_values.get("visual", 0),
        "score": effect_values.get("score", 1),
        "hype": effect_values.get("hype", 1)
    }

def apply_extra_cost(effect_values, conn=None, presentation_row=None, idol_row=None):
    return {
        "extra_cost": effect_values.get("energy", 0)
    }
    
def apply_relative_cost(effect_values, conn=None, presentation_row=None, idol_row=None):
    return {
        "relative_cost": effect_values.get("energy", 1)
    }

def apply_multi_effect(effect_values, conn=None, presentation_row=None, idol_row=None):
    return{
        "relative_cost": effect_values.get("relative_energy", 1),
        "extra_cost": effect_values.get("extra_energy", 0),
        "vocal": effect_values.get("vocal", 0),
        "rap": effect_values.get("rap", 0),
        "dance": effect_values.get("dance", 0),
        "visual": effect_values.get("visual", 0),
        "score": effect_values.get("score", 1),
        "hype": effect_values.get("hype", 1)
    }

async def apply_boost_higher_stat(effect_values, conn, presentation_row, idol_row=None):
    song_id = presentation_row["song_id"]
    section_number = presentation_row["current_section"]

    section = await conn.fetchrow("""
        SELECT vocal, rap, dance, visual
        FROM song_sections
        WHERE song_id = $1 AND section_number = $2
    """, song_id, section_number)

    if not section:
        return {}

    stats = [("vocal", section["vocal"]), ("rap", section["rap"]), ("dance", section["dance"]), ("visual", section["visual"])]
    # Orden para desempate: vocal > rap > dance > visual
    highest = max(stats, key=lambda x: (x[1], -["vocal", "rap", "dance", "visual"].index(x[0])))

    return {
        highest[0]: effect_values.get("value", 0)
    }

async def apply_boost_lower_stat(effect_values, conn, presentation_row, idol_row=None):
    song_id = presentation_row["song_id"]
    section_number = presentation_row["current_section"]

    section = await conn.fetchrow("""
        SELECT vocal, rap, dance, visual
        FROM song_sections
        WHERE song_id = $1 AND section_number = $2
    """, song_id, section_number)

    if not section:
        return {}

    stats = [("vocal", section["vocal"]), ("rap", section["rap"]), ("dance", section["dance"]), ("visual", section["visual"])]
    # Orden para desempate: vocal < rap < dance < visual
    lowest = min(stats, key=lambda x: (x[1], ["vocal", "rap", "dance", "visual"].index(x[0])))

    return {
        lowest[0]: effect_values.get("value", 0)
    }


# MAIN WRAPPER
async def apply_passive_skill_if_applicable(conn, idol_row, section_row, presentation_row, check_only=False):
    card_id = idol_row["unique_id"]
    if not card_id:
        print("no carta")
        return {}

    card = await conn.fetchrow("SELECT p_skill FROM user_idol_cards WHERE unique_id = $1", card_id)
    if not card or not card["p_skill"]:
        print("no skill")
        return {}

    skill = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1 AND skill_type = 'passive'", card["p_skill"])
    if not skill:
        print("no skill data")
        return {}

    condition = skill["condition"]
    condition_values = json.loads(skill["condition_values"])

    
    condition_checkers = {
        "section_stat_above": check_section_stat_above,
        "idol_stat_below": check_idol_stat_below,
        "highest_section_stat": check_highest_section_stat,  # <-- este sería el de Dazzling Smile
        "duration_above": check_duration_above,
        "stage_effect_active": check_stage_effect_active,
        "section_stat_below": check_section_stat_below,
        "duration_below": check_duration_below,
        "idol_stat_above": check_idol_stat_above,
        "highest_score": check_highest_score,
        "highest_energy": check_highest_energy,
        "lowest_score": check_lowest_score,
        "lowest_energy": check_lowest_energy,
        "hype_above": check_hype_above,
        "hype_below": check_hype_below,
        "idol_active": check_idol_active,
        "idol_participated": check_idol_participated,
        "same_highest_stat": check_same_highest_stat,
        "solo_act": check_solo_act,
        "stat_above_stat": check_stat_above_stat,
        "stat_higher_than_section": check_stat_higher_than_section,
        "stage_effect_active": check_stage_effect_active,
        "support_effect_active": check_support_effect_active
    }

    checker = condition_checkers.get(condition)
    if not checker:
        return {} if not check_only else False

    success = await checker(condition_values, idol_row, section_row, presentation_row, conn)
    if not success:
        return {} if not check_only else False

    if check_only:
        return True

    condition_effect = skill["condition_effect"]
    condition_params = json.loads(skill["condition_params"])

    effect_appliers = {
        "stat_boost": apply_stat_boost,
        "extra_cost": apply_extra_cost,
        "relative_cost": apply_relative_cost,
        "multi_effect": apply_multi_effect
    }

    apply_func = effect_appliers.get(condition_effect)
    if not apply_func:
        return {}
    
    print("pasiva aplicada")
    return apply_func(condition_params)


class BasicActionButton(discord.ui.Button):
    def __init__(self, presentation_id: str, disabled: bool = False):
        super().__init__(label="Basic", emoji="🎵", style=discord.ButtonStyle.primary, disabled=disabled, row=0)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()
        async with pool.acquire() as conn:
            # Obtener info de la presentación
            presentation = await conn.fetchrow("""
                SELECT * FROM presentations WHERE presentation_id = $1
            """, self.presentation_id)

            if not presentation:
                return await interaction.response.edit_message("Presentación no encontrada.", ephemeral=True)

            # Verificar idol activo
            idol = await conn.fetchrow("""
                SELECT * FROM presentation_members 
                WHERE presentation_id = $1 AND current_position = 'active'
            """, self.presentation_id)

            if not idol:
                return await interaction.response.edit_message(
                    "❌ No hay un idol activo para realizar la acción.",
                    view=ReturnToSectionView(self.presentation_id),
                    ephemeral=True
                )

            # Obtener sección actual
            current_section = presentation["current_section"]
            song_id = presentation["song_id"]
            song_section = await conn.fetchrow("""
                SELECT * FROM song_sections
                WHERE song_id = $1 AND section_number = $2
            """, song_id, current_section)
            print(f"section number: {song_section['section_number']}")

            if not song_section:
                return await interaction.followup.send(content="Sección no encontrada.", ephemeral=True)
            passive_bonus = await apply_passive_skill_if_applicable(conn, idol, song_section, presentation)
            score, hype, final, base_score = await perform_section_action(conn, self.presentation_id, idol, song_section, presentation, passive_bonus)
            
            

            

            

        embed = discord.Embed(
            title="🎯 Resultado de la sección",
            description=f"Puntuación obtenida: **{format(score,',')}** (de: {format(base_score,',')})\n🔥 Hype ganado: **{hype}**",
            color=discord.Color.green()
        )
        
        if final:
            is_ephemeral:bool = presentation['presentation_type'] == "practice"
            content = await finalize_presentation(conn, presentation)
            await interaction.edit_original_response(embed=embed, view=None)
            
            await interaction.followup.send(
                content=content,
                ephemeral = is_ephemeral
            )
            return
        
        await interaction.edit_original_response(embed=embed, view=ScoreSummaryView(self.presentation_id))
        
        

class ScoreSummaryView(discord.ui.View):
    def __init__(self, presentation_id: str):
        super().__init__(timeout=60)
        self.presentation_id = presentation_id

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.success)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

class ReturnToSectionView(discord.ui.View):
    def __init__(self, presentation_id: str):
        super().__init__(timeout=None)
        self.presentation_id = presentation_id

        self.add_item(ReturnToSectionButton(presentation_id))

class ReturnToSectionButton(discord.ui.Button):
    def __init__(self, presentation_id: str):
        super().__init__(label="Volver a la sección", emoji="⬅️", style=discord.ButtonStyle.secondary)
        self.presentation_id = presentation_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await show_current_section_view(interaction, self.presentation_id, edit=True)

async def finalize_presentation(conn, presentation: dict) -> str:
    presentation_id = presentation["presentation_id"]
    user_id = presentation["user_id"]
    group_id = presentation["group_id"]
    song_id = presentation["song_id"]
    ptype = presentation.get("presentation_type", "live")
    pool = get_pool()
    async with pool.acquire() as conn:

        average_score = await conn.fetchval(
            "SELECT average_score FROM songs WHERE song_id = $1",
            presentation["song_id"])
        
        total_score = await conn.fetchval(
            "SELECT total_score FROM presentations WHERE presentation_id = $1",
            presentation_id)
    
        if ptype == "live":
            popularity = int(1000 * (total_score / average_score))
            xp = popularity // 10
            
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'do_presentation'
                """, user_id)
            
            double = ""
            
            group_name = await conn.fetchval("SELECT name FROM groups WHERE group_id = $1", group_id)
            song_name = await conn.fetchval("SELECT name FROM songs WHERE song_id = $1", song_id)
            double_reward = await conn.fetchval("SELECT amount FROM user_boosts WHERE user_id = $1 AND boost = 'DBRWR'", user_id)
            
            if double_reward:
                if double_reward >= 1:
                    await conn.execute("UPDATE user_boosts SET amount = amount - 1 WHERE user_id = $1 AND boost = 'DBRWR'", user_id)
                    popularity *= 2
                    double = " **(x2)**"

            first_presentation = await conn.fetchval("SELECT first_presentation FROM groups WHERE group_id = $1", group_id)
            first = ""
            if first_presentation:
                popularity *= 1.3
                first = " `+30% Bonus por primera presentación semanal`"
                await  conn.execute("UPDATE groups SET first_presentation = $1 WHERE group_id = $2", False, group_id)
            
            
            popularity = int(popularity)
            xp = int(xp)
            
            await conn.execute(
                "UPDATE users SET xp = xp + $1 WHERE user_id = $2",
                xp, user_id
            )
            await conn.execute(
                """
                UPDATE presentations
                SET status = 'completed',
                    current_section = current_section + 1,
                    total_popularity = $1
                WHERE presentation_id = $2
                """,
                popularity, presentation_id
            )
            await conn.execute(
                "UPDATE groups SET popularity = popularity + $1 WHERE group_id = $2",
                popularity, group_id
            )

            return (
                f"## 🎉 ¡`{group_name}` ha finalizado una presentación de `{song_name}`!\n**Puntuación total:** {format(total_score,',')} _(Esperado: {format(int(average_score),',')})_\n> **Popularidad ganada:** {format(popularity,',')}{double}{first}\n> **XP obtenida:** {xp}"
            )

        else:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'do_practice'
                """, user_id)
            
            await conn.execute(
                """
                UPDATE presentations
                SET status = 'finished',
                    current_section = current_section + 1
                WHERE presentation_id = $1
                """,
                presentation_id
            )
            return (
                f"## ✅ `{group_name}` ha finalizado una práctica de `{song_name}`.\n**Puntuación total:** {format(total_score,',')}\n> _(no se ha recibido popularidad ni XP)_"
            )

async def setup(bot):
    bot.tree.add_command(PresentationGroup())