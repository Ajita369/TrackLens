import cv2
import numpy as np
import json
import os

class ZoneClassifier:
    def __init__(self, store_id: str, camera_id: str):
        self.store_id = store_id
        self.camera_id = camera_id
        self.zones = {}
        self.sku_zones = {}
        
        # Hardcoded polygon coordinates (in 1920x1080 space) for Brigade Road store (ST1008)
        # derived from visual analysis of the camera frame views.
        if camera_id == "CAM 1":
            # CAM 1 covers the rear wall shelves (The Face Shop, Good Vibes, Minimalist, etc.)
            self.zones = {
                "The Face Shop": np.array([[380, 200], [700, 200], [700, 600], [380, 600]], dtype=np.int32),
                "Good Vibes": np.array([[720, 200], [1050, 200], [1050, 600], [720, 600]], dtype=np.int32),
                "Minimalist": np.array([[1070, 200], [1400, 200], [1400, 600], [1070, 600]], dtype=np.int32)
            }
            self.sku_zones = {
                "The Face Shop": "skin",
                "Good Vibes": "skin",
                "Minimalist": "skin"
            }
        elif camera_id == "CAM 2":
            # CAM 2 covers the makeup side wall shelves (Maybelline, Faces Canada, Lakme, etc.)
            self.zones = {
                "Maybelline": np.array([[1400, 300], [1920, 300], [1920, 900], [1400, 900]], dtype=np.int32),
                "Faces Canada": np.array([[1050, 300], [1380, 300], [1380, 900], [1050, 900]], dtype=np.int32),
                "Lakme": np.array([[700, 300], [1020, 300], [1020, 900], [700, 900]], dtype=np.int32)
            }
            self.sku_zones = {
                "Maybelline": "makeup",
                "Faces Canada": "makeup",
                "Lakme": "makeup"
            }
        elif camera_id == "CAM 5":
            # CAM 5 covers the Cash Counter (billing area)
            self.zones = {
                "Cash Counter": np.array([[100, 300], [600, 300], [600, 1080], [100, 1080]], dtype=np.int32)
            }
            self.sku_zones = {
                "Cash Counter": "billing"
            }
            
    def classify(self, center_x: float, center_y: float) -> tuple[str | None, str | None]:
        """
        Returns (zone_id, sku_zone) if point is inside any zone polygon, else (None, None).
        """
        pt = (float(center_x), float(center_y))
        for zone_name, poly in self.zones.items():
            # pointPolygonTest returns >= 0 if inside or on edge
            dist = cv2.pointPolygonTest(poly, pt, False)
            if dist >= 0:
                return zone_name, self.sku_zones.get(zone_name)
        return None, None

class EntryThreshold:
    def __init__(self, line_x: float = 1400.0):
        """
        Entrance is on CAM 3. The door is on the right side.
        A vertical line at x = line_x divides inside (left, x < line_x) and outside (right, x > line_x).
        """
        self.line_x = line_x
        
    def check_crossing(self, prev_center: tuple[float, float], curr_center: tuple[float, float]) -> str | None:
        """
        Checks if a tracked center point crossed the line.
        Returns:
            "ENTRY" if crossing from right to left (outside to inside)
            "EXIT" if crossing from left to right (inside to outside)
            None if no crossing
        """
        prev_x, _ = prev_center
        curr_x, _ = curr_center
        
        # Crossed from right to left
        if prev_x >= self.line_x and curr_x < self.line_x:
            return "ENTRY"
            
        # Crossed from left to right
        if prev_x <= self.line_x and curr_x > self.line_x:
            return "EXIT"
            
        return None
