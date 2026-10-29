// ==============================================================================
// MacRemote Interactive Client Script
// ==============================================================================

function copyInstallCmd() {
  const text = document.getElementById('installCommand').innerText;
  navigator.clipboard.writeText(text).then(() => {
    const feedback = document.getElementById('copyFeedback');
    feedback.innerText = 'Copied! ✓';
    setTimeout(() => {
      feedback.innerText = 'Copy';
    }, 2000);
  });
}

function switchTab(index) {
  const tabs = document.querySelectorAll('.tab-btn');
  const contents = [
    document.getElementById('tabContent0'),
    document.getElementById('tabContent1'),
    document.getElementById('tabContent2')
  ];

  tabs.forEach((tab, i) => {
    if (i === index) {
      tab.classList.add('active');
      contents[i].classList.remove('hidden');
    } else {
      tab.classList.remove('active');
      contents[i].classList.add('hidden');
    }
  });
}

function getCurrentTime() {
  const now = new Date();
  return now.toTimeString().substring(0, 5);
}

function appendUserBubble(text) {
  const chatMessages = document.getElementById('chatMessages');
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble user';
  bubble.innerHTML = `
    <div class="bubble-text">${escapeHtml(text)}</div>
    <span class="bubble-time">${getCurrentTime()}</span>
  `;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendBotBubble(htmlContent) {
  const chatMessages = document.getElementById('chatMessages');
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble bot';
  bubble.innerHTML = `
    <div class="bubble-text">${htmlContent}</div>
    <span class="bubble-time">${getCurrentTime()}</span>
  `;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.innerText = text;
  return div.innerHTML;
}

function simulateCommand(cmd) {
  appendUserBubble(cmd);

  // Show brief typing indicator effect
  setTimeout(() => {
    if (cmd === '📸 Screenshot' || cmd.toLowerCase().includes('ss') || cmd.toLowerCase().includes('screenshot')) {
      appendBotBubble(`
        <div style="margin-bottom:8px;">📸 <strong>Retina Display Captured</strong></div>
        <div style="background:#000; border-radius:8px; overflow:hidden; border:1px solid #333; margin-bottom:6px;">
          <!-- Simulated mini mac desktop SVG -->
          <svg viewBox="0 0 400 240" width="100%" height="auto" style="display:block;">
            <rect width="400" height="240" fill="#1e1e24"/>
            <!-- Menu bar -->
            <rect width="400" height="18" fill="#111116"/>
            <text x="12" y="13" fill="#aaa" font-size="9" font-family="sans-serif"> Finder File Edit View Go Window</text>
            <text x="360" y="13" fill="#aaa" font-size="9" font-family="sans-serif">🔋 84%</text>
            <!-- Wallpaper art -->
            <circle cx="200" cy="130" r="70" fill="url(#screenGrad)" opacity="0.6"/>
            <defs>
              <radialGradient id="screenGrad">
                <stop offset="0%" stop-color="#38bdf8"/>
                <stop offset="100%" stop-color="#6366f1"/>
              </radialGradient>
            </defs>
            <!-- Finder Window -->
            <rect x="50" y="45" width="220" height="140" rx="8" fill="#24242c" stroke="#444" stroke-width="1"/>
            <circle cx="62" cy="56" r="3.5" fill="#ff5f56"/>
            <circle cx="72" cy="56" r="3.5" fill="#ffbd2e"/>
            <circle cx="82" cy="56" r="3.5" fill="#27c93f"/>
            <text x="100" y="58" fill="#888" font-size="8" font-family="sans-serif">Downloads — Mac</text>
            <rect x="60" y="70" width="80" height="12" rx="3" fill="#3b82f6" fill-opacity="0.3"/>
            <text x="65" y="79" fill="#93c5fd" font-size="7" font-family="sans-serif">📄 Project_Brief.pdf</text>
            <rect x="60" y="88" width="70" height="12" rx="3" fill="#333"/>
            <text x="65" y="97" fill="#ccc" font-size="7" font-family="sans-serif">📁 CodeRepository</text>
            <!-- Terminal Window -->
            <rect x="180" y="100" width="180" height="100" rx="8" fill="#0d1117" stroke="#30363d" stroke-width="1"/>
            <text x="190" y="120" fill="#38bdf8" font-size="7" font-family="monospace">sddsd@MacBook ~ % agy</text>
            <text x="190" y="135" fill="#a1a1aa" font-size="7" font-family="monospace">Antigravity daemon active</text>
            <text x="190" y="150" fill="#34d399" font-size="7" font-family="monospace">● Clamshell Keep-Awake ON</text>
          </svg>
        </div>
        <small style="color:#7f91a4;">MacBook Screen • ${getCurrentTime()} • 724 KB</small>
      `);
    } else if (cmd === '🔋 Status') {
      appendBotBubble(`
        💻 <strong>Apple Silicon Mac Status</strong><br><br>
        🔌 <strong>Power:</strong> Plugged into AC Power<br>
        🔋 <strong>Battery Level:</strong> 100% (Fully Charged)<br>
        ⚡ <strong>Clamshell Mode:</strong> Active (Sleep Inactive)<br>
        💾 <strong>Storage:</strong> 142 GB free of 256 GB<br>
        ⏱️ <strong>Uptime:</strong> up 7 days, 14:10
      `);
    } else if (cmd === '📂 Open Finder') {
      appendBotBubble(`
        📂 <strong>Opened Finder in:</strong><br>
        <code>~/Downloads</code><br><br>
        <strong>Contents:</strong><br>
        📄 <code>Q3_Financial_Report.pdf</code><br>
        📁 <code>Client_Presentations</code><br>
        📄 <code>Meeting_Notes.docx</code><br><br>
        💡 <em>Reply with <code>/drive &lt;file&gt;</code> to sync to Google Drive.</em>
      `);
    } else if (cmd === '💾 Google Drive') {
      appendBotBubble(`
        ✅ <strong>Shared to Google Drive!</strong><br><br>
        📄 <strong>File:</strong> <code>Q3_Financial_Report.pdf</code> (2.4 MB)<br>
        💾 <strong>Destination:</strong><br>
        <code>Google Drive &gt; My Drive &gt; Remote_Shared</code><br><br>
        Google Drive cloud client has synced this to your Android phone.
      `);
    } else if (cmd === '🤖 Antigravity AI') {
      appendBotBubble(`
        🤖 <strong>Antigravity AI Agent</strong><br><br>
        <em>Sample response:</em><br>
        Agent tasks are queued for host approval before the local CLI starts.
      `);
    } else if (cmd === '🔒 Lock Screen') {
      appendBotBubble(`
        🔒 <strong>Mac display turned off and screen locked.</strong><br>
        System assertions remain active to process background commands.
      `);
    } else {
      appendBotBubble(`
        <strong>Demo only</strong><br>
        No command was sent to a computer. Use a built-in action in the real app, or submit an explicit agent prompt for host approval.
      `);
    }
  }, 400);
}

function sendCustomCommand() {
  const input = document.getElementById('customInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  simulateCommand(text);
}

const menuButton = document.querySelector('.mobile-menu-toggle');
const primaryNav = document.getElementById('primaryNav');

if (menuButton && primaryNav) {
  menuButton.addEventListener('click', () => {
    const expanded = menuButton.getAttribute('aria-expanded') === 'true';
    menuButton.setAttribute('aria-expanded', String(!expanded));
    menuButton.setAttribute('aria-label', expanded ? 'Open navigation' : 'Close navigation');
    primaryNav.classList.toggle('mobile-open', !expanded);
  });

  primaryNav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      menuButton.setAttribute('aria-expanded', 'false');
      menuButton.setAttribute('aria-label', 'Open navigation');
      primaryNav.classList.remove('mobile-open');
    });
  });
}

const revealElements = document.querySelectorAll(
  '.hero-container > *, .section-header, .simulator-wrapper, .matrix-card, .architecture-diagram, .feature-card, .setup-step',
);

if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  revealElements.forEach((element, index) => {
    element.classList.add('reveal');
    element.style.transitionDelay = `${Math.min(index % 5, 4) * 70}ms`;
  });
  document.documentElement.classList.add('motion-ready');

  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('reveal-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -36px 0px' });

  revealElements.forEach((element) => revealObserver.observe(element));
}
