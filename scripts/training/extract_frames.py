import cv2
import os
import argparse

def extract_frames(video_path, output_dir, interval_seconds=5):
    """
    Extracts frames from a video file at a specified interval.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or fps is None:
        fps = 25 # fallback
        
    frame_interval = int(fps * interval_seconds)
    frame_count = 0
    saved_count = 0

    print(f"Extracting 1 frame every {interval_seconds} seconds (approx every {frame_interval} frames)")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            output_path = os.path.join(output_dir, f"frame_{saved_count:04d}.jpg")
            cv2.imwrite(output_path, frame)
            saved_count += 1
            print(f"Saved {output_path}")

        frame_count += 1

    cap.release()
    print(f"Done! Saved {saved_count} frames to {output_dir}")
    print("Next step: Upload these images to CVAT or Roboflow to draw bounding boxes.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract frames from CCTV for labeling")
    parser.add_argument("--video", type=str, required=True, help="Path to the CCTV video file")
    parser.add_argument("--output", type=str, default="./datasets/cctv/images", help="Output directory for frames")
    parser.add_argument("--interval", type=int, default=5, help="Seconds between extracted frames")
    
    args = parser.parse_args()
    extract_frames(args.video, args.output, args.interval)
