/**
 * MRZ Scanner Test Frontend
 * Browser-based camera with auto-capture on document detection
 * 
 * NOTE: This is a test frontend and will be removed.
 * The production implementation is in the kiosk Django app.
 */

// DOM Elements
const videoElement = document.getElementById('videoElement');
const overlayCanvas = document.getElementById('overlayCanvas');
const startBtn = document.getElementById('startBtn');
const captureBtn = document.getElementById('captureBtn');
const stopBtn = document.getElementById('stopBtn');
const resetBtn = document.getElementById('resetBtn');
const autoCaptureCheckbox = document.getElementById('autoCapture');
const statusMessage = document.getElementById('statusMessage');
const placeholder = document.getElementById('placeholder');
const loader = document.getElementById('loader');
const passportInfo = document.getElementById('passportInfo');
const countdown = document.getElementById('countdown');
const detectionIndicator = document.getElementById('detectionIndicator');

// State
let stream = null;
let isCapturing = false;
let detectionInterval = null;
let consecutiveDetections = 0;
const DETECTION_THRESHOLD = 3; // Number of consecutive detections before auto-capture

// Camera constraints
const constraints = {
    video: {
        width: { ideal: 1920 },
        height: { ideal: 1080 },
        facingMode: 'environment' // Prefer back camera on mobile
    }
};

// Start camera
startBtn.addEventListener('click', async () => {
    try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
        videoElement.srcObject = stream;
        
        startBtn.disabled = true;
        captureBtn.disabled = false;
        stopBtn.disabled = false;
        
        showStatus('Camera started', 'success');
        
        // Start detection loop if auto-capture is enabled
        if (autoCaptureCheckbox.checked) {
            startDetectionLoop();
        }
        
        // Setup canvas for overlay
        videoElement.onloadedmetadata = () => {
            overlayCanvas.width = videoElement.videoWidth;
            overlayCanvas.height = videoElement.videoHeight;
        };
        
    } catch (error) {
        showStatus('Camera access denied: ' + error.message, 'error');
    }
});

// Stop camera
stopBtn.addEventListener('click', () => {
    stopCamera();
});

// Reset for new scan
resetBtn.addEventListener('click', () => {
    placeholder.style.display = 'block';
    passportInfo.style.display = 'none';
    statusMessage.style.display = 'none';
    isCapturing = false;
    consecutiveDetections = 0;
    
    // Restart detection if camera is running
    if (stream && autoCaptureCheckbox.checked) {
        startDetectionLoop();
    }
});

// Toggle auto-capture
autoCaptureCheckbox.addEventListener('change', () => {
    if (autoCaptureCheckbox.checked && stream) {
        startDetectionLoop();
    } else {
        stopDetectionLoop();
    }
});

// Manual capture button
captureBtn.addEventListener('click', () => {
    if (!stream || isCapturing) return;
    performCapture(null); // null means capture new frame
});

function stopCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    videoElement.srcObject = null;
    startBtn.disabled = false;
    captureBtn.disabled = true;
    stopBtn.disabled = true;
    stopDetectionLoop();
    showStatus('Camera stopped', 'info');
}

function startDetectionLoop() {
    if (detectionInterval) return;
    
    detectionIndicator.classList.add('active');
    
    detectionInterval = setInterval(async () => {
        if (isCapturing || !stream) return;
        
        try {
            // Capture frame from video
            const canvas = document.createElement('canvas');
            canvas.width = videoElement.videoWidth;
            canvas.height = videoElement.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(videoElement, 0, 0);
            
            // Get base64 image
            const imageData = canvas.toDataURL('image/jpeg', 0.8).split(',')[1];
            
            // Send to detection endpoint
            const response = await fetch('/api/detect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: imageData })
            });
            
            const result = await response.json();
            
            if (result.detected && result.ready_for_capture) {
                consecutiveDetections++;
                updateDetectionIndicator(true, result.confidence);
                
                if (consecutiveDetections >= DETECTION_THRESHOLD) {
                    // Auto-capture!
                    stopDetectionLoop();
                    performCapture(imageData);
                }
            } else {
                consecutiveDetections = 0;
                updateDetectionIndicator(false, result.confidence || 0);
            }
            
        } catch (error) {
            console.error('Detection error:', error);
        }
        
    }, 500); // Check every 500ms
}

function stopDetectionLoop() {
    if (detectionInterval) {
        clearInterval(detectionInterval);
        detectionInterval = null;
    }
    detectionIndicator.classList.remove('active');
    consecutiveDetections = 0;
}

function updateDetectionIndicator(detected, confidence) {
    const dot = detectionIndicator.querySelector('.detection-dot');
    const text = detectionIndicator.querySelector('.detection-text');
    
    if (detected) {
        dot.classList.add('detected');
        text.textContent = `Document detected (${confidence.toFixed(1)}%)`;
    } else {
        dot.classList.remove('detected');
        text.textContent = 'Searching for document...';
    }
}

async function performCapture(imageData) {
    if (isCapturing) return;
    
    isCapturing = true;
    
    // Show countdown
    countdown.style.display = 'block';
    countdown.textContent = '📸';
    
    setTimeout(async () => {
        countdown.style.display = 'none';
        
        // Show loader
        placeholder.style.display = 'none';
        passportInfo.style.display = 'none';
        loader.style.display = 'block';
        statusMessage.style.display = 'none';
        
        try {
            // If no imageData provided, capture new frame
            if (!imageData) {
                const canvas = document.createElement('canvas');
                canvas.width = videoElement.videoWidth;
                canvas.height = videoElement.videoHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(videoElement, 0, 0);
                imageData = canvas.toDataURL('image/jpeg', 0.95).split(',')[1];
            }
            
            // Send to extraction endpoint
            const response = await fetch('/api/extract', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    image: imageData,
                    filename: 'browser_capture.jpg'
                })
            });
            
            const result = await response.json();
            
            loader.style.display = 'none';
            
            if (result.success) {
                displayPassportData(result.data);
                showStatus('Passport scanned successfully!', 'success');
            } else {
                placeholder.style.display = 'block';
                showDetailedError(result);
                isCapturing = false;
                
                // Restart detection
                if (autoCaptureCheckbox.checked && stream) {
                    setTimeout(() => startDetectionLoop(), 2000);
                }
            }
        } catch (error) {
            loader.style.display = 'none';
            placeholder.style.display = 'block';
            showStatus('Error: ' + error.message, 'error');
            isCapturing = false;
            
            // Restart detection
            if (autoCaptureCheckbox.checked && stream) {
                setTimeout(() => startDetectionLoop(), 2000);
            }
        }
    }, 500);
}

function displayPassportData(data) {
    document.getElementById('docType').textContent = data.mrz_type || data.document_code || '-';
    document.getElementById('country').textContent = data.issuer_code || '-';
    document.getElementById('surname').textContent = data.surname || '-';
    document.getElementById('givenNames').textContent = data.given_name || '-';
    document.getElementById('passportNumber').textContent = data.document_number || '-';
    document.getElementById('nationality').textContent = data.nationality_code || '-';
    document.getElementById('dob').textContent = data.birth_date || '-';
    document.getElementById('sex').textContent = data.sex || '-';
    document.getElementById('expiryDate').textContent = data.expiry_date || '-';
    document.getElementById('personalNumber').textContent = data.optional_data || '-';
    
    passportInfo.style.display = 'block';
}

function showStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = 'status-message status-' + type;
    statusMessage.style.display = 'block';
}

function showDetailedError(error) {
    let errorHtml = `<strong>${error.error || 'An error occurred'}</strong>`;
    
    if (error.error_code) {
        errorHtml += `<br><small>Error Code: ${error.error_code}</small>`;
    }
    
    if (error.details && error.details.suggestion) {
        errorHtml += `<br><br>💡 <em>${error.details.suggestion}</em>`;
    }
    
    statusMessage.innerHTML = errorHtml;
    statusMessage.className = 'status-message status-error';
    statusMessage.style.display = 'block';
}