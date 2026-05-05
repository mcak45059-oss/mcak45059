(() => {
  const form = document.getElementById('waitlist-form');
  const status = document.getElementById('form-status');
  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();
  if (!form) return;

  const FALLBACK_EMAIL = 'hello@apexfilms.example';
  const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

  const setStatus = (msg, kind) => {
    status.textContent = msg;
    status.classList.remove('success', 'error');
    if (kind) status.classList.add(kind);
  };

  const buildMailto = (data) => {
    const subject = `Apex Films waitlist — ${data.name || 'new lead'}`;
    const body = Object.entries(data)
      .filter(([k]) => k !== 'website')
      .map(([k, v]) => `${k}: ${v || '-'}`)
      .join('\n');
    return `mailto:${FALLBACK_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const data = Object.fromEntries(fd.entries());

    if (data.website) return; // honeypot
    if (!data.name || !isEmail(data.email) || !data.project_type) {
      setStatus('Please add your name, a valid email, and a project type.', 'error');
      return;
    }

    setStatus('Sending…');
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('bad status');
      form.reset();
      setStatus("You're on the list — we'll reach out within 24 hours.", 'success');
    } catch (err) {
      setStatus('Network unavailable — opening your email client as a fallback…', 'error');
      window.location.href = buildMailto(data);
    }
  });
})();
