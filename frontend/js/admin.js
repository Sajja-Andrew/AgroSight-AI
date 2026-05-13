/**
 * Admin Panel JavaScript
 * Handles user management, statistics, audit logs, and admin settings
 */

const API_URL = (window.API_CONFIG && window.API_CONFIG.BASE_URL) ? window.API_CONFIG.BASE_URL : 'http://127.0.0.1:5000/api';

function getAuthHeaders() {
    const token = localStorage.getItem('sc_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return headers;
}

let allUsers = [];
let currentAdmin = null;

// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    checkAdminAuth();
    loadDashboardStats();
    loadAllUsers();
    setupNavigation();
    setupSearch();
    setupPasswordForm();
    setupAdminSettings();
    setupLogout();
    setupMobileToggle();
    checkPasswordResetRequired();
});

async function checkAdminAuth() {
    const adminData = await verifyAdminToken();
    if (!adminData) {
        localStorage.removeItem('sc_token');
        localStorage.removeItem('AgroSightAI_current_user');
        localStorage.removeItem('AgroSightAI_admin');
        window.location.href = 'admin-login.html';
        return;
    }
    currentAdmin = adminData;
    document.getElementById('adminName').textContent = currentAdmin.username || 'Administrator';
}

async function verifyAdminToken() {
    try {
        const res = await fetch(API_URL + '/auth/me', { headers: getAuthHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        if (data.success && data.user && data.user.role === 'admin') {
            return data.user;
        }
        return null;
    } catch (e) {
        return null;
    }
}

function checkPasswordResetRequired() {
    const userData = localStorage.getItem('AgroSightAI_current_user');
    if (!userData) return;
    const user = JSON.parse(userData);
    if (user && user.passwordResetRequired) {
        openPasswordResetModal();
    }
}

// ============================================================
// PASSWORD RESET REQUIRED MODAL (First-time admin)
// ============================================================

function openPasswordResetModal() {
    const modal = document.getElementById('passwordResetModal');
    if (modal) modal.classList.add('active');
}

function closePasswordResetModal() {
    const modal = document.getElementById('passwordResetModal');
    if (modal) modal.classList.remove('active');
}

async function submitPasswordReset() {
    const newPassword = document.getElementById('resetNewPassword').value;
    const confirmPassword = document.getElementById('resetConfirmPassword').value;

    if (!newPassword || newPassword.length < 8) {
        showToast('Password must be at least 8 characters', 'error');
        return;
    }
    if (newPassword !== confirmPassword) {
        showToast('Passwords do not match', 'error');
        return;
    }

    try {
        const res = await fetch(API_URL + '/auth/change-password', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ new_password: newPassword })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Password changed successfully. Please log in again.', 'success');
            closePasswordResetModal();
            // Update local user data
            const userData = JSON.parse(localStorage.getItem('AgroSightAI_current_user') || '{}');
            userData.passwordResetRequired = false;
            localStorage.setItem('AgroSightAI_current_user', JSON.stringify(userData));
            // Force re-login after a delay
            setTimeout(() => {
                localStorage.removeItem('sc_token');
                window.location.href = 'admin-login.html';
            }, 2000);
        } else {
            showToast(data.message || 'Failed to change password', 'error');
        }
    } catch (e) {
        showToast('Server error while changing password', 'error');
    }
}

// ============================================================
// NAVIGATION
// ============================================================

function setupNavigation() {
    const navLinks = document.querySelectorAll('.sidebar-nav a[data-section]');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const section = this.getAttribute('data-section');
            navLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');
            showSection(section);
        });
    });
}

function showSection(sectionId) {
    document.querySelectorAll('.section-container').forEach(s => s.classList.add('hidden'));
    const section = document.getElementById(sectionId + '-section');
    if (section) section.classList.remove('hidden');
    const titles = {
        'dashboard': 'Dashboard Overview',
        'users': 'User Management',
        'farmers': 'Farmers Management',
        'agrovets': 'Agro-Vets Management',
        'activity': 'Activity Log'
    };
    document.getElementById('pageTitle').textContent = titles[sectionId] || 'Dashboard';
}

// ============================================================
// LOAD DATA
// ============================================================

async function loadDashboardStats() {
    try {
        const res = await fetch(API_URL + '/users/stats', { headers: getAuthHeaders() });
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.stats) {
                const s = data.stats;
                document.getElementById('totalFarmers').textContent = s.total_farmers || 0;
                document.getElementById('totalAgrovets').textContent = s.total_agrovets || 0;
                document.getElementById('totalDiagnoses').textContent = s.total_detections || 0;
                document.getElementById('totalMessages').textContent = s.total_messages || 0;
                loadRecentActivityFromBackend();
                return;
            }
        }
    } catch (error) {
        console.warn('Backend stats failed:', error);
    }
}

async function loadRecentActivityFromBackend() {
    const container = document.getElementById('recentActivity');
    try {
        const res = await fetch(API_URL + '/activity?limit=20', { headers: getAuthHeaders() });
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.activities) {
                const acts = data.activities.map(a => ({
                    type: a.type,
                    user: 'User ' + a.user_id,
                    description: a.text,
                    date: a.created_at,
                    icon: getActivityIcon(a.type),
                    color: getActivityColor(a.type)
                }));
                renderActivities(acts, container);
                const logContainer = document.getElementById('activityLog');
                if (logContainer) renderAuditLogs(null, logContainer);
                return;
            }
        }
    } catch (e) {
        console.warn('Backend activity load failed', e);
    }
    if (container) container.innerHTML = '<div class="no-data"><i class="fas fa-history"></i><p>No recent activity</p></div>';
}

async function loadAllUsers() {
    try {
        const res = await fetch(API_URL + '/admin/users?limit=200', { headers: getAuthHeaders() });
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.users) {
                allUsers = data.users;
                populateUsersTable(allUsers);
                populateFarmersTable(allUsers.filter(u => u.role === 'farmer'));
                populateAgrovetsTable(allUsers.filter(u => u.role === 'agrovet'));
                return;
            }
        }
    } catch (error) {
        console.warn('Backend users failed:', error);
    }
    allUsers = [];
    populateUsersTable([]);
    populateFarmersTable([]);
    populateAgrovetsTable([]);
}

// ============================================================
// USER TABLES
// ============================================================

function populateUsersTable(users) {
    const tbody = document.getElementById('usersTable');
    if (!tbody) return;
    tbody.innerHTML = users.map(user => `
        <tr>
            <td>${escapeHTML(user.id)}</td>
            <td>${escapeHTML(user.username)} ${user.passwordResetRequired ? '<span class="badge badge-warning" title="Password reset required">!</span>' : ''}</td>
            <td>${escapeHTML(user.email)}</td>
            <td>${escapeHTML(user.phone || '-')}</td>
            <td><span class="badge badge-${escapeHTML(user.role)}">${escapeHTML(user.role)}</span></td>
            <td>${escapeHTML(user.location || '-')}</td>
            <td>${formatDate(user.createdAt)}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="viewUser(${user.id})" title="View Details">
                    <i class="fas fa-eye"></i>
                </button>
                <button class="btn btn-sm btn-warning" onclick="openResetPasswordModal(${user.id})" title="Reset Password">
                    <i class="fas fa-key"></i>
                </button>
                <button class="btn btn-sm btn-danger" onclick="deleteUser(${user.id})" title="Delete User">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="8" class="no-data">No users found</td></tr>';
}

function populateFarmersTable(farmers) {
    const tbody = document.getElementById('farmersTable');
    if (!tbody) return;
    tbody.innerHTML = farmers.map(user => `
        <tr>
            <td>${escapeHTML(user.id)}</td>
            <td>${escapeHTML(user.username)}</td>
            <td>${escapeHTML(user.email)}</td>
            <td>${escapeHTML(user.phone || '-')}</td>
            <td>${escapeHTML(user.location || '-')}</td>
            <td>${formatDate(user.createdAt)}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="viewUser(${user.id})"><i class="fas fa-eye"></i></button>
                <button class="btn btn-sm btn-warning" onclick="openResetPasswordModal(${user.id})"><i class="fas fa-key"></i></button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="7" class="no-data">No farmers found</td></tr>';
}

function populateAgrovetsTable(agrovets) {
    const tbody = document.getElementById('agrovetsTable');
    if (!tbody) return;
    tbody.innerHTML = agrovets.map(user => `
        <tr>
            <td>${escapeHTML(user.id)}</td>
            <td>${escapeHTML(user.username)}</td>
            <td>${escapeHTML(user.email)}</td>
            <td>${escapeHTML(user.phone || '-')}</td>
            <td>${escapeHTML(user.location || '-')}</td>
            <td>${formatDate(user.createdAt)}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="viewUser(${user.id})"><i class="fas fa-eye"></i></button>
                <button class="btn btn-sm btn-warning" onclick="openResetPasswordModal(${user.id})"><i class="fas fa-key"></i></button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="7" class="no-data">No agro-vets found</td></tr>';
}

// ============================================================
// SEARCH
// ============================================================

function setupSearch() {
    const searchInput = document.getElementById('searchUsers');
    const filterRole = document.getElementById('filterRole');
    if (searchInput) searchInput.addEventListener('input', searchUsers);
    if (filterRole) filterRole.addEventListener('change', searchUsers);
}

function searchUsers() {
    const searchTerm = (document.getElementById('searchUsers')?.value || '').toLowerCase();
    const roleFilter = document.getElementById('filterRole')?.value || '';
    let filtered = allUsers;
    if (roleFilter) filtered = filtered.filter(u => u.role === roleFilter);
    if (searchTerm) {
        filtered = filtered.filter(u =>
            (u.username || '').toLowerCase().includes(searchTerm) ||
            (u.email || '').toLowerCase().includes(searchTerm) ||
            (u.phone || '').includes(searchTerm)
        );
    }
    populateUsersTable(filtered);
}

// ============================================================
// PASSWORD RESET (Admin action)
// ============================================================

function openResetPasswordModal(userId) {
    const user = allUsers.find(u => u.id === userId);
    if (!user) return;
    document.getElementById('resetUserId').value = userId;
    document.getElementById('resetUserName').value = user.username;
    document.getElementById('resetUserEmail').value = user.email;
    document.getElementById('generatedPassword').value = '';
    document.getElementById('directNewPassword').value = '';
    document.getElementById('resetPasswordModal').classList.add('active');
}

function closeResetPasswordModal() {
    document.getElementById('resetPasswordModal').classList.remove('active');
}

async function confirmResetPassword() {
    const userId = parseInt(document.getElementById('resetUserId').value);
    if (!userId) return;
    if (!confirm('Reset password for this user? They will be required to change it on next login.')) return;

    try {
        const res = await fetch(API_URL + '/admin/users/' + userId + '/reset-password', {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById('generatedPassword').value = data.temporaryPassword;
            showToast('Password reset. Temporary password displayed below.', 'success');
            loadAllUsers();
        } else {
            showToast(data.message || 'Failed to reset password', 'error');
        }
    } catch (e) {
        showToast('Server error while resetting password', 'error');
    }
}

async function directChangePassword() {
    const userId = parseInt(document.getElementById('resetUserId').value);
    const newPassword = document.getElementById('directNewPassword').value.trim();
    if (!userId) return;
    if (!newPassword || newPassword.length < 8) {
        showToast('Password must be at least 8 characters', 'error');
        return;
    }

    try {
        const res = await fetch(API_URL + '/admin/users/' + userId + '/change-password', {
            method: 'PUT',
            headers: getAuthHeaders(),
            body: JSON.stringify({ new_password: newPassword })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Password changed successfully. The user can now log in with the new password.', 'success');
            closeResetPasswordModal();
            loadAllUsers();
        } else {
            showToast(data.message || 'Failed to change password', 'error');
        }
    } catch (e) {
        showToast('Server error while changing password', 'error');
    }
}

// ============================================================
// USER DETAILS
// ============================================================

function viewUser(userId) {
    const user = allUsers.find(u => u.id === userId);
    if (!user) return;
    const container = document.getElementById('userDetails');
    if (!container) return;
    container.innerHTML = '';
    const fields = [
        { label: 'ID', value: user.id },
        { label: 'Username', value: user.username },
        { label: 'Email', value: user.email },
        { label: 'Phone', value: user.phone || '-' },
        { label: 'Role', value: user.role },
        { label: 'Location', value: user.location || '-' },
        { label: 'Joined', value: formatDate(user.createdAt) },
        { label: 'Password Reset Required', value: user.passwordResetRequired ? 'Yes' : 'No' },
        { label: 'Last Password Change', value: formatDate(user.lastPasswordChange) },
    ];
    fields.forEach(f => {
        const group = document.createElement('div');
        group.className = 'form-group';
        const label = document.createElement('label');
        label.textContent = f.label;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = f.value;
        input.readOnly = true;
        group.appendChild(label);
        group.appendChild(input);
        container.appendChild(group);
    });
    document.getElementById('userModal').classList.add('active');
}

function closeUserModal() {
    document.getElementById('userModal').classList.remove('active');
}

// ============================================================
// DELETE USER
// ============================================================

async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) return;
    const user = allUsers.find(u => u.id === userId);
    if (user && user.role === 'admin') {
        showToast('Admin accounts cannot be deleted from the dashboard.', 'error');
        return;
    }
    try {
        const res = await fetch(API_URL + '/admin/users/' + userId, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.success) {
            allUsers = allUsers.filter(u => u.id !== userId);
            populateUsersTable(allUsers);
            populateFarmersTable(allUsers.filter(u => u.role === 'farmer'));
            populateAgrovetsTable(allUsers.filter(u => u.role === 'agrovet'));
            loadDashboardStats();
            showToast('User deleted successfully', 'success');
        } else {
            showToast(data.message || 'Failed to delete user', 'error');
        }
    } catch (e) {
        showToast('Server error while deleting user', 'error');
    }
}

// ============================================================
// AUDIT LOGS
// ============================================================

async function loadAuditLogs() {
    const container = document.getElementById('activityLog');
    if (!container) return;
    try {
        const res = await fetch(API_URL + '/admin/audit-logs?limit=100', { headers: getAuthHeaders() });
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.logs) {
                renderAuditLogs(data.logs, container);
                return;
            }
        }
    } catch (e) {
        console.warn('Audit logs load failed', e);
    }
    renderAuditLogs([], container);
}

function renderAuditLogs(logs, container) {
    if (!container) return;
    if (!logs || !logs.length) {
        container.innerHTML = '<div class="no-data"><i class="fas fa-history"></i><p>No audit logs recorded yet</p></div>';
        return;
    }
    container.innerHTML = logs.map(log => `
        <div class="audit-item" style="padding:12px;border-bottom:1px solid var(--border-color);display:flex;gap:12px;align-items:flex-start;">
            <div class="audit-icon" style="background:${getAuditColor(log.action)};width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:white;font-size:0.85rem;flex-shrink:0;">
                <i class="fas ${getAuditIcon(log.action)}"></i>
            </div>
            <div style="flex:1;">
                <div style="font-weight:600;font-size:0.9rem;">${escapeHTML(log.adminName)} - ${escapeHTML(log.action)}</div>
                <div style="font-size:0.85rem;color:var(--text-secondary);margin-top:2px;">${escapeHTML(log.details || '')}</div>
                <div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px;">${formatDate(log.createdAt)} | IP: ${escapeHTML(log.ipAddress || 'N/A')}</div>
            </div>
        </div>
    `).join('');
}

function getAuditIcon(action) {
    const icons = {
        'RESET_PASSWORD': 'fa-key',
        'UPDATE_USER': 'fa-edit',
        'DELETE_USER': 'fa-trash',
        'CREATE_USER': 'fa-user-plus'
    };
    return icons[action] || 'fa-circle';
}

function getAuditColor(action) {
    const colors = {
        'RESET_PASSWORD': '#ff9800',
        'UPDATE_USER': '#1d9bf0',
        'DELETE_USER': '#f44336',
        'CREATE_USER': '#4caf50'
    };
    return colors[action] || '#9e9e9e';
}

// ============================================================
// ADMIN SETTINGS
// ============================================================

function setupAdminSettings() {
    const avatar = document.getElementById('adminAvatar');
    if (avatar) avatar.addEventListener('click', openAdminSettings);
    const form = document.getElementById('adminSettingsForm');
    if (form) form.addEventListener('submit', function(e) { e.preventDefault(); saveAdminSettings(); });
}

function openAdminSettings() {
    document.getElementById('newAdminName').value = currentAdmin?.username || '';
    document.getElementById('newAdminPassword').value = '';
    document.getElementById('confirmAdminPassword').value = '';
    document.getElementById('adminSettingsModal').classList.add('active');
}

function closeAdminSettings() {
    document.getElementById('adminSettingsModal').classList.remove('active');
}

async function saveAdminSettings() {
    const newName = document.getElementById('newAdminName').value.trim();
    const newPassword = document.getElementById('newAdminPassword').value;
    const confirmPassword = document.getElementById('confirmAdminPassword').value;
    if (!newName) { showToast('Admin name is required', 'error'); return; }
    if (newPassword) {
        if (newPassword.length < 8) { showToast('Password must be at least 8 characters', 'error'); return; }
        if (newPassword !== confirmPassword) { showToast('Passwords do not match', 'error'); return; }
    }
    try {
        const body = {};
        if (newName !== currentAdmin.username) body.username = newName;
        if (newPassword) body.new_password = newPassword;
        const res = await fetch(API_URL + '/auth/change-password', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            showToast('Settings updated successfully', 'success');
            closeAdminSettings();
        } else {
            showToast(data.message || 'Failed to update settings', 'error');
        }
    } catch (e) {
        showToast('Server error', 'error');
    }
}

// ============================================================
// PASSWORD FORM (legacy modal)
// ============================================================

function setupPasswordForm() {
    const form = document.getElementById('passwordForm');
    if (!form) return;
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        showToast('Use the Reset Password button in the user table instead.', 'warning');
        closePasswordModal();
    });
}

function openPasswordModal(userId) {
    openResetPasswordModal(userId);
}

function closePasswordModal() {
    closeResetPasswordModal();
}

// ============================================================
// EXPORT
// ============================================================

function exportUsers() {
    let csv = 'ID,Username,Email,Phone,Role,Location,Joined,PasswordResetRequired\n';
    allUsers.forEach(user => {
        csv += `${user.id},"${user.username}","${user.email}","${user.phone || '-'}","${user.role}","${user.location || '-'}","${user.createdAt}","${user.passwordResetRequired ? 'Yes' : 'No'}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `AgroSight AI_users_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Users exported successfully', 'success');
}

// ============================================================
// MOBILE & UTILITIES
// ============================================================

function setupMobileToggle() {
    const btn = document.getElementById('toggleSidebarBtn');
    if (btn) btn.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('active'));
}

function setupLogout() {
    const btn = document.getElementById('logoutBtn');
    if (btn) btn.addEventListener('click', function(e) {
        e.preventDefault();
        if (confirm('Are you sure you want to logout?')) {
            localStorage.removeItem('AgroSightAI_admin');
            localStorage.removeItem('sc_token');
            localStorage.removeItem('AgroSightAI_current_user');
            window.location.href = 'admin-login.html';
        }
    });
}

// Close modals on outside click
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', function(e) {
        if (e.target === this) this.classList.remove('active');
    });
});

// ============================================================
// UTILITIES
// ============================================================

function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function getActivityIcon(type) {
    const icons = { 'signup': 'fa-user-plus', 'login': 'fa-sign-in-alt', 'detection': 'fa-camera', 'message': 'fa-comment', 'profile': 'fa-user-edit' };
    return icons[type] || 'fa-info-circle';
}

function getActivityColor(type) {
    const colors = { 'signup': '#00ba7c', 'login': '#1d9bf0', 'detection': '#ffd400', 'message': '#f4212e', 'profile': '#1d9bf0' };
    return colors[type] || '#8899a6';
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check' : type === 'error' ? 'times' : 'info'}-circle"></i> ${message}`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
