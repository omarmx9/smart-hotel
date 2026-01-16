# Smart Hotel Self Check-in Kiosk

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Django](https://img.shields.io/badge/Django-4.2+-green.svg)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-purple.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Status](https://img.shields.io/badge/status-production-success.svg)

> A production-ready, multilingual self-service check-in kiosk system for hotels featuring passport scanning, MRZ extraction, document generation, and multiple access methods.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Guest Journey](#guest-journey)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Internationalization](#internationalization)
- [Theming](#theming)
- [Implementation Status](#implementation-status)
- [Security](#security)

## Overview

The Smart Hotel Kiosk is a self-service check-in system designed for hotel lobbies. Guests can complete their entire check-in process without staff assistance—from passport scanning to keycard collection. The system integrates with the MRZ Automation AI backend for intelligent passport processing and supports multiple access methods including keycards and facial recognition.

Built with Django and modern web technologies, the kiosk provides a touch-friendly interface optimized for large displays while maintaining a professional, accessible design suitable for international guests.

## Features

### Passport Scanning & MRZ Extraction

- **Browser-based camera capture** - No hardware drivers required
- **Real-time document detection** - Visual feedback for positioning
- **Manual capture with automatic extraction** - Guests press a `Capture` button to take a high-quality frame; MRZ parsing is then performed via the microservice. An `Enter Manually` option is also available to type passport details when scanning is not possible.
- **Fallback processing** - Local parser when service unavailable
- **Multi-document support** - TD1, TD2, TD3 formats (passports, ID cards)

### Guest Check-in Flow

- **Multi-language support** - English, German, Polish, Ukrainian, Russian
- **Automatic form population** - MRZ data fills registration fields
- **Digital signatures** - Touch-enabled signature capture
- **PDF generation** - Registration cards for guest records
- **Front Desk integration** - Documents accessible to hotel staff
- **Reservation lookup** - Find booking by number or guest details

### Access Methods

- **Keycard encoding** - Traditional magnetic/RFID keycards
- **Facial recognition** - Camera-based enrollment for room access
- **PIN codes** - Backup access method
- **Multi-person support** - Register multiple guests per room

### Professional Theming

- **Seasonal themes** - Winter holiday theme with CSS decorations
- **Responsive design** - Optimized for kiosk displays (1080p+)
- **Accessibility** - High contrast, large touch targets
- **Branding ready** - Easy customization for hotel identity

## Architecture

The kiosk follows a **microservice architecture** where passport processing is handled by a separate MRZ backend service. This separation allows independent scaling and deployment. Communication uses WebSocket for real-time 24fps video streaming or HTTP fallback.

```mermaid
flowchart TB
    subgraph KIOSK["Smart Hotel Kiosk - Django + Channels"]
        subgraph FRONTEND["Frontend Layer"]
            TEMPLATES["Templates<br/>(Jinja2)"]
            STATIC["Static Files<br/>CSS/JS/i18n"]
            WSJS["WebSocket<br/>Client (24fps)"]
        end
        
        subgraph BACKEND["Backend Layer"]
            VIEWS["Views &<br/>Controllers"]
            EMULATOR["Emulator<br/>(SQLite)"]
            WSPROXY["WebSocket<br/>Proxy"]
        end
        
        subgraph SERVICES["Services Layer"]
            MRZ_CLIENT["MRZ API<br/>Client"]
            DOC_FILLER["Document<br/>Filler"]
        end
    end
    
    subgraph MRZ_BACKEND["MRZ Backend - Flask Microservice"]
        WSOCK["WebSocket<br/>/api/stream/ws"]
        REST["REST API"]
        
        CAPTURE["Layer 1<br/>Auto-Capture"]
        READJUST["Layer 2<br/>Enhancer"]
        EXTRACT["Layer 3<br/>MRZ Extract"]
        FILL["Layer 4<br/>Document Fill"]
        
        WSOCK --> CAPTURE
        REST --> CAPTURE
        CAPTURE --> READJUST
        READJUST --> EXTRACT
        EXTRACT --> FILL
    end
    
    subgraph GUEST["Guest"]
        CAMERA["Camera"]
        PASSPORT["Passport"]
    end

    GUEST --> TEMPLATES
    TEMPLATES <--> VIEWS
    WSJS <-->|Binary Frames| WSPROXY
    WSPROXY <-->|WebSocket| WSOCK
    VIEWS --> EMULATOR
    VIEWS --> MRZ_CLIENT
    MRZ_CLIENT --> REST
    VIEWS --> DOC_FILLER
```

### Component Responsibilities

| Component | Purpose |
| ----------- | --------- |
| **Kiosk (Django + Channels)** | Guest-facing web interface, session management, WebSocket proxy, business logic |
| **MRZ Backend (Flask)** | Passport image processing, YOLO detection, OCR, PDF generation, WebSocket streaming |
| **Emulator Module** | In-memory/SQLite data store for demo mode |
| **MRZ API Client** | HTTP client for microservice communication |
| **WebSocket Proxy** | Django Channels consumer for proxying WebSocket to Flask backend |
| **Document Filler** | DOCX template population with guest data |

### Data Flow

```mermaid
flowchart LR
    A["Guest"] -->|Camera Capture| B["Browser<br/>WebSocket"]
    B -->|24fps Binary| C["Django<br/>Channels"]
    C -->|WebSocket Proxy| D["MRZ Backend<br/>/api/stream/ws"]
    D --> E["YOLO Detection<br/>+ MRZ Extract"]
    E --> F["Detection<br/>Results JSON"]
    F -->|WebSocket| C
    C --> B
    B --> G["UI Update<br/>+ MRZ Data"]
    G --> H["Verification"]
    H --> I["Document<br/>Signing"]
    I --> J["Finalize"]
```

## Guest Journey

The kiosk follows a **strictly linear flow** - guests always progress forward, never looping back:

```mermaid
flowchart TD
    START[/"Advertisement Screen"/] --> LANG["Language Selection"]
    LANG --> CHECKIN["Check-in Start"]
    CHECKIN --> PASSPORT["Passport Scan<br/>+ Access Method Selection"]
    PASSPORT --> VERIFY["Verify Info"]
    
    VERIFY --> FOUND{"Reservation<br/>Found?"}
    
    FOUND -->|Yes| SIGN["Document Signing"]
    FOUND -->|No| WALKIN["Walk-in Flow"]
    WALKIN --> CREATE["Create Reservation<br/>Dates & Room Preferences"]
    CREATE --> SIGN
    
    SIGN --> ACCESS{"Access<br/>Method?"}
    
    ACCESS -->|Keycard Only| FINALIZE["Finalization<br/>Room & Keycard Details"]
    ACCESS -->|Face ID| ENROLL["Face Enrollment"]
    ACCESS -->|Both| ENROLL
    
    ENROLL --> FINALIZE
    
    style START fill:#4CAF50,color:#fff
    style FINALIZE fill:#2196F3,color:#fff
    style SIGN fill:#FF9800,color:#fff
    style VERIFY fill:#9C27B0,color:#fff
```

### Step 1: Advertisement & Language Selection

Guest approaches the kiosk and sees a welcome screen. They select their preferred language from 5 options: English, German, Polish, Ukrainian, or Russian.

### Step 2: Check-in Start

Guest chooses to begin the check-in process. Clear instructions guide them through each step.

### Step 3: Passport Scanning

The kiosk activates the camera for passport scanning:

- Real-time preview shows camera feed
- Green overlay indicates document detection
- Guest holds passport steady and presses **Capture** when positioned correctly
- System extracts MRZ data from the captured frame; alternatively the guest may choose **Enter Manually** to type their passport details
- **Access method selection** (Keycard, Face ID, or both) happens during this step

### Step 4: Information Verification

Extracted passport data is displayed for verification:

- First name, last name, date of birth
- Passport number and nationality
- Guest can edit any incorrect fields
- System looks up reservation by passport details

### Step 5: Walk-in or Reservation Found

- **Reservation Found**: Proceeds directly to document signing
- **Walk-in (No Reservation)**: Guest creates a new reservation with dates and room preferences

### Step 6: Document Signing

Guest signs the registration document:

- Digital signature via touch canvas
- Room is automatically assigned
- RFID keycard token is generated (if keycard selected)

### Step 7: Face Enrollment (Optional)

If guest selected Face ID access:

- Camera captures face images
- Images are enrolled for room access

### Step 8: Finalization

Check-in completes with:

- Room number and keycard details displayed
- Welcome information
- Option to report lost/stolen card

## Quick Start

### Local Development

```bash
# Navigate to kiosk directory
cd kiosk

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize database
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Run development server
python manage.py runserver 0.0.0.0:8000
```

Access the kiosk at `http://localhost:8000`

### Docker Deployment

```bash
# From project root
cd cloud

# Production mode
docker compose up kiosk mrz-backend

# Development mode (exposes MRZ frontend for testing)
docker compose -f docker-compose-dev.yml up kiosk mrz-backend
```

## Configuration

### Environment Variables

| Variable | Description | Default |
| ----------- | ------------- | --------- |
| `DEBUG` | Django debug mode | `0` |
| `SECRET_KEY` | Django secret key | `replace-me-in-production` |
| `ALLOWED_HOSTS` | Allowed hostnames | `*` |
| `MRZ_SERVICE_URL` | MRZ backend URL | `http://mrz-backend:5000` |
| `FRONTDESK_DB` | Frontdesk database name | `frontdesk` |
| `FRONTDESK_DB_USER` | Frontdesk database user | `frontdesk` |
| `FRONTDESK_DB_PASSWORD` | Frontdesk database password | (required) |
| `FRONTDESK_DB_HOST` | Frontdesk database host | `postgres-frontdesk` |
| `FRONTDESK_DB_PORT` | Frontdesk database port | `5432` |

### Frontdesk Database Integration

The kiosk connects to the **Frontdesk PostgreSQL database** to access real reservation data. This integration enables:

- **Reservation lookup** - Find guest bookings by confirmation number or name
- **Guest data sync** - MRZ-scanned passport data is saved to frontdesk database
- **Document storage** - Passport images and signed registration forms are linked to guest records
- **Check-in updates** - Reservation status updates flow back to frontdesk

When `FRONTDESK_DB_PASSWORD` is set, the kiosk queries the frontdesk database for reservations. If not configured, it falls back to in-memory storage for development.

### Settings Overview

Key settings in `kiosk_project/settings.py`:

```python
# MRZ Service Configuration
MRZ_SERVICE_URL = os.environ.get('MRZ_SERVICE_URL', 'http://localhost:5000')

# Media directories
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
TEMP_SCANS_DIR = os.path.join(MEDIA_ROOT, 'temp_scans')
FILLED_DOCS_DIR = os.path.join(MEDIA_ROOT, 'filled_documents')
```

## API Reference

### Guest Flow Pages

| Endpoint | Method | Description |
| ---------- | -------- | ------------- |
| `/` | GET | Welcome/advertisement screen |
| `/language/` | GET | Language selection |
| `/checkin/start/` | GET | Check-in start |
| `/checkin/passport/` | GET | Passport scan start |
| `/checkin/passport-scan/` | GET | Browser camera passport scan |
| `/verify/` | GET/POST | Verify extracted information |
| `/call-front-desk/` | GET | Error page (Call Front Desk) |

### Document Signing

| Endpoint | Method | Description |
| ---------- | -------- | ------------- |
| `/document/sign/` | GET/POST | Main signing route |
| `/document/preview-pdf/` | GET | Serve preview PDF |
| `/document/print/` | POST | Print PDF |

### Walk-in & Reservation

| Endpoint | Method | Description |
| ---------- | -------- | ------------- |
| `/walkin/` | GET | Walk-in flow |
| `/reservation/` | GET/POST | Reservation lookup |
| `/choose-access/<res_id>/` | GET | Access method selection |
| `/enroll-face/<res_id>/` | GET | Facial recognition enrollment |
| `/face-capture/<res_id>/` | GET | Browser camera face capture |
| `/save-faces/<res_id>/` | POST | Save enrolled faces |
| `/final/<res_id>/` | GET | Finalization |
| `/submit-keycards/<res_id>/` | POST | Submit keycards |
| `/report-card/<res_id>/` | POST | Report stolen/lost card |

### Django API Endpoints

| Endpoint | Method | Description |
| ---------- | -------- | ------------- |
| `/api/save-passport-data/` | POST | Save passport data |
| `/api/mrz/update/` | POST | Update document |
| `/api/document/preview/` | POST | Preview document |
| `/api/document/sign/` | POST | Sign document |
| `/api/document/submit-physical/` | POST | Submit physical document |
| `/api/documents/signed/` | GET | List signed documents |
| `/api/document/<id>/` | GET | Get signed document |
| `/api/passports/images/` | GET | List passport images |
| `/api/passport/<id>/` | GET | Get passport image |
| `/api/guest/create/` | POST | Create guest account |
| `/api/guest/deactivate/` | POST | Deactivate guest account |
| `/api/rfid/revoke/` | POST | Revoke RFID card |

### MRZ Backend Proxy Endpoints (Django → Flask)

| Endpoint | Method | Description |
| ---------- | -------- | ------------- |
| `/api/mrz/stream/ws/` | **WebSocket** | Real-time 24fps video streaming proxy |
| `/api/mrz/detect/` | POST | Proxy to Flask `/api/detect` |
| `/api/mrz/extract/` | POST | Proxy to Flask `/api/extract` |
| `/api/mrz/health/` | GET | Proxy to Flask `/health` |
| `/api/mrz/stream/session/` | POST | Create stream session |
| `/api/mrz/stream/session/<id>/` | DELETE | Close stream session |
| `/api/mrz/stream/frame/` | POST | Process single frame |
| `/api/mrz/stream/capture/` | POST | Capture best frame |
| `/api/mrz/stream/video/frames/` | POST | Process batch of frames |
| `/api/mrz/stream/video/` | POST | Process video chunk |

## Project Structure

```text
kiosk/
├── manage.py                   # Django management script
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container build instructions
├── docker-entrypoint.sh        # Container startup script
│
├── kiosk/                      # Main application
│   ├── views.py                # View controllers
│   ├── urls.py                 # URL routing
│   ├── routing.py              # WebSocket URL routing (Channels)
│   ├── consumers.py            # WebSocket consumers (MRZ proxy)
│   ├── emulator.py             # In-memory data store
│   ├── mrz_parser.py           # Local MRZ parsing
│   ├── mrz_api_client.py       # MRZ service client
│   ├── document_filler.py      # DOCX template handling
│   └── context_processors.py   # Template context
│
├── kiosk_project/              # Django project settings
│   ├── settings.py             # Configuration (includes Channels)
│   ├── urls.py                 # Root URL config
│   ├── asgi.py                 # ASGI application (Daphne + WebSocket)
│   └── wsgi.py                 # WSGI application (fallback)
│
├── templates/                  # HTML templates
│   ├── base.html               # Base layout with theme
│   └── kiosk/                  # Kiosk-specific templates
│       ├── start.html
│       ├── passport_scan.html  # WebSocket video streaming
│       ├── verify.html
│       ├── dw_registration.html
│       └── ...
│
├── static/                     # Static assets
│   ├── css/
│   │   ├── style.css           # Main styles
│   │   └── christmas-theme.css # Holiday theme
│   ├── js/                     # JavaScript modules
│   ├── i18n/                   # Translation JSON files
│   └── vendor/                 # Third-party libraries
│
├── media/                      # User uploads
│   ├── temp_scans/             # Temporary passport images
│   └── filled_documents/       # Generated PDFs
│
└── app/                        # MRZ Backend (Flask)
    ├── app.py                  # Flask application (v3.3.0)
    ├── requirements.txt        # Flask dependencies
    ├── README.md               # MRZ Backend documentation
    ├── layer1_auto_capture/    # YOLO detection, stability
    ├── layer2_image_enhancer/  # Image processing
    ├── layer3_mrz/             # MRZ extraction (OCR)
    └── layer4_document_filling/ # PDF generation
```

## Internationalization

The kiosk supports 5 languages with client-side translation:

| Language | Code | Flag |
| ----------- | ------ | ------ |
| English | `en` | 🇬🇧 |
| German | `de` | 🇩🇪 |
| Polish | `pl` | 🇵🇱 |
| Ukrainian | `uk` | 🇺🇦 |
| Russian | `ru` | 🇷🇺 |

Translation files are stored in `static/i18n/` as JSON:

```json
{
  "welcome_title": "Welcome to Smart Hotel",
  "scan_passport": "Please scan your passport",
  "continue": "Continue"
}
```

Language selection persists in browser session storage.

## Theming

### Current Theme: Winter Holiday

The kiosk features a professional winter holiday theme with:

- Animated snowfall (CSS-only, no JavaScript)
- Frosted glass card effects
- Winter color palette (deep blue, evergreen, gold accents)
- Decorative evergreen trees in footer

### Customizing Themes

Themes are controlled via CSS files in `static/css/`:

```css
/* christmas-theme.css - CSS Variables */
:root {
    --brand: #1a5f2a;           /* Evergreen */
    --brand-light: #2e8b47;     /* Light pine */
    --accent: #c9a227;          /* Gold */
    --bg: #0a1628;              /* Deep winter blue */
    --card-bg: rgba(255, 255, 255, 0.05);
}
```

To create a new theme:

1. Copy `christmas-theme.css` as template
2. Modify CSS variables for your colors
3. Update decorative elements (snowfall, trees, etc.)
4. Link new stylesheet in `base.html`

## Implementation Status

✅ **Production Ready** - All core features implemented and security issues resolved.

### Completed Features
- ✅ **RFID token revocation on checkout** - Tokens are properly revoked when guests check out
- ✅ **Dashboard account deactivation** - Guest accounts are deactivated on checkout
- ✅ **Full document signing flow** - Complete audit trail for check-in/checkout
- ✅ **Error handling** - All error pages show "Call Front Desk" with graceful degradation
- ✅ **MRZ proxy endpoints** - Full WebSocket and HTTP streaming support
- ✅ **WebSocket 24fps streaming** - Real-time passport scanning via Django Channels

For development documentation, see [.readme/](.readme/) folder.

## Security

### Production Recommendations

- **Always set a unique `SECRET_KEY`** in production
- **Set `DEBUG=0`** to disable debug mode
- **Configure ALLOWED_HOSTS** with specific hostnames
- **Use HTTPS** for all kiosk communications
- **Restrict MRZ service** to internal network only
- **Review access logs** regularly for suspicious activity

### Data Handling

- Passport images are processed and immediately deleted
- Extracted data stored only in session/emulator
- PDF registration cards saved with timestamp naming
- No permanent storage of biometric data

### Input Validation

- All form inputs sanitized before processing
- File uploads restricted to image types
- MRZ data validated against check digits
- Session tokens prevent CSRF attacks
