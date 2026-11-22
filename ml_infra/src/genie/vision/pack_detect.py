"""Packaging face localization and perspective homography rectification."""
from typing import Optional, Tuple
import cv2
import numpy as np


class PackDetectorRectifier:
    """Localizes packaging face and corrects perspective to a standard canonical planar view."""

    def __init__(self, target_size: Tuple[int, int] = (512, 512)):
        self.target_size = target_size

    def rectify(self, image_np: np.ndarray) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Locates the primary quadrilateral and unwarps it into a planar front-facing image.
        Returns (rectified_image, 3x3 homography_matrix).
        """
        if len(image_np.shape) == 3:
            gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_np

        # Edge detection & contour extraction
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)

        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        screen_cnt = None
        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4:
                screen_cnt = approx
                break

        if screen_cnt is not None:
            pts = screen_cnt.reshape(4, 2)
            rect = self._order_points(pts)
            dst = np.array([
                [0, 0],
                [self.target_size[0] - 1, 0],
                [self.target_size[0] - 1, self.target_size[1] - 1],
                [0, self.target_size[1] - 1],
            ], dtype="float32")

            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(image_np, M, self.target_size)
            return warped, M

        # Fallback: simple center crop / resize
        h, w = image_np.shape[:2]
        crop_dim = min(h, w)
        start_y = (h - crop_dim) // 2
        start_x = (w - crop_dim) // 2
        cropped = image_np[start_y : start_y + crop_dim, start_x : start_x + crop_dim]
        resized = cv2.resize(cropped, self.target_size, interpolation=cv2.INTER_AREA)
        return resized, None

    @staticmethod
    def _order_points(pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect
