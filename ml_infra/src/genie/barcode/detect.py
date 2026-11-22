"""Barcode localization and bounding box extraction."""
from typing import List, Tuple
import cv2
import numpy as np


class BarcodeDetector:
    """Localizes 1D and 2D code regions using gradient edge density heuristics or YOLO."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path

    def detect_regions(self, image_np: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Returns candidate bounding boxes [x, y, w, h]."""
        if len(image_np.shape) == 3:
            gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_np

        # Scharr gradient in X direction to detect dense vertical barcode stripes
        grad_x = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
        grad_y = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
        gradient = cv2.subtract(grad_x, grad_y)
        gradient = cv2.convertScaleAbs(gradient)

        # Blur and threshold
        blurred = cv2.blur(gradient, (9, 9))
        _, thresh = cv2.threshold(blurred, 225, 255, cv2.THRESH_BINARY)

        # Morphology closure
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        closed = cv2.erode(closed, None, iterations=4)
        closed = cv2.dilate(closed, None, iterations=4)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w > 30 and h > 20:
                boxes.append((x, y, w, h))

        # Always return the full image crop if no distinct barcode region was isolated
        if not boxes:
            h, w = gray.shape[:2]
            boxes.append((0, 0, w, h))

        return boxes
