/**
 * intelligence.js
 * College Intelligence tab.
 * Renders plain text reports with styled CAPITAL LETTER section headings.
 * No markdown parsing — just clean formatted prose.
 */

// ---------------------------------------------------------------------------
// Plain text renderer
// Detects CAPITAL LETTER section headings and styles them.
// Everything else is rendered as readable paragraphs.
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelRenderText = function (text) {
    if (!text || !text.trim()) {
        return '<p class="text-sm text-gray-400 italic">No content available.</p>';
    }

    const lines = text.split('\n');
    let html = '';
    let inPara = false;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();

        if (!trimmed) {
            if (inPara) {
                html += '</p>';
                inPara = false;
            }
            continue;
        }

        // Detect section heading: all caps, no special chars, reasonable length
        // e.g. "PLACEMENTS", "ACADEMIC PROGRAMS AND DEPARTMENTS"
        const isHeading = (
            trimmed === trimmed.toUpperCase() &&
            trimmed.length >= 3 &&
            trimmed.length <= 80 &&
            /^[A-Z][A-Z\s,\/\(\)\-&]+$/.test(trimmed) &&
            !trimmed.match(/^\d/)
        );

        if (isHeading) {
            if (inPara) { html += '</p>'; inPara = false; }
            html += `<h3 class="intel-section-heading">${this._ie(trimmed)}</h3>`;
        } else {
            if (!inPara) {
                html += '<p class="intel-para">';
                inPara = true;
            } else {
                html += ' ';
            }
            html += this._ie(trimmed);
        }
    }

    if (inPara) html += '</p>';
    return html;
};

// ---------------------------------------------------------------------------
// Load cached profile when college changes
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype.loadIntelligenceProfile = function () {
    this._intelReset();
    if (!this.selectedCollege) return;

    fetch(`/api/college/profile/${encodeURIComponent(this.selectedCollege)}`)
        .then(r => r.ok ? r.json() : {})
        .then(profile => {
            if (profile && (profile.official || profile.external)) {
                this._intelRender(profile, true);
            }
        })
        .catch(() => {});
};

// ---------------------------------------------------------------------------
// Main collect
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelCollect = async function (forceRefresh) {
    if (!this.selectedCollege || this._intelLoading) return;

    this._intelSetLoading(true);
    this._intelReset();

    try {
        const res = await fetch('/api/college/collect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                college_name: this.selectedCollege,
                force_refresh: !!forceRefresh,
            }),
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Server error ${res.status}`);

        this._intelRender(data.profile || {}, !!data.cached);

        if (data.errors) this._intelShowPartialErrors(data.errors);

    } catch (err) {
        const el = document.getElementById('intelTopError');
        if (el) { el.textContent = err.message || String(err); el.classList.remove('hidden'); }
    } finally {
        this._intelSetLoading(false);
    }
};

// ---------------------------------------------------------------------------
// Manual URL override
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelManualConfirm = async function () {
    if (!this.selectedCollege) return;
    const input = document.getElementById('intelManualUrlInput');
    const url = (input && input.value.trim()) || '';
    if (!url) { alert('Please enter a URL'); return; }

    const btn = document.getElementById('intelManualConfirmBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

    try {
        const res = await fetch('/api/college/confirm-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ college_name: this.selectedCollege, url }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Server error ${res.status}`);
        document.getElementById('intelManualSection')?.classList.add('hidden');
        await this._intelCollect(true);
    } catch (err) {
        alert(err.message || String(err));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Save & collect'; }
    }
};

// ---------------------------------------------------------------------------
// Render full profile
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelRender = function (profile, cached) {
    // URL row
    if (profile.official_url) {
        const urlEl = document.getElementById('intelDetectedUrl');
        if (urlEl) {
            urlEl.innerHTML = `
                <span class="text-gray-400 text-xs">Official URL:</span>
                <a href="${this._ie(profile.official_url)}" target="_blank" rel="noopener"
                   class="underline text-indigo-500 text-xs ml-1">${this._ie(profile.official_url)}</a>
                ${profile.official_url_confirmed
                    ? '<span class="ml-1 text-green-500 text-xs">confirmed</span>'
                    : `<span class="ml-1 text-orange-400 text-xs">unconfirmed</span>
                       <button id="intelFixUrlBtn" class="ml-2 text-xs text-indigo-500 underline">Fix URL</button>`}
            `;
            urlEl.classList.remove('hidden');
            document.getElementById('intelFixUrlBtn')?.addEventListener('click', () => {
                document.getElementById('intelManualSection')?.classList.toggle('hidden');
            });
        }
    }

    document.getElementById('intelCachedBadge')?.classList.toggle('hidden', !cached);

    if (profile.updated_at) {
        const ts = document.getElementById('intelTimestamp');
        if (ts) {
            ts.textContent = `Last updated: ${new Date(profile.updated_at).toLocaleString()}`;
            ts.classList.remove('hidden');
        }
    }

    this._intelRenderOfficial(profile.official || {});
    this._intelRenderExternal(profile.external || {});

    document.getElementById('intelResults')?.classList.remove('hidden');
};

// ---------------------------------------------------------------------------
// Official section
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelRenderOfficial = function (data) {
    const wrap    = document.getElementById('intelOfficialWrap');
    const content = document.getElementById('intelOfficialContent');
    if (!wrap || !content) return;

    wrap.classList.remove('hidden');

    const pages = data.pages_crawled || [];
    const scrapeMethod = data.scrape_method || '';

    let metaHtml = '';

    if (pages.length) {
        metaHtml += `<div class="intel-meta">
            <span class="intel-meta-label">Pages crawled:</span>
            ${pages.map(p => {
                const path = p.replace(/https?:\/\/[^/]+/, '') || '/';
                return `<a href="${this._ie(p)}" target="_blank" rel="noopener"
                    class="intel-page-pill">${this._ie(path)}</a>`;
            }).join('')}
        </div>`;
    }

    if (scrapeMethod === 'gemini_grounding_fallback') {
        metaHtml += `<div class="intel-notice intel-notice-warn">
            Direct scraping was blocked by the website. Data retrieved via Google Search.
        </div>`;
    }

    const textContent = data.text || data.markdown || '';

    content.innerHTML = metaHtml + `<div class="intel-body">${this._intelRenderText(textContent)}</div>`;
};

// ---------------------------------------------------------------------------
// External section
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelRenderExternal = function (data) {
    const wrap    = document.getElementById('intelExternalWrap');
    const content = document.getElementById('intelExternalContent');
    if (!wrap || !content) return;

    wrap.classList.remove('hidden');

    const sources = data.sources || [];
    let metaHtml = `<div class="intel-notice intel-notice-info">
        Excluded sources: CollegeDuniya, Careers360, Shiksha
    </div>`;

    if (sources.length) {
        metaHtml += `<div class="intel-meta">
            <span class="intel-meta-label">Sources used:</span>
            ${sources.slice(0, 20).map(src => `
                <a href="${this._ie(src.link)}" target="_blank" rel="noopener"
                   class="intel-source-pill">${this._ie(src.title || src.link)}</a>
            `).join('')}
        </div>`;
    }

    const textContent = data.text || data.markdown || '';

    content.innerHTML = metaHtml + `<div class="intel-body">${this._intelRenderText(textContent)}</div>`;
};

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelSetLoading = function (on) {
    this._intelLoading = !!on;
    const genBtn   = document.getElementById('intelGenerateBtn');
    const regenBtn = document.getElementById('intelRegenerateBtn');
    const progress = document.getElementById('intelProgress');

    if (genBtn) {
        genBtn.disabled = on;
        genBtn.innerHTML = on
            ? '<i class="fas fa-spinner fa-spin mr-2"></i>Collecting data…'
            : '<i class="fas fa-brain mr-2"></i>Generate College Intelligence';
    }
    if (regenBtn) regenBtn.disabled = on;
    if (progress) progress.classList.toggle('hidden', !on);
};

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelReset = function () {
    [
        'intelResults', 'intelOfficialWrap', 'intelExternalWrap',
        'intelTopError', 'intelPartialErrors', 'intelDetectedUrl',
        'intelCachedBadge', 'intelTimestamp', 'intelProgress',
    ].forEach(id => document.getElementById(id)?.classList.add('hidden'));

    const oc = document.getElementById('intelOfficialContent');
    if (oc) oc.innerHTML = '';
    const ec = document.getElementById('intelExternalContent');
    if (ec) ec.innerHTML = '';
    const ms = document.getElementById('intelManualSection');
    if (ms) ms.classList.add('hidden');
    const mi = document.getElementById('intelManualUrlInput');
    if (mi) mi.value = '';
};

// ---------------------------------------------------------------------------
// Partial errors
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._intelShowPartialErrors = function (errors) {
    const el = document.getElementById('intelPartialErrors');
    if (!el || !errors) return;
    const items = Object.entries(errors)
        .map(([k, v]) => `<span class="block"><b>${this._ie(k)}:</b> ${this._ie(v)}</span>`)
        .join('');
    if (!items) return;
    el.innerHTML = items;
    el.classList.remove('hidden');
};

// ---------------------------------------------------------------------------
// HTML escape
// ---------------------------------------------------------------------------

CollegePlacementDashboard.prototype._ie = function (text) {
    const div = document.createElement('div');
    div.textContent = String(text ?? '');
    return div.innerHTML;
};

// ---------------------------------------------------------------------------
// Wire buttons
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        const d = window.dashboard;
        if (!d) { console.error('intelligence.js: window.dashboard not found'); return; }
        document.getElementById('intelGenerateBtn')
            ?.addEventListener('click', () => d._intelCollect(false));
        document.getElementById('intelRegenerateBtn')
            ?.addEventListener('click', () => d._intelCollect(true));
        document.getElementById('intelManualConfirmBtn')
            ?.addEventListener('click', () => d._intelManualConfirm());
    }, 0);
});