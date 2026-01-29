// File: static/js/doctor_engine.js

const app = {
    // --- STATE ---
    currentView: 'dashboard',
    finalMeds: [],
    
    // --- NAVIGATION ---
    navTo: (viewId) => {
        document.querySelectorAll('.view-container').forEach(el => el.classList.remove('active'));
        document.getElementById(`view-${viewId}`).classList.add('active');
        document.getElementById('pageTitle').innerText = viewId === 'dashboard' ? 'Command Center' : 'My Profile';
    },

    loadPatient: (id) => {
        app.navTo('workspace');
        document.getElementById('pageTitle').innerText = `Patient #${id} Workspace`;
    },

    switchTab: (tabId) => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        // Find button by text roughly or add IDs to buttons. 
        // For simplicity, relying on order or just setting active class on click target in HTML
        event.target.classList.add('active'); 
        document.getElementById(`tab-${tabId}`).classList.add('active');
    },

    // --- DYNAMIC "POPPING" REQUESTS (Simulation) ---
    initDynamicRequests: () => {
        const potentialRequests = [
            { name: "Mike Ross", issue: "Severe Migraine", id: "105" },
            { name: "Rachel Green", issue: "High Fever", id: "106" },
            { name: "Harvey S.", issue: "Palpitations", id: "107" }
        ];

        // "Pop" a new request every 15-30 seconds
        setInterval(() => {
            const req = potentialRequests[Math.floor(Math.random() * potentialRequests.length)];
            app.showToast(`New Request: ${req.name}`, req.issue, 'e911_emergency');
            
            // Also add to sidebar
            const list = document.getElementById('triageList');
            const item = document.createElement('div');
            item.className = 'sidebar-file-item';
            item.innerHTML = `
                <span class="material-symbols-rounded file-icon-small" style="color:#ea8600">person_add</span>
                <div class="file-name-small"><strong>${req.name}</strong><div style="font-size:10px">${req.issue} • Just now</div></div>
            `;
            item.onclick = () => app.loadPatient(req.id);
            // Insert at top
            list.insertBefore(item, list.firstChild);
            
            // Animation
            item.style.animation = "fadeIn 0.5s";
        }, 15000); 
    },

    showToast: (title, msg, icon) => {
        const stack = document.getElementById('toastStack');
        const toast = document.createElement('div');
        toast.className = 'toast-card';
        toast.innerHTML = `
            <span class="material-symbols-rounded" style="color:#0b57d0; font-size:24px;">${icon}</span>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-msg">${msg}</div>
            </div>
        `;
        stack.appendChild(toast);
        setTimeout(() => toast.classList.add('show'), 100);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 500);
        }, 5000);
        
        // Play notification sound if desired
    },

    // --- AI CONSULT CHAT ---
    sendAiConsult: () => {
        const input = document.getElementById('aiConsultInput');
        const text = input.value;
        if(!text) return;
        
        const log = document.getElementById('aiConsultLog');
        
        // 1. Add Doc Msg
        log.innerHTML += `
            <div class="doc-msg-row">
                <div class="doc-bubble">${text}</div>
            </div>`;
        
        input.value = "";
        
        // 2. Simulate Thinking
        const loadingId = Date.now();
        log.innerHTML += `
            <div class="ai-msg-row" id="loading-${loadingId}">
                <div class="ai-avatar"><span class="material-symbols-rounded">smart_toy</span></div>
                <div class="ai-bubble" style="color:#666; font-style:italic;">Scanning patient history...</div>
            </div>`;
        log.scrollTop = log.scrollHeight;

        // 3. Simulate Response
        setTimeout(() => {
            document.getElementById(`loading-${loadingId}`).remove();
            let response = "Based on the logs, the patient has no known allergies. However, he mentioned taking Ibuprofen yesterday.";
            
            if(text.toLowerCase().includes("timeline")) response = "Timeline: <br>• 2 days ago: Mild pain.<br>• Yesterday: Took meds.<br>• Today: Pain 8/10.";
            
            log.innerHTML += `
                <div class="ai-msg-row">
                    <div class="ai-avatar"><span class="material-symbols-rounded">smart_toy</span></div>
                    <div class="ai-bubble">${response}</div>
                </div>`;
            log.scrollTop = log.scrollHeight;
        }, 1500);
    },
    
    quickAsk: (txt) => {
        document.getElementById('aiConsultInput').value = txt;
        app.sendAiConsult();
    },

    // --- MED RECOMMENDER ---
    rxAccept: (elId, name, dose) => {
        // Add to final list
        app.finalMeds.push({name, dose});
        app.renderFinalRx();
        
        // Remove suggestion visually
        document.getElementById(elId).style.opacity = '0.5';
        document.getElementById(elId).style.pointerEvents = 'none';
        document.querySelector(`#${elId} .rx-actions`).innerHTML = '<span style="color:green; font-weight:600;">Accepted</span>';
    },
    
    rxReject: (elId) => {
        document.getElementById(elId).style.display = 'none';
    },

    rxEdit: (elId) => {
        const name = document.querySelector(`#${elId} .rx-name`).innerText;
        const dose = document.querySelector(`#${elId} .rx-dose`).innerText.split('•')[0].trim();
        document.getElementById('manualDrug').value = name;
        document.getElementById('manualDose').value = dose;
        document.getElementById(elId).style.display = 'none'; // Hide suggestion so they add manual
    },

    addManualRx: () => {
        const n = document.getElementById('manualDrug').value;
        const d = document.getElementById('manualDose').value;
        if(n && d) {
            app.finalMeds.push({name: n, dose: d});
            app.renderFinalRx();
            document.getElementById('manualDrug').value = '';
            document.getElementById('manualDose').value = '';
        }
    },

    renderFinalRx: () => {
        const container = document.getElementById('finalRxList');
        if(app.finalMeds.length === 0) {
            container.innerHTML = `<div style="text-align:center; color:var(--text-sub);">No meds added</div>`;
            return;
        }
        container.innerHTML = app.finalMeds.map((m, i) => `
            <div style="display:flex; justify-content:space-between; border-bottom:1px solid #eee; padding:8px 0;">
                <div><strong>${m.name}</strong> <span style="color:#666">${m.dose}</span></div>
                <span class="material-symbols-rounded" style="color:red; cursor:pointer; font-size:16px;" onclick="app.removeFinalRx(${i})">delete</span>
            </div>
        `).join('');
    },
    
    removeFinalRx: (idx) => {
        app.finalMeds.splice(idx, 1);
        app.renderFinalRx();
    },

    // --- REPORT GENERATION ---
    generateReportPreview: () => {
        const notes = document.getElementById('clinicalNoteInput').value;
        const meds = app.finalMeds.map(m => `<li>${m.name} - ${m.dose}</li>`).join('');
        
        const html = `
            <h3>Clinical Encounter Report</h3>
            <p><strong>Patient:</strong> John Doe (ID #101)</p>
            <p><strong>Date:</strong> ${new Date().toLocaleDateString()}</p>
            <hr>
            <h4>Clinical Notes</h4>
            <div style="white-space: pre-wrap;">${notes}</div>
            <hr>
            <h4>Prescription Plan</h4>
            <ul>${meds || '<li>No medications prescribed.</li>'}</ul>
            <br>
            <p><em>Signed electronically by Dr. Smith</em></p>
        `;
        
        document.getElementById('reportContent').innerHTML = html;
        document.getElementById('reportModal').style.display = 'flex';
    },

    printReport: () => {
        const content = document.getElementById('reportContent').innerHTML;
        const win = window.open('', '', 'width=800,height=600');
        win.document.write('<html><head><title>Print Report</title></head><body>');
        win.document.write(content);
        win.document.write('</body></html>');
        win.document.close();
        win.print();
    },

    // --- ADMIN SUPPORT ---
    callDevSupport: () => {
        document.getElementById('devModal').style.display = 'flex';
    },
    
    submitDevTicket: () => {
        document.getElementById('devModal').style.display = 'none';
        app.showToast('Ticket Submitted', 'Support team notified. ID #992.', 'confirmation_number');
    },
    
    toggleAvailability: (btn) => {
        if(btn.style.background.includes('e6f4ea')) {
             // Go Offline
             btn.style.background = '#fee2e2';
             btn.style.color = '#ef4444';
             btn.innerHTML = '<span class="material-symbols-rounded" style="font-size:16px; color:#ef4444">do_not_disturb_on</span> Busy / Offline';
        } else {
             btn.style.background = '#e6f4ea';
             btn.style.color = '#137333';
             btn.innerHTML = '<span class="material-symbols-rounded" style="font-size:16px; color:#137333">fiber_manual_record</span> Accepting Requests';
        }
    }
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    app.initDynamicRequests();
});