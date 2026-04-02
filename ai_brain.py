"""
Layered AI brain (rule-based):
- Reactive layer: immediate safety/urgent response
- Planning layer: context-aware routine behavior
"""

from config import AI_UPDATE_INTERVAL


class AIBrain:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.robot_state = {
            "state": "idle",
            "target": "none",
            "battery": 100.0,
        }
        self.task_state = {
            "current_task": "none",
            "charging_pause": False,
        }
        self.person_state = {
            "state": "idle",
            "fallen": False,
            "position": (0.0, 0.0),
        }
        self.sensor_state = {
            "person_detected": False,
            "obstacle_ahead": False,
        }

        self.ai_timer = 0.0
        self.ai_interval = AI_UPDATE_INTERVAL
        self._emergency_active = False
        self._roam_index = 0
        self._plan_cooldown = 0.0
        self._roam_targets = ["hall", "living_room", "kitchen", "bedroom"]

        self.event_bus.subscribe("robot_state", self._on_robot_state)
        self.event_bus.subscribe("task_manager_update", self._on_task_state)
        self.event_bus.subscribe("person_state", self._on_person_state)
        self.event_bus.subscribe("sensor_update", self._on_sensor_state)

    def update(self, dt, world):
        self.ai_timer += dt
        self._plan_cooldown = max(0.0, self._plan_cooldown - dt)
        if self.ai_timer < self.ai_interval:
            return
        self.ai_timer = 0.0

        action = self.decide_action(
            robot_state=self.robot_state,
            environment=world.get_environment_snapshot(),
        )
        if action is None:
            return
        self._execute_action(action, world)

    def decide_action(self, robot_state, environment):
        """
        Layered decision making:
        1) Reactive layer: emergencies and immediate hazards
        2) Planning layer: deliberate goals / roaming
        """
        reactive = self._reactive_layer(robot_state, environment)
        if reactive is not None:
            return reactive
        return self._planning_layer(robot_state, environment)

    def _reactive_layer(self, robot_state, environment):
        # Highest priority: person fallen -> override everything.
        if environment.get("person_fallen", False):
            return {
                "type": "emergency_to_person",
                "reason": "Person fallen detected",
            }
        return None

    def _planning_layer(self, robot_state, environment):
        # Do not inject plans while tasks are active or charging workflow is paused.
        if self.task_state.get("charging_pause", False):
            return None
        if self.task_state.get("current_task", "none") != "none":
            return None
        if robot_state.get("state") == "charging":
            return None
        if self._plan_cooldown > 0:
            return None

        # Context-aware idle roam.
        if robot_state.get("state") in ("idle",):
            target_id = self._roam_targets[self._roam_index % len(self._roam_targets)]
            self._roam_index += 1
            return {
                "type": "roam_target",
                "target_id": target_id,
            }
        return None

    def _execute_action(self, action, world):
        action_type = action.get("type")
        if action_type == "emergency_to_person":
            if self._emergency_active:
                return
            self._emergency_active = True

            person_target = world.get_target_by_id("person")
            if person_target is None:
                return

            self.event_bus.publish("interrupt_tasks", {"reason": "Emergency override: person may have fallen."})
            self.event_bus.publish(
                "set_target",
                {
                    "target_id": person_target["id"],
                    "position": person_target["position"],
                    "label": "Emergency: Person",
                },
            )
            self.event_bus.publish("robot_alert", {"text": "Emergency mode: assisting fallen person now."})
            self.event_bus.publish("robot_thought", {"text": "Reactive layer activated: critical safety override."})
            return

        if action_type == "roam_target":
            target_id = action.get("target_id")
            target = world.get_target_by_id(target_id)
            if target is None:
                return
            self.event_bus.publish(
                "set_target",
                {
                    "target_id": target["id"],
                    "position": target["position"],
                    "label": f"Patrol: {target['label']}",
                },
            )
            self.event_bus.publish("robot_thought", {"text": f"Planning layer: context patrol to {target['label']}."})
            self._plan_cooldown = 6.0

    def _on_robot_state(self, payload):
        self.robot_state["state"] = payload.get("state", "idle")
        self.robot_state["target"] = payload.get("target", "none")
        self.robot_state["battery"] = payload.get("battery", 100.0)

    def _on_task_state(self, payload):
        self.task_state["current_task"] = payload.get("current_task", "none")
        self.task_state["charging_pause"] = payload.get("charging_pause", False)

    def _on_person_state(self, payload):
        self.person_state["state"] = payload.get("state", "idle")
        self.person_state["fallen"] = payload.get("fallen", False)
        self.person_state["position"] = payload.get("position", self.person_state["position"])

        if not self.person_state["fallen"]:
            # Allow future emergency triggers after recovery.
            self._emergency_active = False

    def _on_sensor_state(self, payload):
        self.sensor_state["person_detected"] = payload.get("person_detected", False)
        self.sensor_state["obstacle_ahead"] = payload.get("obstacle_ahead", False)
