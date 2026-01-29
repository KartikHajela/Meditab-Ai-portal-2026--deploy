/**
 * Meditab Pro - Physician Console Logic
 * Architecture: Global Functions (Direct DOM binding)
 * Features: SPA Navigation, AI Simulation, Clinical Tools, Real-time Triage
 */

// ==========================================================================
// 1. GLOBAL STATE
// ==========================================================================
let currentView = 'dashboard';
let currentPatientId = null;
let isOnline = true;
let shiftStartTime = new Date();
let triageInterval = null;

// Active Clinical Data
let encounterNotes = "";
let activeMedications = []; // Array of objects: { name, dose, source }

// Mock Database
let patients = [
    { id: '101', name: 'John Doe', age: 54, complaint: 'Chest Pain (Acute)', risk: 'critical', wait: '14m', vitals: { hr: '110', bp: '150/95' } },
    { id: '102', name: 'Sarah Smith', age: 29, complaint: 'Severe Dermatitis', risk: 'stable', wait: '8m', vitals: { hr: '72', bp: '118/76' } },
    { id: '103', name: 'Mike Ross', age: 32, complaint: 'Migraine', risk: 'warning', wait: '2m', vitals: { hr: '85', bp: '130/85' } }
];

const aiSuggestions = [
    { id: 'rx_01', name: 'Aspirin', dose: '81mg • Oral • Daily', reason: 'Protocol: Cardiac Prophylaxis' },
    { id: 'rx_02', name: 'Nitroglycerin', dose: '0.4mg • Sublingual • PRN', reason: 'Symptom Control: Angina' }
];

// ==========================================================================
// 2. INITIALIZATION
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    
    // Initial Renders
    renderTriageTable();
    renderActivityFeed();
    startDynamicRequests(); // Start the simulation
    
    // Global Hotkeys
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            saveDraft();
        }
    });
});

function updateClock() {
    const now = new Date();
    const diff = now - shiftStartTime;
    const hh = Math.floor(diff / 3600000).toString().padStart(2, '0');
    const mm = Math.floor((diff % 3600000) / 60000).toString().padStart(2, '0');
    const ss = Math.floor((diff % 60000) / 1000).toString().padStart(2, '0');
    
    const clockEl = document.getElementById('shiftClock');
    if (clockEl) clockEl.innerText = `${hh}:${mm}:${ss}`;
}

// ==========================================================================
// 3. NAVIGATION & VIEW LOGIC
// ==========================================================================
function switchView(viewName) {
    currentView = viewName;

    // 1. Hide all views
    document.querySelectorAll('.view-container').forEach(el => {
        el.classList.remove('active');
        setTimeout(() => el.style.display = 'none', 0);
    });

    // 2. Update Sidebar Active State
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const activeNav = document.getElementById(`nav-${viewName}`);
    if (activeNav) activeNav.classList.add('active');

    // 3. Show Target View
    const target = document.getElementById(`view-${viewName}`);
    if (target) {
        target.style.display = (viewName === 'dashboard') ? 'grid' : (viewName === 'workspace' ? 'flex' : 'block');
        // Force reflow
        void target.offsetWidth;
        target.classList.add('active');
    }

    // 4. Update Header
    const titles = { 'dashboard': 'Command Center', 'workspace': 'Patient Workspace', 'profile': 'My Performance', 'schedule': 'Schedule' };
    document.getElementById('pageTitle').innerText = titles[viewName] || 'Console';
}

function openPatient(id) {
    const p = patients.find(pat => pat.id === id);
    if (!p && !id.includes('EMERGENCY')) return;

    currentPatientId = id;
    
    // Reset Data
    activeMedications = [];
    document.getElementById('clinicalNoteInput').value = "";
    
    // Update UI (Mock Data Injection)
    if(p) {
        // In a real app, bind p.name, p.age to DOM elements here
        // console.log("Loaded:", p.name);
    }

    // Render Sub-components
    renderAiRx();
    renderFinalRx();

    switchView('workspace');
    document.getElementById('pageTitle').innerHTML = `Workspace <span style="opacity:0.6">/ ${p ? p.name : 'Emergency'}</span>`;
    showToast(`Loaded Case #${id}`, 'folder_open');
}

function switchTab(tabId, btn) {
    // Buttons
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    if(btn) btn.classList.add('active');

    // Content
    document.querySelectorAll('.tab-content').forEach(c => {
        c.classList.remove('active');
        c.style.display = 'none';
    });
    
    const target = document.getElementById(`tab-${tabId}`);
    if(target) {
        target.style.display = 'block';
        setTimeout(() => target.classList.add('active'), 10);
    }
}

// ==========================================================================
// 4. CLINICAL TOOLS (Meds & Notes)
// ==========================================================================

// --- Medicine Recommender ---
function renderAiRx() {
    const container = document.getElementById('aiRxList');
    if (!container) return;
    
    container.innerHTML = aiSuggestions.map(rx => `
        <div class="rx-card ai-suggestion" id="${rx.id}">
            <div>
                <div class="rx-name">${rx.name}</div>
                <div class="rx-dose">${rx.dose}</div>
                <div style="font-size:0.75rem; color:#9b72cb; font-style:italic;">Reason: ${rx.reason}</div>
            </div>
            <div class="rx-actions">
                <button class="rx-btn reject" onclick="rejectRx('${rx.id}')" title="Reject">
                    <span class="material-symbols-rounded">close</span>
                </button>
                <button class="rx-btn accept" onclick="acceptRx('${rx.id}', '${rx.name}', '${rx.dose}')" title="Accept">
                    <span class="material-symbols-rounded">check</span>
                </button>
            </div>
        </div>
    `).join('');
}

function acceptRx(id, name, dose) {
    activeMedications.push({ name, dose, source: 'AI' });
    
    // Visual feedback
    const card = document.getElementById(id);
    if(card) {
        card.style.opacity = '0.5';
        card.style.pointerEvents = 'none';
        card.querySelector('.rx-actions').innerHTML = '<span style="color:#16a34a; font-weight:600; font-size:0.8rem;">Accepted</span>';
    }
    renderFinalRx();
}

function rejectRx(id) {
    const card = document.getElementById(id);
    if(card) {
        card.style.transform = 'translateX(20px)';
        card.style.opacity = '0';
        setTimeout(() => card.style.display = 'none', 200);
    }
}

function addManualRx() {
    const name = document.getElementById('manualDrug').value;
    const dose = document.getElementById('manualDose').value;
    
    if (name && dose) {
        activeMedications.push({ name, dose, source: 'Manual' });
        renderFinalRx();
        document.getElementById('manualDrug').value = '';
        document.getElementById('manualDose').value = '';
    } else {
        showToast("Enter drug name and dose", "error");
    }
}

function renderFinalRx() {
    const container = document.getElementById('finalRxList');
    if (!container) return;

    if (activeMedications.length === 0) {
        container.innerHTML = `<div class="empty-state" style="text-align:center; padding:20px; color:var(--text-sub); font-size:0.85rem;">No medications ordered yet.</div>`;
        return;
    }

    container.innerHTML = activeMedications.map((m, i) => `
        <div class="final-rx-item">
            <div>
                <strong>${m.name}</strong> <span style="color:var(--text-sub)">${m.dose}</span>
                ${m.source === 'AI' ? '<span style="background:#f3e8ff; color:#7e22ce; font-size:0.6rem; padding:2px 6px; border-radius:4px; margin-left:6px;">AI</span>' : ''}
            </div>
            <span class="material-symbols-rounded delete-icon" onclick="removeFinalRx(${i})">delete</span>
        </div>
    `).join('');
}

function removeFinalRx(index) {
    activeMedications.splice(index, 1);
    renderFinalRx();
}

// --- Note Editor ---
function insertTemplate() {
    const ta = document.getElementById('clinicalNoteInput');
    ta.value = "Subjective:\nPatient presents with...\n\nObjective:\nVitals stable.\n\nAssessment:\n\nPlan:\n";
    ta.focus();
}

function saveDraft() {
    // Simulate API call
    const btn = document.querySelector('.modal-btn.secondary'); 
    if(btn) btn.innerText = "Saving...";
    
    setTimeout(() => {
        showToast("Draft saved to cloud", "cloud_done");
        if(btn) btn.innerText = "Save Draft";
    }, 800);
}

// ==========================================================================
// 5. REPORT GENERATION
// ==========================================================================
function generateReportPreview() {
    const note = document.getElementById('clinicalNoteInput').value || "No notes recorded.";
    const medsList = activeMedications.length > 0 
        ? activeMedications.map(m => `<li>${m.name} - ${m.dose}</li>`).join('') 
        : "<li>No medications prescribed.</li>";
    
    const p = patients.find(pt => pt.id === currentPatientId) || {name:'Unknown', id:'N/A'};

    const html = `
        <div style="padding:40px; font-family:'Times New Roman', serif; color:black;">
            <div style="text-align:center; border-bottom:2px solid #000; padding-bottom:20px; margin-bottom:30px;">
                <h2 style="margin:0; letter-spacing:1px;">MEDITAB MEDICAL CENTER</h2>
                <p style="margin:5px 0 0 0; font-size:0.9rem;">123 Innovation Blvd, Tech City • (555) 123-4567</p>
            </div>
            
            <table style="width:100%; margin-bottom:30px;">
                <tr>
                    <td><strong>Patient:</strong> ${p.name}</td>
                    <td style="text-align:right;"><strong>Date:</strong> ${new Date().toLocaleDateString()}</td>
                </tr>
                <tr>
                    <td><strong>ID:</strong> #${p.id}</td>
                    <td style="text-align:right;"><strong>Physician:</strong> Dr. Alexander Smith</td>
                </tr>
            </table>

            <h3 style="background:#eee; padding:5px 10px; font-size:1rem; border-left:4px solid #333;">CLINICAL SUMMARY</h3>
            <div style="white-space: pre-wrap; margin:15px 0; line-height:1.6;">${note}</div>

            <h3 style="background:#eee; padding:5px 10px; font-size:1rem; border-left:4px solid #333; margin-top:30px;">TREATMENT PLAN</h3>
            <ul style="margin-top:10px; line-height:1.5;">${medsList}</ul>

            <div style="margin-top:80px; display:flex; justify-content:space-between;">
                <div style="border-top:1px solid #000; width:200px; padding-top:5px; text-align:center;">Patient Signature</div>
                <div style="border-top:1px solid #000; width:200px; padding-top:5px; text-align:center;">Physician Signature</div>
            </div>
        </div>
    `;

    document.getElementById('reportContent').innerHTML = html;
    document.getElementById('reportModal').style.display = 'flex';
}

function printReport() {
    const content = document.getElementById('reportContent').innerHTML;
    const win = window.open('', '', 'width=900,height=700');
    win.document.write(`<html><head><title>Print Report</title></head><body style="padding:0;">${content}</body></html>`);
    win.document.close();
    win.focus();
    win.print();
    win.close();
}

function finalizeEncounter() {
    if(confirm("Sign and Discharge patient? This will finalize the report.")) {
        showToast("Patient Discharged", "check_circle");
        
        // Remove patient from list
        patients = patients.filter(p => p.id !== currentPatientId);
        renderTriageTable();
        
        setTimeout(() => switchView('dashboard'), 1000);
    }
}

// ==========================================================================
// 6. AI SIMULATION & DYNAMIC REQUESTS
// ==========================================================================
function startDynamicRequests() {
    if(triageInterval) clearInterval(triageInterval);
    
    triageInterval = setInterval(() => {
        // 30% chance every 15s to spawn a patient
        if (Math.random() > 0.7) {
            const names = ["Rachel Green", "Harvey Specter", "Louis Litt", "Donna Paulsen"];
            const complaints = ["High Fever (103°F)", "Palpitations", "Severe Anxiety", "Refill Request"];
            
            const newP = {
                id: Math.floor(Math.random() * 9000 + 1000).toString(),
                name: names[Math.floor(Math.random() * names.length)],
                complaint: complaints[Math.floor(Math.random() * complaints.length)],
                risk: Math.random() > 0.6 ? 'stable' : 'warning',
                wait: 'Just now',
                vitals: { hr: 'N/A', bp: 'N/A' }
            };

            patients.unshift(newP); // Add to top
            if(patients.length > 8) patients.pop(); // Prevent overflow

            renderTriageTable();
            addSidebarAlert(newP);
            showToast(`New Request: ${newP.name}`, 'person_add');
        }
    }, 15000);
}

function sendAiConsult() {
    const input = document.getElementById('aiConsultInput');
    const text = input.value;
    if(!text) return;

    const log = document.getElementById('aiConsultLog');
    
    // User Message
    log.innerHTML += `<div class="doc-msg-row"><div class="doc-bubble">${text}</div></div>`;
    input.value = "";
    log.scrollTop = log.scrollHeight;

    // Loading State
    const loadingId = 'loading-' + Date.now();
    log.innerHTML += `<div class="ai-msg-row" id="${loadingId}"><div class="ai-avatar"><span class="material-symbols-rounded">smart_toy</span></div><div class="ai-bubble" style="color:#888; font-style:italic;">Thinking...</div></div>`;
    log.scrollTop = log.scrollHeight;

    // AI Response
    setTimeout(() => {
        document.getElementById(loadingId).remove();
        let reply = "I've reviewed the patient's records. No significant findings matching that query.";
        
        if(text.toLowerCase().includes('allerg')) reply = "<strong>Alert:</strong> Patient has a known allergy to Penicillin (Skin rash, 2018).";
        if(text.toLowerCase().includes('lab')) reply = "Most recent labs (Yesterday):<br>• WBC: 11.2 (Elevated)<br>• Hgb: 14.0<br>• Plt: 250";
        if(text.toLowerCase().includes('summar')) reply = "<strong>Summary:</strong> 54yo Male presented with acute chest pain. ECG showed sinus tachycardia. Troponin negative at 2h.";

        log.innerHTML += `<div class="ai-msg-row"><div class="ai-avatar"><span class="material-symbols-rounded">smart_toy</span></div><div class="ai-bubble">${reply}</div></div>`;
        log.scrollTop = log.scrollHeight;
    }, 1200);
}

function quickAsk(q) {
    document.getElementById('aiConsultInput').value = q;
    sendAiConsult();
}

// ==========================================================================
// 7. UTILS & UI HELPERS
// ==========================================================================
function renderTriageTable() {
    const tbody = document.getElementById('triageTableBody');
    if(!tbody) return;

    tbody.innerHTML = patients.map(p => `
        <tr onclick="openPatient('${p.id}')">
            <td><span class="badge ${p.risk}">${p.risk.toUpperCase()}</span></td>
            <td>
                <div style="font-weight:600; color:var(--text-main);">${p.name}</div>
                <div style="font-size:0.7rem; color:var(--text-sub);">ID #${p.id}</div>
            </td>
            <td style="color:var(--text-main);">${p.complaint}</td>
            <td style="font-weight:600; color:${p.risk === 'critical' ? 'var(--danger)' : 'var(--text-sub)'};">${p.wait}</td>
            <td><span class="material-symbols-rounded" style="color:var(--text-sub);">arrow_forward</span></td>
        </tr>
    `).join('');
}

function addSidebarAlert(p) {
    const list = document.getElementById('triageList');
    if(!list) return;

    const div = document.createElement('div');
    div.className = 'sidebar-file-item';
    div.onclick = () => openPatient(p.id);
    
    let color = '#10b981';
    if(p.risk === 'warning') color = '#f59e0b';
    if(p.risk === 'critical') color = '#ef4444';

    div.innerHTML = `
        <span class="material-symbols-rounded file-icon-small" style="color:${color}">circle</span>
        <div class="file-name-small">
            <strong>${p.name}</strong>
            <div style="font-size:10px; opacity:0.7;">${p.complaint}</div>
        </div>
    `;
    div.style.animation = "fadeIn 0.5s";
    list.insertBefore(div, list.firstChild);
}

function renderActivityFeed() {
    const feed = document.getElementById('activityFeed');
    if(!feed) return;
    
    const items = [
        { icon: 'check_circle', color: '#10b981', text: 'Dr. Smith discharged Patient #109', time: '5m ago' },
        { icon: 'science', color: '#3b82f6', text: 'Lab Results ready for John Doe', time: '12m ago' },
        { icon: 'e911_emergency', color: '#ef4444', text: 'Critical Vitals Alert: Bed 4', time: '20m ago' }
    ];

    feed.innerHTML = items.map(i => `
        <div style="display:flex; gap:12px; padding:12px 16px; border-bottom:1px solid var(--border);">
            <div style="width:32px; height:32px; border-radius:50%; background:${i.color}15; color:${i.color}; display:flex; align-items:center; justify-content:center;">
                <span class="material-symbols-rounded" style="font-size:18px;">${i.icon}</span>
            </div>
            <div>
                <div style="font-size:0.85rem; font-weight:500; color:var(--text-main);">${i.text}</div>
                <div style="font-size:0.7rem; color:var(--text-sub);">${i.time}</div>
            </div>
        </div>
    `).join('');
}

function showToast(message, icon) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span class="material-symbols-rounded" style="font-size:20px;">${icon}</span><span>${message}</span>`;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
}

function toggleStatus() {
    isOnline = !isOnline;
    const btn = document.getElementById('statusBtn');
    if(isOnline) {
        btn.innerHTML = `<span class="material-symbols-rounded" style="font-size:16px; color:#10b981;">fiber_manual_record</span><span>Accepting Cases</span>`;
        btn.style.borderColor = 'var(--border)';
        btn.style.background = 'var(--bg-body)';
        btn.style.color = 'var(--text-main)';
    } else {
        btn.innerHTML = `<span class="material-symbols-rounded" style="font-size:16px; color:#ef4444;">do_not_disturb_on</span><span>Busy / Offline</span>`;
        btn.style.borderColor = '#fecaca';
        btn.style.background = '#fef2f2';
        btn.style.color = '#991b1b';
    }
}

// Sidebar Mobile Toggle
function toggleSidebar() {
    const sb = document.getElementById('sidebar');
    if (sb.style.marginLeft === '-280px' || getComputedStyle(sb).marginLeft === '-280px') {
        sb.style.marginLeft = '0';
    } else {
        sb.style.marginLeft = '-280px';
    }
}

// Dev Modal
function openDevModal() { document.getElementById('devModal').style.display = 'flex'; }
function closeDevModal() { document.getElementById('devModal').style.display = 'none'; }
function submitDevTicket() {
    const txt = document.getElementById('devTicketText').value;
    if(!txt) return alert("Please describe the issue");
    closeDevModal();
    showToast("Ticket #992 Created. Support notified.", "bug_report");
    document.getElementById('devTicketText').value = "";
}

// Emergency Blast
function triggerBlastModal() { document.getElementById('blastModal').style.display = 'flex'; }
function closeBlast() { document.getElementById('blastModal').style.display = 'none'; }
function acceptBlast() {
    closeBlast();
    openPatient('EMERGENCY-001');
    showToast("Emergency Protocol Activated", "e911_emergency");
}