import math

import pygame

from config import (
    PERSON_DETECT_RADIUS,
    PERSON_FRONT_FOV_DEG,
    PROXIMITY_RADIUS,
    SENSOR_LOOK_AHEAD,
    SENSOR_WIDTH,
    VISION_FOV_DEG,
    VISION_RANGE,
)


class SensorSuite:
    """
    Sensor simulation using geometry math only.

    Includes:
    - Proximity sensor: nearby obstacle detection in all directions
    - Vision sensor: object detection only in front cone
    - Person detector: presence + front-check for person target
    """

    def scan(self, x, y, heading, robot_size, obstacles, bounds, objects, person):
        """
        Scan and return a dictionary with all sensor outputs.

        Params:
        - x, y: robot top-left
        - heading: robot heading in degrees
        - robot_size: robot square size
        - obstacles: list of pygame.Rect
        - bounds: (min_x, min_y, max_x, max_y)
        - objects: list of dictionaries with id/label/position
        - person: dictionary with id/label/position
        """
        heading_rad = math.radians(heading)
        center_x = x + robot_size / 2
        center_y = y + robot_size / 2

        front_x = center_x + math.cos(heading_rad) * SENSOR_LOOK_AHEAD
        front_y = center_y - math.sin(heading_rad) * SENSOR_LOOK_AHEAD

        sensor_rect = pygame.Rect(
            int(front_x - SENSOR_WIDTH / 2),
            int(front_y - SENSOR_WIDTH / 2),
            SENSOR_WIDTH,
            SENSOR_WIDTH,
        )

        min_x, min_y, max_x, max_y = bounds
        boundary_hit = (
            sensor_rect.left < min_x
            or sensor_rect.top < min_y
            or sensor_rect.right > max_x
            or sensor_rect.bottom > max_y
        )
        obstacle_hit = any(sensor_rect.colliderect(obstacle) for obstacle in obstacles)

        proximity_hits = self._scan_proximity(center_x, center_y, obstacles)
        visible_objects = self._scan_vision(
            center_x=center_x,
            center_y=center_y,
            heading=heading,
            objects=objects,
        )
        person_sensor = self._scan_person(
            center_x=center_x,
            center_y=center_y,
            heading=heading,
            person=person,
        )

        return {
            "sensor_rect": sensor_rect,
            "obstacle_ahead": boundary_hit or obstacle_hit,
            "proximity_alert": len(proximity_hits) > 0,
            "nearby_obstacles": proximity_hits,
            "visible_objects": visible_objects,
            "person_detected": person_sensor["detected"],
            "person_in_front": person_sensor["in_front"],
            "person_distance": person_sensor["distance"],
            "person_bearing_diff": person_sensor["bearing_diff"],
        }

    def _scan_proximity(self, center_x, center_y, obstacles):
        """
        Proximity = any obstacle whose nearest edge point is inside radius.
        """
        results = []
        for obstacle in obstacles:
            nearest_x = max(obstacle.left, min(center_x, obstacle.right))
            nearest_y = max(obstacle.top, min(center_y, obstacle.bottom))
            distance = math.hypot(nearest_x - center_x, nearest_y - center_y)
            if distance <= PROXIMITY_RADIUS:
                results.append(
                    {
                        "distance": distance,
                        "center": (obstacle.centerx, obstacle.centery),
                    }
                )
        results.sort(key=lambda it: it["distance"])
        return results

    def _scan_vision(self, center_x, center_y, heading, objects):
        """
        Vision = object inside range and inside heading field-of-view cone.
        """
        visible = []
        for obj in objects:
            ox, oy = obj["position"]
            dx = ox - center_x
            dy = center_y - oy  # pygame Y axis is downward
            distance = math.hypot(dx, dy)
            if distance > VISION_RANGE:
                continue

            angle_to_object = math.degrees(math.atan2(dy, dx))
            angle_diff = abs(self._wrap_degrees(angle_to_object - heading))
            if angle_diff <= VISION_FOV_DEG / 2:
                visible.append(
                    {
                        "id": obj["id"],
                        "label": obj["label"],
                        "distance": distance,
                        "position": obj["position"],
                    }
                )

        visible.sort(key=lambda it: it["distance"])
        return visible

    def _scan_person(self, center_x, center_y, heading, person):
        px, py = person["position"]
        dx = px - center_x
        dy = center_y - py  # pygame Y axis is downward
        distance = math.hypot(dx, dy)
        angle_to_person = math.degrees(math.atan2(dy, dx))
        bearing_diff = abs(self._wrap_degrees(angle_to_person - heading))

        detected = distance <= PERSON_DETECT_RADIUS
        in_front = detected and bearing_diff <= PERSON_FRONT_FOV_DEG / 2

        return {
            "detected": detected,
            "in_front": in_front,
            "distance": distance,
            "bearing_diff": bearing_diff,
        }

    def _wrap_degrees(self, degrees_value):
        """Normalize angle to [-180, 180] for easy difference checks."""
        return (degrees_value + 180) % 360 - 180
