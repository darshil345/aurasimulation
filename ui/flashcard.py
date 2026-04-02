"""
AURA Simulation Flashcard UI.

Front side:
- live simulation (already rendered by engine)
- minimal status overlay

Back side:
- project details panel
"""

import pygame


class AuraFlashcard:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.card_flipped = False

        # Flip button appears in top-right.
        self.flip_button_rect = pygame.Rect(0, 0, 124, 38)

        # Minimal status data for front side.
        self.robot_state = "idle"
        self.current_task = "none"
        self.battery = 100.0

        # Tiny animation blend value (0 = front, 1 = back).
        self._flip_blend = 0.0

        self.event_bus.subscribe("robot_state", self._on_robot_state)
        self.event_bus.subscribe("task_manager_update", self._on_task_update)

    def update(self, dt):
        """Small easing animation for smoother transitions."""
        target = 1.0 if self.card_flipped else 0.0
        speed = min(1.0, dt * 8.0)
        self._flip_blend += (target - self._flip_blend) * speed

    def handle_flip(self, mouse_pos, screen_size):
        """
        Flip on button click.

        Returns True if click was consumed by the button.
        """
        self._update_button_position(screen_size)
        if self.flip_button_rect.collidepoint(mouse_pos):
            self.card_flipped = not self.card_flipped
            return True
        return False

    def draw_front(self, screen):
        """
        Front side:
        simulation remains visible, with minimal overlay only.
        """
        self._draw_minimal_overlay(screen)
        self._draw_flip_button(screen)

    def draw_back(self, screen):
        """
        Back side:
        dim simulation and show project information panel.
        """
        self._draw_dim_overlay(screen)
        self._draw_back_panel(screen)
        self._draw_flip_button(screen)

    def _draw_minimal_overlay(self, screen):
        panel = pygame.Rect(16, 16, 286, 96)
        self._draw_shadow(screen, panel, 6)
        pygame.draw.rect(screen, (24, 31, 44), panel, border_radius=11)
        pygame.draw.rect(screen, (88, 103, 130), panel, 1, border_radius=11)

        title_font = pygame.font.SysFont("trebuchet ms", 18, bold=True)
        text_font = pygame.font.SysFont("trebuchet ms", 14)
        screen.blit(title_font.render("AURA Simulation", True, (229, 236, 247)), (panel.x + 10, panel.y + 8))

        rows = [
            f"State: {self.robot_state}",
            f"Task: {self.current_task}",
            f"Battery: {self.battery:.0f}%",
        ]
        y = panel.y + 36
        for row in rows:
            screen.blit(text_font.render(row, True, (178, 191, 212)), (panel.x + 12, y))
            y += 18

    def _draw_back_panel(self, screen):
        sw, sh = screen.get_size()

        # Card layout in center.
        card_w = 660
        card_h = 470
        card = pygame.Rect((sw - card_w) // 2, (sh - card_h) // 2, card_w, card_h)

        self._draw_shadow(screen, card, 10)
        pygame.draw.rect(screen, (245, 248, 252), card, border_radius=16)
        pygame.draw.rect(screen, (185, 194, 209), card, 2, border_radius=16)

        title_font = pygame.font.SysFont("trebuchet ms", 34, bold=True)
        section_font = pygame.font.SysFont("trebuchet ms", 18, bold=True)
        text_font = pygame.font.SysFont("trebuchet ms", 15)

        screen.blit(title_font.render("AURA Simulation", True, (31, 39, 52)), (card.x + 22, card.y + 18))

        sections = [
            ("Project Overview", "AI-powered elderly assistance robot simulation."),
            (
                "Key Features",
                "Voice control system | Natural language understanding | Task planning system | "
                "Emergency detection (fall detection) | Smart navigation (A*) | Battery management",
            ),
            ("Use Cases", "Bring water | Emergency response | Daily assistance"),
            ("Technology Stack", "Python | Pygame | SpeechRecognition | AI-based command parsing"),
            ("How It Works", "Voice -> NLP -> Task -> Robot Action"),
            ("Future Scope", "Real robot hardware | Mobile app integration | Smart home connectivity"),
        ]

        y = card.y + 82
        for heading, content in sections:
            screen.blit(section_font.render(heading, True, (49, 59, 76)), (card.x + 24, y))
            y += 24
            wrapped = _wrap_text(content, text_font, card.width - 48)
            for line in wrapped:
                screen.blit(text_font.render(line, True, (76, 86, 104)), (card.x + 28, y))
                y += 19
            y += 8

    def _draw_dim_overlay(self, screen):
        alpha = int(120 + 70 * self._flip_blend)
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((10, 14, 20, alpha))
        screen.blit(overlay, (0, 0))

    def _draw_flip_button(self, screen):
        self._update_button_position(screen.get_size())
        self._draw_shadow(screen, self.flip_button_rect, 4)
        pygame.draw.rect(screen, (34, 45, 62), self.flip_button_rect, border_radius=9)
        pygame.draw.rect(screen, (98, 117, 148), self.flip_button_rect, 1, border_radius=9)
        font = pygame.font.SysFont("trebuchet ms", 16, bold=True)
        label = "Flip Card"
        text = font.render(label, True, (225, 236, 252))
        tx = self.flip_button_rect.x + (self.flip_button_rect.width - text.get_width()) // 2
        ty = self.flip_button_rect.y + (self.flip_button_rect.height - text.get_height()) // 2
        screen.blit(text, (tx, ty))

    def _draw_shadow(self, screen, rect, offset):
        shadow = rect.move(0, offset // 2)
        pygame.draw.rect(screen, (140, 148, 162), shadow, border_radius=10)

    def _update_button_position(self, screen_size):
        sw, _ = screen_size
        self.flip_button_rect.topleft = (sw - self.flip_button_rect.width - 14, 12)

    def _on_robot_state(self, payload):
        self.robot_state = payload.get("state", self.robot_state)
        self.battery = payload.get("battery", self.battery)

    def _on_task_update(self, payload):
        self.current_task = payload.get("current_task", self.current_task)


def _wrap_text(text, font, max_width):
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = current + " " + word
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
