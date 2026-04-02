"""
Rule-based natural language command parser.

Design goal:
- keep it simple for beginners
- keep structure compatible with future AI/NLP upgrades
"""

from dataclasses import dataclass


@dataclass
class ParsedCommand:
    raw_text: str
    intent: str
    entities: dict
    steps: list
    priority: int
    emergency: bool
    urgency: str
    response_mode: str


class CommandParser:
    """
    Tiny NLP parser using keyword rules.

    Output:
    - intent
    - extracted entities
    - task pipeline steps
    """

    def __init__(self):
        self.location_map = {
            "kitchen": "kitchen",
            "bedroom": "bedroom",
            "living room": "living_room",
            "livingroom": "living_room",
            "hall": "hall",
            "hallway": "hall",
        }
        self.object_map = {
            "water": "water_bottle",
            "water bottle": "water_bottle",
            "bottle": "water_bottle",
        }

    def parse(self, text):
        raw = text.strip()
        normalized = self._normalize(raw)

        intent = self._detect_intent(normalized)
        entities = {
            "location": self._extract_location(normalized),
            "object": self._extract_object(normalized),
            "person": "person" if self._mentions_person(normalized) else None,
        }
        steps = self._build_steps(intent, entities)
        priority, emergency = self._task_meta(intent)
        urgency = self._detect_urgency(raw, normalized, intent)
        response_mode = "immediate" if urgency == "high" else "normal"

        return ParsedCommand(
            raw_text=raw,
            intent=intent,
            entities=entities,
            steps=steps,
            priority=priority,
            emergency=emergency,
            urgency=urgency,
            response_mode=response_mode,
        )

    def _normalize(self, text):
        # Lowercase and simplify punctuation for easy keyword matching.
        lowered = text.lower()
        for mark in [",", ".", "?", "!", ";", ":"]:
            lowered = lowered.replace(mark, " ")
        return " ".join(lowered.split())

    def _detect_intent(self, text):
        if any(phrase in text for phrase in ["stop", "cancel task", "interrupt"]):
            return "interrupt"
        if any(word in text for word in ["help", "emergency", "assist"]):
            return "assist_person"
        if "come here" in text or "come to me" in text:
            return "come_to_person"
        if any(word in text for word in ["bring", "fetch", "get"]) and any(
            word in text for word in ["water", "bottle"]
        ):
            return "bring_object"
        return "unknown"

    def _extract_location(self, text):
        for phrase, location_id in self.location_map.items():
            if phrase in text:
                return location_id
        return None

    def _extract_object(self, text):
        for phrase, object_id in self.object_map.items():
            if phrase in text:
                return object_id
        return None

    def _mentions_person(self, text):
        words = ["me", "person", "elder", "patient", "him", "her"]
        return any(word in text for word in words)

    def _build_steps(self, intent, entities):
        """
        Convert intent+entities into an executable task pipeline.
        """
        steps = []

        if intent == "bring_object":
            location_id = entities["location"] or "kitchen"
            object_id = entities["object"] or "water_bottle"
            steps.extend(
                [
                    f"go_to_{location_id}",
                    f"pick_{object_id}",
                    "go_to_person",
                    f"deliver_{object_id}",
                ]
            )
            return steps

        if intent in ("assist_person", "come_to_person"):
            return ["go_to_person", "offer_help"]

        return []

    def _task_meta(self, intent):
        """
        Return (priority, emergency) for task manager scheduling.
        Larger priority value means higher priority.
        """
        if intent == "assist_person":
            return 100, True
        if intent == "interrupt":
            return 999, False
        if intent == "come_to_person":
            return 60, False
        if intent == "bring_object":
            return 20, False
        return 0, False

    def _detect_urgency(self, raw_text, normalized_text, intent):
        """
        Rule-based urgency detection.

        High urgency examples:
        - "help!"
        - "emergency"
        - panic words + exclamation marks
        """
        urgent_terms = [
            "help",
            "emergency",
            "urgent",
            "quick",
            "fast",
            "now",
            "asap",
            "immediately",
        ]
        if intent == "assist_person":
            return "high"
        if "!" in raw_text:
            return "high"
        if any(term in normalized_text for term in urgent_terms):
            return "high"
        return "normal"
