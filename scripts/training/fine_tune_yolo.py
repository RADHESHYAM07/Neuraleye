import os
from ultralytics import YOLO

def main():
    # Load a pretrained YOLO model (recommended for training)
    print("Loading base YOLOv8n model...")
    model = YOLO("yolov8n.pt")
    
    # Path to your dataset configuration file (YAML)
    dataset_yaml = "dataset.yaml"
    
    if not os.path.exists(dataset_yaml):
        print(f"Error: {dataset_yaml} not found.")
        print("Please create a dataset.yaml file that points to your labeled CCTV images.")
        print("Example dataset.yaml:")
        print("  path: ./datasets/cctv")
        print("  train: images/train")
        print("  val: images/val")
        print("  names:")
        print("    0: person")
        print("    1: product")
        return

    print("Starting fine-tuning...")
    # Train the model using your custom dataset
    # You can adjust epochs, imgsz (image size), and batch size based on your GPU capability
    results = model.train(
        data=dataset_yaml,
        epochs=50,
        imgsz=640,
        batch=16,
        device="cpu", # Change to 0 if you have a GPU
        project="neuraleye_training",
        name="cctv_model"
    )
    
    print("Training complete! The best weights are saved in neuraleye_training/cctv_model/weights/best.pt")

if __name__ == "__main__":
    main()
