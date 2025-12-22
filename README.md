# MRZ Automation AI

A kiosk application for automated processing and recognition of Machine Readable Zone (MRZ) documents using AI.

## Project Structure

- **app.py** - Main application entry point
- **layers/** - Processing layers for document handling
  - `layer1_capture/` - Document capture functionality
  - `layer3_mrz/` - MRZ recognition and processing
- **models/** - Pre-trained models
  - `mrz.traineddata` - Trained MRZ recognition model
- **web/** - Frontend interface
  - `index.html` - Main HTML template
  - `main.js` - JavaScript logic
  - `style.css` - Styling
- **requirements.txt** - Python dependencies

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

## Requirements

See `requirements.txt` for all dependencies.

## License

[Add license information here]
