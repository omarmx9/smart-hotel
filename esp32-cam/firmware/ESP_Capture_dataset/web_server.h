// web_server.h - HTTP Server and Web Interface
#ifndef WEB_SERVER_H
#define WEB_SERVER_H

#include <WiFi.h>
#include "esp_http_server.h"
#include "esp_camera.h"
#include "cam_config.h"

// External variables (defined in main .ino file)
extern String currentPerson;
extern int imageCounter;
extern bool sdCardAvailable;
extern bool useJPEG;
extern bool continuousCapture;
extern bool ledFlashEnabled;
extern bool createPersonDirectory(String personName);
extern int getImageCount(String personName);
extern bool saveImage(camera_fb_t* fb, String personName, int imageNum);

// Server handles
httpd_handle_t camera_httpd = NULL;
httpd_handle_t stream_httpd = NULL;

// Debug helper
static inline void dbg(const char* msg) {
    Serial.println(msg);
}

// ==================== HTML WEB INTERFACE ====================
String getIndexHTML() {
    String resolutionLabel = SENSOR_NAME;
    resolutionLabel += " Resolution:";
    
    String html = R"rawliteral(
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
        .sensor-badge {
            background: #667eea;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            display: inline-block;
            margin-bottom: 20px;
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
        <h1>📸 Dataset Capture</h1>
        <p class="subtitle">Capture high-quality training images for face recognition</p>
        <div style="text-align: center;">
            <span class="sensor-badge">)rawliteral";
    
    html += SENSOR_NAME;
    html += R"rawliteral(</span>
        </div>
        
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
            <label for="resolution">)rawliteral";
    
    html += resolutionLabel;
    html += R"rawliteral(</label>
            <select id="resolution" onchange="changeResolution()">
)rawliteral";
    
    html += getSupportedResolutionsHTML();
    html += R"rawliteral(
            </select>
        </div>

        <div class="input-group">
            <label for="captureMode">Capture Mode:</label>
            <select id="captureMode">
                <option value="single">Single Shot</option>
                <option value="burst">Burst (5 images)</option>
                <option value="auto">Auto (1 per 2 seconds)</option>
                <option value="stream">Continuous Stream</option>
            </select>
        </div>

        <div class="input-group" style="display: flex; align-items: center; gap: 10px;">
            <input type="checkbox" id="ledFlash" onchange="toggleLED()" style="width: auto; cursor: pointer;">
            <label for="ledFlash" style="margin: 0; cursor: pointer;">💡 LED Flash</label>
        </div>

        <div class="camera-container">
            <img id="stream" src="">
            <div class="overlay" id="overlay">Ready</div>
        </div>

        <div class="controls">
            <button class="btn-primary" onclick="setPersonName()">Set Name</button>
            <button class="btn-success" onclick="captureImage()" id="captureBtn">Capture</button>
            <button class="btn-warning" onclick="toggleAuto()" id="autoBtn">Start Auto</button>
            <button class="btn-warning" onclick="toggleStream()" id="streamBtn" style="display:none;">Start Stream</button>
            <button class="btn-info" onclick="resetCounter()">Reset Count</button>
        </div>

        <div class="debug-panel" id="debugPanel">
            <h4>Debug Log:</h4>
            <div id="debugLog"></div>
        </div>

        <div class="tips">
            <h3>💡 Tips for Best Results:</h3>
            <ul>
)rawliteral";
    
    html += getSensorTipsHTML();
    html += R"rawliteral(
                <li>Capture 25-30 images per person minimum</li>
                <li>Vary head angles and expressions</li>
                <li>Different lighting conditions</li>
                <li>Include glasses/hats if normally worn</li>
                <li><strong>Use Continuous Stream</strong> mode to rapidly capture hundreds of images</li>
            </ul>
        </div>
    </div>

    <script>
        let autoCapture = false;
        let autoInterval = null;
        let streamCapture = false;
        let streamInterval = null;
        let streamUrl = window.location.protocol + '//' + window.location.hostname + ':81/stream';

        function debug(msg, type = 'info') {
            const log = document.getElementById('debugLog');
            const time = new Date().toLocaleTimeString();
            const div = document.createElement('div');
            div.className = 'debug-log ' + type;
            div.textContent = '[' + time + '] ' + msg;
            log.insertBefore(div, log.firstChild);
            while(log.children.length > 20) {
                log.removeChild(log.lastChild);
            }
            console.log('[DEBUG ' + type + ']', msg);
        }

        function updateOverlay(text) {
            document.getElementById('overlay').textContent = text;
        }

        function flash() {
            const indicator = document.getElementById('flashIndicator');
            indicator.classList.add('active');
            setTimeout(() => indicator.classList.remove('active'), 100);
        }

        function toggleLED() {
            const enabled = document.getElementById('ledFlash').checked;
            debug('LED flash: ' + (enabled ? 'enabled' : 'disabled'), 'info');
            fetch('/toggle-led?enabled=' + (enabled ? '1' : '0'))
                .then(r => r.json())
                .then(data => {
                    debug('LED toggle response: ' + JSON.stringify(data), 'success');
                    updateOverlay(enabled ? '💡 Flash enabled' : '🌑 Flash disabled');
                    setTimeout(() => updateOverlay('Ready'), 1500);
                })
                .catch(err => {
                    debug('LED toggle error: ' + err, 'error');
                });
        }

        document.getElementById('stream').src = streamUrl;
        debug('Stream URL: ' + streamUrl, 'info');
        debug('Sensor: )rawliteral";
    
    html += SENSOR_NAME;
    html += R"rawliteral(', 'info');

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
                if(data.ledFlash !== undefined) {
                    document.getElementById('ledFlash').checked = data.ledFlash;
                    debug('LED flash state: ' + (data.ledFlash ? 'enabled' : 'disabled'), 'info');
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

        // Show/hide controls based on capture mode
        document.getElementById('captureMode').addEventListener('change', function() {
            const mode = this.value;
            const captureBtn = document.getElementById('captureBtn');
            const autoBtn = document.getElementById('autoBtn');
            const streamBtn = document.getElementById('streamBtn');
            
            if(mode === 'stream') {
                captureBtn.style.display = 'none';
                autoBtn.style.display = 'none';
                streamBtn.style.display = 'block';
            } else if(mode === 'auto') {
                captureBtn.style.display = 'none';
                autoBtn.style.display = 'block';
                streamBtn.style.display = 'none';
            } else {
                captureBtn.style.display = 'block';
                autoBtn.style.display = 'none';
                streamBtn.style.display = 'none';
            }
        });

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

        function toggleStream() {
            const btn = document.getElementById('streamBtn');
            const mode = document.getElementById('captureMode');
            const person = document.getElementById('currentPerson').textContent;
            
            if(streamCapture) {
                debug('Stopping continuous stream...', 'info');
                fetch('/stop-stream')
                    .then(r => r.json())
                    .then(data => {
                        debug('Stream stopped: ' + JSON.stringify(data), 'success');
                        streamCapture = false;
                        btn.textContent = 'Start Stream';
                        btn.className = 'btn-warning';
                        mode.disabled = false;
                        clearInterval(streamInterval);
                        updateOverlay('Stream capture stopped - ' + data.totalCaptured + ' images');
                        document.getElementById('imageCount').textContent = data.imageCount;
                    })
                    .catch(err => {
                        debug('Stop stream error: ' + err, 'error');
                    });
            } else {
                if(person === 'Not set') {
                    debug('No person set! Please set a name first.', 'error');
                    alert('Please set a person name first!');
                    return;
                }
                debug('Starting continuous stream...', 'info');
                streamCapture = true;
                btn.textContent = 'Stop Stream';
                mode.disabled = true;

                function captureLoop() {
                    if(!streamCapture) return;
                    
                    fetch('/capture')
                        .then(r => r.json())
                        .then(data => {
                            if(data.success) {
                                document.getElementById('imageCount').textContent = data.imageCount;
                                updateOverlay('Streaming... ' + data.imageCount);
                            }
                            if(streamCapture) setTimeout(captureLoop, 200); // 5 imgs/sec
                        });
                }
                captureLoop();
                updateOverlay('Streaming... capturing images continuously');
            }
        }

        function resetCounter() {
            if(confirm('Reset image counter? (Images will NOT be deleted)')) {
                fetch('/reset')
                    .then r => r.json())
                    .then(data => {
                        document.getElementById('imageCount').textContent = '0';
                        updateOverlay('Counter reset');
                    });
            }
        }

        function changeResolution() {
            const res = document.getElementById('resolution').value;
            const resNames = {'10':'UXGA','9':'SXGA','8':'XGA','7':'SVGA','6':'VGA','5':'CIF','4':'QVGA','3':'HQVGA','2':'QCIF','1':'QQVGA','17':'240x240'};
            updateOverlay('Changing to ' + (resNames[res] || 'resolution') + '...');
            
            fetch('/control?var=framesize&val=' + res)
                .then(r => {
                    if(!r.ok) throw new Error('Request failed');
                    return r.json();
                })
                .then(data => {
                    if(data.success) {
                        updateOverlay('✓ Resolution: ' + (resNames[res] || res));
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
    
    return html;
}

// ==================== HTTP HANDLERS ====================

static esp_err_t index_handler(httpd_req_t *req) {
    String html = getIndexHTML();
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, html.c_str(), html.length());
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
    
#if defined(LED_GPIO_NUM)
    if(ledFlashEnabled) {
        digitalWrite(LED_GPIO_NUM, HIGH);
        delay(100);
        digitalWrite(LED_GPIO_NUM, LOW);
    }
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
                 ",\"currentPerson\":\"" + currentPerson + "\"" +
                 ",\"ledFlash\":" + String(ledFlashEnabled ? "true" : "false") + "}";
    
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

static esp_err_t start_stream_handler(httpd_req_t *req) {
    dbg("[HTTP] /start-stream");
    String response;
    
    if(currentPerson == "") {
        response = "{\"success\":false,\"message\":\"No person set\"}";
    } else if(!sdCardAvailable) {
        response = "{\"success\":false,\"message\":\"SD card not available\"}";
    } else {
        continuousCapture = true;
        response = "{\"success\":true}";
        dbg("[STREAM] Continuous capture started");
    }
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, response.c_str(), response.length());
    return ESP_OK;
}

static esp_err_t stop_stream_handler(httpd_req_t *req) {
    dbg("[HTTP] /stop-stream");
    continuousCapture = false;
    
    String response = "{\"success\":true,\"imageCount\":" + String(imageCounter) + 
                     ",\"totalCaptured\":" + String(imageCounter) + "}";
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, response.c_str(), response.length());
    dbg("[STREAM] Continuous capture stopped");
    return ESP_OK;
}

static esp_err_t toggle_led_handler(httpd_req_t *req) {
    dbg("[HTTP] /toggle-led");
    char buf[50];
    String response;
    
    size_t buf_len = httpd_req_get_url_query_len(req) + 1;
    if (buf_len > 1) {
        if (httpd_req_get_url_query_str(req, buf, buf_len) == ESP_OK) {
            char param[10];
            if (httpd_query_key_value(buf, "enabled", param, sizeof(param)) == ESP_OK) {
                ledFlashEnabled = (String(param) == "1");
                response = "{\"success\":true,\"ledFlash\":" + String(ledFlashEnabled ? "true" : "false") + "}";
                dbg(ledFlashEnabled ? "[LED] Flash enabled" : "[LED] Flash disabled");
            } else {
                response = "{\"success\":false,\"message\":\"No enabled parameter\"}";
            }
        }
    } else {
        response = "{\"success\":false,\"message\":\"No parameters\"}";
    }
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, response.c_str(), response.length());
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
                if(!s) {
                    response = "{\"success\":false,\"message\":\"Camera sensor not available\"}";
                } else {
                    int res = 0;
                    
                    if(!strcmp(var, "framesize")) {
                        res = s->set_framesize(s, (framesize_t)atoi(val));
                        if(res == 0) response = "{\"success\":true}";
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
                    } else if(res != 0) {
                        response = "{\"success\":false,\"message\":\"Failed to set " + String(var) + "\"}";
                    }
                }
            }
        }
    }
    
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, response.c_str(), response.length());
    return ESP_OK;
}

// ==================== START SERVER FUNCTION ====================
void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.max_open_sockets = 7;

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

    httpd_uri_t start_stream_uri = {
        .uri       = "/start-stream",
        .method    = HTTP_GET,
        .handler   = start_stream_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t stop_stream_uri = {
        .uri       = "/stop-stream",
        .method    = HTTP_GET,
        .handler   = stop_stream_handler,
        .user_ctx  = NULL
    };

    httpd_uri_t toggle_led_uri = {
        .uri       = "/toggle-led",
        .method    = HTTP_GET,
        .handler   = toggle_led_handler,
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
        httpd_register_uri_handler(camera_httpd, &start_stream_uri);
        httpd_register_uri_handler(camera_httpd, &stop_stream_uri);
        httpd_register_uri_handler(camera_httpd, &toggle_led_uri);
        dbg("[HTTP] ✓ Server started on port 80");
    } else {
        dbg("[HTTP] ✗ Failed to start server on port 80");
    }

    // Start stream server on port 81
    config.server_port = 81;
    config.ctrl_port = 32769;
    
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

#endif // WEB_SERVER_H
