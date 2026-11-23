"""Image enhancement algorithms for degraded or low-resolution barcodes."""
import cv2
import numpy as np


def enhance_barcode_crop(image: np.ndarray) -> list[np.ndarray]:
    """Generates a progression of enhanced variants to maximize decode rate."""
    variants = [image]

    # 1. Grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    variants.append(gray)

    # 2. CLAHE (Contrast-Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    variants.append(enhanced)

    # 3. Otsu binarization
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(thresh)

    # 4. Upscaled 2x with bicubic interpolation
    h, w = gray.shape[:2]
    if w < 200 or h < 200:
        upscaled = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        variants.append(upscaled)

    return variants
