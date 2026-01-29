/**
 * chat.js
 * Handles Chat UI, Upload Manager, Autocomplete, Markdown & Mock Data
 * Status: Updated with Material Design 3 & Functional Features
 */

const API_URL ="";

let currentSessionId = "session_" + new Date().getTime();
let uploadCount = 0;
let activeUploads = 0;
let uploadManagerTimeout = null;
let activeAttachments = []; // Stores { id, type, name, file/blob, isPlaying }

// --- DYNAMIC AI AUTOCOMPLETE ---
let autocompleteTimeout = null;

// Recording State 
let isRecording = false;
let isPaused = false;
let recordInterval;
let recordSeconds = 0;
let mediaRecorder = null;
let audioChunks = [];

// --- MOCK DATA ENGINE ---
const MOCK_CHATS = [
    { id: 1, topic: "Project roadmap discussion", date: new Date().toISOString() }, 
    { id: 2, topic: "API Documentation Review", date: new Date().toISOString() },
    { id: 3, topic: "Database Schema Design", date: new Date(Date.now() - 86400000).toISOString() }, // Yesterday
    { id: 4, topic: "Frontend Bug Analysis", date: new Date(Date.now() - 86400000).toISOString() }
];

const MOCK_FILES = [
    { name: "Blood_Report_Oct24.pdf" },
    { name: "MRI_Scan_Results.jpg" },
    { name: "Prescription.pdf" },
    { name: "Blood_Report_Oct24.pdf" },
    { name: "MRI_Scan_Results.jpg" },
    { name: "Prescription.pdf" }
];

// --- 1. DYNAMIC AUTOCOMPLETE ENGINE (Levenshtein Fuzzy Match) ---
const SUGGESTIONS = [
    "Analyze my recent blood report",
    "Draft a referral letter for cardiology",
    "What are the side effects of Metformin?",
    "Summarize this patient's history",
    "Check for drug interactions between Aspirin and Warfarin",
    "Explain the MRI results in simple terms"
];

function levenshtein(a, b) {
    const matrix = [];
    for (let i = 0; i <= b.length; i++) matrix[i] = [i];
    for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
    for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
            if (b.charAt(i - 1) == a.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j] + 1
                );
            }
        }
    }
    return matrix[b.length][a.length];
}

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
    // 1. Check User Login
    const userJson = localStorage.getItem("mediconnect_user");
    if (userJson) {
        const user = JSON.parse(userJson);
        const name = user.profile?.full_name || user.email.split('@')[0];
        const displayName = name.charAt(0).toUpperCase() + name.slice(1);
        
        const elGreeting = document.getElementById("greetingName");
        if(elGreeting) elGreeting.innerText = `Hello, ${displayName}`;
        
        // Update Sidebar/Header Avatars
        const els = ["sidebarName", "modalName"];
        els.forEach(id => { const el = document.getElementById(id); if(el) el.innerText = displayName; });
        
        const emailEl = document.getElementById("modalEmail");
        if(emailEl) emailEl.innerText = user.email;
    }

    // 2. Render Sidebar History
    renderSidebar();
    renderSidebarFiles();
    checkProfileStatus();

    // 3. Scroll Listener for "Go to Bottom" Button
    const scrollContainer = document.getElementById('mainScrollContainer');
    if(scrollContainer) {
        scrollContainer.addEventListener('scroll', () => {
            const btn = document.getElementById('scrollBottomBtn');
            // Show button if user scrolls up more than 100px from bottom
            const distanceToBottom = scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight;
            if (btn) btn.classList.toggle('visible', distanceToBottom > 150);
        });
    }

    // 4. File Input Listener
    const fileIn = document.getElementById("fileInput");
    if (fileIn) {
        fileIn.addEventListener("change", handleFileUpload);
    }
});

// --- AUTOCOMPLETE LOGIC ---
function handleInput(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
    
    const val = textarea.value;
    const list = document.getElementById('autocompleteList');
    
    // Clear previous debounce
    if (autocompleteTimeout) clearTimeout(autocompleteTimeout);

    if (val.length > 3) {
        // Debounce API call (wait 400ms after typing stops)
        autocompleteTimeout = setTimeout(async () => {
            try {
                const res = await fetch(`${API_URL}/chat/autocomplete`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text: val })
                });
                
                if(res.ok) {
                    const data = await res.json();
                    if (data.suggestions && data.suggestions.length > 0) {
                        list.innerHTML = data.suggestions.map(s => 
                            `<div class="suggestion-item" onclick="applySuggestion('${s}')">
                                <span class="material-symbols-outlined" style="font-size:14px; margin-right:8px;">auto_awesome</span>
                                ${s}
                             </div>`
                        ).join('');
                        list.classList.add('visible');
                    } else {
                        list.classList.remove('visible');
                    }
                }
            } catch (e) {
                console.log("Autocomplete skipped");
            }
        }, 400); // 400ms delay
    } else {
        list.classList.remove('visible');
    }
}

function applySuggestion(text) {
    const ta = document.getElementById('chatInput');
    // If the suggestion completes the sentence, append it. 
    // If it's a full phrase, replace. 
    // For simplicity, we just replace current value with the suggestion if it starts with it, or append.
    ta.value = text; 
    document.getElementById('autocompleteList').classList.remove('visible');
    ta.focus();
}


function selectSuggestion(text) {
    const ta = document.getElementById('chatInput');
    ta.value = text;
    document.getElementById('autocompleteList').classList.remove('visible');
    ta.focus();
}

// --- 2. DYNAMIC TITLE GENERATION ---
async function updateChatTitle(firstMessage) {
    // Only generate title for the first message of a new session
    const titleEl = document.getElementById('currentChatTitle');
    if (titleEl.innerText.includes("New Chat") || titleEl.innerText.includes("Project")) {
        try {
            // Call a lightweight endpoint to get a title
            // For now, we simulate or mock if endpoint isn't ready
            const res = await fetch(`${API_URL}/chat/generate_title`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: firstMessage })
            });
            if (res.ok) {
                const data = await res.json();
                titleEl.innerHTML = `<span class="material-symbols-outlined" style="font-size: 18px;">chat</span> ${data.title}`;
            }
        } catch (e) {
            console.log("Title auto-gen skipped");
        }
    }
}

// --- MESSAGE RENDERING & MARKDOWN ---

function parseMarkdown(text) {
    // A lightweight frontend Markdown parser
    let html = text
        // Code Blocks (Triple backticks)
        .replace(/```(\w*)([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
        // Inline Code (Single backtick)
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Bold (**text**)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // Italic (*text*)
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        // Headers (### Text)
        .replace(/^### (.*$)/gm, '<h3>$1</h3>')
        .replace(/^## (.*$)/gm, '<h2>$1</h2>')
        // Bullet Lists (- item)
        .replace(/^\s*-\s+(.*)/gm, '<li>$1</li>')
        // Newlines to <br> (Handle carefully to not break HTML tags)
        .replace(/\n/g, '<br>');
    
    // Simple wrap for lists (imperfect but works for basic cases)
    if (html.includes('<li>')) {
        html = html.replace(/((<li>.*<\/li>)+)/g, '<ul>$1</ul>');
    }
    
    return html;
}

// --- MESSAGE RENDERING (Updated Structure) ---
function appendMessageToUI(role, text, thought = null, rawText = null) {
    const chatContent = document.getElementById("chat-content");
    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    // 1. Avatar (AI Only)
    if (role !== 'user') {
        const avatar = document.createElement("div");
        avatar.className = "msg-avatar ai";
        avatar.innerHTML = `
            <span class="material-symbols-outlined ai-icon result">
                auto_awesome
            </span>`;
        row.appendChild(avatar);
    }

    // 2. Content Container
    const content = document.createElement("div");
    content.className = "msg-content";

    // 3. Render Message Logic
    if (role === 'user') {
        // --- USER MESSAGE ---
        const bubble = document.createElement("div");
        bubble.className = "msg-bubble";
        
        const textDiv = document.createElement("div");
        textDiv.className = "markdown-body";
        textDiv.innerHTML = parseMarkdown(text); // 'text' here contains the HTML chips
        
        bubble.appendChild(textDiv);
        content.appendChild(bubble);

        // Actions
        const actions = document.createElement("div");
        actions.className = "user-actions";
        
        // --- EDIT BUTTON FIX ---
        const editBtn = createActionBtn("edit", "Edit", () => {
            const input = document.getElementById('chatInput');
            
            // FIX: If rawText exists, use it. Otherwise fall back to text.
            // This ensures we get "Hello" instead of "<div>...</div> Hello"
            input.value = rawText !== null ? rawText : text;
            
            input.focus();
            input.style.height = 'auto';
            input.style.height = input.scrollHeight + 'px';
        });

        const copyBtn = createActionBtn("content_copy", "Copy", () => {
            // Prefer copying raw text if available
            navigator.clipboard.writeText(rawText !== null ? rawText : text);
        });

        const delBtn = createActionBtn("delete", "Delete", () => {
            row.remove();
        });

        actions.appendChild(editBtn);
        actions.appendChild(copyBtn);
        actions.appendChild(delBtn);
        content.appendChild(actions);

    } else {
        // --- AI MESSAGE ---
        if (thought) {
            const steps = ["Analyzing request...", "Retrieving data...", "Formulating response..."];
            const stepsHtml = steps.map(s => `<div class="step-item"><span class="material-symbols-outlined" style="font-size:14px; color:var(--text-sub)">check_circle</span> <span>${s}</span></div>`).join('');
            content.innerHTML += `<details class="thinking-steps"><summary class="thinking-summary"><span class="material-symbols-outlined" style="font-size:16px">psychology</span> Thought Process</summary><div class="thinking-details">${stepsHtml}</div></details>`;
        }
        const textDiv = document.createElement("div");
        textDiv.className = "markdown-body";
        textDiv.innerHTML = parseMarkdown(text);
        content.appendChild(textDiv);
    }

    row.appendChild(content);
    chatContent.appendChild(row);
}

// Helper for creating action buttons
function createActionBtn(icon, title, onClick) {
    const btn = document.createElement("button");
    btn.className = "action-icon";
    btn.title = title;
    btn.innerHTML = `<span class="material-symbols-outlined" style="font-size:16px">${icon}</span>`;
    btn.onclick = onClick;
    return btn;
}

function appendLoadingToUI(id) {
    const chatContent = document.getElementById("chat-content");
    const row = document.createElement("div");
    row.id = id;
    row.className = "message-row ai";
    row.innerHTML = `
        <div class="msg-avatar ai">
            <span class="material-symbols-outlined ai-icon loading">
                auto_awesome
            </span>
        </div>
        <div class="msg-content">
            <div class="shimmer-text">Thinking...</div>
        </div>
    `;
    chatContent.appendChild(row);
}

/* --- RECORDING LOGIC --- */
/* --- UPDATED RECORDING LOGIC (Real MediaRecorder) --- */

async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert("Audio recording not supported on this browser.");
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) audioChunks.push(event.data);
        };

        mediaRecorder.start();
        
        // UI State Updates
        isRecording = true;
        isPaused = false;
        recordSeconds = 0;
        
        document.getElementById('standardToolbar').classList.add('hidden');
        document.getElementById('recordingControls').style.display = 'flex';
        document.getElementById('chatInput').placeholder = "Listening...";
        
        updateTimerDisplay();
        startTimer();

        document.querySelector('.rec-visualizer').classList.remove('paused');
        const btn = document.getElementById('pauseRecBtn');
        btn.querySelector('span').innerText = "pause";

    } catch (err) {
        console.error("Error accessing microphone:", err);
        alert("Could not access microphone. Please allow permissions.");
    }
}

function togglePauseRecording() {
    if (!isRecording || !mediaRecorder) return;
    
    if (isPaused) {
        mediaRecorder.resume();
        startTimer();
        document.querySelector('.rec-visualizer').classList.remove('paused');
        document.getElementById('pauseRecBtn').querySelector('span').innerText = "pause";
    } else {
        mediaRecorder.pause();
        clearInterval(recordInterval);
        document.querySelector('.rec-visualizer').classList.add('paused');
        document.getElementById('pauseRecBtn').querySelector('span').innerText = "play_arrow";
    }
    isPaused = !isPaused;
}

function cancelRecording() {
    if (mediaRecorder) {
        mediaRecorder.stop();
        mediaRecorder = null;
    }
    audioChunks = [];
    stopRecordingState();
}

function finishRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        // Define what happens when recorder actually stops
        mediaRecorder.onstop = () => {
            // Create Blob from chunks
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            // Create a File object (to match standard UploadFile logic)
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const file = new File([audioBlob], `voice_${timestamp}.wav`, { type: "audio/wav" });

            // Add to UI Attachments
            activeAttachments.push({
                id: "aud_" + Date.now(),
                type: 'audio',
                name: `Voice Note (${formatTime(recordSeconds)})`,
                src: audioUrl,   // For playback preview
                file: file,      // For API upload
                isPlaying: false
            });
            renderAttachments();
        };

        mediaRecorder.stop();
    }
    stopRecordingState();
}

function stopRecordingState() {
    isRecording = false;
    isPaused = false;
    clearInterval(recordInterval);
    
    // Stop all tracks to release microphone
    if (mediaRecorder && mediaRecorder.stream) {
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }

    document.getElementById('recordingControls').style.display = 'none';
    document.getElementById('standardToolbar').classList.remove('hidden');
    document.getElementById('chatInput').placeholder = "Ask anything...";
}

// Timer Helpers
function startTimer() {
    clearInterval(recordInterval);
    recordInterval = setInterval(() => {
        recordSeconds++;
        updateTimerDisplay();
    }, 1000);
}

function updateTimerDisplay() {
    document.getElementById('recTimerText').innerText = formatTime(recordSeconds);
}

function formatTime(sec) {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = (sec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

// --- CHAT LOGIC ---

function scrollToBottom(force = false) {
    const container = document.getElementById("mainScrollContainer");
    if(container) {
        container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
}


// --- UPDATED SEND MESSAGE (Fixes Saving Bug) ---

async function sendMessage(presetMessage = null) {
    const inputField = document.getElementById("chatInput");
    const text = presetMessage || inputField.value.trim();
    
    // 0. Validation
    if (!text && activeAttachments.length === 0) return;

    // UI Updates
    document.getElementById("landing-hero").style.display = "none";
    document.getElementById("chat-content").style.display = "flex";
    document.getElementById("autocompleteList").classList.remove("visible");

    // 1. Render User Message Immediately
    let displayHtml = "";
    if (activeAttachments.length > 0) {
        displayHtml += `<div class="msg-attachments-row">`;
        activeAttachments.forEach(a => {
            const icon = a.type === 'audio' ? 'mic' : 'description';
            displayHtml += `<div class="attachment-chip ${a.type}"><span class="material-symbols-outlined chip-icon">${icon}</span> ${a.name}</div>`;
        });
        displayHtml += `</div>`;
    }
    if (text) displayHtml += parseMarkdown(text);
    appendMessageToUI("user", displayHtml);

    // 2. Prepare for Backend
    const userJson = localStorage.getItem("mediconnect_user");
    const user = userJson ? JSON.parse(userJson) : { id: 1 };
    
    // Show Loading
    const loadingId = "loading_" + Date.now();
    appendLoadingToUI(loadingId);
    scrollToBottom();
    
    inputField.value = "";
    inputField.style.height = 'auto';

    try {
        let fileContext = "";

        // --- STEP A: PARALLEL FILE UPLOAD & ANALYSIS ---
        if (activeAttachments.length > 0) {
            // We use map to create an array of promises
            const uploadPromises = activeAttachments.map(async (item) => {
                const formData = new FormData();
                formData.append("patient_id", user.id);
                formData.append("session_id", currentSessionId);
                formData.append("file", item.file);
                if (item.type === 'audio') formData.append("is_rec", "true");

                // Hit the upload endpoint
                const res = await fetch(`${API_URL}/upload/`, { method: "POST", body: formData });
                if (!res.ok) throw new Error(`Failed to upload ${item.name}`);
                
                const data = await res.json();
                
                // EXTRACT INTELLIGENCE: 
                // Did the backend analyze the image/PDF?
                let context = "";
                if (data.analysis) {
                    context = `[System: User uploaded file '${item.name}'. AI Analysis: ${data.analysis}]`;
                } else if (data.transcript) {
                    context = `[System: User uploaded audio. Transcript: "${data.transcript}"]`;
                } else {
                    context = `[System: User uploaded file '${item.name}']`;
                }
                return context;
            });

            // Wait for all files to be processed
            const results = await Promise.all(uploadPromises);
            fileContext = results.join("\n") + "\n\n";
        }

        // --- STEP B: SEND CHAT (With Context) ---
        // We combine the file analysis with the user's text
        const fullMessagePayload = fileContext + (text || "");
        
        // Trigger Title Auto-Gen (Fire and forget)
        updateChatTitle(text || "Medical File Upload");

        const res = await fetch(`${API_URL}/chat/send`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: user.id,
                session_id: currentSessionId,
                message: fullMessagePayload 
            })
        });

        if (!res.ok) throw new Error("Message send failed");
        const responseData = await res.json();

        // --- STEP C: RENDER AI RESPONSE ---
        document.getElementById(loadingId).remove();

        if (responseData && responseData.messages) {
            const msgs = responseData.messages;
            const aiMsg = msgs[msgs.length - 1];
            appendMessageToUI("assistant", aiMsg.content);
        }

    } catch (error) {
        console.error("Chat Error:", error);
        const loader = document.getElementById(loadingId);
        if (loader) loader.remove();
        appendMessageToUI("assistant", "⚠️ Connection error. Please try again.");
    }

    // Cleanup
    activeAttachments = [];
    renderAttachments();
    scrollToBottom();
}

/* --- FILE ATTACHMENT LOGIC --- */

// Handle File Input Change
async function handleFileUpload(e) {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    files.forEach(file => {
        activeAttachments.push({
            id: "file_" + Date.now() + Math.random(),
            type: 'file',
            name: file.name,
            file: file
        });
    });

    renderAttachments();
    e.target.value = ""; // Reset input so same file can be selected again
}

// Render All Chips (Audio & Files)
function renderAttachments() {
    const area = document.getElementById('attachmentArea');
    area.innerHTML = "";
    
    if (activeAttachments.length === 0) return;

    activeAttachments.forEach(item => {
        const chip = document.createElement('div');
        
        if (item.type === 'audio') {
            // --- AUDIO CHIP LAYOUT ---
            chip.className = `attachment-chip audio ${item.isPlaying ? 'playing' : ''}`;
            chip.innerHTML = `
                <span class="material-symbols-outlined chip-icon">mic</span>
                <span class="chip-text">${item.name}</span>
                <div class="chip-actions">
                    <button class="chip-btn play" onclick="toggleAudioPreview('${item.id}')" title="${item.isPlaying ? 'Stop' : 'Play'}">
                        <span class="material-symbols-outlined">${item.isPlaying ? 'stop' : 'play_arrow'}</span>
                    </button>
                    <button class="chip-btn delete" onclick="deleteAttachment('${item.id}')" title="Remove">
                        <span class="material-symbols-outlined">close</span>
                    </button>
                </div>
            `;
        } else {
            // --- FILE CHIP LAYOUT ---
            chip.className = "attachment-chip file";
            chip.innerHTML = `
                <span class="material-symbols-outlined chip-icon">attach_file</span>
                <span class="chip-text">${item.name}</span>
                <div class="chip-actions">
                    <button class="chip-btn delete" onclick="deleteAttachment('${item.id}')" title="Remove">
                        <span class="material-symbols-outlined">close</span>
                    </button>
                </div>
            `;
        }
        area.appendChild(chip);
    });
}

function deleteAttachment(id) {
    // If deleting currently playing audio, stop it
    const item = activeAttachments.find(i => i.id === id);
    if (item && item.isPlaying) {
        const audio = document.getElementById('audioPreview');
        audio.pause();
        audio.currentTime = 0;
    }

    activeAttachments = activeAttachments.filter(item => item.id !== id);
    renderAttachments();
}

// Simple Audio Player Logic
function toggleAudioPreview(id) {
    const audio = document.getElementById('audioPreview');
    const itemIndex = activeAttachments.findIndex(i => i.id === id);
    const item = activeAttachments[itemIndex];

    if (item.isPlaying) {
        // Stop
        audio.pause();
        audio.currentTime = 0;
        item.isPlaying = false;
    } else {
        // Stop any other playing audio first
        activeAttachments.forEach(i => i.isPlaying = false);
        
        // Play new
        audio.src = item.src; // In real app use URL.createObjectURL(item.blob)
        audio.play();
        item.isPlaying = true;

        // Auto-reset on end
        audio.onended = () => {
            item.isPlaying = false;
            renderAttachments();
        };
    }
    renderAttachments();
}

// --- GLOBAL ACTIONS (Sidebar, Profile) ---
/* --- RESIZABLE SIDEBAR LOGIC --- */

function toggleSection(id) {
    const widget = document.getElementById(id);
    if (!widget) return;

    // 1. Remove manual height set by Drag Resizer
    // This allows the CSS classes (.collapsed) to actually take effect
    widget.style.height = ''; 

    // 2. Toggle Class
    widget.classList.toggle('collapsed');
}

let startY, startHeight, currentResizingElement;

// Ensure Drag Resizer respects state
function initResize(e, elementId) {
    e.preventDefault(); 
    
    currentResizingElement = document.getElementById(elementId);
    if (!currentResizingElement) return;

    // If hidden/collapsed, force it open before resizing starts
    const widget = currentResizingElement.closest('.files-widget');
    if (widget) {
        if (widget.classList.contains('collapsed')) {
            widget.classList.remove('collapsed');
        }
        widget.classList.add('resizing');
        // Clear any previous fixed height so we start fresh
        // currentResizingElement.style.height = ''; 
    }

    startY = e.clientY;
    startHeight = parseInt(window.getComputedStyle(currentResizingElement).height, 10);

    document.documentElement.addEventListener('mousemove', doDrag);
    document.documentElement.addEventListener('mouseup', stopDrag);
}

function doDrag(e) {
    if (!currentResizingElement) return;

    // Calculate how much mouse moved
    // Dragging UP (negative Y) should INCREASE height
    const dy = startY - e.clientY; 
    
    const newHeight = startHeight + dy;

    // Limit min height to avoid breaking layout (e.g., 50px)
    // Limit max height (e.g., 400px)
    if (newHeight > 40 && newHeight < 600) {
        currentResizingElement.style.height = `${newHeight}px`;
        currentResizingElement.style.maxHeight = 'none'; // Override CSS limit
    }
}

function stopDrag() {
    if (currentResizingElement) {
        const widget = currentResizingElement.closest('.files-widget');
        if (widget) widget.classList.remove('resizing');
    }
    
    currentResizingElement = null;
    document.documentElement.removeEventListener('mousemove', doDrag);
    document.documentElement.removeEventListener('mouseup', stopDrag);
}

function toggleSidebar() {
    const sb = document.getElementById("sidebar");
    // If margin is negative (hidden), set to 0 (visible), and vice versa.
    if (sb.style.marginLeft === "-280px") {
        sb.style.marginLeft = "0";
    } else {
        sb.style.marginLeft = "-280px";
    }
}

function toggleProfile(e) {
    e.stopPropagation();
    const dropdown = document.getElementById("profileDropdown");
    dropdown.classList.toggle("active");
}

function startNewChat() {
    // Reload to reset session (Simple implementation)
    location.reload();
}

function logout() {
    localStorage.removeItem("mediconnect_user");
    window.location.href = "/";
}

function renderSidebar() {
    const list = document.getElementById('historyList');
    if(!list) return;
    
    // Group chats by date (Mock logic)
    const groups = { "Today": [], "Yesterday": [] };
    MOCK_CHATS.forEach(c => {
        const d = new Date(c.date);
        const today = new Date();
        const diff = Math.floor((today - d) / (1000 * 60 * 60 * 24));
        if (diff === 0) groups["Today"].push(c);
        else groups["Yesterday"].push(c);
    });

    let html = "";
    for (const [label, items] of Object.entries(groups)) {
        if(items.length > 0) {
            html += `<div class="group-label">${label}</div>`;
            items.forEach(item => {
                html += `<div class="history-item" onclick="loadChat('${item.topic}')">${item.topic}</div>`;
            });
        }
    }
    list.innerHTML = html;
}

// --- FILE MANAGEMENT (Mini GDrive View - Redesigned) ---

async function renderSidebarFiles() {
    const container = document.getElementById('sidebarFilesList');
    if (!container) return;

    // 1. Get User
    const userJson = localStorage.getItem("mediconnect_user");
    const user = userJson ? JSON.parse(userJson) : null;
    if (!user || !user.hash) {
        container.innerHTML = `<div style="padding:10px; font-size:0.8rem; text-align:center;">Login to view files</div>`;
        return;
    }

    try {
        // 2. Fetch directly from Drive Endpoint
        const res = await fetch(`${API_URL}/app/${user.hash}/files-api`);
        if (!res.ok) throw new Error("Sync failed");
        
        const files = await res.json();
        container.innerHTML = "";

        if (files.length === 0) {
            container.innerHTML = `<div style="padding:15px; font-size:0.8rem; opacity:0.6; text-align:center;">
                <span class="material-symbols-outlined" style="font-size:24px; display:block; margin-bottom:5px;">cloud_off</span>
                Folder Empty
            </div>`;
            return;
        }

        // 3. Render Items (Clean Design)
        files.forEach(file => {
            // Determine Icon
            let icon = "draft"; 
            if (file.mimeType.includes("audio")) icon = "mic";
            else if (file.mimeType.includes("image")) icon = "image";
            else if (file.mimeType.includes("pdf")) icon = "picture_as_pdf";
            
            // Date Format
            const dateStr = new Date(file.createdTime).toLocaleDateString(undefined, {month:'short', day:'numeric'});

            const el = document.createElement('div');
            el.className = 'sidebar-file-item'; 
            el.style.display = "flex";
            el.style.flexDirection = "column";
            el.style.gap = "0";
            
            el.innerHTML = `
                <div style="display:flex; align-items:center; width:100%; gap:8px; padding: 4px 0;">
                    <span class="material-symbols-outlined file-icon-small" style="color:var(--primary); font-size:18px;">${icon}</span>
                    <a href="${file.webViewLink}" target="_blank" class="file-name-small" style="flex:1; text-decoration:none; color:inherit; font-weight:500;" title="${file.name}">
                        ${file.name}
                    </a>
                    <span style="font-size:10px; opacity:0.5; white-space:nowrap;">${dateStr}</span>
                    <button onclick="toggleFileMenu(this)" style="background:none; border:none; cursor:pointer; padding:4px; opacity:0.6; border-radius:50%; display:flex; align-items:center;">
                        <span class="material-symbols-outlined" style="font-size:16px;">more_vert</span>
                    </button>
                </div>
                
                <div class="file-menu" style="display:none; width:100%; padding: 8px 0; border-top:1px solid var(--border); gap:10px; justify-content:flex-start;">
                    
                    <a href="${file.webViewLink}" target="_blank" class="mini-action-pill" style="text-decoration:none; color:var(--text-main); font-size:11px; display:flex; align-items:center; gap:4px; padding:4px 8px; background:rgba(0,0,0,0.05); border-radius:4px;">
                        <span class="material-symbols-outlined" style="font-size:14px;">open_in_new</span> Open
                    </a>

                    <button onclick="deleteFile('${file.id}', this)" class="mini-action-pill" style="border:none; cursor:pointer; font-size:11px; display:flex; align-items:center; gap:4px; padding:4px 8px; background:rgba(217, 48, 37, 0.1); color:#d93025; border-radius:4px;">
                        <span class="material-symbols-outlined" style="font-size:14px;">delete</span> Delete
                    </button>
                </div>
            `;
            container.appendChild(el);
        });

    } catch (e) {
        console.error(e);
        container.innerHTML = `<div style="padding:10px; text-align:center; color:#d93025;">Sync Error</div>`;
    }
}

function toggleFileMenu(btn) {
    // Find the menu div within the same container
    const menu = btn.closest('.sidebar-file-item').querySelector('.file-menu');
    const isVisible = menu.style.display === 'flex';
    
    // Close all other open menus first (Accordion style for cleanliness)
    document.querySelectorAll('.file-menu').forEach(m => m.style.display = 'none');
    
    // Toggle current
    menu.style.display = isVisible ? 'none' : 'flex';
}

async function deleteFile(driveId, btn) {
    if (!confirm("Delete this file from Drive?")) return;
    
    // UI Feedback
    const item = btn.closest('.sidebar-file-item');
    item.style.opacity = '0.3';

    try {
        const res = await fetch(`${API_URL}/files/${driveId}`, { method: 'DELETE' });
        if (res.ok) {
            item.remove();
            if (document.getElementById('sidebarFilesList').children.length === 0) renderSidebarFiles();
        } else {
            alert("Delete failed");
            item.style.opacity = '1';
        }
    } catch (e) {
        console.error(e);
        item.style.opacity = '1';
    }
}

/* --- EMERGENCY LOGIC --- */

function triggerEmergency() {
    const modal = document.getElementById('emergencyModal');
    if(modal) modal.classList.add('active');
}

function handleEmergencyResponse(confirmed) {
    const modal = document.getElementById('emergencyModal');
    if(modal) modal.classList.remove('active');

    // Logic to handle response
    if (confirmed) {
        const payload = {
            type: "EMERGENCY_ALERT",
            status: "CONFIRMED",
            timestamp: new Date().toISOString(),
            user: "current_user_id" 
        };
        console.log("Emergency Submitted:", JSON.stringify(payload, null, 2));
        alert("Emergency Request Submitted: \n" + JSON.stringify(payload));
    } else {
        const payload = {
            type: "EMERGENCY_ALERT",
            status: "CANCELLED",
            timestamp: new Date().toISOString()
        };
        console.log("Emergency Cancelled:", JSON.stringify(payload, null, 2));
    }
}

/* --- SEARCH & HISTORY LOGIC --- */

// 1. Update renderSidebar to accept a filter
function renderSidebar(filter = "") {
    const list = document.getElementById('historyList');
    if(!list) return;
    
    // Filter Chats
    const filteredChats = MOCK_CHATS.filter(c => 
        c.topic.toLowerCase().includes(filter.toLowerCase())
    );

    const groups = { "Today": [], "Yesterday": [] };
    filteredChats.forEach(c => {
        const today = new Date();
        const diff = Math.floor((today - new Date(c.date)) / (1000 * 60 * 60 * 24));
        if (diff === 0) groups["Today"].push(c); else groups["Yesterday"].push(c);
    });

    let html = "";
    if (filteredChats.length === 0) {
        html = `<div style="padding:20px; text-align:center; color:var(--text-sub); font-size:0.85rem;">No chats found</div>`;
    } else {
        for (const [label, items] of Object.entries(groups)) {
            if(items.length > 0) {
                html += `<div class="group-label">${label}</div>`;
                items.forEach(item => html += `<div class="history-item" onclick="loadChat('${item.topic}')">${item.topic}</div>`);
            }
        }
    }
    list.innerHTML = html;
}

// 2. Search Handler
function handleSearch(query) {
    renderSidebar(query);
}

function loadChat(topic) {
    document.getElementById("landing-hero").style.display = "none";
    document.getElementById("chat-content").style.display = "flex";
    document.getElementById("chat-content").innerHTML = ""; 
    appendMessageToUI("user", `Load chat: ${topic}`);
    appendMessageToUI("assistant", `I've loaded the history for **${topic}**.`);
}

// Close Dropdown on Click Outside
window.onclick = function (e) {
    if (!e.target.closest(".user-profile") && !e.target.closest(".profile-dropdown") && !e.target.closest(".header-avatar")) {
        const dropdown = document.getElementById("profileDropdown");
        if(dropdown) dropdown.classList.remove("active");
    }
};

const ta = document.getElementById('chatInput'); // <--- THIS WAS MISSING

if (ta) {
  // Use 'keydown' instead of 'keypress'
  ta.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault(); // Prevents the new line
      sendMessage();
    }
  });
  
  // Keep your existing auto-resize logic if needed
  ta.addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = this.scrollHeight + "px";
  });
}

// --- PROFILE CHECK LOGIC ---
async function checkProfileStatus() {
    const userJson = localStorage.getItem("mediconnect_user");
    const user = userJson ? JSON.parse(userJson) : null;
    
    if (!user || !user.hash) return;

    try {
        const res = await fetch(`/app/${user.hash}/profile/status`);
        const data = await res.json();
        
        if (data.percent < 75) {
            showProfileAlert(data.percent, user.hash);
        }
    } catch (e) {
        console.log("Profile check skipped");
    }
}

function showProfileAlert(percent, userHash) { 
    const sidebar = document.getElementById('sidebar');
    const existing = document.getElementById('profileAlert');
    if (existing) return;

    const btn = document.createElement('button');
    btn.id = 'profileAlert';
    btn.className = 'profile-alert-btn';
    btn.innerHTML = `
        <span class="material-symbols-outlined">assignment_late</span>
        <div style="text-align:left">
            <div style="font-size:11px; opacity:0.8">Profile Incomplete</div>
            <div>Finish Setup (${percent}%)</div>
        </div>
    `;
    
    // Now 'userHash' exists and works
    btn.onclick = () => window.location.href = `/app/${userHash}/profile`;
    
    const footer = document.querySelector('.sidebar-footer');
    if (sidebar && footer) {
        sidebar.insertBefore(btn, footer);
    }
}
