"""
AI Acquisition Dashboard

This Streamlit dashboard displays:
1. Messages mentioning @ai_acq from a Slack channel
2. Top performers bar chart (based on ✅ reactions on their replies)
3. Quarterly breakdown of message volume
4. Searchable message table with CSV export

Data flow:
- SlackMonitor fetches messages from Slack API
- Messages are filtered by fiscal quarter (FY starts in February)
- Top performers are calculated by counting white_check_mark reactions on thread replies
"""

import streamlit as st
import pandas as pd
import re
import pytz
import plotly.express as px
from datetime import datetime
from slack_monitor import SlackMonitor
import config

# Try to import Snowflake for optional message classification feature
try:
    import snowflake.connector
    SNOWFLAKE_AVAILABLE = all([config.SNOWFLAKE_ACCOUNT, config.SNOWFLAKE_USER, config.SNOWFLAKE_PASSWORD])
except (ImportError, AttributeError):
    SNOWFLAKE_AVAILABLE = False

# Page config must be first Streamlit command
st.set_page_config(page_title="AI Acquisition Dashboard", page_icon="🤖", layout="wide")


def clean_slack_formatting(text):
    """
    Remove Slack's special formatting for clean display
    
    Transformations:
    - <!subteam^ID> (user group mention) -> @AI_Acquisition
    - <@U12345> (user mention) -> removed
    - <http://url|display text> -> display text
    - <http://url> -> http://url
    """
    text = re.sub(r'<!subteam\^[^>]+>', '@AI_Acquisition', text)
    text = re.sub(r'<@\w+>', '', text)
    text = re.sub(r'<https?://[^|>]+\|([^>]+)>', r'\1', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    return text.strip()


def get_fiscal_quarter(date):
    """
    Calculate Snowflake's fiscal quarter from a date
    
    Fiscal calendar rules:
    - Q1: Feb, Mar, Apr
    - Q2: May, Jun, Jul  
    - Q3: Aug, Sep, Oct
    - Q4: Nov, Dec, Jan
    - Fiscal year is named after the calendar year at end of Q4
    
    Examples:
    - Aug 2024 -> FY25 Q3 (because Q4 ends Jan 2025)
    - Jan 2025 -> FY25 Q4 (last month of fiscal year)
    - Feb 2025 -> FY26 Q1 (new fiscal year starts)
    
    Returns: (fiscal_year, quarter_number, 'FYxx Qx' string)
    """
    month, year = date.month, date.year
    if month in [2, 3, 4]:
        return year + 1, 1, f"FY{(year + 1) % 100} Q1"
    elif month in [5, 6, 7]:
        return year + 1, 2, f"FY{(year + 1) % 100} Q2"
    elif month in [8, 9, 10]:
        return year + 1, 3, f"FY{(year + 1) % 100} Q3"
    else:  # Nov, Dec, Jan (Q4)
        fy = year + 1 if month in [11, 12] else year
        return fy, 4, f"FY{fy % 100} Q4"


@st.cache_data(ttl=300)  # Cache for 5 minutes to avoid hitting Slack API on every refresh
def load_all_messages():
    """Load all AI Acquisition messages from Slack (cached)"""
    return SlackMonitor().get_ai_acq_messages(limit=1000)


@st.cache_data(ttl=600)  # Cache for 10 minutes
def classify_messages_with_snowflake(messages):
    """
    Use Snowflake Cortex CLASSIFY_TEXT to categorize messages
    
    Classifies each message as either:
    - "Slack Assistance": Help provided through Slack thread
    - "Call Assist": Request to join a call or meeting
    
    Returns: {'slack_assist': count, 'call_assist': count} or None if unavailable
    """
    import json
    if not SNOWFLAKE_AVAILABLE or not messages:
        return None
    
    try:
        conn = snowflake.connector.connect(
            account=config.SNOWFLAKE_ACCOUNT,
            user=config.SNOWFLAKE_USER,
            password=config.SNOWFLAKE_PASSWORD,
            warehouse=config.SNOWFLAKE_WAREHOUSE,
            database=config.SNOWFLAKE_DATABASE,
            schema=config.SNOWFLAKE_SCHEMA
        )
        cursor = conn.cursor()
        slack_assist, call_assist = 0, 0
        
        # Only classify first 50 messages to avoid long processing time
        for msg in messages[:50]:
            clean_text = clean_slack_formatting(msg['message_text'])
            query = """
            SELECT SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
                %s,
                ['Slack Assistance', 'Call Assist'],
                {'task_description': 'Classify if this is a request for help via Slack thread or a request to join a call'}
            ) as classification
            """
            cursor.execute(query, (clean_text,))
            result = cursor.fetchone()
            
            if result:
                classification = result[0]
                if isinstance(classification, str):
                    classification = json.loads(classification)
                label = classification.get('label', '') if isinstance(classification, dict) else ''
                if label == 'Slack Assistance':
                    slack_assist += 1
                elif label == 'Call Assist':
                    call_assist += 1
        
        cursor.close()
        conn.close()
        return {'slack_assist': slack_assist, 'call_assist': call_assist}
    except Exception as e:
        st.error(f"Classification error: {str(e)}")
        return None


# ==================== HEADER ====================
st.title("🤖 AI Acquisition Dashboard")
st.markdown("---")

# ==================== SIDEBAR - TIME RANGE SELECTION ====================
st.sidebar.title("⚙️ Settings")

# Get current fiscal quarter to build dropdown options
tz = pytz.timezone(config.TIMEZONE)
now = datetime.now(tz)
current_fy, current_q, _ = get_fiscal_quarter(now)

# Build list of last 8 quarters (e.g., ["All Time", "FY25 Q4", "FY25 Q3", ...])
quarter_options = ["All Time"]
for i in range(8):
    target_q, years_back = current_q - i, 0
    # Handle quarter wraparound (Q0 -> Q4 of previous year)
    while target_q <= 0:
        target_q += 4
        years_back += 1
    quarter_options.append(f"FY{(current_fy - years_back) % 100} Q{target_q}")

time_range = st.sidebar.selectbox("Time Range", quarter_options, index=0)

# Manual refresh button clears cache and reloads data
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# ==================== LOAD AND FILTER MESSAGES ====================
with st.spinner("Loading messages from Slack..."):
    all_messages = load_all_messages()

# Filter messages by selected time range
if time_range == "All Time":
    filtered_messages = all_messages
else:
    # Parse "FY25 Q3" -> fiscal_year=2025, quarter=3
    match = re.match(r'FY(\d+) Q(\d)', time_range)
    if match:
        fy, q = int(match.group(1)) + 2000, int(match.group(2))
        # Keep only messages matching selected fiscal quarter
        filtered_messages = [m for m in all_messages if get_fiscal_quarter(m['timestamp'])[:2] == (fy, q)]
    else:
        filtered_messages = all_messages

# ==================== CLASSIFY MESSAGES (IF SNOWFLAKE AVAILABLE) ====================
classification = None
if SNOWFLAKE_AVAILABLE and filtered_messages:
    with st.spinner("Classifying messages with Snowflake Cortex..."):
        classification = classify_messages_with_snowflake(filtered_messages)

# ==================== DISPLAY METRICS ====================
# Show 3 columns if Snowflake classification is available, otherwise just 1
if classification:
    col1, col2, col3 = st.columns(3)
else:
    col1 = st.columns(1)[0]

with col1:
    st.metric("Total Messages", len(filtered_messages), help=f"AI Acquisition messages in {time_range}")

# Show Call Assist and Slack Assist metrics if Snowflake classification is available
if classification:
    with col2:
        st.metric("Call Assist", classification['call_assist'], help="Requests to join calls/meetings")
    with col3:
        st.metric("Slack Assist", classification['slack_assist'], help="Help provided via Slack thread")

st.markdown("---")

# ==================== TOP PERFORMERS CHART ====================
if filtered_messages:
    st.subheader("🏆 Top Performers")
    st.caption("Based on answers with ✅ reactions")
    
    # Calculate scores by checking thread replies for white_check_mark reactions
    with st.spinner("Analyzing thread replies..."):
        top_performers = SlackMonitor().get_top_performers(filtered_messages, config.SLACK_CHANNEL_ID)
    
    if top_performers:
        # Create horizontal bar chart with top 10 performers
        df = pd.DataFrame(list(top_performers.items())[:10], columns=['Performer', 'Answers with ✅'])
        fig = px.bar(df, x='Answers with ✅', y='Performer', orientation='h',
                     title='Top 10 Contributors', color='Answers with ✅',
                     color_continuous_scale='Blues', text='Answers with ✅')
        # Sort bars by value (lowest at bottom, highest at top)
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False, height=400)
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No verified answers found.")
    st.markdown("---")

# ==================== QUARTERLY BREAKDOWN ====================
if filtered_messages:
    st.subheader("📅 Quarterly Breakdown")
    
    # Count messages per fiscal quarter
    quarterly_data = {}
    for msg in filtered_messages:
        fy, q, name = get_fiscal_quarter(msg['timestamp'])
        if name not in quarterly_data:
            quarterly_data[name] = {'count': 0, 'fy': fy, 'q': q}
        quarterly_data[name]['count'] += 1
    
    # Sort by fiscal year and quarter (most recent first)
    sorted_quarters = sorted(quarterly_data.items(), key=lambda x: (x[1]['fy'], x[1]['q']), reverse=True)
    
    # Display up to 4 quarters as metric cards
    cols = st.columns(min(4, len(sorted_quarters)))
    for idx, (name, data) in enumerate(sorted_quarters[:4]):
        cols[idx].metric(name, data['count'])
    st.markdown("---")

# ==================== MESSAGE TABLE ====================
if filtered_messages:
    st.subheader(f"📋 Messages ({len(filtered_messages)} total)")
    
    # Build table data with cleaned message text
    df = pd.DataFrame([{
        'Date': m['timestamp'].strftime('%Y-%m-%d'),
        'Time': m['timestamp'].strftime('%H:%M'),
        'User': m['user_name'],
        'Message': clean_slack_formatting(m['message_text'])
    } for m in filtered_messages])
    
    st.dataframe(df, use_container_width=True, height=500)
    
    # CSV download button
    st.markdown("---")
    st.download_button("📥 Download CSV", df.to_csv(index=False),
                       f"ai_acquisition_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
else:
    st.warning(f"No messages found in {time_range}.")

# ==================== FOOTER ====================
st.markdown("---")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data: {time_range}")
