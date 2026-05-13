// ═══════════════════════════════════════════════════════════════
// AgroSight AI — Real-time Messaging Server (Redis Pub/Sub)
// ═══════════════════════════════════════════════════════════════
// Features:
//   • Socket.IO with Redis adapter for multi-instance scaling
//   • Redis TTL-based online user tracking
//   • Async message retry queue for offline recipients
//   • Health checks & graceful shutdown
// ═══════════════════════════════════════════════════════════════

const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const { createAdapter } = require('@socket.io/redis-adapter');
const { createClient } = require('redis');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

// ── Configuration ──
const PORT = process.env.PORT || 5001;
const SOCKET_PATH = process.env.SOCKET_PATH || '';
const REDIS_URL = process.env.REDIS_URL || 'redis://redis:6379/0';
const FLASK_API_URL = process.env.FLASK_API_URL || 'http://api:5000/api';
const MESSAGE_RETRY_MS = parseInt(process.env.MESSAGE_RETRY_MS || '5000', 10);
const ONLINE_TTL_SECONDS = parseInt(process.env.ONLINE_TTL_SECONDS || '120', 10);

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' }));

// Uploads directory
const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir, { recursive: true });
}
app.use('/uploads', express.static(uploadsDir));

// ── Redis Clients ──
const pubClient = createClient({ url: REDIS_URL });
const subClient = createClient({ url: REDIS_URL });
const redisClient = createClient({ url: REDIS_URL });

let redisReady = false;

async function initRedis() {
    try {
        await pubClient.connect();
        await subClient.connect();
        await redisClient.connect();
        redisReady = true;
        console.log('[Redis] Connected');
    } catch (err) {
        console.warn('[Redis] Connection failed:', err.message);
        redisReady = false;
    }
}

// ── Socket.IO + Redis Adapter ──
const server = http.createServer(app);
const io = new Server(server, {
    cors: { origin: '*', methods: ['GET', 'POST'] },
    maxHttpBufferSize: 50e6,
    pingTimeout: 60000,
    pingInterval: 25000,
});

(async () => {
    await initRedis();
    if (redisReady) {
        io.adapter(createAdapter(pubClient, subClient));
        console.log('[Socket.IO] Redis adapter enabled');
    } else {
        console.warn('[Socket.IO] Running in single-instance mode (no Redis)');
    }
})();

// ── Helpers ──
function getConversationId(user1, user2) {
    return [String(user1), String(user2)].sort().join('_');
}

async function setUserOnline(userId, role, name, avatar) {
    if (!redisReady) return;
    const data = JSON.stringify({ role, name, avatar, ts: Date.now() });
    await redisClient.setEx(`agrosight:online:${userId}`, ONLINE_TTL_SECONDS, data);
}

async function setUserOffline(userId) {
    if (!redisReady) return;
    await redisClient.del(`agrosight:online:${userId}`);
}

async function getOnlineUsers() {
    if (!redisReady) return {};
    const keys = await redisClient.keys('agrosight:online:*');
    const users = {};
    for (const key of keys) {
        const id = key.split(':').pop();
        const val = await redisClient.get(key);
        if (val) {
            try {
                users[id] = JSON.parse(val);
            } catch (e) {
                users[id] = {};
            }
        }
    }
    return users;
}

async function queueMessage(msg) {
    if (!redisReady) return;
    const key = `agrosight:queue:${msg.to}`;
    await redisClient.lPush(key, JSON.stringify(msg));
    await redisClient.expire(key, 86400); // 24h queue TTL
}

async function drainQueue(userId, socket) {
    if (!redisReady) return;
    const key = `agrosight:queue:${userId}`;
    const len = await redisClient.lLen(key);
    if (len === 0) return;
    console.log(`[Queue] Draining ${len} queued messages for ${userId}`);
    for (let i = 0; i < len; i++) {
        const raw = await redisClient.rPop(key);
        if (raw) {
            try {
                const msg = JSON.parse(raw);
                socket.emit('new_message', msg);
            } catch (e) {
                console.warn('[Queue] Failed to parse queued message:', e.message);
            }
        }
    }
}

async function persistMessageToFlask(msg) {
    // Fire-and-forget async persistence to Flask backend
    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        await fetch(`${FLASK_API_URL}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                receiver_id: parseInt(msg.to, 10),
                text: msg.text || '',
                type: msg.type || 'text',
                media_url: msg.image || msg.audio || null,
            }),
            signal: controller.signal,
        });
        clearTimeout(timeout);
    } catch (err) {
        // Non-critical: message already delivered via WebSocket
        console.warn('[Persist] Failed to persist message to Flask:', err.message);
    }
}

function storeMedia(base64Data, type) {
    const ext = type === 'image' ? 'png' : 'webm';
    const filename = `${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`;
    const filepath = path.join(uploadsDir, filename);
    const clean = base64Data.replace(/^data:[^;]+;base64,/, '');
    fs.writeFileSync(filepath, clean, 'base64');
    return `/uploads/${filename}`;
}

// ── Routes ──
app.get('/health', async (req, res) => {
    const online = redisReady ? Object.keys(await getOnlineUsers()).length : 0;
    res.json({
        status: 'ok',
        redis: redisReady,
        onlineUsers: online,
        uptime: process.uptime(),
    });
});

app.get('/api/messages/:user1/:user2', async (req, res) => {
    const conversationId = getConversationId(req.params.user1, req.params.user2);
    // Try Redis first (cached recent messages)
    let history = [];
    if (redisReady) {
        const raw = await redisClient.get(`agrosight:history:${conversationId}`);
        if (raw) {
            try {
                history = JSON.parse(raw);
            } catch (e) {}
        }
    }
    res.json({ conversationId, messages: history, source: 'redis' });
});

app.get('/api/conversations/:userId', async (req, res) => {
    const userId = req.params.userId;
    const userConversations = [];
    if (redisReady) {
        const keys = await redisClient.keys('agrosight:history:*');
        for (const key of keys) {
            const convId = key.replace('agrosight:history:', '');
            if (convId.includes(userId)) {
                const raw = await redisClient.get(key);
                if (raw) {
                    let msgs = [];
                    try {
                        msgs = JSON.parse(raw);
                    } catch (e) {
                        continue;
                    }
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
                            totalMessages: msgs.length,
                        });
                    }
                }
            }
        }
    }
    userConversations.sort((a, b) =>
        new Date(b.lastMessage.timestamp) - new Date(a.lastMessage.timestamp)
    );
    res.json({ conversations: userConversations });
});

app.post('/api/upload', (req, res) => {
    const { data, type } = req.body;
    if (!data || !type) {
        return res.status(400).json({ error: 'Missing data or type' });
    }
    const fileUrl = storeMedia(data, type);
    res.json({ success: true, url: fileUrl, type });
});

// ── Socket.IO Events ──
io.on('connection', (socket) => {
    console.log(`[CONNECT] Socket ${socket.id} connected`);

    socket.on('join', async (userData) => {
        const { userId, role, name, avatar } = userData;
        if (!userId) {
            console.warn('[JOIN] Missing userId');
            return;
        }
        socket.join(userId);
        await setUserOnline(userId, role, name, avatar);
        console.log(`[JOIN] ${name} (${role}) joined as ${userId}`);

        const online = await getOnlineUsers();
        io.emit('users_online', online);

        // Drain any queued messages for this user
        await drainQueue(userId, socket);
    });

    // ── TEXT MESSAGE ──
    socket.on('private_message', async (data) => {
        const { senderId, receiverId, text, timestamp } = data;
        if (!senderId || !receiverId || !text) {
            console.warn('[MESSAGE] Invalid data');
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
            read: false,
        };

        // Cache in Redis
        if (redisReady) {
            const key = `agrosight:history:${conversationId}`;
            let history = [];
            const raw = await redisClient.get(key);
            if (raw) {
                try {
                    history = JSON.parse(raw);
                } catch (e) {}
            }
            history.push(message);
            // Keep last 200 messages per conversation
            if (history.length > 200) history = history.slice(-200);
            await redisClient.setEx(key, 86400, JSON.stringify(history));
        }

        // Deliver instantly
        io.to(receiverId).emit('new_message', { ...message, conversationId });
        io.to(senderId).emit('message_sent', { ...message, conversationId });

        // Persist asynchronously to Flask DB
        persistMessageToFlask(message);

        // If recipient is not online, queue for retry
        const online = await getOnlineUsers();
        if (!online[String(receiverId)]) {
            await queueMessage(message);
            console.log(`[MSG] ${senderId} → ${receiverId} (queued, offline)`);
        } else {
            console.log(`[MSG] ${senderId} → ${receiverId}: "${text.slice(0, 50)}"`);
        }
    });

    // ── IMAGE MESSAGE ──
    socket.on('image_message', async (data) => {
        const { senderId, receiverId, image, caption, timestamp } = data;
        if (!senderId || !receiverId || !image) return;

        const conversationId = getConversationId(senderId, receiverId);
        const message = {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            sender: senderId,
            to: receiverId,
            type: 'image',
            image: image,
            caption: caption || '',
            timestamp: timestamp || new Date().toISOString(),
            read: false,
        };

        if (redisReady) {
            const key = `agrosight:history:${conversationId}`;
            let history = [];
            const raw = await redisClient.get(key);
            if (raw) {
                try {
                    history = JSON.parse(raw);
                } catch (e) {}
            }
            history.push(message);
            if (history.length > 200) history = history.slice(-200);
            await redisClient.setEx(key, 86400, JSON.stringify(history));
        }

        io.to(receiverId).emit('new_message', { ...message, conversationId });
        io.to(senderId).emit('message_sent', { ...message, conversationId });

        persistMessageToFlask(message);

        const online = await getOnlineUsers();
        if (!online[String(receiverId)]) {
            await queueMessage(message);
        }
        console.log(`[IMAGE] ${senderId} → ${receiverId}`);
    });

    // ── VOICE MESSAGE ──
    socket.on('voice_message', async (data) => {
        const { senderId, receiverId, audio, duration, timestamp } = data;
        if (!senderId || !receiverId || !audio) return;

        const conversationId = getConversationId(senderId, receiverId);
        const message = {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            sender: senderId,
            to: receiverId,
            type: 'voice',
            audio: audio,
            duration: duration || 0,
            timestamp: timestamp || new Date().toISOString(),
            read: false,
        };

        if (redisReady) {
            const key = `agrosight:history:${conversationId}`;
            let history = [];
            const raw = await redisClient.get(key);
            if (raw) {
                try {
                    history = JSON.parse(raw);
                } catch (e) {}
            }
            history.push(message);
            if (history.length > 200) history = history.slice(-200);
            await redisClient.setEx(key, 86400, JSON.stringify(history));
        }

        io.to(receiverId).emit('new_message', { ...message, conversationId });
        io.to(senderId).emit('message_sent', { ...message, conversationId });

        persistMessageToFlask(message);

        const online = await getOnlineUsers();
        if (!online[String(receiverId)]) {
            await queueMessage(message);
        }
        console.log(`[VOICE] ${senderId} → ${receiverId} (${duration}s)`);
    });

    // ── TYPING ──
    socket.on('typing', (data) => {
        const { senderId, receiverId, isTyping } = data;
        io.to(receiverId).emit('show_typing', { senderId, isTyping });
    });

    // ── MARK READ ──
    socket.on('mark_read', async (data) => {
        const { userId, otherUserId } = data;
        const conversationId = getConversationId(userId, otherUserId);
        if (redisReady) {
            const key = `agrosight:history:${conversationId}`;
            const raw = await redisClient.get(key);
            if (raw) {
                try {
                    const history = JSON.parse(raw);
                    let updated = false;
                    for (const msg of history) {
                        if (msg.to === userId && !msg.read) {
                            msg.read = true;
                            updated = true;
                        }
                    }
                    if (updated) {
                        await redisClient.setEx(key, 86400, JSON.stringify(history));
                    }
                } catch (e) {}
            }
        }
        io.to(otherUserId).emit('messages_read', { readBy: userId, conversationId });
    });

    // ── DISCONNECT ──
    socket.on('disconnect', async () => {
        const rooms = Array.from(socket.rooms);
        for (const room of rooms) {
            // room === socket.id is the default room; skip it
            if (room === socket.id) continue;
            await setUserOffline(room);
            console.log(`[DISCONNECT] ${room} went offline`);
        }
        const online = await getOnlineUsers();
        io.emit('users_online', online);
    });
});

// ── Retry Loop for Offline Messages ──
async function retryLoop() {
    if (!redisReady) return;
    try {
        const keys = await redisClient.keys('agrosight:queue:*');
        for (const key of keys) {
            const userId = key.split(':').pop();
            const online = await getOnlineUsers();
            if (online[String(userId)]) {
                const len = await redisClient.lLen(key);
                if (len > 0) {
                    console.log(`[Retry] ${len} messages for now-online user ${userId}`);
                    // Drain will happen when they join/reconnect; here we just notify them
                    io.to(userId).emit('unread_update', { count: len });
                }
            }
        }
    } catch (e) {
        console.warn('[Retry] Loop error:', e.message);
    }
}

if (redisReady) {
    setInterval(retryLoop, MESSAGE_RETRY_MS);
}

// ── Graceful Shutdown ──
function shutdown() {
    console.log('[Shutdown] Closing server...');
    server.close(() => {
        console.log('[Shutdown] Server closed');
        process.exit(0);
    });
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

// ── Listen ──
const listenTarget = SOCKET_PATH || PORT;
const isUnixSocket = typeof listenTarget === 'string' && listenTarget.startsWith('/');

server.listen(listenTarget, () => {
    if (isUnixSocket) {
        const { chmodSync } = require('fs');
        try {
            chmodSync(listenTarget, 0o777);
        } catch (e) {}
        console.log(`AgroSight Chat Server listening on Unix socket ${listenTarget}`);
    } else {
        console.log(`AgroSight Chat Server running on port ${listenTarget}`);
        console.log(`Health check: http://localhost:${listenTarget}/health`);
    }
});
