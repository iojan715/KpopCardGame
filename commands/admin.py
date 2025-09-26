import discord
from discord.ext import commands
from discord import app_commands
import csv
import os
import string
import random
from datetime import timezone, datetime
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool


class AdminGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="admin", description="Comandos administrativos")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Evita repetir el chequeo de permisos en cada subcomando"""
        admin_role = discord.utils.get(interaction.user.roles, name="Admin")
        if not admin_role:
            language = await get_user_language(interaction.user.id)
            not_permission = get_translation(language, "error.not_permission")
            await interaction.response.send_message(not_permission, ephemeral=True)
            return False
        return True

    CONTENT_CHOICES = [
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Packs", value="packs"),
        app_commands.Choice(name="Level rewards", value="levels"),
        app_commands.Choice(name="Idol Cards", value="idols"),
        app_commands.Choice(name="Performance cards", value="performance"),
        app_commands.Choice(name="Item cards", value="items"),
        app_commands.Choice(name="Redeemables", value="redeemables"),
        app_commands.Choice(name="Badges", value="badges"),
        app_commands.Choice(name="Idol base stats", value="idol_base"),
        app_commands.Choice(name="Skills", value="skills"),
        app_commands.Choice(name="Effects", value="effects"),
        app_commands.Choice(name="Groups", value="idol_group"),
        app_commands.Choice(name="songs", value="songs"),
        app_commands.Choice(name="Song sections", value="song_sections"),
        app_commands.Choice(name="Missions", value="missions"),
        app_commands.Choice(name="Events", value="events"),
        app_commands.Choice(name="Event Rewards", value="event_rewards"),
        
    ]

    @app_commands.command(name="upload_content", description="Sube datos desde un archivo CSV")
    @app_commands.describe(content_type="Tipo de contenido que deseas subir (ej. packs)")
    @app_commands.choices(content_type = CONTENT_CHOICES)
    async def upload_content(self, interaction: discord.Interaction, content_type: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if interaction.guild is None:
            return await interaction.edit_original_response(
                content="❌ Este comando solo está disponible en servidores."
            )
            
        language = await get_user_language(interaction.user.id)
        ALLOWED_CONTENT_TYPES = ["packs",
                                 "levels",
                                 "idols",
                                 "performance",
                                 "items",
                                 "redeemables",
                                 "badges",
                                 "idol_base",
                                 "skills",
                                 "effects",
                                 "idol_group",
                                 "songs",
                                 "song_sections",
                                 "missions",
                                 "events",
                                 "event_rewards"
                                 ]
        if content_type != "all" and content_type not in ALLOWED_CONTENT_TYPES:
            contenido = ', '.join(ALLOWED_CONTENT_TYPES)
            content_type_not_found = get_translation(language,"upload_content.content_type_not_found",contenido=contenido)
            await interaction.edit_original_response(content=content_type_not_found)
            return
        file_path = f"data_upload/{content_type}.csv"
        if content_type != "all" and not os.path.exists(file_path):
            file_not_found = get_translation(language, "upload_content.file_not_found", file_path=file_path)
            await interaction.edit_original_response(content=file_not_found)
            return

        pool = await get_pool()
        inserted = 0

        
        async with pool.acquire() as conn:
            inserted_total = 0
            types_to_process = ALLOWED_CONTENT_TYPES if content_type == "all" else [content_type]

            for ct in types_to_process:
                print(ct)
                file_path = f"data_upload/{ct}.csv"
                if not os.path.exists(file_path):
                    if content_type == "all":
                        continue
                    file_not_found = get_translation(language, "upload_content.file_not_found", file_path=file_path)
                    await interaction.edit_original_response(content=file_not_found)
                    return

                
                if ct == "packs":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO packs (
                                    pack_id, name, card_amount, can_idol, can_group,
                                    can_gift, price, w_idol, w_regular, w_limited, w_fcr, w_pob,
                                    w_legacy, w_item, w_performance, w_redeemable, base_price
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6, $7,
                                    $8, $9, $10, $11, $12, $13, $14,
                                    $15, $16, $17
                                )
                                ON CONFLICT (pack_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    card_amount = EXCLUDED.card_amount,
                                    can_idol = EXCLUDED.can_idol,
                                    can_group = EXCLUDED.can_group,
                                    can_gift = EXCLUDED.can_gift,
                                    price = EXCLUDED.price,
                                    w_idol = EXCLUDED.w_idol,
                                    w_regular = EXCLUDED.w_regular,
                                    w_limited = EXCLUDED.w_limited,
                                    w_fcr = EXCLUDED.w_fcr,
                                    w_pob = EXCLUDED.w_pob,
                                    w_legacy = EXCLUDED.w_legacy,
                                    w_item = EXCLUDED.w_item,
                                    w_performance = EXCLUDED.w_performance,
                                    w_redeemable = EXCLUDED.w_redeemable,
                                    base_price = EXCLUDED.base_price;
                            """, 
                            row["pack_id"], row["name"], int(row["card_amount"]),
                            row["can_idol"].lower() == "true",
                            row["can_group"].lower() == "true",
                            row["can_gift"].lower() == "true", int(row["price"]),
                            int(row["w_idol"]), int(row["w_regular"]), int(row["w_limited"]),
                            int(row["w_fcr"]), int(row["w_pob"]), int(row["w_legacy"]),
                            int(row["w_item"]), int(row["w_performance"]), int(row["w_redeemable"]), int(row["base_price"]))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
                
                elif ct == "idols":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO cards_idol (
                                    card_id, idol_id, set_id, rarity_id, idol_name, group_name, set_name,
                                    rarity, theme, vocal, rap, dance, visual, energy,
                                    weight, value
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6, $7,
                                    $8, $9, $10, $11, $12, $13, $14,
                                    $15, $16
                                )
                                ON CONFLICT (card_id) DO UPDATE SET
                                    idol_id = EXCLUDED.idol_id,
                                    set_id = EXCLUDED.set_id,
                                    rarity_id = EXCLUDED.rarity_id,
                                    idol_name = EXCLUDED.idol_name,
                                    group_name = EXCLUDED.group_name,
                                    set_name = EXCLUDED.set_name,
                                    rarity = EXCLUDED.rarity,
                                    theme = EXCLUDED.theme,
                                    vocal = EXCLUDED.vocal,
                                    rap = EXCLUDED.rap,
                                    dance = EXCLUDED.dance,
                                    visual = EXCLUDED.visual,
                                    energy = EXCLUDED.energy,
                                    weight = EXCLUDED.weight,
                                    value = EXCLUDED.value;
                            """, 
                            row["card_id"], row["idol_id"], row["set_id"], row["rarity_id"],
                            row["idol_name"], row["group_name"], row["set_name"], row["rarity"], row.get("theme"),
                            int(row["vocal"]), int(row["rap"]), int(row["dance"]), int(row["visual"]),
                            int(row["energy"]), int(row["weight"]), int(row["value"]))
                            inserted += 1
                            #print(row['card_id'])
                    inserted_total += inserted
                    inserted = 0
                
                elif ct == "redeemables":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO redeemables (
                                    redeemable_id, name, type, effect, weight
                                ) VALUES (
                                    $1, $2, $3, $4, $5
                                )
                                ON CONFLICT (redeemable_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    type = EXCLUDED.type,
                                    effect = EXCLUDED.effect,
                                    weight = EXCLUDED.weight;
                            """, 
                            row["redeemable_id"], row["name"], row["type"], row.get("effect"), int(row["weight"]))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
                
                elif ct == "badges":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO badges (
                                    badge_id, name, category, set_id, idol_id
                                ) VALUES (
                                    $1, $2, $3, $4, $5
                                )
                                ON CONFLICT (badge_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    category = EXCLUDED.category,
                                    set_id = EXCLUDED.set_id,
                                    idol_id = EXCLUDED.idol_id;
                            """,
                            row["badge_id"], row["name"], row["category"],
                            row.get("set_id"), row.get("idol_id"))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "performance":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO cards_performance (
                                    pcard_id, name, type, effect, duration,
                                    cooldown, match, match_value, weight, value
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6, $7, $8, $9, $10
                                )
                                ON CONFLICT (pcard_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    type = EXCLUDED.type,
                                    effect = EXCLUDED.effect,
                                    duration = EXCLUDED.duration,
                                    cooldown = EXCLUDED.cooldown,
                                    match = EXCLUDED.match,
                                    match_value = EXCLUDED.match_value,
                                    weight = EXCLUDED.weight,
                                    value = EXCLUDED.value;
                            """,
                            row["pcard_id"], row["name"], row["type"],
                            row.get("effect"),
                            int(row["duration"]) if row.get("duration") else 0,
                            int(row["cooldown"]) if row.get("cooldown") else 0,
                            row.get("match"),
                            row.get("match_value"),
                            int(row["weight"]) if row.get("weight") else 0,
                            int(row["value"]) if row.get("value") else 0)
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "items":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO cards_item (
                                    item_id, name, type,
                                    plus_vocal, plus_rap, plus_dance, plus_visual, plus_energy,
                                    max_durability, weight, value
                                ) VALUES (
                                    $1, $2, $3,
                                    $4, $5, $6, $7, $8,
                                    $9, $10, $11
                                )
                                ON CONFLICT (item_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    type = EXCLUDED.type,
                                    plus_vocal = EXCLUDED.plus_vocal,
                                    plus_rap = EXCLUDED.plus_rap,
                                    plus_dance = EXCLUDED.plus_dance,
                                    plus_visual = EXCLUDED.plus_visual,
                                    plus_energy = EXCLUDED.plus_energy,
                                    max_durability = EXCLUDED.max_durability,
                                    weight = EXCLUDED.weight,
                                    value = EXCLUDED.value;
                            """,
                            row["item_id"], row["name"], row["type"],
                            int(row["plus_vocal"]) if row.get("plus_vocal") else 0,
                            int(row["plus_rap"]) if row.get("plus_rap") else 0,
                            int(row["plus_dance"]) if row.get("plus_dance") else 0,
                            int(row["plus_visual"]) if row.get("plus_visual") else 0,
                            int(row["plus_energy"]) if row.get("plus_energy") else 0,
                            int(row["max_durability"]) if row.get("max_durability") else 1,
                            int(row["weight"]) if row.get("weight") else 0,
                            int(row["value"]) if row.get("value") else 0)
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "levels":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO level_rewards (
                                    level, xp_needed, credits, pack, redeemable, badge
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6
                                )
                                ON CONFLICT (level) DO UPDATE SET
                                    xp_needed = EXCLUDED.xp_needed,
                                    credits = EXCLUDED.credits,
                                    pack = EXCLUDED.pack,
                                    redeemable = EXCLUDED.redeemable,
                                    badge = EXCLUDED.badge;
                            """,
                            int(row["level"]),
                            int(row["xp_needed"]),
                            int(row["credits"]) if row.get("credits") else 0,
                            row.get("pack_id"),
                            row.get("redeemable_id"),
                            row.get("badge_id"))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "idol_base":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO idol_base (
                                    idol_id, name, vocal, rap, dance, visual
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6
                                )
                                ON CONFLICT (idol_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    vocal = EXCLUDED.vocal,
                                    rap = EXCLUDED.rap,
                                    dance = EXCLUDED.dance,
                                    visual = EXCLUDED.visual;
                            """,
                            row["idol_id"], row["name"],
                            int(row["vocal"]), int(row["rap"]),
                            int(row["dance"]), int(row["visual"]))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
                            
                elif ct == "idol_group":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO idol_group (
                                    idol_id, idol_name, group_name
                                ) VALUES (
                                    $1, $2, $3
                                )
                                ON CONFLICT (idol_id, group_name) DO UPDATE SET
                                    idol_name = EXCLUDED.idol_name,
                                    group_name = EXCLUDED.group_name;
                            """,
                            row["idol_id"], row["idol_name"], row["group_name"])
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "skills":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO skills (
                                    skill_name, skill_type, condition, condition_values, condition_effect,
                                    condition_params, effect_id, duration, energy_cost,
                                    cost_type, effect, params, tags
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6, $7, $8, $9,
                                    $10, $11, $12, $13
                                )
                                ON CONFLICT (skill_name) DO UPDATE SET
                                    skill_type = EXCLUDED.skill_type,
                                    condition = EXCLUDED.condition,
                                    condition_values = EXCLUDED.condition_values,
                                    condition_effect = EXCLUDED.condition_effect,
                                    condition_params = EXCLUDED.condition_params,
                                    effect_id = EXCLUDED.effect_id,
                                    duration = EXCLUDED.duration,
                                    energy_cost = EXCLUDED.energy_cost,
                                    cost_type = EXCLUDED.cost_type,
                                    effect = EXCLUDED.effect,
                                    params = EXCLUDED.params,
                                    tags = EXCLUDED.tags;
                                """,
                                row["skill_name"],
                                row["skill_type"],
                                row.get("condition"),
                                json.dumps(json.loads(row["condition_values"])) if row.get("condition_values") else None,
                                row.get("condition_effect"),
                                json.dumps(json.loads(row["condition_params"])) if row.get("condition_params") else None,
                                row.get("effect_id"),
                                int(row["duration"]) if row.get("duration") else 0,
                                float(row["energy_cost"]) if row.get("energy_cost") else 0,
                                row.get("cost_type"),
                                row.get("effect"),
                                json.dumps(json.loads(row["params"])) if row.get("params") else None,
                                row.get("tags")
                            )
                            
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "missions":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            
                            await conn.execute(
                                """
                                INSERT INTO missions_base (
                                    mission_id, mission_type, needed, difficulty,
                                    pack_id, redeemable_id, credits, xp
                                ) VALUES (
                                    $1, $2, $3, $4,
                                    $5, $6, $7, $8
                                )
                                ON CONFLICT (mission_id) DO UPDATE SET
                                    mission_type = EXCLUDED.mission_type,
                                    needed = EXCLUDED.needed,
                                    difficulty = EXCLUDED.difficulty,
                                    pack_id = EXCLUDED.pack_id,
                                    redeemable_id = EXCLUDED.redeemable_id,
                                    credits = EXCLUDED.credits,
                                    xp = EXCLUDED.xp;
                                """,
                                row["mission_id"],
                                row.get("mission_type"),
                                int(row.get("needed") or 1),
                                row.get("difficulty"),
                                row.get("pack_id") or None,
                                row.get("redeemable_id"),
                                int(row.get("credits") or 0),
                                int(row.get("xp") or 1)
                            )
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0


                elif ct == "effects":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO performance_effects (
                                    effect_id, effect_name, effect_type,
                                    highest_stat_mod, lowest_stat_mod,
                                    plus_vocal, plus_rap, plus_dance, plus_visual,
                                    hype_mod, score_mod,
                                    extra_cost, relative_cost
                                ) VALUES (
                                    $1, $2, $3,
                                    $4, $5,
                                    $6, $7, $8, $9,
                                    $10, $11,
                                    $12, $13
                                )
                                ON CONFLICT (effect_id) DO UPDATE SET
                                    effect_name = EXCLUDED.effect_name,
                                    effect_type = EXCLUDED.effect_type,
                                    highest_stat_mod = EXCLUDED.highest_stat_mod,
                                    lowest_stat_mod = EXCLUDED.lowest_stat_mod,
                                    plus_vocal = EXCLUDED.plus_vocal,
                                    plus_rap = EXCLUDED.plus_rap,
                                    plus_dance = EXCLUDED.plus_dance,
                                    plus_visual = EXCLUDED.plus_visual,
                                    hype_mod = EXCLUDED.hype_mod,
                                    score_mod = EXCLUDED.score_mod,
                                    extra_cost = EXCLUDED.extra_cost,
                                    relative_cost = EXCLUDED.relative_cost;
                                """,
                                row["effect_id"],
                                row["name"],
                                row["type"],
                                int(row.get("plus_highest") or 0),
                                int(row.get("plus_lowest") or 0),
                                int(row.get("plus_vocal") or 0),
                                int(row.get("plus_rap") or 0),
                                int(row.get("plus_dance") or 0),
                                int(row.get("plus_visual") or 0),
                                float(row.get("hype_mod") or 1.0),
                                float(row.get("score_mod") or 1.0),
                                int(row.get("extra_cost") or 0),
                                float(row.get("relative_cost") or 1.0)
                            )
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "songs":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO songs (
                                    song_id, name, original_artist, total_duration,
                                    total_sections, average_score
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6
                                )
                                ON CONFLICT (song_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    original_artist = EXCLUDED.original_artist,
                                    total_duration = EXCLUDED.total_duration,
                                    total_sections = EXCLUDED.total_sections,
                                    average_score = EXCLUDED.average_score;
                                """,
                                row["song_id"],
                                row["name"],
                                row["original_artist"],
                                int(row["total_duration"]),
                                int(row["total_sections"]),
                                round(float(row["average_score"]),2)
                            )
                            
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "song_sections":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO song_sections (
                                    section_id, song_id, section_number, section_type, duration,
                                    lyrics, vocal, rap, dance, visual, change_rule, type_plus,
                                    plus_vocal, plus_rap, plus_dance, plus_visual, average_score
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6, $7, $8, $9, $10, $11,
                                    $12, $13, $14, $15, $16, $17
                                )
                                ON CONFLICT (section_id) DO UPDATE SET
                                    song_id = EXCLUDED.song_id,
                                    section_number = EXCLUDED.section_number,
                                    section_type = EXCLUDED.section_type,
                                    duration = EXCLUDED.duration,
                                    lyrics = EXCLUDED.lyrics,
                                    vocal = EXCLUDED.vocal,
                                    rap = EXCLUDED.rap,
                                    dance = EXCLUDED.dance,
                                    visual = EXCLUDED.visual,
                                    change_rule = EXCLUDED.change_rule,
                                    type_plus = EXCLUDED.type_plus,
                                    plus_vocal = EXCLUDED.plus_vocal,
                                    plus_rap = EXCLUDED.plus_rap,
                                    plus_dance = EXCLUDED.plus_dance,
                                    plus_visual = EXCLUDED.plus_visual,
                                    average_score = EXCLUDED.average_score;
                                """,
                                row["section_id"],
                                row["song_id"],
                                int(row["section_number"]),
                                row["section_type"],
                                int(row["duration"]),
                                row['lyrics'],
                                int(row["vocal"]),
                                int(row["rap"]),
                                int(row["dance"]),
                                int(row["visual"]),
                                row.get("change_rule", "optional"),
                                row.get("type_plus") or None,
                                int(row["plus_vocal"]) if row["plus_vocal"] else 0,
                                int(row["plus_rap"]) if row["plus_rap"] else 0,
                                int(row["plus_dance"]) if row["plus_dance"] else 0,
                                int(row["plus_visual"]) if row["plus_visual"] else 0,
                                round(float(row["average_score"]),2)
                            )
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "events":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO events (
                                    event_id, event_type, base_name, weight,
                                    can_song, can_set, goal_type, difficulty
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6, $7, $8
                                )
                                ON CONFLICT (event_id) DO UPDATE SET
                                    event_type = EXCLUDED.event_type,
                                    base_name = EXCLUDED.base_name,
                                    weight = EXCLUDED.weight,
                                    can_song = EXCLUDED.can_song,
                                    can_set = EXCLUDED.can_set,
                                    goal_type = EXCLUDED.goal_type,
                                    difficulty = EXCLUDED.difficulty;
                                """,
                                row["event_id"],
                                row.get("event_type"),
                                row.get("base_name"),
                                int(row.get("weight", 0)),
                                row.get("can_song") in ("true", "True", "1", True),
                                row.get("can_set") in ("true", "True", "1", True),
                                row.get("goal_type"),
                                row.get("difficulty")
                            )
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "event_rewards":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO event_rewards (
                                    reward_id, event_id, rank_min, rank_max,
                                    credits, pack_id, is_ranked, redeemable_id, badge_id, boost
                                ) VALUES (
                                    $1, $2, $3, $4,
                                    $5, $6, $7, $8, $9, $10
                                )
                                ON CONFLICT (reward_id) DO UPDATE SET
                                    event_id = EXCLUDED.event_id,
                                    rank_min = EXCLUDED.rank_min,
                                    rank_max = EXCLUDED.rank_max,
                                    credits = EXCLUDED.credits,
                                    pack_id = EXCLUDED.pack_id,
                                    is_ranked = EXCLUDED.is_ranked,
                                    redeemable_id = EXCLUDED.redeemable_id,
                                    badge_id = EXCLUDED.badge_id,
                                    boost = EXCLUDED.boost;
                                """,
                                int(row["reward_id"]),
                                row["event_id"],
                                int(row["rank_min"]),
                                int(row["rank_max"]),
                                int(row.get("credits") or 0),
                                row.get("pack_id"),
                                row.get("is_ranked") in ("true", "True", "1", True),
                                row.get("redeemable_id"),
                                row.get("badge_id"),
                                float(row['boost'])
                            )
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0


        
        if content_type == "all":
            succesfull = get_translation(language, "upload_content.succesfull_all", inserted=inserted_total)
        else:
            succesfull = get_translation(language, "upload_content.succesfull", inserted=inserted_total, content_type=content_type)

        await interaction.edit_original_response(
            content= succesfull
        )


    @app_commands.command(name="give_item_card", description="Entregar manualmente una item card a un jugador")
    @app_commands.describe(
        user="Usuario que recibirá la carta",
        item_id="ID base del ítem a entregar"
    )
    async def give_item_card(self, interaction: discord.Interaction, user: discord.User, item_id: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        pool = get_pool()

        async with pool.acquire() as conn:
            
            item_row = await conn.fetchrow("SELECT * FROM cards_item WHERE item_id = $1", item_id)
            if not item_row:
                await interaction.response.send_message(f"❌ El item `{item_id}` no existe.", ephemeral=True)
                return
            durability = item_row['max_durability']
            item_name = item_row['name']
            
            unique_id = ""
            while True:
                new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                row = await conn.fetchrow("SELECT 1 FROM user_item_cards WHERE unique_id = $1", new_id)
                if not row:
                    unique_id = new_id
                    break

            
            values = (
                unique_id,
                user.id,
                item_id,
                durability,
                None,
                datetime.now(timezone.utc)
            )

            await conn.execute("""
                INSERT INTO user_item_cards (
                    unique_id,
                    user_id,
                    item_id,
                    durability,
                    equipped_idol_card_id,
                    date_obtained
                ) VALUES ($1, $2, $3, $4, $5, $6);
            """, *values)

        await interaction.response.send_message(f"✅ Se entregó `{item_name}` a {user.mention}.", ephemeral=False)



async def setup(bot):
    bot.tree.add_command(AdminGroup())