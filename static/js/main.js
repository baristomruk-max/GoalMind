/**
 * Football Data App - Ana JavaScript Dosyası
 * API istekleri, grafik çizimleri, arama ve state yönetimi
 */

// ─── API Yardımcısı ───
async function api(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, options);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (err) {
        console.error(`API Error (${endpoint}):`, err);
        showToast(`API Hatası: ${err.message}`, 'error');
        return null;
    }
}

// ─── Toast Bildirimleri ───
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = '✅';
    if (type === 'error') icon = '❌';
    else if (type === 'warning') icon = '⚠️';
    
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);
    
    // Animasyon
    setTimeout(() => toast.classList.add('show'), 10);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ─── Animasyonlar ───
function animateNumber(id, end, duration = 1000) {
    const el = document.getElementById(id);
    if (!el || !end) return;
    
    let start = 0;
    const endNum = parseInt(end);
    if (isNaN(endNum)) {
        el.textContent = end;
        return;
    }

    const range = endNum - start;
    let current = start;
    const increment = endNum > start ? 1 : -1;
    const stepTime = Math.abs(Math.floor(duration / range));
    
    // Çok büyük sayılar için optimizasyon
    if (range > 1000) {
        el.textContent = endNum.toLocaleString();
        return;
    }

    const timer = setInterval(() => {
        current += increment;
        el.textContent = current.toLocaleString();
        if (current == endNum) {
            clearInterval(timer);
        }
    }, stepTime);
}

// ─── Grafik Yardımcıları (Chart.js) ───
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.9)';
Chart.defaults.plugins.tooltip.padding = 12;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.legend.labels.usePointStyle = true;

const chartInstances = {};

function createDoughnutChart(id, config) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    
    if (chartInstances[id]) chartInstances[id].destroy();
    
    chartInstances[id] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: config.labels,
            datasets: [{
                data: config.data,
                backgroundColor: config.colors,
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });
}

function createBarChart(id, config) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    
    if (chartInstances[id]) chartInstances[id].destroy();
    
    chartInstances[id] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: config.labels,
            datasets: [{
                label: config.label,
                data: config.data,
                backgroundColor: config.color,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false }, ticks: { maxRotation: 45, minRotation: 45 } }
            }
        }
    });
}

// ─── Sidebar ve Menü ───
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

async function loadSidebarLeagues() {
    const leagues = await api('/api/leagues');
    if (!leagues) return;
    
    const container = document.getElementById('league-list');
    
    // Ülkelere göre grupla
    const byCountry = {};
    leagues.forEach(l => {
        if (!byCountry[l.country]) byCountry[l.country] = [];
        byCountry[l.country].push(l);
    });
    
    let html = '';
    const currentPath = window.location.pathname;
    
    Object.keys(byCountry).sort().forEach(country => {
        const countryLeagues = byCountry[country];
        // En az 1 maç olanları veya hepsini göster
        const activeLeagues = countryLeagues.filter(l => l.match_count > 0 || l.league_type === 'standard');
        
        if (activeLeagues.length === 0) return;
        
        html += `<div style="padding: 8px 16px; font-size: 0.75rem; color: #64748b; font-weight: 600; text-transform: uppercase;">${country}</div>`;
        
        activeLeagues.forEach(l => {
            const isActive = currentPath === `/league/${l.id}`;
            const dotClass = l.match_count > 0 ? 'success' : 'muted';
            
            let name = l.name;
            if (name.includes(' - ')) name = name.split(' - ')[1];
            
            html += `<a href="/league/${l.id}" class="nav-item ${isActive ? 'active' : ''}" style="padding-left: 24px; font-size: 0.85rem;">
                <span class="status-dot ${dotClass}" style="width: 6px; height: 6px; margin-right: 6px; display: inline-block;"></span>
                <span class="nav-label">${name}</span>
            </a>`;
        });
    });
    
    container.innerHTML = html;
}

// ─── Arama İşlevleri ───
function setupSearch() {
    const input = document.getElementById('team-search');
    const results = document.getElementById('search-results');
    if (!input || !results) return;

    let debounceTimer;

    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = input.value.trim();
        
        if (query.length < 2) {
            results.style.display = 'none';
            return;
        }

        debounceTimer = setTimeout(async () => {
            const teams = await api(`/api/teams/search?q=${encodeURIComponent(query)}`);
            if (teams && teams.length > 0) {
                results.innerHTML = teams.map(t => 
                    `<div class="search-item" onclick="window.location.href='/team/${encodeURIComponent(t)}'">${t}</div>`
                ).join('');
                results.style.display = 'block';
            } else {
                results.style.display = 'none';
            }
        }, 300);
    });

    // Dışarı tıklanınca kapat
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-container')) {
            results.style.display = 'none';
        }
    });
}

// ─── Durum / İndirme Takibi ───
let statusInterval;

function updateDbStatus(stats) {
    const indicator = document.getElementById('db-status');
    const text = document.getElementById('db-status-text');
    const dot = indicator.querySelector('.status-dot');
    
    if (stats.total_matches > 0) {
        text.textContent = `${stats.total_matches.toLocaleString()} Maç | ${stats.total_teams} Takım`;
        dot.className = 'status-dot active';
    } else {
        text.textContent = 'Veritabanı Boş - Veri İndirin';
        dot.className = 'status-dot error';
    }
}

async function startFetch(onlyLatest = false) {
    const res = await api('/api/fetch', { 
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ only_latest: onlyLatest })
    });
    if (res && res.error) {
        showToast(res.error, 'warning');
        return;
    }
    
    showToast('Veri indirme başlatıldı', 'success');
    document.getElementById('fetch-status').style.display = 'block';
    
    const indicator = document.getElementById('db-status');
    const text = document.getElementById('db-status-text');
    const dot = indicator.querySelector('.status-dot');
    text.textContent = 'Veriler indiriliyor...';
    dot.className = 'status-dot fetching';
    
    // Polling başlat
    if (!statusInterval) {
        statusInterval = setInterval(checkFetchStatus, 1000);
    }
}

async function startImport() {
    const res = await api('/api/import', { method: 'POST' });
    showToast('Mevcut CSV dosyaları aktarılıyor...', 'success');
    
    const indicator = document.getElementById('db-status');
    const text = document.getElementById('db-status-text');
    const dot = indicator.querySelector('.status-dot');
    text.textContent = 'Veritabanı güncelleniyor...';
    dot.className = 'status-dot fetching';
    
    setTimeout(() => {
        window.location.reload();
    }, 5000); // 5 saniye sonra yenile
}

async function checkFetchStatus() {
    const status = await api('/api/fetch/status');
    if (!status) return;
    
    const container = document.getElementById('fetch-status');
    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');
    
    if (status.in_progress) {
        container.style.display = 'block';
        const pct = status.total > 0 ? ((status.completed + status.failed) / status.total) * 100 : 0;
        fill.style.width = `${pct}%`;
        text.textContent = `İndiriliyor: ${status.completed}/${status.total} (Hata: ${status.failed})`;
        
        // Eğer interval yoksa ama işlem devam ediyorsa, polling'i başlat
        if (!statusInterval) {
            statusInterval = setInterval(checkFetchStatus, 1000);
        }
    } else if (statusInterval) {
        // Sadece bir polling işlemi varsa ve bittiyse yenileme yap
        clearInterval(statusInterval);
        statusInterval = null;
        
        fill.style.width = '100%';
        fill.style.backgroundColor = 'var(--success)';
        text.textContent = `Tamamlandı! ${status.completed} başarılı.`;
        
        setTimeout(() => {
            container.style.display = 'none';
            showToast('Veri indirme tamamlandı! Sayfa yenileniyor...', 'success');
            setTimeout(() => window.location.reload(), 2000);
        }, 3000);
    } else {
        // Polling yoksa ve işlem devam etmiyorsa sadece kutuyu gizle
        container.style.display = 'none';
    }
}

// ─── İnit ───
document.addEventListener('DOMContentLoaded', async () => {
    loadSidebarLeagues();
    setupSearch();
    
    // İlk DB durumu kontrolü
    const stats = await api('/api/stats');
    if (stats) updateDbStatus(stats);
    
    // Devam eden indirme var mı kontrol et
    checkFetchStatus();
});
