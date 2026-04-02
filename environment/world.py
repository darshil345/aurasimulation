import math

import pygame

from config import (
    COLOR_FURNITURE_BED,
    COLOR_FURNITURE_DETAIL,
    COLOR_FURNITURE_SOFA,
    COLOR_FURNITURE_TABLE,
    COLOR_ROOM_BEDROOM,
    COLOR_ROOM_BORDER,
    COLOR_ROOM_HALL,
    COLOR_ROOM_KITCHEN,
    COLOR_ROOM_LIVING,
    COLOR_TEXT,
    COLOR_WATER_BOTTLE,
    GRID_PATH_CLEARANCE,
    GRID_CELL_SIZE,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from environment.objects import Furniture, ItemObject, Obstacle, PersonObject, Room, TargetPoint


class GridMap:
    """
    Internal occupancy grid.

    Important:
    - This grid is for internal map logic.
    - Robot still moves smoothly in world coordinates.
    """

    def __init__(self, width, height, cell_size):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.cols = width // cell_size
        self.rows = height // cell_size
        self.blocked = [[False for _ in range(self.cols)] for _ in range(self.rows)]

    def clear(self):
        for row in range(self.rows):
            for col in range(self.cols):
                self.blocked[row][col] = False

    def mark_rect_blocked(self, rect):
        start_col = max(0, rect.left // self.cell_size)
        end_col = min(self.cols - 1, rect.right // self.cell_size)
        start_row = max(0, rect.top // self.cell_size)
        end_row = min(self.rows - 1, rect.bottom // self.cell_size)

        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                self.blocked[row][col] = True


class World:
    """
    Holds environment data and drawing.

    This module is intentionally focused on world state only.
    """

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.rooms = [
            Room("kitchen", "Kitchen", (20, 20, 280, 220), COLOR_ROOM_KITCHEN, COLOR_ROOM_BORDER),
            Room("living_room", "Living Room", (320, 20, 320, 220), COLOR_ROOM_LIVING, COLOR_ROOM_BORDER),
            Room("bedroom", "Bedroom", (660, 20, 280, 220), COLOR_ROOM_BEDROOM, COLOR_ROOM_BORDER),
            Room("hall", "Hallway", (20, 260, 920, 360), COLOR_ROOM_HALL, COLOR_ROOM_BORDER),
        ]

        self.furniture = [
            # Slightly smaller footprints improve free movement around rooms.
            Furniture("table", "Table", (96, 126, 108, 54), COLOR_FURNITURE_TABLE, COLOR_FURNITURE_DETAIL),
            Furniture("sofa", "Sofa", (430, 120, 150, 70), COLOR_FURNITURE_SOFA, COLOR_FURNITURE_DETAIL),
            Furniture("bed", "Bed", (716, 112, 166, 88), COLOR_FURNITURE_BED, COLOR_FURNITURE_DETAIL),
        ]
        self.items = [
            ItemObject("water_bottle", "Water Bottle", (246, 92), COLOR_WATER_BOTTLE),
        ]
        self.person = PersonObject("person_1", "Person", (520, 430), (255, 128, 120))
        self.person_state = "idle"  # idle, calling_help, fallen
        self._person_state_timer = 0.0
        self._person_state_publish_timer = 0.0

        # Physical boundaries/walls + furniture collision rectangles.
        self.obstacles = self._create_house_obstacles()

        self.targets = [
            TargetPoint("kitchen", 120, 98, "Kitchen"),
            TargetPoint("living_room", 480, 90, "Living Room"),
            TargetPoint("bedroom", 810, 90, "Bedroom"),
            TargetPoint("hall", 480, 430, "Hallway"),
            TargetPoint("water_bottle", 246, 92, "Water Bottle"),
            TargetPoint("person", 520, 430, "Person"),
        ]
        self.time_acc = 0.0
        self.grid_map = GridMap(WINDOW_WIDTH, WINDOW_HEIGHT, GRID_CELL_SIZE)
        self._rebuild_grid()

    def update(self, dt):
        self.time_acc += dt
        self._update_person_state(dt)
        # Example moving target support:
        # water bottle gently oscillates so robot can track moving goals.
        if self.items:
            bottle = self.items[0]
            base_x = 246.0
            base_y = 92.0
            bottle.position = (
                base_x + math.sin(self.time_acc * 0.9) * 8.0,
                base_y + math.cos(self.time_acc * 0.6) * 5.0,
            )
            for target in self.targets:
                if target.id == "water_bottle":
                    target.position = bottle.position
                    break

        # Tiny idle motion for person so sensors can detect a moving target.
        self.person.position = (
            520.0 + math.sin(self.time_acc * 0.5) * 16.0,
            430.0 + math.cos(self.time_acc * 0.35) * 8.0,
        )
        for target in self.targets:
            if target.id == "person":
                target.position = self.person.position
                break

        self._person_state_publish_timer += dt
        if self._person_state_publish_timer >= 0.3:
            self._person_state_publish_timer = 0.0
            self.event_bus.publish(
                "person_state",
                {
                    "state": self.person_state,
                    "position": self.person.position,
                    "fallen": self.person_state == "fallen",
                },
            )

    def draw(self, screen, font):
        self._draw_house_base(screen)

        for room in self.rooms:
            room.draw(screen)
            self._draw_room_texture(screen, room)
            label = font.render(room.name, True, COLOR_TEXT)
            screen.blit(label, (room.rect.x + 12, room.rect.y + 10))

        for furniture in self.furniture:
            furniture.draw(screen)
            text = font.render(furniture.label, True, COLOR_TEXT)
            screen.blit(text, (furniture.rect.x + 8, furniture.rect.y - 22))

        for item in self.items:
            item.draw(screen)
            text = font.render(item.label, True, COLOR_TEXT)
            screen.blit(text, (int(item.position[0] - 36), int(item.position[1] - 34)))

        self.person.draw(screen)
        person_label = self.person.label
        if self.person_state == "fallen":
            person_label = "Person (Fallen)"
        elif self.person_state == "calling_help":
            person_label = "Person (Calling Help)"
        person_text = font.render(person_label, True, COLOR_TEXT)
        screen.blit(
            person_text,
            (int(self.person.position[0] - 24), int(self.person.position[1] + 18)),
        )

        for obstacle in self.obstacles:
            # Draw only actual walls here; furniture already has custom visuals.
            if obstacle.rect.width <= 14 or obstacle.rect.height <= 14:
                obstacle.draw(screen)

        for target in self.targets:
            target.draw(screen)
            label = font.render(target.label, True, COLOR_TEXT)
            screen.blit(label, (target.position[0] + 12, target.position[1] - 8))

        self._draw_decor(screen)
        self._draw_soft_vignette(screen)

    def get_obstacle_rects(self):
        return [ob.rect for ob in self.obstacles]

    def get_target_near(self, mouse_pos, max_distance=20):
        mx, my = mouse_pos
        for target in self.targets:
            tx, ty = target.position
            if math.hypot(tx - mx, ty - my) <= max_distance:
                return {
                    "id": target.id,
                    "position": target.position,
                    "label": target.label,
                }
        return None

    def get_target_by_id(self, target_id):
        for target in self.targets:
            if target.id == target_id:
                return {
                    "id": target.id,
                    "position": target.position,
                    "label": target.label,
                }
        return None

    def get_sensor_objects(self):
        """
        Return generic objects for forward vision sensor.

        Each object has:
        - id
        - label
        - position (x, y)
        """
        objects = []
        for furn in self.furniture:
            objects.append(
                {
                    "id": furn.id,
                    "label": furn.label,
                    "position": (float(furn.rect.centerx), float(furn.rect.centery)),
                }
            )
        for item in self.items:
            objects.append(
                {
                    "id": item.id,
                    "label": item.label,
                    "position": item.position,
                }
            )
        return objects

    def get_person_data(self):
        return {
            "id": self.person.id,
            "label": self.person.label,
            "position": self.person.position,
            "state": self.person_state,
            "fallen": self.person_state == "fallen",
        }

    def get_environment_snapshot(self):
        return {
            "person_state": self.person_state,
            "person_position": self.person.position,
            "person_fallen": self.person_state == "fallen",
        }

    def world_to_cell(self, world_pos):
        x, y = world_pos
        col = int(x // self.grid_map.cell_size)
        row = int(y // self.grid_map.cell_size)
        col = max(0, min(self.grid_map.cols - 1, col))
        row = max(0, min(self.grid_map.rows - 1, row))
        return (col, row)

    def cell_to_world(self, cell):
        col, row = cell
        cx = col * self.grid_map.cell_size + self.grid_map.cell_size / 2
        cy = row * self.grid_map.cell_size + self.grid_map.cell_size / 2
        return (cx, cy)

    def _create_house_obstacles(self):
        """Create room boundaries and collision objects."""
        walls = []
        # Outer house walls.
        walls.extend(
            [
                Obstacle(0, 0, WINDOW_WIDTH, 12),
                Obstacle(0, WINDOW_HEIGHT - 12, WINDOW_WIDTH, 12),
                Obstacle(0, 0, 12, WINDOW_HEIGHT),
                Obstacle(WINDOW_WIDTH - 12, 0, 12, WINDOW_HEIGHT),
            ]
        )

        # Vertical separators between top rooms.
        walls.extend(
            [
                Obstacle(300, 20, 12, 230),
                Obstacle(640, 20, 12, 230),
            ]
        )

        # Horizontal wall between top rooms and hallway, with door gaps.
        walls.extend(
            [
                # Wider door gaps so robot can pass rooms more smoothly.
                Obstacle(20, 250, 70, 12),
                Obstacle(190, 250, 230, 12),
                Obstacle(560, 250, 200, 12),
                Obstacle(900, 250, 40, 12),
            ]
        )

        # Furniture as obstacles.
        for furn in self.furniture:
            # Collision is slightly smaller than visual furniture to reduce snagging.
            hitbox = furn.rect.inflate(-12, -12)
            walls.append(Obstacle(hitbox.x, hitbox.y, hitbox.width, hitbox.height))
        return walls

    def _rebuild_grid(self):
        """Mark blocked cells from obstacles/furniture boundaries."""
        self.grid_map.clear()
        for obstacle in self.obstacles:
            # Inflate blocked areas so A* keeps clearance from hard edges.
            safe_rect = obstacle.rect.inflate(GRID_PATH_CLEARANCE, GRID_PATH_CLEARANCE)
            self.grid_map.mark_rect_blocked(safe_rect)

    def _draw_room_texture(self, screen, room):
        """Room-specific texture so the house looks more realistic."""
        if room.id == "kitchen":
            line_color = (228, 218, 196)
            for x in range(room.rect.x + 8, room.rect.right - 8, 24):
                pygame.draw.line(screen, line_color, (x, room.rect.y + 8), (x, room.rect.bottom - 8), 1)
            for y in range(room.rect.y + 8, room.rect.bottom - 8, 24):
                pygame.draw.line(screen, line_color, (room.rect.x + 8, y), (room.rect.right - 8, y), 1)
            return

        if room.id == "living_room":
            stripe = (205, 226, 248)
            for y in range(room.rect.y + 10, room.rect.bottom - 10, 16):
                pygame.draw.line(screen, stripe, (room.rect.x + 10, y), (room.rect.right - 10, y), 1)
            return

        if room.id == "bedroom":
            dot_color = (214, 198, 236)
            for x in range(room.rect.x + 12, room.rect.right - 12, 18):
                for y in range(room.rect.y + 12, room.rect.bottom - 12, 18):
                    pygame.draw.circle(screen, dot_color, (x, y), 1)
            return

        # Hallway: wood-like planks.
        plank = (229, 230, 232)
        for y in range(room.rect.y + 10, room.rect.bottom - 10, 22):
            pygame.draw.line(screen, plank, (room.rect.x + 8, y), (room.rect.right - 8, y), 2)
        for x in range(room.rect.x + 24, room.rect.right - 24, 100):
            pygame.draw.line(screen, (218, 220, 223), (x, room.rect.y + 8), (x, room.rect.bottom - 8), 1)

    def _draw_house_base(self, screen):
        """Draw a soft home background under rooms."""
        floor_shadow = pygame.Rect(12, 14, WINDOW_WIDTH - 24, WINDOW_HEIGHT - 90)
        pygame.draw.rect(screen, (204, 211, 223), floor_shadow, border_radius=16)
        floor = pygame.Rect(8, 8, WINDOW_WIDTH - 16, WINDOW_HEIGHT - 80)
        pygame.draw.rect(screen, (239, 242, 247), floor, border_radius=14)
        pygame.draw.rect(screen, (208, 214, 225), floor, 2, border_radius=14)

    def _draw_decor(self, screen):
        """Small decorative graphics for realism."""
        # Living room rug
        rug = pygame.Rect(360, 300, 240, 120)
        pygame.draw.ellipse(screen, (208, 229, 246), rug)
        pygame.draw.ellipse(screen, (184, 210, 233), rug, 2)

        # Bedroom rug
        bed_rug = pygame.Rect(700, 300, 200, 100)
        pygame.draw.ellipse(screen, (222, 212, 241), bed_rug)
        pygame.draw.ellipse(screen, (194, 181, 220), bed_rug, 2)

        # Kitchen mat
        mat = pygame.Rect(78, 300, 170, 54)
        pygame.draw.rect(screen, (245, 226, 194), mat, border_radius=8)
        pygame.draw.rect(screen, (220, 198, 162), mat, 2, border_radius=8)


    def _draw_soft_vignette(self, screen):
        """Simple product-demo vignette to focus attention near center."""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        for i in range(4):
            alpha = 18 + i * 8
            pad = i * 14
            rect = pygame.Rect(pad, pad, WINDOW_WIDTH - pad * 2, WINDOW_HEIGHT - pad * 2)
            pygame.draw.rect(overlay, (14, 20, 30, alpha), rect, width=12, border_radius=24)
        screen.blit(overlay, (0, 0))

    def _update_person_state(self, dt):
        """
        Simple person-state simulation for context-aware AI decisions.
        """
        self._person_state_timer += dt

        # Keep fallen state for several seconds before recovery.
        if self.person_state == "fallen":
            if self._person_state_timer >= 7.0:
                self.person_state = "idle"
                self._person_state_timer = 0.0
            return

        # Occasionally switch state to simulate household events.
        if self._person_state_timer < 6.0:
            return

        self._person_state_timer = 0.0
        phase = int(self.time_acc) % 24
        if phase in (7, 15):
            self.person_state = "calling_help"
        elif phase == 20:
            self.person_state = "fallen"
        else:
            self.person_state = "idle"
