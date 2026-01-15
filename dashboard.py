
"""
Acquisition AI Specialists Dashboard

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
from slack_monitor import SlackMonitor
import config
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import Counter

# Try to import Snowflake for optional message classification feature
try:
    import snowflake.connector
    SNOWFLAKE_AVAILABLE = True
except (ImportError, AttributeError):
    SNOWFLAKE_AVAILABLE = False

# Custom CSS for better executive dashboard styling
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        border-radius: 10px;
        padding: 20px;
        color: white;
    }
    .stMetric > div {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .big-number {
        font-size: 2.5em;
        font-weight: bold;
        color: #1e3a5f;
    }
</style>
""", unsafe_allow_html=True)

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

def get_trailing_quarters(n=4):
    """
    Get list of the last n fiscal quarters (including current)
    This automatically updates as we move into new quarters.
    
    Returns: List of (fiscal_year, quarter_number) tuples
    """
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    current_fy, current_q, _ = get_fiscal_quarter(now)
    
    quarters = []
    fy, q = current_fy, current_q
    for _ in range(n):
        quarters.append((fy, q))
        q -= 1
        if q <= 0:
            q = 4
            fy -= 1
    return quarters


def filter_by_trailing_quarters(messages, n=4):
    """Filter messages to only include those from the trailing n quarters"""
    valid_quarters = set(get_trailing_quarters(n))
    return [m for m in messages if get_fiscal_quarter(m['timestamp'])[:2] in valid_quarters]


@st.cache_data(ttl=300)  # Cache for 5 minutes to avoid hitting Slack API on every refresh
def load_all_messages():
    """Load all AI Acquisition messages from Slack (cached)"""
    return SlackMonitor().get_ai_acq_messages(limit=1000)


@st.cache_data(ttl=300)
def get_thread_stats(messages, channel_id):
    """
    Get detailed thread statistics for executive metrics
    
    Returns dict with:
    - threads_with_replies: count of threads that have at least 1 reply
    - threads_with_resolution: count of threads with ✅ on a reply
    - total_response_time_seconds: sum of all response times (for avg calculation)
    - response_times: list of response times in minutes
    - responders: set of unique responders
    - active_responders: dict of responder -> reply count
    """
    monitor = SlackMonitor()
    stats = {
        'threads_with_replies': 0,
        'threads_with_resolution': 0,
        'response_times': [],
        'responders': set(),
        'active_responders': Counter(),
        'total_threads': len(messages)
    }
    
    for msg in messages:
        try:
            replies = monitor.client.conversations_replies(
                channel=channel_id, ts=msg['ts'], limit=1000).get('messages', [])
        except:
            continue
        
        # Skip parent message, only look at replies
        thread_replies = replies[1:] if len(replies) > 1 else []
        
        if thread_replies:
            stats['threads_with_replies'] += 1
            
            # Calculate response time (time from parent to first reply)
            parent_ts = float(msg['ts'])
            first_reply_ts = float(thread_replies[0].get('ts', parent_ts))
            response_time_minutes = (first_reply_ts - parent_ts) / 60
            if response_time_minutes > 0:
                stats['response_times'].append(response_time_minutes)
            
            # Track unique responders and their activity
            for reply in thread_replies:
                if 'user' in reply:
                    responder = monitor._get_user_name(reply['user'])
                    stats['responders'].add(responder)
                    stats['active_responders'][responder] += 1
                
                # Check for resolution (✅ reaction)
                reactions = reply.get('reactions', [])
                if any(r.get('name') == 'white_check_mark' for r in reactions):
                    stats['threads_with_resolution'] += 1
                    break  # Only count once per thread
    
    return stats


@st.cache_data(ttl=600)  # Cache for 10 minutes
def classify_messages_with_snowflake(messages):
    """
    Use Snowflake Cortex CLASSIFY_TEXT to categorize messages
    
    Classifies each message as either:
    - "Slack Assistance": Help provided through Slack thread
    - "Meeting Assist": Request to join a call or meeting
    
    Returns: {'slack_assist': count, 'call_assist': count} or None if unavailable
    """
    import json
    if not SNOWFLAKE_AVAILABLE or not messages:
        return None
    
    try:
        # Use Streamlit's connection method
        conn = st.connection("snowflake")
        slack_assist, call_assist = 0, 0
        
        # Only classify first 50 messages to avoid long processing time
        for msg in messages[:50]:
            clean_text = clean_slack_formatting(msg['message_text'])
            # Escape single quotes for SQL
            clean_text = clean_text.replace("'", "''")
            
            # Use Streamlit's query method with f-string
            query = f"""
            SELECT SNOWFLAKE.CORTEX.CLASSIFY_TEXT(
                '{clean_text}',
                ['Slack Assistance', 'Call Assist'],
                {{'task_description': 'Classify if this is a request for help via Slack thread or a request to join a call'}}
            ) as classification
            """
            
            result = conn.query(query)
            
            if not result.empty:
                classification = result.iloc[0]['CLASSIFICATION']
                if isinstance(classification, str):
                    classification = json.loads(classification)
                label = classification.get('label', '') if isinstance(classification, dict) else ''
                if label == 'Slack Assistance':
                    slack_assist += 1
                elif label == 'Call Assist':
                    call_assist += 1
        
        return {'slack_assist': slack_assist, 'call_assist': call_assist}
    except Exception as e:
        st.error(f"Classification error: {str(e)}")
        return None

def calculate_qoq_change(current_count, previous_count):
    """Calculate quarter-over-quarter percentage change"""
    if previous_count == 0:
        return None
    return ((current_count - previous_count) / previous_count) * 100

def format_response_time(minutes):
    """Format response time in human-readable format"""
    if minutes < 60:
        return f"{minutes:.0f}m"
    elif minutes < 1440:  # Less than 24 hours
        return f"{minutes/60:.1f}h"
    else:
        return f"{minutes/1440:.1f}d"




# ==================== HEADER ====================
st.title("🤖 Acquisition AI Specialists Dashboard")
st.markdown("**Executive Overview** | Real-time team performance and engagement metrics")
st.markdown("---")

# ==================== SIDEBAR - TIME RANGE SELECTION ====================
st.sidebar.title("⚙️ Settings")

# Get current fiscal quarter to build dropdown options
tz = pytz.timezone(config.TIMEZONE)
now = datetime.now(tz)
current_fy, current_q, _ = get_fiscal_quarter(now)

# Build list of last 8 quarters (e.g., ["All Time", "FY25 Q4", "FY25 Q3", ...])
quarter_options = ["Trailing 4 Quarters", "All Time"]
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
elif time_range == "Trailing 4 Quarters":
    filtered_messages = filter_by_trailing_quarters(all_messages, n=4)
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

# Show Call Assist and Slack Assist metrics if Snowflake classification is available
if classification:
    with col2:
        st.metric("Call Assist", classification['call_assist'], help="Requests to join calls/meetings")
    with col3:
        st.metric("Slack Assist", classification['slack_assist'], help="Help provided via Slack thread")



# ==================== GET THREAD STATS FOR EXECUTIVE METRICS ====================
thread_stats = None
if filtered_messages:
    with st.spinner("Analyzing thread engagement..."):
        thread_stats = get_thread_stats(filtered_messages, config.SLACK_CHANNEL_ID)

# ==================== EXECUTIVE SUMMARY METRICS (ROW 1) ====================
st.subheader("📊 Executive Summary")

# Get previous period data for trend calculation
if time_range == "Trailing 4 Quarters":
    # Compare to previous 4 quarters
    prev_quarters = get_trailing_quarters(8)[4:]  # Quarters 5-8
    prev_messages = [m for m in all_messages if get_fiscal_quarter(m['timestamp'])[:2] in set(prev_quarters)]
elif time_range != "All Time":
    # Compare to same quarter previous year
    match = re.match(r'FY(\d+) Q(\d)', time_range)
    if match:
        fy, q = int(match.group(1)) + 2000 - 1, int(match.group(2))  # Previous year
        prev_messages = [m for m in all_messages if get_fiscal_quarter(m['timestamp'])[:2] == (fy, q)]
    else:
        prev_messages = []
else:
    prev_messages = []

# Calculate trend
trend_delta = None
if prev_messages and filtered_messages:
    trend_delta = calculate_qoq_change(len(filtered_messages), len(prev_messages))

# Row 1: Key Volume Metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    delta_str = f"{trend_delta:+.1f}% vs prior" if trend_delta is not None else None
    st.metric("📨 Total Requests", len(filtered_messages), delta=delta_str,
              help=f"AI Acquisition requests in {time_range}")

with col2:
    unique_requesters = len(set(m['user_name'] for m in filtered_messages)) if filtered_messages else 0
    st.metric("👥 Unique Requesters", unique_requesters,
              help="Number of unique team members asking for help")

if thread_stats:
    with col3:
        response_rate = (thread_stats['threads_with_replies'] / thread_stats['total_threads'] * 100) if thread_stats['total_threads'] > 0 else 0
        st.metric("💬 Response Rate", f"{response_rate:.1f}%",
                  help="Percentage of requests that received at least one reply")
    
    with col4:
        resolution_rate = (thread_stats['threads_with_resolution'] / thread_stats['total_threads'] * 100) if thread_stats['total_threads'] > 0 else 0
        st.metric("✅ Resolution Rate", f"{resolution_rate:.1f}%",
                  help="Percentage of requests with verified answers (✅)")

# Row 2: Response Time and Team Metrics
st.markdown("")  # Spacing
col5, col6, col7, col8 = st.columns(4)

if thread_stats:
    with col5:
        avg_response = sum(thread_stats['response_times']) / len(thread_stats['response_times']) if thread_stats['response_times'] else 0
        st.metric("⏱️ Avg Response Time", format_response_time(avg_response),
                  help="Average time to first response")
    
    with col6:
        median_response = sorted(thread_stats['response_times'])[len(thread_stats['response_times'])//2] if thread_stats['response_times'] else 0
        st.metric("⏱️ Median Response", format_response_time(median_response),
                  help="Median time to first response")
    
    with col7:
        st.metric("🏃 Active Responders", len(thread_stats['responders']),
                  help="Team members who responded to requests")

# Show Call Assist and Slack Assist if Snowflake classification is available
if classification:
    with col8:
        call_pct = (classification['call_assist'] / (classification['call_assist'] + classification['slack_assist']) * 100) if (classification['call_assist'] + classification['slack_assist']) > 0 else 0
        st.metric("📞 Call Assist Rate", f"{call_pct:.1f}%",
                  help="Percentage of requests requiring call support")

st.markdown("---")

# ==================== QUARTERLY BREAKDOWN WITH TRENDS ====================
if filtered_messages:
    st.subheader("📅 Quarterly Performance")
    
    # Count messages per fiscal quarter
    quarterly_data = {}
    for msg in all_messages:  # Use all_messages to show full history
        fy, q, name = get_fiscal_quarter(msg['timestamp'])
        if name not in quarterly_data:
            quarterly_data[name] = {'count': 0, 'fy': fy, 'q': q}
        quarterly_data[name]['count'] += 1
    
    # Sort by fiscal year and quarter (most recent first)
    sorted_quarters = sorted(quarterly_data.items(), key=lambda x: (x[1]['fy'], x[1]['q']), reverse=True)
    
    # Show trailing 4 quarters with trend arrows
    cols = st.columns(4)
    for idx, (name, data) in enumerate(sorted_quarters[:4]):
        # Calculate QoQ change
        prev_q_idx = idx + 1
        delta = None
        if prev_q_idx < len(sorted_quarters):
            prev_count = sorted_quarters[prev_q_idx][1]['count']
            if prev_count > 0:
                delta = f"{((data['count'] - prev_count) / prev_count * 100):+.0f}%"
        
        cols[idx].metric(name, data['count'], delta=delta, 
                        help=f"Requests in {name}" + (f" ({delta} vs prior quarter)" if delta else ""))
    

# ==================== ACTIVITY HEATMAP ====================
if filtered_messages:
    st.subheader("🗓️ Activity Patterns")
    
    col_heat, col_dist = st.columns(2)
    
    with col_heat:
        # Day of week activity
        day_counts = Counter()
        for msg in filtered_messages:
            day_name = msg['timestamp'].strftime('%A')
            day_counts[day_name] += 1
        
        # Order days correctly
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_data = pd.DataFrame([
            {'Day': day, 'Requests': day_counts.get(day, 0)}
            for day in day_order
        ])
        
        fig = px.bar(day_data, x='Day', y='Requests',
                    title='Requests by Day of Week',
                    color='Requests', color_continuous_scale='Blues')
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_dist:
        # Hour of day activity
        hour_counts = Counter()
        for msg in filtered_messages:
            hour = msg['timestamp'].hour
            hour_counts[hour] += 1
        
        hour_data = pd.DataFrame([
            {'Hour': f"{h:02d}:00", 'Requests': hour_counts.get(h, 0)}
            for h in range(24)
        ])
        
        fig = px.bar(hour_data, x='Hour', y='Requests',
                    title='Requests by Hour of Day',
                    color='Requests', color_continuous_scale='Blues')
        fig.update_layout(height=300, showlegend=False, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    
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

# ==================== REQUESTER INSIGHTS ====================
if filtered_messages:
    st.subheader("📈 Top 10 Requesters")
    
    # Top requesters
    requester_counts = Counter(m['user_name'] for m in filtered_messages)
    top_requesters = pd.DataFrame([
        {'Requester': name, 'Requests': count}
        for name, count in requester_counts.most_common(10)
    ])
    
    fig = px.bar(top_requesters, x='Requests', y='Requester', orientation='h',
                color='Requests', color_continuous_scale='Oranges',
                text='Requests')
    fig.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False, height=400)
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)
    
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

