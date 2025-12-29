# MRZ Automation AI

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green.svg)
![Flask](https://img.shields.io/badge/Flask-2.3+-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

> A production-ready passport scanning system that transforms live camera feeds into structured data through intelligent document processing.

## Table of Contents

- [Overview](#overview)
- [The Journey: From Camera to Data](#the-journey-from-camera-to-data)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Layer Documentation](#layer-documentation)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Development & Testing](#development--testing)

## Overview

MRZ Automation AI is a passport scanning system built for real-world conditions. Unlike solutions that work only with clean, scanned images, this system handles what actually happens when someone holds a passport in front of a camera: tilted angles, varying lighting, motion blur, and partial visibility.

The system takes you from a live camera feed to extracted, structured passport data in seconds—and saves everything along the way for complete audit and debugging capabilities. Every capture produces traceable artifacts, making the system suitable for both production deployments and compliance-heavy environments.

## The Journey: From Camera to Data

### Step 1: Live Camera Preview

You start the camera and see a live video feed. The system continuously analyzes each frame, looking for a rectangular document. When it spots one, a green overlay appears showing you exactly what it detected.

**What's happening behind the scenes:**
- Camera streams frames in real-time using OpenCV
- Each frame is quickly analyzed for document presence
- Visual feedback helps you position the passport correctly
- Detection metrics show coverage area percentage and confidence

**The user experience:** You see immediate visual feedback. Green box means "I see your passport." No green box means "position it better."

### Step 2: Capture Trigger

When you're ready, you hit "Capture". The system waits 2 seconds (giving you time to hold steady), then grabs a high-quality frame. This delay is intentional—it reduces motion blur and gives you a moment to perfect the positioning.

### Step 3: Document Detection & Correction

Your captured frame probably shows a tilted passport, uneven lighting, maybe some blur. This is where the real transformation happens. The system performs a series of intelligent corrections:

**Finding the Document:**
- Converts to grayscale and applies Gaussian blur to reduce noise
- Uses Canny edge detection to find document boundaries
- Identifies contours and filters for rectangular shapes
- Validates based on area and aspect ratio

**Fixing Perspective:**
- Identifies the four corners of the passport
- Calculates the perspective transformation matrix
- Warps the image to create a straight-on, flat view
- Output: a perfectly aligned document, as if scanned

**Enhancing for OCR:**
- Applies CLAHE (Contrast Limited Adaptive Histogram Equalization)
- Boosts text visibility even in poor lighting
- Uses bilateral filtering to reduce noise while preserving edges
- Result: a crisp, high-contrast image ready for text recognition

**Why this matters:** This is the crucial step that makes real-world capture work. Without correction, MRZ extraction would fail on most camera captures. With it, even shaky handheld shots become readable.

### Step 4: MRZ Extraction

Now the system reads the Machine Readable Zone—those two lines of characters at the bottom of the passport. Using FastMRZ, it decodes and structures all the fields:

**Extracted data includes:**
- Document type and issuing country code
- Full name (surname and given names)
- Passport number and nationality
- Date of birth, sex, and expiry date
- Personal ID number and check digits
- Raw MRZ lines for verification

Everything is validated and parsed into clean, structured JSON format. The system handles multiple document types (TD1, TD2, TD3) including passports, ID cards, and visas.

### Step 5: Saving Everything

Here's where traceability becomes critical. The system saves a complete audit trail:

**For every capture attempt:**
- The processed image (exactly what the OCR engine saw)
- A JSON file with all extracted data, timestamps, and metadata
- Both files linked by matching filenames with timestamps

**If extraction fails:**
- The image is still saved for debugging
- Error details are logged
- You can review exactly what went wrong

This audit trail is invaluable for debugging, compliance requirements, and quality improvement over time.

### Step 6: Document Filling (Optional)

If you've configured a DOCX template, the system automatically populates it with the extracted MRZ fields. This step is optional and non-critical—if it fails, your MRZ data remains safe and accessible.

**How it works:**
- Loads the DOCX template
- Maps MRZ fields to template placeholders (`{{SURNAME}}`, `{{PASSPORT_NUMBER}}`, etc.)
- Generates a filled document with timestamp
- Saves to the `filled_documents/` directory

**The beauty of separation:** Document filling failures don't invalidate the capture. You still have your MRZ data and can fill documents manually or retry later.

## Features

### Live Camera Integration
- Real-time video preview with MJPEG streaming
- Document detection overlay with visual feedback
- USB camera support with V4L2 backend (Linux) and DirectShow (Windows)
- Detection metrics showing document presence and coverage area

### Advanced Image Processing
- Automatic document detection using contour analysis
- Perspective correction to flatten tilted or skewed passports
- CLAHE contrast enhancement for text visibility in any lighting
- Bilateral filtering for noise reduction while preserving edges
- Handles challenging conditions: poor lighting, motion blur, partial visibility

### MRZ Extraction
- FastMRZ-powered optical character recognition
- Support for TD1, TD2, and TD3 document formats
- Structured JSON output with all MRZ fields
- Confidence scoring for extraction quality
- Validation of check digits and data integrity

### Document Automation
- Auto-fill DOCX templates using extracted data
- Customizable field mapping for different document types
- Non-blocking: failures don't invalidate successful extractions
- Template-based approach supports multiple output formats

### Complete Traceability
- Processed images saved for every capture attempt
- JSON results with timestamps and metadata
- Separate storage for successful and failed extractions
- Full audit trail for compliance and debugging
- Easy result inspection and quality verification

## Architecture

The system follows a clean **layered architecture** where each layer has a single responsibility and can be tested or replaced independently. This design emerged through iterative real-world testing—each layer addresses specific failure modes encountered in production conditions.

```
┌─────────────────────────────────────────────────────────┐
│                  ScannerCoordinator                     │
│         (Central orchestration & error handling)        │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌──────────────┐   ┌──────────────┐
│   Layer 1     │   │   Layer 2    │   │   Layer 3    │
│   Capture     │──▶│ Readjustment │──▶│ MRZ Extract  │
│               │   │              │   │   & Save     │
└───────────────┘   └──────────────┘   └──────────────┘
                                                │
                                                ▼
                                        ┌──────────────┐
                                        │   Layer 4    │
                                        │   Document   │
                                        │   Filling    │
                                        └──────────────┘
```

**Layer 1 - Capture**: Manages USB camera I/O, live preview streaming, and raw frame acquisition

**Layer 2 - Readjustment**: Converts real-world camera frames into OCR-ready images through detection, perspective correction, and enhancement

**Layer 3 - MRZ Extraction & Persistence**: Extracts structured data from processed images and maintains complete audit trail

**Layer 4 - Document Filling**: Automates document population by mapping MRZ fields to DOCX templates

### Design Principles

- **Separation of Concerns**: Each layer has one job and doesn't make pipeline control decisions
- **Independence**: Layers can be tested, debugged, and replaced without affecting others
- **Fail-Safe**: Critical failures stop the pipeline; non-critical failures (Layer 4) preserve successful extractions
- **Traceability**: Every operation leaves evidence for debugging and compliance
- **Extensibility**: New layers or alternative implementations can be added cleanly

### Why This Design?

This architecture wasn't planned upfront—it evolved through real-world testing:

**Started with**: Static passport images → Worked great, but not realistic

**Added Layer 1**: Live camera → Problem: MRZ extraction failed constantly (tilted documents, bad lighting)

**Added Layer 2**: Image correction → Problem: Extraction improved, but debugging failures was impossible

**Added Layer 3**: Traceability → Problem: Now we could debug, but wanted automation

**Added Layer 4**: Document filling → Result: Complete pipeline that handles real-world conditions

Each layer exists because a specific problem appeared in testing. Each failure made the system more robust. For the complete evolution story, see [DESIGN_JOURNEY.md](DESIGN_JOURNEY.md).

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/mrz-automation-ai.git
cd mrz-automation-ai

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py

# Open your browser
# Navigate to http://localhost:5000
```

The web interface will load with camera controls. Click "Start Camera" to begin.

### System Requirements

**Operating System**: Linux (recommended), Windows 10/11, or macOS 10.15+

**Hardware**: USB camera or built-in webcam, minimum 4GB RAM

**Python**: 3.10 or higher

**Linux users**: Ensure V4L2 support
```bash
ls /dev/video*  # Check available cameras
sudo apt-get install v4l-utils  # If needed
```

## Configuration

Configuration is centralized at the top of `app.py`. Modify these values before running:

```python
# Camera Configuration
CAMERA_INDEX = 0  # Device index: 0 for /dev/video0 (Linux) or first camera

# Directory Configuration
SAVE_DIR = "captured_passports"  # Base directory for all outputs
TEMPLATE_PATH = "templates/DWA_Registration_Card.docx"  # DOCX template

# OCR Configuration (optional, for future Tesseract integration)
TESSDATA_PATH = None
```

### Output Directory Structure

The system automatically creates this structure:

```
captured_passports/
├── captured_images/    # Processed images ready for OCR
└── captured_json/      # MRZ extraction results with metadata

filled_documents/       # Auto-filled DOCX files (Layer 4 output)
```

## Usage

### Web Interface Workflow

1. **Start the Application**
   ```bash
   python app.py
   ```
   Server starts on `http://localhost:5000`

2. **Initialize Camera**
   - Open the web interface
   - Click "Start Camera" button
   - Video feed appears with real-time preview

3. **Position Document**
   - Hold passport in camera view
   - Green overlay indicates successful detection
   - Metrics show detection status and coverage area
   - Center and flatten the document for best results

4. **Capture and Process**
   - Click "Capture" button
   - System waits 2 seconds for stabilization
   - Full pipeline executes automatically
   - Results appear in output directories

5. **Review Results**
   - Check terminal/logs for processing status
   - Inspect saved files in output directories
   - View extracted MRZ data in JSON format

### Programmatic Usage

Integrate the system into your own applications:

```python
from layer1_capture.camera import CameraManager
from layer2_readjustment.processor import DocumentProcessor
from layer3_mrz.extractor import MRZExtractor
from layer3_mrz.saver import ImageSaver

# Initialize components
camera = CameraManager(camera_index=0)
processor = DocumentProcessor()
extractor = MRZExtractor()
saver = ImageSaver(base_dir="captured_passports")

# Capture and process
camera.start()
frame = camera.get_frame()

# Process through pipeline
processed_image = processor.process_frame(frame)
mrz_data = extractor.extract(processed_image)

# Save results
image_path = saver.save_image(processed_image, prefix="scan")
json_path = saver.save_json(mrz_data, prefix="scan")

print(f"MRZ Data: {mrz_data}")
camera.stop()
```

## API Reference

The Flask server exposes RESTful endpoints for camera control and document processing.

### Camera Management

#### `POST /start_camera`
Initialize the camera and begin video streaming.

**Response**:
```json
{
  "status": "success",
  "message": "Camera started successfully"
}
```

#### `POST /stop_camera`
Release camera resources and stop streaming.

**Response**:
```json
{
  "status": "success",
  "message": "Camera stopped"
}
```

### Video Streaming

#### `GET /video_feed`
MJPEG stream with real-time document detection overlay.

**Response**: Continuous multipart image stream

**Features**:
- Green bounding box when document detected
- Detection metrics overlay
- Real-time visual feedback

#### `GET /detection_status`
Get current document detection metrics without video stream.

**Response**:
```json
{
  "detected": true,
  "area_percentage": 45.2,
  "timestamp": "2024-01-15T10:30:00.123Z"
}
```

### Document Processing

#### `POST /capture`
Trigger complete capture and processing pipeline.

**Response (Success)**:
```json
{
  "status": "success",
  "mrz_data": {
    "type": "P",
    "country": "USA",
    "surname": "SMITH",
    "given_names": "JOHN MICHAEL",
    "passport_number": "123456789",
    "nationality": "USA",
    "date_of_birth": "1990-01-01",
    "sex": "M",
    "expiry_date": "2030-01-01"
  },
  "image_path": "captured_passports/captured_images/scan_20240115_103000.png",
  "json_path": "captured_passports/captured_json/scan_20240115_103000.json",
  "timestamp": "2024-01-15T10:30:00.123Z"
}
```

**Response (Failure)**:
```json
{
  "status": "error",
  "message": "MRZ extraction failed",
  "details": "No valid MRZ data found in image",
  "image_path": "captured_passports/captured_images/failed_20240115_103000.png"
}
```

## Layer Documentation

### Layer 1: Capture

**Purpose**: Manage USB camera hardware and provide reliable frame acquisition.

**What it does:**
- Initializes camera with optimal settings
- Streams frames continuously for preview
- Captures high-quality frames on demand
- Handles camera errors and resource cleanup

**Why it exists:** Initial attempts with static images worked well but weren't realistic. Real deployments need live camera feeds, which introduce variability (motion, lighting, positioning) that must be handled at the source.

**Files**: `layer1_capture/camera.py`

### Layer 2: Readjustment

**Purpose**: Transform real-world camera frames into OCR-ready document images.

**What it does:**
- Detects documents within frame using contour analysis
- Applies perspective transformation to flatten tilted documents
- Enhances contrast with CLAHE for text visibility
- Reduces noise while preserving text edges

**Why it exists:** Moving from static images to live camera feeds caused MRZ extraction accuracy to drop dramatically. The problem wasn't OCR quality—it was image geometry. Real passports are tilted, skewed, and poorly lit. This layer normalizes those inputs before OCR.

**The transformation:**
```
Tilted camera capture → Document detection → Perspective correction → Enhancement → OCR-ready image
```

**Files**: `layer2_readjustment/processor.py`

### Layer 3: MRZ Extraction & Persistence

**Purpose**: Extract structured passport data and maintain complete audit trail.

**What it does:**
- Runs FastMRZ OCR on processed images
- Extracts and validates all MRZ fields
- Saves processed images with timestamps
- Persists extraction results as JSON
- Links images to corresponding data files

**Why it exists:** With improved image quality, MRZ extraction became reliable—but debugging failures was hard. When extraction failed, it was unclear if the image was bad, MRZ was partial, or OCR misread characters. This layer isolates OCR logic and ensures every attempt leaves evidence.

**Output structure:**
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "mrz_type": "TD3",
  "data": { /* all MRZ fields */ },
  "raw_mrz_lines": [ /* original text */ ]
}
```

**Files**: `layer3_mrz/extractor.py`, `layer3_mrz/saver.py`

### Layer 4: Document Filling

**Purpose**: Automate document population using extracted MRZ data.

**What it does:**
- Loads DOCX templates with placeholder fields
- Maps MRZ data to template placeholders
- Generates filled documents with timestamps
- Handles template and field errors gracefully

**Why it's separate:** Document filling can fail independently (missing template, invalid fields, write permissions) without invalidating a successful MRZ extraction. Keeping it isolated preserves pipeline robustness—the scan still succeeds even if automation fails.

**Field mapping example:**
```python
{
  "{{SURNAME}}": "SMITH",
  "{{GIVEN_NAMES}}": "JOHN",
  "{{PASSPORT_NUMBER}}": "123456789",
  "{{DATE_OF_BIRTH}}": "1990-01-01"
}
```

**Files**: `layer4_document_filling/filler.py`

## Project Structure

```
mrz-automation-ai/
│
├── app.py                          # Flask server + ScannerCoordinator
├── error_handlers.py               # Typed error classes
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── DESIGN_JOURNEY.md              # Architecture evolution story
│
├── layer1_capture/                 # Layer 1: Camera Management
│   ├── __init__.py
│   └── camera.py                   # CameraManager class
│
├── layer2_readjustment/            # Layer 2: Image Processing
│   ├── __init__.py
│   └── processor.py                # DocumentProcessor class
│
├── layer3_mrz/                     # Layer 3: MRZ Extraction
│   ├── __init__.py
│   ├── extractor.py                # MRZExtractor class
│   └── saver.py                    # ImageSaver class
│
├── layer4_document_filling/        # Layer 4: Document Automation
│   ├── __init__.py
│   └── filler.py                   # DocumentFiller class
│
├── web/                            # Frontend Assets
│   ├── index.html                  # Main web interface
│   └── static/
│       ├── css/
│       └── js/
│
├── templates/                      # DOCX Templates
│   └── DWA_Registration_Card.docx
│
├── models/                         # Optional: OCR Models
│
├── captured_passports/             # Output: Captures
│   ├── captured_images/
│   └── captured_json/
│
├── filled_documents/               # Output: Filled Documents
│
└── tests/                          # Test Suite
    ├── test_layer1_capture.py
    ├── test_layer2_readjustment.py
    ├── test_layer3_mrz.py
    └── test_layer4_filling.py
```

## Requirements

### Core Dependencies

**Python Version**: 3.10 or higher

**Required Packages**:
```
opencv-python>=4.8.0      # Computer vision and camera access
Flask>=2.3.0              # Web server and RESTful API
python-docx>=0.8.11       # DOCX template manipulation
fastmrz>=0.1.0            # MRZ optical character recognition
numpy>=1.24.0             # Numerical operations
Pillow>=10.0.0            # Image format support
```

### Installation

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import cv2; print(cv2.__version__)"
python -c "import fastmrz; print('FastMRZ OK')"
```

### System Dependencies

**Linux**:
```bash
# Camera support
sudo apt-get install v4l-utils

# Check camera devices
v4l2-ctl --list-devices
```

**Windows/macOS**: No additional system dependencies required

## Development & Testing

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-cov

# Run all tests
pytest tests/

# Run with coverage report
pytest --cov=. --cov-report=html tests/

# Run specific layer tests
pytest tests/test_layer2_readjustment.py -v
```

### Code Style

```bash
# Format code
black .

# Check style
flake8 . --max-line-length=100
```

### Debugging Tips

**Camera not detected:**
```bash
# Linux: List cameras
ls -l /dev/video*

# Test with OpenCV
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"
```

**MRZ extraction fails:**
1. Check saved image in `captured_passports/captured_images/`
2. Verify document is clearly visible and in focus
3. Ensure MRZ lines are complete (not cut off)
4. Try adjusting Layer 2 parameters

**Document filling fails:**
1. Verify template path in configuration
2. Check template has correct placeholders
3. Ensure write permissions for `filled_documents/` directory

---

**Built through iteration, designed for reality.**