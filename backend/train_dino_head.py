import os
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
from tqdm import tqdm
import time

# --- Configuration ---
# Matches dino_service.py
VARIANT = "vits14"
EMBED_DIM = 384  # for vits14
BATCH_SIZE = 32
EPOCHS = 20
LEARNING_RATE = 0.001
DEVICE = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")

print(f"Using device: {DEVICE}")

# --- Model Definition (Must match DinoInferenceService) ---
def create_head():
    return nn.Sequential(
        nn.Linear(EMBED_DIM, 256),
        nn.ReLU(),
        nn.Dropout(0.1),
        nn.Linear(256, 5)  # 5 classes (1, 2, 3, 4, 5)
    )

class DinoClassifier(nn.Module):
    def __init__(self, head):
        super().__init__()
        self.backbone = torch.hub.load('facebookresearch/dinov2', f'dinov2_{VARIANT}')
        self.backbone.eval() # Freeze backbone
        for param in self.backbone.parameters():
            param.requires_grad = False
        self.head = head

    def forward(self, x):
        with torch.no_grad():
            features = self.backbone(x)
        return self.head(features)

# --- Dataset ---
class RQIDataset(Dataset):
    def __init__(self, root_dir, transform=None):
        self.root_dir = root_dir
        self.transform = transform
        self.samples = []
        
        # Expect folders "1", "2", "3", "4", "5"
        for label_str in ["1", "2", "3", "4", "5"]:
            class_dir = os.path.join(root_dir, label_str)
            if not os.path.exists(class_dir):
                print(f"Warning: Class folder {label_str} not found in {root_dir}")
                continue
                
            label = int(label_str) - 1 # 0-indexed (0 to 4)
            for fname in os.listdir(class_dir):
                if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                    self.samples.append((os.path.join(class_dir, fname), label))
        
        print(f"Found {len(self.samples)} images in {root_dir}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        image = Image.open(path).convert('RGB')
        if self.transform:
            image = self.transform(image)
        return image, label

# --- Training Loop ---
def train(data_dir, output_path, epochs=20, batch_size=32, num_workers=0, progress_callback=None):
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    dataset = RQIDataset(data_dir, transform=transform)
    
    if len(dataset) == 0:
        print("Error: No data found. Exiting.")
        if progress_callback:
            progress_callback(0, "Hiba: Nem található tanító adat!")
        return

    # Split Train/Val (80/20)
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    head = create_head().to(DEVICE)
    model = DinoClassifier(head).to(DEVICE)
    
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(head.parameters(), lr=LEARNING_RATE)

    best_acc = 0.0

    print("Starting training...")
    for epoch in range(epochs):
        model.train() # Set head to train mode (backbone is manually set to eval in init)
        
        running_loss = 0.0
        correct = 0
        total = 0
        
        # training loop
        for inputs, labels in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs}"):
            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * inputs.size(0)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

        epoch_loss = running_loss / len(train_dataset)
        epoch_acc = correct / total

        # validation loop
        model.eval() # Set head to eval
        val_correct = 0
        val_total = 0
        
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)
                outputs = model(inputs)
                _, predicted = torch.max(outputs.data, 1)
                val_total += labels.size(0)
                val_correct += (predicted == labels).sum().item()
        
        val_acc = val_correct / val_total if val_total > 0 else 0
        
        log_msg = f"Epoch {epoch+1} - Loss: {epoch_loss:.4f}, Train Acc: {epoch_acc:.4f}, Val Acc: {val_acc:.4f}"
        print(log_msg)

        if val_acc >= best_acc:
            best_acc = val_acc
            print(f"New best model! Saving to {output_path}")
            torch.save(head.state_dict(), output_path)

        # Update progress
        if progress_callback:
            # Report progress from 10% to 90% (leaving room for setup and finish)
            current_progress = 10 + int((epoch + 1) / epochs * 80)
            progress_callback(current_progress, log_msg)

    print("Training complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", required=True, help="Path to exported classification dataset")
    parser.add_argument("--output", default="data/models/dino_rqi_head_vits14.pt", help="Where to save the .pt file")
    args = parser.parse_args()
    
    # Ensure output dir exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    train(args.data_dir, args.output)
