"""
Task manager with steps, queueing, priority, and interruption.

Beginner note:
- A task is a high-level job (example: "bring water")
- A step is one small action in that task (example: "go_to_kitchen")
"""


class TaskManager:
    def __init__(self, event_bus, world):
        self.event_bus = event_bus
        self.world = world

        self._task_id_counter = 1
        self.current_task = None
        self.queue = []
        self.action_timer = 0.0
        self.held_object = None
        self.paused_for_charging = False
        self.paused_task = None
        self.paused_queue = []
        self.personality = {
            "polite": True,
            "efficient": True,
        }

        self.event_bus.subscribe("command_parsed", self._on_command_parsed)
        self.event_bus.subscribe("robot_reached_target", self._on_robot_reached_target)
        self.event_bus.subscribe("interrupt_tasks", self._on_interrupt_tasks)
        self.event_bus.subscribe("charging_requested", self._on_charging_requested)
        self.event_bus.subscribe("charging_complete", self._on_charging_complete)

    def update(self, dt):
        if self.paused_for_charging:
            return

        if self.current_task is None and self.queue:
            self.current_task = self.queue.pop(0)
            self.current_task["status"] = "running"
            self._start_current_step()
            self._publish_state()
            return

        if self.current_task is None:
            return

        if self._current_step_definition()["type"] == "action":
            self.action_timer -= dt
            if self.action_timer <= 0:
                self._advance_step()

    def _on_command_parsed(self, payload):
        if self.paused_for_charging:
            self.event_bus.publish(
                "ui_message",
                {"text": "Charging in progress. New command queued for after charging."},
            )
        intent = payload.get("intent", "unknown")
        urgency = payload.get("urgency", "normal")
        response_mode = payload.get("response_mode", "normal")

        self._publish_thought(
            self._build_thought_for_command(
                raw_text=payload.get("raw_text", ""),
                intent=intent,
                urgency=urgency,
                response_mode=response_mode,
            )
        )

        if intent == "interrupt":
            self._interrupt_all("User requested interrupt.")
            return

        steps = payload.get("steps", [])
        if not steps:
            self.event_bus.publish(
                "ui_message",
                {"text": "No executable steps found for this command."},
            )
            return

        task = {
            "id": self._task_id_counter,
            "name": payload.get("raw_text", "task"),
            "intent": intent,
            "priority": int(payload.get("priority", 0)),
            "emergency": bool(payload.get("emergency", False)),
            "urgency": urgency,
            "response_mode": response_mode,
            "steps": list(steps),
            "step_index": 0,
            "status": "pending",  # pending, running, done, interrupted
        }
        self._task_id_counter += 1

        if task["emergency"]:
            self._interrupt_all("Emergency override: switching to urgent task.")
            task["status"] = "running"
            self.current_task = task
            self._publish_thought("Urgency is high. Switching to immediate assistance.")
            self._start_current_step()
            self._publish_state()
            return

        self.queue.append(task)
        self.queue.sort(key=lambda item: item["priority"], reverse=True)
        self.event_bus.publish(
            "ui_message",
            {"text": f"Task queued (p{task['priority']}): {' -> '.join(task['steps'])}"},
        )
        if urgency == "normal":
            self._publish_thought("Command understood. Planning calm and efficient execution.")
        self._publish_state()

    def _on_robot_reached_target(self, _payload):
        if self.current_task is None:
            return
        if self._current_step_definition()["type"] != "navigate":
            return
        self._advance_step()

    def _on_interrupt_tasks(self, payload):
        reason = payload.get("reason", "Task interruption requested.")
        self._interrupt_all(reason)

    def _interrupt_all(self, reason):
        if self.current_task is not None:
            self.current_task["status"] = "interrupted"
            self.event_bus.publish(
                "robot_alert",
                {"text": f"Task interrupted: {self.current_task['name']}"},
            )
        self.current_task = None
        self.paused_task = None

        for task in self.queue:
            task["status"] = "interrupted"
        self.queue = []
        self.paused_queue = []
        self.paused_for_charging = False

        self.event_bus.publish("clear_target", {})
        self.event_bus.publish("ui_message", {"text": reason})
        self._publish_state()

    def _current_step_name(self):
        if self.current_task is None:
            return "none"
        idx = self.current_task["step_index"]
        return self.current_task["steps"][idx]

    def _current_step_definition(self):
        step_name = self._current_step_name()
        if step_name.startswith("go_to_"):
            target_id = step_name.replace("go_to_", "", 1)
            return {"name": step_name, "type": "navigate", "target_id": target_id}
        return {"name": step_name, "type": "action"}

    def _start_current_step(self):
        if self.current_task is None:
            return

        step = self._current_step_definition()
        self.event_bus.publish("ui_message", {"text": f"Executing: {step['name']}"})
        self._publish_thought(self._step_thought(step["name"], self.current_task.get("response_mode", "normal")))
        self._publish_response(self._step_response(step["name"]))

        if step["type"] == "navigate":
            target = self.world.get_target_by_id(step["target_id"])
            if target is None:
                self.event_bus.publish("robot_alert", {"text": f"Unknown target: {step['target_id']}"})
                self._advance_step()
                return
            self.event_bus.publish(
                "set_target",
                {
                    "target_id": target["id"],
                    "position": target["position"],
                    "label": target["label"],
                },
            )
            return

        # Action step simulation
        self.action_timer = 1.0
        if step["name"].startswith("pick_"):
            self.held_object = step["name"].replace("pick_", "", 1)
        if step["name"].startswith("deliver_"):
            self.held_object = None

    def _advance_step(self):
        if self.current_task is None:
            return
        self.current_task["step_index"] += 1
        if self.current_task["step_index"] >= len(self.current_task["steps"]):
            self.current_task["status"] = "done"
            self.event_bus.publish("ui_message", {"text": f"Task complete: {self.current_task['name']}"})
            self._publish_thought("Task finished. Ready for the next request.")
            self._publish_response("Task complete. I am ready for the next request.")
            self.current_task = None
            self._publish_state()
            return
        self._start_current_step()
        self._publish_state()

    def _publish_state(self):
        if self.paused_for_charging:
            current_task_name = self.paused_task["name"] if self.paused_task else "none"
            current_task_status = "paused_for_charging"
            current_step = self.paused_task["steps"][self.paused_task["step_index"]] if self.paused_task else "none"
            queue_view = [
                f"[p{task['priority']}] {task['intent']} (paused)"
                for task in self.paused_queue
            ]
        else:
            current_task_name = self.current_task["name"] if self.current_task else "none"
            current_task_status = self.current_task["status"] if self.current_task else "idle"
            current_step = self._current_step_name() if self.current_task else "none"
            queue_view = [
                f"[p{task['priority']}] {task['intent']} ({task['status']})"
                for task in self.queue
            ]

        self.event_bus.publish(
            "task_manager_update",
            {
                "current_task": current_task_name,
                "current_task_status": current_task_status,
                "current_step": current_step,
                "queue": queue_view,
                "held_object": self.held_object if self.held_object else "none",
                "personality": "polite + efficient",
                "charging_pause": self.paused_for_charging,
            },
        )

    def _build_thought_for_command(self, raw_text, intent, urgency, response_mode):
        """Create a human-readable 'thought' line for UI."""
        if intent == "assist_person":
            return "I heard an urgent help request. Responding immediately."
        if intent == "bring_object":
            return "Request received for item delivery. Planning the shortest safe steps."
        if intent == "come_to_person":
            return "Understood. Moving to the person now."
        if intent == "interrupt":
            return "Interrupt received. Stopping current actions."
        if response_mode == "immediate" or urgency == "high":
            return f"Urgent tone detected in '{raw_text}'. Prioritizing quick response."
        return f"Command understood: '{raw_text}'. Executing politely and efficiently."

    def _step_thought(self, step_name, response_mode):
        if response_mode == "immediate":
            return f"Urgent mode: executing {step_name} without delay."
        return f"Efficient mode: now running {step_name}."

    def _publish_thought(self, text):
        self.event_bus.publish("robot_thought", {"text": text})

    def _publish_response(self, text):
        self.event_bus.publish("robot_response", {"text": text})

    def _on_charging_requested(self, payload):
        if self.paused_for_charging:
            return

        self.paused_for_charging = True
        self.paused_task = self.current_task
        self.paused_queue = list(self.queue)
        self.current_task = None
        self.queue = []

        if self.paused_task is not None:
            self.paused_task["status"] = "paused"

        battery = payload.get("battery", "unknown")
        self.event_bus.publish(
            "ui_message",
            {"text": f"Battery {battery}%. Tasks paused. Robot auto-charging in place."},
        )
        self._publish_response("Battery is low. I am auto-charging now.")
        self._publish_thought("Pausing tasks for automatic charging.")
        self._publish_state()

    def _on_charging_complete(self, _payload):
        if not self.paused_for_charging:
            return

        self.paused_for_charging = False
        self.queue = list(self.paused_queue)
        self.paused_queue = []

        if self.paused_task is not None:
            self.current_task = self.paused_task
            self.current_task["status"] = "running"
            self.paused_task = None
            self._publish_thought("Charging complete. Resuming paused task.")
            self._start_current_step()
        else:
            self._publish_thought("Charging complete. Resuming queued tasks.")

        self.event_bus.publish("ui_message", {"text": "Charging finished. Tasks resumed."})
        self._publish_response("Charging complete. Resuming tasks now.")
        self._publish_state()

    def _step_response(self, step_name):
        if step_name.startswith("go_to_"):
            place = step_name.replace("go_to_", "", 1).replace("_", " ")
            if place == "person":
                return "Okay, I am coming to you now."
            return f"Okay, I am going to the {place}."
        if step_name.startswith("pick_"):
            obj = step_name.replace("pick_", "", 1).replace("_", " ")
            return f"I found the {obj}."
        if step_name.startswith("deliver_"):
            obj = step_name.replace("deliver_", "", 1).replace("_", " ")
            return f"Here is your {obj}."
        if step_name == "offer_help":
            return "I am here to help. Please stay calm."
        return "Understood. Executing the next action."
