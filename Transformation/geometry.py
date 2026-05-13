# Transformation/geometry.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass
class Plane3D:
    """
    Ebene in Normalenform:

        normal_x * x + normal_y * y + normal_z * z + d = 0

    normal ist normiert.
    """

    normal: np.ndarray  # shape (3,)
    d: float

    @classmethod
    def from_point_and_normal(
        cls,
        point: Sequence[float],
        normal: Sequence[float],
    ) -> "Plane3D":
        n = np.asarray(normal, dtype=float).reshape(3)
        norm = np.linalg.norm(n)

        if norm < 1e-15:
            raise ValueError("Ebenennormale darf nicht Null sein.")

        n = n / norm
        p = np.asarray(point, dtype=float).reshape(3)
        d = -float(np.dot(n, p))

        return cls(normal=n, d=d)

    def signed_distance(self, point: Sequence[float]) -> float:
        p = np.asarray(point, dtype=float).reshape(3)
        return float(np.dot(self.normal, p) + self.d)

    def z_at_xy(self, x: float, y: float) -> float:
        """
        Berechnet z auf der Ebene zu gegebenem x/y.

        Voraussetzung:
        normal_z darf nicht nahe 0 sein.
        """

        nz = self.normal[2]

        if abs(nz) < 1e-12:
            raise ValueError(
                "z_at_xy nicht möglich: Ebene ist nahezu vertikal "
                "(normal_z ist zu klein)."
            )

        nx, ny, _ = self.normal

        return float(-(nx * x + ny * y + self.d) / nz)

    def shifted_along_vector(self, vector: Sequence[float]) -> "Plane3D":
        """
        Verschiebt die Ebene parallel um einen Vektor.

        Beispiel:
            marker_plane = reflector_plane.shifted_along_vector(-offset_lt)
        """

        v = np.asarray(vector, dtype=float).reshape(3)

        # Ein Punkt p auf Ebene wird zu p + v.
        # Neue Ebene: n·x + d' = 0
        # d' = d - n·v
        new_d = self.d - float(np.dot(self.normal, v))

        return Plane3D(
            normal=self.normal.copy(),
            d=new_d,
        )

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (
            float(self.normal[0]),
            float(self.normal[1]),
            float(self.normal[2]),
            float(self.d),
        )

    def format_summary(self, name: str = "Plane3D") -> str:
        nx, ny, nz = self.normal

        return (
            f"{name}\n"
            f"  normal = ({nx:.9f}, {ny:.9f}, {nz:.9f})\n"
            f"  d      = {self.d:.9f}\n"
            f"  Form   = nx*x + ny*y + nz*z + d = 0"
        )


def fit_plane_from_points(
    points: Iterable[Sequence[float]],
) -> Plane3D:
    """
    Least-Squares-Ebenenfit aus 3D-Punkten.

    Funktioniert mit mindestens 3 Punkten.
    Bei mehr Punkten wird eine Ausgleichsebene bestimmt.
    """

    pts = np.asarray(list(points), dtype=float)

    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points muss eine Liste/Array von 3D-Punkten sein.")

    if pts.shape[0] < 3:
        raise ValueError("Für eine Ebene werden mindestens 3 Punkte benötigt.")

    if not np.all(np.isfinite(pts)):
        raise ValueError("Alle Punkte müssen gültige endliche Zahlen sein.")

    centroid = pts.mean(axis=0)
    centered = pts - centroid

    rank = np.linalg.matrix_rank(centered)

    if rank < 2:
        raise ValueError(
            "Ebenenfit nicht möglich: Punkte sind degeneriert "
            "(identisch oder nahezu linear)."
        )

    # SVD: Normale ist Richtung der kleinsten Varianz.
    _, _, vh = np.linalg.svd(centered)
    normal = vh[-1, :]

    # Normale stabil orientieren:
    # Für unsere Anwendung soll normal_z bevorzugt positiv sein.
    if normal[2] < 0:
        normal = -normal

    return Plane3D.from_point_and_normal(
        point=centroid,
        normal=normal,
    )


def offset_vector_robot_to_tracker(
    trafo,
    offset_robot: Sequence[float],
) -> np.ndarray:
    """
    Transformiert einen reinen Offsetvektor vom Roboter- ins Trackersystem.

    Wichtig:
    Nur Rotation und Maßstab, keine Translation.

        offset_tracker = scale * rotation @ offset_robot
    """

    offset = np.asarray(offset_robot, dtype=float).reshape(3)

    return trafo.scale * (trafo.rotation @ offset)