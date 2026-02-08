import os
import re
import json
import datetime
import discord
from discord.ext import commands

import gspread
from google.oauth2.service_account import Credentials

# ============================== Env helpers ==============================
def env_int(name, default=None):
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default

# ============================== Discord config ===========================
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

# ============================== Sheets config ============================
# 下中級生/上級生
LU_SPREADSHEET_ID = os.getenv("LU_SPREADSHEET_ID")
LU_SHEET_NAME = os.getenv("LU_SHEET_NAME", "チャレンジ指導回答")
LU_TS_COLUMN_INDEX = int(os.getenv("LU_TS_COLUMN_INDEX", "1"))
LU_NAME_COL_INDEX = int(os.getenv("LU_NAME_COL_INDEX", "28"))
LU_STATUS_COL_INDEX = int(os.getenv("LU_STATUS_COL_INDEX", "29"))
LU_MENTION_SPREADSHEET_ID = os.getenv("LU_MENTION_SPREADSHEET_ID")
LU_MENTION_SHEET_NAME = os.getenv("LU_MENTION_SHEET_NAME", "メンション")

# インカレ生
INC_SPREADSHEET_ID = os.getenv("INC_SPREADSHEET_ID")
INC_SHEET_NAME = os.getenv("INC_SHEET_NAME", "チャレンジ指導回答")
INC_TS_COLUMN_INDEX = int(os.getenv("INC_TS_COLUMN_INDEX", "1"))
INC_NAME_COL_INDEX = int(os.getenv("INC_NAME_COL_INDEX", "27"))
INC_STATUS_COL_INDEX = int(os.getenv("INC_STATUS_COL_INDEX", "28"))
INC_MENTION_SPREADSHEET_ID = os.getenv("INC_MENTION_SPREADSHEET_ID")
INC_MENTION_SHEET_NAME = os.getenv("INC_MENTION_SHEET_NAME", "メンション")

# ============================== Sheets client ============================
def make_gspread_client():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def open_worksheet(gc, spreadsheet_id, sheet_name):
    sh = gc.open_by_key(spreadsheet_id)
    return sh.worksheet(sheet_name)

def load_mention_map(gc, spreadsheet_id, sheet_name):
    mapping = {}
    if not spreadsheet_id:
        return mapping
    try:
        ws = open_worksheet(gc, spreadsheet_id, sheet_name)
        for row in ws.get_all_values():
            if len(row) >= 2 and row[0] and row[1]:
                mapping[row[1].strip()] = row[0].strip()
    except Exception as e:
        print(f"[mention] load failed: {e}")
    return mapping

def find_row_by_timestamp(ws, ts_str, ts_col_index):
    for idx, val in enumerate(ws.col(ts_col_index), start=1):
        if val.strip() == ts_str.strip():
            return idx
    return None

def update_sheet_reaction(ws, row, name_col_index, status_col_index, names):
    ws.update_cell(row, name_col_index, names)
    ws.update_cell(row, status_col_index, "確認中")

# ============================== Parsing =================================
def extract_request_info(text):
    date_str = "??/??"
    m = re.search(r"日時[:：]\s*(\d{4})/(\d{2})/(\d{2})", text)
    if m:
        date_str = f"{m.group(2)}/{m.group(3)}"

    name, rule, weapon = "不明", "未定", "未定"
    m = re.search(r"生徒No\d+・([^・]+)・([^・]+)・([^・\n]+)", text)
    if m:
        name, rule, weapon = m.groups()

    method = "未記載"
    if "同時視聴" in text:
        method = "後同時視聴"
    elif "フィードバック" in text:
        method = "後フィードバック"

    ts_key = None
    m = re.search(r"日時[:：]\s*([^\n]+)", text)
    if m:
        ts_key = m.group(1)

    return name, date_str, rule, weapon, method, ts_key

# ============================== Embed ===================================
async def create_request_list(bot, source_channel_id, title):
    channel = bot.get_channel(source_channel_id)
    embed = discord.Embed(title=title, color=0x4caf50)

    async for msg in channel.history(limit=50):
        if msg.webhook_id is None:
            continue
        if any(str(r.emoji) == "👍" for r in msg.reactions):
            continue

        name, date_str, rule, weapon, method, _ = extract_request_info(msg.content)
        embed.add_field(
            name=f"■ {name} {date_str}",
            value=f"│ {rule}/{weapon}/{method}\n└ 🔗 [依頼文を開く]({msg.jump_url})",
            inline=False,
        )

    if not embed.fields:
        embed.description = "現在、対応待ちの指導依頼はありません。"

    jst = datetime.timezone(datetime.timedelta(hours=9))
    embed.set_footer(text=f"更新: {datetime.datetime.now(jst).strftime('%H:%M')}")
    return embed

# ============================== Bot =====================================
class MyBot(commands.Bot):
    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.update_all()
        await self.close()

    async def update_all(self):
        gc = make_gspread_client()

        list_channel = self.get_channel(LOWER_UPPER_LIST_CHANNEL_ID)
        if list_channel:
            if LOWER_REQUEST_CHANNEL_ID:
                embed = await create_request_list(self, LOWER_REQUEST_CHANNEL_ID, "下中級生 未対応依頼一覧")
                await list_channel.send(embed=embed)

bot = MyBot(command_prefix="!", intents=intents)
bot.run(TOKEN)
