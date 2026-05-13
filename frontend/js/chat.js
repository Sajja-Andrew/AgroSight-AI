// Supports: Text, Voice Notes, Image Sharing
// Shared by farmer-dashboard.html and agrovet-dashboard.html

(function() {
    'use strict';

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 1. CONFIGURATION
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    const SERVER_URL = window.API_CONFIG?.SOCKET_URL || '';
    const API_BASE_URL = window.API_CONFIG?.BASE_URL || '';
    const RECONNECT_DELAY = 3000;
    const TYPING_TIMEOUT = 2000;
    const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5MB
    const MAX_AUDIO_SIZE = 10 * 1024 * 1024; // 10MB

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 2. STATE
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    let socket = null;
    let currentUser = null;
    let activeChat = null;
    let activeChatMeta = null;
    let typingTimer = null;
    let isConnected = false;
    let conversations = [];

    // Voice Recording State
    let mediaRecorder = null;
    let audioChunks = [];
    let recordingStartTime = 0;
    let recordingInterval = null;
    let isRecording = false;

    // Image State
    let selectedImages = [];

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 3. GET CURRENT USER
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function loadCurrentUser() {
        try {
            const raw = localStorage.getItem('AgroSightAI_current_user');
            if (!raw) {
                console.warn('[Chat] No user found in localStorage.');
                return null;
            }
            const user = JSON.parse(raw);
            if (!user.id && user._id) user.id = user._id;
            if (!user.id) {
                console.error('[Chat] User object has no id field');
                return null;
            }
            return user;
        } catch (e) {
            console.error('[Chat] Failed to parse AgroSightAI_user:', e);
            return null;
        }
    }

    function getAuthHeaders() {
        const token = localStorage.getItem('sc_token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = 'Bearer ' + token;
        return headers;
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 4. CONNECT TO SERVER
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function connect() {
        currentUser = loadCurrentUser();
        if (!currentUser) return;

        if (typeof io === 'undefined') {
            console.warn('[Chat] Socket.IO client not loaded. Retrying...');
            setTimeout(connect, RECONNECT_DELAY);
            return;
        }

        socket = io(SERVER_URL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: RECONNECT_DELAY
        });

        socket.on('connect', () => {
            console.log('[Chat] Connected to server');
            isConnected = true;
            updateConnectionStatus(true);

            socket.emit('join', {
                userId: currentUser.id,
                role: currentUser.role,
                name: currentUser.username || currentUser.email || currentUser.id,
                avatar: ''
            });

            loadConversations();
        });

        socket.on('disconnect', () => {
            console.log('[Chat] Disconnected from server');
            isConnected = false;
            updateConnectionStatus(false);
        });

        socket.on('connect_error', (err) => {
            console.error('[Chat] Connection error:', err.message);
            isConnected = false;
            updateConnectionStatus(false);
        });

        // â”€â”€ Message Events â”€â”€

        socket.on('new_message', (message) => {
            console.log('[Chat] New message received:', message.type || 'text');
            playNotificationSound();

            if (activeChat === message.sender) {
                appendMessage(message, 'received');
                scrollToBottom();

                socket.emit('mark_read', {
                    userId: currentUser.id,
                    otherUserId: message.sender
                });
            } else {
                incrementUnread(message.sender);
                showToastNotification(message);
            }

            loadConversations();
        });

        socket.on('message_sent', (message) => {
            console.log('[Chat] Message delivered:', message.id);
            markMessageDelivered(message.id);
        });

        socket.on('messages_read', (data) => {
            if (activeChat === data.readBy) {
                updateReadReceipts();
            }
        });

        socket.on('show_typing', (data) => {
            if (activeChat === data.senderId) {
                showTypingIndicator(data.isTyping);
            }
        });

        socket.on('users_online', (users) => {
            updateOnlineStatuses(users);
        });
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 5. SEND TEXT MESSAGE
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function sendMessage(text) {
        if (!socket || !isConnected || !activeChat || !text.trim()) return;

        const message = {
            senderId: currentUser.id,
            receiverId: activeChat,
            text: text.trim(),
            timestamp: new Date().toISOString()
        };

        appendMessage({
            ...message,
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            type: 'text',
            pending: true
        }, 'sent');

        scrollToBottom();
        socket.emit('private_message', message);

        socket.emit('typing', {
            senderId: currentUser.id,
            receiverId: activeChat,
            isTyping: false
        });

        setTimeout(loadConversations, 500);
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 6. SEND IMAGE MESSAGE
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function sendImage(imageData, caption = '') {
        if (!socket || !isConnected || !activeChat) return;

        const message = {
            senderId: currentUser.id,
            receiverId: activeChat,
            image: imageData,
            caption: caption,
            timestamp: new Date().toISOString()
        };

        appendMessage({
            ...message,
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            type: 'image',
            pending: true
        }, 'sent');

        scrollToBottom();
        socket.emit('image_message', message);

        setTimeout(loadConversations, 500);
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 7. SEND VOICE MESSAGE
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function sendVoiceNote(audioData, duration) {
        if (!socket || !isConnected || !activeChat) return;

        const message = {
            senderId: currentUser.id,
            receiverId: activeChat,
            audio: audioData,
            duration: duration,
            timestamp: new Date().toISOString()
        };

        appendMessage({
            ...message,
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            type: 'voice',
            pending: true
        }, 'sent');

        scrollToBottom();
        socket.emit('voice_message', message);

        setTimeout(loadConversations, 500);
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 8. IMAGE HANDLING
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function handleImageSelect(file) {
        if (!file || !file.type.startsWith('image/')) {
            showToast('Please select a valid image file', 'error');
            return;
        }

        if (file.size > MAX_IMAGE_SIZE) {
            showToast('Image must be smaller than 5MB', 'error');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            const imageData = e.target.result;
            showImagePreview(imageData, file.name);
        };
        reader.readAsDataURL(file);
    }

    function showImagePreview(imageData, filename) {
        // Find or create preview container
        let previewContainer = document.getElementById('imagePreviewContainer');
        if (!previewContainer) {
            previewContainer = document.createElement('div');
            previewContainer.id = 'imagePreviewContainer';
            previewContainer.className = 'image-preview-container';
            
            const inputArea = document.getElementById('chatInputArea');
            if (inputArea) {
                inputArea.insertBefore(previewContainer, inputArea.firstChild);
            }
        }

        previewContainer.innerHTML = `
            <div class="image-preview-item">
                <img src="${imageData}" alt="Preview">
                <div class="image-preview-info">
                    <span class="filename">${escapeHTML(filename)}</span>
                    <button class="remove-image-btn" onclick="window.AgroSightAIChat.removeImagePreview()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="image-caption-input">
                    <input type="text" id="imageCaption" placeholder="Add a caption (optional)" maxlength="200">
                    <button class="send-image-btn" onclick="window.AgroSightAIChat.confirmSendImage()">
                        <i class="fas fa-paper-plane"></i> Send
                    </button>
                </div>
            </div>
        `;

        previewContainer.dataset.imageData = imageData;
        previewContainer.style.display = 'block';
    }

    function removeImagePreview() {
        const previewContainer = document.getElementById('imagePreviewContainer');
        if (previewContainer) {
            previewContainer.style.display = 'none';
            previewContainer.innerHTML = '';
            delete previewContainer.dataset.imageData;
        }
    }

    function confirmSendImage() {
        const previewContainer = document.getElementById('imagePreviewContainer');
        if (!previewContainer || !previewContainer.dataset.imageData) return;

        const imageData = previewContainer.dataset.imageData;
        const captionInput = document.getElementById('imageCaption');
        const caption = captionInput ? captionInput.value.trim() : '';

        sendImage(imageData, caption);
        removeImagePreview();
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 9. VOICE RECORDING
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async function startVoiceRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            audioChunks = [];
            recordingStartTime = Date.now();

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                
                // Check size
                if (audioBlob.size > MAX_AUDIO_SIZE) {
                    showToast('Voice note too large. Please record a shorter message.', 'error');
                    stopRecordingUI();
                    return;
                }

                const reader = new FileReader();
                reader.onload = (e) => {
                    const audioData = e.target.result;
                    const duration = Math.round((Date.now() - recordingStartTime) / 1000);
                    showVoicePreview(audioData, duration);
                };
                reader.readAsDataURL(audioBlob);

                // Stop all tracks
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            isRecording = true;
            showRecordingUI();

        } catch (err) {
            console.error('[Chat] Microphone access denied:', err);
            showToast('Microphone access denied. Please allow microphone access.', 'error');
        }
    }

    function stopVoiceRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            isRecording = false;
        }
    }

    function cancelVoiceRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            isRecording = false;
        }
        stopRecordingUI();
        
        // Clear audio chunks without saving
        audioChunks = [];
        
        // Clear preview if any
        removeVoicePreview();
        
        showToast('Recording cancelled', 'info');
    }

    function showRecordingUI() {
        const voiceBtn = document.querySelector('.voice-btn');
        if (voiceBtn) {
            voiceBtn.innerHTML = '<i class="fas fa-stop"></i>';
            voiceBtn.classList.add('recording');
            voiceBtn.title = 'Stop recording';
        }

        // Show recording indicator
        let recordingIndicator = document.getElementById('recordingIndicator');
        if (!recordingIndicator) {
            recordingIndicator = document.createElement('div');
            recordingIndicator.id = 'recordingIndicator';
            recordingIndicator.className = 'recording-indicator';
            
            const inputArea = document.getElementById('chatInputArea');
            if (inputArea) {
                inputArea.insertBefore(recordingIndicator, inputArea.firstChild);
            }
        }

        recordingIndicator.innerHTML = `
            <div class="recording-animation">
                <span></span><span></span><span></span>
            </div>
            <span class="recording-text">Recording...</span>
            <span class="recording-time" id="recordingTime">0:00</span>
            <button class="cancel-recording-btn" onclick="window.AgroSightAIChat.cancelVoiceRecording()">
                <i class="fas fa-times"></i>
            </button>
        `;
        recordingIndicator.style.display = 'flex';

        // Start timer
        recordingInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            const timeEl = document.getElementById('recordingTime');
            if (timeEl) {
                timeEl.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            }
        }, 1000);

        // Disable text input
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.disabled = true;
            messageInput.placeholder = 'Recording voice note...';
        }
    }

    function stopRecordingUI() {
        const voiceBtn = document.querySelector('.voice-btn');
        if (voiceBtn) {
            voiceBtn.innerHTML = '<i class="fas fa-microphone"></i>';
            voiceBtn.classList.remove('recording');
            voiceBtn.title = 'Record voice note';
        }

        const recordingIndicator = document.getElementById('recordingIndicator');
        if (recordingIndicator) {
            recordingIndicator.style.display = 'none';
        }

        if (recordingInterval) {
            clearInterval(recordingInterval);
            recordingInterval = null;
        }

        // Re-enable text input
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.disabled = false;
            messageInput.placeholder = 'Type your message...';
        }
    }

    function showVoicePreview(audioData, duration) {
        stopRecordingUI();

        let previewContainer = document.getElementById('voicePreviewContainer');
        if (!previewContainer) {
            previewContainer = document.createElement('div');
            previewContainer.id = 'voicePreviewContainer';
            previewContainer.className = 'voice-preview-container';
            
            const inputArea = document.getElementById('chatInputArea');
            if (inputArea) {
                inputArea.insertBefore(previewContainer, inputArea.firstChild);
            }
        }

        const durationFormatted = formatDuration(duration);

        previewContainer.innerHTML = `
            <div class="voice-preview-item">
                <div class="voice-preview-player">
                    <audio controls src="${audioData}"></audio>
                    <span class="voice-duration">${durationFormatted}</span>
                </div>
                <div class="voice-preview-actions">
                    <button class="send-voice-btn" onclick="window.AgroSightAIChat.confirmSendVoice()">
                        <i class="fas fa-paper-plane"></i> Send
                    </button>
                    <button class="cancel-voice-btn" onclick="window.AgroSightAIChat.removeVoicePreview()">
                        <i class="fas fa-trash"></i> Discard
                    </button>
                </div>
            </div>
        `;

        previewContainer.dataset.audioData = audioData;
        previewContainer.dataset.duration = duration;
        previewContainer.style.display = 'block';
    }

    function removeVoicePreview() {
        const previewContainer = document.getElementById('voicePreviewContainer');
        if (previewContainer) {
            previewContainer.style.display = 'none';
            previewContainer.innerHTML = '';
            delete previewContainer.dataset.audioData;
            delete previewContainer.dataset.duration;
        }
    }

    function confirmSendVoice() {
        const previewContainer = document.getElementById('voicePreviewContainer');
        if (!previewContainer || !previewContainer.dataset.audioData) return;

        const audioData = previewContainer.dataset.audioData;
        const duration = parseInt(previewContainer.dataset.duration) || 0;

        sendVoiceNote(audioData, duration);
        removeVoicePreview();
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 10. LOAD CONVERSATIONS
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function loadConversations() {
        if (!currentUser) return;

        fetch(`${API_BASE_URL}/conversations/${currentUser.id}`, { headers: getAuthHeaders() })
            .then(res => res.json())
            .then(data => {
                conversations = data.conversations || [];
                renderConversationList(conversations);
            })
            .catch(err => {
                console.error('[Chat] Failed to load conversations:', err);
            });
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 11. OPEN CONVERSATION
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function openConversation(otherUserId, otherUserName, otherUserRole) {
        activeChat = otherUserId;
        activeChatMeta = {
            name: otherUserName || otherUserId,
            role: otherUserRole || 'User'
        };

        updateChatHeader(activeChatMeta);

        const inputArea = document.getElementById('chatInputArea');
        if (inputArea) inputArea.classList.add('visible');

        fetch(`${API_BASE_URL}/messages/${currentUser.id}/${otherUserId}`, { headers: getAuthHeaders() })
            .then(res => res.json())
            .then(data => {
                renderMessageHistory(data.messages || []);
                scrollToBottom();

                socket.emit('mark_read', {
                    userId: currentUser.id,
                    otherUserId: otherUserId
                });

                clearUnread(otherUserId);
            })
            .catch(err => {
                console.error('[Chat] Failed to load messages:', err);
                renderMessageHistory([]);
            });
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 12. DOM RENDERING â€” CONVERSATION LIST
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function renderConversationList(convList) {
        const container = document.getElementById('conversationList');
        if (!container) return;

        if (convList.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-comments"></i>
                    <p>No conversations yet</p>
                </div>
            `;
            return;
        }

        container.innerHTML = convList.map(conv => {
            const otherName = conv.otherUser;
            const lastMsg = conv.lastMessage;
            const timeStr = formatTime(lastMsg.timestamp);
            const isActive = activeChat === otherName;
            const unreadBadge = conv.unreadCount > 0 
                ? `<span class="unread-badge">${conv.unreadCount}</span>` 
                : '';
            const onlineClass = isUserOnline(otherName) ? 'online' : '';

            // Preview text based on message type
            let previewText = lastMsg.text || '';
            if (lastMsg.type === 'image') {
                previewText = 'ðŸ“· Photo';
            } else if (lastMsg.type === 'voice') {
                previewText = 'ðŸŽ¤ Voice note';
            }

            return `
                <div class="conversation-item ${isActive ? 'active' : ''} ${onlineClass}" 
                     data-user-id="${otherName}">
                    <div class="conv-avatar">
                        <i class="fas fa-user-circle"></i>
                        <span class="status-dot ${onlineClass}"></span>
                    </div>
                    <div class="conv-details">
                        <div class="conv-top">
                            <span class="conv-name">${escapeHTML(otherName)}</span>
                            <span class="conv-time">${timeStr}</span>
                        </div>
                        <div class="conv-bottom">
                            <span class="conv-preview">${escapeHTML(previewText)}</span>
                            ${unreadBadge}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        container.querySelectorAll('.conversation-item').forEach(item => {
            item.addEventListener('click', () => {
                const userId = item.dataset.userId;
                const userName = item.querySelector('.conv-name')?.textContent || userId;
                openConversation(
                    userId,
                    userName,
                    'user'
                );
                container.querySelectorAll('.conversation-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
            });
        });
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 13. DOM RENDERING â€” MESSAGES
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function renderMessageHistory(messageList) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        if (messageList.length === 0) {
            container.innerHTML = `
                <div class="placeholder-message">
                    <i class="fas fa-comment-dots"></i>
                    <p>No messages yet. Start the conversation!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = messageList.map(msg => {
            const isMine = msg.sender === currentUser.id;
            return buildMessageHTML(msg, isMine ? 'sent' : 'received');
        }).join('');

        // Add click handlers for image lightbox
        container.querySelectorAll('.message-image').forEach(img => {
            img.addEventListener('click', () => {
                openImageLightbox(img.src);
            });
        });
    }

    function appendMessage(msg, direction) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        const placeholder = container.querySelector('.placeholder-message');
        if (placeholder) placeholder.remove();

        const html = buildMessageHTML(msg, direction);
        container.insertAdjacentHTML('beforeend', html);

        // Add click handler for images
        const newMsg = container.lastElementChild;
        const img = newMsg.querySelector('.message-image');
        if (img) {
            img.addEventListener('click', () => openImageLightbox(img.src));
        }
    }

    function buildMessageHTML(msg, direction) {
        const isSent = direction === 'sent';
        const timeStr = formatTime(msg.timestamp);
        const pendingClass = msg.pending ? 'pending' : '';
        let contentHTML = '';
        let statusIcon = '';

        // Build content based on message type
        switch (msg.type) {
            case 'image':
                contentHTML = `
                    <div class="message-image-wrapper">
                        <img class="message-image" src="${escapeHTML(msg.image)}" alt="Shared image" loading="lazy">
                    </div>
                    ${msg.caption ? `<div class="message-caption">${escapeHTML(msg.caption)}</div>` : ''}
                `;
                break;

            case 'voice':
                const duration = formatDuration(msg.duration || 0);
                contentHTML = `
                    <div class="message-voice-wrapper ${isSent ? 'sent' : 'received'}">
                        <button class="voice-play-btn" onclick="window.AgroSightAIChat.playPauseAudio(this)">
                            <i class="fas fa-play"></i>
                        </button>
                        <div class="voice-waveform">
                            <span></span><span></span><span></span><span></span><span></span>
                        </div>
                        <span class="voice-duration">${duration}</span>
                        <audio class="voice-audio" src="${escapeHTML(msg.audio)}" preload="metadata"></audio>
                    </div>
                `;
                break;

            default:
                contentHTML = `<div class="message-text">${escapeHTML(msg.text)}</div>`;
        }

        // Status icon for sent messages
        if (isSent) {
            statusIcon = msg.read 
                ? '<i class="fas fa-check-double read"></i>' 
                : (msg.pending ? '<i class="fas fa-clock sending"></i>' : '<i class="fas fa-check"></i>');
        }

        return `
            <div class="message-bubble ${direction} ${pendingClass}" data-msg-id="${msg.id || ''}" data-type="${msg.type || 'text'}">
                ${contentHTML}
                <div class="message-meta">
                    <span class="message-time">${timeStr}</span>
                    ${statusIcon}
                </div>
            </div>
        `;
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 14. AUDIO PLAYBACK
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function playPauseAudio(button) {
        const wrapper = button.closest('.message-voice-wrapper');
        const audio = wrapper.querySelector('.voice-audio');
        const icon = button.querySelector('i');
        const waveform = wrapper.querySelector('.voice-waveform');

        if (audio.paused) {
            // Pause all other audios first
            document.querySelectorAll('.voice-audio').forEach(a => {
                if (a !== audio) {
                    a.pause();
                    const otherIcon = a.closest('.message-voice-wrapper').querySelector('.voice-play-btn i');
                    if (otherIcon) {
                        otherIcon.className = 'fas fa-play';
                    }
                }
            });

            audio.play();
            icon.className = 'fas fa-pause';
            waveform.classList.add('playing');

            audio.onended = () => {
                icon.className = 'fas fa-play';
                waveform.classList.remove('playing');
            };
        } else {
            audio.pause();
            icon.className = 'fas fa-play';
            waveform.classList.remove('playing');
        }
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 15. IMAGE LIGHTBOX
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function openImageLightbox(src) {
        // Remove existing lightbox
        const existing = document.getElementById('imageLightbox');
        if (existing) existing.remove();

        const lightbox = document.createElement('div');
        lightbox.id = 'imageLightbox';
        lightbox.className = 'image-lightbox';
        lightbox.innerHTML = `
            <div class="lightbox-overlay" onclick="window.AgroSightAIChat.closeLightbox()"></div>
            <div class="lightbox-content">
                <button class="lightbox-close" onclick="window.AgroSightAIChat.closeLightbox()">
                    <i class="fas fa-times"></i>
                </button>
                <img src="${escapeHTML(src)}" alt="Full size image">
            </div>
        `;

        document.body.appendChild(lightbox);
        document.body.style.overflow = 'hidden';

        // Animate in
        requestAnimationFrame(() => {
            lightbox.classList.add('visible');
        });
    }

    function closeLightbox() {
        const lightbox = document.getElementById('imageLightbox');
        if (lightbox) {
            lightbox.classList.remove('visible');
            setTimeout(() => lightbox.remove(), 300);
            document.body.style.overflow = '';
        }
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 16. UI HELPERS
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function updateChatHeader(meta) {
        const header = document.getElementById('currentChatHeader');
        if (!header) return;

        const onlineClass = isUserOnline(activeChat) ? 'online' : 'offline';
        const statusText = onlineClass === 'online' ? 'Online' : 'Offline';

        header.innerHTML = `
            <div class="chat-header-avatar ${onlineClass}">
                <i class="fas fa-user-circle"></i>
                <span class="status-dot ${onlineClass}"></span>
            </div>
            <div class="chat-header-info">
                <h4>${escapeHTML(meta.name)}</h4>
                <span class="chat-header-status ${onlineClass}">${statusText}</span>
            </div>
        `;
    }

    function showTypingIndicator(isTyping) {
        let indicator = document.getElementById('typingIndicator');
        if (!indicator) {
            const chatMessages = document.getElementById('chatMessages');
            if (!chatMessages) return;
            indicator = document.createElement('div');
            indicator.id = 'typingIndicator';
            indicator.className = 'typing-indicator';
            indicator.innerHTML = '<span></span><span></span><span></span>';
            chatMessages.appendChild(indicator);
        }
        indicator.classList.toggle('visible', isTyping);
        if (isTyping) scrollToBottom();
    }

    function updateConnectionStatus(connected) {
        let indicator = document.getElementById('connectionStatus');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'connectionStatus';
            indicator.className = 'connection-status';
            document.body.appendChild(indicator);
        }
        indicator.className = `connection-status ${connected ? 'connected' : 'disconnected'}`;
        indicator.textContent = connected ? 'Connected' : 'Reconnecting...';
    }

    function scrollToBottom() {
        const container = document.getElementById('chatMessages');
        if (container) {
            requestAnimationFrame(() => {
                container.scrollTop = container.scrollHeight;
            });
        }
    }

    function incrementUnread(userId) {
        const items = document.querySelectorAll('.conversation-item');
        items.forEach(item => {
            if (item.dataset.userId === userId) {
                let badge = item.querySelector('.unread-badge');
                if (!badge) {
                    const bottom = item.querySelector('.conv-bottom');
                    if (bottom) {
                        badge = document.createElement('span');
                        badge.className = 'unread-badge';
                        bottom.appendChild(badge);
                    }
                }
                if (badge) {
                    const current = parseInt(badge.textContent) || 0;
                    badge.textContent = current + 1;
                }
            }
        });
    }

    function clearUnread(userId) {
        const items = document.querySelectorAll('.conversation-item');
        items.forEach(item => {
            if (item.dataset.userId === userId) {
                const badge = item.querySelector('.unread-badge');
                if (badge) badge.remove();
            }
        });
    }

    function markMessageDelivered(msgId) {
        const el = document.querySelector(`.message-bubble[data-msg-id="${msgId}"]`);
        if (el) {
            el.classList.remove('pending');
            const clockIcon = el.querySelector('.fa-clock');
            if (clockIcon) {
                clockIcon.className = 'fas fa-check';
            }
        }
    }

    function updateReadReceipts() {
        const bubbles = document.querySelectorAll('.message-bubble.sent .message-meta i');
        bubbles.forEach(icon => {
            if (icon.classList.contains('fa-check') && !icon.classList.contains('read')) {
                icon.classList.remove('fa-check');
                icon.classList.add('fa-check-double', 'read');
            }
        });
    }

    function updateOnlineStatuses(usersObj) {
        const items = document.querySelectorAll('.conversation-item');
        items.forEach(item => {
            const userId = item.dataset.userId;
            const isOnline = usersObj.hasOwnProperty(userId);
            const dot = item.querySelector('.status-dot');
            if (dot) {
                dot.className = `status-dot ${isOnline ? 'online' : ''}`;
            }
        });

        if (activeChat) {
            const isOnline = usersObj.hasOwnProperty(activeChat);
            const headerDot = document.querySelector('#currentChatHeader .status-dot');
            if (headerDot) {
                headerDot.className = `status-dot ${isOnline ? 'online' : ''}`;
            }
            const headerStatus = document.querySelector('.chat-header-status');
            if (headerStatus) {
                headerStatus.textContent = isOnline ? 'Online' : 'Offline';
                headerStatus.className = `chat-header-status ${isOnline ? 'online' : 'offline'}`;
            }
        }
    }

    function isUserOnline(userId) {
        const dot = document.querySelector(`.conversation-item[data-user-id="${userId}"] .status-dot`);
        return dot && dot.classList.contains('online');
    }

    function showToastNotification(message) {
        let preview = 'New message';
        if (message.type === 'image') {
            preview = 'Sent a photo';
        } else if (message.type === 'voice') {
            preview = 'Sent a voice note';
        } else if (message.text) {
            preview = message.text.slice(0, 50);
        }

        if (typeof showToast === 'function') {
            showToast(`New message: ${preview}`, 'info');
        }
    }

    function playNotificationSound() {
        try {
            const audio = new Audio('data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=');
            audio.volume = 0.3;
            audio.play().catch(() => {});
        } catch(e) {}
    }

    function showToast(message, type = 'info') {
        if (typeof window.showToast === 'function' && window.showToast !== showToast) {
            window.showToast(message, type);
        } else {
            console.log(`[Toast] ${type}: ${message}`);
        }
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 17. UTILITY FUNCTIONS
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function formatTime(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;

        if (diff < 86400000 && date.getDate() === now.getDate()) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        if (diff < 604800000) {
            return date.toLocaleDateString([], { weekday: 'short' });
        }
        return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }

    function formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    function escapeHTML(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 18. EVENT BINDINGS
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function initEventBindings() {
        // â”€â”€ Send Button â”€â”€
        const sendBtn = document.getElementById('sendMessageBtn');
        if (sendBtn) {
            sendBtn.addEventListener('click', () => {
                const input = document.getElementById('messageInput');
                if (input && input.value.trim()) {
                    sendMessage(input.value);
                    input.value = '';
                    input.style.height = 'auto';
                }
            });
        }

        // â”€â”€ Message Input â”€â”€
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (messageInput.value.trim()) {
                        sendMessage(messageInput.value);
                        messageInput.value = '';
                        messageInput.style.height = 'auto';
                    }
                }
            });

            messageInput.addEventListener('input', () => {
                messageInput.style.height = 'auto';
                messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';

                if (socket && activeChat) {
                    socket.emit('typing', {
                        senderId: currentUser.id,
                        receiverId: activeChat,
                        isTyping: true
                    });

                    clearTimeout(typingTimer);
                    typingTimer = setTimeout(() => {
                        socket.emit('typing', {
                            senderId: currentUser.id,
                            receiverId: activeChat,
                            isTyping: false
                        });
                    }, TYPING_TIMEOUT);
                }
            });
        }

        // â”€â”€ Voice Button â”€â”€
        const voiceBtn = document.querySelector('.voice-btn');
        if (voiceBtn) {
            voiceBtn.addEventListener('click', () => {
                if (isRecording) {
                    stopVoiceRecording();
                } else {
                    startVoiceRecording();
                }
            });
        }

        // â”€â”€ Image Button â”€â”€
        const imgBtn = document.querySelector('.img-btn');
        if (imgBtn) {
            imgBtn.addEventListener('click', () => {
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'image/*';
                input.onchange = (e) => {
                    if (e.target.files[0]) {
                        handleImageSelect(e.target.files[0]);
                    }
                };
                input.click();
            });
        }

        // â”€â”€ Paste Image from Clipboard â”€â”€
        document.addEventListener('paste', (e) => {
            const items = e.clipboardData.items;
            for (let item of items) {
                if (item.type.startsWith('image/')) {
                    const file = item.getAsFile();
                    if (file) {
                        handleImageSelect(file);
                    }
                    break;
                }
            }
        });

        // â”€â”€ Drag & Drop Image â”€â”€
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            chatMessages.addEventListener('dragover', (e) => {
                e.preventDefault();
                chatMessages.classList.add('dragover');
            });

            chatMessages.addEventListener('dragleave', () => {
                chatMessages.classList.remove('dragover');
            });

            chatMessages.addEventListener('drop', (e) => {
                e.preventDefault();
                chatMessages.classList.remove('dragover');
                
                const file = e.dataTransfer.files[0];
                if (file && file.type.startsWith('image/')) {
                    handleImageSelect(file);
                }
            });
        }

        // â”€â”€ Keyboard Shortcuts â”€â”€
        document.addEventListener('keydown', (e) => {
            // Escape to close lightbox
            if (e.key === 'Escape') {
                closeLightbox();
            }
        });
    }

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 19. PUBLIC API
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    window.AgroSightAIChat = {
        openConversation: openConversation,
        sendMessage: sendMessage,
        sendImage: sendImage,
        sendVoiceNote: sendVoiceNote,
        loadConversations: loadConversations,
        getCurrentUser: () => currentUser,
        isConnected: () => isConnected,
        
        // Voice recording controls
        cancelVoiceRecording: cancelVoiceRecording,
        confirmSendVoice: confirmSendVoice,
        removeVoicePreview: removeVoicePreview,
        
        // Image controls
        removeImagePreview: removeImagePreview,
        confirmSendImage: confirmSendImage,
        
        // Audio playback
        playPauseAudio: playPauseAudio,
        
        // Lightbox
        closeLightbox: closeLightbox
    };

    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // 20. INITIALIZE
    // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    function init() {
        // Skip auto-init if running alongside farmer.js or agrovet.js dashboards,
        // which already bind their own messaging events and Socket.IO connections.
        const page = window.location.pathname;
        const isDashboard = page.includes('farmer-dashboard') || page.includes('agrovet-dashboard');
        if (isDashboard) {
            console.log('[Chat] Dashboard detected. Skipping auto-init to avoid duplicate event bindings.');
            return;
        }

        console.log('[Chat] Initializing AgroSight AI messaging with media support...');
        currentUser = loadCurrentUser();

        if (!currentUser) {
            console.warn('[Chat] No logged-in user. Chat disabled.');
            return;
        }

        console.log(`[Chat] Logged in as ${currentUser.username || currentUser.email} (${currentUser.role})`);
        initEventBindings();
        connect();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();