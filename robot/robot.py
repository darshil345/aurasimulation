import math
from collections import deque

import pygame

from config import (
    COLOR_PATH,
    COLOR_FURNITURE_BED,
    COLOR_FURNITURE_SOFA,
    COLOR_ROBOT,
    COLOR_ROBOT_DIR,
    DEBUG_MODE_DEFAULT,
    SENSOR_UPDATE_INTERVAL,
    ROBOT_ACCELERATION,
    ROBOT_ARRIVAL_RADIUS,
    ROBOT_BATTERY_CHARGE_RATE,
    ROBOT_BATTERY_DRAIN_IDLE,
    ROBOT_BATTERY_DRAIN_MOVING,
    ROBOT_BATTERY_LOW_THRESHOLD,
    ROBOT_BATTERY_MAX,
    ROBOT_DECELERATION,
    ROBOT_MOVE_ANGLE_THRESHOLD,
    ROBOT_MOVE_SPEED,
    ROBOT_SIZE,
    ROBOT_TURN_SPEED,
    VISION_FOV_DEG,
    VISION_RANGE,
    PROXIMITY_RADIUS,
)
from robot.movement import MovementController
from robot.pathfinding import AStarPlanner
from robot.sensors import SensorSuite


class Robot:
    """
    Robot entity.

    Owns:
    - motion state
    - target state
    - sensor state
    """

    def __init__(self, event_bus, x, y):
        self.event_bus = event_bus
        self.x = float(x)
        self.y = float(y)
        self.size = ROBOT_SIZE
        self.color = COLOR_ROBOT

        self.target_position = None
        self.target_id = None
        self.target_label = "none"
        self.arrival_radius = ROBOT_ARRIVAL_RADIUS
        self.path_cells = []
        self.path_points = []
        self.path_index = 0
        self.path_replan_interval = 0.25
        self.path_replan_timer = 0.0
        self.request_replan = False
        self.last_goal_for_path = None

        self.movement = MovementController(
            move_speed=ROBOT_MOVE_SPEED,
            turn_speed=ROBOT_TURN_SPEED,
            angle_threshold=ROBOT_MOVE_ANGLE_THRESHOLD,
            acceleration=ROBOT_ACCELERATION,
            deceleration=ROBOT_DECELERATION,
        )
        self.pathfinder = AStarPlanner()
        self.sensors = SensorSuite()
        self.last_sensor = None
        self.is_moving = False
        self.state = "idle"  # idle, moving, executing_task, charging
        self.battery_level = ROBOT_BATTERY_MAX
        self._battery_low_alert_sent = False
        self._battery_warn_35_sent = False
        self._battery_warn_10_sent = False
        self.base_move_speed = ROBOT_MOVE_SPEED
        self.energy_mode = "normal"
        self._charging_requested = False
        self.anim_phase = 0.0
        self.wheel_phase = 0.0
        self.debug_mode = DEBUG_MODE_DEFAULT
        self.sensor_update_interval = SENSOR_UPDATE_INTERVAL
        self.sensor_timer = 0.0
        self._blocked_message_cooldown = 0.0

        self.event_bus.subscribe("set_target", self._on_set_target)
        self.event_bus.subscribe("clear_target", self._on_clear_target)
        self.event_bus.subscribe("debug_toggle", self._on_debug_toggle)

    def update(self, dt, obstacles, bounds, world):
        """Frame-based robot update."""
        reached_target_label = None
        self._blocked_message_cooldown = max(0.0, self._blocked_message_cooldown - dt)
        self._update_energy_mode()
        self._maybe_request_charging()

        if self.target_position is not None and self.state != "charging":
            prev_x = self.x
            prev_y = self.y
            self.path_replan_timer += dt
            self._refresh_target_from_world_if_moving(world)

            if self.request_replan or self.path_replan_timer >= self.path_replan_interval:
                self._replan_path(world)

            nav_target = self._get_navigation_target()
            if nav_target is not None:
                move_result = self.movement.update_toward_target(
                    position=self.get_center(),
                    target=nav_target,
                    dt=dt,
                )
                # move_result uses center coords, convert back to top-left
                self.x = move_result["x"] - self.size / 2
                self.y = move_result["y"] - self.size / 2
                self.is_moving = move_result["moving_forward"]
            else:
                self.movement.current_speed = max(
                    0.0, self.movement.current_speed - ROBOT_DECELERATION * dt
                )
                self.is_moving = self.movement.current_speed > 0.01

            blocked = self._resolve_collisions(obstacles, bounds)
            if blocked:
                slid = self._try_slide(prev_x, prev_y, nav_target, obstacles, bounds)
                if not slid:
                    self.x = prev_x
                    self.y = prev_y
                    # Keep some momentum so motion does not look jerky.
                    self.movement.current_speed *= 0.35
                self.request_replan = True

            self._advance_path_if_waypoint_reached()

            reached_path_goal = (
                len(self.path_points) > 0
                and self.path_index >= len(self.path_points) - 1
                and self._distance_to_target(self.path_points[-1]) <= self.arrival_radius
            )
            if (
                self._distance_to_target(self.target_position) <= self.arrival_radius
                or reached_path_goal
            ):
                reached_target_label = self.target_label
                self.target_position = None
                self.target_id = None
                self.target_label = "none"
                self.path_cells = []
                self.path_points = []
                self.path_index = 0
                self.is_moving = False
                self.event_bus.publish("robot_reached_target", {"label": reached_target_label})
        else:
            # If no target, smoothly decelerate remaining speed.
            self.movement.current_speed = max(
                0.0, self.movement.current_speed - ROBOT_DECELERATION * dt
            )
            self.is_moving = self.movement.current_speed > 0.01

        self._update_state(dt, reached_target_label)
        self._update_battery(dt)
        self._handle_battery_alerts()
        self._update_animation(dt)

        self.sensor_timer += dt
        if self.last_sensor is None or self.sensor_timer >= self.sensor_update_interval:
            self.sensor_timer = 0.0
            self.last_sensor = self.sensors.scan(
                x=self.x,
                y=self.y,
                heading=self.movement.heading,
                robot_size=self.size,
                obstacles=obstacles,
                bounds=bounds,
                objects=world.get_sensor_objects(),
                person=world.get_person_data(),
            )
            if self.target_position is not None and self.last_sensor["proximity_alert"]:
                # Near obstacle: request replan, but do not over-slow general motion.
                self.request_replan = True
            if self.target_position is not None and self.last_sensor["obstacle_ahead"]:
                # Immediate obstacle ahead: reduce to controlled speed while replanning.
                self.movement.current_speed = min(self.movement.current_speed, 135.0)

        sensor_data = self.last_sensor if self.last_sensor is not None else {
            "obstacle_ahead": False,
            "proximity_alert": False,
            "nearby_obstacles": [],
            "visible_objects": [],
            "person_detected": False,
            "person_in_front": False,
        }
        self.event_bus.publish(
            "sensor_update",
            {
                "obstacle_ahead": sensor_data["obstacle_ahead"],
                "proximity_alert": sensor_data["proximity_alert"],
                "nearby_obstacles": len(sensor_data["nearby_obstacles"]),
                "visible_objects": [obj["label"] for obj in sensor_data["visible_objects"][:3]],
                "person_detected": sensor_data["person_detected"],
                "person_in_front": sensor_data["person_in_front"],
                "target": self.target_label,
            },
        )
        if self.target_position is not None and sensor_data["obstacle_ahead"]:
            self.request_replan = True
        self.event_bus.publish(
            "robot_state",
            {
                "x": self.x,
                "y": self.y,
                "heading": self.movement.heading,
                "moving": self.is_moving,
                "target": self.target_label,
                "state": self.state,
                "battery": round(self.battery_level, 1),
                "speed": round(self.movement.current_speed, 1),
                "path_points": len(self.path_points),
                "energy_mode": self.energy_mode,
            },
        )

    def draw(self, screen):
        center = pygame.Vector2(self.x + self.size / 2, self.y + self.size / 2)
        heading_rad = math.radians(self.movement.heading)
        forward = pygame.Vector2(math.cos(heading_rad), -math.sin(heading_rad))
        side = pygame.Vector2(forward.y, -forward.x)
        speed_ratio = min(1.0, self.movement.current_speed / max(1.0, self.movement.move_speed))
        bob = math.sin(self.anim_phase) * (1.8 * speed_ratio)
        center += pygame.Vector2(0, bob)

        body_radius = int(self.size * 0.48)
        shell_color = self._state_color()

        # Robot shadow
        shadow_rect = pygame.Rect(0, 0, body_radius * 2 + 12, int(body_radius * 1.35))
        shadow_rect.center = (int(center.x), int(center.y + body_radius * 0.85))
        pygame.draw.ellipse(screen, (146, 152, 166), shadow_rect)

        # Main body shell
        pygame.draw.circle(screen, shell_color, (int(center.x), int(center.y)), body_radius)
        pygame.draw.circle(screen, (228, 233, 241), (int(center.x), int(center.y)), body_radius, 3)

        # Top dome
        dome_center = center + forward * (body_radius * 0.18)
        pygame.draw.circle(screen, (233, 238, 247), (int(dome_center.x), int(dome_center.y)), int(body_radius * 0.62))
        pygame.draw.circle(screen, (188, 196, 210), (int(dome_center.x), int(dome_center.y)), int(body_radius * 0.62), 2)

        # Front sensor eye
        eye_center = center + forward * (body_radius * 0.82)
        pygame.draw.circle(screen, (42, 52, 68), (int(eye_center.x), int(eye_center.y)), 8)
        pygame.draw.circle(screen, (95, 208, 255), (int(eye_center.x), int(eye_center.y)), 4)
        pygame.draw.circle(screen, (180, 236, 255), (int(eye_center.x - 1), int(eye_center.y - 1)), 2)

        # Side wheels
        wheel_offset = side * (body_radius * 0.95)
        for sign in (-1, 1):
            wheel_center = center + wheel_offset * sign
            wheel_r = int(body_radius * 0.28)
            hub_r = int(body_radius * 0.14)
            pygame.draw.circle(screen, (56, 60, 68), (int(wheel_center.x), int(wheel_center.y)), wheel_r)
            pygame.draw.circle(screen, (132, 142, 158), (int(wheel_center.x), int(wheel_center.y)), hub_r)

            # Wheel spoke animation
            spoke_angle = self.wheel_phase + (0.9 if sign > 0 else 0.0)
            spoke_dir = pygame.Vector2(math.cos(spoke_angle), math.sin(spoke_angle))
            p1 = wheel_center + spoke_dir * (hub_r + 1)
            p2 = wheel_center + spoke_dir * (wheel_r - 2)
            pygame.draw.line(screen, (188, 197, 215), p1, p2, 2)
            p3 = wheel_center - spoke_dir * (hub_r + 1)
            p4 = wheel_center - spoke_dir * (wheel_r - 2)
            pygame.draw.line(screen, (188, 197, 215), p3, p4, 2)

        # Direction pointer
        front = center + forward * (body_radius + 18)
        pygame.draw.line(screen, COLOR_ROBOT_DIR, center, front, 3)

        # Subtle active glow while moving.
        if self.is_moving:
            glow = pygame.Surface((body_radius * 4, body_radius * 4), pygame.SRCALPHA)
            pygame.draw.circle(
                glow,
                (96, 194, 255, 28),
                (glow.get_width() // 2, glow.get_height() // 2),
                body_radius + 16,
            )
            screen.blit(glow, (center.x - glow.get_width() / 2, center.y - glow.get_height() / 2))

        # Draw sensor box for debug visibility.
        if self.last_sensor is not None:
            if self.debug_mode:
                sensor_color = (220, 70, 70) if self.last_sensor["obstacle_ahead"] else (70, 170, 90)
                pygame.draw.rect(screen, sensor_color, self.last_sensor["sensor_rect"], 2)
                self._draw_sensor_debug(screen)

        # Draw path visualization.
        if len(self.path_points) >= 2:
            pygame.draw.lines(screen, COLOR_PATH, False, self.path_points, 3)
            # Highlight next waypoint.
            if 0 <= self.path_index < len(self.path_points):
                wp = self.path_points[self.path_index]
                pygame.draw.circle(screen, COLOR_PATH, (int(wp[0]), int(wp[1])), 5)

    def get_center(self):
        return (self.x + self.size / 2, self.y + self.size / 2)

    def clear_target(self):
        self.target_position = None
        self.target_id = None
        self.target_label = "none"
        self.is_moving = False
        self.path_cells = []
        self.path_points = []
        self.path_index = 0
        self.request_replan = False
        if self.state != "charging":
            self.state = "idle"

    def _on_set_target(self, payload):
        self.target_id = payload.get("target_id")
        self.target_position = tuple(payload["position"])
        self.target_label = payload.get("label", "target")
        # New task means charging requests should be recomputed on next low-battery cycle.
        self._charging_requested = False
        if self.state == "charging":
            # Emergency/explicit tasks can interrupt charging.
            self.state = "executing_task"
        self.request_replan = True
        self.path_replan_timer = 0.0

    def _on_clear_target(self, _payload):
        self.clear_target()

    def _on_debug_toggle(self, payload):
        self.debug_mode = bool(payload.get("enabled", self.debug_mode))

    def _distance_to_target(self, target):
        if target is None:
            return 0.0
        cx, cy = self.get_center()
        tx, ty = target
        return math.hypot(tx - cx, ty - cy)

    def _resolve_collisions(self, obstacles, bounds):
        """Clamp to bounds and revert simple obstacle penetration."""
        blocked = False
        min_x, min_y, max_x, max_y = bounds
        if self.x < min_x:
            self.x = min_x
            blocked = True
        if self.y < min_y:
            self.y = min_y
            blocked = True
        if self.x + self.size > max_x:
            self.x = max_x - self.size
            blocked = True
        if self.y + self.size > max_y:
            self.y = max_y - self.size
            blocked = True

        rect = pygame.Rect(int(self.x), int(self.y), self.size, self.size)
        for obstacle in obstacles:
            if rect.colliderect(obstacle):
                blocked = True
                break
        if blocked and self.target_position is not None:
            if self._blocked_message_cooldown <= 0.0:
                self.event_bus.publish("ui_message", {"text": "Path blocked, replanning..."})
                self._blocked_message_cooldown = 0.6
        return blocked

    def _is_position_blocked(self, x, y, obstacles, bounds):
        min_x, min_y, max_x, max_y = bounds
        if x < min_x or y < min_y or x + self.size > max_x or y + self.size > max_y:
            return True
        rect = pygame.Rect(int(x), int(y), self.size, self.size)
        for obstacle in obstacles:
            if rect.colliderect(obstacle):
                return True
        return False

    def _try_slide(self, prev_x, prev_y, nav_target, obstacles, bounds):
        """
        If full movement collides, try axis slide to avoid full stop.
        """
        if nav_target is None:
            return False

        cand_x = (self.x, prev_y)
        cand_y = (prev_x, self.y)
        options = []
        for cx, cy in (cand_x, cand_y):
            if not self._is_position_blocked(cx, cy, obstacles, bounds):
                center_x = cx + self.size / 2
                center_y = cy + self.size / 2
                distance = math.hypot(nav_target[0] - center_x, nav_target[1] - center_y)
                options.append((distance, cx, cy))

        if not options:
            return False

        # Pick slide direction that keeps us closer to current waypoint.
        options.sort(key=lambda item: item[0])
        _, best_x, best_y = options[0]
        self.x = best_x
        self.y = best_y
        self.movement.current_speed *= 0.75
        return True

    def _update_state(self, dt, reached_target_label):
        """State machine for robot behavior."""
        if self.state == "charging":
            if self.battery_level >= ROBOT_BATTERY_MAX - 0.01:
                self.state = "idle"
                self._charging_requested = False
                self.event_bus.publish("charging_complete", {"battery": round(self.battery_level, 1)})
                self.event_bus.publish("ui_message", {"text": "Battery full. Resuming paused tasks."})
            return

        if self.target_position is not None:
            if self.is_moving:
                self.state = "moving"
            else:
                # Usually turning/aligning to a target.
                self.state = "executing_task"
            return

        if self.is_moving:
            self.state = "moving"
        else:
            self.state = "idle"

    def _update_battery(self, dt):
        """Battery drains over time and charges while charging."""
        if self.state == "charging":
            self.battery_level += ROBOT_BATTERY_CHARGE_RATE * dt
            if self.battery_level > ROBOT_BATTERY_MAX:
                self.battery_level = ROBOT_BATTERY_MAX
            return

        if self.is_moving:
            self.battery_level -= ROBOT_BATTERY_DRAIN_MOVING * dt
        else:
            self.battery_level -= ROBOT_BATTERY_DRAIN_IDLE * dt
        if self.battery_level < 0:
            self.battery_level = 0.0

    def _handle_battery_alerts(self):
        if self.battery_level <= 35.0 and not self._battery_warn_35_sent:
            self._battery_warn_35_sent = True
            self.event_bus.publish(
                "robot_alert",
                {"text": "Battery warning: below 35%. Energy saving active."},
            )
        if self.battery_level > 40.0:
            self._battery_warn_35_sent = False

        if self.battery_level <= ROBOT_BATTERY_LOW_THRESHOLD and not self._battery_low_alert_sent:
            self._battery_low_alert_sent = True
            self.event_bus.publish(
                "robot_alert",
                {"text": "Battery low. Auto-charging in place."},
            )
        if self.battery_level > ROBOT_BATTERY_LOW_THRESHOLD + 5:
            self._battery_low_alert_sent = False

        if self.battery_level <= 10.0 and not self._battery_warn_10_sent:
            self._battery_warn_10_sent = True
            self.event_bus.publish(
                "robot_alert",
                {"text": "Critical battery level (<10%). Immediate charging required."},
            )
        if self.battery_level > 14.0:
            self._battery_warn_10_sent = False

    def _state_color(self):
        """Visual state indicator via robot body color."""
        if self.state == "charging":
            return COLOR_FURNITURE_SOFA
        if self.state == "executing_task":
            return COLOR_FURNITURE_BED
        return self.color

    def _draw_sensor_debug(self, screen):
        """Draw proximity radius and vision cone lines for debugging."""
        center = self.get_center()
        cx, cy = int(center[0]), int(center[1])

        # Proximity circle (all-around).
        proximity_color = (230, 122, 84) if self.last_sensor["proximity_alert"] else (154, 170, 190)
        pygame.draw.circle(screen, proximity_color, (cx, cy), int(PROXIMITY_RADIUS), 1)

        # Vision cone edges.
        heading = self.movement.heading
        for offset in (-VISION_FOV_DEG / 2, VISION_FOV_DEG / 2):
            edge_heading = math.radians(heading + offset)
            ex = cx + math.cos(edge_heading) * VISION_RANGE
            ey = cy - math.sin(edge_heading) * VISION_RANGE
            pygame.draw.line(screen, (120, 160, 210), (cx, cy), (ex, ey), 1)

        # Draw tiny markers for visible objects.
        for obj in self.last_sensor["visible_objects"][:5]:
            ox, oy = obj["position"]
            pygame.draw.circle(screen, (70, 120, 220), (int(ox), int(oy)), 6, 1)

        # Person marker from sensor state.
        if self.last_sensor["person_detected"]:
            color = (240, 75, 75) if self.last_sensor["person_in_front"] else (240, 170, 70)
            pygame.draw.circle(screen, color, (cx, cy), 5)

    def _replan_path(self, world):
        """Compute A* path from current cell to target cell."""
        if self.target_position is None:
            return

        self.path_replan_timer = 0.0
        self.request_replan = False
        self.last_goal_for_path = self.target_position

        start_cell = world.world_to_cell(self.get_center())
        goal_cell = world.world_to_cell(self.target_position)
        blocked = world.grid_map.blocked

        start_cell = self._find_nearest_free_cell(start_cell, blocked)
        goal_cell = self._find_nearest_free_cell(goal_cell, blocked)

        if start_cell is None or goal_cell is None:
            self.path_cells = []
            self.path_points = []
            self.path_index = 0
            return

        path_cells = self.pathfinder.plan(start_cell, goal_cell, blocked)

        if path_cells:
            self.path_cells = path_cells
            self.path_points = [world.cell_to_world(cell) for cell in path_cells]
            self.path_index = 1 if len(self.path_points) > 1 else 0
            return

        # Path-only mode: if A* fails, stop and wait for next replan cycle.
        self.path_cells = []
        self.path_points = []
        self.path_index = 0
        self.event_bus.publish(
            "ui_message",
            {"text": "No safe path found yet. Replanning..."},
        )

    def _get_navigation_target(self):
        if 0 <= self.path_index < len(self.path_points):
            return self.path_points[self.path_index]
        return None

    def _advance_path_if_waypoint_reached(self):
        if not (0 <= self.path_index < len(self.path_points)):
            return

        current_wp = self.path_points[self.path_index]
        if self._distance_to_target(current_wp) <= self.arrival_radius:
            if self.path_index < len(self.path_points) - 1:
                self.path_index += 1

    def _refresh_target_from_world_if_moving(self, world):
        """
        Support moving targets:
        if target position changed in world, update and request replan.
        """
        if self.target_id is None:
            return
        latest = world.get_target_by_id(self.target_id)
        if latest is None:
            return
        latest_pos = latest["position"]
        if self._distance_between_points(self.target_position, latest_pos) > world.grid_map.cell_size * 0.5:
            self.target_position = latest_pos
            self.target_label = latest.get("label", self.target_label)
            self.request_replan = True

    def _distance_between_points(self, p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def _update_animation(self, dt):
        """Update animation phases for wheel spin and subtle body bobbing."""
        speed_ratio = min(1.0, self.movement.current_speed / max(1.0, self.movement.move_speed))
        self.anim_phase += dt * (4.0 + 7.0 * speed_ratio)
        self.wheel_phase += dt * (5.0 + 12.0 * speed_ratio)

    def _update_energy_mode(self):
        """
        Smart energy management:
        reduce max movement speed as battery drops.
        """
        if self.state == "charging":
            self.energy_mode = "charging"
            self.movement.move_speed = self.base_move_speed * 0.45
            return

        if self.battery_level <= 10.0:
            self.energy_mode = "critical_save"
            self.movement.move_speed = self.base_move_speed * 0.55
            return
        if self.battery_level <= ROBOT_BATTERY_LOW_THRESHOLD:
            self.energy_mode = "low_save"
            self.movement.move_speed = self.base_move_speed * 0.72
            return
        if self.battery_level <= 35.0:
            self.energy_mode = "eco"
            self.movement.move_speed = self.base_move_speed * 0.88
            return

        self.energy_mode = "normal"
        self.movement.move_speed = self.base_move_speed

    def _maybe_request_charging(self):
        """
        When battery is low, pause tasks and auto-charge in place.
        """
        if self.battery_level > ROBOT_BATTERY_LOW_THRESHOLD:
            return
        if str(self.target_label).lower().startswith("emergency"):
            return
        if self.state == "charging":
            return
        if self._charging_requested:
            return

        self._charging_requested = True
        self.clear_target()
        self.state = "charging"
        self.movement.current_speed = 0.0
        self.event_bus.publish(
            "charging_requested",
            {
                "reason": "Battery low",
                "battery": round(self.battery_level, 1),
            },
        )

    def _find_nearest_free_cell(self, cell, blocked_grid):
        """
        Find nearest walkable cell using a small BFS around the requested cell.
        """
        cols = len(blocked_grid[0]) if blocked_grid else 0
        rows = len(blocked_grid)
        if cols == 0 or rows == 0:
            return None

        sx, sy = cell
        if 0 <= sx < cols and 0 <= sy < rows and not blocked_grid[sy][sx]:
            return (sx, sy)

        visited = set()
        queue = deque([(sx, sy)])
        visited.add((sx, sy))
        max_radius = 18  # Limit search for performance.

        while queue:
            cx, cy = queue.popleft()
            if abs(cx - sx) + abs(cy - sy) > max_radius:
                continue
            if 0 <= cx < cols and 0 <= cy < rows and not blocked_grid[cy][cx]:
                return (cx, cy)

            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if (nx, ny) in visited:
                    continue
                if nx < 0 or ny < 0 or nx >= cols or ny >= rows:
                    continue
                visited.add((nx, ny))
                queue.append((nx, ny))

        return None
