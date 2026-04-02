import math


class MovementController:
    """
    Handles low-level robot movement math.

    Movement is frame-independent:
    velocity = speed * direction
    position += velocity * dt
    """

    def __init__(self, move_speed, turn_speed, angle_threshold, acceleration, deceleration):
        self.move_speed = move_speed
        self.turn_speed = turn_speed
        self.angle_threshold = angle_threshold
        self.acceleration = acceleration
        self.deceleration = deceleration
        self.heading = 0.0  # degrees
        self.current_speed = 0.0

    def update_toward_target(self, position, target, dt):
        """
        Rotate and move toward a target.

        Returns:
            dict with x, y, heading, moving_forward, heading_error
        """
        x, y = position
        tx, ty = target

        to_target_x = tx - x
        to_target_y = ty - y
        desired_heading = math.degrees(math.atan2(-to_target_y, to_target_x))
        heading_error = self._normalize_angle(desired_heading - self.heading)

        max_turn = self.turn_speed * dt
        turn = max(-max_turn, min(max_turn, heading_error))
        self.heading = self._normalize_angle(self.heading + turn)

        moving_forward = False
        wants_forward = abs(heading_error) <= self.angle_threshold

        # Smooth acceleration/deceleration.
        if wants_forward:
            self.current_speed += self.acceleration * dt
            if self.current_speed > self.move_speed:
                self.current_speed = self.move_speed
        else:
            self.current_speed -= self.deceleration * dt
            if self.current_speed < 0:
                self.current_speed = 0.0

        new_x = x
        new_y = y
        if self.current_speed > 0.01:
            moving_forward = True
            heading_rad = math.radians(self.heading)
            dir_x = math.cos(heading_rad)
            dir_y = -math.sin(heading_rad)
            vx = self.current_speed * dir_x
            vy = self.current_speed * dir_y
            new_x += vx * dt
            new_y += vy * dt

        return {
            "x": new_x,
            "y": new_y,
            "heading": self.heading,
            "moving_forward": moving_forward,
            "heading_error": heading_error,
            "speed": self.current_speed,
        }

    def _normalize_angle(self, angle):
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle
