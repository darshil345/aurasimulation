import pygame

from config import COLOR_OBSTACLE, COLOR_TARGET


class Obstacle:
    """Static obstacle object."""

    def __init__(self, x, y, w, h):
        self.rect = pygame.Rect(x, y, w, h)

    def draw(self, screen):
        pygame.draw.rect(screen, (84, 90, 102), self.rect)


class TargetPoint:
    """Clickable destination marker."""

    def __init__(self, target_id, x, y, label):
        self.id = target_id
        self.position = (x, y)
        self.label = label

    def draw(self, screen):
        center = (int(self.position[0]), int(self.position[1]))
        pygame.draw.circle(screen, (255, 255, 255), center, 11)
        pygame.draw.circle(screen, COLOR_TARGET, center, 8)
        pygame.draw.circle(screen, (255, 255, 255), center, 3)


class Room:
    """Visual room area with color and border."""

    def __init__(self, room_id, name, rect, fill_color, border_color):
        self.id = room_id
        self.name = name
        self.rect = pygame.Rect(rect)
        self.fill_color = fill_color
        self.border_color = border_color

    def draw(self, screen):
        pygame.draw.rect(screen, self.fill_color, self.rect, border_radius=8)
        pygame.draw.rect(screen, self.border_color, self.rect, 3, border_radius=8)


class Furniture:
    """Furniture object that can also act as collision obstacle."""

    def __init__(self, furniture_id, label, rect, color, detail_color):
        self.id = furniture_id
        self.label = label
        self.rect = pygame.Rect(rect)
        self.color = color
        self.detail_color = detail_color

    def draw(self, screen):
        shadow = self.rect.move(0, 4)
        pygame.draw.rect(screen, (148, 153, 164), shadow, border_radius=10)
        pygame.draw.rect(screen, self.color, self.rect, border_radius=10)
        pygame.draw.rect(screen, self.detail_color, self.rect, 2, border_radius=10)

        if self.id == "table":
            top = pygame.Rect(self.rect.x + 10, self.rect.y + 8, self.rect.width - 20, 14)
            pygame.draw.rect(screen, (212, 177, 137), top, border_radius=5)
            for leg_x in (self.rect.x + 16, self.rect.right - 20):
                pygame.draw.rect(screen, self.detail_color, pygame.Rect(leg_x, self.rect.bottom - 20, 4, 16))
        elif self.id == "sofa":
            seat = pygame.Rect(self.rect.x + 10, self.rect.y + 26, self.rect.width - 20, self.rect.height - 36)
            pygame.draw.rect(screen, (144, 180, 218), seat, border_radius=8)
            arm_l = pygame.Rect(self.rect.x + 4, self.rect.y + 12, 14, self.rect.height - 20)
            arm_r = pygame.Rect(self.rect.right - 18, self.rect.y + 12, 14, self.rect.height - 20)
            pygame.draw.rect(screen, self.detail_color, arm_l, border_radius=5)
            pygame.draw.rect(screen, self.detail_color, arm_r, border_radius=5)
        elif self.id == "bed":
            pillow = pygame.Rect(self.rect.x + 12, self.rect.y + 10, self.rect.width - 24, 18)
            blanket = pygame.Rect(self.rect.x + 8, self.rect.y + 34, self.rect.width - 16, self.rect.height - 42)
            pygame.draw.rect(screen, (242, 244, 248), pillow, border_radius=6)
            pygame.draw.rect(screen, (208, 192, 230), blanket, border_radius=8)


class ItemObject:
    """Small object (example: water bottle)."""

    def __init__(self, item_id, label, position, color):
        self.id = item_id
        self.label = label
        self.position = (float(position[0]), float(position[1]))
        self.color = color

    def draw(self, screen):
        x = int(self.position[0])
        y = int(self.position[1])
        pygame.draw.ellipse(screen, (172, 178, 190), pygame.Rect(x - 6, y + 7, 12, 5))
        pygame.draw.rect(screen, self.color, pygame.Rect(x - 5, y - 12, 10, 18), border_radius=4)
        pygame.draw.rect(screen, (220, 240, 255), pygame.Rect(x - 2, y - 17, 4, 6), border_radius=2)
        pygame.draw.line(screen, (212, 242, 255), (x - 2, y - 8), (x - 2, y + 4), 2)


class PersonObject:
    """Simple person marker used by person detector sensors."""

    def __init__(self, person_id, label, position, color):
        self.id = person_id
        self.label = label
        self.position = (float(position[0]), float(position[1]))
        self.color = color

    def draw(self, screen):
        x = int(self.position[0])
        y = int(self.position[1])
        pygame.draw.ellipse(screen, (168, 173, 184), pygame.Rect(x - 12, y + 13, 24, 7))
        pygame.draw.circle(screen, (245, 220, 180), (x, y - 12), 7)
        pygame.draw.circle(screen, self.color, (x, y + 2), 11)
        pygame.draw.line(screen, (66, 72, 82), (x - 10, y + 2), (x + 10, y + 2), 3)
        pygame.draw.line(screen, (66, 72, 82), (x - 5, y + 12), (x + 5, y + 12), 3)
