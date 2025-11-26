from datetime import datetime
import pytz
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import config

class SlackMonitor:
    def __init__(self):
        self.client = WebClient(token=config.SLACK_BOT_TOKEN)
        self.timezone = pytz.timezone(config.TIMEZONE)
        self.ai_acq_group_id = 'S06TG9U38ET'  # AI Acquisition user group ID
    
    def get_ai_acq_messages(self, limit=1000):
        """Fetch all messages mentioning @ai_acq"""
        search_pattern = f"<!subteam^{self.ai_acq_group_id}"
        messages = []
        cursor = None
        total_checked = 0
        
        try:
            while total_checked < limit:
                response = self.client.conversations_history(
                    channel=config.SLACK_CHANNEL_ID,
                    limit=min(200, limit - total_checked),
                    cursor=cursor
                )
                
                for message in response.get('messages', []):
                    total_checked += 1
                    if 'user' in message and 'text' in message:
                        if search_pattern in message['text']:
                            messages.append({
                                'timestamp': datetime.fromtimestamp(float(message['ts']), tz=self.timezone),
                                'user_id': message['user'],
                                'user_name': self._get_user_name(message['user']),
                                'message_text': message['text']
                            })
                
                if response.get('has_more') and response.get('response_metadata', {}).get('next_cursor'):
                    cursor = response['response_metadata']['next_cursor']
                else:
                    break
            
            return messages
        except SlackApiError as e:
            print(f"Error: {e}")
            return []
    
    def _get_user_name(self, user_id):
        """Get user's display name"""
        try:
            response = self.client.users_info(user=user_id)
            return response['user'].get('real_name', response['user'].get('name', 'Unknown'))
        except:
            return 'Unknown'
