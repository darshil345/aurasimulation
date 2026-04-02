import heapq


class AStarPlanner:
    """
    Grid-based A* path planner.

    Beginner note:
    - Input is a blocked-cell grid.
    - Output is a list of cells from start to goal.
    """

    def plan(self, start_cell, goal_cell, blocked_grid):
        rows = len(blocked_grid)
        if rows == 0:
            return []
        cols = len(blocked_grid[0])

        sx, sy = start_cell
        gx, gy = goal_cell
        if not self._inside(sx, sy, cols, rows) or not self._inside(gx, gy, cols, rows):
            return []
        if blocked_grid[sy][sx] or blocked_grid[gy][gx]:
            return []

        open_heap = []
        heapq.heappush(open_heap, (0.0, 0.0, (sx, sy)))

        came_from = {}
        g_score = {(sx, sy): 0.0}
        closed = set()

        while open_heap:
            _, current_g, current = heapq.heappop(open_heap)
            if current in closed:
                continue
            closed.add(current)

            if current == (gx, gy):
                return self._reconstruct_path(came_from, current)

            cx, cy = current
            for nx, ny in self._neighbors_4(cx, cy):
                if not self._inside(nx, ny, cols, rows):
                    continue
                if blocked_grid[ny][nx]:
                    continue
                if (nx, ny) in closed:
                    continue

                tentative_g = current_g + 1.0
                old_g = g_score.get((nx, ny))
                if old_g is None or tentative_g < old_g:
                    g_score[(nx, ny)] = tentative_g
                    came_from[(nx, ny)] = (cx, cy)
                    f = tentative_g + self._heuristic(nx, ny, gx, gy)
                    heapq.heappush(open_heap, (f, tentative_g, (nx, ny)))

        return []

    def _heuristic(self, x1, y1, x2, y2):
        # Manhattan distance for 4-direction movement.
        return abs(x1 - x2) + abs(y1 - y2)

    def _neighbors_4(self, x, y):
        return [
            (x + 1, y),
            (x - 1, y),
            (x, y + 1),
            (x, y - 1),
        ]

    def _inside(self, x, y, cols, rows):
        return 0 <= x < cols and 0 <= y < rows

    def _reconstruct_path(self, came_from, current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
