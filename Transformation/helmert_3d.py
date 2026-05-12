# Transformation/helmert_3d.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass
class Helmert3DResult:
    translation: np.ndarray          # shape (3,)
    rotation: np.ndarray             # shape (3, 3)
    scale: float
    quaternion: np.ndarray           # [q0, q1, q2, q3]
    residuals: np.ndarray            # tracker_observed - tracker_computed, shape (n, 3)
    residual_norms: np.ndarray       # shape (n,)
    rms: float
    max_residual: float
    point_count: int

    def robot_to_tracker(self, point: Sequence[float]) -> np.ndarray:
        p = np.asarray(point, dtype=float).reshape(3)
        return self.translation + self.scale * (self.rotation @ p)

    def tracker_to_robot(self, point: Sequence[float]) -> np.ndarray:
        p = np.asarray(point, dtype=float).reshape(3)
        return self.rotation.T @ ((p - self.translation) / self.scale)

    def format_summary(self) -> str:
        q = self.quaternion
        t = self.translation

        return (
            "Helmert 3D Transformation\n"
            f"  Punktanzahl: {self.point_count}\n"
            f"  Translation [mm]: "
            f"Tx={t[0]:.6f}, Ty={t[1]:.6f}, Tz={t[2]:.6f}\n"
            f"  Maßstab: {self.scale:.12f}\n"
            f"  Quaternion [q0, q1, q2, q3]: "
            f"{q[0]:.12f}, {q[1]:.12f}, {q[2]:.12f}, {q[3]:.12f}\n"
            f"  RMS [mm]: {self.rms:.6f}\n"
            f"  Max. Restklaffung [mm]: {self.max_residual:.6f}"
        )


def estimate_helmert_3d(
    robot_points: Iterable[Sequence[float]],
    tracker_points: Iterable[Sequence[float]],
    *,
    allow_scale: bool = True,
    min_geometry_rank: int = 2,
) -> Helmert3DResult:
    """
    Berechnet eine räumliche Helmert-Transformation:

        tracker = translation + scale * rotation @ robot

    Parameter
    ---------
    robot_points:
        Punkte im Roboter-/Maschinensystem, shape (n, 3)

    tracker_points:
        Homologe Punkte im Trackersystem, shape (n, 3)

    allow_scale:
        True  -> Maßstab wird geschätzt
        False -> Maßstab wird auf 1.0 fixiert

    min_geometry_rank:
        Mindest-Rang der Roboterpunkt-Geometrie.
        2 reicht für flächig verteilte Punkte.
        3 wäre für echte räumliche Punktverteilung nötig.

    Hinweise
    --------
    Für euren aktuellen XY-Roboter mit z = konstant ist rank=2 realistisch.
    Wenn später auch Z-Punkte räumlich verteilt sind, kann rank=3 gefordert werden.
    """

    robot = np.asarray(list(robot_points), dtype=float)
    tracker = np.asarray(list(tracker_points), dtype=float)

    _validate_points(robot, tracker, min_geometry_rank=min_geometry_rank)

    robot_centroid = robot.mean(axis=0)
    tracker_centroid = tracker.mean(axis=0)

    robot_centered = robot - robot_centroid
    tracker_centered = tracker - tracker_centroid

    # Kreuzkovarianz analog S = L^T G
    s = robot_centered.T @ tracker_centered

    n_matrix = _build_quaternion_matrix(s)

    eigenvalues, eigenvectors = np.linalg.eigh(n_matrix)
    q = eigenvectors[:, np.argmax(eigenvalues)]

    # Vorzeichenkonvention stabilisieren
    if q[0] < 0:
        q = -q

    q = q / np.linalg.norm(q)

    rotation = quaternion_to_rotation_matrix(q)

    if allow_scale:
        numerator = 0.0
        denominator = 0.0

        for r, t in zip(robot_centered, tracker_centered):
            numerator += t @ (rotation @ r)
            denominator += r @ r

        if abs(denominator) < 1e-15:
            raise ValueError("Maßstab nicht bestimmbar: Roboterpunkte haben keine ausreichende Ausdehnung.")

        scale = numerator / denominator
    else:
        scale = 1.0

    translation = tracker_centroid - scale * (rotation @ robot_centroid)

    computed_tracker = np.array([
        translation + scale * (rotation @ p)
        for p in robot
    ])

    residuals = tracker - computed_tracker
    residual_norms = np.linalg.norm(residuals, axis=1)

    rms = float(np.sqrt(np.mean(residual_norms ** 2)))
    max_residual = float(np.max(residual_norms))

    return Helmert3DResult(
        translation=translation,
        rotation=rotation,
        scale=float(scale),
        quaternion=q,
        residuals=residuals,
        residual_norms=residual_norms,
        rms=rms,
        max_residual=max_residual,
        point_count=len(robot),
    )


def quaternion_to_rotation_matrix(q: Sequence[float]) -> np.ndarray:
    """
    Quaternion [q0, q1, q2, q3] -> Rotationsmatrix.
    q0 ist der skalare Anteil.
    """

    q0, q1, q2, q3 = np.asarray(q, dtype=float)

    return np.array([
        [
            q0*q0 + q1*q1 - q2*q2 - q3*q3,
            2.0 * (q1*q2 - q0*q3),
            2.0 * (q1*q3 + q0*q2),
        ],
        [
            2.0 * (q1*q2 + q0*q3),
            q0*q0 - q1*q1 + q2*q2 - q3*q3,
            2.0 * (q2*q3 - q0*q1),
        ],
        [
            2.0 * (q1*q3 - q0*q2),
            2.0 * (q2*q3 + q0*q1),
            q0*q0 - q1*q1 - q2*q2 + q3*q3,
        ],
    ], dtype=float)


def _build_quaternion_matrix(s: np.ndarray) -> np.ndarray:
    sxx, sxy, sxz = s[0, 0], s[0, 1], s[0, 2]
    syx, syy, syz = s[1, 0], s[1, 1], s[1, 2]
    szx, szy, szz = s[2, 0], s[2, 1], s[2, 2]

    return np.array([
        [sxx + syy + szz, syz - szy,       szx - sxz,       sxy - syx],
        [syz - szy,       sxx - syy - szz, sxy + syx,       szx + sxz],
        [szx - sxz,       sxy + syx,      -sxx + syy - szz, syz + szy],
        [sxy - syx,       szx + sxz,       syz + szy,      -sxx - syy + szz],
    ], dtype=float)


def _validate_points(
    robot: np.ndarray,
    tracker: np.ndarray,
    *,
    min_geometry_rank: int,
) -> None:
    if robot.ndim != 2 or tracker.ndim != 2:
        raise ValueError("robot_points und tracker_points müssen 2D-Arrays sein.")

    if robot.shape != tracker.shape:
        raise ValueError(
            f"robot_points und tracker_points müssen gleiche Form haben. "
            f"robot={robot.shape}, tracker={tracker.shape}"
        )

    if robot.shape[1] != 3:
        raise ValueError("Punkte müssen 3D-Koordinaten haben: x, y, z.")

    if robot.shape[0] < 3:
        raise ValueError("Für Helmert 3D werden mindestens 3 Punktpaare benötigt.")

    if not np.all(np.isfinite(robot)) or not np.all(np.isfinite(tracker)):
        raise ValueError("Alle Koordinaten müssen gültige endliche Zahlen sein.")

    robot_centered = robot - robot.mean(axis=0)
    rank = np.linalg.matrix_rank(robot_centered)

    if rank < min_geometry_rank:
        raise ValueError(
            f"Roboterpunkt-Geometrie ist degeneriert. "
            f"Rang={rank}, erforderlich={min_geometry_rank}. "
            f"Punkte dürfen nicht identisch oder nur linear verteilt sein."
        )