from copy import deepcopy

class ScriptedActor:
    """Explicit deterministic test double; never selected by configuration."""
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.closed = False

    def respond(self, messages, tools, timeout):
        self.requests.append(deepcopy({'messages': messages, 'tools': tools}))
        return deepcopy(next(self.replies))

    def close(self):
        self.closed = True
