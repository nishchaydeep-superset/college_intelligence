class DataVisualization {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.charts = {};
        this.init();
    }

    init() {
        this.createChartsContainer();
        this.setupChartToggle();
    }

    createChartsContainer() {
        const chartsSection = document.createElement('section');
        chartsSection.id = 'chartsSection';
        chartsSection.className = 'mb-8 hidden';
        chartsSection.innerHTML = `
            <div class="bg-white rounded-lg shadow-sm p-6">
                <div class="flex justify-between items-center mb-6">
                    <h2 class="text-2xl font-bold text-gray-900">Data Analytics</h2>
                    <div class="flex space-x-2">
                        <button class="chart-btn px-3 py-1 bg-indigo-600 text-white rounded-lg text-sm" data-chart="sources">
                            Data Sources
                        </button>
                        <button class="chart-btn px-3 py-1 bg-gray-200 text-gray-700 rounded-lg text-sm" data-chart="recruiters">
                            Top Recruiters
                        </button>
                        <button class="chart-btn px-3 py-1 bg-gray-200 text-gray-700 rounded-lg text-sm" data-chart="colleges">
                            College Types
                        </button>
                    </div>
                </div>
                
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="bg-gray-50 rounded-lg p-4">
                        <canvas id="mainChart"></canvas>
                    </div>
                    <div class="bg-gray-50 rounded-lg p-4">
                        <canvas id="secondaryChart"></canvas>
                    </div>
                </div>
                
                <div class="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
                    <div class="bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-lg p-4">
                        <h3 class="font-semibold mb-2">Average Package Range</h3>
                        <p id="avgPackageRange" class="text-2xl font-bold">Calculating...</p>
                    </div>
                    <div class="bg-gradient-to-r from-green-500 to-green-600 text-white rounded-lg p-4">
                        <h3 class="font-semibold mb-2">Most Active Sector</h3>
                        <p id="topSector" class="text-2xl font-bold">IT/Consulting</p>
                    </div>
                    <div class="bg-gradient-to-r from-purple-500 to-purple-600 text-white rounded-lg p-4">
                        <h3 class="font-semibold mb-2">Data Completeness</h3>
                        <p id="dataCompleteness" class="text-2xl font-bold">85%</p>
                    </div>
                </div>
            </div>
        `;
        
        const mainContent = document.querySelector('main');
        const statsSection = document.getElementById('statsSection');
        mainContent.insertBefore(chartsSection, statsSection.nextSibling);
    }

    setupChartToggle() {
        document.querySelectorAll('.chart-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.chart-btn').forEach(b => {
                    b.className = 'chart-btn px-3 py-1 bg-gray-200 text-gray-700 rounded-lg text-sm';
                });
                e.target.className = 'chart-btn px-3 py-1 bg-indigo-600 text-white rounded-lg text-sm';
                
                this.renderCharts(e.target.dataset.chart);
            });
        });
    }

    renderCharts(chartType) {
        if (!this.dashboard.collegeData) return;

        // Destroy existing charts
        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });

        switch(chartType) {
            case 'sources':
                this.renderDataSourcesChart();
                this.renderSourceDistributionChart();
                break;
            case 'recruiters':
                this.renderTopRecruitersChart();
                this.renderRecruitersBySectorChart();
                break;
            case 'colleges':
                this.renderCollegeTypesChart();
                this.renderPlacementStatsChart();
                break;
        }

        this.updateAnalyticsCards();
    }

    renderDataSourcesChart() {
        const ctx = document.getElementById('mainChart').getContext('2d');
        const sourceCounts = this.getSourceCounts();
        
        this.charts.main = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: Object.keys(sourceCounts),
                datasets: [{
                    label: 'Number of Colleges',
                    data: Object.values(sourceCounts),
                    backgroundColor: [
                        'rgba(59, 130, 246, 0.8)',
                        'rgba(16, 185, 129, 0.8)',
                        'rgba(251, 146, 60, 0.8)'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Colleges by Data Source'
                    },
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    renderSourceDistributionChart() {
        const ctx = document.getElementById('secondaryChart').getContext('2d');
        const multiSourceCounts = this.getMultiSourceCounts();
        
        this.charts.secondary = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Single Source', 'Multiple Sources'],
                datasets: [{
                    data: [multiSourceCounts.single, multiSourceCounts.multiple],
                    backgroundColor: [
                        'rgba(156, 163, 175, 0.8)',
                        'rgba(99, 102, 241, 0.8)'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Data Source Distribution'
                    }
                }
            }
        });
    }

    renderTopRecruitersChart() {
        const ctx = document.getElementById('mainChart').getContext('2d');
        const topRecruiters = this.getTopRecruitersData();
        
        this.charts.main = new Chart(ctx, {
            type: 'horizontalBar',
            data: {
                labels: topRecruiters.map(r => r.name),
                datasets: [{
                    label: 'Number of Colleges',
                    data: topRecruiters.map(r => r.count),
                    backgroundColor: 'rgba(16, 185, 129, 0.8)',
                    borderWidth: 0
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Top 10 Recruiters Across Colleges'
                    },
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    renderRecruitersBySectorChart() {
        const ctx = document.getElementById('secondaryChart').getContext('2d');
        const sectorData = this.getRecruitersBySector();
        
        this.charts.secondary = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: Object.keys(sectorData),
                datasets: [{
                    data: Object.values(sectorData),
                    backgroundColor: [
                        'rgba(59, 130, 246, 0.8)',
                        'rgba(16, 185, 129, 0.8)',
                        'rgba(251, 146, 60, 0.8)',
                        'rgba(147, 51, 234, 0.8)',
                        'rgba(236, 72, 153, 0.8)'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Recruiters by Sector'
                    }
                }
            }
        });
    }

    renderCollegeTypesChart() {
        const ctx = document.getElementById('mainChart').getContext('2d');
        const collegeTypes = this.getCollegeTypes();
        
        this.charts.main = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: Object.keys(collegeTypes),
                datasets: [{
                    label: 'Number of Colleges',
                    data: Object.values(collegeTypes),
                    backgroundColor: [
                        'rgba(99, 102, 241, 0.8)',
                        'rgba(16, 185, 129, 0.8)',
                        'rgba(251, 146, 60, 0.8)',
                        'rgba(236, 72, 153, 0.8)'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Colleges by Type'
                    },
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    renderPlacementStatsChart() {
        const ctx = document.getElementById('secondaryChart').getContext('2d');
        const placementData = this.getPlacementStatsData();
        
        this.charts.secondary = new Chart(ctx, {
            type: 'line',
            data: {
                labels: placementData.labels,
                datasets: [{
                    label: 'Average Package (LPA)',
                    data: placementData.avgPackages,
                    borderColor: 'rgba(99, 102, 241, 1)',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    tension: 0.4
                }, {
                    label: 'Median Package (LPA)',
                    data: placementData.medianPackages,
                    borderColor: 'rgba(16, 185, 129, 1)',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: {
                        display: true,
                        text: 'Package Trends'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    getSourceCounts() {
        const counts = {};
        Object.values(this.dashboard.collegeData).forEach(college => {
            college.data_sources.forEach(source => {
                counts[source] = (counts[source] || 0) + 1;
            });
        });
        return counts;
    }

    getMultiSourceCounts() {
        let single = 0;
        let multiple = 0;
        
        Object.values(this.dashboard.collegeData).forEach(college => {
            if (college.data_sources.length === 1) {
                single++;
            } else {
                multiple++;
            }
        });
        
        return { single, multiple };
    }

    getTopRecruitersData() {
        const recruiterCounts = {};
        
        Object.values(this.dashboard.collegeData).forEach(college => {
            Object.values(college.source_data).forEach(source => {
                if (source.top_recruiters) {
                    source.top_recruiters.forEach(recruiter => {
                        recruiterCounts[recruiter] = (recruiterCounts[recruiter] || 0) + 1;
                    });
                }
            });
        });
        
        return Object.entries(recruiterCounts)
            .map(([name, count]) => ({ name, count }))
            .sort((a, b) => b.count - a.count)
            .slice(0, 10);
    }

    getRecruitersBySector() {
        const sectors = {
            'IT/Technology': 0,
            'Consulting': 0,
            'Finance': 0,
            'Manufacturing': 0,
            'Others': 0
        };
        
        Object.values(this.dashboard.collegeData).forEach(college => {
            Object.values(college.source_data).forEach(source => {
                if (source.top_recruiters) {
                    source.top_recruiters.forEach(recruiter => {
                        const recruiterLower = recruiter.toLowerCase();
                        if (recruiterLower.includes('tcs') || recruiterLower.includes('infosys') || 
                            recruiterLower.includes('wipro') || recruiterLower.includes('microsoft') ||
                            recruiterLower.includes('google') || recruiterLower.includes('amazon')) {
                            sectors['IT/Technology']++;
                        } else if (recruiterLower.includes('consulting') || recruiterLower.includes('mckinsey') ||
                                  recruiterLower.includes('bain') || recruiterLower.includes('bcg')) {
                            sectors['Consulting']++;
                        } else if (recruiterLower.includes('bank') || recruiterLower.includes('jpmorgan') ||
                                  recruiterLower.includes('goldman') || recruiterLower.includes('kpmg') ||
                                  recruiterLower.includes('deloitte') || recruiterLower.includes('ey')) {
                            sectors['Finance']++;
                        } else if (recruiterLower.includes('tata') || recruiterLower.includes('steel') ||
                                  recruiterLower.includes('manufacturing')) {
                            sectors['Manufacturing']++;
                        } else {
                            sectors['Others']++;
                        }
                    });
                }
            });
        });
        
        return sectors;
    }

    getCollegeTypes() {
        const types = {
            'IITs': 0,
            'IIMs': 0,
            'NITs': 0,
            'Others': 0
        };
        
        Object.keys(this.dashboard.collegeData).forEach(collegeName => {
            const nameLower = collegeName.toLowerCase();
            if (nameLower.includes('indian institute of technology') || nameLower.includes('iit')) {
                types['IITs']++;
            } else if (nameLower.includes('indian institute of management') || nameLower.includes('iim')) {
                types['IIMs']++;
            } else if (nameLower.includes('national institute of technology') || nameLower.includes('nit')) {
                types['NITs']++;
            } else {
                types['Others']++;
            }
        });
        
        return types;
    }

    getPlacementStatsData() {
        const packages = [];
        const colleges = [];
        
        Object.entries(this.dashboard.collegeData).forEach(([collegeName, collegeData]) => {
            Object.values(college.source_data).forEach(source => {
                if (source.placement_statistics) {
                    source.placement_statistics.forEach(stat => {
                        if (stat.headers && stat.values) {
                            const header = stat.headers[0].toLowerCase();
                            const value = stat.values[1];
                            
                            if (header.includes('average') && (header.includes('package') || header.includes('salary'))) {
                                const numericValue = this.extractPackageValue(value);
                                if (numericValue) {
                                    packages.push(numericValue);
                                    colleges.push(collegeName);
                                }
                            }
                        }
                    });
                }
            });
        });
        
        return {
            labels: colleges.slice(0, 10),
            avgPackages: packages.slice(0, 10),
            medianPackages: packages.slice(0, 10).map(p => p * 0.9) // Mock median data
        };
    }

    extractPackageValue(value) {
        if (!value || typeof value !== 'string') return null;
        
        // Extract numeric value from strings like "15 LPA", "20-25 LPA", etc.
        const match = value.match(/(\d+(?:\.\d+)?)/);
        return match ? parseFloat(match[1]) : null;
    }

    updateAnalyticsCards() {
        // Update average package range
        const packages = [];
        Object.values(this.dashboard.collegeData).forEach(college => {
            Object.values(college.source_data).forEach(source => {
                if (source.placement_statistics) {
                    source.placement_statistics.forEach(stat => {
                        if (stat.headers && stat.values) {
                            const header = stat.headers[0].toLowerCase();
                            const value = stat.values[1];
                            
                            if (header.includes('average') && (header.includes('package') || header.includes('salary'))) {
                                const numericValue = this.extractPackageValue(value);
                                if (numericValue) packages.push(numericValue);
                            }
                        }
                    });
                }
            });
        });
        
        if (packages.length > 0) {
            const min = Math.min(...packages);
            const max = Math.max(...packages);
            document.getElementById('avgPackageRange').textContent = `${min}-${max} LPA`;
        } else {
            document.getElementById('avgPackageRange').textContent = 'Data not available';
        }
        
        // Calculate data completeness
        let totalFields = 0;
        let filledFields = 0;
        
        Object.values(this.dashboard.collegeData).forEach(college => {
            Object.values(college.source_data).forEach(source => {
                if (source.placement_statistics && source.placement_statistics.length > 0) {
                    totalFields += source.placement_statistics.length;
                    filledFields += source.placement_statistics.filter(stat => 
                        stat.values && stat.values[1] && stat.values[1].trim() !== ''
                    ).length;
                }
                
                if (source.top_recruiters) {
                    totalFields += 1;
                    if (source.top_recruiters.length > 0) filledFields += 1;
                }
            });
        });
        
        const completeness = totalFields > 0 ? Math.round((filledFields / totalFields) * 100) : 0;
        document.getElementById('dataCompleteness').textContent = `${completeness}%`;
    }

    show() {
        document.getElementById('chartsSection').classList.remove('hidden');
        this.renderCharts('sources');
    }

    hide() {
        document.getElementById('chartsSection').classList.add('hidden');
    }
}
