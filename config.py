import os
from dotenv import load_dotenv

load_dotenv()

# Slack Configuration
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
SLACK_USER_TOKEN = os.getenv('SLACK_USER_TOKEN')  # For search API (optional)
SLACK_APP_TOKEN = os.getenv('SLACK_APP_TOKEN')
SLACK_CHANNEL_ID = os.getenv('SLACK_CHANNEL_ID')
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')

# Dashboard Configuration
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Executive Dashboard')
DASHBOARD_TITLE = os.getenv('DASHBOARD_TITLE', 'Slack Channel Analytics')
TIMEZONE = os.getenv('TIMEZONE', 'America/New_York')

# UI Configuration
EXECUTIVE_THEME = {
    'primary_color': '#1f77b4',
    'background_color': '#ffffff',
    'secondary_background_color': '#f0f2f6',
    'text_color': '#262730',
    'font': 'sans serif'
}

# Snowflake Configuration (optional - for classification)
SNOWFLAKE_ACCOUNT = os.getenv('SNOWFLAKE_ACCOUNT')
SNOWFLAKE_USER = os.getenv('SNOWFLAKE_USER')
SNOWFLAKE_PASSWORD = os.getenv('SNOWFLAKE_PASSWORD')
SNOWFLAKE_WAREHOUSE = os.getenv('SNOWFLAKE_WAREHOUSE')
SNOWFLAKE_DATABASE = os.getenv('SNOWFLAKE_DATABASE', 'DEMO_DB')
SNOWFLAKE_SCHEMA = os.getenv('SNOWFLAKE_SCHEMA', 'PUBLIC')

# Metrics Configuration
REFRESH_INTERVAL = 300  # 5 minutes
MAX_MESSAGES_DISPLAY = 1000
