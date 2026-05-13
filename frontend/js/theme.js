/**
 * Theme helper - syncs with dashboard theme logic
 * Auth pages (signin/signup) are locked to dark mode.
 * Dashboard pages are handled by their own JS (farmer.js/agrovet.js).
 * This only adds toggle functionality on the index page.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Auth pages: force dark mode, no toggle
    const isAuthPage = !!document.querySelector('.auth-card, .auth-section, .auth-container');
    if (isAuthPage) {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('sc_theme', 'dark');
        return;
    }

    // Dashboard pages: farmer.js/agrovet.js handle theme init, skip here
    if (document.querySelector('.dashboard-section, .main-content')) {
        return;
    }

    // Index page: apply saved theme
    const savedTheme = localStorage.getItem('sc_theme') || localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);

    // Add toggle functionality
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        updateToggleIcon(savedTheme);
        themeToggle.addEventListener('click', function() {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('sc_theme', next);
            localStorage.setItem('theme', next);
            updateToggleIcon(next);
            showThemeNotification(next);
        });
    }
});

function updateToggleIcon(theme) {
    const icon = document.querySelector('#themeToggle i, #themeIcon, #mobileThemeIcon');
    if (icon) {
        icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
}

function showThemeNotification(theme) {
    const notification = document.createElement('div');
    notification.style.cssText = 'position:fixed;top:20px;right:20px;padding:1rem 1.5rem;border-radius:8px;display:flex;align-items:center;gap:0.5rem;z-index:3000;animation:slideIn 0.3s ease;box-shadow:0 4px 12px rgba(0,0,0,0.15);font-family:Poppins,sans-serif;background:#2e7d32;color:white;';

    const icon = theme === 'dark' ? 'fa-moon' : 'fa-sun';
    const label = theme === 'dark' ? 'Dark mode' : 'Light mode';
    notification.innerHTML = '<i class="fas ' + icon + '"></i><span>' + label + ' activated!</span>';

    if (!document.querySelector('#theme-notif-style')) {
        const style = document.createElement('style');
        style.id = 'theme-notif-style';
        style.textContent = '@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}@keyframes slideOut{from{transform:translateX(0);opacity:1}to{transform:translateX(100%);opacity:0}}';
        document.head.appendChild(style);
    }

    document.body.appendChild(notification);
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 2000);
}