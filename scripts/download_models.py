from ultralytics import YOLO
import os
import shutil

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Root
MODELS_DIR = os.path.join(BASE_DIR, "backend", "data", "models")

print(f"Target Models Directory: {MODELS_DIR}")
os.makedirs(MODELS_DIR, exist_ok=True)

# 1. Download Standard Detection Models
detection_models = ["yolo12s.pt", "yolo12m.pt", "yolov8m-seg.pt", "rdd_model.pt"]

for m in detection_models:
    target_path = os.path.join(MODELS_DIR, m)
    if os.path.exists(target_path):
        print(f"✅ {m} already exists.")
        continue
        
    print(f"⬇️ Downloading {m}...")
    try:
        # Load (downloads if missing)
        model = YOLO(m)
        # Move if it downloaded to CWD
        if os.path.exists(m):
            shutil.move(m, target_path)
            print(f"✅ Downloaded and moved {m}")
        elif os.path.exists(target_path):
             print(f"✅ {m} is ready.")
        else:
             print(f"⚠️ {m} initialized but file not found.")
    except Exception as e:
        print(f"❌ Failed to download {m}: {e}")

# 2. Build Experimental v12 Segmentation Models
# (Hybrid: Config + Detection Weights)
seg_models = [
    {"name": "yolo12s-seg.pt", "yaml": "yolo12s-seg.yaml", "weights": "yolo12s.pt"},
    {"name": "yolo12m-seg.pt", "yaml": "yolo12m-seg.yaml", "weights": "yolo12m.pt"},
]

for seg in seg_models:
    target_path = os.path.join(MODELS_DIR, seg["name"])
    if os.path.exists(target_path):
        print(f"✅ {seg['name']} already exists.")
        continue

    print(f"🛠️ Building {seg['name']} (Hybrid)...")
    weights_path = os.path.join(MODELS_DIR, seg["weights"])
    
    if not os.path.exists(weights_path):
        print(f"❌ Cannot build {seg['name']}: Missing weights {weights_path}")
        continue
        
    try:
        # Initialize from YAML
        print(f"   Init from {seg['yaml']}...")
        model = YOLO(seg["yaml"])
        
        # Load compatible weights
        print(f"   Loading weights from {seg['weights']}...")
        model.load(weights_path)
        
        # Save to target
        print(f"   Saving to {target_path}...")
        model.save(target_path)
        print(f"✅ Built {seg['name']} successfully!")
        
    except Exception as e:
        print(f"❌ Failed to build {seg['name']}: {e}")

print("\n✨ Model setup complete!")
