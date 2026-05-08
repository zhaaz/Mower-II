# marker_shapes.py

MarkerStroke = list[tuple[float, float]]
MarkerShape = list[MarkerStroke]

MARKER_SHAPES: dict[str, MarkerShape] = {
    "plus": [
        [(-0.5, 0.0), (0.5, 0.0)],
        [(0.0, -0.5), (0.0, 0.5)],
    ],

    "cross": [
        [(-0.5, -0.5), (0.5, 0.5)],
        [(-0.5, 0.5), (0.5, -0.5)],
    ],

    "circle_point": [
        # kleiner Mittelpunkt als kurzer Strich
        [(-0.05, 0.0), (0.05, 0.0)],
    ],

    "plus_circle": [
        [(-0.5, 0.0), (0.5, 0.0)],
        [(0.0, -0.5), (0.0, 0.5)],
    ],
}