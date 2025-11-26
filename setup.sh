#!/bin/bash

echo "🚀 Setting up Slack Executive Dashboard..."

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv slack_env

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source slack_env/bin/activate

# Install requirements
echo "📚 Installing Python packages..."
pip install -r requirements.txt

# Create .env file from example
echo "⚙️ Setting up environment configuration..."
if [ ! -f .env ]; then
    cp config.py .env.template
    echo "
# Copy this template and create a .env file with your actual values:

SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here  
SLACK_CHANNEL_ID=C1234567890
COMPANY_NAME=Your Company Name
DASHBOARD_TITLE=Executive Slack Analytics
TIMEZONE=America/New_York
" > .env.template
    
    echo "✅ Created .env.template - please copy to .env and add your Slack credentials"
else
    echo "✅ .env file already exists"
fi

echo "
🎉 Setup complete! 

Next steps:
1. Create a .env file with your Slack credentials (see .env.template)
2. Run the dashboard: streamlit run dashboard.py

📋 Required Slack Setup:
- Create a Slack App at https://api.slack.com/apps
- Add Bot Token Scopes: channels:history, users:read, channels:read
- Install app to your workspace
- Copy Bot User OAuth Token to SLACK_BOT_TOKEN
- Get your channel ID and add to SLACK_CHANNEL_ID

🔗 For detailed Slack setup instructions, see README.md
"
