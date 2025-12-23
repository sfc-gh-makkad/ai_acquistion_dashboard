"""
Slack Monitor - Fetches AI Acquisition messages and calculates top performers

This module connects to Slack API to:
1. Fetch messages that mention the @ai_acq user group
2. Analyze thread replies for white_check_mark reactions
3. Calculate which team members have the most verified answers
"""

from datetime import datetime
import pytz
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import config

class SlackMonitor:
    def __init__(self):
        # Initialize Slack client with bot token from .env
        self.client = WebClient(token=config.SLACK_BOT_TOKEN)
        self.timezone = pytz.timezone(config.TIMEZONE)
        # This is the Slack user group ID for @ai_acq - find yours in Slack admin
        self.ai_acq_group_id = 'S06TG9U38ET'

    def get_ai_acq_messages(self, limit=1000):
        """
        Fetch all messages that mention @ai_acq user group
        
        How it works:
        - Slack stores user group mentions as <!subteam^GROUP_ID> in message text
        - We paginate through channel history looking for this pattern
        - Returns list of message dicts with timestamp, user info, and text
        """
        # Slack's internal format for user group mentions
        search_pattern = f"<!subteam^{self.ai_acq_group_id}"
        messages, cursor, total = [], None, 0
        
        try:
            while total < limit:
                # Fetch batch of messages (max 200 per API call)
                response = self.client.conversations_history(
                    channel=config.SLACK_CHANNEL_ID, limit=min(200, limit - total), cursor=cursor)
                
                for msg in response.get('messages', []):
                    total += 1
                    # Only include messages from users (not bots) that mention @ai_acq
                    if 'user' in msg and 'text' in msg and search_pattern in msg['text']:
                        messages.append({
                            'timestamp': datetime.fromtimestamp(float(msg['ts']), tz=self.timezone),
                            'user_id': msg['user'],
                            'user_name': self._get_user_name(msg['user']),
                            'message_text': msg['text'],
                            'ts': msg['ts']  # Thread timestamp - needed to fetch replies
                        })
                
                # Check if there are more messages to fetch
                cursor = response.get('response_metadata', {}).get('next_cursor')
                if not response.get('has_more') or not cursor:
                    break
            return messages
        except SlackApiError as e:
            print(f"Error: {e}")
            return []

    def _get_user_name(self, user_id):
        """Convert Slack user ID (e.g., U12345) to display name (e.g., 'John Smith')"""
        try:
            response = self.client.users_info(user=user_id)
            return response['user'].get('real_name', response['user'].get('name', 'Unknown'))
        except:
            return 'Unknown'

    def get_top_performers(self, messages, channel_id):
        """
        Calculate top performers based on verified answers (✅ reactions)
        
        Logic:
        1. For each message that mentions @ai_acq, fetch all thread replies
        2. Check each reply for a :white_check_mark: reaction
        3. If a reply has the checkmark, give that user a point
        4. Return sorted dict of {user_name: count}
        
        Example: If Hannah replies to a thread and someone adds ✅ to her reply,
        Hannah gets +1 point in the leaderboard
        """
        scores = {}
        
        for msg in messages:
            try:
                # Fetch all replies in this message's thread
                replies = self.client.conversations_replies(
                    channel=channel_id, ts=msg['ts'], limit=1000).get('messages', [])
            except SlackApiError:
                continue
            
            # Skip first message (it's the parent), check replies only
            for reply in replies[1:]:
                if 'user' not in reply:
                    continue
                    
                # Check if this reply has a white_check_mark reaction
                # Reactions are stored as: [{'name': 'white_check_mark', 'count': 1, 'users': [...]}]
                reactions = reply.get('reactions', [])
                if any(r.get('name') == 'white_check_mark' for r in reactions):
                    name = self._get_user_name(reply['user'])
                    scores[name] = scores.get(name, 0) + 1
        
        # Sort by score descending (highest first)
        return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))
