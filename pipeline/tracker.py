import numpy as np
import cv2
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as T
from PIL import Image
import supervision as sv
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone

class ReIDMatcher:
    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold
        # Stores exited visitor info: {visitor_id: {"embedding": np.ndarray, "exit_time": float}}
        self.exited_visitors = {}
        
    def add_exited(self, visitor_id: str, embedding: np.ndarray, exit_timestamp: float):
        self.exited_visitors[visitor_id] = {
            "embedding": embedding,
            "exit_time": exit_timestamp
        }
        
    def match(self, new_embedding: np.ndarray, current_timestamp: float) -> Optional[str]:
        # 1. Clean up old entries (TTL of 2 hours in video time = 7200 seconds)
        expired = [vid for vid, info in self.exited_visitors.items() 
                   if current_timestamp - info["exit_time"] > 7200.0]
        for vid in expired:
            del self.exited_visitors[vid]
            
        # 2. Find closest match using cosine similarity
        best_match = None
        best_sim = -1.0
        
        for vid, info in self.exited_visitors.items():
            stored_emb = info["embedding"]
            # Cosine similarity
            sim = np.dot(new_embedding, stored_emb) / (np.linalg.norm(new_embedding) * np.linalg.norm(stored_emb) + 1e-8)
            if sim > best_sim:
                best_sim = sim
                best_match = vid
                
        if best_sim >= self.similarity_threshold:
            return best_match
        return None

class TrackerManager:
    def __init__(self, store_id: str):
        self.store_id = store_id
        # Deprecated warnings suppressed inside supervision, but it works
        self.tracker = sv.ByteTrack()
        self.visitor_seq = 0
        
        # Track active visitor mapping: {tracker_id: visitor_id}
        self.active_tracks = {}
        # Track historical centers to check entry threshold crossing: {tracker_id: [centers]}
        self.track_history = {}
        
        # Re-ID Matcher instance
        self.reid_matcher = ReIDMatcher(similarity_threshold=0.75)
        
        # Load embedding extractor model (ResNet18 as 512-dim vector extractor)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.embedder = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        self.embedder.fc = nn.Identity()
        self.embedder.to(self.device)
        self.embedder.eval()
        
        # Preprocessing transforms for torso crop
        self.transform = T.Compose([
            T.Resize((256, 128)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
    def _generate_new_visitor_id(self, date_str: str) -> str:
        self.visitor_seq += 1
        return f"VIS_{self.store_id}_{date_str}_{self.visitor_seq:04d}"
        
    def _extract_embedding(self, frame: np.ndarray, bbox: List[float]) -> np.ndarray:
        """
        Crops the torso from the bounding box and extracts a 512-dim feature embedding.
        """
        h, w, _ = frame.shape
        x1, y1, x2, y2 = bbox
        
        # Clip coordinates to frame boundary
        x1_c = max(0, int(x1))
        y1_c = max(0, int(y1))
        x2_c = min(w, int(x2))
        y2_c = min(h, int(y2))
        
        # Focus on torso: center-third width, upper middle height
        bw = x2_c - x1_c
        bh = y2_c - y1_c
        
        tx1 = max(0, x1_c + int(bw * 0.25))
        tx2 = min(w, x2_c - int(bw * 0.25))
        ty1 = max(0, y1_c + int(bh * 0.15))
        ty2 = min(h, y1_c + int(bh * 0.65))
        
        torso_crop = frame[ty1:ty2, tx1:tx2]
        if torso_crop.size == 0:
            # Fallback to full bbox if crop is empty
            torso_crop = frame[y1_c:y2_c, x1_c:x2_c]
            if torso_crop.size == 0:
                return np.zeros(512, dtype=np.float32)
                
        # Convert BGR (OpenCV) to RGB (PIL)
        torso_rgb = cv2.cvtColor(torso_crop, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(torso_rgb)
        
        # Extract features without gradients
        with torch.no_grad():
            img_t = self.transform(pil_img).unsqueeze(0).to(self.device)
            emb = self.embedder(img_t).squeeze(0).cpu().numpy()
            
        return emb

    def update(
        self, 
        detections: List[Dict[str, Any]], 
        frame: np.ndarray, 
        camera_id: str, 
        zone_classifier: Any, 
        entry_threshold: Any,
        timestamp_sec: float,
        date_str: str
    ) -> List[Dict[str, Any]]:
        """
        Updates tracking state with new frame detections.
        Returns:
            list of dicts representing tracking updates
        """
        if not detections:
            # ByteTrack update expects empty list inputs to continue tracking
            xyxy = np.empty((0, 4))
            confidence = np.empty((0,))
            class_id = np.empty((0,), dtype=int)
        else:
            xyxy = np.array([d["bbox"] for d in detections])
            confidence = np.array([d["confidence"] for d in detections])
            class_id = np.array([d["class_id"] for d in detections])
            
        sv_dets = sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_id
        )
        
        # Track detections
        tracked_dets = self.tracker.update_with_detections(sv_dets)
        
        updates = []
        current_tracker_ids = set()
        
        # Iterate over tracked items
        for i in range(len(tracked_dets)):
            bbox = tracked_dets.xyxy[i].tolist()
            tracker_id = int(tracked_dets.tracker_id[i])
            conf = float(tracked_dets.confidence[i])
            current_tracker_ids.add(tracker_id)
            
            # Compute center point
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            center = (cx, cy)
            
            # 1. Update history
            if tracker_id not in self.track_history:
                self.track_history[tracker_id] = []
            self.track_history[tracker_id].append(center)
            
            # Keep only the last 30 frames of history to avoid memory bloat
            if len(self.track_history[tracker_id]) > 30:
                self.track_history[tracker_id].pop(0)
                
            is_new = tracker_id not in self.active_tracks
            visitor_id = None
            crossed_event = None
            
            # 2. Handle Entry Camera Crossing (CAM 3)
            if camera_id == "CAM 3" and entry_threshold:
                if len(self.track_history[tracker_id]) >= 2:
                    prev_center = self.track_history[tracker_id][-2]
                    crossed_event = entry_threshold.check_crossing(prev_center, center)
                    
                if is_new:
                    # By default assign a temporary visitor ID until crossing is determined
                    # Or assign immediately if they start inside/outside
                    visitor_id = self._generate_new_visitor_id(date_str)
                    self.active_tracks[tracker_id] = visitor_id
                else:
                    visitor_id = self.active_tracks[tracker_id]
            else:
                # Floor/Billing counter cameras: assign visitor ID via cross-camera Re-ID match
                if is_new:
                    # Match this new appearance against all exiting/active tracks
                    new_emb = self._extract_embedding(frame, bbox)
                    matched_id = self.reid_matcher.match(new_emb, timestamp_sec)
                    if matched_id:
                        visitor_id = matched_id
                    else:
                        # Fallback: create a new visitor ID if we couldn't match
                        visitor_id = self._generate_new_visitor_id(date_str)
                    self.active_tracks[tracker_id] = visitor_id
                else:
                    visitor_id = self.active_tracks[tracker_id]
                    
            # 3. Handle Zone Classification
            zone_id, sku_zone = None, None
            if zone_classifier:
                zone_id, sku_zone = zone_classifier.classify(cx, cy)
                
            updates.append({
                "tracker_id": tracker_id,
                "visitor_id": visitor_id,
                "bbox": bbox,
                "center": center,
                "zone_id": zone_id,
                "sku_zone": sku_zone,
                "confidence": conf,
                "is_new": is_new,
                "crossed_event": crossed_event,
                "frame_embedding_fn": lambda b=bbox: self._extract_embedding(frame, b)
            })
            
        # Identify lost tracks and move them to Re-ID pool
        lost_tracker_ids = set(self.active_tracks.keys()) - current_tracker_ids
        for lid in lost_tracker_ids:
            vid = self.active_tracks[lid]
            # Clean history and active status
            if lid in self.track_history:
                del self.track_history[lid]
            del self.active_tracks[lid]
            
        return updates
