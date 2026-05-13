"""
Chat Manager - Handles real-time messaging
Saves messages and tracks online users
"""

import json
import os
from datetime import datetime
import threading

class ChatManager:
    """
    Manages chat messages and conversations between farmers and agro-vets
    """
    
    def __init__(self, storage_file='data/messages.json'):
        self.storage_file = storage_file
        self.messages = {}
        self.online_users = {}
        self.typing_status = {}
        self.lock = threading.Lock()
        
        # Create data directory
        os.makedirs(os.path.dirname(storage_file), exist_ok=True)
        
        # Load existing messages
        self._load_messages()
    
    def _load_messages(self):
        """Load messages from file"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    self.messages = json.load(f)
            except:
                self.messages = {}
    
    def _save_messages(self):
        """Save messages to file"""
        with open(self.storage_file, 'w') as f:
            json.dump(self.messages, f, indent=2)
    
    def save_message(self, sender_id, receiver_id, message, message_type='text', image_url=None):
        """
        Save a message between two users
        
        Args:
            sender_id: ID of sender
            receiver_id: ID of receiver
            message: Message text
            message_type: 'text', 'image', 'voice'
            image_url: URL if sending image
        
        Returns:
            Saved message object
        """
        with self.lock:
            # Create conversation ID (sorted for consistency)
            conv_id = self._get_conversation_id(sender_id, receiver_id)
            
            # Create message object
            msg = {
                'id': f"{sender_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'message': message,
                'type': message_type,
                'image_url': image_url,
                'timestamp': datetime.now().isoformat(),
                'read': False
            }
            
            # Initialize conversation if not exists
            if conv_id not in self.messages:
                self.messages[conv_id] = {
                    'participants': sorted([str(sender_id), str(receiver_id)]),
                    'messages': []
                }
            
            # Add message
            self.messages[conv_id]['messages'].append(msg)
            
            # Save to file
            self._save_messages()
            
            return msg
    
    def get_conversation(self, user1_id, user2_id, limit=50):
        """Get conversation between two users"""
        conv_id = self._get_conversation_id(user1_id, user2_id)
        
        if conv_id in self.messages:
            messages = self.messages[conv_id]['messages']
            return messages[-limit:] if len(messages) > limit else messages
        
        return []
    
    def get_user_conversations(self, user_id):
        """Get all conversations for a user"""
        conversations = []
        
        for conv_id, conv_data in self.messages.items():
            if str(user_id) in [str(p) for p in conv_data['participants']]:
                # Get other participant
                other_user = [p for p in conv_data['participants'] if str(p) != str(user_id)][0]
                
                # Get last message
                last_message = conv_data['messages'][-1] if conv_data['messages'] else None
                
                # Count unread messages
                unread_count = sum(1 for m in conv_data['messages'] 
                                  if str(m['receiver_id']) == str(user_id) and not m['read'])
                
                conversations.append({
                    'conversation_id': conv_id,
                    'other_user_id': other_user,
                    'last_message': last_message,
                    'unread_count': unread_count,
                    'timestamp': last_message['timestamp'] if last_message else None
                })
        
        # Sort by timestamp
        conversations.sort(key=lambda x: x['timestamp'] or '', reverse=True)
        
        return conversations
    
    def mark_as_read(self, user_id, sender_id):
        """Mark messages as read"""
        conv_id = self._get_conversation_id(user_id, sender_id)
        
        if conv_id in self.messages:
            for msg in self.messages[conv_id]['messages']:
                if str(msg['receiver_id']) == str(user_id) and str(msg['sender_id']) == str(sender_id):
                    msg['read'] = True
            
            self._save_messages()
    
    def set_user_online(self, user_id, session_id, user_info=None):
        """Set user as online"""
        self.online_users[str(user_id)] = {
            'session_id': session_id,
            'online': True,
            'last_seen': datetime.now().isoformat(),
            'user_info': user_info or {}
        }
    
    def set_user_offline(self, user_id):
        """Set user as offline"""
        if str(user_id) in self.online_users:
            self.online_users[str(user_id)]['online'] = False
            self.online_users[str(user_id)]['last_seen'] = datetime.now().isoformat()
    
    def is_user_online(self, user_id):
        """Check if user is online"""
        return str(user_id) in self.online_users and self.online_users[str(user_id)]['online']
    
    def get_online_users(self):
        """Get list of online users"""
        return [uid for uid, data in self.online_users.items() if data['online']]
    
    def get_user_info(self, user_id):
        """Get user info by ID"""
        if str(user_id) in self.online_users:
            return self.online_users[str(user_id)]['user_info']
        return None
    
    def set_typing(self, user_id, receiver_id, is_typing):
        """Set typing status"""
        key = f"{user_id}_{receiver_id}"
        self.typing_status[key] = is_typing
    
    def get_typing_status(self, user_id, receiver_id):
        """Get typing status"""
        key = f"{receiver_id}_{user_id}"
        return self.typing_status.get(key, False)
    
    def _get_conversation_id(self, user1_id, user2_id):
        """Generate unique conversation ID"""
        return '_'.join(sorted([str(user1_id), str(user2_id)]))


# Create global instance
chat_manager = ChatManager()