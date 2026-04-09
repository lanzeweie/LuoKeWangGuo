# Dataset directory structure
dataset/
├── images/          # Original images (git ignored)
│   └── .gitkeep
├── labels/          # YOLO format annotations (git ignored)
│   └── .gitkeep
├── classes.txt      # Class definitions
└── dataset.yaml     # YOLO dataset config (generated)

Example classes.txt:
```
奇丽草群组
```

For multiple pets:
```
奇丽草群组
fire_dragon
water_turtle
grass_snake
```

# Notes
- Keep images and labels in sync (same filename, different extension)
- Use LabelImg for annotation: `pip install labelImg`
- Format: YOLO (one .txt per image)
- Annotation: tight bounding box around pet only
