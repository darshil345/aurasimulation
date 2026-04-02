"""
Entry point.

This file stays small on purpose:
- build shared EventBus
- start Engine
"""

from core.engine import Engine
from core.event_system import EventBus


def main():
    bus = EventBus()
    engine = Engine(event_bus=bus)
    engine.run()


if __name__ == "__main__":
    main()
