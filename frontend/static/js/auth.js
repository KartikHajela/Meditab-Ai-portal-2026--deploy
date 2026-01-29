const API_URL = ""; 

let pendingUserId = null;

    // --- STATE ---
    const modal = document.getElementById('authModal');
    const authCard = document.getElementById('authCard');
    
    // Tracks the VISUAL tab state ('patient' or 'provider')
    let currentTabState = 'patient'; 

    // --- UI FUNCTIONS ---
    function openModal() { if(modal) modal.classList.add('active'); }
    
    function closeModal() {
        if(modal) modal.classList.remove('active');
        setTimeout(() => { toggleAuthView('login'); resetForms(); }, 200);
    }

    if(modal) modal.addEventListener('click', (e) => { if(e.target === modal) closeModal(); });

    function toggleAuthView(viewName) {
        document.querySelectorAll('.auth-view').forEach(v => v.classList.remove('active'));
        document.getElementById(`view-${viewName}`).classList.add('active');
    }

    function switchRole(uiRole) {
        currentTabState = uiRole; // 'patient' or 'provider'
        
        // Update Buttons
        document.getElementById('role-patient').classList.toggle('active', uiRole === 'patient');
        document.getElementById('role-provider').classList.toggle('active', uiRole === 'provider');
        
        // Update Theme & Fields
        if (uiRole === 'provider') {
            authCard.classList.add('provider-mode');
            if(document.getElementById('npi-container')) document.getElementById('npi-container').style.display = 'block';
        } else {
            authCard.classList.remove('provider-mode');
            if(document.getElementById('npi-container')) document.getElementById('npi-container').style.display = 'none';
        }
    }

    function resetForms() {
        document.querySelectorAll('input').forEach(i => i.value = '');
        if(document.getElementById('checkBAA')) document.getElementById('checkBAA').checked = false;
        switchRole('patient');
    }

    // --- LOGIN LOGIC (UPDATED) ---
async function handleLogin() {
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPass').value;
    const btn = document.querySelector('#view-login .submit-btn');
    const originalText = btn.innerText;

    if (!email || !password) { alert("Please enter credentials."); return; }

    try {
        btn.innerText = "Authenticating...";
        btn.disabled = true;

        const res = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email, password: password })
        });

        const data = await res.json();

        if (res.ok) {
            // CASE 1: 2FA REQUIRED
            if (data.status === '2fa_required') {
                pendingUserId = data.user_id; // Store ID for step 2
                
                // Switch UI to Verify View
                toggleAuthView('verify'); 
                
                // Focus the OTP input for better UX
                setTimeout(() => document.getElementById('otpInput').focus(), 100);

                // Reset Login button state
                btn.innerText = originalText;
                btn.disabled = false;
                return;
            }

            // CASE 2: SUCCESSFUL LOGIN (No 2FA)
            processLoginSuccess(data);

        } else {
            // Handle Errors
            const err = data.detail || "Login failed";
            alert("Login Failed: " + (typeof err === 'object' ? JSON.stringify(err) : err));
            btn.innerText = originalText;
            btn.disabled = false;
        }
    } catch (e) {
        console.error(e);
        alert("Server connection failed.");
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

    // --- SIGNUP LOGIC (No changes needed, but included for completeness) ---
    async function handleSignup() {
        const name = document.getElementById('signupName').value;
        const email = document.getElementById('signupEmail').value;
        const password = document.getElementById('signupPass').value;
        const baaCheckbox = document.getElementById('checkBAA');
        const btn = document.querySelector('#view-signup .submit-btn');
        const originalText = btn.innerText;

        if (!email.includes('@')) { alert("Invalid email."); return; }
        if (password.length < 4) { alert("Password too short."); return; }
        if (!baaCheckbox.checked) { alert("Please agree to the BAA & Terms."); return; }

        let payloadRole = 'patient';
        let payloadProviderId = null;

        if (currentTabState === 'provider') {
            payloadRole = 'doctor'; 
            const npi = document.getElementById('signupNPI').value;
            if (!npi || npi.length < 5) { alert("Enter a valid NPI/License Number (Start with 88 or 00)."); return; }
            payloadProviderId = npi;
        }

        try {
            btn.innerText = "Creating Account...";
            btn.disabled = true;

            const res = await fetch(`${API_URL}/users/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    password: password,
                    role: payloadRole,
                    provider_id: payloadProviderId,
                    is_2fa_enabled: false, 
                    has_signed_baa: true
                })
            });

            if (res.ok) {
                alert("Account Created! Please log in.");
                toggleAuthView('login');
                document.getElementById('loginEmail').value = email;
                btn.innerText = originalText;
                btn.disabled = false;
            } else {
                const err = await res.json();
                const errorMsg = typeof err.detail === 'object' ? JSON.stringify(err.detail) : err.detail;
                alert("Registration Failed: " + errorMsg);
                btn.innerText = originalText;
                btn.disabled = false;
            }
        } catch (e) {
            console.error(e);
            alert("Server connection failed.");
            btn.innerText = originalText;
            btn.disabled = false;
        }
    }

async function handleGoogleLogin(response) {
    // 1. Get the Google Token
    const credential = response.credential;
    
    // 2. Select the existing Sign In button to show status (since Google's button can't be changed)
    const btn = document.querySelector('#view-login .submit-btn');
    const originalText = btn.innerText;

    try {
        // 3. UI Feedback: Show user something is happening
        btn.innerText = "Verifying Google...";
        btn.disabled = true;

        // 4. Send to your NEW backend route (Matches the schemas.GoogleOneTapInput we created)
        const res = await fetch(`${API_URL}/auth/google-one-tap`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: credential }) 
        });

        const respData = await res.json();

        // 5. Handle Response based on the "success" flag (matches your Python return format)
        if (respData.success) {
            
            // Store User Data
            localStorage.setItem('mediconnect_user', JSON.stringify(respData.data.user));
            
            // Redirect to the dashboard/app
            window.location.href = respData.data.redirect_url;
            
        } else {
            // Backend returned success: False
            alert("Login Failed: " + (respData.message || "Unknown error"));
            
            // Reset Button
            btn.innerText = originalText;
            btn.disabled = false;
        }

    } catch (e) {
        console.error(e);
        alert("Server connection failed.");
        
        // Reset Button
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

// --- NEW FUNCTION: VERIFY OTP ---
async function handleVerifyOTP() {
    const code = document.getElementById('otpInput').value.replace(/\s/g, ''); // Remove spaces
    const btn = document.querySelector('#view-verify .submit-btn');
    const originalText = btn.innerText;

    if (!code || code.length < 6) { alert("Please enter the 6-digit code."); return; }
    if (!pendingUserId) { alert("Session error. Please log in again."); toggleAuthView('login'); return; }

    try {
        btn.innerText = "Verifying...";
        btn.disabled = true;

        // Call the new verification endpoint
        const res = await fetch(`${API_URL}/auth/verify-2fa`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: pendingUserId, 
                otp_code: code 
            })
        });

        const data = await res.json();

        if (res.ok) {
            processLoginSuccess(data);
        } else {
            alert("Verification Failed: " + (data.detail || "Invalid Code"));
            btn.innerText = originalText;
            btn.disabled = false;
        }

    } catch (e) {
        console.error(e);
        alert("Verification error.");
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

// --- HELPER: CENTRALIZED SUCCESS HANDLER ---
function processLoginSuccess(data) {
    const userRole = (data.role || "").toLowerCase();
    
    // Strict Role Check (Matches your previous logic)
    const isUserProvider = (userRole === 'doctor' || userRole === 'admin');

    if (currentTabState === 'patient' && isUserProvider) {
        alert("⚠️ Access Denied: You are a Provider/Admin. Please use the Provider login.");
        location.reload(); 
        return;
    }
    if (currentTabState === 'provider' && !isUserProvider) {
        alert("⚠️ Access Denied: You are a Patient. Please use the Patient login.");
        location.reload();
        return;
    }

    // Success Actions
    localStorage.setItem('mediconnect_user', JSON.stringify(data));
    
    const btn = document.querySelector('.auth-view.active .submit-btn');
    if(btn) {
        btn.innerText = "Success!";
        btn.style.backgroundColor = "#10b981";
    }

    setTimeout(() => {
        window.location.href = data.redirect_url || "/dashboard";
    }, 500);
}

// --- FORGOT PASSWORD HANDLER ---
async function handleForgotSubmit() {
    const email = document.getElementById('forgotEmail').value;
    const btn = document.querySelector('#view-forgot .submit-btn');
    
    if(!email) { alert("Please enter your email."); return; }

    btn.innerText = "Sending...";
    btn.disabled = true;

    try {
        await fetch(`${API_URL}/auth/forgot-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        
        // Always show success to prevent email fishing
        alert("If an account exists, a reset link has been sent to your email.");
        toggleAuthView('login');
    } catch (e) {
        console.error(e);
        alert("Error sending request.");
    } finally {
        btn.innerText = "Send Link";
        btn.disabled = false;
    }
}

// --- RESET PASSWORD HANDLER ---
async function handleResetSubmit() {
    const password = document.getElementById('newPass').value;
    const token = document.getElementById('resetToken').value;
    const btn = document.querySelector('#view-reset .submit-btn');

    if(!password || password.length < 4) { alert("Password too short."); return; }

    btn.innerText = "Updating...";
    btn.disabled = true;

    try {
        const res = await fetch(`${API_URL}/auth/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, password })
        });
        
        const data = await res.json();
        
        if(res.ok) {
            alert("Password updated! Please log in.");
            toggleAuthView('login');
        } else {
            alert(data.detail || "Failed to update password.");
        }
    } catch (e) {
        console.error(e);
        alert("Connection error.");
    } finally {
        btn.innerText = "Update Password";
        btn.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // 1. Check URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const action = urlParams.get('action');
    const token = urlParams.get('token');

    // 2. If 'action=signup' is present, open modal immediately
    if (action === 'signup') {
        openModal(); // Opens the main modal overlay
        toggleAuthView('signup'); // Switches specifically to the Sign-Up view
        
        // Optional: Clean the URL so a refresh doesn't reopen it forever
        const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
        window.history.replaceState({path: newUrl}, '', newUrl);
    }

    // NEW: Detect Reset Link
    if (action === 'reset_password' && token) {
        openModal();
        toggleAuthView('reset'); // Show the New Password view
        document.getElementById('resetToken').value = token; // Inject token
        
        // Clean URL
        const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
        window.history.replaceState({path: newUrl}, '', newUrl);
    }
    
});