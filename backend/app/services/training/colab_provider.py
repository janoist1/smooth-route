"""
Google Colab training provider - exports training data for Colab execution.
"""
import json
import os
import shutil
import zipfile
from datetime import datetime
from typing import Dict, Any, List

from .base import BaseTrainingProvider, TrainingConfig


class ColabTrainingProvider(BaseTrainingProvider):
    """
    Exports training data for Google Colab execution.
    
    This provider doesn't run training locally - it generates:
    1. A Jupyter notebook (.ipynb) pre-configured for Colab
    2. A zipped dataset for upload to Colab
    """
    
    def __init__(self, export_dir: str = None):
        self.export_dir = export_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "data", "exports"
        )
    
    def get_provider_name(self) -> str:
        return "Google Colab"
    
    def is_available(self) -> bool:
        return True  # Export is always available
    
    def run(self, config: TrainingConfig) -> Dict[str, Any]:
        """
        Export training notebook and dataset for Colab.
        """
        try:
            os.makedirs(self.export_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Export notebook
            notebook_path = self._generate_notebook(config, timestamp)
            
            # Export dataset
            dataset_path = self._export_dataset(config, timestamp)
            
            if config.progress_callback:
                config.progress_callback(100, "Export kész! Töltsd le a fájlokat.")
            
            return {
                "success": True,
                "model_path": None,
                "message": "Colab export kész! Töltsd le a fájlokat és futtasd a notebook-ot.",
                "exports": {
                    "notebook_path": f"/api/v1/exports/{os.path.basename(notebook_path)}",
                    "dataset_path": f"/api/v1/exports/{os.path.basename(dataset_path)}",
                },
                "instructions": self._get_instructions(),
            }
            
        except Exception as e:
            print(f"ERROR: Colab export failed: {e}")
            return {
                "success": False,
                "model_path": None,
                "message": f"Export hiba: {str(e)}",
            }

    def _generate_notebook(self, config: TrainingConfig, timestamp: str) -> str:
        """Generate Colab notebook with training parameters using native dictionary construction."""
        
        # Prepare cells
        cells = [
            {
                "cell_type": "markdown",
                "metadata": {"id": "header"},
                "source": [
                    "# 🚀 Smooth Route - YOLO Training\n",
                    "\n",
                    "Ez a notebook a Smooth Route alkalmazásból lett exportálva.\n",
                    "\n",
                    "**Teendők:**\n",
                    "1. Töltsd fel a letöltött dataset ZIP fájlt a Colab-ra\n",
                    "2. Futtasd az összes cellát\n",
                    "3. Töltsd le a kész modellt (best.pt)\n"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "gpu_check"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 1. GPU ellenőrzés\n",
                    "!nvidia-smi"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "install"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 2. Ultralytics telepítés és frissítés\n",
                    "!pip install -U ultralytics -q\n",
                    "from ultralytics import YOLO\n",
                    "import os\n",
                    "print('Ultralytics version updated and loaded!')"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "upload"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 3. Dataset feltöltés\n",
                    "from google.colab import files\n",
                    "print('Töltsd fel a letöltött dataset ZIP fájlt (pl. dataset_2026...zip)')\n",
                    "uploaded = files.upload()"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "unzip"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 4. Dataset kicsomagolás\n",
                    "!rm -rf /content/dataset\n",
                    "!unzip -q dataset*.zip -d /content/dataset\n",
                    "\n",
                    "# 🔍 ELLENŐRZÉS\n",
                    "def check_paths():\n",
                    "    paths = [\n",
                    "        '/content/dataset/data.yaml',\n",
                    "        '/content/dataset/images/train',\n",
                    "        '/content/dataset/images/val'\n",
                    "    ]\n",
                    "    print('--- Elérési utak ellenőrzése ---')\n",
                    "    all_ok = True\n",
                    "    for p in paths:\n",
                    "        exists = os.path.exists(p)\n",
                    "        status = '✅ LÉTEZIK' if exists else '❌ HIÁNYZIK!'\n",
                    "        print(f'{p}: {status}')\n",
                    "        if not exists: all_ok = False\n",
                    "    return all_ok\n",
                    "\n",
                    "check_paths()"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "train"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 5. Modell betöltés és tanítás\n",
                    f"model_name = '{config.model_name}'\n",
                    "if not os.path.exists('/content/dataset/data.yaml'):\n",
                    "    raise FileNotFoundError('Nem találom a data.yaml-t! Töltsd fel a ZIP-et helyesen.')\n",
                    "\n",
                    "print(f'Modell: {model_name}')\n",
                    "\n",
                    "# Speciális kezelés YOLOv12 szegmentációhoz\n",
                    "if 'yolo12' in model_name and 'seg' in model_name:\n",
                    "    base_model = model_name.replace('-seg.pt', '.pt')\n",
                    "    yaml_name = model_name.replace('.pt', '.yaml')\n",
                    "    print(f'YOLOv12-Seg hibrid mód: {yaml_name} + {base_model}')\n",
                    "    model = YOLO(yaml_name).load(base_model)\n",
                    "else:\n",
                    "    model = YOLO(model_name)\n",
                    "\n",
                    "print('\\n🚀 Tanítás indítása...')\n",
                    "print('Tipp: Ha memóriahiba van, próbáld kisebb batch mérettel (pl. batch=8)')\n",
                    "\n",
                    "results = model.train(\n",
                    "    data='/content/dataset/data.yaml',\n",
                    f"    epochs={config.epochs},\n",
                    "    imgsz=640,\n",
                    f"    batch={config.batch_size},\n",
                    f"    patience={config.patience},\n",
                    "    project='/content/runs',\n",
                    "    name='smooth_route',\n",
                    "    exist_ok=True,\n",
                    "    verbose=True,\n",
                    "    device=0,  # GPU\n",
                    "    workers=4,\n",
                    "    cache=True\n",
                    ")\n",
                    "print('Tanítás sikeresen befejeződött!')"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "download"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 6. Modell letöltés\n",
                    "from google.colab import files\n",
                    "files.download('/content/runs/smooth_route/weights/best.pt')\n",
                    "print('A best.pt fájlt töltsd fel a Smooth Route /backend/data/models/ mappába!')"
                ]
            }
        ]

        # Notebook structure
        notebook_data = {
            "nbformat": 4,
            "nbformat_minor": 0,
            "metadata": {
                "colab": {
                    "provenance": [],
                    "gpuType": "T4"
                },
                "kernelspec": {
                    "name": "python3",
                    "display_name": "Python 3"
                },
                "accelerator": "GPU"
            },
            "cells": cells
        }

        # Save notebook
        notebook_path = os.path.join(self.export_dir, f"training_{timestamp}.ipynb")
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(notebook_data, f, indent=2, ensure_ascii=False)
        
        print(f"DEBUG: Generated Colab notebook at {notebook_path}")
        return notebook_path
    
    def _export_dataset(self, config: TrainingConfig, timestamp: str) -> str:
        """Zip the training dataset for Colab upload."""
        dataset_dir = os.path.join(config.base_dir, "data", "training_dataset")
        
        if not os.path.exists(dataset_dir):
            raise FileNotFoundError(f"Training dataset not found: {dataset_dir}")
        
        zip_path = os.path.join(self.export_dir, f"dataset_{timestamp}.zip")
        
        # Create zip
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(dataset_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, dataset_dir)
                    zipf.write(file_path, arcname)
        
        print(f"DEBUG: Exported dataset to {zip_path}")
        return zip_path
    
    def _get_instructions(self) -> str:
        """Return instructions for Colab execution."""
        return """
## Google Colab Tanítás

1. **Nyisd meg a Colab-ot**: https://colab.research.google.com
2. **Töltsd fel a notebook-ot** (File → Upload notebook)
3. **Állítsd be a GPU-t**: Runtime → Change runtime type → T4 GPU
4. **Töltsd fel a letöltött dataset ZIP fájlt** (nem kell átnevezni!)
5. **Futtasd az összes cellát** (Runtime → Run all)
6. **Töltsd le a kész modellt** (best.pt)
7. **Másold a modellt** a `backend/data/models/` mappába

Becsült futási idő: 10-20 perc
"""


def get_colab_export_path() -> str:
    """Get the export directory path."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(base_dir, "data", "exports")
