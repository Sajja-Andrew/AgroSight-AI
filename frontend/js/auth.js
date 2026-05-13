document.addEventListener('DOMContentLoaded', function() {
    // Password visibility toggle
    const togglePasswordBtn = document.getElementById('togglePassword');
    const passwordInput = document.getElementById('password');

    if (togglePasswordBtn && passwordInput) {
        togglePasswordBtn.addEventListener('click', function() {
            const icon = this.querySelector('i');
            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                passwordInput.type = 'password';
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });
    }

    // Password toggle for any password field
    const passwordToggles = document.querySelectorAll('.password-toggle');
    passwordToggles.forEach(toggle => {
        toggle.addEventListener('click', function() {
            const input = this.previousElementSibling;
            if (input.type === 'password') {
                input.type = 'text';
                this.classList.remove('fa-eye');
                this.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                this.classList.remove('fa-eye-slash');
                this.classList.add('fa-eye');
            }
        });
    });

    // Add password toggle icons if not exists
    const passwordInputs = document.querySelectorAll('input[type="password"]');
    passwordInputs.forEach(input => {
        if (!input.nextElementSibling || !input.nextElementSibling.classList.contains('password-toggle')) {
            const toggle = document.createElement('i');
            toggle.className = 'fas fa-eye password-toggle';
            input.parentNode.insertBefore(toggle, input.nextSibling);

            toggle.addEventListener('click', function() {
                if (input.type === 'password') {
                    input.type = 'text';
                    this.classList.remove('fa-eye');
                    this.classList.add('fa-eye-slash');
                } else {
                    input.type = 'password';
                    this.classList.remove('fa-eye-slash');
                    this.classList.add('fa-eye');
                }
            });
        }
    });

    // â”€â”€ API CONFIG uses dynamic URL from config.js â”€â”€
    const API_BASE_URL = window.API_CONFIG ? window.API_CONFIG.BASE_URL : 'http://127.0.0.1:5000/api';

    function getAuthHeaders() {
        const token = localStorage.getItem('sc_token');
        return {
            'Content-Type': 'application/json',
            'Authorization': token ? 'Bearer ' + token : ''
        };
    }

    // Geolocation helper
    function getGeolocation() {
        return new Promise((resolve) => {
            if (!navigator.geolocation) {
                resolve({ latitude: null, longitude: null });
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
                () => resolve({ latitude: null, longitude: null }),
                { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
            );
        });
    }

    // Sign Up Form Handler
    const signupForm = document.getElementById('signupForm');
    if (signupForm) {
        signupForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const username = sanitizeInput(document.getElementById('username').value, 80);
            const email = sanitizeInput(document.getElementById('email').value, 120);
            const phone = sanitizeInput(document.getElementById('phone').value, 20);
            const role = document.getElementById('role').value;
            const location = sanitizeInput(document.getElementById('location').value, 200);
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;

            if (password !== confirmPassword) {
                showNotification('Passwords do not match!', 'error');
                return;
            }
            if (password.length < 8) {
                showNotification('Password must be at least 8 characters long!', 'error');
                return;
            }

            showNotification('Detecting location...', 'info');
            const geo = await getGeolocation();

            try {
                const payload = { username, email, password, phone, role, location };
                if (geo.latitude !== null && geo.longitude !== null) {
                    payload.latitude = geo.latitude;
                    payload.longitude = geo.longitude;
                }
                const res = await fetch(API_BASE_URL + '/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (data.success) {
                    localStorage.setItem('sc_token', data.token);
                    localStorage.setItem('AgroSightAI_current_user', JSON.stringify(data.user));
                    showNotification('Registration successful! Redirecting to dashboard...', 'success');
                    setTimeout(() => {
                        window.location.href = role === 'farmer' ? 'farmer-dashboard.html' : 'agrovet-dashboard.html';
                    }, 1500);
                } else {
                    showNotification(data.message || 'Registration failed.', 'error');
                }
            } catch (err) {
                console.error('Register error:', err);
                if (err.name === 'TypeError' || err.message.includes('fetch') || err.message.includes('NetworkError')) {
                    showNotification('Cannot connect to server. Make sure the backend is running on http://127.0.0.1:5000', 'error');
                } else {
                    showNotification('Server error. Please try again.', 'error');
                }
            }
        });
    }

    // Sign In Form Handler
    const signinForm = document.getElementById('signinForm');
    if (signinForm) {
        // Forgot Password Modal
        const forgotPasswordLink = document.getElementById('forgotPasswordLink');
        const whatsappModal = document.getElementById('whatsappSupportModal');
        const closeModal = document.getElementById('closeModal');

        if (forgotPasswordLink && whatsappModal) {
            forgotPasswordLink.addEventListener('click', function(e) {
                e.preventDefault();
                whatsappModal.style.display = 'flex';
            });
        }
        if (closeModal && whatsappModal) {
            closeModal.addEventListener('click', function() {
                whatsappModal.style.display = 'none';
            });
            whatsappModal.addEventListener('click', function(e) {
                if (e.target === whatsappModal) {
                    whatsappModal.style.display = 'none';
                }
            });
        }

        signinForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            // identifier can be email, phone, or username
            const identifier = sanitizeInput(document.getElementById('loginIdentifier').value, 120);
            const password = document.getElementById('password').value;
            const rememberMe = document.getElementById('rememberMe') ? document.getElementById('rememberMe').checked : false;

            const signinBtn = document.getElementById('signinBtn');
            const btnText = signinBtn ? signinBtn.querySelector('.btn-text') : null;
            const btnLoader = signinBtn ? signinBtn.querySelector('.btn-loader') : null;

            if (signinBtn && btnText && btnLoader) {
                btnText.style.display = 'none';
                btnLoader.style.display = 'inline-flex';
                signinBtn.disabled = true;
            }

            try {
                // New backend accepts identifier + password only
                const res = await fetch(API_BASE_URL + '/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ identifier, password })
                });
                const data = await res.json();

                if (data.success) {
                    localStorage.setItem('sc_token', data.token);
                    localStorage.setItem('AgroSightAI_current_user', JSON.stringify(data.user));
                    if (rememberMe) {
                        localStorage.setItem('AgroSightAI_remember_me', 'true');
                    }
                    showNotification('Login successful! Redirecting...', 'success');
                    setTimeout(() => {
                        window.location.href = data.user.role === 'farmer' ? 'farmer-dashboard.html' : 'agrovet-dashboard.html';
                    }, 1500);
                } else {
                    if (signinBtn && btnText && btnLoader) {
                        btnText.style.display = 'inline';
                        btnLoader.style.display = 'none';
                        signinBtn.disabled = false;
                    }
                    showNotification(data.message || 'Invalid credentials!', 'error');
                }
            } catch (err) {
                console.error('Login error:', err);
                if (signinBtn && btnText && btnLoader) {
                    btnText.style.display = 'inline';
                    btnLoader.style.display = 'none';
                    signinBtn.disabled = false;
                }
                if (err.name === 'TypeError' || err.message.includes('fetch') || err.message.includes('NetworkError')) {
                    showNotification('Cannot connect to server. Make sure the backend is running on http://127.0.0.1:5000', 'error');
                } else {
                    showNotification('Server error. Please try again.', 'error');
                }
            }
        });
    }

    // Check if user is already logged in (avoid redirect loop on auth pages)
    const currentUser = safeJsonParse(localStorage.getItem('AgroSightAI_current_user'));
    const currentPage = window.location.pathname;
    const isAuthPage = currentPage.includes('signin.html') || currentPage.includes('signup.html') || currentPage === '/' || currentPage.includes('index.html');

    if (currentUser && isAuthPage) {
        setTimeout(() => {
            window.location.href = currentUser.role === 'farmer' ? 'farmer-dashboard.html' : 'agrovet-dashboard.html';
        }, 1000);
    }

    // Auto-fill remember me
    if (localStorage.getItem('AgroSightAI_remember_me') === 'true' && currentUser) {
        const rememberMe = document.getElementById('rememberMe');
        if (rememberMe) rememberMe.checked = true;
    }
});

// Show notification (safe, no XSS)
function showNotification(message, type) {
    const notification = document.createElement('div');
    const colors = { info: '#1976d2', success: '#2e7d32', error: '#f44336' };
    notification.style.cssText = `
        position: fixed; top: 20px; right: 20px; padding: 14px 20px; border-radius: 10px;
        display: flex; align-items: center; gap: 10px; z-index: 3000;
        font-family: 'Poppins', sans-serif; font-size: 0.9rem; font-weight: 500;
        color: white; background: ${colors[type] || colors.info};
        box-shadow: 0 4px 12px rgba(0,0,0,0.2); animation: slideIn 0.3s ease;
    `;

    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-exclamation-circle';

    const iconEl = document.createElement('i');
    iconEl.className = 'fas ' + icon;
    const span = document.createElement('span');
    span.textContent = message;

    notification.appendChild(iconEl);
    notification.appendChild(span);

    if (!document.getElementById('auth-notif-style')) {
        const style = document.createElement('style');
        style.id = 'auth-notif-style';
        style.textContent = `
            @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
            @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(100%); opacity: 0; } }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(notification);
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ── Password Reset ──
let resetTokenData = null;

async function requestPasswordReset() {
    const email = document.getElementById('resetEmail')?.value?.trim();
    const errorEl = document.getElementById('resetError');
    if (!email) {
        if (errorEl) { errorEl.textContent = 'Please enter your email or username.'; errorEl.style.display = 'block'; }
        return;
    }
    try {
        const API_BASE_URL = window.API_CONFIG ? window.API_CONFIG.BASE_URL : 'http://127.0.0.1:5000/api';
        const res = await fetch(API_BASE_URL + '/auth/forgot-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (data.success && data.reset_token) {
            resetTokenData = { token: data.reset_token, user_id: data.user_id };
            document.getElementById('resetStep1').style.display = 'none';
            document.getElementById('resetStep2').style.display = 'block';
            const info = document.getElementById('resetTokenInfo');
            if (info) info.textContent = 'Reset token generated. Enter your new password below.';
            showNotification('Reset token generated! Enter your new password.', 'success');
        } else {
            if (errorEl) { errorEl.textContent = data.message || 'No account found with that email.'; errorEl.style.display = 'block'; }
        }
    } catch (e) {
        if (errorEl) { errorEl.textContent = 'Server error. Please try again.'; errorEl.style.display = 'block'; }
    }
}

async function resetPasswordWithToken() {
    const newPassword = document.getElementById('newResetPassword')?.value;
    const confirmPassword = document.getElementById('confirmResetPassword')?.value;
    const errorEl = document.getElementById('resetStep2Error');

    if (!newPassword || newPassword.length < 8) {
        if (errorEl) { errorEl.textContent = 'Password must be at least 8 characters.'; errorEl.style.display = 'block'; }
        return;
    }
    if (newPassword !== confirmPassword) {
        if (errorEl) { errorEl.textContent = 'Passwords do not match.'; errorEl.style.display = 'block'; }
        return;
    }
    if (!resetTokenData?.token) {
        if (errorEl) { errorEl.textContent = 'No reset token available. Please try again.'; errorEl.style.display = 'block'; }
        return;
    }

    try {
        const API_BASE_URL = window.API_CONFIG ? window.API_CONFIG.BASE_URL : 'http://127.0.0.1:5000/api';
        const res = await fetch(API_BASE_URL + '/auth/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: resetTokenData.token, new_password: newPassword })
        });
        const data = await res.json();
        if (data.success) {
            showNotification('Password reset successfully! Please sign in.', 'success');
            closeResetModal();
            // Clear the form
            document.getElementById('resetEmail').value = '';
            document.getElementById('newResetPassword').value = '';
            document.getElementById('confirmResetPassword').value = '';
            resetTokenData = null;
            // Show step 1 again for next time
            document.getElementById('resetStep1').style.display = 'block';
            document.getElementById('resetStep2').style.display = 'none';
        } else {
            if (errorEl) { errorEl.textContent = data.message || 'Failed to reset password.'; errorEl.style.display = 'block'; }
        }
    } catch (e) {
        if (errorEl) { errorEl.textContent = 'Server error. Please try again.'; errorEl.style.display = 'block'; }
    }
}

function closeResetModal() {
    const modal = document.getElementById('whatsappSupportModal');
    if (modal) modal.style.display = 'none';
    // Reset steps
    const step1 = document.getElementById('resetStep1');
    const step2 = document.getElementById('resetStep2');
    if (step1) step1.style.display = 'block';
    if (step2) step2.style.display = 'none';
    resetTokenData = null;
}
