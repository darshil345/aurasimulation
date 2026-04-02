"""
Simple pub/sub event system for module communication.

Why this helps:
- modules stay loosely coupled
- robot, world, and UI can communicate without direct imports
"""


class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event_name, handler):
        """Register a handler function for a specific event."""
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    def publish(self, event_name, payload=None):
        """Notify all handlers listening to an event."""
        handlers = self._handlers.get(event_name, [])
        for handler in handlers:
            handler(payload if payload is not None else {})
