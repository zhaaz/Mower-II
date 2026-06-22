# Transformation/test_marker_offset_calibration.py

from __future__ import annotations

import numpy as np

from Transformation.marker_offset_calibration import (
    compute_marker_to_reflector_offset,
    format_offset_result,
    make_calibration_sample,
)


def rotation_matrix_z(angle_deg: float) -> np.ndarray:
    angle_rad = np.deg2rad(angle_deg)
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)

    return np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def create_test_samples(
    *,
    true_offset_robot: np.ndarray,
    noise_sigma_mm: float = 0.0,
    rng: np.random.Generator | None = None,
) -> list:
    robot_points = np.array(
        [
            [100.0, 100.0, 0.0],
            [500.0, 120.0, 0.0],
            [700.0, 450.0, 0.0],
            [250.0, 600.0, 0.0],
            [850.0, 750.0, 0.0],
        ],
        dtype=float,
    )

    rotation = rotation_matrix_z(17.0)
    scale = 1.00025
    translation = np.array([3000.0, -1200.0, 800.0], dtype=float)

    samples = []

    for i, robot_marker in enumerate(robot_points, start=1):
        reflector_robot = robot_marker + true_offset_robot

        reflector_lt = translation + scale * (rotation @ reflector_robot)
        marker_lt = translation + scale * (rotation @ robot_marker)

        if noise_sigma_mm > 0.0:
            if rng is None:
                raise ValueError("rng darf bei noise_sigma_mm > 0 nicht None sein.")

            reflector_lt += rng.normal(0.0, noise_sigma_mm, size=3)
            marker_lt += rng.normal(0.0, noise_sigma_mm, size=3)

        samples.append(
            make_calibration_sample(
                label=f"P{i}",
                robot_marker=robot_marker,
                reflector_lt=reflector_lt,
                marker_lt=marker_lt,
            )
        )

    return samples


def test_without_noise() -> None:
    true_offset_robot = np.array([40.0, 0.0, 300.0], dtype=float)

    samples = create_test_samples(
        true_offset_robot=true_offset_robot,
        noise_sigma_mm=0.0,
    )

    result = compute_marker_to_reflector_offset(samples)

    print("=" * 80)
    print("TEST OHNE MESSRAUSCHEN")
    print("=" * 80)
    print(format_offset_result(result))

    print()
    print("Sollwert:")
    print(true_offset_robot)

    print()
    print("Berechneter Mittelwert:")
    print(result.mean_offset_robot)

    error = result.mean_offset_robot - true_offset_robot

    print()
    print("Fehler:")
    print(error)

    if np.allclose(result.mean_offset_robot, true_offset_robot, atol=1e-9):
        print()
        print("OK: Offset wurde korrekt rekonstruiert.")
    else:
        raise AssertionError("FEHLER: Offset stimmt nicht.")


def test_with_noise() -> None:
    rng = np.random.default_rng(42)

    true_offset_robot = np.array([40.0, 0.0, 300.0], dtype=float)
    noise_sigma_mm = 0.2

    samples = create_test_samples(
        true_offset_robot=true_offset_robot,
        noise_sigma_mm=noise_sigma_mm,
        rng=rng,
    )

    result = compute_marker_to_reflector_offset(samples)

    print()
    print("=" * 80)
    print("TEST MIT MESSRAUSCHEN")
    print("=" * 80)
    print(f"Sigma je LT-Koordinate: {noise_sigma_mm:.3f} mm")
    print(format_offset_result(result))

    print()
    print("Sollwert:")
    print(true_offset_robot)

    print()
    print("Berechneter Mittelwert:")
    print(result.mean_offset_robot)

    print()
    print("Fehler Mittelwert:")
    print(result.mean_offset_robot - true_offset_robot)

def test_with_outlier() -> None:
    rng = np.random.default_rng(123)

    true_offset_robot = np.array([40.0, 0.0, 300.0], dtype=float)
    noise_sigma_mm = 0.2

    samples = create_test_samples(
        true_offset_robot=true_offset_robot,
        noise_sigma_mm=noise_sigma_mm,
        rng=rng,
    )

    # --------------------------------------------------
    # Künstlichen Ausreißer erzeugen
    # --------------------------------------------------
    #
    # Simuliert:
    # - CCR nicht exakt auf Markierung
    # - schiefe Schablone
    # - schlechter Messpunkt
    #
    # Wir verfälschen bewusst marker_lt von P3.
    #

    outlier = np.array([2.0, -1.5, 0.8], dtype=float)

    for sample in samples:
        if sample.label == "P3":
            sample.marker_lt += outlier

    result = compute_marker_to_reflector_offset(samples)

    print()
    print("=" * 80)
    print("TEST MIT AUSREISSER")
    print("=" * 80)
    print(f"Normales LT-Rauschen: sigma = {noise_sigma_mm:.3f} mm")
    print(f"Künstlicher Ausreißer auf P3: {outlier}")

    print()
    print(format_offset_result(result))

    print()
    print("Sollwert:")
    print(true_offset_robot)

    print()
    print("Berechneter Mittelwert:")
    print(result.mean_offset_robot)

    print()
    print("Fehler Mittelwert:")
    print(result.mean_offset_robot - true_offset_robot)

    print()
    print(
        "Erwartung: "
        "P3 sollte deutlich höhere Abweichung besitzen "
        "und Max/RMS sichtbar verschlechtern."
    )

def test_wrong_sign() -> None:
    """
    Testet absichtlich die falsche Differenzrichtung.

    Korrekt:
        reflector_lt - marker_lt

    Falsch:
        marker_lt - reflector_lt

    Erwartung:
        Ergebnis sollte ungefähr
            [-40, 0, -300]
        liefern.
    """

    true_offset_robot = np.array([40.0, 0.0, 300.0], dtype=float)

    samples = create_test_samples(
        true_offset_robot=true_offset_robot,
        noise_sigma_mm=0.0,
    )

    # --------------------------------------------------
    # Helmert normal berechnen
    # --------------------------------------------------

    result_correct = compute_marker_to_reflector_offset(samples)

    # --------------------------------------------------
    # Falsches Vorzeichen absichtlich erzeugen
    # --------------------------------------------------

    wrong_offsets = []

    for sample in samples:
        diff_lt_wrong = sample.marker_lt - sample.reflector_lt

        wrong_offset_robot = (
            result_correct.helmert.rotation.T
            @ diff_lt_wrong
        ) / result_correct.helmert.scale

        wrong_offsets.append(wrong_offset_robot)

    wrong_offset_matrix = np.vstack(wrong_offsets)
    wrong_mean = wrong_offset_matrix.mean(axis=0)

    print()
    print("=" * 80)
    print("TEST FALSCHE VORZEICHENRICHTUNG")
    print("=" * 80)

    print()
    print("KORREKT wäre:")
    print(true_offset_robot)

    print()
    print("Berechnet mit ABSICHTLICH falscher Richtung:")
    print(wrong_mean)

    print()
    print("Erwartung:")
    print("ungefähr [-40, 0, -300]")

    if np.allclose(wrong_mean, -true_offset_robot, atol=1e-9):
        print()
        print("OK: Vorzeichen-Test erfolgreich.")
    else:
        raise AssertionError(
            "Vorzeichen-Test fehlgeschlagen."
        )


def main() -> None:
    test_without_noise()
    test_with_noise()
    test_with_outlier()
    test_wrong_sign()


if __name__ == "__main__":
    main()