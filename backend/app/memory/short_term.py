from typing import Dict, Any

class ShortTermMemory:
    def __init__(self):
        self.state: Dict[str, Any] = {}
        
    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)
        
    def set(self, key: str, value: Any):
        self.state[key] = value
        
    def clear(self):
        self.state.clear()
