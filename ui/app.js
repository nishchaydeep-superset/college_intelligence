class CollegePlacementDashboard {
    constructor() {
        this.collegeData = null;
        this.generalData = null;
        this.redditData = null;
        this.activeGeneralSubTab = 'overview';
        this.placementSeasons = {};
        this.selectedCollege = null;
        this.selectedSource = '';
        this.cacheKey = 'college_placement_data';
        this.cacheExpiry = 300 * 60 * 1000; // 300 minutes
        /** @type {Record<string, Array<{role: string, content: string}>>} */
        this.researchChatByCollege = {};
        this.researchLoading = false;

        this.init();
    }

    normalizeKey(key) {
        if (!key) return '';
        return key.toLowerCase()
            .replace(/&/g, 'and')
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
    }

    getGeneralDataForCollege(collegeName) {
        if (!this.generalData || !collegeName) return null;
        if (this.generalData[collegeName]) return this.generalData[collegeName];
        const normSelected = this.normalizeKey(collegeName);
        const matchingKey = Object.keys(this.generalData).find(k => this.normalizeKey(k) === normSelected);
        return matchingKey ? this.generalData[matchingKey] : null;
    }

    getPlacementSeasonForCollege(collegeName) {
        if (!this.placementSeasons || !collegeName) return null;
        if (this.placementSeasons[collegeName]) return this.placementSeasons[collegeName];
        const normSelected = this.normalizeKey(collegeName);
        const matchingKey = Object.keys(this.placementSeasons).find(k => this.normalizeKey(k) === normSelected);
        return matchingKey ? this.placementSeasons[matchingKey] : null;
    }

    async init() {
        this.setupEventListeners();
        await this.loadData();
        this.populateCollegeDropdown();
        this.hideLoading();
    }

    setupEventListeners() {
        document.getElementById('collegeSelect').addEventListener('change', (e) => {
            this.selectedCollege = e.target.value;
            this.updateSourceDropdown();
            this.displayCollegeData();
        });

        document.getElementById('sourceSelect').addEventListener('change', (e) => {
            this.selectedSource = e.target.value;
            this.displayCollegeData();
        });

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tab = e.currentTarget.dataset.tab;
                if (tab) this.switchTab(tab);
            });
        });

        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.refreshData();
        });

        const reportBtn = document.getElementById('researchReportBtn');
        if (reportBtn) {
            reportBtn.addEventListener('click', () => this.runResearchReport({ forceRefresh: false }));
        }
        const regenBtn = document.getElementById('researchRegenerateBtn');
        if (regenBtn) {
            regenBtn.addEventListener('click', () => this.runResearchReport({ forceRefresh: true }));
        }
        const researchForm = document.getElementById('researchChatForm');
        if (researchForm) {
            researchForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.submitResearchFollowUp();
            });
        }

    }

    async loadData() {
        try {
            try {
                let seasonRes = await fetch(`/data/placement_seasons.json?t=${Date.now()}`);
                if (!seasonRes.ok) seasonRes = await fetch(`/data/placement_seasons.json.bak?t=${Date.now()}`);
                if (seasonRes.ok) {
                    this.placementSeasons = await seasonRes.json();
                } else {
                    this.placementSeasons = {};
                }
            } catch (e) {
                this.placementSeasons = {};
            }

            // Fetch general profile data
            try {
                let generalRes = await fetch(`/data/college_general_data.json?t=${Date.now()}`);
                if (!generalRes.ok) generalRes = await fetch(`/data/college_general_data.json.bak?t=${Date.now()}`);
                if (generalRes.ok) {
                    this.generalData = await generalRes.json();
                } else {
                    let fallback = await fetch(`../data/college_general_data.json?t=${Date.now()}`);
                    if (!fallback.ok) fallback = await fetch(`../data/college_general_data.json.bak?t=${Date.now()}`);
                    if (fallback.ok) {
                        this.generalData = await fallback.json();
                    } else {
                        this.generalData = {};
                    }
                }
            } catch (e) {
                console.error('Error loading college general data:', e);
                this.generalData = {};
            }

            // Fetch Reddit data
            try {
                let redditRes = await fetch(`/data/college_reddit_data.json?t=${Date.now()}`);
                if (!redditRes.ok) redditRes = await fetch(`/data/college_reddit_data.json.bak?t=${Date.now()}`);
                if (redditRes.ok) {
                    this.redditData = await redditRes.json();
                } else {
                    let fallback = await fetch(`../data/college_reddit_data.json?t=${Date.now()}`);
                    if (!fallback.ok) fallback = await fetch(`../data/college_reddit_data.json.bak?t=${Date.now()}`);
                    if (fallback.ok) {
                        this.redditData = await fallback.json();
                    } else {
                        this.redditData = {};
                    }
                }
            } catch (e) {
                console.error('Error loading Reddit data:', e);
                this.redditData = {};
            }

            const cachedData = this.getCachedData();
            if (cachedData) {
                this.collegeData = cachedData;
                this.updateDataStatus('cached');
                return;
            }

            let response = await fetch(`/data/college_placement_data.json?t=${Date.now()}`);
            if (!response.ok) response = await fetch(`/data/college_placement_data.json.bak?t=${Date.now()}`);
            
            if (!response.ok) {
                let fallback = await fetch(`../data/college_placement_data.json?t=${Date.now()}`);
                if (!fallback.ok) fallback = await fetch(`../data/college_placement_data.json.bak?t=${Date.now()}`);
                if (!fallback.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await fallback.json();
                this.collegeData = data;
                this.setCachedData(data);
                this.updateDataStatus('loaded');
                return;
            }

            const data = await response.json();
            this.collegeData = data;
            this.setCachedData(data);
            this.updateDataStatus('loaded');

        } catch (error) {
            console.error('Error loading data:', error);
            this.showError('Failed to load college placement data. Please try again.');
        }
    }

    getCachedData() {
        try {
            const cached = localStorage.getItem(this.cacheKey);
            if (!cached) return null;
            const { data, timestamp } = JSON.parse(cached);
            if (Date.now() - timestamp > this.cacheExpiry) {
                localStorage.removeItem(this.cacheKey);
                return null;
            }
            return data;
        } catch (error) {
            return null;
        }
    }

    setCachedData(data) {
        try {
            localStorage.setItem(this.cacheKey, JSON.stringify({ data, timestamp: Date.now() }));
        } catch (error) { }
    }

    async refreshData() {
        this.showLoading();
        localStorage.removeItem(this.cacheKey);
        await this.loadData();
        this.populateCollegeDropdown();
        this.hideLoading();
    }

    populateCollegeDropdown() {
        if (!this.collegeData) return;
        const select = document.getElementById('collegeSelect');
        select.innerHTML = '<option value="">Choose a college...</option>';
        Object.keys(this.collegeData).sort().forEach(collegeName => {
            const option = document.createElement('option');
            option.value = collegeName;
            option.textContent = collegeName;
            select.appendChild(option);
        });
    }

    updateSourceDropdown() {
        if (!this.selectedCollege) return;
        const select = document.getElementById('sourceSelect');
        const collegeEntry = this.collegeData[this.selectedCollege];
        const sources = (collegeEntry && collegeEntry.data_sources) || [];
        select.innerHTML = '<option value="">All Sources</option>';
        sources.forEach(source => {
            const option = document.createElement('option');
            option.value = source;
            option.textContent = source.charAt(0).toUpperCase() + source.slice(1);
            select.appendChild(option);
        });
    }

    displayCollegeData() {
        if (!this.selectedCollege) {
            document.getElementById('collegeDetails').classList.add('hidden');
            return;
        }

        const collegeData = this.collegeData[this.selectedCollege];
        if (!collegeData) return;

        document.getElementById('collegeDetails').classList.remove('hidden');

        this.displayPlacementSeason(this.selectedCollege);
        this.displayTopCompanies(collegeData);
        this.displayRawData(collegeData);
        this.updateResearchTabForCollege();
        this.displayGeneralProfile();
        this.displayRedditData(this.selectedCollege);

        // Load cached intelligence profile for the new college
        if (typeof this.loadIntelligenceProfile === 'function') {
            this.loadIntelligenceProfile();
        }

        this.switchTab('season');
    }

    updateResearchTabForCollege() {
        const input = document.getElementById('researchChatInput');
        const sendBtn = document.getElementById('researchSendBtn');
        const reportBtn = document.getElementById('researchReportBtn');
        if (!input || !sendBtn || !reportBtn) return;

        if (this.selectedCollege) {
            input.disabled = false;
            sendBtn.disabled = false;
            reportBtn.disabled = false;
            const regenBtn = document.getElementById('researchRegenerateBtn');
            if (regenBtn) regenBtn.disabled = false;
        } else {
            input.disabled = true;
            sendBtn.disabled = true;
            reportBtn.disabled = true;
            const regenBtn = document.getElementById('researchRegenerateBtn');
            if (regenBtn) regenBtn.disabled = true;
        }
        this.showResearchCachedNotice(false);
        this.updateResearchSources([]);
        this.renderResearchChat();
    }

    getResearchMessages() {
        if (!this.selectedCollege) return [];
        if (!this.researchChatByCollege[this.selectedCollege]) {
            this.researchChatByCollege[this.selectedCollege] = [];
        }
        return this.researchChatByCollege[this.selectedCollege];
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatAssistantHtml(markdown) {
        if (typeof marked !== 'undefined' && marked.parse) {
            return marked.parse(markdown, { breaks: true });
        }
        return `<pre class="whitespace-pre-wrap text-sm text-gray-800">${this.escapeHtml(markdown)}</pre>`;
    }

    renderResearchChat() {
        const container = document.getElementById('researchChatMessages');
        if (!container) return;

        const messages = this.getResearchMessages();
        container.innerHTML = '';

        if (messages.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'text-sm text-gray-500 text-center py-8';
            empty.textContent = 'No messages yet. Use "Search & generate report" or type a question and send.';
            container.appendChild(empty);
            return;
        }

        messages.forEach((msg) => {
            const wrap = document.createElement('div');
            wrap.className = 'flex ' + (msg.role === 'user' ? 'justify-end' : 'justify-start');
            const bubble = document.createElement('div');
            bubble.className =
                'max-w-[85%] px-4 py-3 text-sm shadow-sm ' +
                (msg.role === 'user'
                    ? 'research-bubble-user text-gray-900'
                    : 'research-bubble-assistant text-gray-800 prose prose-sm max-w-none');
            if (msg.role === 'user') {
                bubble.innerHTML = this.escapeHtml(msg.content).replace(/\n/g, '<br>');
            } else {
                bubble.innerHTML = this.formatAssistantHtml(msg.content);
            }
            wrap.appendChild(bubble);
            container.appendChild(wrap);
        });

        container.scrollTop = container.scrollHeight;
    }

    setResearchLoading(on) {
        this.researchLoading = !!on;
        const reportBtn = document.getElementById('researchReportBtn');
        const sendBtn = document.getElementById('researchSendBtn');
        const input = document.getElementById('researchChatInput');
        const regenBtn = document.getElementById('researchRegenerateBtn');
        if (reportBtn) {
            reportBtn.disabled = on || !this.selectedCollege;
            if (on) reportBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Working…';
            else reportBtn.innerHTML = '<i class="fas fa-search mr-2"></i>Search &amp; generate report';
        }
        if (regenBtn) regenBtn.disabled = on || !this.selectedCollege;
        if (sendBtn) sendBtn.disabled = on || !this.selectedCollege;
        if (input) input.disabled = on || !this.selectedCollege;
    }

    updateResearchSources(sources) {
        const panel = document.getElementById('researchSourcesPanel');
        const list = document.getElementById('researchSourcesList');
        if (!panel || !list) return;
        if (!sources || sources.length === 0) {
            panel.classList.add('hidden');
            list.innerHTML = '';
            return;
        }
        panel.classList.remove('hidden');
        list.innerHTML = sources
            .map(s => `<li><a href="${this.escapeHtml(s.link)}" target="_blank" rel="noopener noreferrer" class="underline">${this.escapeHtml(s.title || s.link)}</a></li>`)
            .join('');
    }

    showResearchCachedNotice(visible) {
        const el = document.getElementById('researchCacheBadge');
        if (!el) return;
        if (visible) el.classList.remove('hidden');
        else el.classList.add('hidden');
    }

    async postResearch(payload) {
        const res = await fetch('/api/placement-research', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.status === 501) {
            throw new Error('Research API is unavailable. Start the app server and reload the page.');
        }
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            let detail = data.detail || data.message || res.statusText;
            if (Array.isArray(detail)) {
                detail = detail.map(d => (d && d.msg) || JSON.stringify(d)).join('; ');
            }
            throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }
        return data;
    }

    buildServerMessages() {
        return this.getResearchMessages().map(m => ({ role: m.role, content: m.content }));
    }

    async runResearchReport(opts = {}) {
        if (!this.selectedCollege || this.researchLoading) return;
        const forceRefresh = !!opts.forceRefresh;
        this.setResearchLoading(true);
        try {
            const data = await this.postResearch({
                college_name: this.selectedCollege,
                main_report: true,
                force_refresh: forceRefresh,
                messages: []
            });
            this.researchChatByCollege[this.selectedCollege] = [
                { role: 'assistant', content: data.reply || '(No report)' }
            ];
            this.updateResearchSources(data.sources || []);
            this.showResearchCachedNotice(!!data.cached);
            this.renderResearchChat();
        } catch (err) {
            alert(err.message || String(err));
        } finally {
            this.setResearchLoading(false);
        }
    }

    async submitResearchFollowUp() {
        if (!this.selectedCollege || this.researchLoading) return;
        const input = document.getElementById('researchChatInput');
        const text = (input && input.value.trim()) || '';
        if (!text) return;

        const msgs = this.getResearchMessages();
        msgs.push({ role: 'user', content: text });
        if (input) input.value = '';
        this.showResearchCachedNotice(false);
        this.renderResearchChat();
        this.setResearchLoading(true);

        try {
            const data = await this.postResearch({
                college_name: this.selectedCollege,
                main_report: false,
                force_refresh: false,
                messages: this.buildServerMessages()
            });
            msgs.push({ role: 'assistant', content: data.reply || '(No reply)' });
            this.updateResearchSources(data.sources || []);
            this.renderResearchChat();
        } catch (err) {
            msgs.pop();
            this.renderResearchChat();
            alert(err.message || String(err));
        } finally {
            this.setResearchLoading(false);
        }
    }

    displayRedditData(collegeName) {
        const container = document.getElementById('redditContent');
        if (!container) return;

        if (!this.redditData || !this.redditData[collegeName]) {
            container.innerHTML = '<p class="text-gray-500 text-sm">No Reddit discussion data available for this college. Run the Reddit scraper to collect data.</p>';
            return;
        }

        const data = this.redditData[collegeName];
        const threads = data.threads || [];

        if (threads.length === 0) {
            container.innerHTML = '<p class="text-gray-500 text-sm">No Reddit discussion threads found for this college.</p>';
            return;
        }

        this.renderRedditThreads(threads, data.scraped_at);
    }

    renderRedditThreads(threads, scrapedAt) {
        const container = document.getElementById('redditContent');
        if (!container) return;

        if (threads.length === 0) {
            container.innerHTML = `
                <div class="text-center py-12 bg-white border border-gray-200 rounded-lg shadow-sm">
                    <i class="fab fa-reddit text-gray-300 text-4xl mb-3"></i>
                    <p class="text-gray-500 text-sm">No Reddit discussion threads found for this college.</p>
                </div>
            `;
            return;
        }

        const scrapedTime = scrapedAt ? new Date(scrapedAt).toLocaleString() : 'N/A';

        container.innerHTML = `
            <div class="mb-4 text-sm flex justify-between items-center">
                <span class="inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-50 border border-indigo-100 text-indigo-700 text-xs font-semibold rounded-full">
                    <i class="fab fa-reddit text-orange-500"></i> Found: ${threads.length} Thread(s)
                </span>
                <span class="text-xs text-gray-400">Last Scraped: ${scrapedTime}</span>
            </div>
            <div class="space-y-6">
                ${threads.map((thread, idx) => `
                    <div class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm hover:shadow-md transition-all duration-300 relative overflow-hidden group">
                        <!-- Top Accent Line (Reddit Themed Gradient) -->
                        <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-orange-500 to-red-500 transform scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left"></div>
                        
                        <!-- Thread Header -->
                        <div class="flex flex-wrap justify-between items-start gap-3 border-b border-gray-100 pb-3 mb-4">
                            <h4 class="text-md font-semibold text-gray-900 flex-1 min-w-[250px] leading-snug">
                                <a href="${thread.url}" target="_blank" rel="noopener noreferrer" class="hover:text-indigo-600 hover:underline flex items-start gap-2.5 transition-colors">
                                    <i class="fab fa-reddit text-orange-500 text-xl mt-0.5 shrink-0 group-hover:scale-110 transition-transform duration-200"></i>
                                    <span>${this.escapeHtml(thread.title)}</span>
                                </a>
                            </h4>
                            <span class="text-xs font-medium px-2.5 py-1 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-full shrink-0">
                                r/${this.escapeHtml(thread.subreddit)}
                            </span>
                        </div>
                        
                        <!-- OP Selftext -->
                        ${thread.selftext ? `
                            <div class="text-sm text-gray-700 bg-gray-50 rounded-lg p-3.5 mb-4 whitespace-pre-wrap border border-gray-100">
                                <span class="font-bold text-xs text-gray-400 uppercase tracking-wider block mb-1.5">Original Post (by ${this.escapeHtml(thread.author)}):</span>
                                <div class="text-gray-800 leading-relaxed font-sans">${this.escapeHtml(thread.selftext)}</div>
                            </div>
                        ` : ''}

                        <!-- Comments Section -->
                        <div class="space-y-3">
                            <div class="flex items-center gap-2 border-t border-gray-100 pt-3">
                                <span class="text-xs font-bold text-gray-400 uppercase tracking-wider">Top Comments (${thread.comments ? thread.comments.length : 0})</span>
                            </div>
                            ${thread.comments && thread.comments.length > 0 ? `
                                <div class="space-y-3">
                                    ${thread.comments.map(comment => `
                                        <div class="bg-gray-50 rounded-lg p-3 text-sm border border-gray-100 hover:border-gray-200 transition-colors">
                                            <div class="flex items-center justify-between mb-1.5 border-b border-gray-100/50 pb-1">
                                                <span class="font-bold text-xs text-gray-500 flex items-center gap-1">
                                                    <i class="fas fa-user-circle text-gray-400 text-xs"></i>
                                                    ${this.escapeHtml(comment.author)}
                                                </span>
                                            </div>
                                            <p class="text-gray-800 leading-relaxed">${this.escapeHtml(comment.body)}</p>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : `
                                <p class="text-xs text-gray-400 italic">No comments found or thread is empty.</p>
                            `}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    displayPlacementSeason(collegeName) {
        const container = document.getElementById('placementSeasonPanel');
        if (!container) return;

        const season = this.getPlacementSeasonForCollege(collegeName);
        if (!season) {
            container.innerHTML = '<p class="text-gray-500 text-sm col-span-2">No placement season data available for this college.</p>';
            return;
        }

        container.innerHTML = `
            <div class="bg-blue-50 rounded-lg p-4">
                <p class="text-xs text-blue-600 font-medium uppercase tracking-wide mb-1">Placement Months</p>
                <p class="text-sm font-semibold text-gray-900">${season.placement_months || '-'}</p>
            </div>
            <div class="bg-indigo-50 rounded-lg p-4">
                <p class="text-xs text-indigo-600 font-medium uppercase tracking-wide mb-1">Peak Season</p>
                <p class="text-sm font-semibold text-gray-900">${season.placement_season || '-'}</p>
            </div>
            <div class="bg-purple-50 rounded-lg p-4">
                <p class="text-xs text-purple-600 font-medium uppercase tracking-wide mb-1">Eligible Semester</p>
                <p class="text-sm font-semibold text-gray-900">${season.eligible_semester || '-'}</p>
            </div>
            <div class="bg-green-50 rounded-lg p-4">
                <p class="text-xs text-green-600 font-medium uppercase tracking-wide mb-1">NAAC Grade</p>
                <p class="text-sm font-semibold text-gray-900">${season.NAAC_grade || '-'}</p>
            </div>
            <div class="bg-gray-50 rounded-lg p-4 col-span-2">
                <p class="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1">Notes</p>
                <p class="text-sm text-gray-700">${season.notes || '-'}</p>
            </div>
            ${season.Contact ? `
            <div class="bg-yellow-50 rounded-lg p-4 col-span-2">
                <p class="text-xs text-yellow-600 font-medium uppercase tracking-wide mb-1">Contact</p>
                <p class="text-sm text-gray-700">${season.Contact}</p>
            </div>` : ''}
        `;
    }

    displayTopCompanies(collegeData) {
        const topCompanies = document.getElementById('topCompanies');
        const companies = this.extractTopCompanies(collegeData);
        if (companies.length > 0) {
            topCompanies.innerHTML = companies.map(company =>
                `<span class="px-4 py-2 bg-green-100 text-green-800 rounded-lg font-medium">${company}</span>`
            ).join('');
        } else {
            topCompanies.innerHTML = '<p class="text-gray-500">No top companies data available</p>';
        }
    }

    displayRawData(collegeData) {
        const rawDataTables = document.getElementById('rawDataTables');
        try {
            const tables = this.createRawDataTables(collegeData);
            if (tables && tables.length > 0) {
                rawDataTables.innerHTML = tables.join('');
            } else {
                rawDataTables.innerHTML = '<p class="text-gray-500">No raw data available</p>';
            }
        } catch (error) {
            rawDataTables.innerHTML = '<p class="text-red-500">Error loading raw data</p>';
        }
    }

    extractTopCompanies(collegeData) {
        const companies = new Set();
        const sourceData = collegeData.source_data || {};

        Object.values(sourceData).forEach(source => {
            if (this.selectedSource && source.source !== this.selectedSource) return;

            if (source.top_recruiters && Array.isArray(source.top_recruiters)) {
                source.top_recruiters.forEach(company => companies.add(company));
            }

            const dataSource = source.raw_data || source.placement_statistics;
            if (dataSource && Array.isArray(dataSource)) {
                dataSource.forEach(item => {
                    if (item.rows && Array.isArray(item.rows)) {
                        const headers = item.headers || [];
                        const firstHeader = headers[0] || '';
                        if (firstHeader.toLowerCase().includes('recruiter') || firstHeader.toLowerCase().includes('company')) {
                            item.rows.forEach(row => {
                                if (Array.isArray(row)) {
                                    row.forEach(cell => {
                                        if (cell && typeof cell === 'string' && cell.length > 2) companies.add(cell);
                                    });
                                }
                            });
                        }
                    }
                    if (item.data && Array.isArray(item.data)) {
                        const headers = item.headers || [];
                        const companyColIndex = headers.findIndex(h =>
                            h.toLowerCase().includes('company') || h.toLowerCase().includes('recruiter')
                        );
                        if (companyColIndex !== -1) {
                            item.data.forEach(row => {
                                const companyName = row[headers[companyColIndex]];
                                if (companyName && typeof companyName === 'string') companies.add(companyName);
                            });
                        }
                    }
                });
            }
        });

        return Array.from(companies).sort();
    }

    createRawDataTables(collegeData) {
        const tables = [];
        const sourceData = collegeData.source_data || {};

        Object.entries(sourceData).forEach(([sourceName, source]) => {
            if (this.selectedSource && source.source !== this.selectedSource) return;
            const dataSource = source.raw_data || source.placement_statistics;
            if (dataSource && Array.isArray(dataSource)) {
                dataSource.forEach((tableData, index) => {
                    if (!tableData) return;
                    if (tableData.type === 'hierarchical') {
                        tables.push(...this.createHierarchicalTable(sourceName, tableData, index));
                    } else if (tableData.type === 'tabular') {
                        tables.push(this.createTabularTable(sourceName, tableData, index));
                    } else if (tableData.headers && tableData.rows) {
                        tables.push(this.createShikshaTable(sourceName, tableData, index));
                    } else {
                        tables.push(this.createLegacyTable(sourceName, tableData, index));
                    }
                });
            }
        });

        return tables;
    }

    createHierarchicalTable(sourceName, tableData, tableIndex) {
        const tables = [];
        const hierarchicalData = tableData.data;
        const metadata = tableData.metadata || {};

        Object.entries(hierarchicalData).forEach(([category, yearData]) => {
            if (!yearData || typeof yearData !== 'object') return;
            const yearTables = [];

            Object.entries(yearData).forEach(([year, metrics]) => {
                if (!metrics || typeof metrics !== 'object') return;
                const flatMetrics = this.flattenHierarchicalMetrics(metrics);
                if (flatMetrics.length > 0) {
                    yearTables.push(`
                        <div class="mb-6">
                            <h5 class="text-lg font-medium text-gray-800 mb-3">${year} - ${category}</h5>
                            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
                                <div class="overflow-x-auto">
                                    <table class="w-full">
                                        <thead class="bg-gray-100">
                                            <tr>
                                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">Metric</th>
                                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">Value</th>
                                            </tr>
                                        </thead>
                                        <tbody class="bg-white divide-y divide-gray-200">
                                            ${flatMetrics.map((metric, idx) =>
                        `<tr class="${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}">
                                                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">${metric.name}</td>
                                                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${metric.value}</td>
                                                </tr>`
                    ).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    `);
                }
            });

            if (yearTables.length > 0) {
                tables.push(`
                    <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                        <div class="bg-indigo-50 px-6 py-4 border-b border-gray-200">
                            <div class="flex justify-between items-center">
                                <h4 class="text-lg font-semibold text-gray-900">
                                    <i class="fas fa-layer-group mr-2 text-indigo-600"></i>
                                    ${sourceName.charAt(0).toUpperCase() + sourceName.slice(1)} - ${category}
                                </h4>
                                <span class="text-sm text-gray-600">Table ${tableIndex + 1} • Hierarchical Data</span>
                            </div>
                            ${metadata.categories ? `
                                <div class="mt-2 flex flex-wrap gap-2">
                                    <span class="text-xs text-gray-600">Categories:</span>
                                    ${metadata.categories.map(cat =>
                    `<span class="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full">${cat}</span>`
                ).join('')}
                                </div>` : ''}
                        </div>
                        <div class="p-6">${yearTables.join('')}</div>
                    </div>
                `);
            }
        });

        return tables;
    }

    createTabularTable(sourceName, tableData, tableIndex) {
        const headers = tableData.headers || [];
        const rows = tableData.data || [];
        const metadata = tableData.metadata || {};
        if (!headers.length) return '';

        const firstHeader = headers[0];
        const isHierarchical = rows.length > 0 &&
            rows.some(row => row[firstHeader] && typeof row[firstHeader] === 'string') &&
            firstHeader.includes(' ') &&
            (firstHeader.includes('Yearly') || firstHeader.includes('Placement') || firstHeader.includes('Comparison')) &&
            headers.length > 2;

        if (isHierarchical) return this.createHierarchicalFromTabular(sourceName, tableData, tableIndex);

        const displayRows = rows.length > 0 ? rows : [{}];

        return `
            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                <div class="bg-green-50 px-6 py-4 border-b border-gray-200">
                    <div class="flex justify-between items-center">
                        <h4 class="text-lg font-semibold text-gray-900">
                            <i class="fas fa-table mr-2 text-green-600"></i>
                            ${sourceName.charAt(0).toUpperCase() + sourceName.slice(1)} - ${headers[0] || 'Data Table'}
                        </h4>
                        <span class="text-sm text-gray-600">Table ${tableIndex + 1} • Tabular Data</span>
                    </div>
                    <div class="mt-2 text-sm text-gray-600">
                        ${rows.length} rows × ${headers.length} columns
                        ${metadata.total_rows ? `(${metadata.total_rows} total rows)` : ''}
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-gray-100">
                            <tr>${headers.map(h => `<th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">${h || ''}</th>`).join('')}</tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                            ${displayRows.map((row, index) =>
            `<tr class="${index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}">
                                    ${headers.map((header, colIndex) =>
                `<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                            ${(row && row[header] !== undefined) ? row[header] : (row && row[colIndex] !== undefined ? row[colIndex] : '-')}
                                        </td>`
            ).join('')}
                                </tr>`
        ).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    createHierarchicalFromTabular(sourceName, tableData, tableIndex) {
        const headers = tableData.headers || [];
        const rows = tableData.data || [];
        const tableName = headers[0];
        const yearHeaders = headers.slice(2);
        const categoryData = {};

        rows.forEach(row => {
            const metricName = row[tableName];
            if (!metricName) return;
            const yearData = {};
            yearHeaders.forEach(year => { if (row[year] !== undefined) yearData[year] = row[year]; });
            categoryData[metricName] = yearData;
        });

        const tables = [];
        Object.entries({ [tableName]: categoryData }).forEach(([category, yearData]) => {
            if (!yearData || typeof yearData !== 'object') return;
            const metricTables = [];

            Object.entries(yearData).forEach(([metric, values]) => {
                if (!values || typeof values !== 'object') return;
                const flatMetrics = Object.entries(values).map(([key, value]) => ({ name: key, value }));
                if (flatMetrics.length > 0) {
                    metricTables.push(`
                        <div class="mb-6">
                            <h5 class="text-lg font-medium text-gray-800 mb-3">${metric}</h5>
                            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
                                <div class="overflow-x-auto">
                                    <table class="w-full">
                                        <thead class="bg-gray-100"><tr>
                                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">Year</th>
                                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">Value</th>
                                        </tr></thead>
                                        <tbody class="bg-white divide-y divide-gray-200">
                                            ${flatMetrics.map((m, idx) =>
                        `<tr class="${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}">
                                                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">${m.name}</td>
                                                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${m.value}</td>
                                                </tr>`
                    ).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    `);
                }
            });

            if (metricTables.length > 0) {
                tables.push(`
                    <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                        <div class="bg-indigo-50 px-6 py-4 border-b border-gray-200">
                            <div class="flex justify-between items-center">
                                <h4 class="text-lg font-semibold text-gray-900">
                                    <i class="fas fa-layer-group mr-2 text-indigo-600"></i>
                                    ${sourceName.charAt(0).toUpperCase() + sourceName.slice(1)} - ${category}
                                </h4>
                                <span class="text-sm text-gray-600">Table ${tableIndex + 1} • Hierarchical Data</span>
                            </div>
                        </div>
                        <div class="p-6">${metricTables.join('')}</div>
                    </div>
                `);
            }
        });

        return tables.join('');
    }

    createShikshaTable(sourceName, tableData, tableIndex) {
        const headers = tableData.headers || [];
        const rows = tableData.rows || [];
        if (!headers.length) return '';

        if (headers.length === 1) {
            const allItems = rows.flat().filter(item => item && item.toString().trim() !== '');
            if (allItems.length === 0) return '';
            return `
                <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                    <div class="bg-purple-50 px-6 py-4 border-b border-gray-200">
                        <div class="flex justify-between items-center">
                            <h4 class="text-lg font-semibold text-gray-900">
                                <i class="fas fa-table mr-2 text-purple-600"></i>
                                ${sourceName.charAt(0).toUpperCase() + sourceName.slice(1)} - ${headers[0]}
                            </h4>
                            <span class="text-sm text-gray-600">Table ${tableIndex + 1} • Shiksha Format</span>
                        </div>
                        <div class="mt-2 text-sm text-gray-600">${allItems.length} items</div>
                    </div>
                    <div class="p-6">
                        <div class="flex flex-wrap gap-2">
                            ${allItems.map(item => `<span class="px-4 py-2 bg-green-100 text-green-800 rounded-lg font-medium">${item}</span>`).join('')}
                        </div>
                    </div>
                </div>
            `;
        }

        const firstHeader = headers[0];
        const isHierarchical = rows.length > 0 &&
            rows.some(row => row.length > 1) &&
            firstHeader.includes(' ') &&
            !firstHeader.toLowerCase().includes('department') &&
            rows.some(row => row.some(cell => typeof cell === 'object' && cell !== null));

        if (isHierarchical) return this.createHierarchicalFromShiksha(sourceName, tableData, tableIndex);

        return `
            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                <div class="bg-purple-50 px-6 py-4 border-b border-gray-200">
                    <div class="flex justify-between items-center">
                        <h4 class="text-lg font-semibold text-gray-900">
                            <i class="fas fa-table mr-2 text-purple-600"></i>
                            ${sourceName.charAt(0).toUpperCase() + sourceName.slice(1)} - ${headers[0] || 'Shiksha Data'}
                        </h4>
                        <span class="text-sm text-gray-600">Table ${tableIndex + 1} • Shiksha Format</span>
                    </div>
                    <div class="mt-2 text-sm text-gray-600">${rows.length} rows × ${headers.length} columns</div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-gray-100">
                            <tr>${headers.map(h => `<th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">${h || ''}</th>`).join('')}</tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                            ${rows.map((row, index) =>
            `<tr class="${index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}">
                                    ${headers.map((_, colIndex) =>
                `<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${row[colIndex] !== undefined ? row[colIndex] : '-'}</td>`
            ).join('')}
                                </tr>`
        ).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    createHierarchicalFromShiksha(sourceName, tableData, tableIndex) {
        const headers = tableData.headers || [];
        const rows = tableData.rows || [];
        const tableName = headers[0];
        const yearHeaders = headers.slice(1);
        const categoryData = {};

        rows.forEach(row => {
            if (row.length < 2) return;
            const metricName = row[0];
            const yearData = {};
            yearHeaders.forEach((year, index) => { if (row[index + 1] !== undefined) yearData[year] = row[index + 1]; });
            categoryData[metricName] = yearData;
        });

        const yearTables = [];
        Object.entries(categoryData).forEach(([metric, values]) => {
            if (!values || typeof values !== 'object') return;
            const flatMetrics = Object.entries(values).map(([key, value]) => ({ name: key, value }));
            if (flatMetrics.length > 0) {
                yearTables.push(`
                    <div class="mb-6">
                        <h5 class="text-lg font-medium text-gray-800 mb-3">${metric}</h5>
                        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
                            <div class="overflow-x-auto">
                                <table class="w-full">
                                    <thead class="bg-gray-100"><tr>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">Year</th>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">Value</th>
                                    </tr></thead>
                                    <tbody class="bg-white divide-y divide-gray-200">
                                        ${flatMetrics.map((m, idx) =>
                    `<tr class="${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}">
                                                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">${m.name}</td>
                                                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${m.value}</td>
                                            </tr>`
                ).join('')}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                `);
            }
        });

        if (!yearTables.length) return '';

        return `
            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                <div class="bg-indigo-50 px-6 py-4 border-b border-gray-200">
                    <div class="flex justify-between items-center">
                        <h4 class="text-lg font-semibold text-gray-900">
                            <i class="fas fa-layer-group mr-2 text-indigo-600"></i>
                            ${sourceName.charAt(0).toUpperCase() + sourceName.slice(1)} - ${tableName}
                        </h4>
                        <span class="text-sm text-gray-600">Table ${tableIndex + 1} • Hierarchical Data</span>
                    </div>
                </div>
                <div class="p-6">${yearTables.join('')}</div>
            </div>
        `;
    }

    createLegacyTable(sourceName, tableData, tableIndex) {
        const headers = tableData.headers || [];
        const values = tableData.values || [];
        if (!headers.length || !values.length) return '';

        return `
            <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                <div class="bg-yellow-50 px-6 py-4 border-b border-gray-200">
                    <div class="flex justify-between items-center">
                        <h4 class="text-lg font-semibold text-gray-900">
                            <i class="fas fa-database mr-2 text-yellow-600"></i>
                            ${sourceName.charAt(0).toUpperCase() + sourceName.slice(1)} - ${headers[0] || 'Legacy Data'}
                        </h4>
                        <span class="text-sm text-gray-600">Table ${tableIndex + 1} • Legacy Format</span>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-gray-100">
                            <tr>${headers.map(h => `<th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider border-b border-gray-200">${h || ''}</th>`).join('')}</tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                            <tr class="bg-white">
                                ${values.map(value => `<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${value || '-'}</td>`).join('')}
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    flattenHierarchicalMetrics(metrics, prefix = '') {
        const flatMetrics = [];
        Object.entries(metrics).forEach(([key, value]) => {
            if (typeof value === 'object' && value !== null) {
                flatMetrics.push(...this.flattenHierarchicalMetrics(value, key));
            } else {
                flatMetrics.push({
                    name: prefix ? `${prefix} - ${this.formatMetricName(key)}` : this.formatMetricName(key),
                    value: this.formatMetricValue(value)
                });
            }
        });
        return flatMetrics;
    }

    formatMetricName(key) {
        return key.replace(/_/g, ' ')
            .replace(/\b\w/g, l => l.toUpperCase())
            .replace(/Lpa/gi, 'LPA')
            .replace(/Percentage/gi, '%');
    }

    formatMetricValue(value) {
        if (value === null || value === undefined) return '-';
        if (typeof value === 'number') {
            return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
        }
        return String(value);
    }

    switchTab(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active', 'border-indigo-500', 'text-indigo-600');
            btn.classList.add('border-transparent', 'text-gray-500');
        });
        const activeBtn = document.querySelector(`[data-tab="${tabName}"]`);
        if (activeBtn) {
            activeBtn.classList.add('active', 'border-indigo-500', 'text-indigo-600');
            activeBtn.classList.remove('border-transparent', 'text-gray-500');
        }
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        const activeContent = document.getElementById(tabName);
        if (activeContent) activeContent.classList.add('active');

        if (tabName === 'generalprofile') {
            this.displayGeneralProfile();
        }
        if (tabName === 'reddit') {
            this.displayRedditData(this.selectedCollege);
        }
    }

    updateDataStatus(status) {
        const statusElement = document.getElementById('dataStatus');
        switch (status) {
            case 'cached':
                statusElement.innerHTML = '<i class="fas fa-circle text-green-500 text-xs mr-1"></i>Loaded from cache';
                break;
            case 'loaded':
                statusElement.innerHTML = '<i class="fas fa-circle text-green-500 text-xs mr-1"></i>Data loaded successfully';
                break;
            case 'loading':
                statusElement.innerHTML = '<i class="fas fa-circle text-yellow-500 text-xs mr-1"></i>Loading data...';
                break;
            case 'error':
                statusElement.innerHTML = '<i class="fas fa-circle text-red-500 text-xs mr-1"></i>Error loading data';
                break;
        }
    }

    showLoading() {
        document.getElementById('loadingState').classList.remove('hidden');
        document.getElementById('collegeDetails').classList.add('hidden');
        this.updateDataStatus('loading');
    }

    hideLoading() {
        document.getElementById('loadingState').classList.add('hidden');
        this.updateDataStatus('loaded');
    }

    showError(message) {
        const loadingState = document.getElementById('loadingState');
        loadingState.innerHTML = `
            <div class="text-center py-12">
                <i class="fas fa-exclamation-triangle text-6xl text-red-400 mb-4"></i>
                <p class="text-xl text-gray-600 mb-4">${message}</p>
                <button onclick="location.reload()" class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
                    Try Again
                </button>
            </div>
        `;
        this.updateDataStatus('error');
    }

    displayGeneralProfile() {
        const contentContainer = document.getElementById('generalProfileContent');
        const pillsContainer = document.getElementById('generalSubPills');
        if (!contentContainer || !pillsContainer) return;

        if (!this.selectedCollege) {
            contentContainer.innerHTML = '';
            pillsContainer.innerHTML = '';
            return;
        }

        const general = this.getGeneralDataForCollege(this.selectedCollege);

        if (!general) {
            pillsContainer.innerHTML = '';
            contentContainer.innerHTML = `
                <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center max-w-2xl mx-auto my-8">
                    <div class="w-16 h-16 bg-indigo-50 text-indigo-600 rounded-full flex items-center justify-center mx-auto mb-4">
                        <i class="fas fa-university text-2xl"></i>
                    </div>
                    <h4 class="text-xl font-bold text-gray-900 mb-2">No General Profile Data Scraped Yet</h4>
                    <p class="text-sm text-gray-600 mb-6 leading-relaxed">
                        We have placement statistics, but general profile information (overview, courses, admissions, reviews, rankings) has not been compiled for this college yet.
                    </p>
                    <div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4 text-left">
                        <p class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">To scrape this college:</p>
                        <code class="text-xs text-indigo-700 block whitespace-pre bg-gray-100 p-2 rounded overflow-x-auto">python3 src/college_placement_scraper.py --general "${this.selectedCollege}"</code>
                    </div>
                    <p class="text-xs text-gray-500">Run the command in your terminal to collect and view general details.</p>
                </div>
            `;
            return;
        }

        const cdData = general.collegedunia || {};
        const c3Data = general.careers360 || {};

        const subTabs = [
            { id: 'overview', name: 'Overview & Highlights', icon: 'fa-info-circle' },
            { id: 'courses', name: 'Courses & Fees', icon: 'fa-file-invoice-dollar' },
            { id: 'admission', name: 'Admissions & Cutoffs', icon: 'fa-door-open' },
            { id: 'facilities', name: 'Facilities & Campus', icon: 'fa-building' },
            { id: 'ranking', name: 'Rankings', icon: 'fa-trophy' },
            { id: 'reviews', name: 'Reviews', icon: 'fa-star' }
        ];

        const availableTabs = subTabs.filter(tab => this.hasDataForSubTab(tab.id, cdData, c3Data));

        if (availableTabs.length === 0) {
            pillsContainer.innerHTML = '';
            contentContainer.innerHTML = `
                <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center max-w-2xl mx-auto my-8">
                    <i class="fas fa-exclamation-circle text-4xl text-yellow-500 mb-3"></i>
                    <h4 class="text-lg font-bold text-gray-900 mb-2">No Profile Information Available</h4>
                    <p class="text-sm text-gray-600">The profile data exists in the file, but contains no valid sections.</p>
                </div>
            `;
            return;
        }

        if (!availableTabs.some(t => t.id === this.activeGeneralSubTab)) {
            this.activeGeneralSubTab = availableTabs[0].id;
        }

        pillsContainer.innerHTML = availableTabs.map(tab => {
            const isActive = tab.id === this.activeGeneralSubTab;
            return `
                <button class="px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm ${isActive
                    ? 'bg-indigo-600 text-white border border-indigo-600'
                    : 'bg-white text-gray-600 hover:bg-gray-50 border border-gray-200'
                }" data-subtab="${tab.id}">
                    ${tab.name}
                </button>
            `;
        }).join('');

        pillsContainer.querySelectorAll('[data-subtab]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.activeGeneralSubTab = e.currentTarget.dataset.subtab;
                this.displayGeneralProfile();
            });
        });

        const { cdSections, cdPageData, c3Sections, c3PageData } = this.getSectionsForSubTab(this.activeGeneralSubTab, cdData, c3Data);

        const cdUrl = cdPageData ? cdPageData.url : '';
        const c3Url = c3PageData ? c3PageData.url : '';

        let html = '';
        if ((!cdSections || cdSections.length === 0) && (!c3Sections || c3Sections.length === 0)) {
            html = `
                <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
                    <i class="fas fa-info-circle text-4xl text-gray-400 mb-3"></i>
                    <h4 class="text-lg font-bold text-gray-700">No profile data available for this section</h4>
                    <p class="text-sm text-gray-500">There is no parsed information for this sub-category from CollegeDunia or Careers360.</p>
                </div>`;
        } else {
            html = `
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-6 overflow-y-auto max-h-[700px] table-container animate-fade-in">
                ${cdSections && cdSections.length > 0 ? this.renderGeneralSections(cdSections) : ''}
                ${c3Sections && c3Sections.length > 0 ? this.renderGeneralSections(c3Sections) : ''}
            </div>`;
        }

        contentContainer.innerHTML = html;
    }

    hasDataForSubTab(subTabId, cdData, c3Data) {
        // Classifiers
        const isAdmissionTitle = t => {
            const l = t.toLowerCase();
            return l.includes('admission') || l.includes('cutoff') || l.includes('eligibility') ||
                l.includes('date') || l.includes('epgp') || l.includes('pgp') || l.includes('event') ||
                l.includes('entrance') || l.includes('criteria') || l.includes('test') || l.includes('exam') ||
                l.includes('intake') || l.includes('admit');
        };
        const isFeeTitle = t => {
            const l = t.toLowerCase();
            return l.includes('fee') || l.includes('course') || l.includes('cost') || l.includes('charge') ||
                l.includes('expense') || l.includes('curriculum');
        };
        const isFacilitiesTitle = t => {
            const l = t.toLowerCase();
            return l.includes('facilities') || l.includes('facility') || l.includes('hostel') ||
                l.includes('infrastructure') || l.includes('campus') || l.includes('library') ||
                l.includes('canteen') || l.includes('gym') || l.includes('sports') ||
                l.includes('residential') || l.includes('accommodation') || l.includes('location') ||
                l.includes('map');
        };
        const isRankingTitle = t => {
            const l = t.toLowerCase();
            return l.includes('ranking') || l.includes('rank') || l.includes('nirf') ||
                l.includes('qs') || l.includes('accreditation') || l.includes('accerditation');
        };
        const isReviewTitle = t => {
            const l = t.toLowerCase();
            return l.includes('review') || l.includes('rating') || l.includes('experience') ||
                l.includes('comment') || l.includes('feedback') || l.includes('student review');
        };

        const hasSections = (pageObj, filterFn = null) => {
            if (!pageObj || !pageObj.sections) return false;
            const keys = Object.keys(pageObj.sections);
            if (keys.length === 0) return false;
            if (filterFn) {
                return keys.some(filterFn);
            }
            return true;
        };

        if (subTabId === 'overview') {
            return hasSections(cdData.main) || hasSections(c3Data.main);
        }
        if (subTabId === 'courses') {
            return hasSections(cdData['courses-fees']) ||
                hasSections(cdData.main, isFeeTitle) ||
                hasSections(c3Data.courses) ||
                hasSections(c3Data.main, isFeeTitle);
        }
        if (subTabId === 'admission') {
            return hasSections(cdData.admission) ||
                hasSections(cdData.main, isAdmissionTitle) ||
                hasSections(c3Data.main, isAdmissionTitle);
        }
        if (subTabId === 'facilities') {
            return hasSections(c3Data.facilities) ||
                hasSections(c3Data.main, isFacilitiesTitle) ||
                hasSections(cdData.main, isFacilitiesTitle);
        }
        if (subTabId === 'ranking') {
            return hasSections(cdData.ranking) ||
                hasSections(cdData.main, isRankingTitle) ||
                hasSections(c3Data.ranking) ||
                hasSections(c3Data.main, isRankingTitle);
        }
        if (subTabId === 'reviews') {
            return hasSections(cdData.reviews) ||
                hasSections(cdData.main, isReviewTitle) ||
                hasSections(c3Data.reviews) ||
                hasSections(c3Data.main, isReviewTitle);
        }
        return false;
    }

    getSectionsForSubTab(subTabId, cdData, c3Data) {
        const isAdmissionTitle = t => {
            const l = t.toLowerCase();
            return l.includes('admission') || l.includes('cutoff') || l.includes('eligibility') ||
                l.includes('date') || l.includes('epgp') || l.includes('pgp') || l.includes('event') ||
                l.includes('entrance') || l.includes('criteria') || l.includes('test') || l.includes('exam') ||
                l.includes('intake') || l.includes('admit');
        };
        const isFeeTitle = t => {
            const l = t.toLowerCase();
            return l.includes('fee') || l.includes('course') || l.includes('cost') || l.includes('charge') ||
                l.includes('expense') || l.includes('curriculum');
        };
        const isFacilitiesTitle = t => {
            const l = t.toLowerCase();
            return l.includes('facilities') || l.includes('facility') || l.includes('hostel') ||
                l.includes('infrastructure') || l.includes('campus') || l.includes('library') ||
                l.includes('canteen') || l.includes('gym') || l.includes('sports') ||
                l.includes('residential') || l.includes('accommodation') || l.includes('location') ||
                l.includes('map');
        };
        const isRankingTitle = t => {
            const l = t.toLowerCase();
            return l.includes('ranking') || l.includes('rank') || l.includes('nirf') ||
                l.includes('qs') || l.includes('accreditation') || l.includes('accerditation');
        };
        const isReviewTitle = t => {
            const l = t.toLowerCase();
            return l.includes('review') || l.includes('rating') || l.includes('experience') ||
                l.includes('comment') || l.includes('feedback') || l.includes('student review');
        };

        const isTableOfContentsSection = (title, sec) => {
            const paragraphs = sec.paragraphs || [];
            const tables = sec.tables || [];
            const lists = sec.lists || [];

            // Table of Contents or Link list panels have 0 paragraphs, 0 tables, and a single list of short navigation items.
            if (paragraphs.length === 0 && tables.length === 0 && lists.length > 0) {
                const allShort = lists.every(listGroup =>
                    listGroup.every(item => item.length < 75)
                );
                if (allShort) {
                    return true;
                }
            }

            const lowerTitle = title.toLowerCase();
            if (lowerTitle.includes("table of contents") || lowerTitle.includes("quick links") ||
                lowerTitle.includes("quick navigation") || (lowerTitle.endsWith(" overview") && paragraphs.length === 0 && lists.length === 1 && lists[0].length > 5)) {
                return true;
            }

            return false;
        };

        let cdSections = [];
        let cdPageData = null;
        let c3Sections = [];
        let c3PageData = null;

        // Helper to collect and filter sections from a page
        const collectSections = (pageObj, filterFn = null) => {
            if (!pageObj || !pageObj.sections) return [];
            return Object.entries(pageObj.sections)
                .filter(([title, sec]) => {
                    // Always filter out Table of Contents / Quick Links
                    if (isTableOfContentsSection(title, sec)) return false;
                    // If filterFn is provided, check if it matches
                    return filterFn ? filterFn(title) : true;
                })
                .map(([title, val]) => ({ title, ...val }));
        };

        // Helper to merge and deduplicate sections (case-insensitive title matching)
        const mergeAndDeduplicate = (secList1, secList2) => {
            const seen = new Set();
            const merged = [];
            [...secList1, ...secList2].forEach(sec => {
                const normTitle = sec.title.toLowerCase().trim().replace(/\s+/g, ' ');
                if (!seen.has(normTitle)) {
                    seen.add(normTitle);
                    merged.push(sec);
                }
            });
            return merged;
        };

        if (subTabId === 'overview') {
            cdPageData = cdData.main;
            const overviewFilter = t => !isFeeTitle(t) && !isRankingTitle(t) && !isReviewTitle(t) && !isFacilitiesTitle(t) && !isAdmissionTitle(t);
            let cdMain = collectSections(cdData.main, overviewFilter);
            // If nothing matched overview filter, fallback to all sections (except TOC)
            if (cdMain.length === 0) {
                cdMain = collectSections(cdData.main);
            }
            cdSections = cdMain;

            c3PageData = c3Data.main;
            let c3Main = collectSections(c3Data.main, overviewFilter);
            if (c3Main.length === 0) {
                c3Main = collectSections(c3Data.main);
            }
            c3Sections = c3Main;
        }
        else if (subTabId === 'courses') {
            cdPageData = cdData['courses-fees'] || cdData.main;
            const cdCourses = collectSections(cdData['courses-fees']);
            const cdMainCourses = collectSections(cdData.main, isFeeTitle);
            cdSections = mergeAndDeduplicate(cdCourses, cdMainCourses);

            c3PageData = c3Data.courses || c3Data.main;
            const c3Courses = collectSections(c3Data.courses);
            const c3MainCourses = collectSections(c3Data.main, isFeeTitle);
            c3Sections = mergeAndDeduplicate(c3Courses, c3MainCourses);
        }
        else if (subTabId === 'admission') {
            cdPageData = cdData.admission || cdData.main;
            const cdAdm = collectSections(cdData.admission);
            const cdMainAdm = collectSections(cdData.main, isAdmissionTitle);
            cdSections = mergeAndDeduplicate(cdAdm, cdMainAdm);

            c3PageData = c3Data.main;
            c3Sections = collectSections(c3Data.main, isAdmissionTitle);
        }
        else if (subTabId === 'facilities') {
            cdPageData = cdData.main;
            cdSections = collectSections(cdData.main, isFacilitiesTitle);

            c3PageData = c3Data.facilities || c3Data.main;
            const c3Fac = collectSections(c3Data.facilities);
            const c3MainFac = collectSections(c3Data.main, isFacilitiesTitle);
            c3Sections = mergeAndDeduplicate(c3Fac, c3MainFac);
        }
        else if (subTabId === 'ranking') {
            cdPageData = cdData.ranking || cdData.main;
            const cdRank = collectSections(cdData.ranking);
            const cdMainRank = collectSections(cdData.main, isRankingTitle);
            cdSections = mergeAndDeduplicate(cdRank, cdMainRank);

            c3PageData = c3Data.ranking || c3Data.main;
            const c3Rank = collectSections(c3Data.ranking);
            const c3MainRank = collectSections(c3Data.main, isRankingTitle);
            c3Sections = mergeAndDeduplicate(c3Rank, c3MainRank);
        }
        else if (subTabId === 'reviews') {
            cdPageData = cdData.reviews || cdData.main;
            const cdRev = collectSections(cdData.reviews);
            const cdMainRev = collectSections(cdData.main, isReviewTitle);
            cdSections = mergeAndDeduplicate(cdRev, cdMainRev);

            c3PageData = c3Data.reviews || c3Data.main;
            const c3Rev = collectSections(c3Data.reviews);
            const c3MainRev = collectSections(c3Data.main, isReviewTitle);
            c3Sections = mergeAndDeduplicate(c3Rev, c3MainRev);
        }

        return { cdSections, cdPageData, c3Sections, c3PageData };
    }

    renderGeneralSections(sections) {
        let html = '';
        sections.forEach(sec => {
            const title = sec.title;
            const paragraphs = sec.paragraphs || [];
            const lists = sec.lists || [];
            const tables = sec.tables || [];

            const hasContent = paragraphs.length > 0 || lists.length > 0 || tables.length > 0;
            if (!hasContent) return;

            html += `
            <div class="border-b border-gray-100 last:border-b-0 pb-6 last:pb-0">
                <h5 class="text-base font-semibold text-gray-800 mb-3 flex items-center gap-2">
                    <span class="w-1.5 h-3 bg-indigo-500 rounded-sm"></span>
                    ${this.escapeHtml(title)}
                </h5>`;

            paragraphs.forEach(p => {
                if (p && p.trim()) {
                    html += `<p class="text-sm text-gray-600 leading-relaxed mb-3">${this.escapeHtml(p)}</p>`;
                }
            });

            lists.forEach(listGroup => {
                if (listGroup && listGroup.length > 0) {
                    html += `<ul class="space-y-2 mb-4">`;
                    listGroup.forEach(item => {
                        if (item && item.trim()) {
                            html += `
                            <li class="flex items-start gap-2 text-sm text-gray-600">
                                <i class="fas fa-check-circle text-indigo-500 mt-1 shrink-0 text-xs"></i>
                                <span>${this.escapeHtml(item)}</span>
                            </li>`;
                        }
                    });
                    html += `</ul>`;
                }
            });

            tables.forEach(table => {
                html += this.renderGeneralTable(table);
            });

            html += `</div>`;
        });
        return html;
    }

    renderGeneralTable(table) {
        if (!table || !table.headers || !table.rows || table.rows.length === 0) return '';
        const headers = table.headers;
        const rows = table.rows;

        let html = `
            <div class="my-4 overflow-hidden border border-gray-200 rounded-lg shadow-sm">
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200 text-sm">
                        <thead class="bg-gray-50">
                            <tr>`;
        headers.forEach(h => {
            html += `<th scope="col" class="px-4 py-3 text-left font-semibold text-gray-700 uppercase tracking-wider text-xs">${this.escapeHtml(h)}</th>`;
        });
        html += `           </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200 bg-white">`;

        rows.forEach((row, idx) => {
            html += `<tr class="${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'} hover:bg-indigo-50/20 transition-colors">`;
            row.forEach(cell => {
                html += `<td class="px-4 py-3 text-gray-600 whitespace-pre-wrap">${this.escapeHtml(cell || '-')}</td>`;
            });
            html += `</tr>`;
        });

        html += `       </tbody>
                    </table>
                </div>
            </div>`;
        return html;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new CollegePlacementDashboard();
});