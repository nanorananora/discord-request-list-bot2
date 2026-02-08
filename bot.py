import os
import re
import json
import datetime
import discord
from discord.ext import commands

import gspread
from google.oauth2.service_account import Credentials

# ============================== Env helpers ==========================
def env_int(name, default=None):
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default

# ============================== Discord config =======================
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

LOWER_REQUEST_CHANNEL_ID = env_int("LOWER_REQUEST_CHANNEL_ID")
UPPER_REQUEST_CHANNEL_ID = env_int("UPPER_REQUEST_CHANNEL_ID")
LOWER_UPPER_LIST_CHANNEL_ID = env_int("LOWER_UPPER_LIST_CHANNEL_ID")

INCOLLE_REQUEST_CHANNEL_ID = env_int("INCOLLE_REQUEST_CHANNEL_ID")
INCOLLE_LIST_CHANNEL_ID = env_int("INCOLLE_LIST_CHANNEL_ID")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True

# ============================== Sheets config ========================
# 下中級生/上級生
LU_SPREADSHEET_ID = os.getenv("LU_SPREADSHEET_ID")
LU_SHEET_NAME = os.getenv("LU_SHEET_NAME", "チャレンジ指導回答")
LU_TS_COLUMN_INDEX = int(os.getenv("LU_TS_COLUMN_INDEX", "1"))
LU_NAME_COL_INDEX = int(os.getenv("LU_NAME_COL_INDEX", "28"))   # 既定: AB列
LU_STATUS_COL_INDEX = int(os.getenv("LU_STATUS_COL_INDEX", "29"))# 既定: AC列
LU_MENTION_SPREADSHEET_ID = os.getenv("LU_MENTION_SPREADSHEET_ID")
LU_MENTION_SHEET_NAME = os.getenv("LU_MENTION_SHEET_NAME", "メンション")

# インカレ生
INC_SPREADSHEET_ID = os.getenv("INC_SPREADSHEET_ID")
INC_SHEET_NAME = os.getenv("INC_SHEET_NAME", "チャレンジ指導回答")
INC_TS_COLUMN_INDEX = int(os.getenv("INC_TS_COLUMN_INDEX", "1"))
INC_NAME_COL_INDEX = int(os.getenv("INC_NAME_COL_INDEX", "27"))   # 既定: AA列
INC_STATUS_COL_INDEX = int(os.getenv("INC_STATUS_COL_INDEX", "28"))# 既定: AB列
INC_MENTION_SPREADSHEET_ID = os.getenv("INC_MENTION_SPREADSHEET_ID")
INC_MENTION_SHEET_NAME = os.getenv("INC_MENTION_SHEET_NAME", "メンション")

# ============================== Sheets client ========================
def make_gspread_client():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def open_worksheet(gc, spreadsheet_id, sheet_name):
    sh = gc.open_by_key(spreadsheet_id)
    return sh.worksheet(sheet_name)

def load_mention_map(gc, spreadsheet_id, sheet_name):
    # A列=なまえ, B列=DiscordユーザーID
    mapping = {}
    if not spreadsheet_id:
        return mapping
    try:
        ws = open_worksheet(gc, spreadsheet_id, sheet_name)
        values = ws.get_all_values()
        for row in values:
            if len(row) < 2:
                continue
            name = (row[0] or "").strip()
            user_id = (row[1] or "").strip()
            if user_id and name:
                mapping[user_id] = name
    except Exception as e:
        print(f"[mention] load failed ({sheet_name}): {e}")
    return mapping

def find_row_by_timestamp(ws, ts_str, ts_col_index):
    try:
        col_vals = ws.col(ts_col_index)
        target = (ts_str or "").strip()
        for idx, val in enumerate(col_vals, start=1):
            if (val or "").strip() == target:
                return idx
    except Exception as e:
        print(f"[sheet] find by timestamp failed: {e}")
    return None

def update_sheet_reaction(ws, row, name_col_index, status_col_index, user_names_str):
    try:
        ws.update_cell(row, name_col_index, user_names_str)
        ws.update_cell(row, status_col_index, "確認中")
    except Exception as e:
        print(f"[sheet] update failed at row {row}: {e}")

# ============================== Parsing ==============================
def shorten_method(text, lines):
    mapping = [
        ("後からフィードバック", "後からフィードバック"),
        ("後から同時視聴で指導を希望", "後から同時視聴"),
        ("生徒の配信を同時視聴で指導を希望", "生徒の配信同時視聴"),
    ]
    for phrase, short in mapping:
        if phrase in text:
            return short
    for i, line in enumerate(lines):
        if "【希望の指導方法】" in line:
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            for phrase, short in mapping:
                if phrase in next_line:
                    return short
            return next_line if next_line else "未記載"
    return "未記載"

def extract_timestamp_key(text):
    # 「日時：」の後の文字列をキー（シートA列と完全一致前提）
    m = re.search(r'日時[:：]\s*([^\n\r]+)', text)
    if m:
        return m.group(1).strip()
    return None

def extract_request_info(text):
    lines = text.splitlines()

    # 依頼日（表示用 MM/DD）
    date_str = "??/??"
    m = re.search(r'日時[:：]\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})', text)
    if m:
        mm = int(m.group(2))
        dd = int(m.g
# ============================== Embed creation =======================
async def create_request_list_embed_for_channel(bot, source_channel_id, title):
    channel = bot.get_channel(source_channel_id)
    if not channel:
        return None

    embed = discord.Embed(title=title, color=0x4caf50)
    count = 0

    async for msg in channel.history(limit=50):
        # 通常メッセージ・Webhook投稿のみ
        if msg.type != discord.MessageType.default or msg.webhook_id is None:
            continue
        # 👍 が付いていたら「未対応一覧」から除外
        if msg.reactions and any(str(r.emoji) == "👍" for r in msg.reactions):
            continue

        name, date_str, rule, weapon, method, _ = extract_request_info(msg.content)
        embed.add_field(
            name=f"■ {name}・ {date_str}",
            value=(
                f"│ {rule}・{weapon}\n"
                f"│ {method}\n"
                f"└ 🔗 [依頼分のリンク]({msg.jump_url})"
            ),
            inline=False
        )
        count += 1
        if count >= 25:  # Embedフィールド上限
            break

    if not embed.fields:
        embed.description = "現在、対応待ちの指導依頼はありません。"

    jst = datetime.timezone(datetime.timedelta(hours=9))
    embed.set_footer(text=f"更新: {datetime.datetime.now(jst).strftime('%H:%M')}")
    return embed

# ============================== Reaction → Sheet =====================
async def process_thumbs_up_to_sheet(
    ws, ts_col_index, name_col_index, status_col_index,
    mention_map, bot, source_channel_id
):
    channel = bot.get_channel(source_channel_id)
    if not channel:
        return

    async for msg in channel.history(limit=50):
        # 通常メッセージ・Webhook投稿のみ
        if msg.type != discord.MessageType.default or msg.webhook_id is None:
            continue

        # 👍 リアクション収集
        thumbs = None
        for r in msg.reactions:
            if str(r.emoji) == "👍":
                thumbs = r
                break
        if not thumbs:
            continue

        users = [u async for u in thumbs.users(limit=None)]
        users = [u for u in users if not getattr(u, "bot", False)]
        if not users:
            continue

        # タイムスタンプキー（本文の「日時：」から抽出）
        _, _, _, _, _, ts_key = extract_request_info(msg.content)
        if not ts_key:
            print(f"[sheet] timestamp key not found for message: {msg.id}")
            continue

        # 名寄せ: Discord ID → なまえ（メンションリスト）。なければニックネーム等で補完
        names = []
        for u in users:
            mapped = mention_map.get(str(u.id))
            if mapped:
                names.append(mapped)
                continue

            display = None
            if msg.guild:
                member = msg.guild.get_member(u.id)
                if member is None:
                    try:
                        member = await msg.guild.fetch_member(u.id)
                    except Exception:
                        member = None
                if member:
                    display = member.display_name

            names.append(display or getattr(u, "global_name", None) or u.name)

        unique_names = sorted(set(n for n in names if n))
        names_str = "、".join(unique_names)

        row = find_row_by_timestamp(ws, ts_key, ts_col_index)
        if row:
            update_sheet_reaction(ws, row, name_col_index, status_col_index, names_str)
        else:
            print(f"[sheet] No matching timestamp row for: {ts_key}")

# ============================== Upsert embed =========================
async def find_existing_embed_message(channel, title, bot_user):
    async for msg in channel.history(limit=50):
        if msg.author == bot_user and msg.embeds:
            if (msg.embeds[0].title or "") == title:
                return msg
    return None

async def upsert_embed(channel, embed, bot_user):
    if embed is None:
        return
    existing = await find_existing_embed_message(channel, embed.title or "", bot_user)
    if existing:
        await existing.edit(embed=embed)
    else:
        await channel.send(embed=embed)

# ============================== Bot ==============================
class MyBot(commands.Bot):
    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.update_all()
        await self.close()

    async def update_all(self):
        # Google Sheets 接続（1回のみ）
        gc = None
        try:
            gc = make_gspread_client()
        except Exception as e:
            print(f"[sheet] initialization failed: {e}")

        ws_lu = None
        mention_map_lu = {}
        if gc and LU_SPREADSHEET_ID:
            try:
                ws_lu = open_worksheet(gc, LU_SPREADSHEET_ID, LU_SHEET_NAME)
            except Exception as e:
                print(f"[sheet] LU open failed: {e}")
            mention_map_lu = load_mention_map(
                gc, LU_MENTION_SPREADSHEET_ID, LU_MENTION_SHEET_NAME
            )

        ws_inc = None
        mention_map_inc = {}
        if gc and INC_SPREADSHEET_ID:
            try:
                ws_inc = open_worksheet(gc, INC_SPREADSHEET_ID, INC_SHEET_NAME)
            except Exception as e:
                print(f"[sheet] INC open failed: {e}")
            mention_map_inc = load_mention_map(
                gc, INC_MENTION_SPREADSHEET_ID, INC_MENTION_SHEET_NAME
            )

        # 1) 下中級生・上級生 → 同一出力チャンネルへEmbed
        list_channel_1 = self.get_channel(LOWER_UPPER_LIST_CHANNEL_ID)
        if list_channel_1:
            if LOWER_REQUEST_CHANNEL_ID:
                lower_embed = await create_request_list_embed_for_channel(
                    self, LOWER_REQUEST_CHANNEL_ID, "下中級生 未対応依頼一覧"
                )
                await upsert_embed(list_channel_1, lower_embed, self.user)

            if UPPER_REQUEST_CHANNEL_ID:
                upper_embed = await create_request_list_embed_for_channel(
                    self, UPPER_REQUEST_CHANNEL_ID, "上級生 未対応依頼一覧"
                )
                await upsert_embed(list_channel_1, upper_embed, self.user)

        # 2) インカレ生 → 別出力チャンネルへEmbed
        list_channel_2 = self.get_channel(INCOLLE_LIST_CHANNEL_ID)
        if list_channel_2 and INCOLLE_REQUEST_CHANNEL_ID:
            incolle_embed = await create_request_list_embed_for_channel(
                self, INCOLLE_REQUEST_CHANNEL_ID, "インカレ生　未対応依頼一覧"
            )
            await upsert_embed(list_channel_2, incolle_embed, self.user)

        # 3) 👍 リアクションをシートへ反映
        if ws_lu:
            if LOWER_REQUEST_CHANNEL_ID:
                await process_thumbs_up_to_sheet(
                    ws_lu,
                    LU_TS_COLUMN_INDEX,
                    LU_NAME_COL_INDEX,
                    LU_STATUS_COL_INDEX,
                    mention_map_lu,
                    self,
                    LOWER_REQUEST_CHANNEL_ID,
                )
            if UPPER_REQUEST_CHANNEL_ID:
                await process_thumbs_up_to_sheet(
                    ws_lu,
                    LU_TS_COLUMN_INDEX,
                    LU_NAME_COL_INDEX,
                    LU_STATUS_COL_INDEX,
                    mention_map_lu,
                    self,
                    UPPER_REQUEST_CHANNEL_ID,
                )

        if ws_inc and INCOLLE_REQUEST_CHANNEL_ID:
            await process_thumbs_up_to_sheet(
                ws_inc,
                INC_TS_COLUMN_INDEX,
                INC_NAME_COL_INDEX,
                INC_STATUS_COL_INDEX,
                mention_map_inc,
                self,
                INCOLLE_REQUEST_CHANNEL_ID,
            )

bot = MyBot(command_prefix="!", intents=intents)
bot.run(TOKEN)

