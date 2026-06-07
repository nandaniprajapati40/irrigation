<template>
  <div class="chart-container">
    <!-- Controls -->
    <div class="chart-controls">
      <div class="control-group">
        <label>Indicator</label>
        <div class="select-wrapper">
          <select v-model="selectedLayer" class="select">
            <option v-for="layer in layerOptions" :key="layer.value" :value="layer.value">
              {{ layer.label }}
            </option>
          </select>
          <svg class="select-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>

      <div class="control-group">
        <label>View</label>
        <div class="toggle-switch">
          <button class="toggle-option" :class="{ active: mode === 'monthly' }" @click="mode = 'monthly'">
            Monthly
          </button>
          <button class="toggle-option" :class="{ active: mode === 'cumulative' }" @click="mode = 'cumulative'">
            Cumulative
          </button>
        </div>
      </div>

      <!-- Chart type badge -->
      <div class="chart-type-badge">
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-overlay">
      <div class="spinner"></div>
      <span>Loading chart data…</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-box">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      {{ error }}
    </div>

    <!-- Chart -->
    <div v-else class="chart-wrapper">
      <canvas ref="chartCanvas" class="chart"></canvas>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import Chart from 'chart.js/auto'

const canvasBackgroundPlugin = {
  id: 'canvasBackgroundPlugin',
  beforeDraw(chartInstance) {
    const { ctx, width, height } = chartInstance
    ctx.save()
    ctx.fillStyle = '#fff'; // Light background
    ctx.fillRect(0, 0, width, height)
    ctx.restore()
  }
}

Chart.register(canvasBackgroundPlugin)

const props = defineProps({
  isDark: { type: Boolean, default: true },
  title: { type: String, default: 'Wheat Crop Parameters - Historical Data' },
  initialLayer: { type: String, default: 'savi' },
  showBoundaryData: { type: Boolean, default: true }
})

const chartCanvas = ref(null)
let chart = null

const MONTHLY_LAYER_OPTIONS = [
  { value: 'savi', label: 'SAVI - Soil Adjusted Vegetation Index' },
  { value: 'kc', label: 'Kc - Crop Coefficient' },
  { value: 'cwr', label: 'CWR - Crop Water Requirement' },
  { value: 'iwr', label: 'IWR - Irrigation Water Requirement' },
  { value: 'etc', label: 'ETc - Actual Evapotranspiration' },
]
const CUMULATIVE_LAYER_OPTIONS = MONTHLY_LAYER_OPTIONS.filter(layer => ['cwr', 'iwr'].includes(layer.value))

function normalizeTrendLayer(layer, chartMode = 'monthly') {
  const normalized = String(layer || '').toLowerCase()
  const allowed = chartMode === 'cumulative'
    ? CUMULATIVE_LAYER_OPTIONS
    : MONTHLY_LAYER_OPTIONS
  return allowed.some(item => item.value === normalized) ? normalized : 'cwr'
}

const mode = ref('monthly')
const selectedLayer = ref(normalizeTrendLayer(props.initialLayer, mode.value))
const loading = ref(false)
const error = ref(null)
const layerOptions = computed(() => mode.value === 'cumulative' ? CUMULATIVE_LAYER_OPTIONS : MONTHLY_LAYER_OPTIONS)

const API_BASE = (process.env.VUE_APP_API_BASE || '').replace(/\/$/, '')

const YEAR_COLORS = [
  '#0f4c81',
  '#1f7a5c',
  '#d97706',
  '#c2410c',
  '#0f766e',
  '#b91c1c',
  '#7c3aed',
  '#4b5563',
  '#0284c7',
  '#65a30d',
]

// ─── Fetch from FastAPI ────────────────────────────────────────────────────────
async function fetchChart() {
  loading.value = true
  error.value = null

  try {
    // Fix: Ensure layer name is correct (not 'swai' typo)
    const layerParam = selectedLayer.value.toLowerCase()
    const url = `${API_BASE}/api/graph/seasonal-chart?layer=${layerParam}&mode=${mode.value}`
    
    console.log('Fetching chart data from:', url)
    
    const res = await fetch(url)
    
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail?.detail || `HTTP ${res.status}: ${res.statusText}`)
    }
    
    const data = await res.json()
    console.log('Chart data received:', data)
    
    if ((!data.seasons || data.seasons.length === 0) && (!data.years || data.years.length === 0)) {
      throw new Error('No seasonal history data available for this layer')
    }
    
    loading.value = false   // ← show canvas BEFORE nextTick
    await nextTick()        // ← canvas is now in DOM
    renderChart(data)       // ← canvas.value is valid
  } catch (err) {
    console.error('Chart fetch error:', err)
    error.value = err.message || 'Failed to load chart data.'
    loading.value = false   // ← ensure spinner clears on error too
  }
}

// ─── Render Logic ─────────────────────────────────────────────────────────────
function renderChart(data) {
  if (!chartCanvas.value) {
    console.warn('Chart canvas not ready')
    return
  }

  const ctx = chartCanvas.value.getContext('2d')
  if (chart) {
    chart.destroy()
    chart = null
  }

  // Light theme colors
  const textColor = '#222';
  const gridColor = 'rgba(60, 60, 60, 0.08)';
  const tooltipBg = '#fff';
  const tooltipBorder = '#222';
  const unit = mode.value === 'cumulative'
    ? data.layer_config?.cumulative_unit
    : (data.layer_config?.monthly_unit || data.layer_config?.unit)
  const unitLabel = unit
    ? `${data.layer_config?.full_name || data.layer || 'Value'} (${unit})`
    : (data.layer_config?.full_name || data.layer || 'Value')

  if (mode.value === 'monthly') {
    renderMonthly(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel })
  } else {
    renderCumulative(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel })
  }
}

// ─── Monthly: single continuous time-series line ──────────────────────────────
function renderMonthly(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel }) {
  // Build a flat Rabi-season timeline: Nov -> Apr for each agricultural season.
  const labels = []
  const values = []

  const seasons = data.seasons?.length
    ? data.seasons
    : [...new Set((data.data || []).map(item => item.season || String(item.year)))].filter(Boolean)

  seasons.forEach(season => {
    const seasonData = data.data?.find(d => (d.season || String(d.year)) === season)
    data.months?.forEach((month, mIdx) => {
      labels.push(`${data.month_names?.[mIdx]?.slice(0, 3) || ''} ${season}`)
      values.push(seasonData?.monthly?.[mIdx] ?? null)
    })
  })

  if (labels.length === 0) {
    error.value = 'No data points available'
    return
  }


  const color = '#3b9fd9';
  const gradient = ctx.createLinearGradient(0, 0, 0, 420);
  gradient.addColorStop(0, color + '22'); // lighter fill
  gradient.addColorStop(1, color + '00');

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: unitLabel,
        data: values,
        borderColor: color,
        backgroundColor: gradient,
        borderWidth: 2.8,
        tension: 0.35,
        pointRadius: 3,
        pointHoverRadius: 7,
        pointBackgroundColor: color,
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        fill: true,
        spanGaps: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: {
        duration: 520,
        easing: 'easeOutQuart'
      },
      plugins: {
        canvasBackgroundPlugin: {
          color: '#fff'
        },
        legend: {
          display: true,
          position: 'top',
          align: 'end',
          labels: {
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' },
            boxWidth: 24,
            padding: 16
          }
        },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: textColor,
          bodyColor: textColor,
          borderColor: tooltipBorder,
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.y
              return v === null ? ' No data' : ` ${v.toFixed(3)}`
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 10, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' },
            maxRotation: 45,
            autoSkip: true,
            maxTicksLimit: 24
          }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' }
          },
          title: {
            display: true,
            text: unitLabel,
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' }
          }
        }
      }
    }
  })
}

// ─── Cumulative: one running total per agricultural season ────────────────────
function renderCumulative(ctx, data, { textColor, gridColor, tooltipBg, tooltipBorder, unitLabel }) {
  if (!data.data || data.data.length === 0) {
    error.value = 'No cumulative data available'
    return
  }

  const labels = data.month_names?.map(month => month.slice(0, 3)) || []

  const seasonDatasets = data.data.map((seasonData, idx) => {
    const color = YEAR_COLORS[idx % YEAR_COLORS.length]
    return {
      label: seasonData.season || String(seasonData.year),
      data: seasonData.cumulative || [],
      borderColor: color,
      backgroundColor: color + '18',
      borderWidth: 2.6,
      tension: 0.42,
      pointRadius: 3,
      pointHoverRadius: 8,
      pointBackgroundColor: color,
      pointBorderColor: '#ffffff',
      pointBorderWidth: 2,
      fill: false,
      spanGaps: false
    }
  })

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: seasonDatasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: {
        duration: 560,
        easing: 'easeOutQuart'
      },
      plugins: {
        canvasBackgroundPlugin: {
          color: '#fff'
        },
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' },
            boxWidth: 28,
            padding: 16,
            usePointStyle: true,
            pointStyle: 'circle'
          }
        },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: textColor,
          bodyColor: textColor,
          borderColor: tooltipBorder,
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.y
              return v === null ? `  ${ctx.dataset.label}: No data` : `  ${ctx.dataset.label}: ${v.toFixed(3)}`
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' }
          },
          title: {
            display: true,
            text: 'Rabi season months',
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' }
          }
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 11, family: "'Inter', 'Segoe UI', sans-serif", weight: '500' }
          },
          title: {
            display: true,
            text: `Cumulative ${unitLabel}`,
            color: textColor,
            font: { size: 12, family: "'Inter', 'Segoe UI', sans-serif", weight: '600' }
          }
        }
      }
    }
  })
}

// ─── Watchers & Lifecycle ─────────────────────────────────────────────────────
watch(() => selectedLayer.value, () => {
  fetchChart()
})

watch(() => props.initialLayer, layer => {
  const normalized = normalizeTrendLayer(layer, mode.value)
  if (normalized !== selectedLayer.value) selectedLayer.value = normalized
})

watch(() => mode.value, () => {
  const normalized = normalizeTrendLayer(selectedLayer.value, mode.value)
  if (normalized !== selectedLayer.value) {
    selectedLayer.value = normalized
    return
  }
  fetchChart()
})

watch(() => props.isDark, () => {
  if (chart) {
    fetchChart() // Re-render with new theme
  }
})

onMounted(() => {
  fetchChart()
})

onUnmounted(() => {
  if (chart) {
    chart.destroy()
    chart = null
  }
})
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: clamp(0.65rem, 1.4vw, 1rem);
  gap: 0.75rem;
  background: #fff;
  color: #1b485f;
  font-family: 'Inter', 'Segoe UI', sans-serif;
  border-radius: 12px;
  overflow: hidden;
  animation: chartPanelIn 0.24s cubic-bezier(.2,.8,.2,1) both;
}

/* ── Controls ── */
.chart-controls {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0;
  min-width: 0;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.control-group label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #0d1012;
  white-space: nowrap;
}

/* Select */
.select-wrapper {
  position: relative;
  min-width: 0;
  flex: 1 1 auto;
}

.select {
  padding: 0.45rem 2.25rem 0.45rem 1rem;
  border: 1px solid rgba(200, 210, 220, 0.2);
  border-radius: 30px;
  background: #0d1319;
  font-size: 0.875rem;
  color: #f0f4f8;
  outline: none;
  cursor: pointer;
  appearance: none;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.select:hover { border-color: #2f855a; }
.select:focus { border-color: #2b6cb0; box-shadow: 0 0 0 4px rgba(43, 108, 176, 0.12); }

.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: #8899aa;
}

/* Toggle */
.toggle-switch {
  display: flex;
  flex: 0 0 auto;
  background: rgba(40, 95, 150, 0.1);
  border-radius: 30px;
  padding: 3px;
  gap: 2px;
}

.toggle-option {
  padding: 0.4rem 1rem;
  border: none;
  background: transparent;
  border-radius: 30px;
  font-size: 0.875rem;
  font-weight: 500;
  color: #8899aa;
  white-space: nowrap;
  cursor: pointer;
  transition: transform 0.18s ease, background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}
.toggle-option:hover { transform: translateY(-1px); }

.toggle-option.active {
  background: #2f855a;
  color: #f0f4f8;
  box-shadow: 0 6px 16px rgba(47, 133, 90, 0.3);
}

/* Badge */
.chart-type-badge {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-left: auto;
  padding: 0.35rem 0.85rem;
  background: rgba(47, 133, 90, 0.15);
  border: 1px solid rgba(47, 133, 90, 0.3);
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 500;
  color: #3b9fd9;
}

/* Loading */
.loading-overlay {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: #8899aa;
  font-size: 0.9rem;
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(200, 210, 220, 0.2);
  border-top-color: #2f855a;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* Error */
.error-box {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  color: #f87171;
  font-size: 0.9rem;
  background: rgba(127, 29, 29, 0.2);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: 12px;
  padding: 1.5rem;
  margin: 1rem 0;
}

:global(.dark) .error-box {
  background: rgba(127, 29, 29, 0.3);
  border-color: rgba(248, 113, 113, 0.4);
}

/* Chart */
.chart-wrapper {
  flex: 1;
  min-height: 0;
  height: 0;
  position: relative;
  background: #fff;
  border: 1px solid rgba(60, 60, 60, 0.08);
  border-radius: 10px;
  padding: clamp(0.2rem, 0.8vw, 0.35rem);
  animation: chartSurfaceIn 0.32s cubic-bezier(.2,.8,.2,1) both;
}

.chart {
  position: absolute !important;
  top: 0;
  left: 0;
  width: 100% !important;
  height: 100% !important;
}

/* Responsive */
@media (max-width: 768px) {
  .chart-container { padding: 0.65rem; gap: 0.65rem; }

  .chart-controls {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .control-group { width: 100%; }

  .select { min-width: 0; width: 100%; }

  .chart-type-badge { margin-left: 0; }
}

@media (max-width: 460px) {
  .chart-container { padding: 0.55rem; gap: 0.55rem; }
  .control-group {
    align-items: stretch;
    flex-direction: column;
    gap: 0.38rem;
  }
  .control-group label {
    font-size: 0.72rem;
  }
  .toggle-switch {
    width: 100%;
  }
  .toggle-option {
    flex: 1;
    padding-inline: 0.65rem;
    font-size: 0.8rem;
  }
}

@keyframes chartPanelIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes chartSurfaceIn {
  from { opacity: 0; transform: scale(0.985); }
  to { opacity: 1; transform: scale(1); }
}
</style>
