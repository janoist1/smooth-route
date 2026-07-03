import uuid
from typing import Any, Dict

from app.core.paths import data_path, image_path
from app.services.inference import inference_service
from app.services.preprocessing import road_preprocessor

class ReviewService:
    """
    Unified service for handling interactive review toolbar actions.
    ``preview_preprocessing`` is a quarantined YOLO-dataset diagnostic and is
    never used by the production RQI inference path.
    """

    def perform_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a review action.
        
        Args:
            action_type: Identifier string (e.g. 'auto_detect', 'preview_preprocessing')
            params: Dictionary of parameters specific to the action
            
        Returns:
            Dict containing optional keys: 'annotations', 'processedImageUrl', 'message'
        """
        print(f"ReviewService: Executing {action_type} with params: {params}")
        
        if action_type == 'auto_detect':
            return self._handle_auto_detect(params)
        elif action_type == 'preview_preprocessing':
            return self._handle_preview_preprocessing(params)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    def _resolve_image_path(self, filename: str) -> str:
        path = image_path(filename)
        if path.is_file():
            return str(path)
        raise FileNotFoundError(f"Image {filename} not found in canonical data directory")

    def _handle_auto_detect(self, params: Dict[str, Any]) -> Dict[str, Any]:
        filename = params.get('filename')
        conf_threshold = params.get('confThreshold', 0.25)
        classes = params.get('classes')
        
        if not filename:
            raise ValueError("filename is required for auto_detect")
            
        image_path = self._resolve_image_path(filename)
        
        results = inference_service.detect_objects(
            image_path=image_path,
            conf_threshold=conf_threshold,
            classes=classes
        )
        
        # Map to unified annotation format (matches frontend Annotation type)
        annotations = []
        for i, res in enumerate(results):
            annotations.append({
                "id": f"ai-{uuid.uuid4().hex[:8]}", # Generate temp ID
                "label": res['label'],
                "score": res['confidence'],
                "points": res['points'],
                "type": "polygon" if len(res['points']) > 2 else "box"
            })
            
        return {
            "annotations": annotations,
            "message": f"Detected {len(annotations)} objects"
        }

    def _handle_preview_preprocessing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        filename = params.get('filename')
        raw_options = params.get('options', {}) 
        
        # Map frontend camelCase OR snake_case to backend snake_case
        # The frontend might send either, so we check both.
        options = {
            "use_roi": raw_options.get("useRoi") if raw_options.get("useRoi") is not None else raw_options.get("use_roi", True),
            "smart_roi": raw_options.get("smartRoi") if raw_options.get("smartRoi") is not None else raw_options.get("smart_roi", False),
            "use_mask": raw_options.get("useMask") if raw_options.get("useMask") is not None else raw_options.get("use_mask", True),
            "remove_shadows_1": raw_options.get("removeShadows1") if raw_options.get("removeShadows1") is not None else raw_options.get("remove_shadows_1", False),
            "remove_shadows_2": raw_options.get("removeShadows2") if raw_options.get("removeShadows2") is not None else raw_options.get("remove_shadows_2", False)
        }
        
        if not filename:
            raise ValueError("filename is required for preview_preprocessing")
            
        src_path = self._resolve_image_path(filename)
        
        # Create temp output path
        # Assuming we have a static/temp folder served by API
        temp_dir = data_path("static", "previews")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        temp_filename = f"preview_{uuid.uuid4().hex[:8]}_{filename}"
        dst_path = temp_dir / temp_filename
        
        # Execute Preprocessing
        road_preprocessor.process_and_save(src_path, str(dst_path), options)
        
        # Return URL (assuming /static/previews/ is mounted)
        # Note: Vite proxy needs to handle /static/ or /api/v1/static
        # In main.py usually 'data/static' is mounted
        
        # We'll return a relative path that the frontend can construct
        # or a full URL if we knew the host.
        # Safe bet: return relative path from 'statc' mount point
        
        return {
            "processedImageUrl": f"previews/{temp_filename}",
            "message": "Preview generated"
        }

review_service = ReviewService()
