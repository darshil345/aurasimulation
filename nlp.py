"""
Rule-based natural language understanding for voice/text commands.

This file is intentionally API-free and beginner-friendly.
"""


def parse_command(text):
    """
    Convert free-form text to a structured command.

    Returns:
    {
      "intent": "bring|go|help|stop|unknown",
      "object": "water|medicine|...",
      "location": "kitchen|bedroom|living_room|hall|none",
      "urgency": "normal|high",
      "normalized_text": "...",
    }
    """
    normalized = _normalize(text)
    tokens = normalized.split()

    intent = _extract_intent(normalized)
    obj = _extract_object(normalized)
    location = _extract_location(normalized)
    urgency = _extract_urgency(text, normalized, intent)

    return {
        "intent": intent,
        "object": obj,
        "location": location,
        "urgency": urgency,
        "normalized_text": normalized,
        "tokens": tokens,
    }


def generate_task_steps(parsed):
    """
    Convert structured command into task step list.
    """
    intent = parsed["intent"]
    obj = parsed["object"]
    location = parsed["location"]

    if intent == "bring":
        chosen_object = obj or "water_bottle"
        object_step = _map_object_to_step_name(chosen_object)
        target_location = location or "kitchen"
        return [
            f"go_to_{target_location}",
            f"pick_{object_step}",
            "go_to_person",
            f"deliver_{object_step}",
        ]

    if intent == "go":
        return [f"go_to_{location or 'hall'}"]

    if intent == "help":
        return ["go_to_person", "offer_help"]

    if intent == "stop":
        return []

    return []


def build_command_payload(text):
    """
    Full NLU pipeline:
    speech/text -> parsed intent/entities -> task payload for TaskManager.
    """
    parsed = parse_command(text)
    steps = generate_task_steps(parsed)

    intent_map = {
        "bring": "bring_object",
        "go": "go_to_location",
        "help": "assist_person",
        "stop": "interrupt",
    }
    mapped_intent = intent_map.get(parsed["intent"], "unknown")
    is_emergency = parsed["intent"] == "help" and parsed["urgency"] == "high"
    if parsed["intent"] == "help":
        is_emergency = True

    priority = 0
    if mapped_intent == "assist_person":
        priority = 100
    elif mapped_intent == "interrupt":
        priority = 999
    elif mapped_intent == "bring_object":
        priority = 20
    elif mapped_intent == "go_to_location":
        priority = 15

    return {
        "raw_text": text.strip(),
        "intent": mapped_intent,
        "entities": {
            "object": parsed["object"],
            "location": parsed["location"],
        },
        "steps": steps,
        "priority": priority,
        "emergency": is_emergency,
        "urgency": parsed["urgency"],
        "response_mode": "immediate" if parsed["urgency"] == "high" else "normal",
        "parsed": parsed,
    }


def _normalize(text):
    out = text.lower().strip()
    for mark in [",", ".", "?", "!", ";", ":"]:
        out = out.replace(mark, " ")
    return " ".join(out.split())


def _extract_intent(text):
    if any(term in text for term in ["help", "emergency", "i fell", "fall", "save me"]):
        return "help"
    if any(term in text for term in ["stop", "cancel", "interrupt"]):
        return "stop"
    if any(term in text for term in ["bring", "fetch", "get"]):
        return "bring"
    if any(term in text for term in ["go to", "move to", "navigate to"]):
        return "go"
    return "unknown"


def _extract_object(text):
    if "water bottle" in text:
        return "water_bottle"
    if "water" in text:
        return "water_bottle"
    if "medicine" in text or "med" in text:
        return "medicine"
    return None


def _extract_location(text):
    if "kitchen" in text:
        return "kitchen"
    if "bedroom" in text:
        return "bedroom"
    if "living room" in text or "livingroom" in text:
        return "living_room"
    if "hallway" in text or "hall" in text:
        return "hall"
    return None


def _extract_urgency(raw_text, normalized_text, intent):
    if intent == "help":
        return "high"
    if "!" in raw_text:
        return "high"
    urgent_terms = ["emergency", "urgent", "quick", "asap", "now", "immediately"]
    if any(term in normalized_text for term in urgent_terms):
        return "high"
    return "normal"


def _map_object_to_step_name(obj):
    if obj in ("water", "water_bottle"):
        return "water_bottle"
    return obj
