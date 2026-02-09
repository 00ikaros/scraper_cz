/**
 * UI Components and Rendering Functions
 */

const UIComponents = {
    
    /**
     * Update connection status indicator
     */
    updateConnectionStatus(isConnected) {
        const indicator = document.getElementById('statusIndicator');
        const text = document.getElementById('statusText');
        
        if (isConnected) {
            indicator.classList.add('connected');
            indicator.classList.remove('error');
            text.textContent = 'Connected';
        } else {
            indicator.classList.remove('connected');
            indicator.classList.add('error');
            text.textContent = 'Disconnected';
        }
    },
    
    /**
     * Update current state display
     */
    updateState(state, message) {
        const stateElement = document.getElementById('currentState');
        const messageElement = document.getElementById('statusMessage');

        // State classes for color coding
        const stateClasses = {
            'idle': 'state-idle',
            'initializing': 'state-active',
            'logging_in': 'state-active',
            'searching': 'state-active',
            'awaiting_court_selection': 'state-waiting',
            'processing_results': 'state-active',
            'navigating_to_document': 'state-active',
            'extracting_entries': 'state-active',
            'awaiting_transcript_selection': 'state-waiting',
            'downloading': 'state-active',
            'returning_to_results': 'state-active',
            'completed': 'state-success',
            'error': 'state-error',
            'cancelled': 'state-cancelled'
        };

        const stateClass = stateClasses[state] || 'state-idle';
        const stateText = state.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

        stateElement.className = `current-state ${stateClass}`;
        stateElement.innerHTML = `
            <span class="state-indicator"></span>
            <span class="state-text">${stateText}</span>
        `;

        messageElement.textContent = message || 'Processing...';
    },
    
    /**
     * Update progress bar
     */
    updateProgress(current, total, percentage) {
        const container = document.getElementById('progressContainer');
        const fill = document.getElementById('progressFill');
        const text = document.getElementById('progressText');
        
        if (current !== null && total !== null) {
            container.style.display = 'block';
            const percent = percentage || Math.round((current / total) * 100);
            fill.style.width = `${percent}%`;
            text.textContent = `${current}/${total} (${percent}%)`;
        } else {
            container.style.display = 'none';
        }
    },
    
    /**
     * Add log entry
     */
    addLogEntry(message, type = 'info') {
        const log = document.getElementById('activityLog');
        const time = new Date().toLocaleTimeString();
        
        const entry = document.createElement('div');
        entry.className = `log-entry log-${type}`;
        entry.innerHTML = `
            <span class="log-time">${time}</span>
            <span class="log-message">${message}</span>
        `;
        
        log.appendChild(entry);
        
        // Auto-scroll to bottom
        log.scrollTop = log.scrollHeight;
        
        // Limit log entries to 50
        const entries = log.querySelectorAll('.log-entry');
        if (entries.length > 50) {
            entries[0].remove();
        }
    },
    
    /**
     * Show court selection interface
     */
    showCourtSelection(data) {
        const panel = document.getElementById('interactionPanel');
        const title = document.getElementById('interactionTitle');
        const content = document.getElementById('interactionContent');
        
        panel.style.display = 'block';
        title.textContent = 'Select Court';
        
        let html = `
            <p><strong>You searched for:</strong> "${data.user_input}"</p>
            <p style="margin: 12px 0; color: var(--text-secondary);">
                ${data.message || 'Please select the correct court from the options below:'}
            </p>
        `;
        
        // Exact matches first
        if (data.exact_matches && data.exact_matches.length > 0) {
            html += '<h4 style="margin: 16px 0 8px 0;">Exact Matches:</h4>';
            html += '<div class="court-options">';
            data.exact_matches.forEach((court, index) => {
                html += `
                    <div class="option-item highlight" data-court="${court}" onclick="UIComponents.selectCourt('${court.replace(/'/g, "\\'")}')">
                        ${court}
                    </div>
                `;
            });
            html += '</div>';
        }
        
        // Fuzzy matches
        if (data.fuzzy_matches && data.fuzzy_matches.length > 0) {
            html += '<h4 style="margin: 16px 0 8px 0;">Similar Matches:</h4>';
            html += '<div class="court-options">';
            data.fuzzy_matches.forEach((court, index) => {
                html += `
                    <div class="option-item" data-court="${court}" onclick="UIComponents.selectCourt('${court.replace(/'/g, "\\'")}')">
                        ${court}
                    </div>
                `;
            });
            html += '</div>';
        }
        
        // All other options
        if (data.options && data.options.length > 0) {
            const otherOptions = data.options.filter(opt =>
                !data.exact_matches?.includes(opt) &&
                !data.fuzzy_matches?.includes(opt)
            );

            if (otherOptions.length > 0) {
                html += '<h4 style="margin: 16px 0 8px 0;">All Options:</h4>';
                html += '<div class="court-options">';
                otherOptions.forEach((court, index) => {
                    html += `
                        <div class="option-item" data-court="${court}" onclick="UIComponents.selectCourt('${court.replace(/'/g, "\\'")}')">
                            ${court}
                        </div>
                    `;
                });
                html += '</div>';
            }
        }

        // Add Skip button for manual workflow
        html += `
            <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color);">
                <button class="btn btn-secondary" onclick="UIComponents.skipCourtSelection()" style="width: 100%;">
                    Skip - I Already Selected the Court Manually
                </button>
                <small style="display: block; margin-top: 8px; color: var(--text-secondary); text-align: center;">
                    Use this if you've already selected the court in the browser window
                </small>
            </div>
        `;

        content.innerHTML = html;
    },
    
    /**
     * Handle court selection
     */
    selectCourt(courtName) {
        // Highlight selected
        document.querySelectorAll('.option-item').forEach(item => {
            item.classList.remove('selected');
        });

        const selected = document.querySelector(`[data-court="${courtName}"]`);
        if (selected) {
            selected.classList.add('selected');
        }

        // Send selection to backend
        if (window.wsClient) {
            window.wsClient.sendUserResponse({
                action: 'select_court',
                selected_court: courtName
            });
        }

        // Hide interaction panel
        document.getElementById('interactionPanel').style.display = 'none';

        UIComponents.addLogEntry(`Selected court: ${courtName}`, 'success');
    },

    /**
     * Skip court selection (user already selected manually)
     */
    skipCourtSelection() {
        // Send skip signal to backend
        if (window.wsClient) {
            window.wsClient.sendUserResponse({
                action: 'skip_court_selection',
                selected_court: '__SKIP__'
            });
        }

        // Hide interaction panel
        document.getElementById('interactionPanel').style.display = 'none';

        UIComponents.addLogEntry('Skipped court selection (manual selection)', 'info');
    },
    
    /**
     * Show transcript selection interface
     */
    showTranscriptSelection(data) {
        const panel = document.getElementById('interactionPanel');
        const title = document.getElementById('interactionTitle');
        const content = document.getElementById('interactionContent');
        
        panel.style.display = 'block';
        title.textContent = 'Select Entries to Download';

        const patternMatches = data.entries.filter(e => e.matches_pattern).length;
        const patternInfo = patternMatches > 0
            ? ` (${patternMatches} match${patternMatches === 1 ? 'es' : ''} pattern)`
            : '';

        let html = `
            <p><strong>Document:</strong> ${data.document_title}</p>
            <p><strong>Progress:</strong> ${data.document_index} / ${data.total_documents}</p>
            <p style="margin: 12px 0; color: var(--text-secondary);">
                Found ${data.entries.length} downloadable ${data.entries.length === 1 ? 'entry' : 'entries'}${patternInfo}.
                Select which to download:
            </p>
            <div class="transcript-options">
        `;
        
        data.entries.forEach((entry, index) => {
            const matchClass = entry.matches_pattern ? 'matches' : '';
            const downloadBadge = entry.has_download 
                ? '<span class="badge badge-success">Downloadable</span>' 
                : '<span class="badge badge-warning">No PDF</span>';
            
            html += `
                <div class="transcript-entry ${matchClass}" data-index="${index}">
                    <div class="transcript-header">
                        <div>
                            <strong>Entry ${entry.entry_num}</strong>
                            ${entry.matches_pattern ? '<span class="badge badge-success">Pattern match</span>' : '<span class="badge badge-muted">No pattern match</span>'}
                            ${downloadBadge}
                        </div>
                        <input type="checkbox" 
                               class="transcript-checkbox" 
                               data-index="${index}" 
                               ${entry.has_download ? 'checked' : 'disabled'}
                               onchange="UIComponents.toggleTranscript(${index})">
                    </div>
                    <div class="transcript-meta">
                        <span> Filed: ${entry.filed_date}</span>
                    </div>
                    <div class="transcript-description">
                        ${entry.description}
                    </div>
                </div>
            `;
        });
        
        html += `
            </div>
            <div class="action-buttons">
                <button class="btn btn-success" onclick="UIComponents.downloadSelectedTranscripts()">
                    ⬇️ Download Selected
                </button>
                <button class="btn btn-primary" onclick="UIComponents.downloadAllTranscripts()">
                    ⬇️ Download All
                </button>
                <button class="btn btn-secondary" onclick="UIComponents.skipDocument()">
                    ⏭️ Skip Document
                </button>
            </div>
        `;
        
        content.innerHTML = html;
        
        // Store data for later use
        window.currentTranscriptData = data;
    },
    
    /**
     * Toggle transcript checkbox
     */
    toggleTranscript(index) {
        // Just update the checkbox state
        console.log(`Transcript ${index} toggled`);
    },
    
    /**
     * Download selected transcripts
     */
    downloadSelectedTranscripts() {
        const checkboxes = document.querySelectorAll('.transcript-checkbox:checked');
        const selectedIndices = Array.from(checkboxes).map(cb => parseInt(cb.dataset.index));
        
        if (selectedIndices.length === 0) {
            alert('Please select at least one transcript to download');
            return;
        }
        
        if (window.wsClient) {
            window.wsClient.sendUserResponse({
                action: 'download_selected',
                selected_indices: selectedIndices
            });
        }
        
        document.getElementById('interactionPanel').style.display = 'none';
        UIComponents.addLogEntry(`Downloading ${selectedIndices.length} selected transcripts`, 'info');
    },
    
    /**
     * Download all transcripts
     */
    downloadAllTranscripts() {
        if (window.wsClient) {
            window.wsClient.sendUserResponse({
                action: 'download_all'
            });
        }
        
        document.getElementById('interactionPanel').style.display = 'none';
        UIComponents.addLogEntry('Downloading all transcripts', 'info');
    },
    
    /**
     * Skip current document
     */
    skipDocument() {
        if (window.wsClient) {
            window.wsClient.sendUserResponse({
                action: 'skip'
            });
        }
        
        document.getElementById('interactionPanel').style.display = 'none';
        UIComponents.addLogEntry('Skipped document', 'warning');
    },
    
    /**
     * Add downloaded file to list
     */
    addDownloadedFile(filename, entryNum) {
        const panel = document.getElementById('downloadsPanel');
        const list = document.getElementById('downloadsList');
        
        panel.style.display = 'block';
        
        const item = document.createElement('div');
        item.className = 'download-item';
        item.innerHTML = `
            <div>
                <div class="download-filename">${filename}</div>
                <small class="download-entry-meta">Entry ${entryNum}</small>
            </div>
            <span class="download-status">Downloaded</span>
        `;
        
        list.appendChild(item);
        
        // Auto-scroll
        list.scrollTop = list.scrollHeight;
    },
    
    /**
     * Update job summary stats
     */
    updateJobSummary(docsProcessed, transcriptsFound, transcriptsDownloaded) {
        const summary = document.getElementById('jobSummary');
        summary.style.display = 'block';
        
        document.getElementById('docsProcessed').textContent = docsProcessed || 0;
        document.getElementById('transcriptsFound').textContent = transcriptsFound || 0;
        document.getElementById('transcriptsDownloaded').textContent = transcriptsDownloaded || 0;
    },
    
    /**
     * Show completion message
     */
    showCompletion(summary) {
        const panel = document.getElementById('interactionPanel');
        const title = document.getElementById('interactionTitle');
        const content = document.getElementById('interactionContent');
        
        panel.style.display = 'block';
        title.textContent = 'Scraping complete';
        
        content.innerHTML = `
            <div class="completion-content">
                <h3 class="completion-heading">Job completed</h3>
                <div class="summary-stats">
                    <div class="stat">
                        <span class="stat-label">Documents</span>
                        <span class="stat-value">${summary.documents_processed || 0}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Downloads</span>
                        <span class="stat-value">${summary.transcripts_downloaded || 0}</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Duration</span>
                        <span class="stat-value">${this.formatDuration(summary.duration)}</span>
                    </div>
                </div>
                <button class="btn btn-primary completion-action" onclick="location.reload()">Start new job</button>
            </div>
        `;
    },
    
    /**
     * Show error message
     */
    showError(message, details) {
        const panel = document.getElementById('interactionPanel');
        const title = document.getElementById('interactionTitle');
        const content = document.getElementById('interactionContent');
        
        panel.style.display = 'block';
        title.textContent = 'Error';
        
        content.innerHTML = `
            <div class="error-content">
                <h3 class="error-heading">Something went wrong</h3>
                <p class="error-message">${message}</p>
                ${details ? `<pre class="error-details">${JSON.stringify(details, null, 2)}</pre>` : ''}
                <button class="btn btn-primary completion-action" onclick="location.reload()">Restart</button>
            </div>
        `;
    },
    
    /**
     * Format duration in seconds
     */
    formatDuration(seconds) {
        if (!seconds) return '--';
        
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        
        if (minutes === 0) {
            return `${secs}s`;
        }
        return `${minutes}m ${secs}s`;
    },
    
    /**
     * Reset UI to initial state
     */
    reset() {
        document.getElementById('progressContainer').style.display = 'none';
        document.getElementById('interactionPanel').style.display = 'none';
        document.getElementById('jobSummary').style.display = 'none';
        document.getElementById('downloadsPanel').style.display = 'none';
        document.getElementById('downloadsList').innerHTML = '';
        
        this.updateState('idle', 'Ready to start scraping...');
        this.updateProgress(null, null, null);
    }
};