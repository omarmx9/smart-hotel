// CameraWebServer_fixed.ino
#include <Arduino.h>
#include <WiFi.h>
#include <FS.h>
#include <SD_MMC.h>
#include "esp_camera.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_http_server.h"
#include "board_config.h"
#include "camera_pins.h"

// ===========================
// Enter your WiFi credentials
// ===========================
const char* ssid = "omar";
const char* password = "12345678";

// ===========================
// Global Variables
// ===========================
httpd_handle_t camera_httpd = NULL;
httpd_handle_t stream_httpd = NULL;  // Separate server for streaming
String currentPerson = "";
int imageCounter = 0;
bool sdCardAvailable = false;
bool useJPEG = false; // Set at runtime by sensor detection

// Lightweight serial debug helper
static inline void dbg(const char* msg) {
    Serial.println(msg);
}

// Small 1x1 PNG placeholder (shown when sensor cannot deliver JPEG previews)
static const unsigned char placeholder_png[] PROGMEM = {
  0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,
  0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,0x08,0x06,0x00,0x00,0x00,0x1F,0x15,0xC4,
  0x89,0x00,0x00,0x00,0x0A,0x49,0x44,0x41,0x54,0x78,0x9C,0x63,0x60,0x60,0x00,0x00,
  0x00,0x02,0x00,0x01,0xE2,0x21,0xBC,0x33,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,0x44,
  0xAE,0x42,0x60,0x82
};
static const size_t placeholder_png_len = sizeof(placeholder_png);

// ==================== HTML WEB INTERFACE ====================
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>ESP32-CAM Dataset Capture</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 30px;
        }
        h1 {
            color: #667eea;
            text-align: center;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .status {
            background: #f0f0f0;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }
        .status-item {
            display: inline-block;
            margin: 0 15px;
            font-size: 14px;
        }
        .status-label {
            font-weight: bold;
            color: #667eea;
        }
        .input-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: bold;
        }
        input[type="text"], select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border 0.3s;
        }
        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }
        .camera-container {
            position: relative;
            width: 100%;
            padding-bottom: 75%;
            background: #000;
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 20px;
        }
        #stream {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        .overlay {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 8px 12px;
            border-radius: 5px;
            font-size: 12px;
        }
        .controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        button {
            padding: 15px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            color: white;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .btn-success {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }
        .btn-warning {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        .btn-info {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        button:active {
            transform: translateY(0);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .tips {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
        }
        .tips h3 {
            color: #856404;
            margin-bottom: 10px;
            font-size: 16px;
        }
        .tips ul {
            margin-left: 20px;
            color: #856404;
        }
        .tips li {
            margin-bottom: 5px;
            font-size: 14px;
        }
        .debug-panel {
            background: #1a1a2e;
            color: #0f0;
            padding: 10px;
            border-radius: 8px;
            margin-top: 15px;
            font-family: monospace;
            font-size: 11px;
            max-height: 150px;
            overflow-y: auto;
        }
        .debug-panel h4 {
            color: #4facfe;
            margin-bottom: 8px;
        }
        .debug-log {
            margin: 2px 0;
        }
        .debug-log.error { color: #f5576c; }
        .debug-log.success { color: #38ef7d; }
        .debug-log.info { color: #4facfe; }
        .flash-indicator {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: white;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.1s;
        }
        .flash-indicator.active {
            opacity: 0.8;
        }
        @media (max-width: 600px) {
            .container { padding: 15px; }
            h1 { font-size: 24px; }
            .controls { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="flash-indicator" id="flashIndicator"></div>
    <div class="container">
        <h1>Dataset Capture</h1>
        <p class="subtitle">Capture high-quality training images for face recognition</p>
        
        <div class="status">
            <div class="status-item">
                <span class="status-label">Person:</span>
                <span id="currentPerson">Not set</span>
            </div>
            <div class="status-item">
                <span class="status-label">Images:</span>
                <span id="imageCount">0</span>
            </div>
            <div class="status-item">
                <span class="status-label">SD Card:</span>
                <span id="sdStatus">Checking...</span>
            </div>
        </div>

        <div class="input-group">
            <label for="personName">Person Name:</label>
            <input type="text" id="personName" placeholder="Enter name (e.g., john_doe)" 
                   pattern="[a-zA-Z0-9_]+" title="Use only letters, numbers, and underscores">
        </div>

        <div class="input-group">
            <label for="resolution">Resolution (RHYX M21-45 max: 240x240):</label>
            <select id="resolution" onchange="changeResolution()">
                <option value="10" disabled>UXGA (1600x1200) - Not supported</option>
                <option value="9" disabled>SXGA (1280x1024) - Not supported</option>
                <option value="8" disabled>XGA (1024x768) - Not supported</option>
                <option value="7" disabled>SVGA (800x600) - Not supported</option>
                <option value="6" disabled>VGA (640x480) - Not supported</option>
                <option value="5" disabled>CIF (400x296) - Not supported</option>
                <option value="4" disabled>QVGA (320x240) - Not supported</option>
                <option value="3" disabled>HQVGA (240x176) - Not supported</option>
                <option value="2" disabled>QCIF (176x144) - Not supported</option>
                <option value="1" disabled>QQVGA (160x120) - Not supported</option>
                <option value="17" selected>240x240 - ONLY supported size!</option>
                <option value="5">CIF (400x296)</option>
                <option value="4">QVGA (320x240)</option>
                <option value="3">HQVGA (240x176)</option>
                <option value="2">QCIF (176x144)</option>
                <option value="1">QQVGA (160x120)</option>
            </select>
        </div>

        <div class="input-group">
            <label for="captureMode">Capture Mode:</label>
            <select id="captureMode">
                <option value="single">Single Shot</option>
                <option value="burst">Burst (5 images)</option>
                <option value="auto">Auto (1 per 2 seconds)</option>
            </select>
        </div>

        <div class="camera-container">
            <img id="stream" src="">
            <div class="overlay" id="overlay">Ready</div>
        </div>

        <div class="controls">
            <button class="btn-primary" onclick="setPersonName()">Set Name</button>
            <button class="btn-success" onclick="captureImage()" id="captureBtn">Capture</button>
            <button class="btn-warning" onclick="toggleAuto()" id="autoBtn">Start Auto</button>
            <button class="btn-info" onclick="resetCounter()">Reset Count</button>
        </div>

        <div class="debug-panel" id="debugPanel">
            <h4>Debug Log:</h4>
            <div id="debugLog"></div>
        </div>

        <div class="tips">
            <h3>Tips for Best Results:</h3>
            <ul>
                <li><strong>⚠️ RHYX M21-45 is limited to 240x240 resolution only!</strong></li>
                <li>This sensor has NO hardware JPEG encoder</li>
                <li>Capture 25-30 images per person minimum</li>
                <li>Vary head angles and expressions</li>
                <li>Different lighting conditions</li>
                <li>Include glasses/hats if normally worn</li>
            </ul>
        </div>
    </div>

    <script>
        let autoCapture = false;
        let autoInterval = null;
        // Stream runs on port 81 to avoid blocking API calls
        let streamUrl = window.location.protocol + '//' + window.location.hostname + ':81/stream';

        function debug(msg, type = 'info') {
            const log = document.getElementById('debugLog');
            const time = new Date().toLocaleTimeString();
            const div = document.createElement('div');
            div.className = 'debug-log ' + type;
            div.textContent = '[' + time + '] ' + msg;
            log.insertBefore(div, log.firstChild);
            // Keep only last 20 entries
            while(log.children.length > 20) {
                log.removeChild(log.lastChild);
            }
            console.log('[DEBUG ' + type + ']', msg);
        }

        // Initialize stream
        document.getElementById('stream').src = streamUrl;
        debug('Stream URL: ' + streamUrl, 'info');
        debug('Page loaded, fetching status...', 'info');

        // Check SD card status on load
        fetch('/status')
            .then(r => {
                debug('Status response: ' + r.status, r.ok ? 'success' : 'error');
                return r.json();
            })
            .then(data => {
                debug('Status data: ' + JSON.stringify(data), 'success');
                document.getElementById('sdStatus').textContent = 
                    data.sdCard ? '✓ Ready' : '✗ Not Found';
                document.getElementById('imageCount').textContent = data.imageCount;
                if(data.currentPerson && data.currentPerson !== '') {
                    document.getElementById('currentPerson').textContent = data.currentPerson;
                    debug('Person already set: ' + data.currentPerson, 'success');
                }
            })
            .catch(err => {
                document.getElementById('sdStatus').textContent = '? Error';
                debug('Status fetch error: ' + err, 'error');
            });

        function setPersonName() {
            const name = document.getElementById('personName').value.trim();
            debug('Setting person name: "' + name + '"', 'info');
            if(!name) {
                debug('Name is empty!', 'error');
                alert('Please enter a person name');
                return;
            }
            if(!/^[a-zA-Z0-9_]+$/.test(name)) {
                debug('Invalid name format', 'error');
                alert('Use only letters, numbers, and underscores');
                return;
            }

            fetch('/set-person?name=' + encodeURIComponent(name))
                .then(r => {
                    debug('set-person response: ' + r.status, r.ok ? 'success' : 'error');
                    return r.json();
                })
                .then(data => {
                    debug('set-person data: ' + JSON.stringify(data), data.success ? 'success' : 'error');
                    if(data.success) {
                        document.getElementById('currentPerson').textContent = name;
                        updateOverlay('Ready to capture for ' + name);
                        debug('Person set successfully: ' + name, 'success');
                    } else {
                        alert('Error: ' + data.message);
                    }
                })
                .catch(err => {
                    debug('set-person error: ' + err, 'error');
                });
        }

        function captureImage() {
            const mode = document.getElementById('captureMode').value;
            const person = document.getElementById('currentPerson').textContent;
            debug('Capture clicked - Mode: ' + mode + ', Person: ' + person, 'info');
            if(person === 'Not set') {
                debug('No person set! Please set a name first.', 'error');
                alert('Please set a person name first!');
                return;
            }
            if(mode === 'burst') {
                captureBurst();
            } else {
                captureSingle();
            }
        }

        function captureSingle() {
            debug('Capturing single image...', 'info');
            updateOverlay('Capturing...');
            flash();
            fetch('/capture')
                .then(r => {
                    debug('Capture response: ' + r.status, r.ok ? 'success' : 'error');
                    return r.json();
                })
                .then(data => {
                    debug('Capture result: ' + JSON.stringify(data), data.success ? 'success' : 'error');
                    if(data.success) {
                        document.getElementById('imageCount').textContent = data.imageCount;
                        updateOverlay('✓ Captured #' + data.imageCount);
                    } else {
                        updateOverlay('✗ Error: ' + data.message);
                    }
                })
                .catch(err => {
                    debug('Capture error: ' + err, 'error');
                    updateOverlay('✗ Capture failed');
                });
        }

        function captureBurst() {
            let count = 0;
            const total = 5;
            const interval = setInterval(() => {
                if(count >= total) {
                    clearInterval(interval);
                    updateOverlay('✓ Burst complete!');
                    return;
                }
                updateOverlay(`Burst ${count + 1}/${total}...`);
                flash();
                fetch('/capture')
                    .then(r => r.json())
                    .then(data => {
                        if(data.success) {
                            document.getElementById('imageCount').textContent = data.imageCount;
                        }
                    });
                count++;
            }, 500);
        }

        function toggleAuto() {
            const btn = document.getElementById('autoBtn');
            const mode = document.getElementById('captureMode');
            if(autoCapture) {
                clearInterval(autoInterval);
                autoCapture = false;
                btn.textContent = 'Start Auto';
                btn.className = 'btn-warning';
                mode.disabled = false;
                updateOverlay('Auto capture stopped');
            } else {
                mode.value = 'single';
                mode.disabled = true;
                autoCapture = true;
                btn.textContent = 'Stop Auto';
                btn.className = 'btn-warning';
                autoInterval = setInterval(() => {
                    captureSingle();
                }, 2000);
            }
        }

        function resetCounter() {
            if(confirm('Reset image counter? (Images will NOT be deleted)')) {
                fetch('/reset')
                    .then(r => r.json())
                    .then(data => {
                        document.getElementById('imageCount').textContent = '0';
                        updateOverlay('Counter reset');
                    });
            }
        }

        function updateOverlay(text) {
            document.getElementById('overlay').textContent = text;
        }

        function flash() {
            const indicator = document.getElementById('flashIndicator');
            indicator.classList.add('active');
            setTimeout(() => indicator.classList.remove('active'), 100);
        }

        function changeResolution() {
            const res = document.getElementById('resolution').value;
            const resNames = {'10':'UXGA','9':'SXGA','8':'XGA','7':'SVGA','6':'VGA','5':'CIF','4':'QVGA','3':'HQVGA','2':'QCIF','1':'QQVGA'};
            updateOverlay('Changing to ' + resNames[res] + '...');
            
            fetch('/control?var=framesize&val=' + res)
                .then(r => {
                    if(!r.ok) throw new Error('Request failed');
                    return r.json();
                })
                .then(data => {
                    if(data.success) {
                        updateOverlay('✓ Resolution: ' + resNames[res]);
                        // Force reload stream with new timestamp to break MJPEG connection
                        const stream = document.getElementById('stream');
                        stream.src = '';
                        setTimeout(() => {
                            stream.src = streamUrl + '?' + Date.now();
                        }, 200);
                    } else {
                        updateOverlay('✗ Failed to change resolution');
                    }
                })
                .catch(err => {
                    console.error('Resolution change error:', err);
                    updateOverlay('✗ Resolution change failed');
                });
        }

        // Stream error handling - auto retry
        document.getElementById('stream').onerror = function() {
            updateOverlay('Stream error - retrying...');
            setTimeout(() => {
                document.getElementById('stream').src = streamUrl + '?' + Date.now();
            }, 1000);
        };
    </script>
</body>
</html>
)rawliteral";

// ==================== SD CARD FUNCTIONS ====================

bool createPersonDirectory(String personName) {
    String path = "/dataset/" + personName;
    if(!SD_MMC.exists(path)) {
        if(SD_MMC.mkdir(path)) {
            Serial.println("Created directory: " + path);
            return true;
        } else {
            Serial.println("Failed to create directory: " + path);
            return false;
        }
    }
    return true;
}

int getImageCount(String personName) {
    String path = "/dataset/" + personName;
    File dir = SD_MMC.open(path);
    if(!dir || !dir.isDirectory()) {
        return 0;
    }
    
    int count = 0;
    File file = dir.openNextFile();
    while(file) {
        if(!file.isDirectory()) {
            count++;
        }
        file = dir.openNextFile();
    }
    return count;
}

bool saveImage(camera_fb_t* fb, String personName, int imageNum) {
    // choose extension and write accordingly
    String filenameBase = "/dataset/" + personName + "/img_" + String(imageNum);
    if (useJPEG && fb->format == PIXFORMAT_JPEG) {
        String filename = filenameBase + ".jpg";
        File file = SD_MMC.open(filename, FILE_WRITE);
        if(!file) {
            Serial.println("Failed to open file for writing: " + filename);
            return false;
        }
        file.write(fb->buf, fb->len);
        file.close();
        Serial.println("Saved: " + filename);
        return true;
    } else {
        // Save as PGM (P5) raw grayscale. This is easy to convert on PC.
        // Ensure fb->format is grayscale or RGB565. For RGB565 we'd need conversion,
        // but we configured sensor to GRAYSCALE fallback, so this will usually be GRAYSCALE.
        String filename = filenameBase + ".pgm";
        File file = SD_MMC.open(filename, FILE_WRITE);
        if(!file) {
            Serial.println("Failed to open file for writing: " + filename);
            return false;
        }
        // Write PGM header: P5\n<width> <height>\n255\n
        if (fb->width <= 0 || fb->height <= 0) {
            // fallback dimensions (should not happen)
            Serial.printf("Invalid fb dimensions: w=%d h=%d\n", fb->width, fb->height);
            file.close();
            return false;
        }
        String header = "P5\n" + String(fb->width) + " " + String(fb->height) + "\n255\n";
        file.print(header);
        file.write(fb->buf, fb->len);
        file.close();
        Serial.println("Saved (PGM): " + filename + "  bytes:" + String(fb->len));
        return true;
    }
}

// ==================== WEB SERVER HANDLERS ====================

static esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, (const char *)index_html, strlen(index_html));
}

static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t * fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t * _jpg_buf = NULL;
    char * part_buf[64];

    res = httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
    if(res != ESP_OK){
        return res;
    }

    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    while(true){
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("Camera capture failed");
            res = ESP_FAIL;
        } else {
            // Always convert to JPEG if not already in JPEG format
            if(fb->format != PIXFORMAT_JPEG){
                bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
                esp_camera_fb_return(fb);
                fb = NULL;
                if(!jpeg_converted){
                    Serial.println("JPEG compression failed");
                    res = ESP_FAIL;
                }
            } else {
                _jpg_buf_len = fb->len;
                _jpg_buf = fb->buf;
            }
        }
        if(res == ESP_OK){
            size_t hlen = snprintf((char *)part_buf, 64, "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", _jpg_buf_len);
            res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
        }
        if(res == ESP_OK){
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
        if(res == ESP_OK){
            res = httpd_resp_send_chunk(req, "\r\n--frame\r\n", 12);
        }
        if(fb){
            esp_camera_fb_return(fb);
            fb = NULL;
            _jpg_buf = NULL;
        } else if(_jpg_buf){
            free(_jpg_buf);
            _jpg_buf = NULL;
        }
        if(res != ESP_OK){
            break;
        }
    }
    return res;
}

static esp_err_t capture_handler(httpd_req_t *req) {
    dbg("[HTTP] /capture");
    if(currentPerson == "") {
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, "{\"success\":false,\"message\":\"No person set\"}", -1);
        return ESP_OK;
    }
    
    // Blink flash LED if available (non-blocking recommended, but keep simple here)
#if defined(LED_GPIO_NUM)
    digitalWrite(LED_GPIO_NUM, HIGH);
    delay(100);
    digitalWrite(LED_GPIO_NUM, LOW);
#endif
    
    camera_fb_t* fb = esp_camera_fb_get();
    if(!fb) {
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, "{\"success\":false,\"message\":\"Camera capture failed\"}", -1);
        return ESP_OK;
    }
    
    String response;
    if(sdCardAvailable) {
        imageCounter++;
        bool saved = saveImage(fb, currentPerson, imageCounter);
        esp_camera_fb_return(fb);
        
        if(saved) {
            response = "{\"success\":true,\"imageCount\":" + String(imageCounter) + "}";
        } else {
            response = "{\"success\":false,\"message\":\"Failed to save\"}";
        }
    } else {
        esp_camera_fb_return(fb);
        response = "{\"success\":false,\"message\":\"SD card not available\"}";
    }
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, response.c_str(), response.length());
    return ESP_OK;
}

static esp_err_t set_person_handler(httpd_req_t *req) {
    dbg("[HTTP] /set-person");
    char buf[100];
    size_t buf_len;
    String response;
    
    buf_len = httpd_req_get_url_query_len(req) + 1;
    if (buf_len > 1) {
        if (httpd_req_get_url_query_str(req, buf, buf_len) == ESP_OK) {
            char param[32];
            if (httpd_query_key_value(buf, "name", param, sizeof(param)) == ESP_OK) {
                String name = String(param);
                currentPerson = name;
                
                if(sdCardAvailable) {
                    if(createPersonDirectory(name)) {
                        imageCounter = getImageCount(name);
                        response = "{\"success\":true,\"imageCount\":" + String(imageCounter) + "}";
                    } else {
                        response = "{\"success\":true,\"imageCount\":0,\"warning\":\"Directory creation failed\"}";
                    }
                } else {
                    imageCounter = 0;
                    response = "{\"success\":true,\"imageCount\":0,\"warning\":\"SD card not available\"}";
                }
            } else {
                response = "{\"success\":false,\"message\":\"No name provided\"}";
            }
        }
    } else {
        response = "{\"success\":false,\"message\":\"No name provided\"}";
    }
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, response.c_str(), response.length());
    return ESP_OK;
}

static esp_err_t status_handler(httpd_req_t *req) {
    dbg("[HTTP] /status");
    String json = "{\"sdCard\":" + String(sdCardAvailable ? "true" : "false") +
                 ",\"imageCount\":" + String(imageCounter) +
                 ",\"currentPerson\":\"" + currentPerson + "\"}";
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, json.c_str(), json.length());
    return ESP_OK;
}

static esp_err_t reset_handler(httpd_req_t *req) {
    dbg("[HTTP] /reset (counter->0)");
    imageCounter = 0;
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, "{\"success\":true}", -1);
    return ESP_OK;
}

static esp_err_t control_handler(httpd_req_t *req) {
    dbg("[HTTP] /control");
    char buf[100];
    String response = "{\"success\":false}";
    
    size_t buf_len = httpd_req_get_url_query_len(req) + 1;
    if (buf_len > 1) {
        if (httpd_req_get_url_query_str(req, buf, buf_len) == ESP_OK) {
            char var[32];
            char val[32];
            
            if (httpd_query_key_value(buf, "var", var, sizeof(var)) == ESP_OK &&
                httpd_query_key_value(buf, "val", val, sizeof(val)) == ESP_OK) {
                
                sensor_t * s = esp_camera_sensor_get();
                int res = 0;
                
                if(!strcmp(var, "framesize")) {
                    if(s->pixformat == PIXFORMAT_JPEG) {
                        res = s->set_framesize(s, (framesize_t)atoi(val));
                        response = "{\"success\":true}";
                    }
                }
                else if(!strcmp(var, "quality")) res = s->set_quality(s, atoi(val));
                else if(!strcmp(var, "contrast")) res = s->set_contrast(s, atoi(val));
                else if(!strcmp(var, "brightness")) res = s->set_brightness(s, atoi(val));
                else if(!strcmp(var, "saturation")) res = s->set_saturation(s, atoi(val));
                else {
                    response = "{\"success\":false,\"message\":\"Unknown variable\"}";
                }
                
                if(res == 0 && response == "{\"success\":false}") {
                    response = "{\"success\":true}";
                }
            }
        }
    }
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, response.c_str(), response.length());
    return ESP_OK;
}

void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.max_open_sockets = 7;  // Increase max connections

    httpd_uri_t index_uri = {
        .uri       = "/",
        .method    = HTTP_GET,
        .handler   = index_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t capture_uri = {
        .uri       = "/capture",
        .method    = HTTP_GET,
        .handler   = capture_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t set_person_uri = {
        .uri       = "/set-person",
        .method    = HTTP_GET,
        .handler   = set_person_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t status_uri = {
        .uri       = "/status",
        .method    = HTTP_GET,
        .handler   = status_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t reset_uri = {
        .uri       = "/reset",
        .method    = HTTP_GET,
        .handler   = reset_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t control_uri = {
        .uri       = "/control",
        .method    = HTTP_GET,
        .handler   = control_handler,
        .user_ctx  = NULL
    };

    // Start main server on port 80
    dbg("[HTTP] Starting server on port 80...");
    if (httpd_start(&camera_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(camera_httpd, &index_uri);
        httpd_register_uri_handler(camera_httpd, &capture_uri);
        httpd_register_uri_handler(camera_httpd, &set_person_uri);
        httpd_register_uri_handler(camera_httpd, &status_uri);
        httpd_register_uri_handler(camera_httpd, &reset_uri);
        httpd_register_uri_handler(camera_httpd, &control_uri);
        dbg("[HTTP] ✓ Server started on port 80");
    } else {
        dbg("[HTTP] ✗ Failed to start server on port 80");
    }

    // Start stream server on port 81 (separate to avoid blocking)
    config.server_port = 81;
    config.ctrl_port = 32769;  // Different control port
    
    httpd_uri_t stream_uri = {
        .uri       = "/stream",
        .method    = HTTP_GET,
        .handler   = stream_handler,
        .user_ctx  = NULL
    };

    dbg("[STREAM] Starting server on port 81...");
    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        dbg("[STREAM] ✓ Server started on port 81");
    } else {
        dbg("[STREAM] ✗ Failed to start stream server on port 81");
    }
}

void setupLedFlash() {
#if defined(LED_GPIO_NUM)
    pinMode(LED_GPIO_NUM, OUTPUT);
    digitalWrite(LED_GPIO_NUM, LOW);
#endif
}

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\n--- ESP32-CAM Dataset Capture ---");
    dbg("[BOOT] Init start");

  // 1. Camera basic config (use safe defaults)
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;  // RHYX M21-45 (GC2415) requires 20MHz
  // RHYX M21-45 config: NO JPEG encoder, limited by frame buffer size
  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size = FRAMESIZE_240X240;  // CRITICAL: Max size for this sensor!
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;  // Required for stability
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;  // For JPEG conversion in streaming
  config.fb_count = 2;  // Essential for this sensor

  // 2. Try initial init with safe defaults
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed (initial) with error 0x%x\n", err);
        dbg("[BOOT] Camera init failed initial");
    return;
  }

  // 3. Query sensor and check capabilities
  sensor_t * s = esp_camera_sensor_get();
  if (!s) {
    Serial.println("Sensor not detected after init");
        dbg("[BOOT] Sensor not detected");
    return;
  }
  Serial.printf("Sensor PID: 0x%x\n", s->id.PID);

  // RHYX M21-45 (GC2415) does NOT support hardware JPEG - uses RGB565
  if (s->id.PID == OV2640_PID || s->id.PID == OV3660_PID || s->id.PID == OV5640_PID) {
    Serial.println("JPEG-capable sensor detected; reconfiguring for JPEG previews...");
    // Deinit and re-init with JPEG config
    esp_camera_deinit();

    config.pixel_format = PIXFORMAT_JPEG;
    // prefer XGA for dataset preview; adjust if PSRAM present
    config.frame_size = FRAMESIZE_XGA;
    config.jpeg_quality = 10;
    if (psramFound()) {
      config.fb_count = 2;
      config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
      config.fb_count = 1;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }

    err = esp_camera_init(&config);
    if (err == ESP_OK) {
      useJPEG = true;
      Serial.println("Re-init JPEG OK. Streaming will provide JPEG frames.");
            dbg("[BOOT] JPEG re-init OK");
    } else {
      // if re-init fails, fall back to the already-inited grayscale session by re-initializing grayscale
      Serial.printf("Re-init with JPEG failed (0x%x). Falling back to RGB565.\n", err);
            dbg("[BOOT] JPEG re-init failed, fallback RGB565");
      // Attempt to re-init with RGB565 for RHYX M21-45
      esp_camera_deinit();
      config.pixel_format = PIXFORMAT_RGB565;
      config.frame_size = FRAMESIZE_240X240;  // RHYX M21-45 max resolution
      config.fb_location = CAMERA_FB_IN_PSRAM;
      config.fb_count = 2;
      config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
      err = esp_camera_init(&config);
      if (err != ESP_OK) {
        Serial.printf("Fallback re-init failed with error 0x%x\n", err);
        return;
      }
      useJPEG = false;
    }
  } else {
    Serial.println("Sensor is not JPEG-capable (RHYX M21-45/GC2415); using RGB565.");
    useJPEG = false;
        dbg("[BOOT] RHYX M21-45 detected, using RGB565");
  }

  // Final sensor pointer after (re-)init
  s = esp_camera_sensor_get();
  if (!s) {
    Serial.println("Sensor not available after final init");
    return;
  }

  // RHYX M21-45 minimal sensor tuning - keep it simple for stability
  // This sensor is different from OV series and doesn't support all settings

  // 4. Hardware stability pins (common recommended pins)
  pinMode(2, INPUT_PULLUP);
  pinMode(4, INPUT_PULLUP);
  pinMode(12, INPUT_PULLUP);
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
  pinMode(15, INPUT_PULLUP);

  // 5. Setup LED Flash if defined
#if defined(LED_GPIO_NUM)
  setupLedFlash();
#endif

  // 6. Initialize SD card
  if(!SD_MMC.begin("/sdcard", true)) {
    Serial.println("SD Card Mount Failed");
    sdCardAvailable = false;
        dbg("[BOOT] SD mount failed");
  } else {
    uint8_t cardType = SD_MMC.cardType();
    if(cardType == CARD_NONE) {
      Serial.println("No SD Card");
      sdCardAvailable = false;
    } else {
      sdCardAvailable = true;
      Serial.println("✓ SD Card initialized");
      Serial.printf("SD Card Size: %lluMB\n", SD_MMC.cardSize() / (1024 * 1024));
    dbg("[BOOT] SD ready");
      
      // Create base dataset directory
      if(!SD_MMC.exists("/dataset")) {
        SD_MMC.mkdir("/dataset");
        Serial.println("Created /dataset directory");
      }
    }
  }

  // 7. Connect WiFi
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);  // CRITICAL: Disable WiFi sleep for fast streaming!
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✓ WiFi Connected");
  Serial.print("Stream: http://");
  Serial.println(WiFi.localIP());
    dbg("[BOOT] WiFi connected");

  // 8. Start web server
  startCameraServer();
  Serial.println("✓ Web server started\n");
  Serial.println("Ready to capture dataset!");
  Serial.println("Open the IP address above in your web browser");
    dbg("[BOOT] Startup complete");
}

void loop() {
  // Nothing needed here - HTTP server handles everything
  delay(10);
}
