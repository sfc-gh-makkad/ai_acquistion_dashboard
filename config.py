# import os
# from dotenv import load_dotenv


# load_dotenv()

# # Slack Configuration
# #SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
# SLACK_CHANNEL_ID = os.getenv('SLACK_CHANNEL_ID')

# # Dashboard Configuration
# TIMEZONE = os.getenv('TIMEZONE', 'America/New_York')

# # Snowflake Configuration (optional - for classification)
# SNOWFLAKE_ACCOUNT = os.getenv('SNOWFLAKE_ACCOUNT')
# SNOWFLAKE_USER = os.getenv('SNOWFLAKE_USER')
# SNOWFLAKE_PASSWORD = os.getenv('SNOWFLAKE_PASSWORD')
# SNOWFLAKE_WAREHOUSE = os.getenv('SNOWFLAKE_WAREHOUSE')
# SNOWFLAKE_DATABASE = os.getenv('SNOWFLAKE_DATABASE', 'DEMO_DB')
# SNOWFLAKE_SCHEMA = os.getenv('SNOWFLAKE_SCHEMA', 'PUBLIC')




# import streamlit as st


# #SLACK_BOT_TOKEN = st.secrets["slack_bot_token"]

# conn = st.connection("snowflake")

# df = conn.query("SELECT PST.PS_UTILIZATION.GET_SLACK_TOKEN() AS TOKEN")
# SLACK_BOT_TOKEN = df["TOKEN"].iloc[0]   # or: df.iloc[0, 0]
# print(SLACK_BOT_TOKEN)


import os
from dotenv import load_dotenv
import streamlit as st

# Load .env for local development
load_dotenv()

# ----- Slack configuration -----

# Channel ID: safe to keep in .env, with a default for Snowflake
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "C06L2AG0ZTQ")

# Timezone (non‑secret config)
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

# 1) Try getting the bot token from env (for local dev)
_env_token = os.getenv("SLACK_BOT_TOKEN")

if _env_token:
    SLACK_BOT_TOKEN = _env_token
else:
    # 2) Fallback: get the bot token from Snowflake via your secret-backed function
    conn = st.connection("snowflake")
    df = conn.query("SELECT PST.PS_UTILIZATION.GET_SLACK_TOKEN() AS TOKEN")
    if df.empty:
        raise RuntimeError("GET_SLACK_TOKEN() returned no rows")
    SLACK_BOT_TOKEN = df["TOKEN"].iloc[0]
    if not SLACK_BOT_TOKEN:
        raise RuntimeError("GET_SLACK_TOKEN() returned an empty token")