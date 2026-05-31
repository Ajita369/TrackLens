import cv2
import numpy as np
from typing import List, Dict, Any, Tuple

class StaffDetector:
    def __init__(self):
        # List of uniform color templates (normalized HSV histograms)
        self.uniform_templates = []
        # Store visitor behavioral histories to run staff analysis at clip end:
        # {visitor_id: {"frames": int, "zones": set, "cameras": set, "torso_hists": list}}
        self.visitor_history = {}
        
    def add_visitor_frame(self, visitor_id: str, frame: np.ndarray, bbox: List[float], zone_id: str | None, camera_id: str):
        """
        Record a visitor appearance on a frame, extracting color and spatial info.
        """
        if visitor_id not in self.visitor_history:
            self.visitor_history[visitor_id] = {
                "frames": 0,
                "zones": set(),
                "cameras": set(),
                "torso_hists": []
            }
            
        hist = self._extract_torso_hsv_hist(frame, bbox)
        if hist is not None:
            self.visitor_history[visitor_id]["torso_hists"].append(hist)
            
        self.visitor_history[visitor_id]["frames"] += 1
        self.visitor_history[visitor_id]["cameras"].add(camera_id)
        if zone_id:
            self.visitor_history[visitor_id]["zones"].add(zone_id)

    def _extract_torso_hsv_hist(self, frame: np.ndarray, bbox: List[float]) -> np.ndarray | None:
        """
        Crops torso from frame and computes a normalized 2D HSV histogram.
        """
        h, w, _ = frame.shape
        x1, y1, x2, y2 = bbox
        
        # Clip bbox to frame dimensions
        x1_c = max(0, int(x1))
        y1_c = max(0, int(y1))
        x2_c = min(w, int(x2))
        y2_c = min(h, int(y2))
        
        bw = x2_c - x1_c
        bh = y2_c - y1_c
        
        if bw < 5 or bh < 5:
            return None
            
        # Torso crop
        tx1 = max(0, x1_c + int(bw * 0.25))
        tx2 = min(w, x2_c - int(bw * 0.25))
        ty1 = max(0, y1_c + int(bh * 0.15))
        ty2 = min(h, y1_c + int(bh * 0.55))
        
        torso_crop = frame[ty1:ty2, tx1:tx2]
        if torso_crop.size == 0:
            return None
            
        hsv = cv2.cvtColor(torso_crop, cv2.COLOR_BGR2HSV)
        # Use H (Hue) and S (Saturation) channels
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    def calibrate_uniform_templates(self, total_frames: int):
        """
        Calibrate uniform templates from the visitor history.
        Identify tracks that are present in a significant percentage of frames (>60% of total_frames)
        as likely store staff and use their average torso color as the uniform template.
        """
        if total_frames <= 0:
            return
            
        for vid, history in self.visitor_history.items():
            presence_ratio = history["frames"] / total_frames
            # If present in > 60% of the clip duration, they are likely staff
            if presence_ratio > 0.60 and len(history["torso_hists"]) > 0:
                # Compute average histogram
                avg_hist = np.mean(history["torso_hists"], axis=0)
                cv2.normalize(avg_hist, avg_hist, 0, 1, cv2.NORM_MINMAX)
                self.uniform_templates.append(avg_hist)
                print(f"Calibrated staff uniform template from visitor {vid} (presence {presence_ratio:.1%})")
                
    def check_is_staff(self, visitor_id: str, total_frames: int) -> Tuple[bool, float]:
        """
        Evaluates the three staff exclusion signals for a visitor ID.
        Returns:
            (is_staff, staff_confidence)
        """
        if visitor_id not in self.visitor_history or total_frames <= 0:
            return False, 0.0
            
        history = self.visitor_history[visitor_id]
        
        # Signal 1:Torso color matches uniform template
        color_match = False
        max_corr = 0.0
        if len(history["torso_hists"]) > 0 and len(self.uniform_templates) > 0:
            avg_hist = np.mean(history["torso_hists"], axis=0)
            cv2.normalize(avg_hist, avg_hist, 0, 1, cv2.NORM_MINMAX)
            
            for template in self.uniform_templates:
                corr = cv2.compareHist(avg_hist, template, cv2.HISTCMP_CORREL)
                if corr > max_corr:
                    max_corr = corr
            if max_corr > 0.75:
                color_match = True
                
        # Signal 2:Presence duration ratio in clip
        presence_ratio = history["frames"] / total_frames
        long_presence = presence_ratio > 0.60
        
        # Signal 3: visits 3+ distinct zones (staff roam, customers usually visit 1 or 2)
        multi_zone = len(history["zones"]) >= 3
        
        # Exclude visitor as staff if:
        # 1. Color matches calibrated uniform template with high confidence
        # 2. Or, they have long presence AND roam through multiple zones
        is_staff = color_match or (long_presence and multi_zone)
        
        # Confidence calculation
        confidence = 0.0
        if is_staff:
            if color_match:
                confidence = max(0.8, max_corr)
            else:
                confidence = min(0.9, presence_ratio)
        else:
            if max_corr > 0.5:
                confidence = 1.0 - max_corr  # How confident we are they are NOT staff
            else:
                confidence = 0.95
                
        return is_staff, float(confidence)
