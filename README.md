# 🤖 AI Acquisition Dashboard

Simple dashboard to view @ai_acq messages from Slack.

## Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Create `.env` file:**
```bash
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_CHANNEL_ID=C06L2AG0ZTQ
COMPANY_NAME=Snowflake
TIMEZONE=America/New_York
```

3. **Run:**
```bash
streamlit run dashboard.py
```

## Files

- `dashboard.py` - Main app (79 lines)
- `slack_monitor.py` - Slack API (52 lines)
- `config.py` - Configuration
- `requirements.txt` - Dependencies

## Features

- View all @ai_acq messages in a table
- Filter by time range
- Export to CSV
- Auto-refresh every 5 minutes

That's it! 🚀
