import cv2
import os

clips_dir = "data/clips"
output_dir = "data/frames"
os.makedirs(output_dir, exist_ok=True)

for f in sorted(os.listdir(clips_dir)):
    if f.endswith(".mp4"):
        path = os.path.join(clips_dir, f)
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print(f"Failed to open {f}")
            continue
        ret, frame = cap.read()
        if ret:
            out_path = os.path.join(output_dir, f.replace(".mp4", ".png"))
            cv2.imwrite(out_path, frame)
            print(f"Saved first frame of {f} to {out_path}")
        cap.release()
