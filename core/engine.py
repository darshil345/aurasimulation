import math

import pygame

from ai_brain import AIBrain
from command_parser import CommandParser
from config import (
    COLOR_BG,
    COLOR_GRID,
    DEBUG_MODE_DEFAULT,
    TARGET_FPS,
    WINDOW_HEIGHT,
    WINDOW_TITLE,
    WINDOW_WIDTH,
)
from core.showcase_system import ShowcaseSystem
from environment.world import World
from robot.robot import Robot
from ui.flashcard import AuraFlashcard
from task_manager import TaskManager
from ui.dashboard import Dashboard
from voice import VoiceController


class Engine:
    """
    Main runtime engine.

    Responsibilities:
    - setup pygame window
    - run game loop with delta time
    - route input to event bus
    - update world/robot/UI
    """

    def __init__(self, event_bus):
        self.event_bus = event_bus
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(WINDOW_TITLE)
        pygame.display.set_icon(self._create_window_icon())
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 26)
        self.running = True
        self.debug_mode = DEBUG_MODE_DEFAULT
        self.camera_offset = pygame.Vector2(0.0, 0.0)
        self.command_input = ""
        self.input_hint = "Type command and press Enter (example: Can you bring me water from the kitchen?)"
        self.max_input_chars = 120
        self.last_heard_command = "none"
        self.last_robot_response = "Ready."
        self.voice_status_text = "Voice: Initializing..."
        self.voice_enabled = False
        self.voice_listening = False
        self.voice_button_rect = pygame.Rect(0, 0, 160, 36)

        # Core modules
        self.world = World(event_bus=self.event_bus)
        self.robot = Robot(event_bus=self.event_bus, x=WINDOW_WIDTH * 0.5, y=WINDOW_HEIGHT * 0.55)
        self.dashboard = Dashboard(event_bus=self.event_bus)
        self.command_parser = CommandParser()
        self.task_manager = TaskManager(event_bus=self.event_bus, world=self.world)
        self.ai_brain = AIBrain(event_bus=self.event_bus)
        self.showcase = ShowcaseSystem(event_bus=self.event_bus, command_parser=self.command_parser)
        self.voice = VoiceController()
        self.flashcard = AuraFlashcard(event_bus=self.event_bus)
        self.static_bg = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT)).convert()
        self._rebuild_static_layers()
        self.event_bus.subscribe("robot_response", self._on_robot_response)

        self.event_bus.publish(
            "ui_message",
            {
                "text": "SPACE voice listen | Click red targets | F5 Demo | F6 Record | F7 Replay | F3 Debug.",
            },
        )
        self.event_bus.publish("debug_toggle", {"enabled": self.debug_mode})

    def run(self):
        """Run frame-based simulation loop."""
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._handle_input()
            self._update(dt)
            self._draw()
        self.voice.shutdown()
        pygame.quit()

    def _handle_input(self):
        """Convert pygame input into high-level events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_BACKSPACE:
                    self.command_input = self.command_input[:-1]
                elif event.key == pygame.K_RETURN:
                    self._submit_command_text()
                elif event.key == pygame.K_SPACE:
                    self.voice.request_listen()
                elif event.key == pygame.K_c and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    self.event_bus.publish("clear_target", {})
                elif event.key == pygame.K_x and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    self.event_bus.publish(
                        "interrupt_tasks",
                        {"reason": "Manual interrupt (Ctrl+X)."},
                    )
                elif event.key == pygame.K_F3:
                    self.debug_mode = not self.debug_mode
                    self.event_bus.publish("debug_toggle", {"enabled": self.debug_mode})
                elif event.key == pygame.K_F5:
                    self.event_bus.publish("showcase_toggle_demo", {})
                elif event.key == pygame.K_F6:
                    self.event_bus.publish("showcase_toggle_record", {})
                elif event.key == pygame.K_F7:
                    self.event_bus.publish("showcase_start_replay", {})
                elif event.unicode and event.unicode.isprintable():
                    if len(self.command_input) < self.max_input_chars:
                        self.command_input += event.unicode
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self._voice_button_rect().collidepoint(event.pos):
                    self.voice.request_listen()
                    continue
                if self.flashcard.handle_flip(event.pos, self.screen.get_size()):
                    continue
                if self.flashcard.card_flipped:
                    # Back side is informational only.
                    continue
                # Convert screen click into scene/world coordinates (camera-aware).
                scene_mouse = (
                    event.pos[0] - int(self.camera_offset.x),
                    event.pos[1] - int(self.camera_offset.y),
                )
                clicked_target = self.world.get_target_near(scene_mouse)
                if clicked_target is not None:
                    self.event_bus.publish(
                        "set_target",
                        {
                            "target_id": clicked_target["id"],
                            "position": clicked_target["position"],
                            "label": clicked_target["label"],
                        },
                    )
                    self.event_bus.publish(
                        "ui_message",
                        {"text": f"Target selected: {clicked_target['label']}"},
                    )

    def _update(self, dt):
        """Update all modules with delta time."""
        self.world.update(dt)
        self._poll_voice_queue()
        self.ai_brain.update(dt, self.world)
        self.task_manager.update(dt)
        self.showcase.update(dt)
        self.flashcard.update(dt)
        self.robot.update(
            dt=dt,
            obstacles=self.world.get_obstacle_rects(),
            bounds=(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT),
            world=self.world,
        )
        self._update_camera(dt)
        self.dashboard.update(dt)

    def _draw(self):
        """Render scene and dashboard."""
        self.screen.blit(self.static_bg, (0, 0))

        # Draw scene to a separate surface, then blit with camera offset.
        scene_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        self.world.draw(scene_surface, self.font)
        self.robot.draw(scene_surface)
        self.showcase.draw_scene(scene_surface)
        self.screen.blit(scene_surface, (int(self.camera_offset.x), int(self.camera_offset.y)))

        if self.flashcard.card_flipped:
            self.flashcard.draw_back(self.screen)
        else:
            self.flashcard.draw_front(self.screen)

        # Keep existing dashboard available in debug mode as a deeper diagnostics view.
        if self.debug_mode:
            self.dashboard.draw(
                self.screen,
                self.font,
                fps=int(self.clock.get_fps()),
                world=self.world,
                robot=self.robot,
            )
        self._draw_command_input()
        self._draw_voice_button()
        self.showcase.draw_overlay(self.screen)
        if self.debug_mode:
            self._draw_debug_overlay()
        pygame.display.flip()

    def _draw_background_grid(self):
        """Light grid makes motion easier to see."""
        spacing = 32
        for x in range(0, WINDOW_WIDTH, spacing):
            pygame.draw.line(self.screen, (226, 231, 241), (x, 0), (x, WINDOW_HEIGHT), 1)
        for y in range(0, WINDOW_HEIGHT, spacing):
            pygame.draw.line(self.screen, (226, 231, 241), (0, y), (WINDOW_WIDTH, y), 1)

    def _draw_background_gradient(self):
        """Soft top-to-bottom gradient for a more realistic ambience."""
        for y in range(WINDOW_HEIGHT):
            t = y / max(1, WINDOW_HEIGHT - 1)
            r = int(241 + (232 - 241) * t)
            g = int(245 + (238 - 245) * t)
            b = int(252 + (244 - 252) * t)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (WINDOW_WIDTH, y))

    def _rebuild_static_layers(self):
        """
        Build static background once to avoid per-frame redraw loops.
        """
        self.static_bg.fill(COLOR_BG)
        for y in range(WINDOW_HEIGHT):
            t = y / max(1, WINDOW_HEIGHT - 1)
            r = int(241 + (232 - 241) * t)
            g = int(245 + (238 - 245) * t)
            b = int(252 + (244 - 252) * t)
            pygame.draw.line(self.static_bg, (r, g, b), (0, y), (WINDOW_WIDTH, y))
        spacing = 32
        for x in range(0, WINDOW_WIDTH, spacing):
            pygame.draw.line(self.static_bg, (226, 231, 241), (x, 0), (x, WINDOW_HEIGHT), 1)
        for y in range(0, WINDOW_HEIGHT, spacing):
            pygame.draw.line(self.static_bg, (226, 231, 241), (0, y), (WINDOW_WIDTH, y), 1)

    def _create_window_icon(self):
        """Generate a tiny icon surface so we always have an app icon."""
        icon = pygame.Surface((32, 32), pygame.SRCALPHA)
        icon.fill((0, 0, 0, 0))
        pygame.draw.circle(icon, (52, 118, 255), (16, 16), 14)
        # Direction line
        angle = math.radians(-30)
        x2 = int(16 + math.cos(angle) * 10)
        y2 = int(16 + math.sin(angle) * 10)
        pygame.draw.line(icon, (255, 255, 255), (16, 16), (x2, y2), 3)
        return icon

    def _draw_command_input(self):
        """
        Draw a simple command text box.

        This keeps natural language command entry beginner-friendly.
        """
        box = pygame.Rect(16, WINDOW_HEIGHT - 56, WINDOW_WIDTH - 32, 40)
        pygame.draw.rect(self.screen, (37, 44, 58), box, border_radius=10)
        pygame.draw.rect(self.screen, (86, 99, 123), box, 2, border_radius=10)

        display_text = self.command_input if self.command_input else self.input_hint
        color = (239, 244, 252) if self.command_input else (147, 159, 181)
        text_surface = self.font.render(display_text, True, color)
        self.screen.blit(text_surface, (box.x + 12, box.y + 9))

    def _voice_button_rect(self):
        """
        Keep button near the command bar so users can always find it.
        """
        return pygame.Rect(WINDOW_WIDTH - 176, WINDOW_HEIGHT - 102, 160, 36)

    def _draw_voice_button(self):
        rect = self._voice_button_rect()

        if self.voice_listening:
            fill = (35, 132, 88)
            border = (76, 186, 134)
            label = "Listening..."
        elif self.voice_enabled:
            fill = (37, 44, 58)
            border = (88, 104, 130)
            label = "Talk (Mic)"
        else:
            fill = (66, 54, 54)
            border = (123, 95, 95)
            label = "Mic Unavailable"

        pygame.draw.rect(self.screen, fill, rect, border_radius=10)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=10)

        label_surf = self.font.render(label, True, (236, 242, 252))
        lx = rect.x + (rect.width - label_surf.get_width()) // 2
        ly = rect.y + (rect.height - label_surf.get_height()) // 2
        self.screen.blit(label_surf, (lx, ly))

        status_font = pygame.font.SysFont(None, 20)
        status_text = self.voice_status_text[:56]
        status_color = (86, 98, 120) if self.voice_enabled else (140, 92, 92)
        self.screen.blit(status_font.render(status_text, True, status_color), (rect.x - 292, rect.y + 9))

    def _update_camera(self, dt):
        """
        Smooth camera follow with motion lead.

        Since scene and window are same size, we use a cinematic offset
        (small amount) to make movement feel less static.
        """
        heading_rad = math.radians(self.robot.movement.heading)
        forward = pygame.Vector2(math.cos(heading_rad), -math.sin(heading_rad))

        speed_ratio = min(1.0, self.robot.movement.current_speed / max(1.0, self.robot.movement.move_speed))
        lead = 12.0 + 18.0 * speed_ratio
        desired = -forward * lead

        # Ease camera toward desired offset.
        follow_strength = min(1.0, dt * 6.0)
        self.camera_offset += (desired - self.camera_offset) * follow_strength

        # Keep offset subtle so edges never look broken.
        self.camera_offset.x = max(-24.0, min(24.0, self.camera_offset.x))
        self.camera_offset.y = max(-18.0, min(18.0, self.camera_offset.y))

    def _submit_command_text(self):
        text = self.command_input.strip()
        if not text:
            return
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
        self.event_bus.publish(
            "ui_message",
            {"text": f"Intent: {parsed.intent} | Pipeline: {' -> '.join(parsed.steps) if parsed.steps else 'none'}"},
        )
        self.command_input = ""

    def _poll_voice_queue(self):
        """
        Pull voice recognition results from background thread.
        """
        for item in self.voice.poll_results():
            item_type = item.get("type")
            if item_type == "voice_status":
                self.voice_enabled = bool(item.get("ok", False))
                self.voice_status_text = item.get("message", "Voice status updated.")
                if "already listening" in self.voice_status_text.lower():
                    self.voice_listening = True
                self.event_bus.publish("ui_message", {"text": self.voice_status_text})
                continue
            if item_type == "voice_listening":
                self.voice_listening = True
                self.voice_status_text = "Listening... speak now."
                self.event_bus.publish("ui_message", {"text": "Listening... speak now."})
                continue
            if item_type == "voice_error":
                self.voice_listening = False
                msg = item.get("message", "Sorry, I didn't understand.")
                self.voice_status_text = msg
                self.event_bus.publish("ui_message", {"text": msg})
                self.event_bus.publish("robot_response", {"text": "Sorry, I didn't understand."})
                continue
            if item_type == "voice_text":
                self.voice_listening = False
                text = item.get("text", "").strip()
                if not text:
                    continue
                self.last_heard_command = text
                self.voice_status_text = f"Heard: {text}"
                print(f"You said: {text}")
                self.event_bus.publish("voice_heard", {"text": text})
                self.event_bus.publish("ui_message", {"text": f"You said: {text}"})
                parsed = self.command_parser.parse(text)
                payload = {
                    "raw_text": parsed.raw_text,
                    "intent": parsed.intent,
                    "entities": parsed.entities,
                    "steps": parsed.steps,
                    "priority": parsed.priority,
                    "emergency": parsed.emergency,
                    "urgency": parsed.urgency,
                    "response_mode": parsed.response_mode,
                }
                self.event_bus.publish("command_parsed", payload)
                self.event_bus.publish(
                    "ui_message",
                    {
                        "text": (
                            f"Voice intent: {payload['intent']} | "
                            f"steps: {' -> '.join(payload['steps']) if payload['steps'] else 'none'}"
                        )
                    },
                )

    def _on_robot_response(self, payload):
        text = payload.get("text", "")
        if not text:
            return
        self.last_robot_response = text
        self.voice.speak(text)

    def _draw_debug_overlay(self):
        """
        Lightweight debug overlay (F3 toggle).
        """
        fps = self.clock.get_fps()
        dt_ms = self.clock.get_time()
        lines = [
            f"DEBUG MODE",
            f"FPS: {fps:.1f}",
            f"Frame: {dt_ms}ms",
            f"Cam: ({self.camera_offset.x:.1f}, {self.camera_offset.y:.1f})",
            f"Robot: ({self.robot.x:.1f}, {self.robot.y:.1f}) state={self.robot.state}",
            f"Battery: {self.robot.battery_level:.1f}% mode={self.robot.energy_mode}",
        ]
        panel = pygame.Rect(14, 14, 286, 130)
        pygame.draw.rect(self.screen, (20, 25, 34), panel, border_radius=8)
        pygame.draw.rect(self.screen, (92, 106, 132), panel, 1, border_radius=8)
        y = panel.y + 8
        for idx, text in enumerate(lines):
            color = (163, 228, 255) if idx == 0 else (212, 220, 236)
            surf = self.font.render(text, True, color)
            self.screen.blit(surf, (panel.x + 8, y))
            y += 19
