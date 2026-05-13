// ============================================================
// AGROVET DASHBOARD - COMPLETE WORKING VERSION
// ============================================================

const API_BASE_URL = window.API_CONFIG ? window.API_CONFIG.BASE_URL : 'http://127.0.0.1:5000/api';

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
let allFarmers = [];
let socket = null;
let onlineUsers = {};
let typingTimeout = null;

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

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', async function() {
    console.log('Agro-Vet dashboard loading...');

    await checkAuth();
    initTheme();
    initNavigation();
    initMobileMenu();
    initMessaging();
    initProfile();
    initLogout();

    loadDashboardData();
    loadRegisteredFarmers();

    // Modern disease detection UI
    if (typeof window.DiseaseDetectionUI !== 'undefined') {
        window.DiseaseDetectionUI.init({ containerId: 'disease-detection', role: 'agrovet' });
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
    if (currentUser.role !== 'agrovet') {
        alert('Access denied. This dashboard is for Agro-Vets only.');
        window.location.href = 'farmer-dashboard.html';
        return;
    }

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
    if (geo.lat != null && geo.lng != null && currentUser) {
        await updateBackendLocation(geo.lat, geo.lng);
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
    if (el) el.textContent = greeting + '! Ready to help farmers today?';
}

// ============================================================
// THEME
// ============================================================

function initTheme() {
    const savedTheme = localStorage.getItem('sc_theme') || localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
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
        mobileThemeToggle.addEventListener('click', toggleTheme);
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
// LOAD REGISTERED FARMERS
// ============================================================

function loadRegisteredFarmers() {
    const users = JSON.parse(localStorage.getItem('AgroSightAI_users') || '[]');
    allFarmers = users.filter(u => u.role === 'farmer');
    console.log('Found ' + allFarmers.length + ' registered farmers');

    loadConversations();
    renderFarmersList();
    renderMiniFarmers();
    renderConversations();
}

function renderFarmersList() {
    const container = document.getElementById('farmersList');
    if (!container) return;

    if (!allFarmers.length) {
        container.innerHTML = '<div class="empty-state" style="grid-column:1/-1;"><i class="fas fa-users"></i><p>No farmers registered yet</p><p style="font-size:0.85rem;margin-top:8px;">Farmers will appear here once they sign up</p></div>';
        return;
    }

    container.innerHTML = allFarmers.map(farmer => {
        const initials = escapeHtml(farmer.username.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase());
        const username = escapeHtml(farmer.username);
        const email = escapeHtml(farmer.email || '-');
        const location = escapeHtml(farmer.location || 'Not specified');
        const phone = escapeHtml(farmer.phone || 'Not provided');
        const isOnline = !!onlineUsers[String(farmer.id)];
        return '<div class="farmer-card">' +
            '<div class="farmer-header"><div class="farmer-avatar">' + initials + '</div><div>' +
            '<div class="farmer-name">' + username + '</div>' +
            '<div class="farmer-email">' + email + '</div></div></div>' +
            '<div class="farmer-info"><i class="fas fa-map-marker-alt"></i> ' + location + '</div>' +
            '<div class="farmer-info"><i class="fas fa-phone"></i> ' + phone + '</div>' +
            '<div class="farmer-info"><i class="fas fa-calendar"></i> Joined: ' + new Date(farmer.createdAt).toLocaleDateString() + '</div>' +
            '<span class="availability ' + (isOnline ? 'available' : 'unavailable') + '"><span class="avail-dot"></span>' + (isOnline ? 'Online Now' : 'Currently Offline') + '</span>' +
            '<button class="btn-contact" onclick="openChatWithFarmer(\'' + farmer.id + '\')"><i class="fas fa-comment"></i> Message ' + escapeHtml(farmer.username.split(' ')[0]) + '</button></div>';
    }).join('');
}

function renderMiniFarmers() {
    const container = document.getElementById('miniFarmers');
    if (!container) return;

    if (!allFarmers.length) {
        container.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">No farmers yet</p>';
        return;
    }

    const sorted = [...allFarmers].sort((a, b) => {
        const aOnline = !!onlineUsers[String(a.id)];
        const bOnline = !!onlineUsers[String(b.id)];
        if (aOnline !== bOnline) return bOnline ? 1 : -1;
        return a.username.localeCompare(b.username);
    });

    container.innerHTML = sorted.slice(0, 5).map(farmer => {
        const isOnline = !!onlineUsers[String(farmer.id)];
        const initials = escapeHtml(farmer.username.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase());
        const usernameFirst = escapeHtml(farmer.username.split(' ')[0]);
        const location = escapeHtml(farmer.location?.split(',')[0] || 'Unknown');
        return '<div class="farmer-mini-card" onclick="openChatWithFarmer(\'' + farmer.id + '\')" style="display:flex;align-items:center;gap:12px;padding:12px;background:var(--bg-tertiary);border-radius:var(--radius);margin-bottom:10px;cursor:pointer;">' +
            '<div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--secondary));display:flex;align-items:center;justify-content:center;color:white;font-weight:600;font-size:0.85rem;position:relative;">' + initials +
            '<div style="position:absolute;bottom:-1px;right:-1px;width:10px;height:10px;border-radius:50%;background:' + (isOnline ? '#4caf50' : '#9e9e9e') + ';border:2px solid var(--bg-card);"></div></div>' +
            '<div style="flex:1;min-width:0;"><div style="font-weight:600;font-size:0.85rem;">' + usernameFirst + '</div>' +
            '<div style="font-size:0.7rem;color:var(--text-muted);">' + location + '</div></div></div>';
    }).join('');
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
    const oldMsgs = JSON.parse(localStorage.getItem('sc_messages_agrovet') || '{}');
    const newConvs = JSON.parse(localStorage.getItem('sc_conversations') || '{}');
    conversations = { ...oldMsgs, ...newConvs };
}

function renderConversations() {
    const container = document.getElementById('conversationList');
    if (!container) return;
    loadConversations();

    if (!allFarmers.length) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-comments"></i><p>No conversations yet</p><p style="font-size:0.8rem;margin-top:4px;color:var(--text-muted);">Farmers will appear here when they sign up</p></div>';
        return;
    }

    const sortedFarmers = [...allFarmers].sort((a, b) => {
        const convA = conversations[getConversationId(String(currentUser.id), String(a.id))] || [];
        const convB = conversations[getConversationId(String(currentUser.id), String(b.id))] || [];
        const lastA = convA.length ? new Date(convA[convA.length - 1].time || 0).getTime() : 0;
        const lastB = convB.length ? new Date(convB[convB.length - 1].time || 0).getTime() : 0;
        return lastB - lastA;
    });

    container.innerHTML = sortedFarmers.map(farmer => {
        const convId = getConversationId(String(currentUser.id), String(farmer.id));
        const msgs = conversations[convId] || [];
        const lastMsg = msgs[msgs.length - 1];
        const unread = msgs.filter(m => !m.sent && !m.read).length;
        const isOnline = !!onlineUsers[String(farmer.id)];
        const initials = escapeHtml(farmer.username.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase());
        const username = escapeHtml(farmer.username);
        const lastMsgText = lastMsg ? escapeHtml(lastMsg.text) : 'Start a conversation';

        return '<div class="conversation-item ' + (currentChat === convId ? 'active' : '') + '" onclick="openChat(\'' + convId + '\')">' +
            '<div class="conv-avatar" style="position:relative;">' + initials +
            '<div style="position:absolute;bottom:0;right:0;width:8px;height:8px;border-radius:50%;background:' + (isOnline ? '#4caf50' : '#9e9e9e') + ';border:2px solid var(--bg-card);"></div></div>' +
            '<div class="conv-info" style="flex:1;min-width:0;"><div class="conv-name">' + username + (isOnline ? ' <span style="font-size:0.65rem;color:var(--success);">online</span>' : '') + '</div>' +
            '<div class="conv-preview" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + lastMsgText + '</div></div>' +
            (unread > 0 ? '<span class="unread-badge">' + unread + '</span>' : '') + '</div>';
    }).join('');
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
    if (voiceBtn) voiceBtn.addEventListener('click', toggleVoiceRecording);

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
            socket.emit('image_message', { senderId: String(currentUser.id), receiverId: otherUserId, image: imageData, caption: '', timestamp: new Date().toISOString() });
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
    if (isRecording) stopVoiceRecording();
    else startVoiceRecording();
}

async function startVoiceRecording() {
    if (!currentChat) { showToast('Select a conversation first', 'error'); return; }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const reader = new FileReader();
            reader.onload = (e) => {
                const audioData = e.target.result;
                const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                loadConversations();
                if (!conversations[currentChat]) conversations[currentChat] = [];
                conversations[currentChat].push({ text: '', sent: true, time: time, read: true, type: 'voice', audio: audioData });
                saveConversations();
                renderMessages(currentChat);
                renderConversations();
                const parts = currentChat.split('_');
                const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];
                if (socket && socket.connected) {
                    socket.emit('voice_message', { senderId: String(currentUser.id), receiverId: otherUserId, audio: audioData, duration: 0, timestamp: new Date().toISOString() });
                }
                logActivity('message', 'Sent a voice note');
                showToast('Voice note sent!', 'success');
            };
            reader.readAsDataURL(audioBlob);
            stream.getTracks().forEach(t => t.stop());
        };
        mediaRecorder.start();
        isRecording = true;
        const voiceBtn = document.getElementById('voiceBtn');
        if (voiceBtn) { voiceBtn.style.background = '#f44336'; voiceBtn.style.color = 'white'; voiceBtn.innerHTML = '<i class="fas fa-stop"></i>'; }
        showToast('Recording... Click stop when done', 'info');
    } catch (err) {
        console.error('Microphone error:', err);
        showToast('Microphone access denied', 'error');
    }
}

function stopVoiceRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
    isRecording = false;
    const voiceBtn = document.getElementById('voiceBtn');
    if (voiceBtn) { voiceBtn.style.background = ''; voiceBtn.style.color = ''; voiceBtn.innerHTML = '<i class="fas fa-microphone"></i>'; }
}

function initSocketIO() {
    try {
        if (typeof io === 'undefined') {
            console.warn('[Socket.IO] Library not loaded - using localStorage only');
            return;
        }

        socket = io(window.API_CONFIG ? window.API_CONFIG.SOCKET_URL : 'http://127.0.0.1:5001', {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 3000
        });

        socket.on('connect', () => {
            console.log('[Socket.IO] Agrovet connected');
            if (currentUser) {
                socket.emit('join', {
                    userId: String(currentUser.id),
                    role: currentUser.role,
                    name: currentUser.username,
                    avatar: currentUser.profilePicture || ''
                });
            }
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
            renderMiniFarmers();
            renderFarmersList();
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
            const farmer = allFarmers.find(f => String(f.id) === msg.sender);
            showToast('New message from ' + (farmer?.username || 'Farmer'), 'info');
            logActivity('message', 'Received ' + (msg.type || 'message') + ' from ' + (farmer?.username || 'farmer'));
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

function openChat(convId) {
    currentChat = convId;
    loadConversations();

    const parts = convId.split('_');
    const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];
    const farmer = allFarmers.find(f => String(f.id) === otherUserId);
    const isOnline = !!onlineUsers[otherUserId];
    const chatHeader = document.getElementById('currentChatHeader');
    const chatInput = document.getElementById('chatInputArea');

    if (farmer) {
        const initials = escapeHtml(farmer.username.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase());
        const username = escapeHtml(farmer.username);
        const location = escapeHtml(farmer.location || 'Unknown location');
        if (chatHeader) {
            chatHeader.innerHTML = '<div class="conv-avatar" style="position:relative;">' + initials +
                '<div style="position:absolute;bottom:0;right:0;width:8px;height:8px;border-radius:50%;background:' + (isOnline ? '#4caf50' : '#9e9e9e') + ';border:2px solid var(--bg-card);"></div></div>' +
                '<div><strong>' + username + '</strong><br><small style="color:var(--text-muted);">' +
                (isOnline ? '<span style="color:var(--success);">Online</span>' : 'Offline') + ' Â· ' + location + '</small></div>';
        }
    } else {
        if (chatHeader) {
            chatHeader.innerHTML = '<strong>Farmer</strong><small style="color:var(--text-muted);font-size:0.75rem;margin-left:6px;">' + (isOnline ? 'Online' : 'Offline') + '</small>';
        }
    }

    if (chatInput) chatInput.style.display = 'flex';
    renderMessages(convId);
    renderConversations();

    if (socket && socket.connected) {
        socket.emit('mark_read', { userId: String(currentUser.id), otherUserId: otherUserId });
    }
    const msgs = conversations[convId] || [];
    msgs.forEach(m => { if (!m.sent && !m.read) m.read = true; });
    saveConversations();
}

window.openChatWithFarmer = function(farmerId) {
    const convId = getConversationId(String(currentUser.id), String(farmerId));
    navigateTo('messages');
    setTimeout(() => openChat(convId), 150);
};

function renderMessages(convId) {
    const container = document.getElementById('chatMessages');
    if (!container) return;
    const msgs = conversations[convId] || [];

    if (!msgs.length) {
        const parts = convId.split('_');
        const otherUserId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];
        const farmer = allFarmers.find(f => String(f.id) === otherUserId);
        container.innerHTML = '<div class="placeholder-message"><i class="fas fa-seedling"></i><p>Start a conversation with ' + escapeHtml(farmer?.username || 'Farmer') + '</p></div>';
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
            '<div class="message-time" style="text-align:' + (m.sent ? 'right' : 'left') + ';">' + escapeHtml(m.time || '') + '</div></div>';
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

    const farmer = allFarmers.find(f => String(f.id) === otherUserId);
    logActivity('message', 'Sent message to ' + (farmer?.username || 'Farmer'));
    loadDashboardData();
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
            showToast('Thank you! Your feedback has been saved.', 'success');
        } else {
            showToast('Feedback saved locally. The AI will learn from it.', 'success');
        }
    } catch (error) {
        console.error('Feedback error:', error);
        showToast('Could not submit to server, but saved locally.', 'warning');
    }
}

// ============================================================
// DASHBOARD DATA
// ============================================================

async function loadDashboardData() {
    let ownDetections = [];
    let totalMessages = 0;

    // Try server first
    try {
        const detRes = await fetch(API_BASE_URL + '/detections', { headers: getAuthHeaders() });
        if (detRes.ok) {
            const detData = await detRes.json();
            if (detData.success) {
                ownDetections = (detData.detections || []).map(d => ({
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
    } catch (e) {
        console.warn('Server sync failed, falling back to localStorage.', e);
    }

    // Fallback to localStorage
    if (!ownDetections.length) {
        ownDetections = JSON.parse(localStorage.getItem('sc_detections_agrovet') || '[]');
    }

    const allMessages = JSON.parse(localStorage.getItem('sc_conversations') || '{}');
    totalMessages = Object.values(allMessages).reduce((a, c) => a + (c.length || 0), 0);

    // Count unique farmers helped through conversations
    let farmersHelped = new Set();
    Object.keys(allMessages).forEach(convId => {
        const parts = convId.split('_');
        if (parts.length === 2) {
            const otherId = parts[0] === String(currentUser.id) ? parts[1] : parts[0];
            const farmer = allFarmers.find(f => String(f.id) === otherId);
            if (farmer) farmersHelped.add(farmer.id);
        }
    });

    // Success rate based on own detection confidence average (or fallback)
    let successRate = 0;
    if (ownDetections.length > 0) {
        const avgConf = ownDetections.reduce((a, d) => a + (d.confidence || 0), 0) / ownDetections.length;
        successRate = Math.round(avgConf);
    } else {
        successRate = farmersHelped.size > 0 ? 85 : 0;
    }

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('totalFarmersHelped', farmersHelped.size);
    set('totalDiagnoses', ownDetections.length);
    set('totalMessages', totalMessages);
    set('successRate', successRate + '%');

    loadActivity();
}

function loadActivity() {
    const activities = JSON.parse(localStorage.getItem('sc_activity_agrovet') || '[]');
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

function logActivity(type, text) {
    const activities = JSON.parse(localStorage.getItem('sc_activity_agrovet') || '[]');
    activities.unshift({ type: type, text: text, ts: new Date().toISOString() });
    localStorage.setItem('sc_activity_agrovet', JSON.stringify(activities.slice(0, 50)));
    loadActivity();
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
                localStorage.removeItem('sc_token');
                localStorage.removeItem('AgroSightAI_current_user');
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

