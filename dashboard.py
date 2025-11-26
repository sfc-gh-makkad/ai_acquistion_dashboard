"""
AI Acquisition Dashboard - Simplified with Dynamic Metrics

This dashboard:
1. Fetches AI Acquisition messages from Slack
2. Displays dynamic metrics based on selected time range
3. Optionally classifies messages using Snowflake Cortex
4. Shows messages in a clean table
"""

import streamlit as st
import pandas as pd
import re
import pytz
from datetime import datetime, timedelta
from slack_monitor import SlackMonitor
import config

# ============================================================================
# SNOWFLAKE SETUP (OPTIONAL)
# ============================================================================
# Try to import Snowflake connector for message classification
# If not available or credentials missing, dashboard will work without it
try:
    import snowflake.connector
    SNOWFLAKE_AVAILABLE = all([
        config.SNOWFLAKE_ACCOUNT,
        config.SNOWFLAKE_USER,
        config.SNOWFLAKE_PASSWORD
    ])
except (ImportError, AttributeError):
    SNOWFLAKE_AVAILABLE = False

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================
st.set_page_config(
    page_title="AI Acquisition Dashboard",
    page_icon="🤖",
    layout="wide"
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def clean_slack_formatting(text):
    """
    Remove Slack's special formatting characters for clean display
    
    Replaces:
    - User group mentions: <!subteam^ID> -> @AI_Acquisition
    - User mentions: <@USERID> -> (removed)
    - Links with text: <http://url|text> -> text
    - Plain links: <http://url> -> http://url
    
    Args:
        text (str): Raw Slack message text
        
    Returns:
        str: Cleaned text for display
    """
    text = re.sub(r'<!subteam\^[^>]+>', '@AI_Acquisition', text)
    text = re.sub(r'<@\w+>', '', text)
    text = re.sub(r'<https?://[^|>]+\|([^>]+)>', r'\1', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    return text.strip()

def get_fiscal_quarter(date):
    """
    Calculate fiscal quarter based on Snowflake's fiscal calendar
    
    Rules:
    - Fiscal year starts in February
    - Fiscal year is named after the calendar year at end of Q4
    - Quarter cutoffs: Feb, May, Aug, Nov
    
    Fiscal quarters:
    - Q1: Feb, Mar, Apr
    - Q2: May, Jun, Jul
    - Q3: Aug, Sep, Oct
    - Q4: Nov, Dec, Jan
    
    Args:
        date (datetime): Date to check
        
    Returns:
        tuple: (fiscal_year, quarter_number, quarter_name)
    
    Examples:
        - Aug 2024 -> FY25 Q3 (Q4 ends Jan 2025, so FY25)
        - Nov 2024 -> FY25 Q4
        - Jan 2025 -> FY25 Q4 (last month of FY25)
        - Feb 2025 -> FY26 Q1 (new fiscal year)
    """
    month = date.month
    year = date.year
    
    if month in [2, 3, 4]:  # Q1
        quarter = 1
        fiscal_year = year + 1
    elif month in [5, 6, 7]:  # Q2
        quarter = 2
        fiscal_year = year + 1
    elif month in [8, 9, 10]:  # Q3
        quarter = 3
        fiscal_year = year + 1
    else:  # Q4 (Nov, Dec, Jan)
        quarter = 4
        fiscal_year = year + 1 if month in [11, 12] else year
    
    return fiscal_year, quarter, f"FY{fiscal_year % 100} Q{quarter}"

@st.cache_data(ttl=600)  # Cache for 10 minutes
def classify_messages_with_snowflake(messages):
    """
    Use Snowflake Cortex CLASSIFY_TEXT to categorize messages
    
    Classifies each message as either:
    - "Slack Assistance": Help provided through Slack thread
    - "Call Assist": Request to join a call or meeting
    
    Args:
        messages (list): List of message dictionaries
        
    Returns:
        dict: {'slack_assist': count, 'call_assist': count} or None if unavailable
    """
    if not SNOWFLAKE_AVAILABLE or not messages:
        return None
    
    try:
        # Connect to Snowflake
        conn = snowflake.connector.connect(
            account=config.SNOWFLAKE_ACCOUNT,
            user=config.SNOWFLAKE_USER,
            password=config.SNOWFLAKE_PASSWORD,
            warehouse=config.SNOWFLAKE_WAREHOUSE,
            database=config.SNOWFLAKE_DATABASE,
            schema=config.SNOWFLAKE_SCHEMA
        )
        cursor = conn.cursor()
        
        # Initialize counters
        slack_assist = 0
        call_assist = 0
        
        # Only classify first 50 messages to avoid long processing time
        for msg in messages[:50]:
            clean_text = clean_slack_formatting(msg['message_text'])
            
            # Call Snowflake Cortex CLASSIFY_TEXT function
            query = """
            SELECT SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
                %s,
                ['Slack Assistance', 'Call Assist'],
                {
                    'task_description': 'Classify if this is a request for help via Slack thread or a request to join a call'
                }
            ) as classification
            """
            
            cursor.execute(query, (clean_text,))
            result = cursor.fetchone()
            
            if result:
                classification = result[0]
                
                # Parse JSON string if needed
                if isinstance(classification, str):
                    import json
                    classification = json.loads(classification)
                
                # Get the label from classification result
                label = classification.get('label', '') if isinstance(classification, dict) else ''
                
                # Count the classification
                if label == 'Slack Assistance':
                    slack_assist += 1
                elif label == 'Call Assist':
                    call_assist += 1
        
        cursor.close()
        conn.close()
        
        return {
            'slack_assist': slack_assist,
            'call_assist': call_assist
        }
        
    except Exception as e:
        st.error(f"Classification error: {str(e)}")
        return None

# ============================================================================
# MAIN APPLICATION
# ============================================================================

# Header
st.title("🤖 AI Acquisition Dashboard")
st.markdown("---")

# ============================================================================
# SIDEBAR - TIME RANGE SELECTION
# ============================================================================
st.sidebar.title("⚙️ Settings")

# Generate quarter options based on current date
tz = pytz.timezone(config.TIMEZONE)
now = datetime.now(tz)
current_fy, current_q, current_q_name = get_fiscal_quarter(now)

# Create list of recent quarters (last 8 quarters going backwards)
quarter_options = ["All Time"]

# Calculate total quarters from current position
# We go back 8 quarters from current quarter
for i in range(8):
    # Calculate how many quarters back from current
    quarters_back = i
    
    # Calculate the target quarter number (1-4, cycling backwards)
    target_q = current_q - quarters_back
    
    # Calculate how many years to go back
    years_back = 0
    while target_q <= 0:
        target_q += 4
        years_back += 1
    
    target_fy = current_fy - years_back
    quarter_options.append(f"FY{target_fy % 100} Q{target_q}")

# User selects time range for filtering
time_range = st.sidebar.selectbox(
    "Time Range",
    quarter_options,
    index=0  # Default to "All Time"
)

# Manual refresh button
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_all_messages():
    """Load all AI Acquisition messages from Slack"""
    monitor = SlackMonitor()
    return monitor.get_ai_acq_messages(limit=1000)

# Load all messages (cached)
with st.spinner("Loading messages from Slack..."):
    all_messages = load_all_messages()
        
# ============================================================================
# FILTER MESSAGES BY SELECTED TIME RANGE
# ============================================================================

# Filter messages based on selected time range
if time_range == "All Time":
    # Show all messages
    filtered_messages = all_messages
else:
    # Parse selected quarter (e.g., "FY25 Q1")
    # Extract fiscal year and quarter number
    import re
    match = re.match(r'FY(\d+) Q(\d)', time_range)
    if match:
        fy = int(match.group(1)) + 2000  # Convert FY25 -> 2025
        q = int(match.group(2))
        
        # Filter messages that belong to this fiscal quarter
        filtered_messages = []
        for msg in all_messages:
            msg_fy, msg_q, _ = get_fiscal_quarter(msg['timestamp'])
            if msg_fy == fy and msg_q == q:
                filtered_messages.append(msg)
    else:
        filtered_messages = all_messages

# ============================================================================
# CALCULATE METRICS BASED ON FILTERED MESSAGES
# ============================================================================

# Total messages in selected period
total_messages = len(filtered_messages)

# ============================================================================
# CLASSIFY MESSAGES (IF SNOWFLAKE AVAILABLE)
# ============================================================================
classification = None
if SNOWFLAKE_AVAILABLE and filtered_messages:
    with st.spinner("Classifying messages with Snowflake Cortex..."):
        classification = classify_messages_with_snowflake(filtered_messages)

# ============================================================================
# DISPLAY METRICS
# ============================================================================

# Create columns based on whether classification is available
if classification:
    col1, col2, col3 = st.columns(3)
else:
    col1 = st.columns(1)[0]

# Metric 1: Total Messages in selected period
with col1:
    st.metric(
        label="Total Messages",
        value=total_messages,
        help=f"Total AI Acquisition messages in {time_range}"
    )

# Metrics 2 & 3: Call Assist and Slack Assist (if Snowflake classification available)
if classification:
    with col2:
        st.metric(
            label="Call Assist",
            value=classification['call_assist'],
            help="Requests to join calls/meetings"
        )
    
    with col3:
        st.metric(
            label="Slack Assist",
            value=classification['slack_assist'],
            help="Help provided via Slack thread"
        )

st.markdown("---")

# ============================================================================
# QUARTERLY BREAKDOWN
# ============================================================================

if filtered_messages:
    st.subheader("📅 Quarterly Breakdown")
    
    # Calculate messages by quarter
    quarterly_data = {}
    for msg in filtered_messages:
        fiscal_year, quarter_num, quarter_name = get_fiscal_quarter(msg['timestamp'])
        if quarter_name not in quarterly_data:
            quarterly_data[quarter_name] = {
                'count': 0,
                'fiscal_year': fiscal_year,
                'quarter_num': quarter_num
            }
        quarterly_data[quarter_name]['count'] += 1
    
    # Sort by fiscal year and quarter
    sorted_quarters = sorted(
        quarterly_data.items(),
        key=lambda x: (x[1]['fiscal_year'], x[1]['quarter_num']),
        reverse=True  # Most recent first
    )
    
    # Display as columns (up to 4 quarters)
    if sorted_quarters:
        num_quarters = min(4, len(sorted_quarters))
        cols = st.columns(num_quarters)
        
        for idx, (quarter_name, data) in enumerate(sorted_quarters[:num_quarters]):
            with cols[idx]:
                st.metric(
                    label=quarter_name,
                    value=data['count'],
                    help=f"Messages in {quarter_name}"
                )
    
    st.markdown("---")

# ============================================================================
# MESSAGE TABLE
# ============================================================================

if filtered_messages:
    st.subheader(f"📋 Messages ({len(filtered_messages)} total)")
    
    # Prepare data for table display
    table_data = []
    for msg in filtered_messages:
        table_data.append({
            'Date': msg['timestamp'].strftime('%Y-%m-%d'),
            'Time': msg['timestamp'].strftime('%H:%M'),
            'User': msg['user_name'],
            'Message': clean_slack_formatting(msg['message_text'])
        })
    
    # Create DataFrame
    df = pd.DataFrame(table_data)
    
    # Display table
    st.dataframe(
        df,
        use_container_width=True,
        height=500
    )
    
    # Export functionality
    st.markdown("---")
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=f"ai_acquisition_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
    
else:
    # No messages found in selected time range
    st.warning(f"No AI Acquisition messages found in {time_range.lower()}.")
    st.info("Try selecting a different time range or checking your Slack connection.")

# ============================================================================
# FOOTER INFO
# ============================================================================
st.markdown("---")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
           f"Showing data for: {time_range}")
