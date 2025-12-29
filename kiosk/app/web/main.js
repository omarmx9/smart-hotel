const captureBtn = document.getElementById('captureBtn');
const resetBtn = document.getElementById('resetBtn');
const statusMessage = document.getElementById('statusMessage');
const placeholder = document.getElementById('placeholder');
const loader = document.getElementById('loader');
const passportInfo = document.getElementById('passportInfo');
const countdown = document.getElementById('countdown');

let isCapturing = false;

captureBtn.addEventListener('click', async () => {
    if (isCapturing) return;
    
    isCapturing = true;
    captureBtn.disabled = true;
    
    // Show countdown
    countdown.style.display = 'block';
    let count = 2;
    countdown.textContent = count;
    
    const countdownInterval = setInterval(() => {
        count--;
        if (count > 0) {
            countdown.textContent = count;
        } else {
            clearInterval(countdownInterval);
            countdown.textContent = '📸';
            setTimeout(() => {
                countdown.style.display = 'none';
                capturePassport();
            }, 500);
        }
    }, 1000);
});

async function capturePassport() {
    // Hide placeholder, show loader
    placeholder.style.display = 'none';
    passportInfo.style.display = 'none';
    loader.style.display = 'block';
    statusMessage.style.display = 'none';
    
    try {
        const response = await fetch('/capture', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        loader.style.display = 'none';
        
        if (result.success) {
            // Display passport data
            displayPassportData(result.data);
            showStatus('Passport scanned successfully!', 'success');
            resetBtn.disabled = false;
        } else {
            placeholder.style.display = 'block';
            showStatus('Error: ' + result.error, 'error');
            captureBtn.disabled = false;
            isCapturing = false;
        }
    } catch (error) {
        loader.style.display = 'none';
        placeholder.style.display = 'block';
        showStatus('Error: ' + error.message, 'error');
        captureBtn.disabled = false;
        isCapturing = false;
    }
}

function displayPassportData(data) {
    // Map the actual field names from FastMRZ to the display fields
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

resetBtn.addEventListener('click', () => {
    placeholder.style.display = 'block';
    passportInfo.style.display = 'none';
    statusMessage.style.display = 'none';
    captureBtn.disabled = false;
    resetBtn.disabled = true;
    isCapturing = false;
});

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