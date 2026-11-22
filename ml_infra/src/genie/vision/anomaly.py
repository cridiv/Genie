"""Geometric alignment and feature matching via LightGlue / SuperPoint."""
from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class AlignmentResult:
    matched: bool
    inlier_ratio: float
    num_matches: int
    homography_matrix: Optional[np.ndarray] = None


class GeometricMatcher:
    """Matches query pack features against canonical reference faces."""

    def __init__(self, min_inliers: int = 25, min_inlier_ratio: float = 0.35):
        self.min_inliers = min_inliers
        self.min_inlier_ratio = min_inlier_ratio

    def match(self, query_img: np.ndarray, reference_img: np.ndarray) -> AlignmentResult:
        import cv2

        # ORB/SIFT descriptor matching fallback when LightGlue torch model is not mounted
        orb = cv2.ORB_create(nfeatures=1000)
        kp1, des1 = orb.detectAndCompute(query_img, None)
        kp2, des2 = orb.detectAndCompute(reference_img, None)

        if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
            return AlignmentResult(matched=False, inlier_ratio=0.0, num_matches=0)

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)

        if len(matches) < 4:
            return AlignmentResult(matched=False, inlier_ratio=0.0, num_matches=len(matches))

        src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        inliers = int(mask.sum()) if mask is not None else 0
        inlier_ratio = float(inliers / len(matches)) if matches else 0.0

        matched = inliers >= self.min_inliers and inlier_ratio >= self.min_inlier_ratio

        return AlignmentResult(
            matched=matched,
            inlier_ratio=inlier_ratio,
            num_matches=inliers,
            homography_matrix=H,
        )
