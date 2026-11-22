"""Synthetic counterfeit degradation and adversarial packaging defect generator."""
import cv2
import numpy as np


def apply_adversarial_counterfeit_degradations(image: np.ndarray) -> np.ndarray:
    """Applies realistic camera blur, specular glare, and color shift perturbations."""
    # 1. Specular glare simulation
    h, w = image.shape[:2]
    glare = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(glare, (w // 2, h // 2), min(h, w) // 4, 255, -1)
    glare = cv2.GaussianBlur(glare, (55, 55), 0)

    degraded = image.copy()
    if len(degraded.shape) == 3:
        for c in range(3):
            degraded[:, :, c] = np.clip(degraded[:, :, c] + glare * 0.4, 0, 255).astype(np.uint8)

    # 2. Gaussian motion blur
    degraded = cv2.GaussianBlur(degraded, (7, 7), 0)
    return degraded
