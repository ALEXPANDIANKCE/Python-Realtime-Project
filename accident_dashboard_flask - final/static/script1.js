// Global variables
let map;
let alertModal;
let detectionActive = false;
let alertCheckInterval;
let videoFeedInterval;
let lastAlertTime = null;
const alertSound = new Audio('/static/alert.mp3'); // Make sure this file exists

// DOM Elements
const videoFeed = document.getElementById('videoFeed');
const startBtn = document.getElementById('startDetection');
const stopBtn = document.getElementById('stopDetection');
const alertList = document.getElementById('alertList');
const alertsToggle = document.getElementById('alertsToggle');
const logoutBtn = document.getElementById('logoutBtn');
const accidentCount = document.getElementById('accidentCount');
const fireCount = document.getElementById('fireCount');
const detectionStatus = document.getElementById('detectionStatus');
const lastAlertTimeElement = document.getElementById('lastAlertTime');

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize components
    initMap();
    initModal();
    setupEventListeners();
    fetchRecentAlerts();
    updateStatistics();
});

// Initialize Google Map
function initMap() {
    map = new google.maps.Map(document.getElementById('map'), {
        center: { lat: 12.9716, lng: 77.5946 }, // Default to Bangalore coordinates
        zoom: 14,
        mapTypeId: 'hybrid',
        styles: [
            {
                featureType: "poi",
                elementType: "labels",
                stylers: [{ visibility: "off" }]
            }
        ]
    });

    // Add initial marker
    new google.maps.Marker({
        position: { lat: 12.9716, lng: 77.5946 },
        map: map,
        title: 'Monitoring Center',
        icon: {
            url: "https://maps.google.com/mapfiles/ms/icons/blue-dot.png",
            scaledSize: new google.maps.Size(32, 32)
        }
    });
}

// Initialize Bootstrap Modal
function initModal() {
    alertModal = new bootstrap.Modal(document.getElementById('alertModal'));
}

// Set up event listeners
function setupEventListeners() {
    // Detection controls
    startBtn.addEventListener('click', startDetection);
    stopBtn.addEventListener('click', stopDetection);
    
    // Alert toggle
    alertsToggle.addEventListener('change', toggleAlerts);
    
    // Logout button
    logoutBtn.addEventListener('click', logout);
    
    // Modal buttons
    document.getElementById('viewOnMapBtn').addEventListener('click', viewOnMap);
    document.getElementById('dispatchBtn').addEventListener('click', dispatchEmergency);
    document.getElementById('falseAlarmBtn').addEventListener('click', markFalseAlarm);
    
    // Camera controls
    document.getElementById('startButton').addEventListener('click', startCamera);
    document.getElementById('stopButton').addEventListener('click', stopCamera);
}

// Start detection system
function startDetection() {
    if (detectionActive) return;
    
    fetch('/start_detection', { 
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        if (data.success) {
            detectionActive = true;
            updateControlButtons(true);
            startVideoFeed();
            startAlertPolling();
            showToast('Detection started successfully', 'success');
        }
    })
    .catch(error => {
        console.error('Error starting detection:', error);
        showToast('Failed to start detection', 'danger');
    });
}

// Stop detection system
function stopDetection() {
    fetch('/stop_detection', { 
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        if (data.success) {
            detectionActive = false;
            updateControlButtons(false);
            stopVideoFeed();
            stopAlertPolling();
            showToast('Detection stopped successfully', 'info');
        }
    })
    .catch(error => {
        console.error('Error stopping detection:', error);
        showToast('Failed to stop detection', 'danger');
    });
}

// Update control buttons state
function updateControlButtons(isActive) {
    startBtn.disabled = isActive;
    stopBtn.disabled = !isActive;
    detectionStatus.textContent = isActive ? 'ACTIVE' : 'INACTIVE';
    detectionStatus.className = isActive ? 'badge bg-success' : 'badge bg-secondary';
}

// Start video feed
function startVideoFeed() {
    if (videoFeedInterval) clearInterval(videoFeedInterval);
    videoFeedInterval = setInterval(() => {
        videoFeedElement.src = '/video_feed?' + new Date().getTime(); // Cache busting
    }, 100);
}

// Stop video feed
function stopVideoFeed() {
    if (videoFeedInterval) clearInterval(videoFeedInterval);
    videoFeed.src = '';
}

// Start polling for alerts
function startAlertPolling() {
    // Clear any existing interval
    if (alertCheckInterval) clearInterval(alertCheckInterval);
    
    // Check for alerts every 3 seconds
    alertCheckInterval = setInterval(checkForAlerts, 3000);
}

// Stop polling for alerts
function stopAlertPolling() {
    if (alertCheckInterval) clearInterval(alertCheckInterval);
}

// Check for new alerts
function checkForAlerts() {
    fetch('/api/alerts')
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        if (data.latest_alert && (!lastAlertTime || lastAlertTime !== data.latest_alert.time)) {
            lastAlertTime = data.latest_alert.time;
            handleNewAlert(data.latest_alert);
        }
        updateStatistics(data);
    })
    .catch(error => {
        console.error('Error checking alerts:', error);
    });
}

// Handle new alert
function handleNewAlert(alert) {
    // Add to alert list
    addAlertToList(alert);
    
    // Show modal if alerts are enabled
    if (alertsToggle.checked) {
        showAlertModal(alert);
    }
    
    // Play sound (muted if browser blocks autoplay)
    alertSound.play().catch(e => console.log('Audio play prevented:', e));
}

// Add alert to the list
function addAlertToList(alert) {
    const alertElement = document.createElement('div');
    alertElement.className = `alert-item ${alert.type === 'Accident' ? 'alert-danger' : 'alert-warning'} new-alert`;
    alertElement.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <strong><i class='bx ${alert.type === 'Accident' ? 'bxs-car-crash' : 'bxs-fire'}'></i> ${alert.type}</strong>
                <p class="mb-0 small">${alert.location || 'Location not available'}</p>
            </div>
            <div class="text-end">
                <small class="text-muted">${formatTime(alert.time)}</small>
                <span class="badge ${alert.type === 'Accident' ? 'bg-danger' : 'bg-warning'} ms-2">NEW</span>
            </div>
        </div>
    `;
    
    // Add click handler to show details
    alertElement.addEventListener('click', () => showAlertModal(alert));
    
    // Add to top of list
    alertList.insertBefore(alertElement, alertList.firstChild);
    
    // Limit to 50 alerts
    if (alertList.children.length > 50) {
        alertList.removeChild(alertList.lastChild);
    }
}

// Format time for display
function formatTime(timeString) {
    const date = new Date(timeString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Show alert modal with details
function showAlertModal(alert) {
    document.getElementById('alertModalTitle').textContent = `${alert.type} Detected!`;
    document.getElementById('alertTime').textContent = formatTime(alert.time);
    document.getElementById('alertLocation').textContent = alert.location || 'Location not available';
    document.getElementById('alertType').textContent = alert.type;
    
    // Set image (use placeholder if not available)
    const alertImage = document.getElementById('alertImage');
    alertImage.src = alert.image_path || '/static/no-image.jpg';
    alertImage.onerror = () => {
        alertImage.src = '/static/no-image.jpg';
    };
    
    // Add marker to map
    addAlertToMap(alert);
    
    // Show modal
    alertModal.show();
}

// Add alert location to map
function addAlertToMap(alert) {
    // For demo purposes, we'll add a marker near the default location
    // In a real app, you would geocode the actual location
    const lat = 12.9716 + (Math.random() * 0.02 - 0.01);
    const lng = 77.5946 + (Math.random() * 0.02 - 0.01);
    
    new google.maps.Marker({
        position: { lat, lng },
        map: map,
        title: alert.type,
        icon: {
            url: alert.type === 'Accident' ? 
                'https://maps.google.com/mapfiles/ms/icons/red-dot.png' :
                'https://maps.google.com/mapfiles/ms/icons/orange-dot.png',
            scaledSize: new google.maps.Size(32, 32)
        }
    });
    
    // Center map on the alert if it's the first one
    if (!map.getCenter() || !lastAlertTime) {
        map.setCenter({ lat, lng });
    }
}

// View alert on map
function viewOnMap() {
    alertModal.hide();
    document.getElementById('map').scrollIntoView({ 
        behavior: 'smooth',
        block: 'center'
    });
}

// Dispatch emergency services
function dispatchEmergency() {
    // In a real app, this would call your backend
    showToast('Emergency services have been notified!', 'success');
    alertModal.hide();
}

// Mark as false alarm
function markFalseAlarm() {
    // In a real app, this would call your backend
    showToast('Incident marked as false alarm', 'info');
    alertModal.hide();
}

// Toggle alerts
function toggleAlerts() {
    const status = alertsToggle.checked ? 'enabled' : 'disabled';
    showToast(`Alerts ${status}`, 'info');
}

// Fetch recent alerts on page load
function fetchRecentAlerts() {
    fetch('/api/alerts')
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        if (data.latest_alert) {
            lastAlertTime = data.latest_alert.time;
            addAlertToList(data.latest_alert);
        }
        updateStatistics(data);
    })
    .catch(error => {
        console.error('Error fetching alerts:', error);
    });
}

// Update statistics display
function updateStatistics(data) {
    if (!data) return;
    
    accidentCount.textContent = data.accident_count || 0;
    fireCount.textContent = data.fire_count || 0;
    
    if (data.latest_alert) {
        lastAlertTimeElement.textContent = formatTime(data.latest_alert.time);
    } else {
        lastAlertTimeElement.textContent = 'None';
    }
}

// Logout
function logout() {
    fetch('/logout')
    .then(() => {
        window.location.href = '/';
    })
    .catch(error => {
        console.error('Logout error:', error);
        showToast('Failed to logout', 'danger');
    });
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    const toastId = 'toast-' + Date.now();
    
    const toast = document.createElement('div');
    toast.className = `toast show align-items-center text-white bg-${type} border-0`;
    toast.role = 'alert';
    toast.id = toastId;
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        const toastElement = document.getElementById(toastId);
        if (toastElement) {
            toastElement.remove();
        }
    }, 5000);
}

// Handle page visibility changes
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible' && detectionActive) {
        // Refresh data when tab becomes active
        fetchRecentAlerts();
    }
});

// Camera script
document.addEventListener('DOMContentLoaded', () => {
    const videoFeedElement = document.getElementById('video-feed');
    const videoFeedContainer = document.getElementById('video-feed-container');
    const startCameraButton = document.getElementById('start-camera');
    const stopCameraButton = document.getElementById('stop-camera');

    // Start Camera
    startCameraButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/start_detection', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                alert('Camera started successfully!');
                videoFeedElement.src = '/video_feed';
                videoFeedContainer.classList.remove('hidden');
            } else {
                alert('Failed to start the camera.');
            }
        } catch (error) {
            console.error('Error starting camera:', error);
            alert('Error starting the camera.');
        }
    });

    // Stop Camera
    stopCameraButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/stop_detection', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                alert('Camera stopped successfully!');
                videoFeedElement.src = '';
                videoFeedContainer.classList.add('hidden');
            } else {
                alert('Failed to stop the camera.');
            }
        } catch (error) {
            console.error('Error stopping camera:', error);
            alert('Error stopping the camera.');
        }
    });
});