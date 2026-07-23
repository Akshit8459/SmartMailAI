// SmartMail AI — Application Logic with Google OAuth

const API_BASE = '/api/v1';

let state = {
    currentFolder: 'INBOX',
    emails: [],
    selectedEmailId: null,
    selectedIndex: -1,
    selectedEmailIds: new Set(),
    user: null,
    token: null,
    limit: 50,
    offset: 0,
    totalCount: 0,
    syncRetryCount: 0
};

// ─────────────────────────────────────────
// Theme Management (Gmail Light / Dark Theme)
// ─────────────────────────────────────────
function initTheme() {
    const savedTheme = localStorage.getItem('sm_theme') || 'dark';
    applyTheme(savedTheme);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('sm_theme', theme);
    const sunIcon = document.getElementById('themeSunIcon');
    const moonIcon = document.getElementById('themeMoonIcon');
    if (theme === 'light') {
        if (sunIcon) sunIcon.classList.remove('hidden');
        if (moonIcon) moonIcon.classList.add('hidden');
    } else {
        if (sunIcon) sunIcon.classList.add('hidden');
        if (moonIcon) moonIcon.classList.remove('hidden');
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
}

document.addEventListener('DOMContentLoaded', initTheme);

// ─────────────────────────────────────────
// Boot
// ─────────────────────────────────────────
function checkAuthToken() {
    const hash = window.location.hash;
    if (hash.includes('token=')) {
        const parts = hash.split('token=');
        if (parts.length > 1) {
            const token = parts[1].split('&')[0];
            if (token) {
                localStorage.setItem('sm_token', token);
                state.token = token;
                history.replaceState(null, '', window.location.pathname);
                initApp();
                return true;
            }
        }
    }
    return false;
}

window.addEventListener('hashchange', checkAuthToken);

document.addEventListener('DOMContentLoaded', () => {
    // Check for auth_error in URL query parameters
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('auth_error')) {
        const err = urlParams.get('auth_error');
        showLoginError(`Google OAuth Notice: ${err}`);
        history.replaceState(null, '', window.location.pathname);
    }

    if (checkAuthToken()) {
        return;
    }

    const token = localStorage.getItem('sm_token');
    if (token) {
        state.token = token;
        initApp();
    } else {
        showLoginScreen();
    }
});

// ─────────────────────────────────────────
// Auth
// ─────────────────────────────────────────
function showLoginScreen() {
    document.getElementById('loginScreen').classList.remove('hidden');
    document.getElementById('appShell').classList.add('hidden');
}

function hideLoginScreen() {
    document.getElementById('loginScreen').classList.add('hidden');
    document.getElementById('appShell').classList.remove('hidden');
}

async function handleGoogleLogin() {
    const btn = document.getElementById('googleLoginBtn');
    btn.disabled = true;
    btn.innerHTML = `<svg class="animate-spin w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> Connecting to Google...`;
    
    // Safety timer if browser blocks navigation or network is slow
    const resetTimer = setTimeout(() => {
        if (btn && !state.token) {
            btn.disabled = false;
            btn.innerHTML = `<img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" class="w-5 h-5 mr-3"> Continue with Google`;
            showLoginError('Google sign-in taking longer than expected. Click "Instant Demo Guest Access" below for immediate login.');
        }
    }, 6000);

    try {
        const res = await fetch(`${API_BASE}/auth/login-url`);
        const data = await res.json();
        if (!data.configured) {
            clearTimeout(resetTimer);
            btn.disabled = false;
            btn.innerHTML = `<img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" class="w-5 h-5 mr-3"> Continue with Google`;
            showLoginError('GOOGLE_CLIENT_ID is not configured in .env. Logging in via Demo Mode...');
            setTimeout(handleDemoLogin, 800);
            return;
        }
        window.location.href = data.url;
    } catch (e) {
        clearTimeout(resetTimer);
        btn.disabled = false;
        btn.innerHTML = `<img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" class="w-5 h-5 mr-3"> Continue with Google`;
        showLoginError('Could not reach server. Is it running?');
    }
}

async function handleDemoLogin() {
    const btn = document.getElementById('demoLoginBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<svg class="animate-spin w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> Logging in...`;
    }
    try {
        const res = await fetch(`${API_BASE}/auth/demo-login`, { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        localStorage.setItem('sm_token', data.access_token);
        state.token = data.access_token;
        state.user = data.user;
        await initApp();
    } catch (e) {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i data-lucide="zap" class="w-4 h-4 text-amber-400"></i> Instant Demo Guest Access`;
            if (window.lucide) lucide.createIcons();
        }
        showLoginError(`Demo login failed: ${e.message}`);
    }
}

function showLoginError(msg) {
    const el = document.getElementById('loginError');
    el.textContent = msg;
    el.classList.remove('hidden');
}

function logout() {
    localStorage.removeItem('sm_token');
    state.token = null;
    state.user = null;
    showLoginScreen();
}

// ─────────────────────────────────────────
// Authenticated fetch helper
// ─────────────────────────────────────────
async function apiFetch(path, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
        'Authorization': `Bearer ${state.token}`,
    };
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401) {
        logout();
        throw new Error('Session expired');
    }
    return res;
}

// ─────────────────────────────────────────
// App Init
// ─────────────────────────────────────────
async function initApp() {
    try {
        const res = await apiFetch('/auth/me');
        if (res.ok) {
            state.user = await res.json();
            localStorage.setItem('sm_user', JSON.stringify(state.user));
        }
    } catch (_) {
        const storedUser = localStorage.getItem('sm_user');
        if (storedUser) state.user = JSON.parse(storedUser);
    }

    hideLoginScreen();
    setupEventListeners();
    setupKeyboardShortcuts();
    updateUserProfile();
    await loadEmails('INBOX');
    startInboundPolling();
}

let inboundPollInterval = null;

async function pollGmailChanges() {
    try {
        const res = await apiFetch('/emails/poll-changes');
        if (res.ok) {
            const data = await res.json();
            const changes = data.changes || {};
            if (changes.labels_updated > 0 || changes.new_messages > 0) {
                console.log('[InboundSync] Detected changes from Gmail:', changes);
                await loadEmails(state.currentFolder, state.offset);
            }
        }
    } catch (err) {
        console.warn('[InboundSync] Poll error:', err);
    }
}

function startInboundPolling() {
    if (inboundPollInterval) clearInterval(inboundPollInterval);
    // Poll every 25 seconds for live inbound changes from Gmail
    inboundPollInterval = setInterval(pollGmailChanges, 25000);
}

function updateUserProfile() {
    const user = state.user;
    if (!user) return;
    const avatarEl = document.getElementById('userAvatar');
    const fallbackEl = document.getElementById('userAvatarFallback');
    const nameEl = document.getElementById('userName');
    const emailEl = document.getElementById('userEmail');

    if (nameEl) nameEl.textContent = user.name || 'User';
    if (emailEl) emailEl.textContent = user.email || '';

    // Set initial fallback badge (e.g. 'A' for Akshit)
    const displayName = user.name || user.email || 'User';
    const initial = displayName.charAt(0).toUpperCase();
    if (fallbackEl) fallbackEl.textContent = initial;

    if (avatarEl && user.picture) {
        avatarEl.referrerPolicy = 'no-referrer';
        avatarEl.src = user.picture;
        avatarEl.onload = () => {
            avatarEl.classList.remove('hidden');
            if (fallbackEl) fallbackEl.classList.add('hidden');
        };
        avatarEl.onerror = () => {
            // Google image failed to load / 404 / referrer blocked → show clean initial badge!
            avatarEl.classList.add('hidden');
            if (fallbackEl) fallbackEl.classList.remove('hidden');
        };
    } else {
        if (avatarEl) avatarEl.classList.add('hidden');
        if (fallbackEl) fallbackEl.classList.remove('hidden');
    }
}

// ─────────────────────────────────────────
// Event Listeners
// ─────────────────────────────────────────
function setupEventListeners() {
    document.querySelectorAll('.nav-item, [data-folder]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            const folder = el.getAttribute('data-folder');
            if (folder) {
                document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
                el.classList.add('active');
                state.selectedEmailIds.clear();
                updateBulkActionsBar();
                loadEmails(folder, 0);
            }
        });
    });

    const searchInput = document.getElementById('searchInput');
    let searchTimeout;
    let suggestionTimeout;
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            clearTimeout(suggestionTimeout);
            const query = e.target.value.trim();
            if (query) {
                searchTimeout = setTimeout(() => searchEmails(query), 300);
                // Fetch AI suggestions after a slightly longer delay
                if (query.length >= 2) {
                    suggestionTimeout = setTimeout(() => fetchSearchSuggestions(query), 500);
                } else {
                    hideSearchSuggestions();
                }
            } else {
                loadEmails(state.currentFolder, 0);
                hideSearchSuggestions();
            }
        });
        // Close suggestions on blur (delay allows click/mousedown on suggestion to execute first)
        searchInput.addEventListener('blur', () => {
            setTimeout(hideSearchSuggestions, 300);
        });
        searchInput.addEventListener('focus', () => {
            const query = searchInput.value.trim();
            if (query.length >= 2) fetchSearchSuggestions(query);
        });
    }

    const selectAllCheckbox = document.getElementById('selectAll');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            state.emails.forEach(email => {
                if (isChecked) state.selectedEmailIds.add(email.id);
                else state.selectedEmailIds.delete(email.id);
            });
            document.querySelectorAll('.email-row input[type="checkbox"]').forEach(cb => cb.checked = isChecked);
            updateBulkActionsBar();
        });
    }

    document.getElementById('refreshInbox')?.addEventListener('click', async () => {
        await pollGmailChanges();
        await loadEmails(state.currentFolder, state.offset);
    });
    document.getElementById('openComposeBtn')?.addEventListener('click', openCompose);
    document.getElementById('closeCompose')?.addEventListener('click', closeCompose);
    document.getElementById('closeComposeBtn')?.addEventListener('click', closeCompose);
    document.getElementById('composeForm')?.addEventListener('submit', handleComposeSubmit);
    document.getElementById('generateAIDraftBtn')?.addEventListener('click', handleGenerateAIDraft);
    document.getElementById('toggleAIChat')?.addEventListener('click', toggleAIChat);
    document.getElementById('closeAIChat')?.addEventListener('click', toggleAIChat);
    document.getElementById('closeAIChatBtn')?.addEventListener('click', toggleAIChat);
    document.getElementById('aiChatForm')?.addEventListener('submit', handleAIChatSubmit);
    document.getElementById('backToListBtn')?.addEventListener('click', showEmailList);
    document.getElementById('aiSummarizeThreadBtn')?.addEventListener('click', handleSummarizeCurrentEmail);
    document.getElementById('logoutBtn')?.addEventListener('click', logout);

    // Smart Inbox nav button
    document.getElementById('smartInboxNavBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('smartInboxNavBtn').classList.add('active');
        state.selectedEmailIds.clear();
        updateBulkActionsBar();
        loadSmartInbox();
    });

    // RAG Dashboard toggle
    document.getElementById('toggleRagDashboard')?.addEventListener('click', () => {
        const content = document.getElementById('ragDashboardContent');
        const chevron = document.getElementById('dashboardChevron');
        const isOpen = content.style.display !== 'none';
        content.style.display = isOpen ? 'none' : 'block';
        if (chevron) chevron.style.transform = isOpen ? '' : 'rotate(180deg)';
        if (!isOpen) refreshRagDashboard();
    });

    // ── Search suggestion dropdown — persistent delegation ──
    const suggestionDropdown = document.getElementById('searchSuggestions');
    if (suggestionDropdown) {
        const handleSuggestionSelect = (e) => {
            const btn = e.target.closest('.suggestion-item');
            if (btn) {
                e.preventDefault();
                const idx = parseInt(btn.getAttribute('data-idx'), 10);
                if (!isNaN(idx) && state.currentSuggestions && state.currentSuggestions[idx]) {
                    applySuggestion(state.currentSuggestions[idx]);
                }
            }
        };

        // mousedown prevents input blur before selection
        suggestionDropdown.addEventListener('mousedown', handleSuggestionSelect);
        suggestionDropdown.addEventListener('click', handleSuggestionSelect);
    }

    // Command palette close on click outside or input filter
    const commandInput = document.getElementById('commandPaletteInput');
    if (commandInput) {
        commandInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const val = commandInput.value.trim();
                if (val) {
                    closeCommandPalette();
                    openAIChatPanel();
                    const chatInput = document.getElementById('aiChatInput') || document.getElementById('aiQueryInput');
                    if (chatInput) {
                        chatInput.value = val;
                        handleAIChatSubmit(new Event('submit'));
                    }
                }
            }
        });
    }

    document.querySelectorAll('.ai-chip, .chip-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const text = btn.innerText.replace(/^[^\w\s]+/, '').trim();
            const input = document.getElementById('aiChatInput') || document.getElementById('aiQueryInput');
            if (input) {
                openAIChatPanel();
                input.value = text;
                handleAIChatSubmit(new Event('submit'));
            }
        });
    });

    // ── Sidebar toggle (hamburger) — desktop collapse + mobile drawer ──────
    const toggleBtn = document.getElementById('toggleSidebar');
    const sidebar   = document.getElementById('sidebar');
    const overlay   = document.getElementById('sidebarOverlay');

    function openMobileSidebar() {
        if (!sidebar) return;
        sidebar.classList.add('mobile-open');
        if (overlay) { overlay.classList.remove('hidden'); overlay.setAttribute('aria-hidden', 'false'); }
    }

    function closeMobileSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove('mobile-open');
        if (overlay) { overlay.classList.add('hidden'); overlay.setAttribute('aria-hidden', 'true'); }
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const isMobile = window.innerWidth < 1024;
            if (isMobile) {
                const isOpen = sidebar && sidebar.classList.contains('mobile-open');
                isOpen ? closeMobileSidebar() : openMobileSidebar();
            } else {
                // Desktop: toggle mini-icon sidebar mode (Gmail collapsed style)
                if (sidebar) {
                    sidebar.classList.toggle('collapsed');
                }
            }
        });
    }

    // Close mobile sidebar when overlay is tapped
    if (overlay) {
        overlay.addEventListener('click', closeMobileSidebar);
    }

    // Close mobile sidebar when a nav item is clicked (auto-close after navigation)
    document.querySelectorAll('#sidebar .nav-item, #sidebar [data-folder]').forEach(el => {
        el.addEventListener('click', () => {
            if (window.innerWidth < 1024) closeMobileSidebar();
        });
    });

    // Resize listener: clean up mobile state when window grows past breakpoint
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 1024) closeMobileSidebar();
    });
}

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Handle Ctrl+K / Cmd+K Command Palette anytime
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            openCommandPalette();
            return;
        }

        if (e.key === 'Escape') {
            closeCommandPalette();
            closeCompose();
            return;
        }

        if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

        if (e.key === 'c') { e.preventDefault(); openCompose(); }
        else if (e.key === '/') { e.preventDefault(); document.getElementById('searchInput')?.focus(); }
        else if (e.key === 'j') { e.preventDefault(); navigateEmails(1); }
        else if (e.key === 'k') { e.preventDefault(); navigateEmails(-1); }
        else if (e.key === 'e') { e.preventDefault(); archiveActiveEmail(); }
        else if (e.key === '#') { e.preventDefault(); deleteActiveEmail(); }
        else if (e.key === 'r') { e.preventDefault(); quickAIReply('Draft polite reply'); }
        else if (e.key === 'a') { e.preventDefault(); quickAIReply('Draft reply to all participants'); }
    });
}

// ─────────────────────────────────────────
// Email Loading
// ─────────────────────────────────────────

function setComposePrompt(text) {
    document.getElementById('aiComposePrompt').value = text;
    handleGenerateAIDraft();
}

let syncPollCounter = 0;

async function updateUnreadBadge() {
    try {
        const res = await apiFetch('/emails?label=UNREAD&limit=1');
        if (res.ok) {
            const totalHeader = res.headers.get('X-Total-Count');
            const count = totalHeader ? parseInt(totalHeader) : 0;
            const badgeEl = document.getElementById('unreadBadge');
            if (badgeEl) {
                if (count > 0) {
                    badgeEl.textContent = count;
                    badgeEl.classList.remove('hidden');
                } else {
                    badgeEl.classList.add('hidden');
                }
            }
        }
    } catch (_) {}
}

async function loadSmartInbox() {
    state.currentFolder = 'SMART_INBOX';
    const rowsContainer = document.getElementById('emailRows');
    if (rowsContainer) {
        rowsContainer.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs flex flex-col items-center justify-center gap-2.5"><svg class="animate-spin w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span class="font-medium text-slate-300">Sorting Smart Inbox by AI Priority...</span></div>';
    }
    try {
        const res = await apiFetch('/emails?label=INBOX&limit=50&offset=0');
        if (res.ok) {
            const emails = await res.json();
            emails.sort((a, b) => {
                const scoreA = (a.is_unread ? 2 : 0) + (a.is_starred ? 1 : 0);
                const scoreB = (b.is_unread ? 2 : 0) + (b.is_starred ? 1 : 0);
                if (scoreA !== scoreB) return scoreB - scoreA;
                return new Date(b.received_at) - new Date(a.received_at);
            });
            state.emails = emails;
            renderEmailList(emails);
            updatePaginationUI();
            updateUnreadBadge();
        }
    } catch (err) {
        console.error('loadSmartInbox error:', err);
    }
}

async function loadEmails(folder = 'INBOX', offset = 0) {
    if (folder === 'SMART_INBOX') {
        return loadSmartInbox();
    }
    state.currentFolder = folder;
    state.offset = offset;
    const rowsContainer = document.getElementById('emailRows');
    if (rowsContainer && offset === 0 && (!state.emails || state.emails.length === 0)) {
        rowsContainer.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs flex flex-col items-center justify-center gap-2.5"><svg class="animate-spin w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg><span class="font-medium text-slate-300">Syncing your Gmail inbox... Emails will appear in a moment!</span></div>';
    }

    try {
        const res = await apiFetch(`/emails?label=${encodeURIComponent(folder)}&limit=${state.limit}&offset=${offset}`);
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `Server returned status ${res.status}`);
        }
        const totalHeader = res.headers.get('X-Total-Count');
        if (totalHeader) state.totalCount = parseInt(totalHeader);
        
        const emails = await res.json();
        state.emails = emails;
        if (!totalHeader) state.totalCount = emails.length;
        
        renderEmailList(emails);
        updatePaginationUI();
        updateUnreadBadge();

        // Continuously refresh inbox in background while remaining 250+ emails load
        if (folder === 'INBOX' && offset === 0 && state.syncRetryCount < 10) {
            state.syncRetryCount++;
            window.setTimeout(() => {
                if (state.currentFolder === 'INBOX' && offset === 0) {
                    loadEmails('INBOX', 0);
                }
            }, 3000);
        } else if (state.syncRetryCount >= 10) {
            state.syncRetryCount = 0;
        }
    } catch (err) {
        console.error('loadEmails error:', err);
        if (err.message !== 'Session expired') {
            rowsContainer.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">Failed to load emails (${escapeHtml(err.message || 'Unknown error')}).</div>`;
        }
    }
}

function updatePaginationUI() {
    const rangeEl = document.getElementById('emailRange');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    if (!rangeEl) return;

    const start = state.emails.length > 0 ? state.offset + 1 : 0;
    const end = state.offset + state.emails.length;
    const total = state.totalCount || end;

    rangeEl.textContent = `${start}–${end} of ${total}`;

    if (prevBtn) {
        prevBtn.disabled = state.offset <= 0;
        prevBtn.onclick = () => {
            if (state.offset > 0) {
                loadEmails(state.currentFolder, Math.max(0, state.offset - state.limit));
            }
        };
    }
    if (nextBtn) {
        nextBtn.disabled = end >= total;
        nextBtn.onclick = () => {
            if (end < total) {
                loadEmails(state.currentFolder, state.offset + state.limit);
            }
        };
    }
}

async function searchEmails(query) {
    const rowsContainer = document.getElementById('emailRows');
    rowsContainer.innerHTML = '<div class="p-6 text-center text-slate-400 text-xs">Searching inbox...</div>';
    try {
        const res = await apiFetch(`/emails/search?q=${encodeURIComponent(query)}`);
        if (!res.ok) throw new Error(`Status ${res.status}`);
        const emails = await res.json();
        state.emails = emails;
        state.totalCount = emails.length;
        state.offset = 0;
        renderEmailList(emails);
        updatePaginationUI();
    } catch (err) {
        console.error('searchEmails error:', err);
        rowsContainer.innerHTML = '<div class="p-6 text-center text-rose-400 text-xs">Search error.</div>';
    }
}

function renderEmailList(emails) {
    const rowsContainer = document.getElementById('emailRows');
    if (!emails || emails.length === 0) {
        rowsContainer.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs">No emails found in this folder.</div>';
        return;
    }

    try {
        rowsContainer.innerHTML = emails.map((email, idx) => {
            const isUnread = email.is_unread ? 'unread' : '';
            const isChecked = state.selectedEmailIds.has(email.id) ? 'checked' : '';
            const starColor = email.is_starred ? 'text-amber-400 fill-amber-400' : 'text-slate-600';
            let dateStr = '';
            try {
                if (email.received_at) {
                    const d = new Date(email.received_at);
                    const datePart = d.toLocaleDateString([], { month: 'short', day: 'numeric' });
                    const timePart = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                    dateStr = `${datePart}, ${timePart}`;
                }
            } catch (_) {
                dateStr = '';
            }
            const sender = escapeHtml(email.sender_name || email.sender_email || 'Unknown');
            const subject = escapeHtml(email.subject || '(No Subject)');
            const displaySnippet = escapeHtml(email.match_snippet || email.snippet || '');
            const matchTag = email.match_type ? `<span class="text-[9px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-medium shrink-0 mr-1.5">${escapeHtml(email.match_type)}</span>` : '';
            const attCount = email.attachments ? email.attachments.length : 0;
            const attBadge = attCount > 0 ? `<span class="text-[10px] text-indigo-400 font-mono flex items-center gap-0.5 shrink-0 ml-2" title="${attCount} attachment(s)"><i data-lucide="paperclip" class="w-3 h-3"></i>${attCount}</span>` : '';

            return `
                <div data-id="${email.id}" data-idx="${idx}" class="email-row ${isUnread} px-4 py-3 flex items-center gap-3 cursor-pointer transition">
                    <input type="checkbox" ${isChecked} onclick="toggleRowCheckbox('${email.id}', event)" class="rounded bg-slate-800 border-slate-700">
                    <button onclick="toggleStar('${email.id}', event)" class="p-1 text-slate-500 hover:${starColor}">
                        <i data-lucide="star" class="w-4 h-4 ${starColor}"></i>
                    </button>
                    <div class="w-48 truncate font-medium text-xs email-sender">${sender}</div>
                    <div class="flex-1 truncate text-xs flex items-center">
                        ${matchTag}
                        <span class="font-semibold email-subject">${subject}</span>
                        <span class="email-snippet ml-2 truncate">— ${displaySnippet}</span>
                    </div>
                    ${attBadge}
                    <div class="text-[11px] email-date font-mono">${dateStr}</div>
                </div>
            `;
        }).join('');

        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }

        document.querySelectorAll('.email-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.tagName === 'INPUT' || e.target.closest('button')) return;
                const id = row.getAttribute('data-id');
                const idx = parseInt(row.getAttribute('data-idx'));
                selectEmail(id, idx);
            });
        });
    } catch (e) {
        console.error('Error rendering email list:', e);
    }
}

function toggleRowCheckbox(emailId, event) {
    event.stopPropagation();
    if (event.target.checked) {
        state.selectedEmailIds.add(emailId);
    } else {
        state.selectedEmailIds.delete(emailId);
    }
    updateBulkActionsBar();
}

function updateBulkActionsBar() {
    const bar = document.getElementById('bulkActionsBar');
    const badge = document.getElementById('selectedCountBadge');
    const count = state.selectedEmailIds.size;
    if (bar) {
        if (count > 0) {
            bar.style.display = 'flex';
            if (badge) badge.textContent = `${count} selected`;
        } else {
            bar.style.display = 'none';
        }
    }
}

async function triggerBulkAction(action, labelName = null) {
    if (state.selectedEmailIds.size === 0) return;
    const emailIds = Array.from(state.selectedEmailIds);
    try {
        const res = await apiFetch('/emails/bulk-action', {
            method: 'POST',
            body: JSON.stringify({ email_ids: emailIds, action: action, label: labelName })
        });
        if (res.ok) {
            state.selectedEmailIds.clear();
            const selectAllCb = document.getElementById('selectAll');
            if (selectAllCb) selectAllCb.checked = false;
            updateBulkActionsBar();
            loadEmails(state.currentFolder, state.offset);
        }
    } catch (err) {
        console.error('triggerBulkAction error:', err);
    }
}

async function archiveActiveEmail() {
    if (!state.selectedEmailId) return;
    try {
        const res = await apiFetch(`/emails/${state.selectedEmailId}/archive`, { method: 'POST' });
        if (res.ok) {
            showEmailList();
            loadEmails(state.currentFolder);
        }
    } catch (err) { console.error(err); }
}

async function deleteActiveEmail() {
    if (!state.selectedEmailId) return;
    try {
        const res = await apiFetch(`/emails/${state.selectedEmailId}`, { method: 'DELETE' });
        if (res.ok) {
            showEmailList();
            loadEmails(state.currentFolder);
        }
    } catch (err) { console.error(err); }
}

function openCommandPalette() {
    const modal = document.getElementById('commandPaletteModal');
    const input = document.getElementById('commandPaletteInput');
    if (modal) {
        modal.classList.remove('hidden');
        if (input) {
            input.value = '';
            setTimeout(() => input.focus(), 50);
        }
    }
}

function closeCommandPalette() {
    const modal = document.getElementById('commandPaletteModal');
    if (modal) modal.classList.add('hidden');
}

function executeCommand(cmd) {
    closeCommandPalette();
    if (cmd === 'summarize_inbox') {
        openAIChatPanel();
        const input = document.getElementById('aiChatInput') || document.getElementById('aiQueryInput');
        if (input) {
            input.value = 'Summarize my unread emails and top inbox priorities';
            handleAIChatSubmit(new Event('submit'));
        }
    } else if (cmd === 'find_invoices') {
        const invoiceBtn = document.querySelector('[data-folder="INVOICES"]');
        if (invoiceBtn) invoiceBtn.click();
        else searchEmails('invoice OR receipt OR payment');
    } else if (cmd === 'draft_reply') {
        if (state.selectedEmailId) {
            quickAIReply('Draft professional reply to sender');
        } else {
            openCompose();
        }
    } else if (cmd === 'show_meetings') {
        const workBtn = document.querySelector('[data-folder="WORK"]');
        if (workBtn) workBtn.click();
        else searchEmails('meeting OR interview OR agenda');
    } else if (cmd === 'open_ai_search') {
        openAIChatPanel();
        const input = document.getElementById('aiChatInput') || document.getElementById('aiQueryInput');
        if (input) input.focus();
    }
}

async function selectEmail(id, idx) {
    state.selectedEmailId = id;
    state.selectedIndex = idx;

    document.getElementById('emailListContainer').classList.add('hidden');
    document.getElementById('emailViewPanel').classList.remove('hidden');

    const threadContent = document.getElementById('threadContent');
    let email = state.emails.find(e => e.id === id);

    // Fetch full email record (including attachments) from API
    try {
        const res = await apiFetch(`/emails/${id}`);
        if (res.ok) {
            const fullEmail = await res.json();
            email = fullEmail;
            const itemIdx = state.emails.findIndex(e => e.id === id);
            if (itemIdx !== -1) state.emails[itemIdx] = fullEmail;
        }
    } catch (_) {}

    if (!email) return;

    // Auto mark-as-read when opening an unread email
    if (email.is_unread) {
        email.is_unread = false;
        apiFetch(`/emails/${id}/read`, {
            method: 'PATCH',
            body: JSON.stringify({ is_unread: false })
        }).then(() => updateUnreadBadge()).catch(err => console.error('Auto mark read error:', err));
    }

    const dateStr = new Date(email.received_at).toLocaleString();

    let attachmentsHTML = '';
    const attachments = email.attachments || [];
    if (attachments.length > 0) {
        attachmentsHTML = `
            <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-3">
                <div class="flex items-center justify-between">
                    <div class="text-xs font-semibold text-slate-200 flex items-center gap-2">
                        <i data-lucide="paperclip" class="w-4 h-4 text-indigo-400"></i>
                        <span>Attached Documents & Files (${attachments.length})</span>
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    ${attachments.map(att => {
                        const fname = escapeHtml(att.filename || 'Attachment');
                        const ext = (fname.split('.').pop() || '').toLowerCase();
                        let badgeColor = 'bg-slate-800/80 text-slate-300 border-slate-700/80';
                        let iconName = 'file';
                        if (ext === 'pdf') { badgeColor = 'bg-rose-950/80 text-rose-300 border-rose-800/60'; iconName = 'file-text'; }
                        else if (['doc', 'docx'].includes(ext)) { badgeColor = 'bg-blue-950/80 text-blue-300 border-blue-800/60'; iconName = 'file-text'; }
                        else if (['txt', 'md', 'csv', 'json'].includes(ext)) { badgeColor = 'bg-emerald-950/80 text-emerald-300 border-emerald-800/60'; iconName = 'file-code'; }
                        else if (['jpg', 'jpeg', 'png', 'gif'].includes(ext)) { badgeColor = 'bg-amber-950/80 text-amber-300 border-amber-800/60'; iconName = 'image'; }
                        
                        const sizeKB = att.file_size ? `${Math.round(att.file_size / 1024)} KB` : '';
                        const hasText = att.extracted_text && att.extracted_text.length > 10;
                        const textSnippet = hasText ? escapeHtml(att.extracted_text.slice(0, 350)) : '';

                        return `
                            <div class="p-3 rounded-xl ${badgeColor} border flex flex-col justify-between gap-2 shadow-sm">
                                <div class="flex items-start justify-between gap-2">
                                    <div class="flex items-center gap-2 min-w-0">
                                        <i data-lucide="${iconName}" class="w-4 h-4 shrink-0"></i>
                                        <div class="truncate">
                                            <div class="font-semibold text-xs truncate" title="${fname}">${fname}</div>
                                            <div class="text-[10px] opacity-75">${sizeKB || ext.toUpperCase()}</div>
                                        </div>
                                    </div>
                                </div>

                                ${hasText ? `
                                    <div id="attText_${att.id}" style="display:none" class="mt-1 p-2 rounded-lg bg-slate-950/90 border border-slate-800 text-[10px] font-mono text-slate-300 max-h-36 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                                        ${textSnippet}${att.extracted_text.length > 350 ? '...' : ''}
                                    </div>
                                ` : ''}

                                <div class="flex items-center gap-1.5 pt-1.5 border-t border-slate-700/40">
                                    <button onclick="askAIAboutAttachment('${att.id}', '${fname}')" class="px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] font-semibold transition flex items-center gap-1">
                                        <i data-lucide="sparkles" class="w-3 h-3 text-amber-300"></i> Ask AI
                                    </button>
                                    ${hasText ? `
                                        <button onclick="toggleAttachmentText('${att.id}')" class="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] font-medium transition flex items-center gap-1">
                                            <i data-lucide="eye" class="w-3 h-3"></i> Text
                                        </button>
                                    ` : ''}
                                    <a href="${API_BASE}/emails/attachments/${att.id}/content?token=${encodeURIComponent(state.token || '')}" target="_blank" download="${fname}" class="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] font-medium transition flex items-center gap-1 ml-auto">
                                        <i data-lucide="download" class="w-3 h-3"></i> Open
                                    </a>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }

    threadContent.innerHTML = `
        <div class="space-y-4">
            <h1 class="text-xl font-bold font-outfit text-white">${escapeHtml(email.subject)}</h1>
            <div class="flex items-center justify-between border-b border-slate-800 pb-4">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center font-bold text-white text-sm">
                        ${(email.sender_name || email.sender_email)[0].toUpperCase()}
                    </div>
                    <div>
                        <div class="font-semibold text-sm text-slate-200">${escapeHtml(email.sender_name)} <span class="text-xs text-slate-400">&lt;${email.sender_email}&gt;</span></div>
                        <div class="text-xs text-slate-400">To: ${escapeHtml(email.recipient_list)}</div>
                    </div>
                </div>
                <div class="text-xs text-slate-400 font-mono">${dateStr}</div>
            </div>
            ${attachmentsHTML}
            <div class="prose prose-invert max-w-none text-slate-200 text-sm leading-relaxed bg-slate-900/40 p-5 rounded-2xl border border-slate-800/80">
                ${email.body_html || escapeHtml(email.body_text)}
            </div>

            <!-- Email Action Buttons Card -->
            <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 flex flex-wrap items-center justify-between gap-3">
                <div class="flex flex-wrap items-center gap-2">
                    <button onclick="openReplyToSelectedEmail()" class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition flex items-center gap-2 shadow-md shadow-indigo-600/20">
                        <i data-lucide="reply" class="w-4 h-4"></i> Reply
                    </button>
                    <button onclick="openReplyToSelectedEmail()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition flex items-center gap-2 border border-slate-700">
                        <i data-lucide="reply-all" class="w-4 h-4"></i> Reply All
                    </button>
                    <button onclick="openForwardToSelectedEmail()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition flex items-center gap-2 border border-slate-700">
                        <i data-lucide="forward" class="w-4 h-4"></i> Forward
                    </button>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="toggleStarSelectedEmail()" class="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition border border-slate-700 flex items-center gap-1.5">
                        <i data-lucide="star" class="w-4 h-4 ${email.is_starred ? 'text-amber-400 fill-amber-400' : 'text-slate-400'}"></i> ${email.is_starred ? 'Starred' : 'Star'}
                    </button>
                    <button onclick="archiveSelectedEmail()" class="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition border border-slate-700 flex items-center gap-1.5">
                        <i data-lucide="archive" class="w-4 h-4 text-emerald-400"></i> Archive
                    </button>
                </div>
            </div>

            <!-- AI Reply Generator Section -->
            <div class="p-4 rounded-2xl bg-indigo-950/30 border border-indigo-500/20 space-y-3">
                <div class="text-xs font-semibold text-indigo-300 flex items-center gap-2">
                    <i data-lucide="sparkles" class="w-4 h-4 text-amber-300"></i>
                    <span>Generate Smart AI Reply</span>
                </div>
                <div class="flex flex-wrap gap-2">
                    <button onclick="quickAIReply('Confirm attendance and thank the sender')" class="px-3 py-1.5 rounded-xl bg-indigo-600/30 hover:bg-indigo-600/50 border border-indigo-500/30 text-xs text-indigo-200 transition">✅ Confirm</button>
                    <button onclick="quickAIReply('Politely decline the invitation due to scheduling conflict')" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300 transition">❌ Decline</button>
                    <button onclick="quickAIReply('Request more details regarding the agenda')" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300 transition">❓ More Info</button>
                </div>
            </div>
        </div>
    `;
    lucide.createIcons();
}

async function toggleReadSelectedEmail() {
    if (!state.selectedEmailId) return;
    const email = state.emails.find(e => e.id === state.selectedEmailId);
    const newUnread = email ? !email.is_unread : true;
    try {
        const res = await apiFetch(`/emails/${state.selectedEmailId}/read`, {
            method: 'PATCH',
            body: JSON.stringify({ is_unread: newUnread })
        });
        if (res.ok) {
            if (email) email.is_unread = newUnread;
            showEmailList();
            loadEmails(state.currentFolder, state.offset);
        }
    } catch (err) { console.error('toggleRead error:', err); }
}

async function toggleStarSelectedEmail() {
    if (!state.selectedEmailId) return;
    const email = state.emails.find(e => e.id === state.selectedEmailId);
    const newStarred = email ? !email.is_starred : true;
    try {
        const res = await apiFetch(`/emails/${state.selectedEmailId}/star`, {
            method: 'PATCH',
            body: JSON.stringify({ is_starred: newStarred })
        });
        if (res.ok) {
            if (email) email.is_starred = newStarred;
            selectEmail(state.selectedEmailId, state.selectedIndex);
            loadEmails(state.currentFolder, state.offset);
        }
    } catch (err) { console.error('toggleStar error:', err); }
}

async function archiveSelectedEmail() {
    if (!state.selectedEmailId) return;
    try {
        const res = await apiFetch(`/emails/${state.selectedEmailId}/archive`, {
            method: 'POST'
        });
        if (res.ok) {
            showEmailList();
            loadEmails(state.currentFolder, state.offset);
        }
    } catch (err) { console.error('archive error:', err); }
}

async function deleteSelectedEmail() {
    if (!state.selectedEmailId) return;
    if (!confirm('Are you sure you want to delete this email?')) return;
    try {
        const res = await apiFetch(`/emails/${state.selectedEmailId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            showEmailList();
            loadEmails(state.currentFolder, state.offset);
        }
    } catch (err) { console.error('delete error:', err); }
}

function openReplyToSelectedEmail() {
    if (!state.selectedEmailId) return;
    const email = state.emails.find(e => e.id === state.selectedEmailId);
    if (!email) return;
    openCompose();
    const toInput = document.getElementById('composeTo');
    const subjInput = document.getElementById('composeSubject');
    if (toInput) toInput.value = email.sender_email;
    if (subjInput) subjInput.value = email.subject.startsWith('Re:') ? email.subject : `Re: ${email.subject}`;
    const bodyInput = document.getElementById('composeBody');
    if (bodyInput) bodyInput.focus();
}

function openForwardToSelectedEmail() {
    if (!state.selectedEmailId) return;
    const email = state.emails.find(e => e.id === state.selectedEmailId);
    if (!email) return;
    openCompose();
    const toInput = document.getElementById('composeTo');
    const subjInput = document.getElementById('composeSubject');
    const bodyInput = document.getElementById('composeBody');
    if (toInput) toInput.value = '';
    if (subjInput) subjInput.value = email.subject.startsWith('Fwd:') ? email.subject : `Fwd: ${email.subject}`;
    if (bodyInput) {
        bodyInput.value = `\n\n---------- Forwarded message ---------\nFrom: ${email.sender_name} <${email.sender_email}>\nDate: ${new Date(email.received_at).toLocaleString()}\nSubject: ${email.subject}\nTo: ${email.recipient_list}\n\n${email.body_text || ''}`;
    }
}

function showEmailList() {
    document.getElementById('emailViewPanel').classList.add('hidden');
    document.getElementById('emailListContainer').classList.remove('hidden');
}

function navigateEmails(direction) {
    if (state.emails.length === 0) return;
    let nextIdx = state.selectedIndex + direction;
    if (nextIdx < 0) nextIdx = 0;
    if (nextIdx >= state.emails.length) nextIdx = state.emails.length - 1;
    const nextEmail = state.emails[nextIdx];
    if (nextEmail) selectEmail(nextEmail.id, nextIdx);
}

async function toggleStar(emailId, event) {
    if (event) event.stopPropagation();
    const email = state.emails.find(e => e.id === emailId);
    if (!email) return;

    // Optimistic UI Update (0ms latency)
    email.is_starred = !email.is_starred;
    if (event && event.currentTarget) {
        const icon = event.currentTarget.querySelector('i, svg');
        if (icon) {
            if (email.is_starred) {
                icon.classList.add('text-amber-400', 'fill-amber-400');
                icon.classList.remove('text-slate-400');
            } else {
                icon.classList.remove('text-amber-400', 'fill-amber-400');
                icon.classList.add('text-slate-400');
            }
        }
    }

    try {
        await apiFetch(`/emails/${emailId}/star`, {
            method: 'PATCH',
            body: JSON.stringify({ is_starred: email.is_starred })
        });
    } catch (err) {
        email.is_starred = !email.is_starred;
        console.error('toggleStar error:', err);
    }
}

function openCompose() {
    state.isReplyMode = false;
    document.getElementById('composeModal').classList.remove('hidden');
}

function closeCompose() {
    document.getElementById('composeModal').classList.add('hidden');
}

async function handleComposeSubmit(e) {
    e.preventDefault();
    const to = document.getElementById('composeTo').value.split(',').map(s => s.trim()).filter(Boolean);
    const subject = document.getElementById('composeSubject').value;
    const body_html = document.getElementById('composeBody').value;
    if (!to.length) {
        alert('Enter at least one recipient.');
        return;
    }
    try {
        const res = await apiFetch('/emails/send', {
            method: 'POST',
            body: JSON.stringify({
                to,
                subject,
                body_html,
                thread_id: state.isReplyMode ? state.emails.find(e => e.id === state.selectedEmailId)?.thread_id : null
            })
        });
        if (!res.ok) {
            const error = await res.json().catch(() => ({}));
            throw new Error(error.detail || 'Failed to send email.');
        }
        if (res.ok) {
            closeCompose();
            loadEmails(state.currentFolder);
            appendChatMessage('assistant', `✅ Sent email to ${to.join(', ')} — "${subject}"`);
        }
    } catch (err) { alert('Failed to send email.'); }
}

async function handleGenerateAIDraft() {
    const userPrompt = document.getElementById('aiComposePrompt').value.trim();
    if (!userPrompt) return;
    const btn = document.getElementById('generateAIDraftBtn');
    btn.innerText = 'Generating...';
    try {
        if (state.isReplyMode && state.selectedEmailId) {
            const res = await apiFetch('/ai/generate-reply', {
                method: 'POST',
                body: JSON.stringify({ email_id: state.selectedEmailId, user_intent: userPrompt })
            });
            const data = await res.json();
            document.getElementById('composeBody').value = data.draft_reply || data.answer || '';
            if (data.recipient) document.getElementById('composeTo').value = data.recipient;
            if (data.subject && !document.getElementById('composeSubject').value) {
                document.getElementById('composeSubject').value = data.subject;
            }
        } else {
            const res = await apiFetch('/ai/query', {
                method: 'POST',
                body: JSON.stringify({ query: `Draft a professional email for: ${userPrompt}` })
            });
            const data = await res.json();
            document.getElementById('composeBody').value = data.answer || '';
        }
    } catch (err) {
        console.error('handleGenerateAIDraft error:', err);
    } finally {
        btn.innerText = 'Generate';
    }
}

async function quickAIReply(intent) {
    if (!state.selectedEmailId) return;
    const email = state.emails.find(e => e.id === state.selectedEmailId);
    state.isReplyMode = true;
    openCompose();
    state.isReplyMode = true;
    if (email) {
        document.getElementById('composeTo').value = email.sender_email;
        document.getElementById('composeSubject').value = email.subject.startsWith('Re:') ? email.subject : `Re: ${email.subject}`;
    }
    document.getElementById('aiComposePrompt').value = intent;
    handleGenerateAIDraft();
}

async function handleSummarizeCurrentEmail() {
    if (!state.selectedEmailId) return;

    // Ensure AI Chat Panel is open
    document.getElementById('aiChatPanel').classList.remove('hidden');

    const email = state.emails.find(e => e.id === state.selectedEmailId);
    const subject = email ? email.subject : 'Selected Email';
    const threadId = email ? email.thread_id : null;

    appendChatMessage('user', `Summarize: "${subject}"`);
    const botDiv = appendChatMessage('assistant', 'Generating summary...');
    botDiv.innerHTML = '<div class="ai-text-content">Generating summary...</div><div class="ai-sources-content"></div>';
    const textEl = botDiv.querySelector('.ai-text-content');

    // Prefer thread summary stream if we have a thread_id
    if (threadId) {
        try {
            const res = await fetch(`${API_BASE}/ai/summarize-thread`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${state.token}` },
                body: JSON.stringify({ thread_id: threadId })
            });
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                for (const line of decoder.decode(value).split('\n')) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.replace('data: ', '').trim();
                        if (dataStr === '[DONE]') break;
                        try {
                            const parsed = JSON.parse(dataStr);
                            if (parsed.text) { fullText += parsed.text; textEl.innerText = fullText; }
                        } catch (_) {}
                    }
                }
            }
            if (!fullText) textEl.innerText = 'Thread summary generated.';
            return;
        } catch (_) {
            // fallthrough to single email summary
        }
    }

    // Single email fallback
    try {
        const res = await apiFetch('/ai/summarize-email', {
            method: 'POST',
            body: JSON.stringify({ email_id: state.selectedEmailId })
        });
        const data = await res.json();
        textEl.innerHTML = renderMarkdown(data.summary || 'Summary generated.');
    } catch (err) {
        textEl.innerText = 'Error generating summary.';
    }
}

function toggleAIChat() {
    const panel = document.getElementById('aiChatPanel');
    if (panel) panel.classList.toggle('hidden');
}

function openAIChatPanel() {
    const panel = document.getElementById('aiChatPanel');
    if (panel) panel.classList.remove('hidden');
}

function appendChatMessage(role, text) {
    const container = document.getElementById('aiChatMessages') || document.getElementById('chatMessages');
    if (!container) return null;
    const isUser = role === 'user';
    const msgDiv = document.createElement('div');
    msgDiv.className = isUser ? 'flex items-start gap-2.5 justify-end' : 'flex items-start gap-2.5';
    msgDiv.innerHTML = isUser ? `
        <div class="bg-indigo-600 rounded-2xl rounded-tr-none p-3 text-white max-w-[85%] leading-relaxed shadow-sm">
            ${escapeHtml(text)}
        </div>
    ` : `
        <div class="w-6 h-6 rounded-full bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-[10px] text-indigo-300 font-bold shrink-0">AI</div>
        <div class="bg-slate-800/90 rounded-2xl rounded-tl-none p-3 text-slate-300 border border-slate-700/60 leading-relaxed max-w-[85%] shadow-sm space-y-2">
            ${escapeHtml(text)}
        </div>
    `;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
    return isUser ? msgDiv : msgDiv.querySelector('.bg-slate-800\\/90');
}

async function handleAIChatSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    const input = document.getElementById('aiChatInput') || document.getElementById('aiQueryInput');
    if (!input) return;
    const query = input.value.trim();
    if (!query) return;
    input.value = '';
    appendChatMessage('user', query);

    const queryLower = query.toLowerCase();
    const isAction = ['archive', 'star', 'flag', 'mark as read', 'delete', 'trash'].some(w => queryLower.includes(w));

    if (isAction) {
        const actionBotDiv = appendChatMessage('assistant', 'Processing inbox action...');
        try {
            const actRes = await apiFetch('/ai/execute-action', {
                method: 'POST',
                body: JSON.stringify({ prompt: query })
            });
            if (actRes.ok) {
                const actData = await actRes.json();
                if (actData.executed) {
                    actionBotDiv.innerHTML = `
                        <div class="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl text-emerald-200 text-xs font-semibold flex items-center gap-2 shadow-sm">
                            <span class="text-base">⚡</span> ${escapeHtml(actData.message)}
                        </div>
                    `;
                    loadEmails(state.currentFolder);
                    return;
                }
            }
        } catch (err) { console.warn('Action execution fallback to RAG:', err); }
    }

    const botDiv = appendChatMessage('assistant', 'Thinking...');
    
    botDiv.innerHTML = '<div class="ai-text-content">Thinking...</div><div class="ai-sources-content"></div>';
    const textEl = botDiv.querySelector('.ai-text-content');
    const sourcesEl = botDiv.querySelector('.ai-sources-content');

    let currentSources = [];

    try {
        const response = await fetch(`${API_BASE}/ai/query-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${state.token}` },
            body: JSON.stringify({ query })
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            const lines = decoder.decode(value).split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.replace('data: ', '').trim();
                    if (dataStr === '[DONE]') break;
                    try {
                        const parsed = JSON.parse(dataStr);
                        if (parsed.type === 'sources') {
                            currentSources = parsed.sources || [];
                        } else if (parsed.type === 'text') {
                            if (parsed.text) {
                                fullText += parsed.text;
                                textEl.innerText = fullText;
                            }
                        } else if (parsed.text) {
                            fullText += parsed.text;
                            textEl.innerText = fullText;
                        }
                    } catch (_) {}
                }
            }
        }

        if (!fullText) {
            textEl.innerText = 'SmartMail AI: Checked your emails and retrieved details for your query.';
        }

        if (currentSources && currentSources.length > 0) {
            sourcesEl.innerHTML = `
                <div class="mt-3 pt-2.5 border-t border-slate-700/60 space-y-1.5">
                    <div class="text-[10px] font-semibold text-indigo-300 uppercase tracking-wider flex items-center gap-1">
                        <i data-lucide="mail" class="w-3 h-3 text-indigo-400"></i> Referenced Email:
                    </div>
                    <div class="flex flex-col gap-1.5">
                        ${currentSources.map(src => `
                            <button onclick="openEmailFromChat('${src.email_id}')" class="text-left px-3 py-2 rounded-xl bg-indigo-950/80 hover:bg-indigo-900/90 border border-indigo-500/40 transition group flex items-center justify-between gap-2 shadow-sm">
                                <div class="truncate">
                                    <div class="font-semibold text-xs text-indigo-100 group-hover:text-white truncate">${escapeHtml(src.subject)}</div>
                                    <div class="text-[10px] text-slate-400">From: ${escapeHtml(src.sender)} ${src.date ? '• ' + src.date : ''}</div>
                                </div>
                                <i data-lucide="external-link" class="w-3.5 h-3.5 text-indigo-400 group-hover:text-indigo-200 shrink-0"></i>
                            </button>
                        `).join('')}
                    </div>
                </div>
            `;
            lucide.createIcons();
        }

    } catch (err) {
        textEl.innerText = 'SmartMail AI: Could not reach the assistant.';
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-slate-100">$1</strong>');
    // Italic: *text*
    html = html.replace(/\*(.*?)\*/g, '<em class="italic text-slate-300">$1</em>');
    // Code block: `code`
    html = html.replace(/`(.*?)`/g, '<code class="bg-slate-800 text-indigo-300 px-1 py-0.5 rounded text-[11px] font-mono">$1</code>');
    // Bullet points
    html = html.replace(/^[-•*]\s+(.*)$/gm, '<li class="ml-4 list-disc text-slate-200 py-0.5">$1</li>');
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    return html;
}

// ─────────────────────────────────────────
// Open email from AI Chat source citation
// ─────────────────────────────────────────
function openEmailFromChat(emailId) {
    if (!emailId) return;
    const email = state.emails.find(e => e.id === emailId);
    if (email) {
        const idx = state.emails.indexOf(email);
        selectEmail(emailId, idx);
    } else {
        apiFetch(`/emails/${emailId}`)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (data) {
                    state.emails.unshift(data);
                    selectEmail(data.id, 0);
                }
            })
            .catch(() => {
                appendChatMessage('assistant', `Could not open email (ID: ${escapeHtml(emailId)})`);
            });
    }
}

// ─────────────────────────────────────────
// Smart Inbox — Priority-sorted email view
// ─────────────────────────────────────────
async function loadSmartInbox() {
    state.currentFolder = 'SMART_INBOX';
    const rowsContainer = document.getElementById('emailRows');
    rowsContainer.innerHTML = `
        <div class="p-6 text-center">
            <div class="flex items-center justify-center gap-2 text-indigo-400 text-xs font-semibold">
                <svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
                AI is scoring your emails by priority...
            </div>
        </div>`;

    try {
        const res = await apiFetch('/emails/smart-inbox?limit=20');
        if (!res.ok) throw new Error(`Status ${res.status}`);
        const emails = await res.json();
        state.emails = emails;
        state.totalCount = emails.length;
        state.offset = 0;
        renderSmartInboxList(emails);
        updatePaginationUI();
    } catch (err) {
        rowsContainer.innerHTML = `<div class="p-6 text-center text-rose-400 text-xs">Failed to load Smart Inbox: ${escapeHtml(err.message)}</div>`;
    }
}

const PRIORITY_CONFIG = {
    HIGH:   { color: 'text-rose-400',   bg: 'bg-rose-500/15',   border: 'border-rose-500/30',   dot: 'bg-rose-400',   label: '🔴 High' },
    MEDIUM: { color: 'text-amber-400',  bg: 'bg-amber-500/15',  border: 'border-amber-500/30',  dot: 'bg-amber-400',  label: '🟡 Medium' },
    LOW:    { color: 'text-slate-400',  bg: 'bg-slate-700/20',  border: 'border-slate-600/30',  dot: 'bg-slate-500',  label: '🟢 Low' },
};

function renderSmartInboxList(emails) {
    const rowsContainer = document.getElementById('emailRows');
    if (!emails || emails.length === 0) {
        rowsContainer.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs">Smart Inbox is empty.</div>';
        return;
    }

    // Header
    rowsContainer.innerHTML = `
        <div class="px-4 py-2.5 bg-indigo-950/30 border-b border-indigo-500/20 flex items-center gap-2">
            <i data-lucide="brain" class="w-3.5 h-3.5 text-indigo-400"></i>
            <span class="text-[11px] font-semibold text-indigo-300">AI Priority Ranking</span>
            <span class="text-[10px] text-slate-400 ml-auto">${emails.length} emails scored</span>
        </div>
        ${emails.map((email, idx) => {
            const cfg = PRIORITY_CONFIG[email.priority_label] || PRIORITY_CONFIG.LOW;
            const isUnread = email.is_unread ? 'font-semibold' : '';
            const dateStr = email.received_at ? new Date(email.received_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '';
            return `
            <div data-id="${email.id}" data-idx="${idx}" class="email-row smart-row px-4 py-3 flex items-start gap-3 cursor-pointer hover:bg-slate-900/50 transition border-b border-slate-800/40">
                <div class="flex flex-col items-center gap-1 pt-0.5 shrink-0">
                    <div class="w-2.5 h-2.5 rounded-full ${cfg.dot}"></div>
                    <span class="text-[9px] font-bold ${cfg.color}">${email.priority_score}</span>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between gap-2 mb-0.5">
                        <span class="text-xs ${isUnread} text-slate-200 truncate">${escapeHtml(email.sender_name || email.sender_email)}</span>
                        <span class="text-[10px] text-slate-400 font-mono shrink-0">${dateStr}</span>
                    </div>
                    <div class="text-xs text-slate-300 truncate ${isUnread}">${escapeHtml(email.subject)}</div>
                    <div class="flex items-center gap-2 mt-1">
                        <span class="text-[10px] px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.color} border ${cfg.border} font-semibold">${cfg.label}</span>
                        <span class="text-[10px] text-slate-400 truncate">${escapeHtml(email.priority_reason)}</span>
                    </div>
                </div>
            </div>
            `;
        }).join('')}
    `;

    if (window.lucide) window.lucide.createIcons();

    document.querySelectorAll('.smart-row').forEach(row => {
        row.addEventListener('click', () => {
            const id = row.getAttribute('data-id');
            const idx = parseInt(row.getAttribute('data-idx'));
            selectEmail(id, idx);
        });
    });
}

// ─────────────────────────────────────────
// AI Search Suggestions dropdown
// ─────────────────────────────────────────
async function fetchSearchSuggestions(partialQuery) {
    try {
        const res = await apiFetch('/ai/search-suggestions', {
            method: 'POST',
            body: JSON.stringify({ partial_query: partialQuery, limit: 5 })
        });
        if (!res.ok) return;
        const data = await res.json();
        renderSearchSuggestions(data.suggestions || []);
    } catch (_) {
        hideSearchSuggestions();
    }
}

function renderSearchSuggestions(suggestions) {
    const dropdown = document.getElementById('searchSuggestions');
    const list = document.getElementById('searchSuggestionsList');
    if (!dropdown || !list) return;
    if (!suggestions || !suggestions.length) { hideSearchSuggestions(); return; }

    state.currentSuggestions = suggestions;

    list.innerHTML = suggestions.map((s, idx) => `
        <button type="button" data-idx="${idx}" class="suggestion-item w-full text-left px-4 py-2 hover:bg-indigo-600/20 text-slate-300 hover:text-white transition flex items-center gap-2 cursor-pointer select-none">
            <i data-lucide="search" class="w-3 h-3 text-slate-500 shrink-0 pointer-events-none"></i>
            <span class="truncate pointer-events-none">${escapeHtml(s)}</span>
        </button>
    `).join('');
    if (window.lucide) window.lucide.createIcons();

    dropdown.style.display = 'block';
}

function hideSearchSuggestions() {
    const dropdown = document.getElementById('searchSuggestions');
    if (dropdown) dropdown.style.display = 'none';
}

function applySuggestion(text) {
    const input = document.getElementById('searchInput');
    if (input) {
        input.value = text;
        hideSearchSuggestions();
        searchEmails(text);
    }
}

// ─────────────────────────────────────────
// RAG Developer Dashboard
// ─────────────────────────────────────────
async function refreshRagDashboard() {
    const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setEl('statChunks', '…');
    setEl('statEmails', '…');
    setEl('statLatency', '…');
    setEl('statDims', '…');
    setEl('statProvider', '…');
    try {
        const res = await apiFetch('/eval/stats');
        if (!res.ok) return;
        const data = await res.json();
        setEl('statChunks', data.total_chunks ?? '—');
        setEl('statEmails', data.total_emails_indexed ?? '—');
        setEl('statLatency', data.avg_retrieval_latency_ms ? `${data.avg_retrieval_latency_ms} ms` : '—');
        setEl('statDims', data.embedding_dimensions ?? '—');
        setEl('statProvider', data.llm_provider ?? '—');
    } catch (_) {
        setEl('statChunks', 'Error');
    }
}

// ─────────────────────────────────────────
// Document & Attachment Intelligence Actions
// ─────────────────────────────────────────
function toggleAttachmentText(attId) {
    const el = document.getElementById(`attText_${attId}`);
    if (el) {
        el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }
}

async function askAIAboutAttachment(attId, filename) {
    openAIChatPanel();
    const defaultQuestion = `Summarize key details from attached document "${filename}" and list any action items, financial amounts, or dates mentioned.`;
    
    appendChatMessage('user', `Ask about document "${filename}": ${defaultQuestion}`);
    const botDiv = appendChatMessage('assistant', 'Analyzing document...');
    botDiv.innerHTML = '<div class="ai-text-content"><div class="flex items-center gap-2 text-indigo-400 text-xs py-1"><svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> Analyzing document content...</div></div><div class="ai-sources-content"></div>';
    const textEl = botDiv.querySelector('.ai-text-content');

    try {
        const res = await apiFetch('/ai/ask-attachment', {
            method: 'POST',
            body: JSON.stringify({
                attachment_id: attId,
                question: defaultQuestion,
                email_id: state.selectedEmailId
            })
        });
        if (!res.ok) throw new Error(`Status ${res.status}`);
        const data = await res.json();
        textEl.innerHTML = renderMarkdown(data.answer || 'Analysis complete.');
    } catch (err) {
        textEl.innerText = `Error analyzing attachment: ${err.message}`;
    }
}

// ─────────────────────────────────────────
// Global Window Exports for Inline HTML Handlers
// ─────────────────────────────────────────
window.quickAIReply = quickAIReply;
window.setComposePrompt = setComposePrompt;
window.openEmailFromChat = openEmailFromChat;
window.toggleStar = toggleStar;
window.toggleRowCheckbox = toggleRowCheckbox;
window.updateBulkActionsBar = updateBulkActionsBar;
window.triggerBulkAction = triggerBulkAction;
window.archiveActiveEmail = archiveActiveEmail;
window.deleteActiveEmail = deleteActiveEmail;
window.openCommandPalette = openCommandPalette;
window.closeCommandPalette = closeCommandPalette;
window.executeCommand = executeCommand;
window.openCompose = openCompose;
window.closeCompose = closeCompose;
window.toggleAIChat = toggleAIChat;
window.openAIChatPanel = openAIChatPanel;
window.handleGenerateAIDraft = handleGenerateAIDraft;
window.handleSummarizeCurrentEmail = handleSummarizeCurrentEmail;
window.loadEmails = loadEmails;
window.searchEmails = searchEmails;
window.showEmailList = showEmailList;
window.handleGoogleLogin = handleGoogleLogin;
window.handleDemoLogin = handleDemoLogin;
window.loadSmartInbox = loadSmartInbox;
window.applySuggestion = applySuggestion;
window.refreshRagDashboard = refreshRagDashboard;
window.selectEmail = selectEmail;
window.toggleAttachmentText = toggleAttachmentText;
window.askAIAboutAttachment = askAIAboutAttachment;
window.renderMarkdown = renderMarkdown;
