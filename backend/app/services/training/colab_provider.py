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
        """Generate Colab notebook with training parameters depending on model type."""
        
        if config.model_type == "DINO":
             return self._generate_dino_notebook(config, timestamp)

        # Legacy YOLO Notebook Generation
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
    
    
    def _generate_dino_notebook(self, config: TrainingConfig, timestamp: str) -> str:
        """Generate Colab notebook for DINO training."""
        cells = [
            {
                "cell_type": "markdown",
                "metadata": {"id": "header"},
                "source": [
                    "# 🦕 Smooth Route - DINO RQI Training\n",
                    "\n",
                    "Ez a notebook a Smooth Route DINO osztályozó (RQI) tanítására szolgál.\n",
                    "A skript letölti a DINOv2 modellt, és finomhangol egy MLP head-et az RQI (1-5) osztályozáshoz.\n",
                    "\n",
                    "**Teendők:**\n",
                    "1. Töltsd fel a letöltött dataset ZIP fájlt a Colab-ra (pl. `dataset_...zip`)\n",
                    "2. Futtasd az összes cellát\n",
                    "3. Töltsd le a kész modellt (`dino_rqi_head_vits14.pt`)\n"
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
                    "# 2. Környezet előkészítése\n",
                    "!pip install torch torchvision numpy scikit-learn -q\n",
                    "import torch\n",
                    "import os\n",
                    "print(f'Torch version: {torch.__version__}')"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "dataset_upload"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 3. Dataset kicsomagolás\n",
                    "# Feltételezzük, hogy a user feltöltötte a zip-et\n",
                    "import glob\n",
                    "zips = glob.glob('dataset_*.zip')\n",
                    "if not zips:\n",
                    "    print('❌ NEM TALÁLOM A ZIP FÁJLT! Kérlek töltsd fel a Files menüben bal oldalt.')\n",
                    "    from google.colab import files\n",
                    "    uploaded = files.upload()\n",
                    "    zips = glob.glob('dataset_*.zip')\n",
                    "\n",
                    "if zips:\n",
                    "    zip_file = zips[0]\n",
                    "    print(f'Kicsomagolás: {zip_file} -> /content/dataset')\n",
                    "    !rm -rf /content/dataset\n",
                    "    !unzip -q {zip_file} -d /content/dataset\n",
                    "else:\n",
                    "    print('Hiba: Még mindig nincs zip.')"
                ]
            },
            {
                 "cell_type": "code",
                 "metadata": {"id": "dino_code"},
                 "execution_count": None,
                 "outputs": [],
                 "source": [
                     "# 4. Training Code Definitions (Inline)\n",
                     "import torch\n",
                     "import torch.nn as nn\n",
                     "from torch.utils.data import Dataset, DataLoader\n",
                     "from torchvision import transforms, datasets\n",
                     "import copy\n",
                     "\n",
                     "# --- Model Definition ---\n",
                     "class DinoClassifier(nn.Module):\n",
                     "    def __init__(self, dino_version='dinov2_vits14'):\n",
                     "        super().__init__()\n",
                     "        print(f'Loading {dino_version} from torch.hub...')\n",
                     "        self.backbone = torch.hub.load('facebookresearch/dinov2', dino_version)\n",
                     "        self.backbone.eval()\n",
                     "        for param in self.backbone.parameters():\n",
                     "            param.requires_grad = False\n",
                     "\n",
                     "        # Embed dim: vits14=384, vitb14=768, vitl14=1024, vitg14=1536\n",
                     "        embed_dim = 384 \n",
                     "        if 'vitb' in dino_version: embed_dim = 768\n",
                     "        if 'vitl' in dino_version: embed_dim = 1024\n",
                     "        if 'vitg' in dino_version: embed_dim = 1536\n",
                     "\n",
                     "        self.head = nn.Sequential(\n",
                     "            nn.Linear(embed_dim, 256),\n",
                     "            nn.ReLU(),\n",
                     "            nn.Dropout(0.1),\n",
                     "            nn.Linear(256, 5)  # 5 classes (RQI 1-5)\n",
                     "        )\n",
                     "\n",
                     "    def forward(self, x):\n",
                     "        with torch.no_grad():\n",
                     "            features = self.backbone(x)\n",
                     "        return self.head(features)\n",
                     "\n",
                     "# --- Training Logic ---\n",
                     "def train_model():\n",
                     f"    EPOCHS = {config.epochs}\n",
                     f"    BATCH_SIZE = {config.batch_size}\n",
                     "    DATA_DIR = '/content/dataset'\n",
                     "\n",
                     "    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')\n",
                     "    print(f'Using device: {device}')\n",
                     "\n",
                     "    transform = transforms.Compose([\n",
                     "        transforms.Resize(256),\n",
                     "        transforms.CenterCrop(224),\n",
                     "        transforms.ToTensor(),\n",
                     "        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])\n",
                     "    ])\n",
                     "\n",
                     "    # Load dataset using ImageFolder structure (1, 2, 3, 4, 5)\n",
                     "    full_dataset = datasets.ImageFolder(root=DATA_DIR, transform=transform)\n",
                     "    print(f'Found {len(full_dataset)} images. Classes: {full_dataset.classes}')\n",
                     "\n",
                     "    # Split\n",
                     "    train_size = int(0.8 * len(full_dataset))\n",
                     "    val_size = len(full_dataset) - train_size\n",
                     "    train_dataset, val_dataset = torch.utils.data.random_split(full_dataset, [train_size, val_size])\n",
                     "\n",
                     "    dataloaders = {\n",
                     "        'train': DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True),\n",
                     "        'val': DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)\n",
                     "    }\n",
                     "\n",
                     "    model = DinoClassifier()\n",
                     "    model = model.to(device)\n",
                     "\n",
                     "    criterion = nn.CrossEntropyLoss()\n",
                     "    optimizer = torch.optim.Adam(model.head.parameters(), lr=1e-3)\n",
                     "\n",
                     "    best_acc = 0.0\n",
                     "    best_model_wts = copy.deepcopy(model.head.state_dict())\n",
                     "\n",
                     "    for epoch in range(EPOCHS):\n",
                     "        print(f'Epoch {epoch+1}/{EPOCHS}')\n",
                     "        \n",
                     "        for phase in ['train', 'val']:\n",
                     "            if phase == 'train':\n",
                     "                model.head.train()\n",
                     "            else:\n",
                     "                model.head.eval()\n",
                     "\n",
                     "            running_loss = 0.0\n",
                     "            running_corrects = 0\n",
                     "\n",
                     "            for inputs, labels in dataloaders[phase]:\n",
                     "                inputs = inputs.to(device)\n",
                     "                labels = labels.to(device)\n",
                     "\n",
                     "                optimizer.zero_grad()\n",
                     "\n",
                     "                with torch.set_grad_enabled(phase == 'train'):\n",
                     "                    outputs = model(inputs)\n",
                     "                    _, preds = torch.max(outputs, 1)\n",
                     "                    loss = criterion(outputs, labels)\n",
                     "\n",
                     "                    if phase == 'train':\n",
                     "                        loss.backward()\n",
                     "                        optimizer.step()\n",
                     "\n",
                     "                running_loss += loss.item() * inputs.size(0)\n",
                     "                running_corrects += torch.sum(preds == labels.data)\n",
                     "\n",
                     "            epoch_loss = running_loss / len(dataloaders[phase].dataset)\n",
                     "            epoch_acc = running_corrects.double() / len(dataloaders[phase].dataset)\n",
                     "\n",
                     "            print(f'{phase} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}')\n",
                     "\n",
                     "            if phase == 'val' and epoch_acc > best_acc:\n",
                     "                best_acc = epoch_acc\n",
                     "                best_model_wts = copy.deepcopy(model.head.state_dict())\n",
                     "\n",
                     "    print(f'Best valid Acc: {best_acc:4f}')\n",
                     "    \n",
                     "    # Save model head only (smallest size)\n",
                     "    # Or we can save full state dict if needed, but for service we only need head\n",
                     "    torch.save(best_model_wts, 'dino_rqi_head_vits14.pt')\n",
                     "    print('Modell elmentve: dino_rqi_head_vits14.pt')\n",
                     "\n",
                     "train_model()"
                 ]
            },
            {
                "cell_type": "code",
                "metadata": {"id": "download"},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# 5. Modell letöltés\n",
                    "from google.colab import files\n",
                    "if os.path.exists('dino_rqi_head_vits14.pt'):\n",
                    "    files.download('dino_rqi_head_vits14.pt')\n",
                    "    print('A fájlt másold a Smooth Route /backend/data/models/ mappába!')\n",
                    "else:\n",
                    "    print('Hiba: Nem találom a kimeneti fájlt.')"
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
        notebook_path = os.path.join(self.export_dir, f"dino_training_{timestamp}.ipynb")
        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(notebook_data, f, indent=2, ensure_ascii=False)
        
        print(f"DEBUG: Generated DINO Colab notebook at {notebook_path}")
        return notebook_path

    def _get_instructions(self) -> str:
        """Return instructions for Colab execution."""
        return """
## Google Colab Tanítás

1. **Nyisd meg a Colab-ot**: https://colab.research.google.com
2. **Töltsd fel a notebook-ot** (File → Upload notebook)
3. **Állítsd be a GPU-t**: Runtime → Change runtime type → T4 GPU
4. **Töltsd fel a letöltött dataset ZIP fájlt** (nem kell átnevezni!)
5. **Futtasd az összes cellát** (Runtime → Run all)
6. **Töltsd le a kész modellt**
7. **Másold a modellt** a `backend/data/models/` mappába
"""

def get_colab_export_path() -> str:
    """Get the export directory path."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(base_dir, "data", "exports")
