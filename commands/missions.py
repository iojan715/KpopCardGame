import discord, random, string
from datetime import timezone, datetime, timedelta
from discord.ext import commands
from discord import app_commands
from utils.language import get_user_language
from utils.localization import get_translation
from db.connection import get_pool

class MissionsGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="missions", description="Comandos para moderación")

    @app_commands.command(name="list", description="Entregar recompensa a un jugador por reporte de error")

    async def missions(self, interaction:discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)

        embed, view = await build_missions_embed_view_for_user(interaction.user.id)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)



class ClaimMissionButton(discord.ui.Button):
    def __init__(self, user_mission_id: int, mission_number: int, owner_id: int, *, disabled: bool):
        super().__init__(
            label=f"Reclamar #{mission_number}",
            style=discord.ButtonStyle.green,
            custom_id=f"cancel_{user_mission_id}",
            disabled=disabled
        )
        self.user_mission_id = user_mission_id
        self.mission_number = mission_number
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):

        confirm_embed = discord.Embed(
            title="Completar mision",
            description=f"¿Deseas completar la misión #{self.mission_number}?",
            color=discord.Color.dark_grey()
        )
        confirm_view = ConfirmClaimView(self.user_mission_id, self.mission_number, self.owner_id)

        await interaction.response.edit_message(content=None, embed=confirm_embed, view=confirm_view)

class ConfirmClaimView(discord.ui.View):
    def __init__(self, user_mission_id: int, mission_number: int, owner_id: int):
        super().__init__(timeout=60)
        self.user_mission_id = user_mission_id
        self.mission_number = mission_number
        self.owner_id = owner_id

    @discord.ui.button(label="Reclamar", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):

        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM user_missions WHERE id = $1", self.user_mission_id)
            if not row:
                await interaction.response.edit_message(content="No se encontró la misión (posiblemente ya fue modificada).", embed=None, view=None)
                return
            if row["status"] != "active":
                embed, view = await build_missions_embed_view_for_user(self.owner_id)
                await interaction.response.edit_message(content="La misión ya no se encuentra activa", embed=embed, view=view)
                return

            now = datetime.now(timezone.utc)
            reward = random.choice(("pack", "redeemable", "credits"))
            
            reward_desc = ""
            
            if reward == "pack":
                while True:
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    exists = await conn.fetchval("SELECT 1 FROM players_packs WHERE unique_id = $1", new_id)
                    if not exists:
                        break
                reward_d = await conn.fetchval("SELECT name FROM packs WHERE pack_id = $1", row['pack_id'])
                reward_desc = f"📦 {reward_d}"
                await conn.execute("""
                    INSERT INTO players_packs (
                        unique_id, user_id, pack_id, buy_date
                    ) VALUES ($1, $2, $3, $4)
                """, new_id, interaction.user.id, row['pack_id'], now)
                
            elif reward == "redeemable":
                reward_d = await conn.fetchval("SELECT name FROM redeemables WHERE redeemable_id = $1", row['redeemable_id'])
                reward_desc = f"🎟 {reward_d}"
                await conn.execute("""
                        INSERT INTO user_redeemables (user_id, redeemable_id, quantity, last_updated)
                        VALUES ($1, $2, 1, now())
                        ON CONFLICT (user_id, redeemable_id) DO UPDATE SET
                        quantity = user_redeemables.quantity + 1,
                        last_updated = now()
                    """, interaction.user.id, row["redeemable_id"])
            
            elif reward == "credits":
                reward_desc = f"💵 {row['credits']}"
                await conn.execute(
                    "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                    row['credits'], interaction.user.id)
            
            await conn.execute(
                "UPDATE users SET xp = xp + $1 WHERE user_id = $2",
                row['xp'], interaction.user.id
            )
            
            await conn.execute(
                "UPDATE user_missions SET status = 'completed', last_updated = now() WHERE id = $1",
                self.user_mission_id)

        new_embed, new_view = await build_missions_embed_view_for_user(self.owner_id)
        await interaction.response.edit_message(content=f"## ✅ Misión #{self.mission_number} completada.\nRecompensa: {reward_desc}\n> + {row['xp']} XP", embed=new_embed, view=new_view)

    @discord.ui.button(label="Volver", style=discord.ButtonStyle.secondary)
    async def abort(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed, view = await build_missions_embed_view_for_user(self.owner_id)
        await interaction.response.edit_message(content=None, embed=embed, view=view)



class CancelMissionButton(discord.ui.Button):
    def __init__(self, user_mission_id: int, mission_number: int, owner_id: int, *, disabled: bool):
        super().__init__(
            label=f"Cancelar #{mission_number}",
            style=discord.ButtonStyle.danger,
            custom_id=f"cancel_{user_mission_id}",
            disabled=disabled
        )
        self.user_mission_id = user_mission_id
        self.mission_number = mission_number
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):

        confirm_embed = discord.Embed(
            title="⚠️ Confirmar cancelación",
            description=f"¿Estás seguro de que quieres cancelar la misión #{self.mission_number}? Esta acción marcará la misión como cancelada.",
            color=discord.Color.orange()
        )
        confirm_view = ConfirmCancelView(self.user_mission_id, self.mission_number, self.owner_id)

        await interaction.response.edit_message(content=None, embed=confirm_embed, view=confirm_view)

class ConfirmCancelView(discord.ui.View):
    def __init__(self, user_mission_id: int, mission_number: int, owner_id: int):
        super().__init__(timeout=60)
        self.user_mission_id = user_mission_id
        self.mission_number = mission_number
        self.owner_id = owner_id

    @discord.ui.button(label="Confirmar cancelación", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):

        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, status FROM user_missions WHERE id = $1", self.user_mission_id)
            if not row:
                # editar el mismo mensaje para indicar error
                await interaction.response.edit_message(content="No se encontró la misión (posiblemente ya fue modificada).", embed=None, view=None)
                return
            if row["status"] != "active":
                # regenerar vista principal para reflejar el cambio
                embed, view = await build_missions_embed_view_for_user(self.owner_id)
                await interaction.response.edit_message(content=None, embed=embed, view=view)
                return

            # marcar como cancelada
            await conn.execute("UPDATE user_missions SET status = 'cancelled', last_updated = now() WHERE id = $1", self.user_mission_id)

        # regenerar embed + view actualizados y editar el mismo mensaje
        new_embed, new_view = await build_missions_embed_view_for_user(self.owner_id)
        await interaction.response.edit_message(content=f"✅ Misión #{self.mission_number} cancelada.", embed=new_embed, view=new_view)

    @discord.ui.button(label="Abortar", style=discord.ButtonStyle.secondary)
    async def abort(self, interaction: discord.Interaction, button: discord.ui.Button):

        embed, view = await build_missions_embed_view_for_user(self.owner_id)
        await interaction.response.edit_message(content=None, embed=embed, view=view)




async def build_missions_embed_view_for_user(user_id: int):
    pool = get_pool()
    language = await get_user_language(user_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT um_latest.*, mb.mission_type
            FROM (
              SELECT DISTINCT ON (mission_number) *
              FROM user_missions
              WHERE user_id = $1
              ORDER BY mission_number, id DESC
            ) AS um_latest
            LEFT JOIN missions_base mb ON um_latest.mission_id = mb.mission_id
            ORDER BY um_latest.mission_number ASC
        """, user_id)

    embed = discord.Embed(
        title="📜 Tus misiones",
        description="",
        color=discord.Color.blurple()
    )
    view = discord.ui.View(timeout=None)

    # mapear por número (1..5)
    by_number = {r["mission_number"]: r for r in rows}
    now = datetime.now(timezone.utc)
    
    for num in range(1, 6):
        if num == 1:
            next_daily = now.replace(hour=5, minute=0, second=0, microsecond=0)
            if now >= next_daily:
                next_daily = next_daily + timedelta(days=1)

            ts = int(next_daily.timestamp())
            embed.add_field(
                name="⏰ Reinicio diario (misiones 1, 2 y 3):",
                value=f"<t:{ts}:R>",
                inline=False
            )
            
        if num == 4:
            days_ahead = (0 - now.weekday()) % 7
            next_monday = (now + timedelta(days=days_ahead)).replace(hour=5, minute=0, second=0, microsecond=0)
            
            if now >= next_monday:
                next_monday = next_monday + timedelta(days=7)

            ts_week = int(next_monday.timestamp())
            embed.add_field(
                name="----------\n📅 Reinicio semanal (misiones 4 y 5)",
                value=f"<t:{ts_week}:R>",
                inline=False
            )
            
            
        if num in by_number:
            r = by_number[num]
            needed = r["needed"] or 0
            obtained = r["obtained"] or 0
            mtype = r["mission_type"] or "unknown"
            status = r["status"] or "unknown"
            
            m_desc = get_translation(language, f"mission.{mtype}")
            
            status_e = "🔹"
            canceled = ""
            if status == "completed":
                status_e = " ✅"
            elif status == "cancelled":
                status_e = " ❌"
                canceled = "~~"

            embed.add_field(
                name=f"{status_e} Misión #{num}",
                value=f"**Tipo:** {m_desc}\n{canceled}**Progreso:** {obtained}/{needed}{canceled}",
                inline=False
            )

            # botones: Reclamar si está activa y completada; sino Cancelar si está activa; si no, botón gris
            is_active = (status == "active")
            can_claim = is_active and (obtained >= needed)

            if can_claim:
                btn = ClaimMissionButton(
                    user_mission_id=r["id"],
                    mission_number=num,
                    owner_id=user_id,
                    disabled=False
                )
                view.add_item(btn)
            elif is_active:
                # botón de cancelar (abre confirmación en el mismo mensaje)
                btn = CancelMissionButton(
                    user_mission_id=r["id"],
                    mission_number=num,
                    owner_id=user_id,
                    disabled=False
                )
                view.add_item(btn)
            else:
                # misión no activa: botón deshabilitado
                view.add_item(discord.ui.Button(label=f"❌", style=discord.ButtonStyle.gray, disabled=True))
        else:
            embed.add_field(
                name=f"🔹 Misión #{num}",
                value="(Sin asignar)",
                inline=False
            )
            view.add_item(discord.ui.Button(label=f"Reclamar #{num}", style=discord.ButtonStyle.gray, disabled=True))

    return embed, view


async def setup(bot):
    bot.tree.add_command(MissionsGroup())