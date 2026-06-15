# App/services/hatch_logo_generator.py

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image


HatchSegment = tuple[float, float, float, float]


def generate_logo_hatch_segments(
    image_path: str | Path,
    *,
    center_x: float,
    center_y: float,
    target_box_width_mm: float = 100.0,
    target_box_height_mm: float = 100.0,
    spacing_mm: float = 1.0,
    min_segment_length_mm: float = 0.8,
    mask_mode: Literal["white", "gray", "non_black"] = "white",
    add_vertical: bool = True,
    add_horizontal: bool = True,
) -> list[HatchSegment]:
    """
    Erzeugt Schraffursegmente aus einem Logo-PNG.

    Die resultierenden Segmente liegen im Roboter-XY-System und sind um
    center_x / center_y zentriert.

    mask_mode:
        "white":
            Nur helle / weiße Logo-Elemente werden schraffiert.
            Für das BAU/Weltkugel-Logo sinnvoll.

        "non_black":
            Alle nicht-schwarzen Pixel werden schraffiert.
            Achtung: Graue Flächen und weiße Details verschmelzen dann.
    """

    image_path = Path(image_path)

    image = Image.open(image_path).convert("RGBA")

    gray = _rgba_to_gray_array(image)
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)

    # Sichtbaren Bereich suchen: alles, was nicht fast schwarz und nicht transparent ist.
    visible_mask = (alpha > 10) & (gray > 15)

    if not np.any(visible_mask):
        raise ValueError("Im Logo wurde kein sichtbarer Inhalt gefunden.")

    y_indices, x_indices = np.where(visible_mask)

    x0 = int(x_indices.min())
    x1 = int(x_indices.max()) + 1
    y0 = int(y_indices.min())
    y1 = int(y_indices.max()) + 1

    cropped = image.crop((x0, y0, x1, y1)).convert("RGBA")

    crop_w_px, crop_h_px = cropped.size

    if crop_w_px <= 0 or crop_h_px <= 0:
        raise ValueError("Ungültiger Logo-Zuschnitt.")

    # In die 100x100-Box einpassen, Seitenverhältnis bleibt erhalten.
    scale_mm_per_px = min(
        target_box_width_mm / crop_w_px,
        target_box_height_mm / crop_h_px,
    )

    logo_width_mm = crop_w_px * scale_mm_per_px
    logo_height_mm = crop_h_px * scale_mm_per_px

    gray_crop = _rgba_to_gray_array(cropped)
    alpha_crop = np.asarray(cropped.getchannel("A"), dtype=np.uint8)

    if mask_mode == "white":
        # Nur helle / weisse Elemente.
        mask = (alpha_crop > 10) & (gray_crop > 180)

    elif mask_mode == "gray":
        # Nur graue Flaechen.
        # Schwarz liegt nahe 0, weiss nahe 255.
        # Die Logo-Grauflaechen liegen typischerweise etwa im Bereich 80..160.
        mask = (alpha_crop > 10) & (gray_crop >= 50) & (gray_crop <= 180)

    elif mask_mode == "non_black":
        # Alle sichtbaren nicht-schwarzen Pixel.
        mask = (alpha_crop > 10) & (gray_crop > 15)

    else:
        raise ValueError(f"Unbekannter mask_mode: {mask_mode}")

    segments: list[HatchSegment] = []

    if add_vertical:
        segments.extend(
            _generate_vertical_segments(
                mask=mask,
                center_x=center_x,
                center_y=center_y,
                logo_width_mm=logo_width_mm,
                logo_height_mm=logo_height_mm,
                spacing_mm=spacing_mm,
                min_segment_length_mm=min_segment_length_mm,
            )
        )

    if add_horizontal:
        segments.extend(
            _generate_horizontal_segments(
                mask=mask,
                center_x=center_x,
                center_y=center_y,
                logo_width_mm=logo_width_mm,
                logo_height_mm=logo_height_mm,
                spacing_mm=spacing_mm,
                min_segment_length_mm=min_segment_length_mm,
            )
        )

    return segments


def _rgba_to_gray_array(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)

    r = rgba[:, :, 0]
    g = rgba[:, :, 1]
    b = rgba[:, :, 2]

    gray = 0.299 * r + 0.587 * g + 0.114 * b

    return gray.astype(np.uint8)


def _generate_vertical_segments(
    *,
    mask: np.ndarray,
    center_x: float,
    center_y: float,
    logo_width_mm: float,
    logo_height_mm: float,
    spacing_mm: float,
    min_segment_length_mm: float,
) -> list[HatchSegment]:
    height_px, width_px = mask.shape

    x_left_mm = center_x - logo_width_mm / 2.0
    y_top_mm = center_y + logo_height_mm / 2.0

    segments: list[HatchSegment] = []

    x_mm_local = 0.0

    while x_mm_local <= logo_width_mm:
        col = int(round((x_mm_local / logo_width_mm) * (width_px - 1)))
        col = max(0, min(width_px - 1, col))

        column_mask = mask[:, col]
        runs = _find_true_runs(column_mask)

        x_robot = x_left_mm + x_mm_local

        for start_px, end_px in runs:
            y_start_local = (start_px / (height_px - 1)) * logo_height_mm
            y_end_local = (end_px / (height_px - 1)) * logo_height_mm

            # Pixel-y läuft nach unten, Roboter-y soll nach oben laufen.
            y1 = y_top_mm - y_start_local
            y2 = y_top_mm - y_end_local

            if abs(y2 - y1) >= min_segment_length_mm:
                segments.append((x_robot, y1, x_robot, y2))

        x_mm_local += spacing_mm

    return segments


def _generate_horizontal_segments(
    *,
    mask: np.ndarray,
    center_x: float,
    center_y: float,
    logo_width_mm: float,
    logo_height_mm: float,
    spacing_mm: float,
    min_segment_length_mm: float,
) -> list[HatchSegment]:
    height_px, width_px = mask.shape

    x_left_mm = center_x - logo_width_mm / 2.0
    y_top_mm = center_y + logo_height_mm / 2.0

    segments: list[HatchSegment] = []

    y_mm_local = 0.0

    while y_mm_local <= logo_height_mm:
        row = int(round((y_mm_local / logo_height_mm) * (height_px - 1)))
        row = max(0, min(height_px - 1, row))

        row_mask = mask[row, :]
        runs = _find_true_runs(row_mask)

        y_robot = y_top_mm - y_mm_local

        for start_px, end_px in runs:
            x_start_local = (start_px / (width_px - 1)) * logo_width_mm
            x_end_local = (end_px / (width_px - 1)) * logo_width_mm

            x1 = x_left_mm + x_start_local
            x2 = x_left_mm + x_end_local

            if abs(x2 - x1) >= min_segment_length_mm:
                segments.append((x1, y_robot, x2, y_robot))

        y_mm_local += spacing_mm

    return segments


def _find_true_runs(values: np.ndarray) -> list[tuple[int, int]]:
    """
    Findet zusammenhängende True-Bereiche in einer 1D-Maske.

    Rückgabe:
        Liste aus (start_index, end_index)
    """

    runs: list[tuple[int, int]] = []

    in_run = False
    start = 0

    for i, value in enumerate(values):
        if value and not in_run:
            start = i
            in_run = True

        elif not value and in_run:
            runs.append((start, i - 1))
            in_run = False

    if in_run:
        runs.append((start, len(values) - 1))

    return runs