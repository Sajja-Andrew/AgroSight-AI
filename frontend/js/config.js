/**
 * Smart Crop AI - API Configuration
 * Routes all requests through Nginx reverse proxy
 */

(function() {
    'use strict';

    // API uses same-origin (Nginx at localhost:8080 or domain)
    // Nginx proxies /api/ to backend:5000 and /socket.io/ to chat:5001
    window.API_CONFIG = {
        BASE_URL: window.location.origin + '/api',
        SOCKET_URL: window.location.origin,
        isLocal: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    };

    // Helper to build full API path
    window.apiUrl = function(path) {
        path = path.replace(/^\//, '');
        return window.API_CONFIG.BASE_URL + '/' + path;
    };

    window.socketUrl = function() {
        return window.API_CONFIG.SOCKET_URL;
    };

    console.log('[API_CONFIG] Using API endpoint:', window.API_CONFIG.BASE_URL);
})();
