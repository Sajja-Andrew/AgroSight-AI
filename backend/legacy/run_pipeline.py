"""
Complete Pipeline Script
Run the entire training pipeline from dataset preparation to model training
"""

import os
import sys
import argparse
from pathlib import Path

def run_command(cmd):
    """Run a shell command and return success status"""
    print(f"\n{'='*60}")
    print(f"Running: {cmd}")
    print(f"{'='*60}\n")
    result = os.system(cmd)
    return result == 0

def main():
    parser = argparse.ArgumentParser(description='Complete Training Pipeline')
    parser.add_argument('--dataset_path', type=str, 
                        default='../dataset/Agrosight AI_dataset',
                        help='Path to Agrosight AI_dataset folder')
    parser.add_argument('--output_path', type=str,
                        default='../dataset/processed',
                        help='Output path for processed dataset')
    parser.add_argument('--model_save_dir', type=str,
                        default='../saved_models',
                        help='Path to save trained models')
    parser.add_argument('--epochs', type=int, default=30,
                        help='Number of training epochs')
    parser.add_argument('--skip_prep', action='store_true',
                        help='Skip dataset preparation')
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("Agrosight AI AI TRAINING PIPELINE")
    print("="*60)

    # Convert to absolute paths
    base_dir = Path(__file__).parent.parent
    dataset_path = Path(args.dataset_path)
    if not dataset_path.is_absolute():
        dataset_path = base_dir / args.dataset_path

    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = base_dir / args.output_path

    model_save_dir = Path(args.model_save_dir)
    if not model_save_dir.is_absolute():
        model_save_dir = base_dir / args.model_save_dir

    print(f"\nDataset path: {dataset_path}")
    print(f"Output path: {output_path}")
    print(f"Model save dir: {model_save_dir}")
    print(f"Epochs: {args.epochs}")

    # Step 1: Prepare dataset
    if not args.skip_prep:
        print("\n" + "="*60)
        print("STEP 1: DATASET PREPARATION")
        print("="*60)

        cmd = f'python utils/dataset_prep.py --dataset_path "{dataset_path}" --output_path "{output_path}"'
        if not run_command(cmd):
            print("\nDataset preparation failed!")
            sys.exit(1)

    # Step 2: Train model
    print("\n" + "="*60)
    print("STEP 2: MODEL TRAINING")
    print("="*60)

    cmd = f'python model/train.py --data_dir "{output_path}" --model_save_dir "{model_save_dir}" --epochs {args.epochs} --model_type transfer --base_model MobileNetV2'
    if not run_command(cmd):
        print("\nTraining failed!")
        sys.exit(1)

    print("\n" + "="*60)
    print("PIPELINE COMPLETED SUCCESSFULLY!")
    print("="*60)
    print(f"\nProcessed dataset: {output_path}")
    print(f"Trained models: {model_save_dir}")
    print("\nNext steps:")
    print("1. Test prediction: python model/predict.py --model saved_models/best_model.keras --class_indices saved_models/class_indices.json --image path/to/image.jpg")
    print("2. Start API server: python app.py")

if __name__ == "__main__":
    main()