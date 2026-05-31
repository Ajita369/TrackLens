from ultralytics import YOLO
import numpy as np
from typing import List, Dict, Any

class PersonDetector:
    def __init__(self, model_path: str = "yolov8s.pt", conf_threshold: float = 0.3):
        # This will auto-download yolov8s.pt on first load if not present
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        
    def process_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Runs YOLOv8 person detection on a BGR frame from OpenCV.
        Returns:
            list of dicts: [{bbox: [x1, y1, x2, y2], confidence: float, class_id: int}]
        """
        # Run inference (disable verbose printouts to keep logs clean)
        results = self.model(frame, verbose=False, conf=self.conf_threshold)[0]
        
        detections = []
        for box in results.boxes:
            class_id = int(box.cls[0].item())
            # We only care about class 0 (person)
            if class_id == 0:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                confidence = float(box.conf[0].item())
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": confidence,
                    "class_id": class_id
                })
                
        return detections
