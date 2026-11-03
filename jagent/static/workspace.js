// Opportunity navigation and review feedback; activeId selects a brief, mobile controls list/detail visibility.
(() => {
  const mobile = window.matchMedia('(max-width: 900px)');
  let activeId;
  let pending = false;
  const rows = () => [...document.querySelectorAll('.index-row')];
  const feedback = (message, error = false) => {
    const node = document.getElementById('workspace-feedback');
    node.textContent = message;
    node.classList.toggle('is-error', error);
    node.setAttribute('role', error ? 'alert' : 'status');
  };
  function select(id, open = false, focus = false) {
    const row = rows().find(item => item.dataset.posting === id);
    if (!row) return;
    activeId = id;
    rows().forEach(item => {
      if (item === row) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
    });
    document.querySelectorAll('.opportunity-detail').forEach(panel => {
      panel.hidden = panel.id !== `posting-${id}`;
    });
    const workspace = document.querySelector('.opportunity-workspace');
    if (open) workspace.classList.add('detail-open');
    if (focus) {
      const panel = document.getElementById(`posting-${id}`);
      panel.focus({preventScroll: true});
      if (mobile.matches) workspace.scrollIntoView({block: 'start'});
      else document.querySelector('.intelligence-panel').scrollTop = 0;
    }
  }
  function initialize(preferred, open = false) {
    const index = rows();
    if (!index.length) return;
    document.querySelector('.opportunity-workspace').classList.add('enhanced');
    const fromHash = location.hash.match(/^#posting-(\d+)$/)?.[1];
    const id = [preferred, fromHash, index[0].dataset.posting].find(value => index.some(row => row.dataset.posting === value));
    select(id, open || Boolean(fromHash));
  }
  document.addEventListener('click', event => {
    const row = event.target.closest('.index-row');
    if (row) {
      event.preventDefault();
      select(row.dataset.posting, true, true);
      history.replaceState(null, '', row.hash);
    }
    if (event.target.closest('.back-to-index')) {
      document.querySelector('.opportunity-workspace').classList.remove('detail-open');
      rows().find(row => row.dataset.posting === activeId)?.focus();
      history.replaceState(null, '', location.pathname + location.search);
    }
  });
  document.addEventListener('keydown', event => {
    if (event.ctrlKey || event.altKey || event.metaKey || event.target.closest('input, textarea, select, [contenteditable]')) return;
    if (event.key === '/' && document.getElementById('q')) {
      event.preventDefault();
      document.getElementById('q').focus();
    }
    const row = event.target.closest('.index-row');
    if (row && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const index = rows();
      const position = index.indexOf(row);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? index.length - 1 : Math.max(0, Math.min(index.length - 1, position + (event.key === 'ArrowDown' ? 1 : -1)));
      index[next].focus();
      select(index[next].dataset.posting);
      history.replaceState(null, '', index[next].hash);
    }
    if (event.key === 'Escape' && mobile.matches) document.querySelector('.opportunity-detail:not([hidden]) .back-to-index')?.click();
  });
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches('.review-form') || !event.submitter) return;
    event.preventDefault();
    if (pending) return;
    const action = event.submitter.value;
    const values = new URLSearchParams(new FormData(form));
    values.set('action', action);
    const index = rows();
    const position = index.findIndex(row => row.dataset.posting === activeId);
    const nextId = action === 'later' ? activeId : (index[position + 1] || index[position - 1])?.dataset.posting;
    const wasOpen = document.querySelector('.opportunity-workspace').classList.contains('detail-open');
    pending = true;
    form.setAttribute('aria-busy', 'true');
    [...form.elements].filter(item => item.tagName === 'BUTTON').forEach(button => button.disabled = true);
    feedback('Recording your decision…');
    try {
      const response = await fetch(form.getAttribute('action'), {method: 'POST', body: values, headers: {'HX-Request': 'true'}});
      if (!response.ok) throw new Error(`Review returned ${response.status}`);
      const fragment = new DOMParser().parseFromString(await response.text(), 'text/html');
      const queue = fragment.getElementById('queue-content');
      if (!queue) throw new Error('Missing queue');
      document.getElementById('queue-content').replaceWith(queue);
      const banner = fragment.getElementById('health-banner');
      if (banner) document.getElementById('health-banner')?.replaceWith(banner);
      history.replaceState(null, '', location.pathname + location.search);
      initialize(nextId, wasOpen);
      if (activeId && rows().length) {
        if (mobile.matches && wasOpen) document.getElementById(`posting-${activeId}`)?.focus({preventScroll: true});
        else rows().find(row => row.dataset.posting === activeId)?.focus({preventScroll: true});
      }
      feedback(action === 'later' ? 'Saved for later. Your notes are recorded.' : action === 'skip' ? 'Opportunity skipped. Your reason and notes are recorded.' : 'Application recorded. View it in Applied.');
    } catch {
      feedback('Could not confirm your decision. Your notes are still here. Try again or reload to check the saved state.', true);
    } finally {
      pending = false;
      form.removeAttribute('aria-busy');
      [...form.elements].filter(item => item.tagName === 'BUTTON').forEach(button => button.disabled = button.classList.contains('brief-save') && button.textContent === 'Saved for later');
    }
  });
  document.addEventListener('submit', event => {
    if (!event.target.matches('.profile-form, .filter-form')) return;
    event.target.setAttribute('aria-busy', 'true');
    const button = event.target.querySelector('button[type="submit"]');
    button.textContent = 'Saving…';
    button.disabled = true;
  });
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('.profile-form, .filter-form').forEach(form => {
      form.removeAttribute('aria-busy');
      const button = form.querySelector('button[type="submit"]');
      button.disabled = false;
      button.textContent = form.matches('.profile-form') ? 'Save profile' : 'Save preferences and update queue';
    });
  });
  initialize();
})();
