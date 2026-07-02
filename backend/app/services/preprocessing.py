import os
import cv2
import numpy as np
from ultralytics import YOLO, FastSAM
from app.core.settings_manager import settings_manager

class RoadPreprocessor:
    """
    Preprocesses images for road quality analysis by:
    1. Applying a geometric ROI (Region of Interest) to remove sky/horizon.
    2. Using a YOLO segmentation model to mask out dynamic objects (cars, people, etc.) that obstruct the road.
    3. Using FastSAM for intelligent road segmentation.
    """
    
    # COCO Classes to mask out (obstructions)
    # 0: person, 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck
    OBSTRUCTION_CLASSES = [0, 1, 2, 3, 5, 7]

    def __init__(self, model_name="yolov8n-seg.pt"):
        self.model_name = model_name
        self.model = None
        self.fastsam = None

    def _load_model(self):
        if self.model is None:
            print(f"RoadPreprocessor: Loading {self.model_name}...")
            self.model = YOLO(self.model_name)

    def _load_fastsam(self):
        if self.fastsam is None:
            print("RoadPreprocessor: Loading FastSAM-s.pt...")
            # Automatically downloads if not present
            self.fastsam = FastSAM('FastSAM-s.pt')

    def process_and_save(self, src_path: str, dst_path: str, options: dict = None):
        """
        Reads image from src_path, applies masking based on options, and saves to dst_path.
        Options:
            - use_roi (bool): Apply geometric crop
            - smart_roi (bool): Apply FastSAM AI road detection
            - use_mask (bool): Apply YOLO obstruction masking
            - remove_shadows_1 (bool): MSR
            - remove_shadows_2 (bool): CLAHE
        """
        self._load_model()
        
        if options is None:
            options = {"use_roi": True, "smart_roi": False, "use_mask": True, "remove_shadows_1": False}
        
        # Read Image
        img = cv2.imread(src_path)
        if img is None:
            raise ValueError(f"Could not read image: {src_path}")
            
        h, w = img.shape[:2]

        # Initialize mask (255 = Keep)
        final_mask = np.ones((h, w), dtype=np.uint8) * 255

        # 1. Geometric ROI (Fixed Trapezoid)
        if options.get("use_roi", True):
            roi_mask = np.zeros((h, w), dtype=np.uint8)
            # Default Trapezoid
            mask_poly = np.array([
                [w * 0, h],            # Bottom-left
                [w * 1, h],            # Bottom-right
                [w * 0.8, h * 0.45],   # Top-right
                [w * 0.2, h * 0.45]    # Top-left
            ], dtype=np.int32)
            cv2.fillPoly(roi_mask, [mask_poly], 255)
            final_mask = cv2.bitwise_and(final_mask, roi_mask)

        # 1.5 Smart ROI (FastSAM AI Road Detection)
        # Segments the road specifically using a bottom-center point prompt semantics
        if options.get("smart_roi", False):
            self._load_fastsam()
            
            # Run FastSAM
            # Retina_masks=True gives better quality borders
            # Lower confidence (0.15) to ensure we catch the road segment even if texture is uniform/bland
            results = self.fastsam(img, device='cpu', retina_masks=True, imgsz=1024, conf=0.15, iou=0.9, verbose=False)
            
            road_mask = np.zeros((h, w), dtype=np.uint8)
            found_road = False
            
            if results and results[0].masks:
                # Get all masks
                masks_data = results[0].masks.data # GPU/CPU tensor
                if masks_data is not None:
                    # Convert to numpy (N, H, W)
                    masks_np = masks_data.cpu().numpy()
                    
                    masks_np = masks_data.cpu().numpy()
                    
                    # Multi-point PROMPT Strategy
                    # We try multiple points to ensure we hit the road surface:
                    # 1. Bottom Center (Standard)
                    # 2. Left and Right (In case of lane markings or damage in center)
                    # 3. Slightly higher up (In case of car hood at bottom)
                    
                    seed_points = [
                        (int(h * 0.85), w // 2),      # Bottom Center
                        (int(h * 0.85), w // 4),      # Bottom Left
                        (int(h * 0.85), 3 * w // 4),  # Bottom Right
                        (int(h * 0.70), w // 2),      # Mid-Lower Center
                    ]
                    
                    print(f"RoadPreprocessor: FastSAM Prompting with points: {seed_points} for image {w}x{h}")

                    for (py, px) in seed_points:
                        # Define patch bounds (5px radius)
                        y1, y2 = max(0, py - 5), min(h, py + 5)
                        x1, x2 = max(0, px - 5), min(w, px + 5)
                        
                        for m in masks_np:
                            # Resize mask to original image size if needed
                            if m.shape[0] != h or m.shape[1] != w:
                                m_resized = cv2.resize(m, (w, h))
                            else:
                                m_resized = m
                            
                            # Check patch intersection
                            patch = m_resized[y1:y2, x1:x2]
                            if np.any(patch > 0.5):
                                found_road = True
                                # Add to road mask
                                road_mask = cv2.bitwise_or(road_mask, (m_resized > 0.5).astype(np.uint8) * 255)
            
            if found_road:
                # Validation: Check if the mask is large enough to be a road
                total_pixels = h * w
                mask_pixels = cv2.countNonZero(road_mask)
                road_ratio = mask_pixels / total_pixels
                
                if road_ratio < 0.05: # Less than 5% of image
                    print(f"RoadPreprocessor: Smart ROI mask too small ({road_ratio:.2%}). Likely just a line or artifact. Rejected.")
                    found_road = False # Will trigger fallback below
            
            # Apply mask if road found and validated
            if found_road:
                # Post-process: Fill small holes (lane markings might be holes)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
                road_mask = cv2.morphologyEx(road_mask, cv2.MORPH_CLOSE, kernel)
                final_mask = cv2.bitwise_and(final_mask, road_mask)
            else:
                # Fallback Strategy:
                # If AI fails to find road at seed (e.g. glare, occlusion) OR validation failed,
                # do NOT black out the image. Fallback to Geometric ROI.
                print(f"RoadPreprocessor: FastSAM failed or rejected. Falling back to Geometric ROI.")
                
                # Create default trapezoid fallback
                fallback_mask = np.zeros((h, w), dtype=np.uint8)
                mask_poly = np.array([
                    [w * 0, h],            # Bottom-left
                    [w * 1, h],            # Bottom-right
                    [w * 0.8, h * 0.45],   # Top-right
                    [w * 0.2, h * 0.45]    # Top-left
                ], dtype=np.int32)
                cv2.fillPoly(fallback_mask, [mask_poly], 255)
                
                final_mask = cv2.bitwise_and(final_mask, fallback_mask)

        # 2. YOLO Segmentation for Obstructions (Mask ALL objects)
        if options.get("use_mask", True):
            # No classes filter -> detects EVERYTHING the model knows (COCO - 80 classes)
            results = self.model(img, verbose=False) 
            obstruction_mask = np.zeros((h, w), dtype=np.uint8)
            
            for result in results:
                if result.masks:
                    for mask_obj in result.masks.data:
                        m = mask_obj.cpu().numpy()
                        m = cv2.resize(m, (w, h))
                        obstruction_mask = cv2.bitwise_or(obstruction_mask, (m > 0.5).astype(np.uint8) * 255)
            
            # Invert: 255 -> Keep, 0 -> Remove
            inv_obstruction = cv2.bitwise_not(obstruction_mask)
            final_mask = cv2.bitwise_and(final_mask, inv_obstruction)

        # 3. Apply Mask
        # Create black background (or maybe gray for visibility?)
        processed_img = cv2.bitwise_and(img, img, mask=final_mask)
        
        # 4. Shadow Removal Actions

        # Method 1: Multi-Scale Retinex (MSR)
        # Combines multiple scales of dynamic range compression.
        # Good for seeing details in both bright and dark areas.
        if options.get("remove_shadows_1", False):
            img_f = processed_img.astype(float) + 1.0
            log_img = np.log(img_f)
            
            # 3 Scales (Fine, Medium, Coarse)
            scales = [15, 80, 250]
            retinex_sum = np.zeros_like(log_img)
            
            for sigma in scales:
                # Gaussian Blur for illumination estimation
                blur = cv2.GaussianBlur(img_f, (0, 0), sigma)
                log_blur = np.log(blur)
                retinex_sum += (log_img - log_blur)
            
            # Average
            retinex = retinex_sum / 3.0
            
            # Restoration / Normalization
            # Simple normalization to 0-255
            # We use a robust normalization (cutting off outliers)
            mean = np.mean(retinex)
            std = np.std(retinex)
            min_val = mean - 2.0 * std
            max_val = mean + 2.0 * std
            
            retinex_norm = (retinex - min_val) / (max_val - min_val) * 255.0
            retinex_norm = np.clip(retinex_norm, 0, 255).astype(np.uint8)
            processed_img = retinex_norm

        # Method 2: CLAHE (Contrast Limited Adaptive Histogram Equalization)
        # Applied to Luminance channel of LAB color space.
        # This is the "Industrial Standard" for local contrast enhancement.
        if options.get("remove_shadows_2", False):
            lab = cv2.cvtColor(processed_img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # ClipLimit 2.0 is usually safe, GridSize 8x8 is standard
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            
            # Merge back
            limg = cv2.merge((cl, a, b))
            processed_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

        # Save
        cv2.imwrite(dst_path, processed_img)

# Singleton
road_preprocessor = RoadPreprocessor()
