// ============================================================
// NHAI Email Automation Portal - main.js
// ============================================================

// Quill rich text editor
const quill = new Quill('#editor', {
    theme: 'snow',
    placeholder: 'Write your email body here... Use {{ColumnName}} for personalization.',
    modules: {
        toolbar: [
            [{ 'header': [1, 2, 3, false] }],
            ['bold', 'italic', 'underline'],
            [{ 'list': 'ordered' }, { 'list': 'bullet' }],
            ['link', 'clean']
        ]
    }
});

let statusPollingInterval = null;
let lastLogCount = 0;
let allCampaignLogs = [];


// ============================================================
// On Page Load - Check Gmail Auth Status
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    checkAuthStatus();
});

function checkAuthStatus() {
    fetch('/auth-status')
        .then(r => r.json())
        .then(data => {
            const statusText = document.getElementById('authStatusText');
            const emailText = document.getElementById('authEmailText');
            const statusIcon = document.getElementById('authStatusIcon');
            const authorizeBtn = document.getElementById('authorizeBtn');

            if (data.authorized) {
                statusText.innerHTML = '<span class="text-success">✓ Gmail Connected</span>';
                emailText.textContent = data.email || '';
                statusIcon.textContent = '✅';
                authorizeBtn.textContent = '🔄 Reconnect Gmail';
                authorizeBtn.classList.remove('btn-outline-warning');
                authorizeBtn.classList.add('btn-outline-success');
            } else {
                statusText.innerHTML = '<span class="text-danger">✗ Not Connected</span>';
                emailText.textContent = 'Click below to authorize';
                statusIcon.textContent = '❌';
            }
        })
        .catch(() => {
            document.getElementById('authStatusText').innerHTML =
                '<span class="text-warning">⚠ Could not check status</span>';
        });
}


// ============================================================
// Gmail Authorize Button
// ============================================================

document.getElementById('authorizeBtn').addEventListener('click', function () {
    window.location.href = '/authorize';
});


// ============================================================
// Recipient File Upload
// ============================================================

document.getElementById('recipientFile').addEventListener('change', function () {
    const file = this.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('recipient_file', file);

    fetch('/validate-recipients', {
        method: 'POST',
        body: formData
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                // Show recipient info
                document.getElementById('recipientInfo').classList.remove('d-none');
                document.getElementById('recipientCount').textContent =
                    data.recipient_count + ' Recipients';
                document.getElementById('uploadedFileName').textContent = file.name;

                // Show variables
                if (data.columns && data.columns.length > 0) {
                    document.getElementById('variablesSection').classList.remove('d-none');
                    const varList = document.getElementById('variablesList');
                    varList.innerHTML = '';
                    data.columns.forEach(col => {
                        const badge = document.createElement('span');
                        badge.className = 'badge border me-1 mb-1 variable-badge';
                        badge.style.cursor = 'pointer';
                        badge.textContent = `{{${col}}}`;
                        badge.title = 'Click to copy';
                        badge.addEventListener('click', function () {
                            const variable = `{{${col}}}`;
                            const selection = quill.getSelection();
                            if (selection) {
        // Cursor body mein hai - wahan insert karo
                                quill.insertText(selection.index, variable);
                                quill.focus();
                                quill.setSelection(selection.index + variable.length);
                            } else {
        // Cursor body mein nahi hai - end mein insert karo
                                const length = quill.getLength();
                                quill.insertText(length - 1, variable);
                                quill.focus();
                                quill.setSelection(length - 1 + variable.length);
                            }
    // Focus back to editor
                            
});
                        varList.appendChild(badge);
                    });
                }
            } else {
                alert('Error: ' + data.error);
                this.value = '';
                document.getElementById('recipientInfo').classList.add('d-none');
                document.getElementById('variablesSection').classList.add('d-none');
            }
        })
        .catch(err => {
            alert('Failed to validate file: ' + err);
        });
});


// ============================================================
// Preview Button
// ============================================================

document.getElementById('previewBtn').addEventListener('click', function () {
    const subject = document.getElementById('subject').value;
    const body = quill.root.innerHTML;
    const recipientFile = document.getElementById('recipientFile').files[0];

    if (!recipientFile) {
        alert('Please upload a recipient Excel file first.');
        return;
    }

    const formData = new FormData();
    formData.append('subject', subject);
    formData.append('body', body);
    formData.append('recipient_file', recipientFile);

    fetch('/preview', {
        method: 'POST',
        body: formData
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                document.getElementById('previewContent').innerHTML = `
                    <div class="mb-3">
                        <span class="text-muted small">To:</span>
                        <strong> ${data.recipient}</strong>
                        <span class="ms-3 text-muted small">(1 of ${data.total_recipients} recipients)</span>
                    </div>
                    <div class="mb-2">
                        <span class="text-muted small">Subject:</span>
                        <strong> ${data.subject}</strong>
                    </div>
                    <hr style="border-color:#444">
                    <div style="background:#ffffff; padding:16px; border-radius:8px; line-height:1.6;">
                        ${data.body}
                    </div>
                `;
                new bootstrap.Modal(
                    document.getElementById('previewModal')
                ).show();
            } else {
                alert('Preview error: ' + data.error);
            }
        })
        .catch(err => alert('Failed to load preview: ' + err));
});


// ============================================================
// Send Button
// ============================================================

document.getElementById('sendBtn').addEventListener('click', function () {
    const subject = document.getElementById('subject').value.trim();
    const body = quill.root.innerHTML.trim();
    const recipientFile = document.getElementById('recipientFile').files[0];

    if (!subject) {
        alert('Please enter a subject.');
        return;
    }

    if (!recipientFile) {
        alert('Please upload a recipient Excel file.');
        return;
    }

    if (!confirm(`Are you sure you want to send this campaign?`)) return;

    const formData = new FormData();
    formData.append('subject', subject);
    formData.append('body', body);
    formData.append('recipient_file', recipientFile);

    const attachments = document.getElementById('attachments').files;
    for (let i = 0; i < attachments.length; i++) {
        formData.append('attachments', attachments[i]);
    }

    fetch('/send', {
        method: 'POST',
        body: formData
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                showStatusSection();
                startPolling();
            } else {
                alert('Error: ' + data.message);
            }
        })
        .catch(err => alert('Failed to start campaign: ' + err));
});


// ============================================================
// Show status section
// ============================================================

function showStatusSection() {
    document.getElementById('statusSection').classList.remove('d-none');
    document.getElementById('copyFailedSection').classList.add('d-none');
    document.getElementById('campaignLogs').innerHTML =
        '<div class="log-entry log-info">> Campaign starting...</div>';
    lastLogCount = 0;
    allCampaignLogs = [];
}


// ============================================================
// Status Polling
// ============================================================

function startPolling() {
    if (statusPollingInterval) clearInterval(statusPollingInterval);
    statusPollingInterval = setInterval(pollStatus, 1500);
}

function pollStatus() {
    fetch('/status')
        .then(r => r.json())
        .then(data => {
            updateStatusUI(data);
            allCampaignLogs = data.logs || [];

            if (!data.running) {
                clearInterval(statusPollingInterval);
                statusPollingInterval = null;

                // Show copy failed button if there are failures
                const failedLogs = (data.logs || []).filter(
                    l => l.status === 'failed' && l.recipient !== 'System'
                );
                if (failedLogs.length > 0) {
                    document.getElementById('copyFailedSection').classList.remove('d-none');
                }
            }
        })
        .catch(err => console.error('Poll error:', err));
}

function updateStatusUI(data) {
    const total = data.total || 0;
    const sent = data.sent || 0;
    const failed = data.failed || 0;
    const running = data.running;

    // Stats
    document.getElementById('statTotal').textContent = total;
    document.getElementById('statSent').textContent = sent;
    document.getElementById('statFailed').textContent = failed;

// Make stats clickable
    document.getElementById('statTotal').onclick = () => showEmailList('all', data.logs);
    document.getElementById('statSent').onclick = () => showEmailList('sent', data.logs);
    document.getElementById('statFailed').onclick = () => showEmailList('failed', data.logs);

    // Progress bar
    const progress = total > 0 ? Math.round(((sent + failed) / total) * 100) : 0;
    document.getElementById('campaignProgressBar').style.width = progress + '%';
    document.getElementById('progressPercentage').textContent = progress + '%';

    // Status badge
    const badge = document.getElementById('campaignStatusText');
    if (running) {
        badge.className = 'badge bg-primary';
        badge.textContent = 'Running';
    } else if (failed === 0 && sent > 0) {
        badge.className = 'badge bg-success';
        badge.textContent = 'Finished ✓';
    } else if (sent === 0 && failed > 0) {
        badge.className = 'badge bg-danger';
        badge.textContent = 'Failed';
    } else {
        badge.className = 'badge bg-warning text-dark';
        badge.textContent = 'Finished';
    }

    // Append new logs only
    const logs = data.logs || [];
    if (logs.length > lastLogCount) {
        const logContainer = document.getElementById('campaignLogs');
        for (let i = lastLogCount; i < logs.length; i++) {
            const log = logs[i];
            const entry = document.createElement('div');

            let cssClass = 'log-entry ';
            if (log.status === 'sent') cssClass += 'log-success';
            else if (log.status === 'failed') cssClass += 'log-error';
            else cssClass += 'log-info';

            let icon = log.status === 'sent' ? '✓' : log.status === 'failed' ? '✗' : '>';
            let text = `[${log.time}] ${icon} ${log.recipient}`;
            if (log.error) text += ` - ${log.error}`;

            entry.className = cssClass;
            entry.textContent = text;
            logContainer.appendChild(entry);
        }
        logContainer.scrollTop = logContainer.scrollHeight;
        lastLogCount = logs.length;
    }
}


// ============================================================
// Copy Failed Emails Button
// ============================================================

document.getElementById('copyFailedBtn').addEventListener('click', function () {
    const failedEmails = allCampaignLogs
        .filter(l => l.status === 'failed' && l.recipient !== 'System')
        .map(l => l.recipient)
        .join('\n');

    if (!failedEmails) {
        alert('No failed emails found.');
        return;
    }

    navigator.clipboard.writeText(failedEmails).then(() => {
        const fb = document.getElementById('copyFeedback');
        fb.classList.remove('d-none');
        setTimeout(() => fb.classList.add('d-none'), 2500);
    }).catch(() => {
        // Fallback for browsers that block clipboard
        const textarea = document.createElement('textarea');
        textarea.value = failedEmails;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);

        const fb = document.getElementById('copyFeedback');
        fb.classList.remove('d-none');
        setTimeout(() => fb.classList.add('d-none'), 2500);
    });
});
function showEmailList(type, logs) {
    if (!logs || logs.length === 0) return;

    let filtered = logs.filter(l => l.recipient !== 'System');
    if (type === 'sent') filtered = filtered.filter(l => l.status === 'sent');
    if (type === 'failed') filtered = filtered.filter(l => l.status === 'failed');

    if (filtered.length === 0) {
        alert('No emails in this category.');
        return;
    }

    const title = type === 'all' ? 'All Recipients' :
                  type === 'sent' ? 'Sent Emails' : 'Failed Emails';

    const emailList = filtered.map(l => {
        const icon = l.status === 'sent' ? '✓' : '✗';
        const error = l.error ? ` — ${l.error}` : '';
        return `<div class="py-1 border-bottom" style="font-size:13px;">
            <span class="${l.status === 'sent' ? 'text-success' : 'text-danger'}">${icon}</span>
            <span class="ms-2">${l.recipient}</span>
            ${error ? `<span class="text-muted">${error}</span>` : ''}
        </div>`;
    }).join('');

    const copyBtn = type !== 'all' ? `
        <button class="btn btn-sm btn-outline-secondary" onclick="
            navigator.clipboard.writeText('${filtered.map(l => l.recipient).join('\\n')}');
            this.textContent='Copied!';
            setTimeout(()=>this.textContent='Copy Emails',1500);
        ">Copy Emails</button>` : '';

    document.getElementById('previewContent').innerHTML = `
        <h6 class="mb-3">${title} (${filtered.length})</h6>
        ${copyBtn}
        <div class="mt-3" style="max-height:400px; overflow-y:auto;">
            ${emailList}
        </div>
    `;

    new bootstrap.Modal(document.getElementById('previewModal')).show();
}