#!/usr/bin/env python3
"""
Dataset Image Index Fixer
Renumbers all images in dataset folders sequentially after removing bad images.
"""

import os
import sys
from pathlib import Path
import shutil

def get_image_files(folder_path):
    """Get all image files from a folder sorted by name."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
    images = []
    
    for file in folder_path.iterdir():
        if file.is_file() and file.suffix.lower() in image_extensions:
            images.append(file)
    
    # Sort by current name to maintain some order
    images.sort(key=lambda x: x.name.lower())
    return images

def rename_images(folder_path, prefix="image", start_index=1, padding=3, dry_run=False):
    """
    Rename all images in a folder sequentially.
    
    Args:
        folder_path: Path to the folder containing images
        prefix: Prefix for renamed files (default: "image")
        start_index: Starting number (default: 1)
        padding: Number of digits for zero-padding (default: 3)
        dry_run: If True, only show what would be done without actually renaming
    """
    images = get_image_files(folder_path)
    
    if not images:
        print(f"  ⚠️  No images found in {folder_path.name}")
        return 0
    
    print(f"\n📁 Processing folder: {folder_path.name}")
    print(f"   Found {len(images)} images")
    
    # Create temporary names to avoid conflicts
    temp_mapping = []
    
    for idx, old_file in enumerate(images, start=start_index):
        extension = old_file.suffix.lower()
        new_name = f"{prefix}_{str(idx).zfill(padding)}{extension}"
        new_path = folder_path / new_name
        
        # Skip if already correctly named
        if old_file.name == new_name:
            continue
            
        temp_mapping.append((old_file, new_path, old_file.name, new_name))
    
    if not temp_mapping:
        print(f"   ✅ All images already correctly indexed!")
        return len(images)
    
    if dry_run:
        print(f"   🔍 DRY RUN - Would rename {len(temp_mapping)} files:")
        for old_file, new_path, old_name, new_name in temp_mapping[:5]:  # Show first 5
            print(f"      {old_name} → {new_name}")
        if len(temp_mapping) > 5:
            print(f"      ... and {len(temp_mapping) - 5} more")
    else:
        # Use temporary names first to avoid conflicts
        temp_files = []
        try:
            # Step 1: Rename to temporary names
            for old_file, new_path, old_name, new_name in temp_mapping:
                temp_name = folder_path / f"temp_{os.urandom(8).hex()}{old_file.suffix}"
                old_file.rename(temp_name)
                temp_files.append((temp_name, new_path))
            
            # Step 2: Rename to final names
            for temp_file, final_path in temp_files:
                temp_file.rename(final_path)
            
            print(f"   ✅ Renamed {len(temp_mapping)} files successfully!")
            
        except Exception as e:
            print(f"   ❌ Error during renaming: {e}")
            # Try to restore from temp files if possible
            for temp_file, _ in temp_files:
                if temp_file.exists():
                    print(f"   ⚠️  Temp file left behind: {temp_file.name}")
            return 0
    
    return len(images)

def process_dataset(dataset_path, prefix="image", start_index=1, padding=3, dry_run=False):
    """
    Process all person folders in the dataset directory.
    
    Args:
        dataset_path: Path to the dataset directory
        prefix: Prefix for renamed files
        start_index: Starting number for images
        padding: Number of digits for zero-padding
        dry_run: If True, only show what would be done
    """
    dataset_path = Path(dataset_path)
    
    if not dataset_path.exists():
        print(f"❌ Dataset path does not exist: {dataset_path}")
        return
    
    if not dataset_path.is_dir():
        print(f"❌ Path is not a directory: {dataset_path}")
        return
    
    print("=" * 60)
    print("🔧 Dataset Image Index Fixer")
    print("=" * 60)
    print(f"Dataset path: {dataset_path}")
    print(f"Naming format: {prefix}_XXX (padding: {padding})")
    print(f"Starting index: {start_index}")
    if dry_run:
        print("⚠️  DRY RUN MODE - No files will be modified")
    print("=" * 60)
    
    # Get all subdirectories (person folders)
    person_folders = [f for f in dataset_path.iterdir() if f.is_dir()]
    
    if not person_folders:
        print("❌ No person folders found in dataset!")
        return
    
    person_folders.sort(key=lambda x: x.name.lower())
    
    total_images = 0
    for person_folder in person_folders:
        count = rename_images(person_folder, prefix, start_index, padding, dry_run)
        total_images += count
    
    print("\n" + "=" * 60)
    print(f"✅ Done! Processed {total_images} images across {len(person_folders)} folders")
    if dry_run:
        print("⚠️  This was a DRY RUN. Run without --dry-run to apply changes.")
    print("=" * 60)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fix image indices in dataset folders after removing bad images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be changed
  python fix_dataset_index.py --dry-run
  
  # Actually rename files
  python fix_dataset_index.py
  
  # Use custom dataset path
  python fix_dataset_index.py --dataset /path/to/dataset
  
  # Use custom prefix and start from 0
  python fix_dataset_index.py --prefix img --start 0
        """
    )
    
    parser.add_argument(
        '--dataset',
        type=str,
        default='./dataset',
        help='Path to dataset directory (default: ./dataset)'
    )
    
    parser.add_argument(
        '--prefix',
        type=str,
        default='image',
        help='Prefix for renamed files (default: image)'
    )
    
    parser.add_argument(
        '--start',
        type=int,
        default=1,
        help='Starting index number (default: 1)'
    )
    
    parser.add_argument(
        '--padding',
        type=int,
        default=3,
        help='Number of digits for zero-padding (default: 3)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually renaming files'
    )
    
    args = parser.parse_args()
    
    try:
        process_dataset(
            args.dataset,
            args.prefix,
            args.start,
            args.padding,
            args.dry_run
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
