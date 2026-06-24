# App/map_view.py

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from App.stakeout_point import StakeoutPoint


class MapView(ctk.CTkFrame):
    """
    2D-Draufsicht fuer Absteckpunkte im LT-/Projektkoordinatensystem.

    Funktionen:
        - Punkte zeichnen
        - Auswahl per Klick
        - Ansicht mit linker Maustaste verschieben
        - Zoom per Mausrad
        - kleine View-Buttons im Canvas: +, -, []
        - Massstabsbalken rechts unten
        - optional Trackerposition und Arbeitsbereichspolygon
    """

    def __init__(
        self,
        master,
        on_point_selected: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)

        self.on_point_selected = on_point_selected

        self.points: list[StakeoutPoint] = []
        self.tracker_position: tuple[float, float] | None = None
        self.robot_workspace_polygon: list[tuple[float, float]] | None = None
        self.robot_wagon_outline_polygon: list[tuple[float, float]] | None = None
        self.robot_front_arrow: tuple[tuple[float, float], tuple[float, float]] | None = None
        self.robot_reflector_position: tuple[float, float] | None = None
        self.robot_marker_position: tuple[float, float] | None = None

        self.view_center_x = 0.0
        self.view_center_y = 0.0
        self.scale_px_per_mm = 1.0

        self._drag_start: tuple[int, int] | None = None
        self._drag_total_px = 0.0

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self,
            bg="#1f1f1f",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.canvas.bind("<B1-Motion>", self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Button-4>", lambda event: self.zoom_at(event.x, event.y, 1.15))
        self.canvas.bind("<Button-5>", lambda event: self.zoom_at(event.x, event.y, 1.0 / 1.15))

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def set_points(self, points: list[StakeoutPoint], *, keep_view: bool = False) -> None:
        self.points = points
        if keep_view:
            self.redraw()
        else:
            self.zoom_all()

    def set_tracker_position(self, position: tuple[float, float] | None) -> None:
        self.tracker_position = position
        self.redraw()

    def set_robot_workspace_polygon(
        self,
        polygon: list[tuple[float, float]] | None,
    ) -> None:
        self.robot_workspace_polygon = polygon
        self.redraw()

    def set_robot_wagon_outline_polygon(
        self,
        polygon: list[tuple[float, float]] | None,
    ) -> None:
        self.robot_wagon_outline_polygon = polygon
        self.redraw()

    def set_robot_front_arrow(
        self,
        arrow: tuple[tuple[float, float], tuple[float, float]] | None,
    ) -> None:
        self.robot_front_arrow = arrow
        self.redraw()

    def set_robot_reflector_position(
        self,
        position: tuple[float, float] | None,
    ) -> None:
        self.robot_reflector_position = position
        self.redraw()

    def set_robot_marker_position(
        self,
        position: tuple[float, float] | None,
    ) -> None:
        self.robot_marker_position = position
        self.redraw()

    def set_robot_visualization(
        self,
        *,
        workspace_polygon: list[tuple[float, float]] | None = None,
        wagon_outline_polygon: list[tuple[float, float]] | None = None,
        front_arrow: tuple[tuple[float, float], tuple[float, float]] | None = None,
        reflector_position: tuple[float, float] | None = None,
        marker_position: tuple[float, float] | None = None,
    ) -> None:
        self.robot_workspace_polygon = workspace_polygon
        self.robot_wagon_outline_polygon = wagon_outline_polygon
        self.robot_front_arrow = front_arrow
        self.robot_reflector_position = reflector_position
        self.robot_marker_position = marker_position
        self.redraw()

    def zoom_all(self) -> None:
        bounds = self._calculate_bounds()

        if bounds is None:
            self.view_center_x = 0.0
            self.view_center_y = 0.0
            self.scale_px_per_mm = 1.0
            self.redraw()
            return

        min_x, min_y, max_x, max_y = bounds
        width_world = max(max_x - min_x, 1.0)
        height_world = max(max_y - min_y, 1.0)

        self.view_center_x = (min_x + max_x) / 2.0
        self.view_center_y = (min_y + max_y) / 2.0

        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        margin_px = 80.0
        scale_x = max((canvas_w - 2 * margin_px) / width_world, 0.001)
        scale_y = max((canvas_h - 2 * margin_px) / height_world, 0.001)

        self.scale_px_per_mm = min(scale_x, scale_y)
        self.redraw()

    def zoom_in(self) -> None:
        self.zoom_at(
            self.canvas.winfo_width() / 2.0,
            self.canvas.winfo_height() / 2.0,
            1.25,
        )

    def zoom_out(self) -> None:
        self.zoom_at(
            self.canvas.winfo_width() / 2.0,
            self.canvas.winfo_height() / 2.0,
            1.0 / 1.25,
        )

    def redraw(self) -> None:
        self.canvas.delete("all")

        self._draw_background_grid()
        self._draw_robot_wagon_outline()
        self._draw_robot_workspace()
        self._draw_robot_front_arrow()
        self._draw_robot_reflector_marker()
        self._draw_tracker()
        self._draw_points()
        self._draw_scale_bar()
        self._draw_view_buttons()

    # --------------------------------------------------
    # Coordinate transforms
    # --------------------------------------------------

    def world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        sx = canvas_w / 2.0 + (x - self.view_center_x) * self.scale_px_per_mm
        sy = canvas_h / 2.0 - (y - self.view_center_y) * self.scale_px_per_mm

        return sx, sy

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        x = self.view_center_x + (sx - canvas_w / 2.0) / self.scale_px_per_mm
        y = self.view_center_y - (sy - canvas_h / 2.0) / self.scale_px_per_mm

        return x, y

    # --------------------------------------------------
    # Drawing
    # --------------------------------------------------

    def _draw_background_grid(self) -> None:
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        self.canvas.create_rectangle(0, 0, canvas_w, canvas_h, fill="#1f1f1f", outline="")

        grid_mm = self._nice_length(max(50.0, 80.0 / max(self.scale_px_per_mm, 0.001)))

        left_world, top_world = self.screen_to_world(0, 0)
        right_world, bottom_world = self.screen_to_world(canvas_w, canvas_h)

        min_x = min(left_world, right_world)
        max_x = max(left_world, right_world)
        min_y = min(bottom_world, top_world)
        max_y = max(bottom_world, top_world)

        start_x = math.floor(min_x / grid_mm) * grid_mm
        end_x = math.ceil(max_x / grid_mm) * grid_mm
        start_y = math.floor(min_y / grid_mm) * grid_mm
        end_y = math.ceil(max_y / grid_mm) * grid_mm

        x = start_x
        while x <= end_x:
            sx1, sy1 = self.world_to_screen(x, min_y)
            sx2, sy2 = self.world_to_screen(x, max_y)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#2b2b2b")
            x += grid_mm

        y = start_y
        while y <= end_y:
            sx1, sy1 = self.world_to_screen(min_x, y)
            sx2, sy2 = self.world_to_screen(max_x, y)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#2b2b2b")
            y += grid_mm

    def _draw_robot_wagon_outline(self) -> None:
        if not self.robot_wagon_outline_polygon:
            return

        coords: list[tuple[float, float]] = [
            self.world_to_screen(x, y)
            for x, y in self.robot_wagon_outline_polygon
        ]

        if len(coords) < 3:
            return

        closed = coords + [coords[0]]
        flat: list[float] = []
        for sx, sy in closed:
            flat.extend([sx, sy])

        self.canvas.create_line(
            *flat,
            fill="#666666",
            width=1,
            dash=(6, 4),
        )

    def _draw_robot_workspace(self) -> None:
        if not self.robot_workspace_polygon:
            return

        coords: list[float] = []
        for x, y in self.robot_workspace_polygon:
            sx, sy = self.world_to_screen(x, y)
            coords.extend([sx, sy])

        if len(coords) >= 6:
            self.canvas.create_polygon(
                *coords,
                fill="#004d5c",
                outline="#00bcd4",
                width=2,
                stipple="gray12",
            )

    def _draw_robot_front_arrow(self) -> None:
        if self.robot_front_arrow is None:
            return

        (start_x, start_y), (end_x, end_y) = self.robot_front_arrow
        sx1, sy1 = self.world_to_screen(start_x, start_y)
        sx2, sy2 = self.world_to_screen(end_x, end_y)

        self.canvas.create_line(
            sx1,
            sy1,
            sx2,
            sy2,
            fill="#006f8a",
            width=3,
            arrow=tk.LAST,
            arrowshape=(16, 20, 7),
        )

    def _draw_robot_reflector_marker(self) -> None:
        if self.robot_reflector_position is not None:
            x, y = self.robot_reflector_position
            sx, sy = self.world_to_screen(x, y)
            r = 5
            self.canvas.create_oval(
                sx - r,
                sy - r,
                sx + r,
                sy + r,
                fill="#ffffff",
                outline="#006f8a",
                width=2,
            )
            self.canvas.create_text(
                sx + 8,
                sy + 8,
                text="R",
                fill="#006f8a",
                anchor="nw",
                font=("Segoe UI", 8, "bold"),
            )

        if self.robot_marker_position is not None:
            x, y = self.robot_marker_position
            sx, sy = self.world_to_screen(x, y)
            r = 6
            self.canvas.create_line(sx - r, sy, sx + r, sy, fill="#c62828", width=2)
            self.canvas.create_line(sx, sy - r, sx, sy + r, fill="#c62828", width=2)
            self.canvas.create_text(
                sx + 8,
                sy - 8,
                text="M",
                fill="#c62828",
                anchor="sw",
                font=("Segoe UI", 8, "bold"),
            )

    def _draw_tracker(self) -> None:
        if self.tracker_position is None:
            return

        x, y = self.tracker_position
        sx, sy = self.world_to_screen(x, y)
        r = 10

        self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, outline="#ff9800", width=2)
        self.canvas.create_line(sx - 14, sy, sx + 14, sy, fill="#ff9800", width=2)
        self.canvas.create_line(sx, sy - 14, sx, sy + 14, fill="#ff9800", width=2)
        self.canvas.create_text(
            sx + 14,
            sy - 14,
            text="Lasertracker",
            fill="#ff9800",
            anchor="sw",
            font=("Segoe UI", 9),
        )

    def _draw_points(self) -> None:
        for point in self.points:
            sx, sy = self.world_to_screen(point.x, point.y)

            radius = 6
            fill = "#4aa3ff"
            outline = "#cfd8dc"
            width = 1

            if point.reachable:
                fill = "#2ecc71"
                outline = "#ffffff"
                width = 2

            if point.marked:
                fill = "#757575"
                outline = "#bdbdbd"
                width = 1

            if point.selected:
                outline = "#ffeb3b"
                width = 3
                radius = 8

            self.canvas.create_oval(
                sx - radius,
                sy - radius,
                sx + radius,
                sy + radius,
                fill=fill,
                outline=outline,
                width=width,
            )

            self.canvas.create_text(
                sx + 10,
                sy - 10,
                text=point.name,
                fill="#eeeeee",
                anchor="sw",
                font=("Segoe UI", 9),
            )

    def _draw_scale_bar(self) -> None:
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        visible_width_mm = canvas_w / max(self.scale_px_per_mm, 0.001)
        length_mm = self._nice_length(visible_width_mm / 5.0)
        length_px = length_mm * self.scale_px_per_mm

        x2 = canvas_w - 28
        y = canvas_h - 28
        x1 = x2 - length_px

        self.canvas.create_line(x1, y, x2, y, fill="#ffffff", width=3)
        self.canvas.create_line(x1, y - 5, x1, y + 5, fill="#ffffff", width=2)
        self.canvas.create_line(x2, y - 5, x2, y + 5, fill="#ffffff", width=2)
        self.canvas.create_text(
            (x1 + x2) / 2.0,
            y - 10,
            text=f"{length_mm:g} mm",
            fill="#ffffff",
            anchor="s",
            font=("Segoe UI", 9),
        )

    def _draw_view_buttons(self) -> None:
        button_specs = [
            ("+", "zoom_in"),
            ("-", "zoom_out"),
            ("[]", "zoom_all"),
        ]

        x0 = max(self.canvas.winfo_width() - 112, 8)
        y0 = 10
        size = 28
        gap = 6

        for index, (label, tag_name) in enumerate(button_specs):
            x1 = x0 + index * (size + gap)
            y1 = y0
            x2 = x1 + size
            y2 = y1 + size
            tag = f"view_button_{tag_name}"

            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#303030",
                outline="#cfd8dc",
                width=1,
                tags=("view_button", tag),
            )
            self.canvas.create_text(
                (x1 + x2) / 2.0,
                (y1 + y2) / 2.0,
                text=label,
                fill="#ffffff",
                font=("Segoe UI", 10, "bold"),
                tags=("view_button", tag),
            )

    # --------------------------------------------------
    # Events
    # --------------------------------------------------

    def _on_left_press(self, event) -> None:
        self._drag_start = (event.x, event.y)
        self._drag_total_px = 0.0

    def _on_left_drag(self, event) -> None:
        if self._drag_start is None:
            return

        last_x, last_y = self._drag_start
        dx_px = event.x - last_x
        dy_px = event.y - last_y

        self._drag_total_px += math.hypot(dx_px, dy_px)

        self.view_center_x -= dx_px / self.scale_px_per_mm
        self.view_center_y += dy_px / self.scale_px_per_mm

        self._drag_start = (event.x, event.y)
        self.redraw()

    def _on_left_release(self, event) -> None:
        clicked_button = self._handle_view_button_click(event.x, event.y)
        if clicked_button:
            self._drag_start = None
            self._drag_total_px = 0.0
            return

        # Kleine Bewegungen gelten als Klick, groessere als Kartenverschiebung.
        if self._drag_total_px < 5.0:
            nearest = self._nearest_point(event.x, event.y)
            if nearest is not None and self.on_point_selected is not None:
                self.on_point_selected(nearest.name)

        self._drag_start = None
        self._drag_total_px = 0.0

    def _on_mouse_wheel(self, event) -> None:
        factor = 1.15 if event.delta > 0 else 1.0 / 1.15
        self.zoom_at(event.x, event.y, factor)

    def zoom_at(self, screen_x: float, screen_y: float, factor: float) -> None:
        before_x, before_y = self.screen_to_world(screen_x, screen_y)
        self.scale_px_per_mm = max(0.0001, min(self.scale_px_per_mm * factor, 1000.0))
        after_x, after_y = self.screen_to_world(screen_x, screen_y)

        self.view_center_x += before_x - after_x
        self.view_center_y += before_y - after_y

        self.redraw()

    def _handle_view_button_click(self, sx: float, sy: float) -> bool:
        canvas_w = max(self.canvas.winfo_width(), 1)
        x0 = max(canvas_w - 112, 8)
        y0 = 10
        size = 28
        gap = 6

        actions = [self.zoom_in, self.zoom_out, self.zoom_all]

        for index, action in enumerate(actions):
            x1 = x0 + index * (size + gap)
            y1 = y0
            x2 = x1 + size
            y2 = y1 + size

            if x1 <= sx <= x2 and y1 <= sy <= y2:
                action()
                return True

        return False

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _calculate_bounds(self) -> tuple[float, float, float, float] | None:
        xs: list[float] = []
        ys: list[float] = []

        for point in self.points:
            xs.append(point.x)
            ys.append(point.y)

        if self.tracker_position is not None:
            xs.append(self.tracker_position[0])
            ys.append(self.tracker_position[1])

        if self.robot_workspace_polygon:
            for x, y in self.robot_workspace_polygon:
                xs.append(x)
                ys.append(y)

        if self.robot_wagon_outline_polygon:
            for x, y in self.robot_wagon_outline_polygon:
                xs.append(x)
                ys.append(y)

        if self.robot_front_arrow:
            for x, y in self.robot_front_arrow:
                xs.append(x)
                ys.append(y)

        if self.robot_reflector_position is not None:
            xs.append(self.robot_reflector_position[0])
            ys.append(self.robot_reflector_position[1])

        if self.robot_marker_position is not None:
            xs.append(self.robot_marker_position[0])
            ys.append(self.robot_marker_position[1])

        if not xs or not ys:
            return None

        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)

        padding = max(max_x - min_x, max_y - min_y, 100.0) * 0.15

        return min_x - padding, min_y - padding, max_x + padding, max_y + padding

    def _nearest_point(self, sx: float, sy: float) -> StakeoutPoint | None:
        best: StakeoutPoint | None = None
        best_dist = 14.0

        for point in self.points:
            px, py = self.world_to_screen(point.x, point.y)
            dist = math.hypot(px - sx, py - sy)

            if dist < best_dist:
                best = point
                best_dist = dist

        return best

    @staticmethod
    def _nice_length(value: float) -> float:
        if value <= 0:
            return 1.0

        exponent = math.floor(math.log10(value))
        fraction = value / (10 ** exponent)

        if fraction < 1.5:
            nice_fraction = 1.0
        elif fraction < 3.5:
            nice_fraction = 2.0
        elif fraction < 7.5:
            nice_fraction = 5.0
        else:
            nice_fraction = 10.0

        return nice_fraction * (10 ** exponent)
