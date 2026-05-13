/**
 * Smart Crop AI - Security Utilities
 * XSS-safe DOM helpers and input sanitization.
 */

(function() {
    'use strict';

    const ESCAPE_MAP = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '/': '&#x2F;',
        '`': '&#x60;'
    };

    const ESCAPE_REGEX = /[&<>"'`\/]/g;

    /**
     * Escape HTML special characters to prevent XSS.
     */
    window.escapeHtml = function(str) {
        if (str == null) return '';
        if (typeof str !== 'string') str = String(str);
        return str.replace(ESCAPE_REGEX, function(match) {
            return ESCAPE_MAP[match];
        });
    };

    /**
     * Sanitize user input: trim, limit length, remove null bytes.
     */
    window.sanitizeInput = function(value, maxLength) {
        if (value == null) return '';
        if (typeof value !== 'string') value = String(value);
        value = value.trim();
        if (maxLength && value.length > maxLength) {
            value = value.substring(0, maxLength);
        }
        // Remove null bytes and most control characters
        value = value.replace(/\x00/g, '');
        value = value.replace(/[\x00-\x08\x0b-\x0c\x0e-\x1f]/g, '');
        return value;
    };

    /**
     * Safely set innerHTML by validating against dangerous tags.
     * Prefer textContent for plain text.
     */
    window.safeSetHTML = function(element, html) {
        if (!element) return;
        // Check for script tags or event handlers
        const dangerous = /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi;
        const events = /\son\w+\s*=/gi;
        if (dangerous.test(html) || events.test(html)) {
            console.warn('Blocked dangerous HTML content');
            element.textContent = '[Content blocked for security]';
            return;
        }
        element.innerHTML = html;
    };

    /**
     * Build a DOM element safely from a template object.
     * Usage:
     *   const el = buildElement('div', { className: 'card' }, [
     *     buildElement('h3', {}, escapeHtml(title))
     *   ]);
     */
    window.buildElement = function(tag, attrs, children) {
        const el = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function(key) {
                if (key === 'textContent') {
                    el.textContent = attrs[key];
                } else if (key === 'innerHTML') {
                    // Only allow innerHTML if it passes safeSetHTML check
                    safeSetHTML(el, attrs[key]);
                } else if (key === 'onclick' || key.startsWith('on')) {
                    // Disallow inline event handlers for security
                    console.warn('Blocked inline event handler:', key);
                } else {
                    el.setAttribute(key, attrs[key]);
                }
            });
        }
        if (children) {
            children.forEach(function(child) {
                if (typeof child === 'string') {
                    el.appendChild(document.createTextNode(child));
                } else if (child instanceof Node) {
                    el.appendChild(child);
                }
            });
        }
        return el;
    };

    /**
     * Parse JSON safely without throwing.
     */
    window.safeJsonParse = function(str, defaultValue) {
        try {
            return JSON.parse(str);
        } catch (e) {
            return defaultValue !== undefined ? defaultValue : null;
        }
    };

    /**
     * Show a toast notification safely.
     */
    window.showSecureToast = function(message, type) {
        type = type || 'info';
        let toast = document.getElementById('toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'toast';
            toast.style.cssText = 'position:fixed;bottom:20px;right:20px;padding:12px 20px;border-radius:8px;z-index:9999;font-size:14px;transition:opacity 0.3s;';
            document.body.appendChild(toast);
        }
        toast.textContent = message; // Safe - uses textContent
        const colors = {
            success: '#4caf50',
            error: '#f44336',
            warning: '#ff9800',
            info: '#2196f3'
        };
        toast.style.background = colors[type] || colors.info;
        toast.style.color = '#fff';
        toast.style.opacity = '1';
        setTimeout(function() {
            toast.style.opacity = '0';
        }, 3000);
    };
})();
