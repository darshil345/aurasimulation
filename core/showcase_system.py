"""
Showcase features for startup-style demos:
- replay system (record robot actions and play ghost replay)
- demo mode (auto simulation script)
- multi-task automation
"""

import math

import pygame


class ShowcaseSystem:
    def __init__(self, event_bus, command_parser):
        self.event_bus = event_bus
        self.command_parser = command_parser

        # Replay data
        self.recording = False
        self.replaying = False
        self.recorded_frames = []
        self.max_frames = 4000
        self.sample_interval = 0.08
        self.sample_timer = 0.0
        self.replay_index = 0
        self.replay_timer = 0.0
        self.replay_speed = 1.15
        self.latest_robot = None

        # Demo automation data
        self.demo_mode = False
        self.demo_script = [
            {"command": "bring water", "delay": 0.4},
            {"command": "come here", "delay": 0.4},
            {"command": "bring water from kitchen", "delay": 0.4},
            {"command": "help!", "delay": 0.6},
            {"command": "bring water", "delay": 0.4},
        ]
        self.demo_index = 0
        self.demo_timer = 0.0
        self.task_busy = False

        self.event_bus.subscribe("robot_state", self._on_robot_state)
        self.event_bus.subscribe("task_manager_update", self._on_task_update)
        self.event_bus.subscribe("showcase_toggle_demo", self._on_toggle_demo)
        self.event_bus.subscribe("showcase_toggle_record", self._on_toggle_record)
        self.event_bus.subscribe("showcase_start_replay", self._on_start_replay)

        self._publish_status("ready")

    def update(self, dt):
        self._update_recording(dt)
        self._update_replay(dt)
        self._update_demo(dt)

    def draw_scene(self, surface):
        """
        Draw replay path and ghost robot onto the world surface.
        """
        if not self.recorded_frames:
            return

        if len(self.recorded_frames) > 1:
            # Decimate points for performance if list is large.
            step = max(1, len(self.recorded_frames) // 1200)
            points = [
                (int(f["x"]), int(f["y"]))
                for i, f in enumerate(self.recorded_frames)
                if i % step == 0
            ]
            if len(points) >= 2:
                pygame.draw.lines(surface, (93, 221, 255), False, points, 2)

        if self.replaying and self.recorded_frames:
            frame = self.recorded_frames[self.replay_index]
            cx = int(frame["x"])
            cy = int(frame["y"])
            heading = math.radians(frame["heading"])

            ghost = pygame.Surface((44, 44), pygame.SRCALPHA)
            pygame.draw.circle(ghost, (93, 221, 255, 70), (22, 22), 18)
            pygame.draw.circle(ghost, (230, 250, 255, 190), (22, 22), 6)
            surface.blit(ghost, (cx - 22, cy - 22))

            fx = cx + int(math.cos(heading) * 22)
            fy = cy - int(math.sin(heading) * 22)
            pygame.draw.line(surface, (196, 245, 255), (cx, cy), (fx, fy), 2)

    def draw_overlay(self, screen):
        """
        Draw compact top-center showcase badge.
        """
        mode = self._mode_string()
        badge = pygame.Rect(screen.get_width() // 2 - 130, 10, 260, 30)
        pygame.draw.rect(screen, (24, 30, 44), badge, border_radius=8)
        pygame.draw.rect(screen, (78, 95, 124), badge, 1, border_radius=8)

        font = pygame.font.SysFont("trebuchet ms", 16, bold=True)
        text = font.render(f"SHOWCASE  |  {mode}", True, (201, 231, 255))
        screen.blit(text, (badge.x + 10, badge.y + 7))

    def _update_recording(self, dt):
        if not self.recording or self.latest_robot is None:
            return

        self.sample_timer += dt
        if self.sample_timer < self.sample_interval:
            return
        self.sample_timer = 0.0

        frame = {
            "x": self.latest_robot["x"] + 21,
            "y": self.latest_robot["y"] + 21,
            "heading": self.latest_robot["heading"],
            "state": self.latest_robot["state"],
            "battery": self.latest_robot["battery"],
        }
        self.recorded_frames.append(frame)
        if len(self.recorded_frames) > self.max_frames:
            self.recorded_frames = self.recorded_frames[-self.max_frames :]

    def _update_replay(self, dt):
        if not self.replaying or len(self.recorded_frames) < 2:
            return

        self.replay_timer += dt * self.replay_speed
        while self.replay_timer >= self.sample_interval:
            self.replay_timer -= self.sample_interval
            self.replay_index += 1
            if self.replay_index >= len(self.recorded_frames):
                self.replay_index = len(self.recorded_frames) - 1
                self.replaying = False
                self.event_bus.publish("ui_message", {"text": "Replay finished."})
                self._publish_status("replay_finished")
                break

    def _update_demo(self, dt):
        if not self.demo_mode:
            return

        self.demo_timer += dt
        if self.task_busy:
            return

        current = self.demo_script[self.demo_index]
        if self.demo_timer < current["delay"]:
            return

        self.demo_timer = 0.0
        self._dispatch_command(current["command"], source="demo")
        self.demo_index = (self.demo_index + 1) % len(self.demo_script)

    def _dispatch_command(self, text, source):
        parsed = self.command_parser.parse(text)
        self.event_bus.publish(
            "command_parsed",
            {
                "raw_text": parsed.raw_text,
                "intent": parsed.intent,
                "entities": parsed.entities,
                "steps": parsed.steps,
                "priority": parsed.priority,
                "emergency": parsed.emergency,
                "urgency": parsed.urgency,
                "response_mode": parsed.response_mode,
            },
        )
        self.event_bus.publish("ui_message", {"text": f"{source.title()} command: {text}"})

    def _mode_string(self):
        flags = []
        flags.append("DEMO ON" if self.demo_mode else "DEMO OFF")
        flags.append("REC ON" if self.recording else "REC OFF")
        flags.append("REPLAY ON" if self.replaying else "REPLAY OFF")
        return " | ".join(flags)

    def _publish_status(self, note):
        self.event_bus.publish(
            "showcase_status",
            {
                "demo_mode": self.demo_mode,
                "recording": self.recording,
                "replaying": self.replaying,
                "frames": len(self.recorded_frames),
                "note": note,
            },
        )

    def _on_robot_state(self, payload):
        self.latest_robot = payload

    def _on_task_update(self, payload):
        current_task = payload.get("current_task", "none")
        charging_pause = payload.get("charging_pause", False)
        self.task_busy = current_task != "none" or charging_pause

    def _on_toggle_demo(self, _payload):
        self.demo_mode = not self.demo_mode
        self.demo_timer = 0.0
        if self.demo_mode:
            self.event_bus.publish("ui_message", {"text": "Demo mode enabled."})
        else:
            self.event_bus.publish("ui_message", {"text": "Demo mode disabled."})
        self._publish_status("demo_toggled")

    def _on_toggle_record(self, _payload):
        self.recording = not self.recording
        self.sample_timer = 0.0
        if self.recording:
            self.recorded_frames = []
            self.replaying = False
            self.replay_index = 0
            self.event_bus.publish("ui_message", {"text": "Replay recording started."})
        else:
            self.event_bus.publish(
                "ui_message",
                {"text": f"Replay recording stopped. Frames: {len(self.recorded_frames)}"},
            )
        self._publish_status("record_toggled")

    def _on_start_replay(self, _payload):
        if len(self.recorded_frames) < 2:
            self.event_bus.publish("ui_message", {"text": "Not enough replay data yet."})
            self._publish_status("replay_failed")
            return
        self.replaying = True
        self.recording = False
        self.replay_index = 0
        self.replay_timer = 0.0
        self.event_bus.publish("ui_message", {"text": "Replay started."})
        self._publish_status("replay_started")
