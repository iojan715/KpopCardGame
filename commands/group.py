import discord, asyncio, difflib
from discord.ext import commands
from discord import app_commands
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from datetime import timezone, datetime
import random, string
from commands.starter import version as v

version = v

class Group(app_commands.Group):
    def __init__(self):
        super().__init__(name="group", description="Group comands")
        
    @app_commands.command(name="list", description="Show groups")
    @app_commands.describe(agency="Agency")
    async def list_groups(self, interaction: discord.Interaction, agency:str = None):
        user_id = interaction.user.id
        i_user_id = user_id
        pool = get_pool()
        language = await get_user_language(user_id)
        
        async with pool.acquire() as conn:
            if agency:
                agency_r = await conn.fetchrow("SELECT user_id FROM users WHERE agency_name = $1", agency)
                user = await interaction.client.fetch_user(agency_r["user_id"])
                user_id = user.id
                
            query = """
            SELECT group_id, name, popularity, permanent_popularity, status, unpaid_weeks, user_id,
                (SELECT COUNT(*) FROM groups_members WHERE group_id = g.group_id) AS member_count
            FROM groups g
            WHERE user_id = $1
            """
            
            if user_id != i_user_id:
                query += " AND status = 'active'"
            
            query += "ORDER BY creation_date DESC"
            
            rows = await conn.fetch(query, user_id)

        if not rows:
            await interaction.response.send_message(get_translation(language=language, key="group_list.not_created_groups"), ephemeral=True)
            return

        paginator = GroupPaginator(groups=rows, interaction=interaction, language=language)
        await paginator.start()

    @list_groups.autocomplete("agency")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users")
        return [
            app_commands.Choice(name=f"{row["agency_name"]}", value=row["agency_name"])
            for row in rows if current.lower() in row["agency_name"].lower()
        ][:25]     

    @app_commands.command(name="create", description="Create new group")
    async def create_group(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pool = get_pool()
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            existing = await conn.fetchrow("SELECT * FROM groups WHERE user_id = $1 AND status = 'creating'", user_id)
            if existing:
                group_id = existing["group_id"]
            else:
                while True:
                    group_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                    exists = await conn.fetchval("SELECT 1 FROM groups WHERE group_id = $1", group_id)
                    if not exists:
                        break
                await conn.execute("INSERT INTO groups (group_id, user_id, status) VALUES ($1, $2, 'creating')", group_id, user_id)

        await send_group_creation_ui(interaction, group_id, user_id, language)
   

# Classes for `/group create`:
async def send_group_creation_ui(interaction, group_id: str, user_id: int, language:str, from_callback=False):
    pool = get_pool()
    async with pool.acquire() as conn:
        group = await conn.fetchrow("SELECT * FROM groups WHERE group_id = $1", group_id)
        name = group["name"] or "Sin nombre"
        members = await conn.fetch("""
            SELECT DISTINCT ON (gm.idol_id) gm.idol_id, ig.idol_name
            FROM groups_members gm
            JOIN idol_group ig ON gm.idol_id = ig.idol_id
            WHERE gm.group_id = $1 AND gm.user_id = $2
        """, group_id, user_id)

        member_names = [row["idol_name"] + f" ({row["idol_id"]})" for row in members]
        total_members = len(member_names)
        weekly_cost = 100 + (total_members * 50)

        description = get_translation(language, "group_create.group_name", name=name)
        description += get_translation(language, "group_create.weekly_cost", weekly_cost=weekly_cost)
        description += get_translation(language, "group_create.current_members")
        description += "\n".join([f"• {idol}" for idol in member_names]) if member_names else get_translation(language, "group_create.no_members")

        embed = discord.Embed(title=get_translation(language, "group_create.group_creation"),
                              description=description,
                              color=discord.Color.orange())
        view = GroupCreationView(group_id, user_id)

        if from_callback and interaction.message:
            await interaction.response.edit_message(content= "", embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True, content="")
 
class GroupCreationView(discord.ui.View):
    def __init__(self, group_id: str, user_id: int):
        super().__init__(timeout=300)
        self.add_item(SetNameButton(group_id, user_id))
        self.add_item(AddIdolButton(group_id, user_id))
        self.add_item(RemoveIdolButton(group_id, user_id))
        self.add_item(ConfirmButton(group_id, user_id))
        self.add_item(CancelButton(group_id, user_id))

class SetNameButton(discord.ui.Button):
    def __init__(self, group_id, user_id):
        super().__init__(label="Set Name", style=discord.ButtonStyle.primary)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        pool=get_pool()
        async with pool.acquire() as conn:
            
            def normalize(name):
                return name.lower().replace(" ", "") if name else ""

            # Umbral de similitud (0.9 = 90%)
            SIMILARITY_THRESHOLD = 0.9
            
            groups = await conn.fetch("SELECT name FROM groups")
            group_list = [
                "Star Harmony",
                "Peachy Pop",
                "NANANA",
                "ReVERB",
                "404 Stars",
                "FirstWish",
                "Honeybeat",
                "Lovewave",
                "PRiSM",
                "Cherry Wish",
                "Mint Crush",
                "NovaX",
                "BloomX",
                "Youniverse",
                "Pinkrush",
                "RedMoon",
                "ITZME",
                "OrbitGirls",
                "Starline",
                "Fearless",
                "NewGenZ",
                "Starlight",
                "Kizmi",
                "Dream Kiss",
                "Cherry Beat",
                "Rocket Love",
                "Moonie Pop",
                "Sugar Light"
            ]
            used_names = [normalize(row["name"]) for row in groups if row["name"]]

            # Filtrar los nombres de ejemplo que sean distintos y no demasiado parecidos
            filtered_list = [
                name for name in group_list
                if name and all(
                    difflib.SequenceMatcher(None, normalize(name), used).ratio() < SIMILARITY_THRESHOLD
                    for used in used_names
                )
            ]

            # Elegir uno al azar si quedan
            if filtered_list:
                group_name = random.choice(filtered_list)
            else:
                group_name = "Star Harmony"
        
        await interaction.response.send_modal(SetNameModal(self.group_id, self.user_id, group_name))

class SetNameModal(discord.ui.Modal, title="Change name"):
    def __init__(self, group_id, user_id, group_name):
        super().__init__()
        self.group_id = group_id
        self.user_id = user_id
        self.name_input = discord.ui.TextInput(label="New name:", placeholder=f"Ej: {group_name}", min_length=1, max_length=30)
        self.add_item(self.name_input)
        

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value.strip()
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE groups SET name = $1 WHERE group_id = $2 AND user_id = $3", new_name, self.group_id, self.user_id)
        await send_group_creation_ui(interaction, self.group_id, self.user_id, from_callback=True, language=await get_user_language(interaction.user.id))

class AddIdolButton(discord.ui.Button):
    def __init__(self, group_id, user_id):
        super().__init__(label="➕", style=discord.ButtonStyle.success)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(interaction.user.id)
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT group_name FROM idol_group ORDER BY group_name")
            options = [discord.SelectOption(label=row["group_name"]) for row in rows]

        view = discord.ui.View()
        view.add_item(IdolGroupSelector(self.group_id, self.user_id, options))
        await interaction.response.edit_message(content=get_translation(language,"group_create.select_group"),
                                                embed=None,
                                                view=view)

class IdolGroupSelector(discord.ui.Select):
    def __init__(self, group_id, user_id, options):
        super().__init__(placeholder="Select", options=options)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        selected_group = self.values[0]
        pool = get_pool()
        async with pool.acquire() as conn:
            idols = await conn.fetch("SELECT * FROM idol_group WHERE group_name = $1", selected_group)

        view = discord.ui.View()
        for idol in idols:
            view.add_item(SelectIdolButton(self.group_id, self.user_id, idol["idol_id"], f"{idol["idol_name"]} ({idol['idol_id']})"))
        language = await get_user_language(interaction.user.id)
        await interaction.response.edit_message(content=get_translation(language,"group_create.select_idol", selected_group=selected_group),
                                                embed=None,
                                                view=view)

class SelectIdolButton(discord.ui.Button):
    def __init__(self, group_id, user_id, idol_id, idol_name):
        super().__init__(label=idol_name, style=discord.ButtonStyle.secondary)
        self.group_id = group_id
        self.user_id = user_id
        self.idol_id = idol_id

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(interaction.user.id)
        pool = get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM groups_members WHERE group_id = $1", self.group_id)
            if count >= 24:
                await show_error(interaction,
                                 self.user_id,
                                 self.group_id,
                                 get_translation(language, "group_create.cannot_add_more"))
                return

            exists = await conn.fetchval("SELECT 1 FROM groups_members WHERE group_id = $1 AND idol_id = $2", self.group_id, self.idol_id)
            if exists:
                await show_error(interaction,
                                 self.user_id,
                                 self.group_id,
                                 get_translation(language, "group_create.already_added"))
                return

            await conn.execute("INSERT INTO groups_members (group_id, user_id, idol_id) VALUES ($1, $2, $3)", self.group_id, self.user_id, self.idol_id)

        await send_group_creation_ui(interaction, self.group_id, self.user_id, from_callback=True, language=await get_user_language(interaction.user.id))

class RemoveIdolButton(discord.ui.Button):
    def __init__(self, group_id, user_id):
        super().__init__(label="➖", style=discord.ButtonStyle.danger)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        async with pool.acquire() as conn:
            members = await conn.fetch("""
                SELECT gm.idol_id, ig.idol_name
                FROM groups_members gm
                JOIN idol_group ig ON gm.idol_id = ig.idol_id
                WHERE gm.group_id = $1 AND gm.user_id = $2
            """, self.group_id, self.user_id)

        if not members:
            await show_error(interaction, self.user_id, self.group_id, get_translation(language, "group_create.no_members"))
            return

        # Usar un set para asegurar que no se repita el mismo idol_id
        seen_ids = set()
        options = []

        for row in members:
            idol_id = row["idol_id"]
            if idol_id in seen_ids:
                continue  # ya lo agregamos
            seen_ids.add(idol_id)
            label = f"{row['idol_name']} ({idol_id})"
            options.append(discord.SelectOption(label=label, value=idol_id))

        view = discord.ui.View()
        view.add_item(RemoveIdolSelector(self.group_id, self.user_id, options))

        await interaction.response.edit_message(
            content=get_translation(language, "group_create.select_to_remove"),
            embed=None,
            view=view
        )

class RemoveIdolSelector(discord.ui.Select):
    def __init__(self, group_id, user_id, options):
        super().__init__(placeholder="Select idol", options=options)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        idol_id = str(self.values[0])
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM groups_members WHERE group_id = $1 AND idol_id = $2", self.group_id, idol_id)

        await send_group_creation_ui(interaction, self.group_id, self.user_id, from_callback=True, language=await get_user_language(interaction.user.id))

class CancelButton(discord.ui.Button):
    def __init__(self, group_id, user_id):
        super().__init__(label="❌", style=discord.ButtonStyle.secondary)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM groups WHERE group_id = $1 AND user_id = $2", self.group_id, self.user_id)
            await conn.execute("DELETE FROM groups_members WHERE group_id = $1 AND user_id = $2", self.group_id, self.user_id)

        await interaction.response.edit_message(content=get_translation(language, "group_create.cancelled"),
                                                embed=None,
                                                view=None)

class ConfirmButton(discord.ui.Button):
    def __init__(self, group_id, user_id):
        super().__init__(label="✅", style=discord.ButtonStyle.secondary)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        async with pool.acquire() as conn:
            group = await conn.fetchrow("SELECT * FROM groups WHERE group_id = $1", self.group_id)
            name = group["name"]
            members = await conn.fetch("SELECT ib.idol_name FROM groups_members gm JOIN idol_base ib ON gm.idol_id = ib.idol_id WHERE gm.group_id = $1", self.group_id)
            member_names = [row["idol_name"] for row in members]
            member_count = len(member_names)
            existing = await conn.fetchval("SELECT COUNT(*) FROM groups WHERE user_id = $1 AND status = 'active'", self.user_id)
            cost = 10000 if existing else 0
            credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", self.user_id)

        if not name:
            await show_error(interaction, self.user_id, self.group_id,
                             get_translation(language, "group_create.add_name"))
            return

        if member_count == 0:
            await show_error(interaction, self.user_id, self.group_id,
                             get_translation(language, "group_create.add_members"))
            return

        if credits < cost:
            await show_error(interaction, self.user_id, self.group_id,
                             get_translation(language, "group_create.not_enough_credits"))
            return

        description = get_translation(language, "group_create.sure_to_create")
        description += get_translation(language, "group_create.name", name=name)
        description += get_translation(language, "group_create.members", member_count=member_count)
        description += get_translation(language, "group_create.cost", cost=cost)
        description += get_translation(language, "group_create.credits", credits=credits)
        description += get_translation(language, "group_create.warning")

        embed = discord.Embed(title=get_translation(language, "group_create.final_confirm"), description=description, color=discord.Color.green())
        view = FinalConfirmationView(self.group_id, self.user_id, name, cost)
        await interaction.response.edit_message(embed=embed, view=view)

class FinalConfirmationView(discord.ui.View):
    def __init__(self, group_id, user_id, name, cost):
        super().__init__(timeout=60)
        self.add_item(ReallyConfirmButton(group_id, user_id, name, cost))
        self.add_item(ReturnToMainButton(group_id, user_id))

class ReallyConfirmButton(discord.ui.Button):
    def __init__(self, group_id, user_id, name, cost):
        super().__init__(label="☑️", style=discord.ButtonStyle.success)
        self.group_id = group_id
        self.user_id = user_id
        self.name = name
        self.cost = cost

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            if self.cost > 0:
                await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", self.cost, self.user_id)
            await conn.execute("UPDATE groups SET status = 'active', name = $1 WHERE group_id = $2", self.name, self.group_id)
        await interaction.response.edit_message(content=f"✅ ¡Grupo **{self.name}** creado con éxito!", embed=None, view=None)

async def show_error(interaction, user_id, group_id, message: str):
    embed = discord.Embed(title="❌ Error", description=message, color=discord.Color.red())
    view = discord.ui.View()
    view.add_item(ReturnToMainButton(group_id, user_id))
    await interaction.response.edit_message(content="",embed=embed, view=view)
    
class ReturnToMainButton(discord.ui.Button):
    def __init__(self, group_id, user_id):
        super().__init__(label="⬅️", style=discord.ButtonStyle.secondary)
        self.group_id = group_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(interaction.user.id)
        await send_group_creation_ui(interaction, self.group_id, self.user_id, from_callback=True, language=await get_user_language(interaction.user.id))

# Classes for `/group list`:
class GroupPaginator:
    def __init__(self, groups: list, interaction: discord.Interaction, language: str, embeds_per_page: int = 3):
        self.groups = groups
        self.interaction = interaction
        self.language = language
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(groups) + embeds_per_page - 1) // embeds_per_page

    def get_page_items(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        return self.groups[start:end]

    def get_embeds_and_view(self):
        page_items = self.get_page_items()
        embeds = []
        view = discord.ui.View(timeout=300)

        for group in page_items:
            
            popularity = group['popularity'] + group['permanent_popularity']
            group_member_count = group['member_count']
            unpaid_weeks = get_translation(self.language, "group_list.paid_up1") if group['unpaid_weeks'] == 0 else f'{group['unpaid_weeks']} '+get_translation(self.language, "group_list.unpaid_weeks")
            
            embed = discord.Embed(title=group["name"] or "n/a", color=discord.Color.blurple())
            embed.add_field(name=get_translation(self.language,"group_list.member_count", group_member_count=group_member_count),
                            value=get_translation(self.language,"group_list.popularity_total",popularity=popularity),
                            inline=True)
            embed.add_field(name=f"📊 {get_translation(self.language, "utilities."+str(group["status"]))}",
                            value=f"💵 {unpaid_weeks}",
                            inline=True)
            embeds.append(embed)

            # Botón individual por grupo
            view.add_item(GroupDetailButton(
                group_id=group["group_id"],
                user_id=group["user_id"],
                group_name=group["name"] or "n/a",
                paginator=self,
                language=self.language
            ))

        # Botones de paginación
        view.add_item(PreviousPageButton(self))
        view.add_item(NextPageButton(self))

        # Embed con página
        footer_embed = discord.Embed(
            description=f"### Total: {len(self.groups)}"+ get_translation(self.language, "utilities.page") + f"{self.current_page + 1} / {self.total_pages}",
            color=discord.Color.dark_gray()
        )
        embeds.append(footer_embed)

        return embeds, view

    async def start(self):
        embeds, view = self.get_embeds_and_view()
        await self.interaction.response.send_message(embeds=embeds, view=view, ephemeral=True)

    async def update(self, interaction: discord.Interaction):
        embeds, view = self.get_embeds_and_view()
        await interaction.response.edit_message(embeds=embeds, view=view)

class PreviousPageButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="◀️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page - 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class NextPageButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="▶️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page + 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class GroupDetailButton(discord.ui.Button):
    def __init__(self, group_id: str, user_id: int, group_name: str, paginator, language: str):
        super().__init__(label=group_name[:80], style=discord.ButtonStyle.primary)
        self.group_id = group_id
        self.user_id = user_id
        self.paginator = paginator
        self.language = language

    async def callback(self, interaction: discord.Interaction):

        pool = get_pool()
        async with pool.acquire() as conn:
            group = await conn.fetchrow("""
                SELECT * FROM groups WHERE group_id = $1
            """, self.group_id)

            members = await conn.fetch("""
                SELECT gm.idol_id, gm.weekly_payment, ib.name
                FROM groups_members gm
                JOIN idol_base ib ON gm.idol_id = ib.idol_id
                WHERE gm.group_id = $1
                ORDER BY ib.name
            """, self.group_id)
            
            # Payment
            unpaid_weeks_n = await conn.fetchval("SELECT unpaid_weeks FROM groups WHERE group_id = $1", self.group_id)
            disabled_payment = unpaid_weeks_n <= 0
            
            members_payment = await conn.fetch("SELECT weekly_payment FROM groups_members WHERE group_id = $1", self.group_id)
            group_payment = await conn.fetchval("SELECT weekly_payment FROM groups WHERE group_id = $1", self.group_id)
            
            total_payment = 0
            if group_payment and members_payment:
                total_payment = int(group_payment)
                for m in members_payment:
                    total_payment += m['weekly_payment']
                total_payment = int(total_payment*unpaid_weeks_n*(1.02**(unpaid_weeks_n-1)))

        user = await interaction.client.fetch_user(group["user_id"])
        popularity = str(group["popularity"])
        perm_popularity = str(group['permanent_popularity'])
        weekly_payment = int(group['weekly_payment'])
        
        for m in members:
            weekly_payment += m['weekly_payment']
        
        group_name = group['name']
        user_mention = user.mention
        
        embed = discord.Embed(
            title=get_translation(self.language, "group_list.title_details", group_name=group_name),
            description=get_translation(self.language, "group_list.managed_by", user_mention=user_mention),
            color=discord.Color.gold()
        )
        
        unpaid_weeks = get_translation(self.language, "group_list.paid_up2") if group['unpaid_weeks'] == 0 else f'⚠️ {group['unpaid_weeks']} ' + get_translation(self.language, "group_list.unpaid_weeks")
        group_status = get_translation(self.language, "utilities."+str(group["status"]))
        no_members = get_translation(self.language, "group_list.no_members")
        
        embed.add_field(name=f"🌟: {popularity}",
                        value=f"🏆: {perm_popularity}",
                        inline=True)
        embed.add_field(name=get_translation(self.language,"group_list.weekly_payment",weekly_payment=weekly_payment),
                        value=f"{unpaid_weeks}",
                        inline=True)
        embed.add_field(name=f"📊: {group_status}",
                        value=f"",
                        inline=True)
        embed.add_field(name=get_translation(self.language, "group_list.members"),
                        value="\n".join([f"• {row['name']} ({row['idol_id']})" for row in members]) or no_members,
                        inline=False)
        embed.add_field(name=f"",
                        value=f"",
                        inline=False)

        label_back = get_translation(self.language, "utilities.back")
        view = discord.ui.View()
        view.add_item(ShowCardsButton(self.group_id, self.language))
        view.add_item(BackToListButton(self.paginator if hasattr(self, 'paginator') else None, label=label_back))
        
        if group["user_id"] == interaction.user.id:
            view.add_item(AddMemberButton(self.group_id))
            view.add_item(RemoveMemberButton(self.group_id))
            view.add_item(PayGroupButton(self.group_id, disabled=disabled_payment, payment=total_payment))
            #view.add_item(StatusButton(self.group_id))
            #view.add_item(RenameGroupButton(self.group_id))
        
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

# - Add member
class AddMemberButton(discord.ui.Button):
    def __init__(self, group_id: str):
        super().__init__(label="➕👤", style=discord.ButtonStyle.success, row=1)
        self.group_id = group_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT DISTINCT group_name FROM idol_group ORDER BY group_name"
            )
        group_names = [r["group_name"] for r in records]

        paginator = AddMemberGroupPaginator(self.group_id, group_names, embeds_per_page=5)
        await paginator.start(interaction)

class AddMemberGroupPaginator:
    def __init__(self, group_id: str, group_names: list[str], embeds_per_page: int = 5):
        self.group_names = group_names
        self.embeds_per_page = embeds_per_page
        self.group_id = group_id
        self.current_page = 0
        self.total_pages = (len(group_names) + embeds_per_page - 1) // embeds_per_page

    async def get_current_embeds(self) -> list[discord.Embed]:
        pool = get_pool()
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        embeds = []
        
        for name in self.group_names[start:end]:
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM idol_group WHERE group_name = $1", name)
            embed = discord.Embed(
                title=name,
                description=f"Integrantes: **{len(rows)}**",
                color=discord.Color.blue()
            )
            embeds.append(embed)
        footer = discord.Embed(
            description=f"Página {self.current_page+1} / {self.total_pages}",
            color=discord.Color.dark_gray()
        )
        embeds.append(footer)
        return embeds

    async def get_view(self) -> discord.ui.View:
        pool = get_pool()
        async with pool.acquire() as conn:
            user_id = await conn.fetchval("SELECT user_id FROM groups WHERE group_id = $1", self.group_id)
        language = await get_user_language(user_id)

        view = discord.ui.View(timeout=120)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        for name in self.group_names[start:end]:
            view.add_item(AddMemberGroupSelectButton(name, self))
        view.add_item(AddMemberPrevButton(self))
        view.add_item(AddMemberNextButton(self))
        view.add_item(BackToDetailsButton(self.group_id, language))
            
        return view

    async def start(self, interaction: discord.Interaction):
        embeds = await self.get_current_embeds()
        await interaction.response.edit_message(embeds=embeds, view=await self.get_view())

    async def update(self, interaction: discord.Interaction):
        embeds = await self.get_current_embeds()
        await interaction.response.edit_message(embeds=embeds, view=await self.get_view())

class AddMemberPrevButton(discord.ui.Button):
    def __init__(self, paginator: AddMemberGroupPaginator):
        super().__init__(label="◀️", style=discord.ButtonStyle.secondary, row=1)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page - 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class AddMemberNextButton(discord.ui.Button):
    def __init__(self, paginator: AddMemberGroupPaginator):
        super().__init__(label="▶️", style=discord.ButtonStyle.secondary, row=1)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page + 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class AddMemberGroupSelectButton(discord.ui.Button):
    def __init__(self, group_name: str, paginator: AddMemberGroupPaginator):
        super().__init__(label=group_name, style=discord.ButtonStyle.primary, row=0)
        self.group_name = group_name
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            user_id = await conn.fetchval(
                "SELECT user_id FROM groups WHERE group_id = $1",
                self.paginator.group_id
            )
            idols = await conn.fetch(
                "SELECT idol_id, idol_name FROM idol_group WHERE group_name = $1 ORDER BY idol_id",
                self.group_name
            )
        language = await get_user_language(user_id)
        
        view = discord.ui.View(timeout=120)
        for idol in idols:
            group_id = self.paginator.group_id
            async with pool.acquire() as conn:
                members = await conn.fetch("SELECT idol_id FROM groups_members WHERE group_id = $1 ORDER BY idol_id", group_id)
            
            disabled = False
            for m in members:
                if idol['idol_id'] == m['idol_id']:
                    disabled = True
            
            label = f"{idol['idol_name']} ({idol['idol_id']})"
            view.add_item(
                SelectMemberToAddButton(group_id=self.paginator.group_id,
                    idol_id=idol['idol_id'],
                    label=label,
                    paginator=self.paginator,
                    disabled = disabled))
            
        view.add_item(BackToDetailsButton(
                group_id=self.paginator.group_id,
                language=language))
        
        await interaction.response.edit_message(
            content=get_translation(language, "group_manage.select_idol", selected_group=self.group_name),
            embed=None,
            view=view
        )

class SelectMemberToAddButton(discord.ui.Button):
    def __init__(
        self,
        group_id: str,
        idol_id: str,
        label: str,
        paginator: AddMemberGroupPaginator,
        disabled: bool
    ):
        super().__init__(label=label, style=discord.ButtonStyle.primary if not disabled else discord.ButtonStyle.danger, disabled=disabled)
        self.group_id = group_id
        self.idol_id = idol_id
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            user_id = await conn.fetchval(
                "SELECT user_id FROM groups WHERE group_id = $1",
                self.group_id)
        language = await get_user_language(user_id)
        
        view = discord.ui.View(timeout=60)
        view.add_item(ConfirmAddIdolButton(
                group_id=self.group_id,
                idol_id=self.idol_id,
                label=self.label,
                paginator=self.paginator))
        
        view.add_item(BackToDetailsButton(group_id=self.group_id,
                language=language))

        await interaction.response.edit_message(
            content=get_translation(language,
                "group_manage.confirm_add_idol",
                idol=self.label),
            embed=None,
            view=view)

class ConfirmAddIdolButton(discord.ui.Button):
    def __init__(self, group_id: str, idol_id: str, label: str, paginator: AddMemberGroupPaginator):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.group_id = group_id
        self.idol_id = idol_id
        self.label_text = label
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            user_id = await conn.fetchval("SELECT user_id FROM groups WHERE group_id = $1", self.group_id)
            language = await get_user_language(user_id)

            count = await conn.fetchval(
                "SELECT COUNT(*) FROM groups_members WHERE group_id = $1",
                self.group_id
            )
            if count >= 24:
                await interaction.response.send_message(
                    get_translation(language, "group_manage.error_group_full"),
                    ephemeral=True
                )
                return

            # Verificar si el idol ya está en el grupo
            already = await conn.fetchval(
                "SELECT 1 FROM groups_members WHERE group_id = $1 AND idol_id = $2",
                self.group_id, self.idol_id
            )
            idol_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", self.idol_id)
            if already:
                await interaction.response.send_message(
                    get_translation(language, "group_manage.error_idol_already_in_group", idol_Id=self.idol_id, idol_name=idol_name),
                    ephemeral=True
                )
                return

            await conn.execute("UPDATE groups SET permanent_popularity = 0 WHERE group_id = $1", self.group_id)
            
            await conn.execute(
                """
                INSERT INTO groups_members (group_id, user_id, idol_id)
                VALUES ($1, $2, $3)
                """,
                self.group_id, user_id, self.idol_id
            )
            
            rows = await conn.fetch("""
                SELECT group_id, name, popularity, permanent_popularity, status, unpaid_weeks, user_id,
                    (SELECT COUNT(*) FROM groups_members WHERE group_id = g.group_id) AS member_count
                FROM groups g
                WHERE user_id = $1
                ORDER BY creation_date DESC
            """, user_id)

        button = GroupDetailButton(
            group_id=self.group_id,
            user_id=interaction.user.id,
            group_name="",
            paginator=GroupPaginator(rows, interaction=interaction, language=language),
            language=language
        )
        await button.callback(interaction)


# - Remove member
class RemoveMemberButton(discord.ui.Button):
    def __init__(self, group_id: str):
        super().__init__(label="➖👤", style=discord.ButtonStyle.danger, row=1)
        self.group_id = group_id
        
    async def callback(self, interaction):
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        pool = get_pool()
        async with pool.acquire() as conn:
            group_members = await conn.fetch(
                "SELECT idol_id FROM groups_members WHERE group_id = $1 ORDER BY idol_id",
                self.group_id
            )
        
        view = discord.ui.View(timeout=60)
        for idol in group_members:
            async with pool.acquire() as conn:
                idol_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", idol['idol_id'])
            
            view.add_item(SelectMemberToRemoveButton(
                self.group_id, idol['idol_id'], idol_name
            ))
            
        view.add_item(BackToDetailsButton(self.group_id, language))

        await interaction.response.edit_message(
            content=get_translation(language, "group_manage.select_idol_remove"),
            view=view,
            embed=None
        )

class SelectMemberToRemoveButton(discord.ui.Button):
    def __init__(self, group_id: str, idol_id, idol_name):
        super().__init__(label=f"{idol_name} ({idol_id})", style=discord.ButtonStyle.danger)
        self.group_id = group_id
        self.idol_id = idol_id
        self.idol_name = idol_name
        
    async def callback(self, interaction):
        language = await get_user_language(interaction.user.id)
        idol = f"{self.idol_name} ({self.idol_id})"
        
        view = discord.ui.View(timeout=60)
        view.add_item(ConfirmRemoveIdolButton(
            self.group_id, self.idol_id
        ))
        view.add_item(BackToDetailsButton(self.group_id, language))
        

        await interaction.response.edit_message(
            content=get_translation(language, "group_manage.confirm_remove_idol", idol=idol),
            view=view,
            embed=None
        )

class ConfirmRemoveIdolButton(discord.ui.Button):
    def __init__(self, group_id, idol_id):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.danger)
        self.group_id = group_id
        self.idol_id = idol_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        
        async with pool.acquire() as conn:
            member_items = await conn.fetchrow("""
                SELECT mic_id, outfit_id, accessory_id, consumable_id
                FROM groups_members WHERE group_id = $1 AND idol_id = $2""",
                self.group_id, self.idol_id)

            for mi in member_items:
                if mi:
                    id, u_id = mi.split(".")
                    await conn.execute("UPDATE user_item_cards SET status = 'available' WHERE unique_id = $1", u_id)

            member_card = await conn.fetchrow("SELECT card_id FROM groups_members WHERE group_id = $1 AND idol_id = $2",
                                              self.group_id, self.idol_id)
            if member_card:
                card_id, unique_id = member_card['card_id'].split(".")
                await conn.execute("UPDATE user_idol_cards SET status = 'available' WHERE unique_id = $1", unique_id)
            
            await conn.execute("""
                DELETE FROM groups_members WHERE group_id = $1 AND idol_id = $2
            """, self.group_id, self.idol_id)
            
            await conn.execute("UPDATE groups SET permanent_popularity = 0 WHERE group_id = $1", self.group_id)


            rows = await conn.fetch("""
                SELECT group_id, name, popularity, permanent_popularity, status, unpaid_weeks, user_id,
                    (SELECT COUNT(*) FROM groups_members WHERE group_id = g.group_id) AS member_count
                FROM groups g
                WHERE user_id = $1
                ORDER BY creation_date DESC
            """, user_id)

        button = GroupDetailButton(
            group_id=self.group_id,
            user_id=user_id,
            group_name="",
            paginator=GroupPaginator(rows, interaction=interaction, language=language),
            language=language
        )
        await button.callback(interaction)

            

# - Change Status
class StatusButton(discord.ui.Button):
    def __init__(self, group_id: str):
        super().__init__(label="Estado", style=discord.ButtonStyle.secondary, row=1)
        self.group_id = group_id

    async def callback(self, interaction):
        await interaction.response.send_message("⚙️ Cambiar estado (pendiente)", ephemeral=True)

# - Rename
class RenameGroupButton(discord.ui.Button):
    def __init__(self, group_id: str):
        super().__init__(label="📝", style=discord.ButtonStyle.secondary, row=1)
        self.group_id = group_id

    async def callback(self, interaction):
        await interaction.response.send_message("⚙️ Renombrar grupo (pendiente)", ephemeral=True)

# - Pay group
class PayGroupButton(discord.ui.Button):
    def __init__(self, group_id: str, disabled, payment):
        super().__init__(label=f"${payment}", emoji="💸", style=discord.ButtonStyle.success, disabled=disabled, row=1)
        self.group_id = group_id

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        
        async with pool.acquire() as conn:
            unpaid_weeks = await conn.fetchval("SELECT unpaid_weeks FROM groups WHERE group_id = $1", self.group_id)
        # Protección adicional en caso de que logren presionarlo igual
        if unpaid_weeks == 0:
            embed = discord.Embed(
                description="✅ Este grupo ya está al corriente en sus pagos.",
                color=discord.Color.green()
            )
            view = BackToDetailsButton(self.group_id, language)
            await interaction.response.edit_message(embed=embed, view=view)
            return

        await interaction.response.send_modal(PayWeeksModal(self.group_id, unpaid_weeks))

class PayWeeksModal(discord.ui.Modal, title="Weekly payments"):
    def __init__(self, group_id, unpaid_weeks):
        super().__init__()
        self.group_id = group_id
        self.unpaid_weeks = unpaid_weeks
        self.input = discord.ui.TextInput(label="¿Cuántas semanas quieres pagar?", placeholder=f"Max. {unpaid_weeks}", min_length=1, max_length=2)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        view = discord.ui.View()
        try:
            weeks_to_pay = int(self.input.value)
        except ValueError:
            view.add_item(BackToDetailsButton(self.group_id, language))
            await interaction.response.edit_message(content="❌ Entrada inválida. Usa solo números.", view=view, embed=None)
            return

        unpaid_weeks = self.unpaid_weeks
        if weeks_to_pay > unpaid_weeks or weeks_to_pay <= 0:
            view.add_item(BackToDetailsButton(self.group_id, language))
            await interaction.response.edit_message(content="⚠️ Número de semanas no válido.", view=view, embed=None)
            return
        
        async with pool.acquire() as conn:
            members_payment = await conn.fetch("SELECT weekly_payment FROM groups_members WHERE group_id = $1", self.group_id)
            group_payment = await conn.fetchval("SELECT weekly_payment FROM groups WHERE group_id = $1", self.group_id)
            
            weekly_total = 0
            if group_payment and members_payment:
                weekly_total = int(group_payment)
                for m in members_payment:
                    weekly_total += m['weekly_payment']
        cost = int(weekly_total*unpaid_weeks*(1.02**(unpaid_weeks-1))-weekly_total*(unpaid_weeks-weeks_to_pay)*(1.02**((unpaid_weeks-weeks_to_pay)-1)))

        confirm_view = discord.ui.View()
        confirm_view.add_item(ConfirmPayWeeksButton(self.group_id, cost, weeks_to_pay))
        confirm_view.add_item(BackToDetailsButton(self.group_id, language))
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"¿Confirmas pagar **{weeks_to_pay} semanas** por **💵 {cost}**?",
                color=discord.Color.orange()
            ),
            view=confirm_view
        )
        
class ConfirmPayWeeksButton(discord.ui.Button):
    def __init__(self, group_id, cost, weeks_to_pay):
        super().__init__(label=f"", emoji="✅", style=discord.ButtonStyle.primary)
        self.group_id = group_id
        self.cost = cost
        self.weeks_to_pay = weeks_to_pay
    
    async def callback(self, interaction:discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        user_id = interaction.user.id
        
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", self.cost, user_id)
            
            await conn.execute("UPDATE groups SET unpaid_weeks = unpaid_weeks - $1 WHERE group_id = $2", self.weeks_to_pay, self.group_id)
            
            rows = await conn.fetch("""
                SELECT group_id, name, popularity, permanent_popularity, status, unpaid_weeks, user_id,
                    (SELECT COUNT(*) FROM groups_members WHERE group_id = g.group_id) AS member_count
                FROM groups g
                WHERE user_id = $1
                ORDER BY creation_date DESC
            """, user_id)
        # Simula un clic en el botón de detalles
        button = GroupDetailButton(
            group_id=self.group_id,
            user_id=user_id,
            group_name="",
            paginator=GroupPaginator(rows, interaction=interaction, language=language),
            language=language
        )
        await button.callback(interaction)


# -- Back to list
class BackToListButton(discord.ui.Button):
    def __init__(self, paginator, label):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        if self.paginator:
            await self.paginator.update(interaction)

class ShowCardsButton(discord.ui.Button):
    def __init__(self, group_id: str, language: str):
        label = get_translation(language, "group_list.view_cards")
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.group_id = group_id
        self.language = language

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT gm.idol_id, ib.name,
                    gm.card_id, gm.mic_id, gm.outfit_id, gm.accessory_id, gm.consumable_id
                FROM groups_members gm
                JOIN idol_base ib ON gm.idol_id = ib.idol_id
                WHERE gm.group_id = $1
                ORDER BY ib.name
            """, self.group_id)

        if not rows:
            embed = discord.Embed(
                description=get_translation(self.language, "group_list.no_members"),
                color=discord.Color.orange()
            )
            view = discord.ui.View()
            view.add_item(BackToDetailsButton(group_id=self.group_id, language=self.language))
            await interaction.response.edit_message(embed=embed, view=view)
            return

        paginator = EquippedCardsPaginator(members=rows, interaction=interaction, group_id=self.group_id, language=self.language)
        await paginator.start()
        
class EquippedCardsPaginator:
    def __init__(self, members: list, interaction: discord.Interaction, group_id: str, language: str, per_page: int = 3):
        self.members = members
        self.interaction = interaction
        self.group_id = group_id
        self.language = language
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(members) + per_page - 1) // per_page
        self.guild = interaction.guild

    async def get_current_embeds(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_members = self.members[start:end]
        pool = get_pool()
        embeds = []
        for row in page_members:
            async with pool.acquire() as conn:
                card_id=u_c=mic_id=outfit_id=accessory_id=consumable_id=""
                if row['card_id']:
                    card_id, u_c = row['card_id'].split(".")
                if row['mic_id']:
                    mic_id, um = row['mic_id'].split(".")
                if row['outfit_id']:
                    outfit_id, uo = row['outfit_id'].split(".")
                if row['accessory_id']:
                    accessory_id, ua = row['accessory_id'].split(".")
                if row['consumable_id']:
                    consumable_id, uc = row['consumable_id'].split(".")
                card_data = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", card_id)
                idol_data = await conn.fetchrow("SELECT * FROM idol_base WHERE idol_id = $1", row['idol_id'])
                user_card_data = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", u_c)
                
                mic_durability=outfit_durability=accessory_durability=consumable_durability=""
                mic_name=outfit_name=accessory_name=consumale_name="n/a"
                card_name = ""
                if card_data:
                    c_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", card_data['idol_id'])
                    card_name = f"`{c_name} -"
                    
                mic_data = await conn.fetchrow(
                    "SELECT * FROM cards_item WHERE item_id = $1",
                    mic_id)
                if mic_data:
                    mic_name = mic_data['name']
                    mic_durability += "⏳"
                    mic_durability += str(await conn.fetchval("SELECT durability FROM user_item_cards WHERE unique_id = $1", um))
                    
                outfit_data = await conn.fetchrow(
                    "SELECT * FROM cards_item WHERE item_id = $1",
                    outfit_id)
                if outfit_data:
                    outfit_name = outfit_data['name']
                    outfit_durability += "⏳"
                    outfit_durability += str(await conn.fetchval("SELECT durability FROM user_item_cards WHERE unique_id = $1", uo))
                
                accessory_data = await conn.fetchrow(
                    "SELECT * FROM cards_item WHERE item_id = $1",
                    accessory_id)
                if accessory_data:
                    accessory_name = accessory_data['name']
                    accessory_durability += "⏳"
                    accessory_durability += str(await conn.fetchval("SELECT durability FROM user_item_cards WHERE unique_id = $1", ua))
                
                consumale_data = await conn.fetchrow(
                    "SELECT * FROM cards_item WHERE item_id = $1",
                    consumable_id)
                if consumale_data:
                    consumale_name = consumale_data['name']
                    consumable_durability += "⏳"
                    consumable_durability += str(await conn.fetchval("SELECT durability FROM user_item_cards WHERE unique_id = $1", uc))
                
            
            idol = f"🃏 {get_translation(self.language,"utilities.idol_card")}: {card_name} {card_data['set_name'] if card_data else "`n/a`"} {f"- {card_data['rarity_id']}`" if card_data else ""}\n"
            mic = f"🎤 {get_translation(self.language,"utilities.mic")}: `{mic_name}` {mic_durability}\n"
            outfit = f"👗 {get_translation(self.language,"utilities.outfit")}: `{outfit_name}` {outfit_durability}\n"
            accesory = f"💍 {get_translation(self.language,"utilities.accesory")}: `{accessory_name}` {accessory_durability}\n"
            consumable = f"🍬 {get_translation(self.language,"utilities.consumable")}: `{consumale_name}` {consumable_durability}"

            embed = discord.Embed(title=row["name"], color=discord.Color.green())
            embed.add_field(name=f"{get_translation(self.language, "group_list.equipped_cards")}", value=idol+mic+outfit+accesory+consumable, inline=False)
            if card_data:
                url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}"
                embed.set_thumbnail(url=url)
            embeds.append(embed)
            vocal=rap=dance=visual=energy=plus_vocal=plus_rap=plus_dance=plus_visual=plus_energy=0
            p_vocal=p_rap=p_dance=p_visual=p_energy=""
            skills = "n/a"
            if card_data:
                vocal += card_data['vocal']
                rap += card_data['rap']
                dance += card_data['dance']
                visual += card_data['visual']
                energy += card_data['energy']
                if user_card_data:
                    skills = ""
                    if user_card_data['p_skill']:
                        skills += f"{discord.utils.get(self.guild.emojis, name="PassiveSkill")} "
                    if user_card_data['a_skill']:
                        skills += f"{discord.utils.get(self.guild.emojis, name="ActiveSkill")} "
                    if user_card_data['s_skill']:
                        skills += f"{discord.utils.get(self.guild.emojis, name="SupportSkill")} "
                    if user_card_data['u_skill']:
                        skills += f"{discord.utils.get(self.guild.emojis, name="UltimateSkill")} "
            else:
                vocal += idol_data['vocal']
                rap += idol_data['rap']
                dance += idol_data['dance']
                visual += idol_data['visual']
                energy += 50
            items_data = [mic_data,outfit_data,accessory_data,consumale_data]
            for id in items_data:
                if id:
                    plus_vocal += id['plus_vocal']
                    if plus_vocal > 0:
                        p_vocal = f" (+{plus_vocal})"
                    elif plus_vocal < 0:
                        p_vocal = f" ({plus_vocal})"
                        
                    plus_rap += id['plus_rap']
                    if plus_rap > 0:
                        p_rap = f" (+{plus_rap})"
                    elif plus_rap < 0:
                        p_rap = f" ({plus_rap})"
                        
                    plus_dance += id['plus_dance']
                    if plus_dance > 0:
                        p_dance = f" (+{plus_dance})"
                    elif plus_dance < 0:
                        p_dance = f" ({plus_dance})"
                        
                    plus_visual += id['plus_visual']
                    if plus_visual > 0:
                        p_visual = f" (+{plus_visual})"
                    elif plus_visual < 0:
                        p_visual = f" ({plus_visual})"
                        
                    plus_energy += id['plus_energy']
                    if plus_energy > 0:
                        p_energy = f" (+{plus_energy})"
                    elif plus_energy < 0:
                        p_energy = f" ({plus_energy})"
            
            embed.add_field(name=f"**🎤 Vocal: {vocal}{p_vocal}**", value=f"**🎶 Rap: {rap}{p_rap}**", inline=True)
            embed.add_field(name=f"**💃 Dance: {dance}{p_dance}**", value=f"**✨ Visual: {visual}{p_visual}**", inline=True)
            embed.add_field(name=f"**⚡ Energy: {energy}{p_energy}**", value=f"**Skills: {skills}**", inline=True)

        page_info = discord.Embed(
            description=f"### Total: {len(self.members)}\nPage: {self.current_page + 1} / {self.total_pages}",
            color=discord.Color.dark_gray()
        )
        embeds.append(page_info)

        return embeds

    def get_view(self):
        view = discord.ui.View()
        view.add_item(BackToDetailsButton(group_id=self.group_id, language=self.language))
        if self.total_pages > 1:
            view.add_item(PreviousCardsButton(self))
            view.add_item(NextCardsButton(self))
        return view

    async def start(self):
        embeds = await self.get_current_embeds()
        await self.interaction.response.edit_message(embeds=embeds, view=self.get_view())

    async def update(self, interaction: discord.Interaction):
        embeds = await self.get_current_embeds()
        await interaction.response.edit_message(embeds=embeds, view=self.get_view())

# -         
class PreviousCardsButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="⬅️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page - 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class NextCardsButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="➡️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page + 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class BackToDetailsButton(discord.ui.Button):
    def __init__(self, group_id: str, language: str):
        label = get_translation(language, "utilities.back")
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.group_id = group_id
        self.language = language

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            user_id = await conn.fetchval("SELECT user_id FROM groups WHERE group_id = $1", self.group_id)
            
            rows = await conn.fetch("""
                SELECT group_id, name, popularity, permanent_popularity, status, unpaid_weeks, user_id,
                    (SELECT COUNT(*) FROM groups_members WHERE group_id = g.group_id) AS member_count
                FROM groups g
                WHERE user_id = $1
                ORDER BY creation_date DESC
            """, user_id)
        # Simula un clic en el botón de detalles
        button = GroupDetailButton(
            group_id=self.group_id,
            user_id=interaction.user.id,
            group_name="",
            paginator=GroupPaginator(rows, interaction=interaction, language=self.language),
            language=self.language
        )
        await button.callback(interaction)


# - 
async def create_group_embed(language, group, members):
    embed = discord.Embed(
        title=get_translation(language, "group_manage.title", name=group["name"]),
        description="",
        color=discord.Color.orange()
    )
    embed.add_field(name="📊 Estado", value=group["status"], inline=True)
    embed.add_field(name="⭐ Popularidad", value=group["popularity"], inline=True)
    embed.add_field(name="🔥 Permanente", value=group["permanent_popularity"], inline=True)
    embed.add_field(name="💳 Pagos pendientes", value=group["unpaid_weeks"], inline=True)

    # Costos semanales
    weekly_group = group["weekly_payment"]
    weekly_members = sum(m["weekly_payment"] for m in members)
    embed.add_field(name="🪙 Pago semanal total", value=f"{weekly_group + weekly_members}", inline=True)

    # Lista de miembros
    idol_lines = []
    for m in members:
        equipos = [m["card_id"], m["mic_id"], m["outfit_id"], m["accessory_id"], m["consumable_id"]]
        icon = "✅" if any(equipos) else "❌"
        idol_lines.append(f"• {icon} {m['idol_name']} ({m['idol_id']})")
    embed.add_field(name=get_translation(language, "group_list.members"), value="\n".join(idol_lines) or "-", inline=False)

    return embed

async def regenerate_group_view(interaction, group_id, language, paginator):
    pool = get_pool()
    async with pool.acquire() as conn:
        group = await conn.fetchrow("SELECT * FROM groups WHERE group_id = $1", group_id)
        members = await conn.fetch("""
            SELECT gm.*, ib.name AS idol_name
            FROM groups_members gm
            JOIN idol_base ib ON gm.idol_id = ib.idol_id
            WHERE gm.group_id = $1
            ORDER BY gm.idol_id, ib.name
        """, group_id)

    embed = await create_group_embed(language, group, members)
    view = GroupManageView(group, members, language, paginator=paginator)

    await interaction.response.edit_message(content=None, embed=embed, view=view)



class GroupManageView(discord.ui.View):
    def __init__(self, group, members, language, paginator=None):
        super().__init__(timeout=300)
        self.group = group
        self.members = members
        self.language = language
        self.paginator = paginator


class ChangeStatusButton(discord.ui.Button):
    def __init__(self, group, paginator):
        label = "🔴Hiatus" if group["status"] == "active" else "🟢Activate"
        super().__init__(label=label, style=discord.ButtonStyle.success if group['status'] == "active" else discord.ButtonStyle.danger)
        self.group = group
        self.paginator=paginator

    async def callback(self, interaction: discord.Interaction):
        new_status = "inactive" if self.group["status"] == "active" else "active"
        view = ConfirmStatusChangeView(self.group, new_status, self.paginator)
        
        descr = f"¿Deseas activar de nuevo el grupo?\n> Costo: **💵1000**."
        if new_status == "inactive":
            descr = f"¿Deseas enviar el grupo a Hiatus?"
        
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=descr,
                color=discord.Color.orange()
            ),
            view=view
        )

class ConfirmStatusChangeView(discord.ui.View):
    def __init__(self, group, new_status, paginator):
        super().__init__(timeout=60)
        self.group = group
        self.new_status = new_status
        self.paginator = paginator
        self.cost = 1000
        self.add_item(ConfirmButtonStatus(self))
        self.add_item(CancelButtonStatus(self))

class ConfirmButtonStatus(discord.ui.Button):
    def __init__(self, parent):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", self.parent.group["user_id"])
            if credits < self.parent.cost:
                await interaction.response.edit_message(content="❌ Créditos insuficientes.", view=None)
                return
            if self.parent.new_status == "active":
                await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", self.parent.cost, self.parent.group["user_id"])
            await conn.execute("UPDATE groups SET status = $1 WHERE group_id = $2", self.parent.new_status, self.parent.group["group_id"])

        language = await get_user_language(user_id=self.parent.group["user_id"])
        await regenerate_group_view(interaction, self.parent.group["group_id"], language, self.parent.paginator)

class CancelButtonStatus(discord.ui.Button):
    def __init__(self, parent):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.danger)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(user_id=self.parent.group["user_id"])
        await regenerate_group_view(interaction, self.parent.group["group_id"], language, self.parent.paginator)
        
# -
class ChangeNameButton(discord.ui.Button):
    def __init__(self, group, paginator):
        super().__init__(label="📝", style=discord.ButtonStyle.secondary)
        self.group = group
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ChangeNameModal(self.group, self.paginator))

class ChangeNameModal(discord.ui.Modal, title="Change group name"):
    def __init__(self, group, paginator):
        super().__init__()
        self.group = group
        self.paginator = paginator
        self.name_input = discord.ui.TextInput(label="Nuevo nombre", min_length=2, max_length=30, placeholder="Ej: Moonlight Girls")
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value.strip()

        if new_name == self.group["name"]:
            await interaction.response.edit_message(content="⚠️ El nombre es igual al actual.", view=None)
            return

        confirm_view = ConfirmNameChangeView(self.group, new_name, self.paginator)
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"¿Confirmas cambiar el nombre a **{new_name}**?\n⚠️ Esto borrará la popularidad permanente.\n> **Costo:** 💵5000",
                color=discord.Color.orange()
            ),
            view=confirm_view
        )

class ConfirmNameChangeView(discord.ui.View):
    def __init__(self, group, new_name, paginator):
        super().__init__(timeout=60)
        self.group = group
        self.new_name = new_name
        self.cost = 5000
        self.paginator = paginator

        self.add_item(ConfirmButtonName(self, self.paginator))
        self.add_item(CancelButtonName(self, self.paginator))

class ConfirmButtonName(discord.ui.Button):
    def __init__(self, parent, paginator):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.parent = parent
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", self.parent.group["user_id"])
            if credits < self.parent.cost:
                await interaction.response.edit_message(content=f"❌ No tienes suficientes créditos. Requiere {self.parent.cost}, tienes {credits}.", view=None)
                return

            await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", self.parent.cost, self.parent.group["user_id"])
            await conn.execute("UPDATE groups SET name = $1, permanent_popularity = 0 WHERE group_id = $2", self.parent.new_name, self.parent.group["group_id"])

        language = await get_user_language(user_id=self.parent.group["user_id"])
        await regenerate_group_view(interaction, self.parent.group["group_id"], language, self.paginator)

class CancelButtonName(discord.ui.Button):
    def __init__(self, parent):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.danger)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(user_id=self.parent.group["user_id"])
        await regenerate_group_view(interaction, self.parent.group["group_id"], language)

# -
class ConfirmPayWeeksView(discord.ui.View):
    def __init__(self, group, weeks_to_pay, cost, paginator):
        super().__init__(timeout=60)
        self.group = group
        self.weeks_to_pay = weeks_to_pay
        self.cost = cost
        self.paginator = paginator
        self.add_item(ConfirmButtonManage(self))
        self.add_item(CancelButtonManage(self))

class ConfirmButtonManage(discord.ui.Button):
    def __init__(self, parent):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", self.parent.group["user_id"])
            if credits < self.parent.cost:
                await interaction.response.edit_message(content=f"❌ No tienes suficientes créditos.", view=None)
                return

            await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", self.parent.cost, self.parent.group["user_id"])
            await conn.execute("UPDATE groups SET unpaid_weeks = unpaid_weeks - $1 WHERE group_id = $2", self.parent.weeks_to_pay, self.parent.group["group_id"])

        language = await get_user_language(user_id=self.parent.group["user_id"])
        await regenerate_group_view(interaction, self.parent.group["group_id"], language, self.parent.paginator)

class CancelButtonManage(discord.ui.Button):
    def __init__(self, parent):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.danger)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(user_id=self.parent.group["user_id"])
        await regenerate_group_view(interaction, self.parent.group["group_id"], language, self.parent.paginator)

class ReturnToManageView(discord.ui.View):
    def __init__(self, group_id):
        super().__init__(timeout=60)
        self.group_id = group_id
        self.add_item(ReturnToManageButton(group_id))

class ReturnToManageButton(discord.ui.Button):
    def __init__(self, group_id):
        super().__init__(label="🔙", style=discord.ButtonStyle.secondary)
        self.group_id = group_id

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(user_id=interaction.user.id)  # O del owner del grupo si lo prefieres
        await regenerate_group_view(interaction, self.group_id, language)

# -
class ViewMembersButton(discord.ui.Button):
    def __init__(self, group, paginator=None):
        super().__init__(label="👥🔎", style=discord.ButtonStyle.primary)
        self.group = group
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            members = await conn.fetch("""
                SELECT gm.*, ig.idol_name FROM groups_members gm
                JOIN idol_group ig ON gm.idol_id = ig.idol_id
                WHERE gm.group_id = $1
            """, self.group["group_id"])

        embed = discord.Embed(
            title="👥 Integrantes del grupo",
            color=discord.Color.teal()
        )

        for m in members:
            equips = []
            if m["card_id"]: equips.append("🎴 Idol")
            if m["mic_id"]: equips.append("🎤 Mic")
            if m["outfit_id"]: equips.append("👗 Outfit")
            if m["accessory_id"]: equips.append("💍 Accesorio")
            if m["consumable_id"]: equips.append("🍬 Consumible")
            eq_str = ", ".join(equips) if equips else "❌ Nada equipado"
            embed.add_field(
                name=f"{m['idol_name']} ({m['idol_id']})",
                value=eq_str,
                inline=False
            )

        view = ReturnToMainView(self.group, paginator=self.paginator)
        await interaction.response.edit_message(embed=embed, view=view)

class ReturnToMainView(discord.ui.View):
    def __init__(self, group, paginator=None):
        super().__init__(timeout=60)
        self.group = group
        self.add_item(ReturnButtonMembers(self.group, paginator=paginator))

class ReturnButtonMembers(discord.ui.Button):
    def __init__(self, group, paginator=None):
        super().__init__(label="🔙 Volver", style=discord.ButtonStyle.secondary)
        self.group = group
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(user_id=self.group["user_id"])
        await regenerate_group_view(interaction, self.group["group_id"], language, self.paginator)




async def setup(bot):
    bot.tree.add_command(Group())