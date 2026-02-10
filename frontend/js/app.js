/**
 * Main Application Logic
 */

// Global variables
let wsClient = null;
let currentJobId = null;
let jobStats = {
    docsProcessed: 0,
    transcriptsFound: 0,
    transcriptsDownloaded: 0
};
let cmecfErrors = []; // Store CMECF errors for report

/**
 * Initialize application
 */
function initApp() {
    console.log('Initializing Document Scraper Control Panel...');

    // Connect to WebSocket (with auth token)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    wsClient = new WebSocketClient(wsUrl, Auth.getToken());
    window.wsClient = wsClient;

    // Set up WebSocket event handlers
    wsClient.onConnectionChange = (isConnected) => {
        UIComponents.updateConnectionStatus(isConnected);

        if (isConnected) {
            UIComponents.addLogEntry('Connected to server', 'success');
        } else {
            UIComponents.addLogEntry('Disconnected from server', 'error');
        }
    };

    wsClient.onMessage = handleWebSocketMessage;

    wsClient.onError = (error) => {
        console.error('WebSocket error:', error);
        UIComponents.addLogEntry('Connection error', 'error');
    };

    // Connect
    wsClient.connect();

    // Set up Bloomberg form submission
    document.getElementById('searchForm').addEventListener('submit', handleFormSubmit);

    // Set up Bloomberg stop button
    document.getElementById('stopBtn').addEventListener('click', handleStop);

    // Set up CMECF form submission
    document.getElementById('cmecfForm').addEventListener('submit', handleCMECFFormSubmit);

    // Set up CMECF stop button
    document.getElementById('cmecfStopBtn').addEventListener('click', handleCMECFStop);

    // Download path: load current and save button
    loadDownloadPath();
    document.getElementById('saveDownloadPathBtn').addEventListener('click', saveDownloadPath);

    document.getElementById('loadServerFilesBtn').addEventListener('click', loadServerFiles);
    document.getElementById('clearServerFilesBtn').addEventListener('click', clearServerFiles);

    document.getElementById('logoutBtn').addEventListener('click', () => {
        if (wsClient) wsClient.disconnect();
        Auth.logout();
    });

    UIComponents.addLogEntry('Application initialized', 'info');
}

async function loadDownloadPath() {
    try {
        const r = await fetch('/api/settings', { headers: Auth.getAuthHeaders() });
        if (r.ok) {
            const data = await r.json();
            document.getElementById('downloadPathInput').value = data.download_path || '';
        }
    } catch (e) {
        console.error('Load settings:', e);
    }
}

async function saveDownloadPath() {
    const input = document.getElementById('downloadPathInput');
    const statusEl = document.getElementById('downloadPathStatus');
    try {
        const r = await fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...Auth.getAuthHeaders() },
            body: JSON.stringify({ download_path: input.value.trim() || null })
        });
        if (r.ok) {
            statusEl.textContent = 'Saved';
            statusEl.className = 'download-path-status saved';
        } else {
            statusEl.textContent = 'Failed to save';
            statusEl.className = 'download-path-status error';
        }
    } catch (e) {
        statusEl.textContent = 'Error';
        statusEl.className = 'download-path-status error';
    }
    setTimeout(() => { statusEl.textContent = ''; }, 3000);
}

async function loadServerFiles() {
    const listEl = document.getElementById('serverDownloadsList');
    listEl.innerHTML = '<span class="log-message">Loading...</span>';
    try {
        const r = await fetch('/api/downloads', { headers: Auth.getAuthHeaders() });
        if (!r.ok) throw new Error(r.statusText);
        const data = await r.json();
        const files = data.files || [];
        if (files.length === 0) {
            listEl.innerHTML = '<span class="log-message">No files on server (or path not set).</span>';
            return;
        }
        listEl.innerHTML = files.map(f => {
            const safePath = encodeURIComponent(f.path);
            return `<div class="download-item" style="display: flex; align-items: center; justify-content: space-between;">
                <div><span class="download-filename">${f.name}</span> <small class="download-entry-meta">${f.path}</small></div>
                <button type="button" class="btn btn-secondary" style="margin-left: 8px;" data-path="${f.path.replace(/"/g, '&quot;')}">Download</button>
            </div>`;
        }).join('');
        listEl.querySelectorAll('button[data-path]').forEach(btn => {
            btn.addEventListener('click', () => downloadFileFromServer(btn.getAttribute('data-path')));
        });
    } catch (e) {
        listEl.innerHTML = `<span class="log-message log-error">Failed to load: ${e.message}</span>`;
    }
}

async function downloadFileFromServer(path) {
    try {
        const r = await fetch('/api/downloads/file?path=' + encodeURIComponent(path), { headers: Auth.getAuthHeaders() });
        if (!r.ok) throw new Error(r.statusText);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = path.split('/').pop() || 'download.pdf';
        a.click();
        URL.revokeObjectURL(url);
        // Remove file from server after successful download (auto-clean cache)
        fetch('/api/downloads/file?path=' + encodeURIComponent(path), { method: 'DELETE', headers: Auth.getAuthHeaders() }).catch(() => {});
        loadServerFiles();
    } catch (e) {
        console.error('Download failed:', e);
        alert('Download failed: ' + e.message);
    }
}

async function clearServerFiles() {
    if (!confirm('Delete all files on the server? This cannot be undone. Use this after you have downloaded what you need.')) return;
    try {
        const r = await fetch('/api/downloads', { method: 'DELETE', headers: Auth.getAuthHeaders() });
        if (!r.ok) throw new Error(r.statusText);
        const data = await r.json();
        const n = data.deleted != null ? data.deleted : 0;
        alert(n > 0 ? `Cleared ${n} file(s) from the server.` : 'No files were on the server.');
        loadServerFiles();
    } catch (e) {
        console.error('Clear failed:', e);
        alert('Failed to clear server files: ' + e.message);
    }
}

function setupLoginForm() {
    document.getElementById('loginForm').addEventListener('submit', handleLoginSubmit);
}

async function handleLoginSubmit(e) {
    e.preventDefault();
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errEl = document.getElementById('loginError');
    errEl.style.display = 'none';
    try {
        const r = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await r.json().catch(() => ({}));
        if (r.ok && data.token) {
            Auth.setToken(data.token);
            Auth.showApp();
            initApp();
        } else {
            errEl.textContent = data.detail || 'Invalid username or password';
            errEl.style.display = 'block';
        }
    } catch (err) {
        errEl.textContent = 'Connection error';
        errEl.style.display = 'block';
    }
}

/**
 * Handle form submission
 */
async function handleFormSubmit(event) {
    event.preventDefault();
    
    // Get form values
    const keywords = document.getElementById('keywords').value.trim();
    const courtName = document.getElementById('courtName').value.trim();
    const judgeName = document.getElementById('judgeName').value.trim(); // Optional

    // Get selection mode
    const selectionMode = document.querySelector('input[name="selectionMode"]:checked').value;
    const rangeStart = document.getElementById('rangeStart').value;
    const rangeEnd = document.getElementById('rangeEnd').value;
    const downloadMode = document.querySelector('input[name="downloadMode"]:checked').value;

    if (!keywords || !courtName) {
        alert('Please fill in keywords and court name');
        return;
    }
    
    // Reset UI
    UIComponents.reset();
    jobStats = { docsProcessed: 0, transcriptsFound: 0, transcriptsDownloaded: 0 };
    
    // Disable form
    setFormEnabled(false);
    
    UIComponents.addLogEntry('Starting scraping job...', 'info');
    
    try {
        // Get client ID from WebSocket
        const clientId = wsClient.clientId;

        if (!clientId) {
            throw new Error('WebSocket not connected. Please refresh the page.');
        }

        // Create job via REST API
        const response = await fetch('/api/scrape/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...Auth.getAuthHeaders(),
            },
            body: JSON.stringify({
                keywords,
                court_name: courtName,
                judge_name: judgeName,
                client_id: clientId,
                // Selection mode parameters
                selection_mode: selectionMode,
                document_range_start: rangeStart ? parseInt(rangeStart) : 1,
                document_range_end: rangeEnd ? parseInt(rangeEnd) : null,
                download_mode: downloadMode
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Failed to create job');
        }

        const jobData = await response.json();
        currentJobId = jobData.job_id;

        UIComponents.addLogEntry(`Job created: ${currentJobId}`, 'success');
        UIComponents.addLogEntry('Scraping job started', 'info');

        // Show job summary panel
        document.getElementById('jobSummary').style.display = 'block';

    } catch (error) {
        console.error('Error creating job:', error);
        UIComponents.addLogEntry('Failed to create job: ' + error.message, 'error');
        setFormEnabled(true);
    }
}

/**
 * Handle stop button (Bloomberg)
 */
function handleStop() {
    if (currentJobId) {
        fetch(`/api/jobs/${currentJobId}/cancel`, {
            method: 'POST',
            headers: Auth.getAuthHeaders(),
        })
        .then(() => {
            UIComponents.addLogEntry('Job cancelled', 'warning');
        })
        .catch(error => {
            console.error('Error cancelling job:', error);
        });
    }

    setFormEnabled(true);
}

/**
 * Handle CMECF form submission
 */
async function handleCMECFFormSubmit(event) {
    event.preventDefault();

    // Get case numbers
    const caseNumbers = getCaseNumbers();

    if (caseNumbers.length === 0) {
        alert('Please enter at least one case number');
        return;
    }

    // Show confirmation
    if (!showConfirmation()) {
        return;
    }

    // Reset UI
    UIComponents.reset();
    jobStats = { docsProcessed: 0, transcriptsFound: 0, transcriptsDownloaded: 0 };
    cmecfErrors = [];

    // Disable form
    setCMECFFormEnabled(false);

    UIComponents.addLogEntry(`Starting CMECF scraping for ${caseNumbers.length} case(s)...`, 'info');

    try {
        // Get client ID from WebSocket
        const clientId = wsClient.clientId;

        if (!clientId) {
            throw new Error('WebSocket not connected. Please refresh the page.');
        }

        // Create job via REST API
        const response = await fetch('/api/cmecf/scrape/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...Auth.getAuthHeaders(),
            },
            body: JSON.stringify({
                case_numbers: caseNumbers,
                client_id: clientId
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Failed to create job');
        }

        const jobData = await response.json();
        currentJobId = jobData.job_id;

        UIComponents.addLogEntry(`CMECF job created: ${currentJobId}`, 'success');
        UIComponents.addLogEntry(`Processing ${caseNumbers.length} case number(s)`, 'info');

        // Show job summary panel
        document.getElementById('jobSummary').style.display = 'block';

    } catch (error) {
        console.error('Error creating CMECF job:', error);
        UIComponents.addLogEntry('Failed to create job: ' + error.message, 'error');
        setCMECFFormEnabled(true);
    }
}

/**
 * Handle CMECF stop button
 */
function handleCMECFStop() {
    if (currentJobId) {
        fetch(`/api/jobs/${currentJobId}/cancel`, {
            method: 'POST',
            headers: Auth.getAuthHeaders(),
        })
        .then(() => {
            UIComponents.addLogEntry('CMECF job cancelled', 'warning');
        })
        .catch(error => {
            console.error('Error cancelling job:', error);
        });
    }

    setCMECFFormEnabled(true);
}

/**
 * Enable/disable CMECF form
 */
function setCMECFFormEnabled(enabled) {
    const form = document.getElementById('cmecfForm');
    const inputs = form.querySelectorAll('input, button[type="submit"]');
    const startBtn = document.getElementById('cmecfStartBtn');
    const stopBtn = document.getElementById('cmecfStopBtn');

    inputs.forEach(input => {
        input.disabled = !enabled;
    });

    if (enabled) {
        startBtn.style.display = 'block';
        stopBtn.style.display = 'none';
    } else {
        startBtn.style.display = 'none';
        stopBtn.style.display = 'block';
    }
}

/**
 * Add error to CMECF error list
 */
function addCMECFError(caseNumber, docNumber, message) {
    cmecfErrors.push({
        case_number: caseNumber,
        doc_number: docNumber,
        error: message,
        timestamp: new Date().toISOString()
    });

    // Show error panel
    const errorPanel = document.getElementById('errorReportPanel');
    const errorList = document.getElementById('errorList');

    errorPanel.style.display = 'block';

    const errorItem = document.createElement('div');
    errorItem.className = 'error-item';
    errorItem.innerHTML = `
        <div class="error-item-case">${caseNumber} #${docNumber}</div>
        <div class="error-item-message">${message}</div>
    `;
    errorList.appendChild(errorItem);
}

/**
 * Download error report as CSV
 */
function downloadErrorReport() {
    if (cmecfErrors.length === 0) {
        alert('No errors to report');
        return;
    }

    // Create CSV content
    let csvContent = 'Case Number,Document Number,Error,Timestamp\n';
    cmecfErrors.forEach(error => {
        csvContent += `"${error.case_number}","${error.doc_number}","${error.error}","${error.timestamp}"\n`;
    });

    // Download
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cmecf_errors_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/**
 * Handle WebSocket messages
 */
function handleWebSocketMessage(data) {
    const messageType = data.type;
    
    switch (messageType) {
        case 'STATE_CHANGE':
            UIComponents.updateState(data.state, data.message);
            UIComponents.addLogEntry(data.message, 'info');
            break;
        
        case 'COURT_SELECTION':
            UIComponents.showCourtSelection(data);
            UIComponents.addLogEntry('Waiting for court selection...', 'warning');
            break;
        
        case 'TRANSCRIPT_OPTIONS':
            UIComponents.showTranscriptSelection(data);
            UIComponents.addLogEntry(`Found ${data.entries.length} transcript entries`, 'info');
            jobStats.transcriptsFound += data.entries.length;
            UIComponents.updateJobSummary(
                jobStats.docsProcessed,
                jobStats.transcriptsFound,
                jobStats.transcriptsDownloaded
            );
            break;
        
        case 'PROGRESS':
            if (data.current && data.total) {
                UIComponents.updateProgress(data.current, data.total, data.percentage);
            }
            UIComponents.addLogEntry(data.message, 'info');
            break;
        
        case 'DOWNLOAD_SUCCESS':
            UIComponents.addDownloadedFile(data.filename || data.data?.filename, data.entry_num || data.data?.entry_num);
            UIComponents.addLogEntry(`Downloaded: ${data.filename || data.data?.filename}`, 'success');
            jobStats.transcriptsDownloaded++;
            UIComponents.updateJobSummary(
                jobStats.docsProcessed,
                jobStats.transcriptsFound,
                jobStats.transcriptsDownloaded
            );
            break;
        
        case 'DOWNLOAD_FAILED':
            UIComponents.addLogEntry(`Download failed: ${data.message}`, 'error');
            break;
        
        case 'INFO':
            UIComponents.addLogEntry(data.message, 'info');
            break;
        
        case 'WARNING':
            UIComponents.addLogEntry(data.message, 'warning');
            break;
        
        case 'ERROR':
            UIComponents.addLogEntry(data.message, 'error');
            UIComponents.showError(data.message, data.details);
            setFormEnabled(true);
            break;
        
        case 'COMPLETE':
            UIComponents.addLogEntry('Scraping completed!', 'success');
            UIComponents.showCompletion(data.data || {});
            // Re-enable the appropriate form
            if (window.currentScraper === 'cmecf') {
                setCMECFFormEnabled(true);
            } else {
                setFormEnabled(true);
            }
            break;

        case 'NO_TRANSCRIPTS':
            UIComponents.addLogEntry(`No transcripts found in: ${data.document}`, 'warning');
            break;

        // CMECF-specific events
        case 'CMECF_ERROR':
            addCMECFError(data.case_number, data.doc_number, data.error);
            UIComponents.addLogEntry(`Error: ${data.case_number} #${data.doc_number}: ${data.error}`, 'error');
            break;

        default:
            console.log('Unknown message type:', messageType, data);

            // Handle generic event with data containing type
            if (data.data && data.data.type === 'DOWNLOAD_SUCCESS') {
                UIComponents.addDownloadedFile(data.data.filename, data.data.doc_number || data.data.entry_num);
                UIComponents.addLogEntry(`Downloaded: ${data.data.filename}`, 'success');
                jobStats.transcriptsDownloaded++;
                UIComponents.updateJobSummary(
                    jobStats.docsProcessed,
                    jobStats.transcriptsFound,
                    jobStats.transcriptsDownloaded
                );
            }
    }
}

/**
 * Enable/disable form
 */
function setFormEnabled(enabled) {
    const form = document.getElementById('searchForm');
    const inputs = form.querySelectorAll('input, button[type="submit"]');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    
    inputs.forEach(input => {
        input.disabled = !enabled;
    });
    
    if (enabled) {
        startBtn.style.display = 'block';
        stopBtn.style.display = 'none';
    } else {
        startBtn.style.display = 'none';
        stopBtn.style.display = 'block';
    }
}

/**
 * Bootstrap: check auth, then show login or app
 */
window.addEventListener('DOMContentLoaded', async () => {
    const ok = await Auth.checkAuth();
    if (ok) {
        Auth.showApp();
        initApp();
    } else {
        Auth.showLogin();
        setupLoginForm();
    }
});

/**
 * Clean up on page unload
 */
window.addEventListener('beforeunload', () => {
    if (wsClient) {
        wsClient.disconnect();
    }
});