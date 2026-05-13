/**
 * Farmer Dashboard JavaScript
 * Complete working version
 */

// ============================================================
// CONFIGURATION
// ============================================================

const API_BASE_URL = (window.API_CONFIG && window.API_CONFIG.BASE_URL) ? window.API_CONFIG.BASE_URL : 'http://127.0.0.1:5000/api';

function getAuthHeaders() {
    const token = localStorage.getItem('sc_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return headers;
}

// State
let currentUser = null;
let currentChat = null;
let conversations = {};
let socket = null;
let onlineUsers = {};
let typingTimeout = null;
let nearbyAgrovets = []; // cached from backend API
let farmerGeo = { lat: null, lng: null };

// ============================================================
// GEOLOCATION HELPERS
// ============================================================

function getUserGeolocation() {
    return new Promise((resolve) => {
        if (!navigator.geolocation) {
            resolve({ lat: null, lng: null });
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
            () => resolve({ lat: null, lng: null }),
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
    });
}

async function updateBackendLocation(lat, lng) {
    try {
        const res = await fetch(API_BASE_URL + '/auth/location', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ latitude: lat, longitude: lng })
        });
        if (res.ok) {
            currentUser.latitude = lat;
            currentUser.longitude = lng;
            localStorage.setItem('AgroSightAI_current_user', JSON.stringify(currentUser));
        }
    } catch (e) {
        console.warn('Failed to update backend location:', e);
    }
}

async function loadNearbyAgrovets() {
    if (farmerGeo.lat == null || farmerGeo.lng == null) {
        // Fallback to old localStorage method
        return loadRegisteredAgrovetsLegacy();
    }
    try {
        const res = await fetch(
            API_BASE_URL + '/agrovets/nearby?lat=' + farmerGeo.lat + '&lng=' + farmerGeo.lng + '&radius=50&limit=50'
        );
        const data = await res.json();
        if (data.success) {
            nearbyAgrovets = data.agrovets || [];
            return nearbyAgrovets;
        }
    } catch (e) {
        console.warn('Nearby agrovets API failed, falling back to legacy:', e);
    }
    return loadRegisteredAgrovetsLegacy();
}

function loadRegisteredAgrovetsLegacy() {
    const users = JSON.parse(localStorage.getItem('AgroSightAI_users') || '[]');
    const agrovets = users.filter(u => u.role === 'agrovet');
    const farmerLocation = (currentUser?.location || '').toLowerCase();
    const farmerParts = farmerLocation.split(/[\s,]+/).filter(p => p.length > 2);
    agrovets.sort((a, b) => {
        const aScore = getLocationMatchScore(a.location, farmerParts);
        const bScore = getLocationMatchScore(b.location, farmerParts);
        return bScore - aScore;
    });
    return agrovets;
}

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', async function() {
    console.log('Farmer dashboard loading...');

    await checkAuth();
    initTheme();
    initNavigation();
    initMobileMenu();
    initMessaging();
    initProfile();
    initLogout();

    await loadDashboardData();
    renderAgrovetsGrid();
    renderMiniAgrovets();
    renderConversations();

    // Modern disease detection UI
    if (typeof window.DiseaseDetectionUI !== 'undefined') {
        window.DiseaseDetectionUI.init({ containerId: 'disease-detection', role: 'farmer' });
    }

    console.log('Dashboard initialized successfully!');
});

// ============================================================
// AUTHENTICATION
// ============================================================

async function checkAuth() {
    const userData = localStorage.getItem('AgroSightAI_current_user');
    const token = localStorage.getItem('sc_token');
    if (!userData || !token) {
        window.location.href = 'signin.html';
        return;
    }
    currentUser = JSON.parse(userData);

    // Validate token with backend
    try {
        const res = await fetch(API_BASE_URL + '/auth/me', { headers: getAuthHeaders() });
        if (res.status === 401) {
            localStorage.removeItem('sc_token');
            localStorage.removeItem('AgroSightAI_current_user');
            window.location.href = 'signin.html';
            return;
        }
        const data = await res.json();
        if (data.success && data.user) {
            currentUser = data.user;
            localStorage.setItem('AgroSightAI_current_user', JSON.stringify(currentUser));
        }
    } catch (e) {
        console.warn('Auth validation failed, using cached user.', e);
    }

    // Get geolocation and update backend
    const geo = await getUserGeolocation();
    if (geo.lat != null && geo.lng != null) {
        farmerGeo = geo;
        if (currentUser) {
            await updateBackendLocation(geo.lat, geo.lng);
        }
    } else if (currentUser?.latitude && currentUser?.longitude) {
        farmerGeo = { lat: currentUser.latitude, lng: currentUser.longitude };
    }

    console.log('User loaded:', currentUser.username);
    updateUserDisplay();
    updateGreeting();
}

function updateUserDisplay() {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    set('userName', currentUser.username.split(' ')[0]);
    set('userDisplayName', currentUser.username);
    set('navAvatar', currentUser.username[0].toUpperCase());
    set('profileUsername', currentUser.username);
    set('profileEmail', currentUser.email || '-');
    set('profilePhone', currentUser.phone || '-');
    set('profileLocation', currentUser.location || '-');
    set('profileDate', new Date(currentUser.createdAt || Date.now()).toLocaleDateString());
    set('profileNameLarge', currentUser.username);

    const sidebarAvatar = document.getElementById('sidebarAvatar');
    if (sidebarAvatar) sidebarAvatar.textContent = currentUser.username[0].toUpperCase();
    const sidebarUserName = document.getElementById('sidebarUserName');
    if (sidebarUserName) sidebarUserName.textContent = currentUser.username;

    if (currentUser.profilePicture) {
        const preview = document.getElementById('profilePreview');
        if (preview) preview.src = currentUser.profilePicture;
    }
}

function updateGreeting() {
    const hour = new Date().getHours();
    let greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    const el = document.getElementById('greetingText');
    if (el) el.textContent = greeting + '! Ready to protect your crops today?';
}

// ============================================================
// THEME
// ============================================================

function initTheme() {
    const savedTheme = localStorage.getItem('sc_theme') || localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('sc_theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('themeIcon');
    if (icon) icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    const mobileIcon = document.getElementById('mobileThemeIcon');
    if (mobileIcon) mobileIcon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
}

// ============================================================
// NAVIGATION
// ============================================================

function initNavigation() {
    document.querySelectorAll('.sidebar-nav li[data-section]').forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            navigateTo(this.getAttribute('data-section'));
        });
    });

    document.querySelectorAll('.action-btn[data-nav]').forEach(btn => {
        btn.addEventListener('click', function() {
            navigateTo(this.getAttribute('data-nav'));
        });
    });
}

function initMobileMenu() {
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const mobileThemeToggle = document.getElementById('mobileThemeToggle');

    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', function() {
            sidebar.classList.toggle('active');
            sidebarOverlay.classList.toggle('active');
            document.body.style.overflow = sidebar.classList.contains('active') ? 'hidden' : '';
        });
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', function() {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
            document.body.style.overflow = '';
        });
    }

    document.querySelectorAll('.sidebar-nav li[data-section]').forEach(item => {
        item.addEventListener('click', function() {
            if (sidebar) sidebar.classList.remove('active');
            if (sidebarOverlay) sidebarOverlay.classList.remove('active');
            document.body.style.overflow = '';
        });
    });

    if (mobileThemeToggle) {
        mobileThemeToggle.addEventListener('click', function() {
            toggleTheme();
        });
    }
}

function navigateTo(sectionId) {
    document.querySelectorAll('.sidebar-nav li').forEach(li => li.classList.remove('active'));
    const navItem = document.querySelector('.sidebar-nav li[data-section="' + sectionId + '"]');
    if (navItem) navItem.classList.add('active');

    document.querySelectorAll('.dashboard-section').forEach(s => s.classList.remove('active-section'));
    const section = document.getElementById(sectionId);
    if (section) section.classList.add('active-section');

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ============================================================
// DISEASE DETECTION (legacy helpers for new module)
// ============================================================

function showFeedbackForm() {
    if (!window._lastPrediction) {
        showToast('No prediction to report. Please analyze an image first.', 'error');
        return;
    }

    const pred = window._lastPrediction;
    const correctClass = prompt(
        'Report Wrong Prediction\n\n' +
        'Predicted: ' + (pred.disease || 'Unknown') + '\n\n' +
        'Please enter the correct disease class name (or "skip" to cancel):'
    );

    if (!correctClass || correctClass.toLowerCase() === 'skip') return;

    submitFeedback(correctClass);
}

async function submitFeedback(correctClass) {
    try {
        showToast('Submitting feedback...', 'info');
        const response = await fetch(API_BASE_URL + '/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                predicted_class: window._lastPrediction.class_name || window._lastPrediction.disease,
                correct_class: correctClass,
                confidence: (window._lastPrediction.confidence || 0) * 100,
                image: window._lastImageData
            })
        });

        const result = await response.json();
        if (result.success) {
            showToast('Thank you! Your feedback has been saved and will help improve the AI.', 'success');
        } else {
            showToast('Feedback saved locally. The AI will learn from it during retraining.', 'success');
        }
    } catch (error) {
        console.error('Feedback error:', error);
        showToast('Could not submit feedback to server, but it has been saved locally.', 'warning');
    }
}

function saveDetection(prediction, imageData, caption) {
    const detections = JSON.parse(localStorage.getItem('sc_detections') || '[]');
    detections.unshift({
        id: Date.now(),
        disease: prediction.disease,
        confidence: prediction.confidence,
        severity: prediction.severity || 'Unknown',
        img: imageData,
        caption: caption || '',
        date: new Date().toISOString()
    });
    localStorage.setItem('sc_detections', JSON.stringify(detections.slice(0, 50)));
    loadDashboardData();
}

// ============================================================
// DASHBOARD DATA
// ============================================================

async function loadDashboardData() {
    let detections = [];
    let totalMessages = 0;
    let activities = [];
    let activeDays = 1;

    // Try server first
    try {
        const [detRes, actRes] = await Promise.all([
            fetch(API_BASE_URL + '/detections', { headers: getAuthHeaders() }),
            fetch(API_BASE_URL + '/activity', { headers: getAuthHeaders() })
        ]);
        if (detRes.ok) {
            const detData = await detRes.json();
            if (detData.success) {
                detections = (detData.detections || []).map(d => ({
                    id: d.id,
                    disease: d.disease,
                    confidence: d.confidence,
                    severity: d.severity,
                    img: d.image_id ? '/uploads/' + d.image_id : '',
                    caption: d.caption || '',
                    date: d.created_at
                }));
            }
        }
        if (actRes.ok) {
            const actData = await actRes.json();
            if (actData.success) {
                activities = (actData.activities || []).map(a => ({
                    type: a.type,
                    text: a.text,
                    ts: a.created_at
                }));
                activeDays = new Set(activities.map(a => new Date(a.ts).toDateString())).size;
            }
        }
    } catch (e) {
        console.warn('Server sync failed, falling back to localStorage.', e);
    }

    // Fallback to localStorage if server returned nothing
    if (!detections.length) {
        detections = JSON.parse(localStorage.getItem('sc_detections') || '[]');
    }
    if (!activities.length) {
        activities = JSON.parse(localStorage.getItem('sc_activity') || '[]');
        activeDays = new Set(activities.map(a => new Date(a.ts).toDateString())).size;
    }

    const allMessagesLocal = JSON.parse(localStorage.getItem('sc_conversations') || '{}');
    totalMessages = Object.values(allMessagesLocal).reduce((a, c) => a + (c.length || 0), 0);

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('totalDetections', detections.length);
    set('totalMessages', totalMessages);
    set('activeDays', Math.max(activeDays, 1));

    const agrovets = await loadNearbyAgrovets();
    set('nearbyAgrovets', agrovets.length);

    renderRecentDetections(detections.slice(0, 5));
    renderActivity(activities);
}

function renderRecentDetections(detections) {
    const container = document.getElementById('recentDetections');
    if (!container) return;

    if (!detections.length) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-images"></i><p>No detections yet. Upload a plant image to get started.</p></div>';
        return;
    }

    container.innerHTML = detections.map(d => {
        const conf = (d.confidence < 1) ? Math.round(d.confidence * 100) : d.confidence;
        const badgeClass = d.severity === 'None' ? 'badge-success' : d.severity === 'Severe' ? 'badge-danger' : 'badge-warning';
        return '<div class="detection-item"><img src="' + d.img + '" alt="Detection"><div class="detection-item-info"><p>' + escapeHtml(d.disease) + '</p><small>' + conf + '% confidence Â· ' + d.severity + '</small><br><small style="color:var(--text-muted);">' + new Date(d.date).toLocaleDateString() + '</small></div><span class="disease-badge ' + badgeClass + '">' + d.severity + '</span></div>';
    }).join('');
}

function renderActivity(activities) {
    const container = document.getElementById('activityTimeline');
    if (!container) return;

    if (!activities.length) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-stream"></i><p>No activity recorded yet.</p></div>';
        return;
    }

    const icons = { detection: 'fa-leaf', message: 'fa-comment', login: 'fa-sign-in-alt' };
    const iconClasses = { detection: 'icon-detection', message: 'icon-message', login: 'icon-login' };

    container.innerHTML = activities.slice(0, 20).map(a =>
        '<div class="timeline-item"><div class="timeline-icon ' + (iconClasses[a.type] || 'icon-login') + '"><i class="fas ' + (icons[a.type] || 'fa-circle') + '"></i></div><div class="timeline-content"><p>' + escapeHtml(a.text) + '</p><small>' + new Date(a.ts).toLocaleString() + '</small></div></div>'
    ).join('');
}

// ============================================================
// LOAD REGISTERED AGROVETS
// ============================================================

function loadRegisteredAgrovets() {
    const users = JSON.parse(localStorage.getItem('AgroSightAI_users') || '[]');
    const agrovets = users.filter(u => u.role === 'agrovet');
    const farmerLocation = (currentUser?.location || '').toLowerCase();
    const farmerParts = farmerLocation.split(/[\s,]+/).filter(p => p.length > 2);

    agrovets.sort((a, b) => {
        const aScore = getLocationMatchScore(a.location, farmerParts);
        const bScore = getLocationMatchScore(b.location, farmerParts);
        return bScore - aScore;
    });

    return agrovets;
}

function getLocationMatchScore(agrovetLocation, farmerParts) {
    if (!farmerParts.length) return 0;
    const avLoc = (agrovetLocation || '').toLowerCase();
    let score = 0;
    farmerParts.forEach(part => {
        if (avLoc.includes(part)) score += 2;
    });
    if (farmerParts.some(p => avLoc === p)) score += 5;
    return score;
}

function isAgrovetOnline(agrovetId) {
    if (onlineUsers && onlineUsers[String(agrovetId)]) return true;
    const currentSession = JSON.parse(localStorage.getItem('AgroSightAI_current_user') || 'null');
    return currentSession?.id === agrovetId;
}

function renderAgrovetsGrid() {
    const container = document.getElementById('agrovetsList');
    if (!container) return;
    const agrovets = nearbyAgrovets.length ? nearbyAgrovets : loadRegisteredAgrovetsLegacy();

    if (!agrovets.length) {
        container.innerHTML = '<div class="empty-state" style="grid-column:1/-1;text-align:center;padding:60px 20px;"><i class="fas fa-user-md" style="font-size:4rem;opacity:0.3;margin-bottom:16px;"></i><h3 style="margin-bottom:8px;">No Agro-Vets Available</h3><p style="color:var(--text-muted);">No agro-vets have registered in the system yet.</p><p style="color:var(--text-muted);font-size:0.85rem;margin-top:8px;">Check back later or contact support.</p></div>';
        return;
    }

    container.innerHTML = agrovets.map(agrovet => {
        const isOnline = agrovet.isOnline || isAgrovetOnline(agrovet.id);
        const distanceText = (agrovet.distance_km != null)
            ? '<span style="font-size:0.7rem;background:var(--primary-light);color:var(--primary);padding:2px 8px;border-radius:12px;margin-left:6px;">' + agrovet.distance_km + ' km</span>'
            : '';
        const initials = (agrovet.username || 'U').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

        return '<div class="agrovet-card">' +
            '<div class="agrovet-header"><div class="agrovet-avatar" style="position:relative;">' + escapeHtml(initials) +
            '<span class="status-indicator ' + (isOnline ? 'online' : 'offline') + '"></span></div><div>' +
            '<div class="agrovet-name">' + escapeHtml(agrovet.username) + distanceText + '</div>' +
            '<div class="agrovet-spec">Crop Health Specialist</div></div></div>' +
            '<div class="agrovet-info"><i class="fas fa-map-marker-alt"></i><span>' + escapeHtml(agrovet.location || 'Location not specified') + '</span></div>' +
            '<div class="agrovet-info"><i class="fas fa-envelope"></i><span>' + escapeHtml(agrovet.email || '-') + '</span></div>' +
            '<div class="agrovet-info"><i class="fas fa-phone"></i><span>' + escapeHtml(agrovet.phone || 'Not provided') + '</span></div>' +
            '<span class="availability ' + (isOnline ? 'available' : 'unavailable') + '"><span class="avail-dot"></span>' + (isOnline ? 'Available Now' : 'Currently Offline') + '</span>' +
            '<div style="display:flex;gap:10px;margin-top:16px;">' +
            '<button class="btn-contact" onclick="contactAgrovet(' + agrovet.id + ')" style="flex:1;"><i class="fas fa-comment"></i> Message</button>' +
            '<a href="tel:' + escapeHtml(agrovet.phone || '') + '" class="btn-contact" style="flex:1;text-decoration:none;display:flex;align-items:center;justify-content:center;background:var(--secondary);"><i class="fas fa-phone"></i> Call</a>' +
            '</div></div>';
    }).join('');
}

function renderMiniAgrovets() {
    const container = document.getElementById('miniAgrovets');
    if (!container) return;
    const agrovets = nearbyAgrovets.length ? nearbyAgrovets : loadRegisteredAgrovetsLegacy();

    if (!agrovets.length) {
        container.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;text-align:center;">No agro-vets registered yet</p>';
        return;
    }

    container.innerHTML = agrovets.slice(0, 5).map(agrovet => {
        const online = agrovet.isOnline || isAgrovetOnline(agrovet.id);
        const distLabel = (agrovet.distance_km != null) ? agrovet.distance_km + ' km' : (agrovet.location || 'Unknown');
        const initials = (agrovet.username || 'U').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
        return '<div class="mini-agrovet" onclick="contactAgrovet(' + agrovet.id + ')" style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--bg-tertiary);border-radius:var(--radius);margin-bottom:10px;cursor:pointer;transition:var(--transition);">' +
            '<div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--secondary));display:flex;align-items:center;justify-content:center;color:white;font-weight:600;">' + escapeHtml(initials) + '</div>' +
            '<div style="flex:1;min-width:0;"><div style="font-weight:600;font-size:0.85rem;">' + escapeHtml((agrovet.username || '').split(' ')[0]) + '</div><div style="font-size:0.7rem;color:var(--text-muted);">' + escapeHtml(distLabel) + '</div></div>' +
            '<div style="width:8px;height:8px;border-radius:50%;background:' + (online ? 'var(--success)' : '#9ca3af') + ';"></div></div>';
    }).join('');
}

function contactAgrovet(agrovetId) {
    const agrovets = nearbyAgrovets.length ? nearbyAgrovets : loadRegisteredAgrovetsLegacy();
    const agrovet = agrovets.find(a => a.id == agrovetId);
    if (!agrovet) return;

    const convId = getConversationId(String(currentUser.id), String(agrovetId));
    navigateTo('messages');
    setTimeout(() => openChat(convId), 150);
    showToast('Opening chat with ' + agrovet.username, 'info');
}

function autoSelectNearestAgrovet() {
    if (!nearbyAgrovets.length) {
        showToast('No nearby agro-vets found.', 'warning');
        return;
    }
    const nearest = nearbyAgrovets[0];
    contactAgrovet(nearest.id);
    showToast('Auto-connected to nearest agro-vet: ' + nearest.username + ' (' + nearest.distance_km + ' km)', 'success');
}

// ============================================================
// MESSAGING (Socket.IO + localStorage)
// ============================================================

function getConversationId(userId1, userId2) {
    return [String(userId1), String(userId2)].sort().join('_');
}

function saveConversations() {
    localStorage.setItem('sc_conversations', JSON.stringify(conversations));
}

function loadConversations() {
    const oldMsgs = JSON.parse(localStorage.getItem('sc_messages') || '{}');
    const newConvs = JSON.parse(localStorage.getItem('sc_conversations') || '{}');
    conversations = { ...oldMsgs, ...newConvs };
}

function initMessaging() {
    const sendBtn = document.getElementById('sendMessageBtn');
    if (sendBtn) sendBtn.addEventListener('click', sendMessage);

    const msgInput = document.getElementById('messageInput');
    if (msgInput) {
        msgInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        msgInput.addEventListener('input', () => {
            if (!currentChat || !socket || !socket.connected) return;
            const parts = currentChat.split('_');
            const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];
            socket.emit('typing', { senderId: String(currentUser.id), receiverId: otherUserId, isTyping: true });
            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(() => {
                socket.emit('typing', { senderId: String(currentUser.id), receiverId: otherUserId, isTyping: false });
            }, 1500);
        });
    }

    // Image upload in chat
    const imgBtn = document.getElementById('imgBtn');
    const chatImageUpload = document.getElementById('chatImageUpload');
    if (imgBtn && chatImageUpload) {
        imgBtn.addEventListener('click', () => chatImageUpload.click());
        chatImageUpload.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) sendImageMessage(file);
            chatImageUpload.value = '';
        });
    }

    // Voice recording
    const voiceBtn = document.getElementById('voiceBtn');
    if (voiceBtn) {
        voiceBtn.addEventListener('click', toggleVoiceRecording);
    }

    initSocketIO();
}

// ============================================================
// IMAGE MESSAGING
// ============================================================

function sendImageMessage(file) {
    if (!currentChat) { showToast('Select a conversation first', 'error'); return; }

    const reader = new FileReader();
    reader.onload = (e) => {
        const imageData = e.target.result;
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        loadConversations();
        if (!conversations[currentChat]) conversations[currentChat] = [];
        conversations[currentChat].push({ text: '', sent: true, time: time, read: true, type: 'image', image: imageData });
        saveConversations();

        renderMessages(currentChat);
        renderConversations();

        const parts = currentChat.split('_');
        const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];

        if (socket && socket.connected) {
            socket.emit('image_message', {
                senderId: String(currentUser.id),
                receiverId: otherUserId,
                image: imageData,
                caption: '',
                timestamp: new Date().toISOString()
            });
        }

        logActivity('message', 'Sent an image');
        showToast('Image sent!', 'success');
    };
    reader.readAsDataURL(file);
}

// ============================================================
// VOICE MESSAGING
// ============================================================

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

function toggleVoiceRecording() {
    if (isRecording) {
        stopVoiceRecording();
    } else {
        startVoiceRecording();
    }
}

async function startVoiceRecording() {
    if (!currentChat) { showToast('Select a conversation first', 'error'); return; }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const reader = new FileReader();
            reader.onload = (e) => {
                const audioData = e.target.result;
                const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                loadConversations();
                if (!conversations[currentChat]) conversations[currentChat] = [];
                conversations[currentChat].push({ text: '', sent: true, time: time, read: true, type: 'voice', audio: audioData, duration: Math.round(audioChunks.length) });
                saveConversations();

                renderMessages(currentChat);
                renderConversations();

                const parts = currentChat.split('_');
                const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];

                if (socket && socket.connected) {
                    socket.emit('voice_message', {
                        senderId: String(currentUser.id),
                        receiverId: otherUserId,
                        audio: audioData,
                        duration: 0,
                        timestamp: new Date().toISOString()
                    });
                }

                logActivity('message', 'Sent a voice note');
                showToast('Voice note sent!', 'success');
            };
            reader.readAsDataURL(audioBlob);

            // Stop all tracks
            stream.getTracks().forEach(t => t.stop());
        };

        mediaRecorder.start();
        isRecording = true;

        const voiceBtn = document.getElementById('voiceBtn');
        if (voiceBtn) {
            voiceBtn.style.background = '#f44336';
            voiceBtn.style.color = 'white';
            voiceBtn.innerHTML = '<i class="fas fa-stop"></i>';
        }
        showToast('Recording... Click stop when done', 'info');
    } catch (err) {
        console.error('Microphone error:', err);
        showToast('Microphone access denied', 'error');
    }
}

function stopVoiceRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }
    isRecording = false;

    const voiceBtn = document.getElementById('voiceBtn');
    if (voiceBtn) {
        voiceBtn.style.background = '';
        voiceBtn.style.color = '';
        voiceBtn.innerHTML = '<i class="fas fa-microphone"></i>';
    }
}

function initSocketIO() {
    try {
        if (typeof io === 'undefined') {
            console.warn('[Socket.IO] Library not loaded - using localStorage only');
            return;
        }

        socket = io(window.API_CONFIG?.SOCKET_URL || '', {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 3000
        });

        socket.on('connect', () => {
            console.log('[Socket.IO] Connected');
            if (currentUser) {
                socket.emit('join', {
                    userId: String(currentUser.id),
                    role: currentUser.role,
                    name: currentUser.username,
                    avatar: currentUser.profilePicture || ''
                });
            }
            // Start backend heartbeat for online status
            if (window._heartbeatInterval) clearInterval(window._heartbeatInterval);
            window._heartbeatInterval = setInterval(() => {
                if (currentUser) {
                    fetch(API_BASE_URL + '/users/online', {
                        method: 'POST',
                        headers: getAuthHeaders()
                    }).catch(() => {});
                }
            }, 60000);
        });

        socket.on('users_online', (users) => {
            onlineUsers = users;
            renderConversations();
            renderMiniAgrovets();
            renderAgrovetsGrid();
        });

        socket.on('new_message', (msg) => {
            const convId = getConversationId(String(currentUser.id), msg.sender);
            if (!conversations[convId]) conversations[convId] = [];
            const msgObj = {
                text: msg.text || msg.caption || '',
                sent: false,
                time: new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                read: false,
                type: msg.type || 'text'
            };
            if (msg.type === 'image' && msg.image) msgObj.image = msg.image;
            if (msg.type === 'voice' && msg.audio) msgObj.audio = msg.audio;
            conversations[convId].push(msgObj);
            saveConversations();
            renderConversations();
            if (currentChat === convId) {
                renderMessages(convId);
                socket.emit('mark_read', { userId: String(currentUser.id), otherUserId: msg.sender });
            }
            showToast('New message from ' + (msg.senderName || 'Agro-Vet'), 'info');
            logActivity('message', 'Received ' + (msg.type || 'message') + ' from agro-vet');
        });

        socket.on('show_typing', (data) => {
            const header = document.getElementById('currentChatHeader');
            if (!header) return;
            if (data.senderId && data.isTyping) {
                if (!header.querySelector('.typing-indicator')) {
                    const span = document.createElement('span');
                    span.className = 'typing-indicator';
                    span.style.cssText = 'font-size:0.75rem;color:var(--text-muted);margin-left:8px;';
                    span.textContent = 'typing...';
                    header.appendChild(span);
                }
            } else {
                const el = header.querySelector('.typing-indicator');
                if (el) el.remove();
            }
        });

        socket.on('disconnect', () => console.log('[Socket.IO] Disconnected'));
        socket.on('connect_error', () => console.warn('[Socket.IO] Connection error'));
    } catch (e) {
        console.warn('[Socket.IO] Not available - using localStorage only');
    }
}

function renderConversations() {
    const container = document.getElementById('conversationList');
    if (!container) return;
    const agrovets = nearbyAgrovets.length ? nearbyAgrovets : loadRegisteredAgrovetsLegacy();
    loadConversations();

    if (!agrovets.length) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-user-md"></i><p>No agro-vets registered yet</p><p style="font-size:0.8rem;margin-top:4px;color:var(--text-muted);">Conversations will appear when agrovets sign up</p></div>';
        return;
    }

    container.innerHTML = agrovets.map(agrovet => {
        const convId = getConversationId(String(currentUser.id), String(agrovet.id));
        const msgs = conversations[convId] || [];
        const lastMsg = msgs[msgs.length - 1];
        const unread = msgs.filter(m => !m.sent && !m.read).length;
        const isOnline = !!onlineUsers[String(agrovet.id)];
        const initials = (agrovet.username || 'U').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

        return '<div class="conversation-item ' + (currentChat === convId ? 'active' : '') + '" onclick="openChat(\'' + convId + '\')">' +
            '<div class="conv-avatar" style="position:relative;">' + escapeHtml(initials) +
            '<div style="position:absolute;bottom:0;right:0;width:8px;height:8px;border-radius:50%;background:' + (isOnline ? '#4caf50' : '#9e9e9e') + ';border:2px solid var(--bg-card);"></div></div>' +
            '<div style="flex:1;min-width:0;"><div class="conv-name">' + escapeHtml(agrovet.username) + (isOnline ? ' <span style="font-size:0.65rem;color:var(--success);">online</span>' : '') + '</div>' +
            '<div class="conv-preview" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtml(lastMsg ? lastMsg.text : 'Start a conversation') + '</div></div>' +
            (unread > 0 ? '<span class="unread-badge">' + unread + '</span>' : '') + '</div>';
    }).join('');
}

function openChat(convId) {
    currentChat = convId;
    loadConversations();

    const parts = convId.split('_');
    const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];
    const agrovets = loadRegisteredAgrovets();
    const agrovet = agrovets.find(a => String(a.id) === otherUserId);
    const isOnline = !!onlineUsers[otherUserId];
    const chatHeader = document.getElementById('currentChatHeader');
    const chatInput = document.getElementById('chatInputArea');

    if (agrovet) {
        const initials = (agrovet.username || 'U').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
        if (chatHeader) {
            chatHeader.innerHTML = '<div class="conv-avatar" style="position:relative;">' + escapeHtml(initials) +
                '<div style="position:absolute;bottom:0;right:0;width:8px;height:8px;border-radius:50%;background:' + (isOnline ? '#4caf50' : '#9e9e9e') + ';border:2px solid var(--bg-card);"></div></div>' +
                '<div><strong>' + escapeHtml(agrovet.username) + '</strong><small style="color:var(--text-muted);font-size:0.75rem;margin-left:6px;">' +
                (isOnline ? '<span style="color:var(--success);">Online</span>' : 'Offline') + ' Â· ' + escapeHtml(agrovet.location || 'Unknown') + '</small></div>';
        }
    } else {
        if (chatHeader) {
            chatHeader.innerHTML = '<strong>Agro-Vet</strong><small style="color:var(--text-muted);font-size:0.75rem;margin-left:6px;">' + (isOnline ? 'Online' : 'Offline') + '</small>';
        }
    }

    if (chatInput) chatInput.style.display = 'flex';
    renderMessages(convId);
    renderConversations();

    // Mark as read
    if (socket && socket.connected) {
        socket.emit('mark_read', { userId: String(currentUser.id), otherUserId: otherUserId });
    }
    const msgs = conversations[convId] || [];
    msgs.forEach(m => { if (!m.sent && !m.read) m.read = true; });
    saveConversations();
}

function renderMessages(convId) {
    const container = document.getElementById('chatMessages');
    if (!container) return;
    const msgs = conversations[convId] || [];

    if (!msgs.length) {
        container.innerHTML = '<div class="placeholder-message"><i class="fas fa-seedling"></i><p>Send a message to start the conversation</p></div>';
        return;
    }

    container.innerHTML = msgs.map(m => {
        let content = '';
        if (m.type === 'image' && m.image) {
            content = '<img src="' + escapeHtml(m.image) + '" style="max-width:240px;border-radius:8px;cursor:pointer;" onclick="window.open(this.src,\'_blank\')" alt="Shared image">' + (m.text ? '<p style="margin-top:4px;">' + escapeHtml(m.text) + '</p>' : '');
        } else if (m.type === 'voice' && m.audio) {
            content = '<div style="display:flex;align-items:center;gap:8px;"><i class="fas fa-microphone" style="color:' + (m.sent ? 'white' : 'var(--primary)') + ';"></i><audio controls src="' + escapeHtml(m.audio) + '" style="height:36px;max-width:200px;"></audio></div>' + (m.text ? '<p style="margin-top:4px;">' + escapeHtml(m.text) + '</p>' : '');
        } else {
            content = escapeHtml(m.text || '');
        }
        return '<div><div class="message-bubble ' + (m.sent ? 'sent' : 'received') + '">' + content + '</div>' +
            '<div class="message-time" style="text-align:' + (m.sent ? 'right' : 'left') + ';margin:2px 4px;">' + escapeHtml(m.time || '') + '</div></div>';
    }).join('');

    container.scrollTop = container.scrollHeight;
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text || !currentChat) return;

    loadConversations();
    if (!conversations[currentChat]) conversations[currentChat] = [];

    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    conversations[currentChat].push({ text: text, sent: true, time: time, read: true });
    saveConversations();

    input.value = '';
    renderMessages(currentChat);
    renderConversations();

    const parts = currentChat.split('_');
    const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];

    if (socket && socket.connected) {
        socket.emit('private_message', {
            senderId: String(currentUser.id),
            receiverId: otherUserId,
            text: text,
            timestamp: new Date().toISOString()
        });
    }

    const agrovets = loadRegisteredAgrovets();
    const agrovet = agrovets.find(a => String(a.id) === otherUserId);
    logActivity('message', 'Sent message to ' + (agrovet?.username || 'Agro-Vet'));
    loadDashboardData();
}

// ============================================================
// PROFILE
// ============================================================

function initProfile() {
    const profileUpload = document.getElementById('profileUpload');
    if (profileUpload) {
        profileUpload.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (ev) => {
                    const preview = document.getElementById('profilePreview');
                    if (preview) preview.src = ev.target.result;
                    currentUser.profilePicture = ev.target.result;
                    updateLocalStorage();
                    showToast('Profile photo updated!', 'success');
                };
                reader.readAsDataURL(file);
            }
        });
    }

    const editBtn = document.getElementById('editProfileBtn');
    if (editBtn) {
        editBtn.addEventListener('click', () => {
            const phoneInput = document.getElementById('editPhone');
            const locInput = document.getElementById('editLocation');
            if (phoneInput) phoneInput.value = currentUser.phone || '';
            if (locInput) locInput.value = currentUser.location || '';
            const modal = document.getElementById('editModal');
            if (modal) modal.classList.add('show');
        });
    }

    const cancelBtn = document.getElementById('cancelEdit');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            const modal = document.getElementById('editModal');
            if (modal) modal.classList.remove('show');
        });
    }

    const saveBtn = document.getElementById('saveProfile');
    if (saveBtn) {
        saveBtn.addEventListener('click', () => {
            const phoneInput = document.getElementById('editPhone');
            const locInput = document.getElementById('editLocation');
            if (phoneInput) currentUser.phone = phoneInput.value;
            if (locInput) currentUser.location = locInput.value;
            updateLocalStorage();
            updateUserDisplay();
            const modal = document.getElementById('editModal');
            if (modal) modal.classList.remove('show');
            showToast('Profile updated!', 'success');
        });
    }
}

// ============================================================
// LOGOUT
// ============================================================

function initLogout() {
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (confirm('Are you sure you want to logout?')) {
                localStorage.removeItem('AgroSightAI_current_user');
                localStorage.removeItem('sc_token');
                showToast('Logged out successfully', 'info');
                setTimeout(() => window.location.href = 'index.html', 1000);
            }
        });
    }
}

// ============================================================
// UTILITIES
// ============================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function logActivity(type, text) {
    const activities = JSON.parse(localStorage.getItem('sc_activity') || '[]');
    activities.unshift({ type: type, text: text, ts: new Date().toISOString() });
    localStorage.setItem('sc_activity', JSON.stringify(activities.slice(0, 50)));
}

function updateLocalStorage() {
    localStorage.setItem('AgroSightAI_current_user', JSON.stringify(currentUser));
    const users = JSON.parse(localStorage.getItem('AgroSightAI_users') || '[]');
    const index = users.findIndex(u => u.id === currentUser.id);
    if (index !== -1) {
        users[index] = currentUser;
        localStorage.setItem('AgroSightAI_users', JSON.stringify(users));
    }
}

function showToast(message, type) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'toast ' + (type || 'success') + ' show';
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Expose globals for inline onclick handlers
window.contactAgrovet = contactAgrovet;
window.openChat = openChat;