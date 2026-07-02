"""
Base classes and types for training providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, Callable


class TrainingProvider(str, Enum):
    """Available training execution backends."""
    LOCAL = "local"
    GOOGLE_COLAB = "google_colab"


@dataclass
class TrainingConfig:
    """Configuration for a training run."""
    job_id: str
    data_yaml_path: str
    model_name: str
    epochs: int
    batch_size: int
    workers: int
    device: str
    # Paths
    base_dir: str
    output_dir: str
    
    # Options with defaults
    model_type: str = "YOLO" # "YOLO" or "DINO"
    patience: int = 50
    
    # Callbacks
    progress_callback: Optional[Callable[[int, str], None]] = None


class BaseTrainingProvider(ABC):
    """Abstract base class for training providers."""
    
    @abstractmethod
    def run(self, config: TrainingConfig) -> Dict[str, Any]:
        """
        Execute training with the given configuration.
        
        Args:
            config: TrainingConfig with all parameters
            
        Returns:
            Dict with results including:
                - success: bool
                - model_path: str (path to saved model, if successful)
                - message: str
                - metrics: dict (optional training metrics)
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return human-readable provider name."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available on the current system."""
        pass
    
    def get_status_message(self) -> str:
        """Return status message for UI display."""
        if self.is_available():
            return f"{self.get_provider_name()} - Elérhető ✓"
        return f"{self.get_provider_name()} - Nem elérhető"
