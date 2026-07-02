"""
Local training provider - runs YOLO training on local machine.
"""
import os
from datetime import datetime
from typing import Dict, Any

import torch
from ultralytics import YOLO

from .base import BaseTrainingProvider, TrainingConfig


class LocalTrainingProvider(BaseTrainingProvider):
    """Executes training locally using available hardware (CPU/MPS/CUDA)."""
    
    def __init__(self):
        self._device = self._detect_device()
    
    def _detect_device(self) -> str:
        """Detect best available device for training."""
        if torch.backends.mps.is_available():
            return 'mps'
        elif torch.cuda.is_available():
            return '0'  # First CUDA device
        return 'cpu'
    
    def get_provider_name(self) -> str:
        return "Lokális Tanítás"
    
    def is_available(self) -> bool:
        return True  # Always available
    
    def run(self, config: TrainingConfig) -> Dict[str, Any]:
        """
        Execute local training (YOLO or DINO) with progress callbacks.
        """
        # Handle DINO training
        if config.model_type == "DINO":
            return self._run_dino_training(config)

        # Handle YOLO training
        device = config.device or self._device
        
        # Log device info
        device_name = {
            'mps': 'Apple MPS (Metal Performance Shaders) 🚀',
            'cpu': 'CPU',
            '0': 'CUDA GPU'
        }.get(device, device)
        
        print(f"DEBUG: LocalTrainingProvider using device: {device_name}")
        
        # Load model
        model = self._load_model(config)
        
        # Setup progress callbacks
        self._setup_callbacks(model, config)
        
        # Run training
        try:
            results = model.train(
                data=config.data_yaml_path,
                epochs=config.epochs,
                imgsz=640,
                batch=config.batch_size,
                patience=config.patience,
                workers=config.workers,
                project=config.output_dir,
                name="smooth_route_train",
                exist_ok=True,
                verbose=True,
                device=device,
                cache=True,  # Cache images for speed
            )
            
            # Save model
            best_model_path = self._save_trained_model(config)
            
            return {
                "success": True,
                "model_path": best_model_path,
                "message": "Tanítás sikeresen befejeződött!",
                "metrics": self._extract_metrics(results),
            }
            
        except Exception as e:
            print(f"ERROR: Training failed: {e}")
            return {
                "success": False,
                "model_path": None,
                "message": f"Tanítási hiba: {str(e)}",
                "metrics": {},
            }
    
    def _run_dino_training(self, config: TrainingConfig) -> Dict[str, Any]:
        """Execute local DINO classification head training."""
        print("DEBUG: Starting local DINO training...")
        try:
            # Import dynamically to avoid circular dependencies
            import sys
            import os
            
            # Ensure backend dir is in path
            # base_dir is project/backend
            sys.path.append(config.base_dir)
            
            from train_dino_head import train
            
            # Define output path
            timestamp = datetime.now().strftime("%Y%m%d")
            # Using vits14 as suffix for now, maybe in future dynamic based on config
            target_name = f"dino_rqi_head_vits14_{timestamp}.pt"
            output_path = os.path.join(config.base_dir, "data", "models", target_name)
            
            # Wrapper for progress updates?
            # train_dino_head currently doesn't support callbacks, 
            # so we just run it and assume it logs enough or finishes fast.
            # TODO: Add callback support to train_dino_head.py
            
            if config.progress_callback:
                config.progress_callback(50, "DINO Head tanítása folyamatban...")
            
            # config.data_yaml_path is actually the DIR path for DINO
            train(
                config.data_yaml_path,
                output_path,
                epochs=config.epochs,
                batch_size=config.batch_size,
                num_workers=0, # Force main process to avoid "daemonic processes are not allowed to have children"
                progress_callback=config.progress_callback
            )
            
            if config.progress_callback:
                config.progress_callback(100, "Tanítás kész!")
                
            return {
                "success": True,
                "model_path": output_path,
                "message": "DINO Tanítás sikeresen befejeződött!",
                "metrics": {},
            }
            
        except Exception as e:
            print(f"ERROR: DINO Training failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "model_path": None,
                "message": f"DINO Tanítási hiba: {str(e)}",
                "metrics": {},
            }
    
    def _load_model(self, config: TrainingConfig) -> YOLO:
        """Load YOLO model from config."""
        model_path = config.model_name
        
        # Check if model exists in models directory
        candidate_path = os.path.join(config.base_dir, "data", "models", model_path)
        if os.path.exists(candidate_path):
            model_path = candidate_path
        
        # Special handling for YOLOv12 segmentation
        if "yolo12" in model_path and "-seg" in model_path and not os.path.exists(model_path):
            return self._init_yolo12_seg(config, model_path)
        
        print(f"DEBUG: Loading model: {model_path}")
        return YOLO(model_path)
    
    def _init_yolo12_seg(self, config: TrainingConfig, model_path: str) -> YOLO:
        """Initialize YOLOv12 segmentation from YAML + detection weights."""
        base_name = model_path.replace(".pt", "")
        yaml_file = f"{base_name}.yaml"
        detection_weights = base_name.replace("-seg", "") + ".pt"
        detection_weights_path = os.path.join(config.base_dir, "data", "models", detection_weights)
        
        print(f"DEBUG: Initializing YOLOv12 seg from {yaml_file}")
        model = YOLO(yaml_file)
        
        if os.path.exists(detection_weights_path):
            print(f"DEBUG: Transferring weights from {detection_weights_path}")
            model.load(detection_weights_path)
        
        return model
    
    def _setup_callbacks(self, model: YOLO, config: TrainingConfig):
        """Setup epoch and batch level progress callbacks."""
        
        # Track batch progress for throttling
        last_batch_update = {"value": 0}
        
        def on_train_epoch_end(trainer):
            """Called at end of each epoch."""
            current_epoch = trainer.epoch + 1
            total_epochs = trainer.epochs
            
            # Progress: map epochs to 20-90% range
            progress = 20 + int((current_epoch / total_epochs) * 70)
            
            # Extract loss metrics
            loss_str = self._format_losses(trainer)
            
            msg = f"Epoch {current_epoch}/{total_epochs}"
            if loss_str:
                msg += f" | {loss_str}"
            
            print(f"DEBUG: {msg}")
            if config.progress_callback:
                config.progress_callback(progress, msg)
        
        def on_train_batch_end(trainer):
            """Called at end of each batch - throttled updates."""
            if not hasattr(trainer, 'batch_i') or trainer.epochs is None:
                return
            
            current_batch = trainer.batch_i + 1
            total_batches = len(trainer.train_loader)
            current_epoch = trainer.epoch + 1
            total_epochs = trainer.epochs
            
            # Calculate overall progress
            epoch_fraction = (current_epoch - 1 + current_batch / total_batches) / total_epochs
            progress = 20 + int(epoch_fraction * 70)
            
            # Throttle: only update every 10% within an epoch
            update_threshold = max(1, total_batches // 10)
            if current_batch % update_threshold != 0 and current_batch != total_batches:
                return
            
            # Avoid duplicate updates
            if progress <= last_batch_update["value"]:
                return
            last_batch_update["value"] = progress
            
            msg = f"Epoch {current_epoch}/{total_epochs} - Batch {current_batch}/{total_batches}"
            
            if config.progress_callback:
                config.progress_callback(progress, msg)
        
        model.add_callback("on_train_epoch_end", on_train_epoch_end)
        model.add_callback("on_train_batch_end", on_train_batch_end)
    
    def _format_losses(self, trainer) -> str:
        """Format loss values from trainer."""
        if not hasattr(trainer, 'loss_names') or not trainer.loss_names:
            return ""
        
        items = []
        for i, name in enumerate(trainer.loss_names):
            if i < len(trainer.tloss):
                val = trainer.tloss[i].item()
                items.append(f"{name}: {val:.3f}")
        
        return " | ".join(items)
    
    def _save_trained_model(self, config: TrainingConfig) -> str:
        """Save the trained model with timestamp."""
        best_model_src = os.path.join(
            config.output_dir, "smooth_route_train", "weights", "best.pt"
        )
        
        if not os.path.exists(best_model_src):
            print(f"WARNING: Best model not found at {best_model_src}")
            return ""
        
        # Save with timestamp
        timestamp = datetime.now().strftime("%Y%m%d")
        target_name = f"model_{timestamp}.pt"
        target_path = os.path.join(config.base_dir, "data", "models", target_name)
        
        import shutil
        shutil.copy2(best_model_src, target_path)
        
        print(f"DEBUG: Saved trained model to {target_path}")
        return target_path
    
    def _extract_metrics(self, results) -> Dict[str, Any]:
        """Extract metrics from training results."""
        if results is None:
            return {}
        
        try:
            return {
                "box_map50": getattr(results, 'box', {}).get('map50', None),
                "seg_map50": getattr(results, 'seg', {}).get('map50', None),
            }
        except Exception:
            return {}
