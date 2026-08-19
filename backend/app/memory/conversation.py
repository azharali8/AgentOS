from typing import List, Dict

class ConversationMemory:
    def __init__(self):
        self.messages: List[Dict[str, str]] = []
        
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        
    def get_messages(self) -> List[Dict[str, str]]:
        return self.messages
