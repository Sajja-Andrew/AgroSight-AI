import os
import shutil
import random
from sklearn.model_selection import train_test_split
import pathlib
import json

# Load disease database from shared JSON
DISEASE_DB_PATH = pathlib.Path(__file__).parent.parent / 'data' / 'disease_database.json'
DISEASE_INFO = {}
try:
    with open(DISEASE_DB_PATH, 'r', encoding='utf-8') as f:
        DISEASE_INFO = json.load(f)
except Exception as e:
    print(f"Warning: Could not load disease database from {DISEASE_DB_PATH}: {e}")
    DISEASE_INFO = {}

class DatasetPreparator:
    def __init__(self, dataset_path, output_path, test_size=0.2, val_size=0.1, use_color=True):
        """
        Initialize dataset preparator
        
        Args:
            dataset_path: Path to Agrosight AI_dataset folder
            output_path: Path to save processed dataset
            test_size: Fraction for testing (default 0.2 = 20%)
            val_size: Fraction for validation (default 0.1 = 10%)
            use_color: Use color images (recommended)
        """
        self.dataset_path = pathlib.Path(dataset_path)
        self.output_path = pathlib.Path(output_path)
        self.test_size = test_size
        self.val_size = val_size
        self.use_color = use_color
        
        # Determine which folder to use
        if use_color:
            self.image_folder = self.dataset_path / 'color'
        else:
            self.image_folder = self.dataset_path / 'color'  # Default to color even if specified otherwise
        
    def get_image_extensions(self):
        """Get supported image extensions"""
        return ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG', '.bmp', '.BMP']
    
    def find_class_folders(self):
        """
        Recursively find all class folders containing images.
        Handles nested structures like color/Maize/DiseaseClass/
        """
        class_folders = []
        for root, dirs, files in os.walk(self.image_folder):
            # Check if this directory contains images
            has_images = any(
                f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))
                for f in files
            )
            if has_images and root != str(self.image_folder):
                class_folders.append(pathlib.Path(root))
        return sorted(class_folders)

    def prepare_dataset(self):
        """
        Organize dataset into train/val/test folders
        """
        print("\n" + "="*60)
        print(" SMART CROP DATASET PREPARATION")
        print("="*60)

        # Check if source folder exists
        if not self.image_folder.exists():
            print(f"\n ERROR: Dataset folder not found!")
            print(f"   Expected path: {self.image_folder}")
            print(f"\n   Please ensure your dataset is at:")
            print(f"   {self.dataset_path}")
            print(f"\n   And contains folders: color/, grayscale/, segmented/")
            return False

        # Create output directories
        for split in ['train', 'val', 'test']:
            (self.output_path / split).mkdir(parents=True, exist_ok=True)

        # Get all class folders from the color/grayscale/segmented folder
        class_folders = self.find_class_folders()

        if not class_folders:
            print(f"\n ERROR: No class folders found in {self.image_folder}")
            print(f"   Expected folders like: Tomato___Late_blight/, Potato___Early_blight/, etc.")
            return False
        
        print(f"\n Dataset path: {self.image_folder}")
        print(f" Found {len(class_folders)} disease classes\n")
        
        total_images = 0
        class_stats = []
        
        for class_folder in class_folders:
            class_name = class_folder.name
            
            # Get all images in this class
            images = []
            for ext in self.get_image_extensions():
                images.extend(list(class_folder.glob(f'*{ext}')))
            
            if not images:
                print(f"ï¸  No images found in {class_name}, skipping...")
                continue
            
            total_images += len(images)
            
            # Split into train, val, test
            train_images, test_images = train_test_split(
                images, test_size=self.test_size, random_state=42
            )
            
            # Calculate actual validation size from remaining data
            val_size_actual = self.val_size / (1 - self.test_size)
            train_images, val_images = train_test_split(
                train_images, test_size=val_size_actual, random_state=42
            )
            
            class_stats.append({
                'name': class_name,
                'total': len(images),
                'train': len(train_images),
                'val': len(val_images),
                'test': len(test_images)
            })
            
            # Copy images to respective folders
            for split, split_images in [('train', train_images), ('val', val_images), ('test', test_images)]:
                split_class_dir = self.output_path / split / class_name
                split_class_dir.mkdir(parents=True, exist_ok=True)
                
                for img_path in split_images:
                    dest_path = split_class_dir / img_path.name
                    if not dest_path.exists():
                        shutil.copy2(img_path, dest_path)
            
            print(f" {class_name}: {len(images)} images")
            print(f"   Train: {len(train_images)}, Val: {len(val_images)}, Test: {len(test_images)}")
        
        # Print summary
        print("\n" + "="*60)
        print(" DATASET SUMMARY")
        print("="*60)
        print(f"Total classes: {len(class_stats)}")
        print(f"Total images: {total_images}")
        print(f"Training images: {sum(s['train'] for s in class_stats)}")
        print(f"Validation images: {sum(s['val'] for s in class_stats)}")
        print(f"Test images: {sum(s['test'] for s in class_stats)}")
        print(f"\n Dataset prepared at: {self.output_path}")
        
        # Save class names
        class_names = [s['name'] for s in class_stats]
        class_file = self.output_path / 'class_names.txt'
        with open(class_file, 'w') as f:
            f.write('\n'.join(class_names))
        print(f" Class names saved to: {class_file}")
        
        # Save disease info
        import json
        disease_file = self.output_path / 'disease_info.json'
        with open(disease_file, 'w') as f:
            json.dump(DISEASE_INFO, f, indent=2)
        print(f" Disease info saved to: {disease_file}")
        
        return True

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Prepare Smart Crop Dataset')
    parser.add_argument('--dataset_path', type=str, required=True, help='Path to Agrosight AI_dataset folder')
    parser.add_argument('--output_path', type=str, default='./processed', help='Output path for processed dataset')
    parser.add_argument('--use_color', type=bool, default=True, help='Use color images (recommended)')
    
    args = parser.parse_args()
    
    preparator = DatasetPreparator(
        dataset_path=args.dataset_path,
        output_path=args.output_path,
        use_color=args.use_color
    )
    
    preparator.prepare_dataset()

if __name__ == "__main__":
    main()