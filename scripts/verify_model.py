from ultralytics import YOLO
import os
import cv2
import glob

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Root
MODEL_PATH = os.path.join(BASE_DIR, "backend", "data", "models", "trained_yolo_restored.pt")
IMAGE_DIR = os.path.join(BASE_DIR, "backend", "data", "training_dataset", "images", "val")

print(f"Testing model: {MODEL_PATH}")

if not os.path.exists(MODEL_PATH):
    print("❌ Model file not found!")
    exit(1)

model = YOLO(MODEL_PATH)

# Get first image
images = glob.glob(os.path.join(IMAGE_DIR, "*.jpg"))
if not images:
    print("❌ No images found in val set.")
    exit(1)

test_image = images[0]
print(f"Testing on image: {test_image}")

# Run inference
results = model(test_image, conf=0.25)

for r in results:
    print(f"Detections: {len(r.boxes)}")
    for box in r.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        label = model.names[cls_id]
        print(f" - {label}: {conf:.2f}")

if len(results[0].boxes) > 0:
    print("✅ Model is detecting objects!")
else:
    print("⚠️ No objects detected.")
