import pygame


class Dashboard:
    """
    Clean, modern UI dashboard.

    Displays:
    - robot status
    - battery
    - current task
    - alerts
    - minimap
    - logs panel
    """

    def __init__(self, event_bus):
        self.event_bus = event_bus

        # Core status
        self.status_message = "System ready."
        self.robot_state = "idle"
        self.battery = 100.0
        self.speed = 0.0
        self.current_target = "none"
        self.current_task = "none"
        self.current_task_status = "idle"
        self.current_step = "none"
        self.energy_mode = "normal"
        self.ai_mode = "normal"
        self.last_heard_command = "none"
        self.last_robot_response = "Ready."
        self.charging_pause = False
        self._last_charging_pause = False
        self.showcase_demo = False
        self.showcase_recording = False
        self.showcase_replaying = False
        self.showcase_frames = 0
        self.debug_mode = False
        self.alerts = []

        # Robot position (for minimap)
        self.robot_x = 0.0
        self.robot_y = 0.0

        # Logs panel
        self.logs = []
        self.max_logs = 8
        self._log_index = 1
        self.title_font = pygame.font.SysFont("trebuchet ms", 22, bold=True)
        self.text_font = pygame.font.SysFont("trebuchet ms", 15)
        self.small_font = pygame.font.SysFont("trebuchet ms", 13)

        self.event_bus.subscribe("ui_message", self._on_ui_message)
        self.event_bus.subscribe("robot_reached_target", self._on_reached_target)
        self.event_bus.subscribe("robot_alert", self._on_robot_alert)
        self.event_bus.subscribe("robot_state", self._on_robot_state)
        self.event_bus.subscribe("set_target", self._on_set_target)
        self.event_bus.subscribe("task_manager_update", self._on_task_update)
        self.event_bus.subscribe("debug_toggle", self._on_debug_toggle)
        self.event_bus.subscribe("showcase_status", self._on_showcase_status)
        self.event_bus.subscribe("voice_heard", self._on_voice_heard)
        self.event_bus.subscribe("robot_response", self._on_robot_response)

    def update(self, _dt):
        pass

    def draw(self, screen, _font, fps, world=None, robot=None):
        screen_w = screen.get_width()
        screen_h = screen.get_height()

        # Right-side stacked panels.
        x = screen_w - 322
        gap = 10
        status_rect = pygame.Rect(x, 14, 308, 264)
        minimap_rect = pygame.Rect(x, status_rect.bottom + gap, 308, 146)
        logs_rect = pygame.Rect(x, minimap_rect.bottom + gap, 308, screen_h - (minimap_rect.bottom + gap) - 66)

        self._draw_card(screen, status_rect)
        self._draw_card(screen, minimap_rect)
        self._draw_card(screen, logs_rect)

        self._draw_status_panel(screen, status_rect, fps)
        self._draw_minimap(screen, minimap_rect, world, robot)
        self._draw_logs_panel(screen, logs_rect)

    def _draw_status_panel(self, screen, rect, fps):
        title_font = self.title_font
        text_font = self.text_font
        small_font = self.small_font

        title = "Dashboard [DEBUG]" if self.debug_mode else "Dashboard"
        screen.blit(title_font.render(title, True, (235, 241, 252)), (rect.x + 12, rect.y + 10))

        state_chip = pygame.Rect(rect.right - 114, rect.y + 12, 100, 28)
        pygame.draw.rect(screen, self._state_color(), state_chip, border_radius=9)
        screen.blit(small_font.render(self.robot_state.upper(), True, (255, 255, 255)), (state_chip.x + 10, state_chip.y + 8))

        # Battery
        battery_bar = pygame.Rect(rect.x + 12, rect.y + 48, rect.width - 24, 14)
        battery_fill = (79, 201, 122) if self.battery > 35 else (233, 176, 80)
        self._draw_progress(screen, battery_bar, self.battery / 100.0, battery_fill)
        battery_text = f"Battery {self.battery:.0f}%  |  Speed {self.speed:.0f}px/s  |  FPS {fps}"
        screen.blit(small_font.render(battery_text, True, (178, 191, 212)), (rect.x + 12, rect.y + 66))

        rows = [
            ("Status", self.status_message),
            ("Heard", self.last_heard_command),
            ("Response", self.last_robot_response),
            ("Target", self.current_target),
            ("Task", f"{self.current_task} [{self.current_task_status}]"),
            ("Step", self.current_step),
            ("Energy", self.energy_mode),
            ("AI", self.ai_mode),
            ("Showcase", self._showcase_text()),
            ("Alert", self.alerts[-1] if self.alerts else "none"),
        ]
        y = rect.y + 90
        for label, value in rows:
            screen.blit(text_font.render(f"{label}:", True, (152, 167, 192)), (rect.x + 12, y))
            screen.blit(text_font.render(self._shorten(value, 30), True, (230, 237, 248)), (rect.x + 88, y))
            y += 18

    def _draw_minimap(self, screen, rect, world, robot):
        title_font = pygame.font.SysFont("trebuchet ms", 19, bold=True)
        text_font = self.small_font
        screen.blit(title_font.render("Minimap", True, (235, 241, 252)), (rect.x + 12, rect.y + 10))

        map_rect = pygame.Rect(rect.x + 12, rect.y + 38, rect.width - 24, rect.height - 50)
        pygame.draw.rect(screen, (33, 41, 55), map_rect, border_radius=8)
        pygame.draw.rect(screen, (83, 96, 120), map_rect, 1, border_radius=8)

        if world is None:
            screen.blit(text_font.render("Map unavailable.", True, (164, 176, 199)), (map_rect.x + 8, map_rect.y + 8))
            return

        scale_x = map_rect.width / max(1, screen.get_width())
        scale_y = map_rect.height / max(1, screen.get_height())

        # Rooms
        for room in world.rooms:
            r = room.rect
            mr = pygame.Rect(
                int(map_rect.x + r.x * scale_x),
                int(map_rect.y + r.y * scale_y),
                max(2, int(r.width * scale_x)),
                max(2, int(r.height * scale_y)),
            )
            room_color = tuple(max(0, c - 22) for c in room.fill_color)
            pygame.draw.rect(screen, room_color, mr, border_radius=5)

        # Obstacles
        for ob in world.get_obstacle_rects():
            mo = pygame.Rect(
                int(map_rect.x + ob.x * scale_x),
                int(map_rect.y + ob.y * scale_y),
                max(1, int(ob.width * scale_x)),
                max(1, int(ob.height * scale_y)),
            )
            pygame.draw.rect(screen, (86, 93, 104), mo)

        # Targets
        for t in world.targets:
            tx = int(map_rect.x + t.position[0] * scale_x)
            ty = int(map_rect.y + t.position[1] * scale_y)
            pygame.draw.circle(screen, (236, 112, 96), (tx, ty), 3)

        # Person
        person = world.get_person_data()
        px = int(map_rect.x + person["position"][0] * scale_x)
        py = int(map_rect.y + person["position"][1] * scale_y)
        pygame.draw.circle(screen, (255, 153, 132), (px, py), 4)

        # Robot
        if robot is not None:
            rcx = robot.x + robot.size / 2
            rcy = robot.y + robot.size / 2
        else:
            rcx = self.robot_x
            rcy = self.robot_y
        rx = int(map_rect.x + rcx * scale_x)
        ry = int(map_rect.y + rcy * scale_y)
        pygame.draw.circle(screen, (98, 203, 255), (rx, ry), 5)
        pygame.draw.circle(screen, (236, 248, 255), (rx, ry), 2)

    def _draw_logs_panel(self, screen, rect):
        title_font = pygame.font.SysFont("trebuchet ms", 19, bold=True)
        text_font = self.small_font
        screen.blit(title_font.render("Logs", True, (235, 241, 252)), (rect.x + 12, rect.y + 10))

        log_area = pygame.Rect(rect.x + 12, rect.y + 36, rect.width - 24, rect.height - 46)
        pygame.draw.rect(screen, (33, 41, 55), log_area, border_radius=8)
        pygame.draw.rect(screen, (83, 96, 120), log_area, 1, border_radius=8)

        if not self.logs:
            screen.blit(text_font.render("No logs yet.", True, (168, 180, 202)), (log_area.x + 8, log_area.y + 8))
            return

        y = log_area.y + 8
        for entry in self.logs[-self.max_logs :]:
            screen.blit(text_font.render(self._shorten(entry, 42), True, (198, 210, 229)), (log_area.x + 8, y))
            y += 16
            if y > log_area.bottom - 14:
                break

    def _draw_card(self, screen, rect):
        shadow = rect.move(0, 4)
        pygame.draw.rect(screen, (154, 164, 182), shadow, border_radius=12)
        pygame.draw.rect(screen, (31, 38, 52), rect, border_radius=12)
        pygame.draw.rect(screen, (76, 88, 110), rect, 2, border_radius=12)

    def _draw_progress(self, screen, rect, progress, fill_color):
        progress = max(0.0, min(1.0, progress))
        pygame.draw.rect(screen, (53, 62, 80), rect, border_radius=7)
        if progress > 0:
            fill = pygame.Rect(rect.x, rect.y, int(rect.width * progress), rect.height)
            pygame.draw.rect(screen, fill_color, fill, border_radius=7)
        pygame.draw.rect(screen, (100, 114, 139), rect, 1, border_radius=7)

    def _on_ui_message(self, payload):
        text = payload.get("text", self.status_message)
        self.status_message = text
        self._add_log(f"INFO: {text}")

    def _on_reached_target(self, payload):
        label = payload.get("label", "target")
        self.status_message = f"Reached {label}"
        self._add_log(f"REACHED: {label}")

    def _on_robot_alert(self, payload):
        text = payload.get("text", "Robot alert.")
        self.alerts.append(text)
        self.status_message = text
        self._add_log(f"ALERT: {text}")

    def _on_robot_state(self, payload):
        self.robot_state = payload.get("state", "idle")
        self.battery = payload.get("battery", 100.0)
        self.speed = payload.get("speed", 0.0)
        self.current_target = payload.get("target", "none")
        self.energy_mode = payload.get("energy_mode", self.energy_mode)
        self.robot_x = payload.get("x", self.robot_x)
        self.robot_y = payload.get("y", self.robot_y)

    def _on_set_target(self, payload):
        label = payload.get("label", "target")
        self._add_log(f"TARGET: {label}")

    def _on_task_update(self, payload):
        self.current_task = payload.get("current_task", "none")
        self.current_task_status = payload.get("current_task_status", "idle")
        self.current_step = payload.get("current_step", "none")
        self.charging_pause = payload.get("charging_pause", False)
        if str(self.current_task_status).startswith("paused_for_charging"):
            self.ai_mode = "planning: charge"
        elif "Emergency" in str(self.current_target):
            self.ai_mode = "reactive"
        elif self.current_task != "none":
            self.ai_mode = "planning"
        else:
            self.ai_mode = "normal"
        if self.charging_pause and not self._last_charging_pause:
            self._add_log("SYSTEM: Task queue paused for charging")
        if (not self.charging_pause) and self._last_charging_pause:
            self._add_log("SYSTEM: Charging pause cleared; tasks resumed")
        self._last_charging_pause = self.charging_pause

    def _on_debug_toggle(self, payload):
        self.debug_mode = bool(payload.get("enabled", self.debug_mode))
        self._add_log(f"SYSTEM: Debug mode {'ON' if self.debug_mode else 'OFF'}")

    def _on_showcase_status(self, payload):
        self.showcase_demo = bool(payload.get("demo_mode", self.showcase_demo))
        self.showcase_recording = bool(payload.get("recording", self.showcase_recording))
        self.showcase_replaying = bool(payload.get("replaying", self.showcase_replaying))
        self.showcase_frames = int(payload.get("frames", self.showcase_frames))
        note = payload.get("note", "")
        if note:
            self._add_log(f"SHOWCASE: {note}")

    def _on_voice_heard(self, payload):
        text = payload.get("text", "none")
        self.last_heard_command = text
        self._add_log(f"VOICE: {text}")

    def _on_robot_response(self, payload):
        text = payload.get("text", "")
        if not text:
            return
        self.last_robot_response = text
        self._add_log(f"ROBOT: {text}")

    def _add_log(self, text):
        entry = f"{self._log_index:03d} | {text}"
        self._log_index += 1
        self.logs.append(entry)
        if len(self.logs) > 30:
            self.logs = self.logs[-30:]

    def _shorten(self, text, max_len):
        text = str(text)
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _showcase_text(self):
        parts = [
            "D:ON" if self.showcase_demo else "D:OFF",
            "R:ON" if self.showcase_recording else "R:OFF",
            "P:ON" if self.showcase_replaying else "P:OFF",
            f"F:{self.showcase_frames}",
        ]
        return " ".join(parts)

    def _state_color(self):
        if self.robot_state == "charging":
            return (67, 158, 255)
        if self.robot_state == "moving":
            return (61, 171, 104)
        if self.robot_state == "executing_task":
            return (221, 145, 76)
        return (132, 140, 155)
