// Run: npm init -y && npm install express socket.io cors
// Then: node server.js

const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' })); // Increase limit for base64 images/audio

// Create uploads directory if it doesn't exist
const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir, { recursive: true });
}
app.use('/uploads', express.static(uploadsDir));

// In-memory storage
const messages = new Map();
const onlineUsers = new Map();
const unreadCounts = new Map();

const server = http.createServer(app);
const io = new Server(server, {
    cors: {
        origin: '*',
        methods: ['GET', 'POST']
    },
    maxHttpBufferSize: 50e6 // 50MB for large files
});

// Health check
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        onlineUsers: onlineUsers.size,
        totalConversations: messages.size
    });
});

// Fetch conversation history
app.get('/api/messages/:user1/:user2', (req, res) => {
    const conversationId = getConversationId(req.params.user1, req.params.user2);
    const history = messages.get(conversationId) || [];
    res.json({ conversationId, messages: history });
});

// Fetch all conversations for a user
app.get('/api/conversations/:userId', (req, res) => {
    const userId = req.params.userId;
    const userConversations = [];

    for (const [convId, msgs] of messages.entries()) {
        if (convId.includes(userId)) {
            const parts = convId.split('_');
            const otherUser = parts[0] === userId ? parts[1] : parts[0];
            const lastMsg = msgs[msgs.length - 1];
            
            if (lastMsg) {
                const unread = msgs.filter(m => m.to === userId && !m.read).length;
                userConversations.push({
                    conversationId: convId,
                    otherUser,
                    lastMessage: lastMsg,
                    unreadCount: unread,
                    totalMessages: msgs.length
                });
            }
        }
    }

    userConversations.sort((a, b) => 
        new Date(b.lastMessage.timestamp) - new Date(a.lastMessage.timestamp)
    );

    res.json({ conversations: userConversations });
});

// Upload media file (image or audio)
app.post('/api/upload', (req, res) => {
    const { data, type, sender, recipient } = req.body;
    
    if (!data || !type) {
        return res.status(400).json({ error: 'Missing data or type' });
    }

    // Generate unique filename
    const ext = type === 'image' ? 'png' : 'webm';
    const filename = `${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`;
    const filepath = path.join(uploadsDir, filename);

    // Remove data URL prefix and save
    const base64Data = data.replace(/^data:[^;]+;base64,/, '');
    fs.writeFileSync(filepath, base64Data, 'base64');

    const fileUrl = `/uploads/${filename}`;

    res.json({
        success: true,
        url: fileUrl,
        filename,
        type
    });
});

function getConversationId(user1, user2) {
    return [user1, user2].sort().join('_');
}

io.on('connection', (socket) => {
    console.log(`[CONNECT] Socket ${socket.id} connected`);

    socket.on('join', (userData) => {
        const { userId, role, name, avatar } = userData;

        if (!userId) {
            console.warn('[JOIN] Missing userId, ignoring');
            return;
        }

        onlineUsers.set(userId, {
            socketId: socket.id,
            role: role || 'unknown',
            name: name || userId,
            avatar: avatar || ''
        });

        socket.join(userId);
        console.log(`[JOIN] ${name} (${role}) joined as ${userId}`);
        io.emit('users_online', Object.fromEntries(onlineUsers));

        const unreads = unreadCounts.get(userId) || [];
        if (unreads.length > 0) {
            io.to(userId).emit('unread_update', { count: unreads.length });
        }
    });

    // â”€â”€ TEXT MESSAGE â”€â”€
    socket.on('private_message', (data) => {
        const { senderId, receiverId, text, timestamp } = data;

        if (!senderId || !receiverId || !text) {
            console.warn('[MESSAGE] Invalid data:', data);
            return;
        }

        const conversationId = getConversationId(senderId, receiverId);

        const message = {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            sender: senderId,
            to: receiverId,
            text: text.trim(),
            timestamp: timestamp || new Date().toISOString(),
            type: 'text',
            read: false
        };

        if (!messages.has(conversationId)) {
            messages.set(conversationId, []);
        }
        messages.get(conversationId).push(message);

        console.log(`[MSG] ${senderId} â†’ ${receiverId}: "${text.slice(0, 50)}"`);

        io.to(receiverId).emit('new_message', { ...message, conversationId });
        io.to(senderId).emit('message_sent', { ...message, conversationId });
    });

    // â”€â”€ IMAGE MESSAGE â”€â”€
    socket.on('image_message', (data) => {
        const { senderId, receiverId, image, caption, timestamp } = data;

        if (!senderId || !receiverId || !image) {
            console.warn('[IMAGE] Invalid data');
            return;
        }

        const conversationId = getConversationId(senderId, receiverId);

        const message = {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            sender: senderId,
            to: receiverId,
            type: 'image',
            image: image, // Base64 data URL or URL
            caption: caption || '',
            timestamp: timestamp || new Date().toISOString(),
            read: false
        };

        if (!messages.has(conversationId)) {
            messages.set(conversationId, []);
        }
        messages.get(conversationId).push(message);

        console.log(`[IMAGE] ${senderId} â†’ ${receiverId}: Image sent`);

        io.to(receiverId).emit('new_message', { ...message, conversationId });
        io.to(senderId).emit('message_sent', { ...message, conversationId });
    });

    // â”€â”€ VOICE MESSAGE â”€â”€
    socket.on('voice_message', (data) => {
        const { senderId, receiverId, audio, duration, timestamp } = data;

        if (!senderId || !receiverId || !audio) {
            console.warn('[VOICE] Invalid data');
            return;
        }

        const conversationId = getConversationId(senderId, receiverId);

        const message = {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            sender: senderId,
            to: receiverId,
            type: 'voice',
            audio: audio, // Base64 data URL
            duration: duration || 0,
            timestamp: timestamp || new Date().toISOString(),
            read: false
        };

        if (!messages.has(conversationId)) {
            messages.set(conversationId, []);
        }
        messages.get(conversationId).push(message);

        console.log(`[VOICE] ${senderId} â†’ ${receiverId}: Voice note (${duration}s)`);

        io.to(receiverId).emit('new_message', { ...message, conversationId });
        io.to(senderId).emit('message_sent', { ...message, conversationId });
    });

    // â”€â”€ TYPING INDICATOR â”€â”€
    socket.on('typing', (data) => {
        const { senderId, receiverId, isTyping } = data;
        io.to(receiverId).emit('show_typing', { senderId, isTyping });
    });

    // â”€â”€ MARK AS READ â”€â”€
    socket.on('mark_read', (data) => {
        const { userId, otherUserId } = data;
        const conversationId = getConversationId(userId, otherUserId);

        const conversation = messages.get(conversationId);
        if (conversation) {
            let updated = false;
            conversation.forEach(msg => {
                if (msg.to === userId && !msg.read) {
                    msg.read = true;
                    updated = true;
                }
            });

            if (updated) {
                io.to(otherUserId).emit('messages_read', {
                    readBy: userId,
                    conversationId
                });
            }
        }
    });

    // â”€â”€ GET ONLINE USERS â”€â”€
    socket.on('get_online_users', () => {
        socket.emit('users_online', Object.fromEntries(onlineUsers));
    });

    // â”€â”€ DISCONNECT â”€â”€
    socket.on('disconnect', () => {
        for (const [userId, info] of onlineUsers.entries()) {
            if (info.socketId === socket.id) {
                onlineUsers.delete(userId);
                console.log(`[DISCONNECT] ${userId} went offline`);
                io.emit('users_online', Object.fromEntries(onlineUsers));
                break;
            }
        }
    });
});

const PORT = process.env.PORT || 5001;
const SOCKET_PATH = process.env.SOCKET_PATH || '';

// Support Unix socket for Nginx reverse proxy in Docker
const listenTarget = SOCKET_PATH || PORT;
const isUnixSocket = typeof listenTarget === 'string' && listenTarget.startsWith('/');

server.listen(listenTarget, () => {
    if (isUnixSocket) {
        // Ensure Nginx can read the socket
        const { chmodSync } = require('fs');
        try { chmodSync(listenTarget, 0o777); } catch (e) {}
        console.log(`AgroSight AI Messaging Server listening on Unix socket ${listenTarget}`);
    } else {
        console.log(`AgroSight AI Messaging Server running on port ${listenTarget}`);
        console.log(`Socket.IO endpoint: http://localhost:${listenTarget}`);
        console.log(`Health check: http://localhost:${listenTarget}/health`);
    }
});