# Tools directory
# Scripts for data preparation, training, and utilities

tools/
├── extract_frames.py      # Extract frames from video
├── prepare_dataset.py     # Prepare YOLO dataset structure
└── train.py              # Train YOLO model

Usage examples:

# Extract frames (1 frame per 2 seconds)
python tools/extract_frames.py --video input.mp4 --output dataset/images --interval 2

# Prepare dataset for YOLO training
python tools/prepare_dataset.py --dataset dataset --output data.yaml

# Train model
python tools/train.py --data data.yaml --epochs 100 --imgsz 640
