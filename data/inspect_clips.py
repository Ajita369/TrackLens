import cv2
import os

clips_dir = "data/clips"
for f in sorted(os.listdir(clips_dir)):
    if f.endswith(".mp4"):
        path = os.path.join(clips_dir, f)
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print(f"Failed to open {f}")
            continue
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration_sec = count / fps if fps > 0 else 0
        print(f"{f}: {width}x{height}, {count} frames, {fps:.2f} fps, duration: {duration_sec:.2f} sec")
        cap.release()
