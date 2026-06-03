# Training NeuralEye YOLOv8 Model

This directory contains scripts to fine-tune the YOLOv8 model for your specific CCTV cameras.

## 1. Data Preparation (Important!)

Computer Vision models like YOLOv8 require **images and bounding box coordinates**, not tabular sales/POS data (like GMV, NMV, tax, etc.).

If you have a CSV with sales data (as shown in your screenshot with columns like `hsn_code`, `GMV`, `tax`), that data is excellent for the **Analytics Engine** (to correlate dwell time with actual sales), but it **cannot** be used to train YOLOv8 to detect people in video frames.

To train the YOLO model, you need:
1. Extracted image frames from your CCTV `.mp4` files.
2. Annotations (labels) in YOLO text format. Each text file corresponds to an image and contains lines like: `<class_id> <x_center> <y_center> <width> <height>`

### Recommended Workflow for Annotation:
1. **Extract Frames**: Use a tool (or python script) to extract 1 frame every second from your CCTV footage.
2. **Label**: Upload those frames to a tool like [Roboflow](https://roboflow.com) or [CVAT](https://www.cvat.ai).
3. **Draw Boxes**: Draw boxes around the people (and products, if you want) in the frames.
4. **Export**: Export the dataset in "YOLOv8" format.

## 2. Setup the Dataset

Once you have your YOLO dataset exported, place it in a `datasets/cctv` folder.
Create a `dataset.yaml` file in this directory:

```yaml
path: ./datasets/cctv  # dataset root dir
train: images/train  # train images (relative to 'path')
val: images/val      # val images (relative to 'path')

# Classes
names:
  0: person
```

## 3. Run Fine-Tuning

Make sure you have installed the requirements:
```bash
pip install ultralytics
```

Then run the training script:
```bash
python fine_tune_yolo.py
```

Once training completes, update `services/ingestion/main.py` to point `YOLO("yolov8n.pt")` to your new trained weights at `neuraleye_training/cctv_model/weights/best.pt`.
