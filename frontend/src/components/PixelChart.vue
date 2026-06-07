<template>
  <div class="chart-container" :class="[{ compact }, theme === 'glass' ? 'glass' : 'light']">

    <!-- ── Header ── -->
    <div class="pixel-header">
      <div class="pixel-meta">
      </div>
    </div>

    <!-- ── Controls ── -->
    <div class="chart-controls">

      <div class="control-group view-control">
        <label>Season</label>
        <div ref="seasonDropdownRef" class="season-multi-select" :class="{ open: seasonMenuOpen }">
          <button
            type="button"
            class="season-select-button"
            :disabled="availableSeasons.length === 0"
            :aria-expanded="seasonMenuOpen"
            aria-haspopup="listbox"
            aria-label="Pixel graph seasons"
            @click="toggleSeasonMenu"
          >
            <span>{{ selectedSeasonSummary }}</span>
            <svg class="select-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>

          <div v-if="seasonMenuOpen" class="season-menu" role="listbox" aria-label="Season selection">
            <label class="season-option season-option-all">
              <input
                type="checkbox"
                :checked="isAllSeasonsSelected"
                :disabled="availableSeasons.length === 0"
                @change="toggleAllSeasons"
              />
              <span>All seasons</span>
            </label>
            <label
              v-for="season in availableSeasons"
              :key="season"
              class="season-option"
            >
              <input
                type="checkbox"
                :checked="activeSeasonSet.has(season)"
                @change="toggleSeason(season)"
              />
              <span>{{ season }}</span>
            </label>
          </div>
        </div>
      </div>
    </div>

    

    <!-- ── Loading ── -->
    <div v-if="!pixelData" class="loading-overlay">
      <div class="chart-skeleton-line short"></div>
      <div class="chart-skeleton-panel">
        <span v-for="n in 8" :key="n"></span>
      </div>
      <div class="chart-skeleton-line"></div>
    </div>

    <!-- ── Error ── -->
    <div v-else-if="error" class="error-box">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      {{ error }}
    </div>

    <!-- ── No Data ── -->
    <div v-else-if="recordCount === 0" class="error-box no-data-box">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3 3h18v18H3z"/><path d="M9 9l6 6M15 9l-6 6"/>
      </svg>
      <template v-if="chartLayers.length === 0">Select a layer to show the pixel graph.</template>
      <template v-else>No data stored for <strong>{{ chartLayerLabel }}</strong> at this pixel yet.</template>
    </div>

    <!-- ── Chart ── -->
    <div v-else class="chart-wrapper">
      <div
        ref="chartViewport"
        class="chart-viewport"
      >
        <canvas ref="chartCanvas" class="chart"></canvas>
      </div>
    </div> 

    <!-- ── Record count hint ── -->
    <div class="record-hint" v-if="pixelData && recordCount > 0">
      {{ activeSeasonLabel }} · {{ recordCount }} observations
    </div>

  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, onUnmounted, nextTick, computed } from 'vue'
import Chart from 'chart.js/auto'

// ── Canvas background plugin (same as DataChart) ──────────────────────────
const canvasBackgroundPlugin = {
  id: 'canvasBackgroundPlugin',

  beforeDraw(chartInstance) {
    if (!chartInstance) return false

    const ctx = chartInstance.ctx
    const canvas = chartInstance.canvas

    if (!ctx) return false
    if (!canvas) return false
    if (!canvas.isConnected) return false

    const width = chartInstance.width
    const height = chartInstance.height

    const color =
      chartInstance.options?.plugins?.canvasBackgroundPlugin?.color ||
      'rgba(0,0,0,0)'

    ctx.save()
    ctx.fillStyle = color
    ctx.fillRect(0, 0, width, height)
    ctx.restore()
    return true
  },

  beforeDatasetsDraw(chartInstance) {
    if (!chartInstance?.ctx) return false
    if (!chartInstance?.canvas?.isConnected) return false
    return true
  },

  beforeDatasetDraw(chartInstance) {
    if (!chartInstance?.ctx) return false
    if (!chartInstance?.canvas?.isConnected) return false
    return true
  }
}
Chart.register(canvasBackgroundPlugin)

// ── Props ─────────────────────────────────────────────────────────────────
const props = defineProps({
  pixelData: { type: Object, default: null },        // full /api/pixel-timeseries response
  initialLayer: { type: String, default: null },
  modelLayer: { type: String, default: null },
  modelMode: { type: String, default: null },
  modelOpacity: { type: Number, default: null },
  visibleLayers: { type: Array, default: () => [] },
  theme: { type: String, default: 'light' },
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelLayer', 'update:modelMode', 'update:modelOpacity'])
const theme = computed(() => props.theme)
const compact = computed(() => props.compact)

// ── State ─────────────────────────────────────────────────────────────────
const chartCanvas = ref(null)
const chartViewport = ref(null)
const seasonDropdownRef = ref(null)
let chart = null
let chartViewportObserver = null
let chartLayoutFrame = null
let chartBuildFrame = null
let chartBuildRun = 0
let componentAlive = true
let chartBuildInProgress = false
let chartDestroying = false

const selectedLayer = ref(props.modelLayer || props.initialLayer || null)
const mode = ref('monthly')
const error = ref(null)
const chartOpacity = ref(clamp(Number(props.modelOpacity) || 0.9, 0.2, 1))
const chartViewportWidth = ref(0)
const chartViewportHeight = ref(0)
const selectedSeasons = ref([])
const seasonMenuOpen = ref(false)

const MIN_CHART_VIEWPORT_WIDTH = 280

// ── Layer metadata (same units as DataChart / info panel) ─────────────────
const LAYER_CONFIG = {
  savi: { full_name: 'SAVI',  unit: '' },
  kc:   { full_name: 'KC',    unit: '' },
  cwr:  { full_name: 'CWR',   unit: 'mm/day' },
  iwr:  { full_name: 'IWR',   unit: 'mm/day' },
  etc:  { full_name: 'ETC',   unit: 'mm/day' },
}
const layerKeys = Object.keys(LAYER_CONFIG)

const MONTH_NAMES_SHORT = {
  '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
  '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
  '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}

// Multi-season colour palette — matches DataChart's YEAR_COLORS
const SEASON_COLORS = [
  '#0f4c81', '#1f7a5c', '#d97706', '#c2410c',
  '#0f766e', '#b91c1c', '#7c3aed', '#4b5563',
  '#0284c7', '#65a30d',
]

const LAYER_COLORS = {
  savi: '#7ddc6f',
  kc: '#3b9fd9',
  cwr: '#facc15',
  iwr: '#f97316',
  etc: '#a78bfa',
}
// ── Helpers ───────────────────────────────────────────────────────────────

/** Return actual raster observations sorted by acquisition date. */
function buildObservationSeries(records) {
  return [...records]
    .filter(r => r.date && r.value !== null && r.value !== undefined)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map(r => ({
      date: r.date,
      value: Number(r.value),
    }))
    .filter(r => Number.isFinite(r.value))
}

function formatDateLabel(dateStr) {
  const [y, mo, d] = dateStr.split('-')
  return `${MONTH_NAMES_SHORT[mo]} ${Number(d)}, ${y}`
}

function getSeasonId(dateInput) {
  const date = dateInput instanceof Date ? dateInput : new Date(`${dateInput}T00:00:00`)
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const startYear = month >= 11 ? year : year - 1
  return `${startYear}-${String(startYear + 1).slice(-2)}`
}

function seasonDateKey(dateStr) {
  const [, mo, d] = dateStr.split('-')
  return `${mo}-${d}`
}

function seasonDateSortValue(key) {
  const [mo, d] = key.split('-')
  const month = Number(mo)
  const day = Number(d)
  const monthOrder = [11, 12, 1, 2, 3, 4]
  const monthIndex = monthOrder.indexOf(month)
  return (monthIndex === -1 ? 99 : monthIndex) * 40 + day
}

function formatSeasonDateLabel(key) {
  const [mo, d] = key.split('-')
  return `${MONTH_NAMES_SHORT[mo]} ${Number(d)}`
}

function seasonStartYear(season) {
  return Number(String(season || '').split('-')[0]) || 0
}

function layerColor(layer, index = 0) {
  return LAYER_COLORS[layer] || SEASON_COLORS[index % SEASON_COLORS.length]
}

function alphaHex(opacity) {
  return Math.round(clamp(opacity, 0, 1) * 255).toString(16).padStart(2, '0')
}

function selectedSeasonList(seasons = availableSeasons.value) {
  const allowed = new Set(seasons)
  const unique = selectedSeasons.value
    .filter(season => allowed.has(season))
    .filter((season, index, arr) => arr.indexOf(season) === index)
  if (unique.length > 0) return unique
  return seasons.length > 0 ? [seasons[0]] : []
}

function toggleSeasonMenu() {
  if (availableSeasons.value.length === 0) return
  seasonMenuOpen.value = !seasonMenuOpen.value
}

function toggleSeason(season) {
  if (!availableSeasons.value.includes(season)) return
  const current = selectedSeasonList()
  const hasSeason = current.includes(season)
  if (hasSeason && current.length === 1) return
  selectedSeasons.value = hasSeason
    ? current.filter(item => item !== season)
    : [...current, season].sort((a, b) => seasonStartYear(b) - seasonStartYear(a))
}

function toggleAllSeasons() {
  if (availableSeasons.value.length === 0) return
  selectedSeasons.value = isAllSeasonsSelected.value
    ? [availableSeasons.value[0]]
    : [...availableSeasons.value]
}

function handleDocumentPointerDown(event) {
  if (!seasonMenuOpen.value) return
  if (seasonDropdownRef.value?.contains(event.target)) return
  seasonMenuOpen.value = false
}

// ── Computed helpers ──────────────────────────────────────────────────────
const chartLayers = computed(() => {
  const ordered = [
    selectedLayer.value,
    ...props.visibleLayers,
  ]
  const unique = ordered
    .map(layer => String(layer || '').toLowerCase())
    .filter(layer => layerKeys.includes(layer))
    .filter((layer, index, arr) => arr.indexOf(layer) === index)

  return unique
})

const chartLayerLabel = computed(() => {
  if (chartLayers.value.length === 0) return 'Select layer'
  const labels = chartLayers.value.map(layer => LAYER_CONFIG[layer]?.full_name || layer.toUpperCase())
  return labels.length > 1 ? labels.join(' + ') : labels[0]
})

const chartRecordsByLayer = computed(() => {
  return chartLayers.value.reduce((acc, layer) => {
    acc[layer] = props.pixelData?.timeseries?.[layer] || []
    return acc
  }, {})
})

const availableSeasons = computed(() => {
  const seasons = new Set()
  ;(props.pixelData?.seasons || []).forEach(season => {
    if (season) seasons.add(String(season))
  })
  Object.values(chartRecordsByLayer.value).forEach(records => {
    buildObservationSeries(records).forEach(record => seasons.add(getSeasonId(record.date)))
  })
  return [...seasons].sort((a, b) => seasonStartYear(b) - seasonStartYear(a))
})

const activeSeasons = computed(() => selectedSeasonList())

const activeSeasonSet = computed(() => new Set(activeSeasons.value))

const isAllSeasonsSelected = computed(() => {
  return availableSeasons.value.length > 0 && activeSeasons.value.length === availableSeasons.value.length
})

const selectedSeasonSummary = computed(() => {
  if (availableSeasons.value.length === 0) return 'No seasons'
  if (isAllSeasonsSelected.value) return 'All seasons'
  if (activeSeasons.value.length === 1) return activeSeasons.value[0]
  return `${activeSeasons.value.length} seasons`
})

const activeSeasonLabel = computed(() => {
  return selectedSeasonSummary.value
})

const seasonRecordsByLayer = computed(() => {
  if (activeSeasons.value.length === 0 || isAllSeasonsSelected.value) return chartRecordsByLayer.value
  return Object.entries(chartRecordsByLayer.value).reduce((acc, [layer, records]) => {
    acc[layer] = records.filter(record => record.date && activeSeasonSet.value.has(getSeasonId(record.date)))
    return acc
  }, {})
})

const recordCount = computed(() => {
  return Object.values(seasonRecordsByLayer.value).reduce((sum, records) => sum + records.length, 0)
})

const canRenderChart = computed(() => {
  return Boolean(props.pixelData && chartLayers.value.length > 0 && recordCount.value > 0)
})

const chartCanvasWidth = computed(() => {
  const viewport = Math.max(MIN_CHART_VIEWPORT_WIDTH, chartViewportWidth.value || 0)
  return viewport
})

// ── Chart rendering ───────────────────────────────────────────────────────
function destroyChart({ cancelBuild = true } = {}) {
  chartDestroying = true
  try {
    if (chartLayoutFrame) {
      cancelAnimationFrame(chartLayoutFrame)
      chartLayoutFrame = null
    }

    if (cancelBuild && chartBuildFrame) {
      cancelAnimationFrame(chartBuildFrame)
      chartBuildFrame = null
    }

    const canvasChart = chartCanvas.value ? Chart.getChart(chartCanvas.value) : null
    const chartInstances = [chart, canvasChart].filter(Boolean)
    const uniqueChartInstances = [...new Set(chartInstances)]

    chart = null
    uniqueChartInstances.forEach(chartInstance => {
      try {
        chartInstance.stop?.()
        if (chartInstance.options) {
          chartInstance.options.animation = false
          chartInstance.options.responsive = false
        }
        chartInstance.destroy()
      } catch (err) {
        console.warn('Chart instance destroy skipped:', err)
      }
    })
  } catch (err) {
    console.warn('Chart destroy skipped:', err)
  } finally {
    chartDestroying = false
  }
}

function isChartCanvasConnected() {
  const canvas = chartCanvas.value || chart?.canvas
  return Boolean(
    componentAlive &&
    canvas &&
    canvas.isConnected &&
    canvas.ownerDocument &&
    canvas.parentNode &&
    chartViewport.value?.isConnected
  )
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function measureChartViewport() {
  if (!chartViewport.value) return
  const rect = chartViewport.value.getBoundingClientRect()
  chartViewportWidth.value = Math.floor(rect.width || chartViewport.value.clientWidth || 0)
  chartViewportHeight.value = Math.floor(rect.height || chartViewport.value.clientHeight || 0)
  if (!chart && !chartBuildInProgress && canRenderChart.value && chartViewportHeight.value > 0) {
    scheduleBuildChart()
  }
}

function attachChartViewportObserver() {
  if (!chartViewport.value) return
  if (chartViewportObserver) chartViewportObserver.disconnect()

  measureChartViewport()
  if (typeof ResizeObserver === 'undefined') return

  chartViewportObserver = new ResizeObserver(entries => {
    const entry = entries[0]
    const nextWidth = Math.floor(entry.contentRect.width)
    const nextHeight = Math.floor(entry.contentRect.height)
    const widthChanged = nextWidth !== chartViewportWidth.value
    const heightChanged = nextHeight !== chartViewportHeight.value
    chartViewportWidth.value = nextWidth
    chartViewportHeight.value = nextHeight
    if (!widthChanged && !heightChanged) return
    scheduleChartLayout()
  })
  chartViewportObserver.observe(chartViewport.value)
}

function xTickLimit(labelCount) {
  const width = chartCanvasWidth.value || chartViewportWidth.value || 800
  const target = width < 620 ? 110 : 92
  return Math.min(labelCount, Math.max(4, Math.floor(width / target)))
}

function scheduleChartLayout() {
  if (!chart) return
  if (chartLayoutFrame) cancelAnimationFrame(chartLayoutFrame)
  chartLayoutFrame = requestAnimationFrame(() => {
    chartLayoutFrame = null
    if (chartDestroying || !chart || !isChartCanvasConnected()) return
    measureChartViewport()
    if (!chartViewportWidth.value || !chartViewportHeight.value) return
    const labelCount = chart.data?.labels?.length || 0
    if (chart.options?.scales?.x?.ticks) {
      chart.options.scales.x.ticks.maxTicksLimit = xTickLimit(labelCount)
    }
    try {
      chart.resize()
      chart.update('none')
    } catch (err) {
      if (chartDestroying || !isChartCanvasConnected()) return
      console.warn('Chart layout skipped:', err)
    }
  })
}

function scheduleBuildChart() {
  if (!componentAlive) return
  if (chartBuildFrame) cancelAnimationFrame(chartBuildFrame)
  chartBuildFrame = requestAnimationFrame(() => {
    chartBuildFrame = null
    if (!componentAlive) return
    buildChart()
  })
}

async function buildChart() {
  const runId = ++chartBuildRun
  error.value = null

  if (!canRenderChart.value) return

  await nextTick()
  if (runId !== chartBuildRun) return
  chartBuildInProgress = true
  attachChartViewportObserver()
  chartBuildInProgress = false
  if (!isChartCanvasConnected()) return
  measureChartViewport()
  if (!chartViewportWidth.value || !chartViewportHeight.value) {
    setTimeout(() => {
      if (componentAlive && canRenderChart.value) scheduleBuildChart()
    }, 60)
    return
  }

  const primaryLayer = selectedLayer.value || chartLayers.value[0]
  const cfg = LAYER_CONFIG[primaryLayer] || { full_name: primaryLayer, unit: '' }
  const unitLabel = chartLayers.value.length > 1
    ? 'Value'
    : (cfg.unit ? `${cfg.full_name} (${cfg.unit})` : cfg.full_name)

  const isGlass = props.theme === 'glass'
  const textColor = '#1f2937'
  const gridColor = 'rgba(31,41,55,0.12)'
  const tooltipBg = '#fff'
  const tooltipBorder = isGlass ? 'rgba(130,185,220,0.4)' : '#222'
  const canvasBg = '#fff'

  if (runId !== chartBuildRun) return
  renderMonthly({ runId, textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg })
}

// ── Timeline: one point for each available raster date ───────────────────
function renderMonthly({ runId, textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg }) {
  if (runId !== chartBuildRun || chartDestroying || !isChartCanvasConnected()) return

  if (chartLayers.value.length === 1 && activeSeasons.value.length > 1) {
    renderSeasonComparison({ runId, textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg })
    return
  }

  const observationsByLayer = chartLayers.value.map(layer => ({
    layer,
    observations: buildObservationSeries(seasonRecordsByLayer.value[layer] || []),
  })).filter(item => item.observations.length > 0)

  if (observationsByLayer.length === 0) {
    error.value = 'No raster observations to display'
    return
  }

  const dates = [...new Set(
    observationsByLayer.flatMap(item => item.observations.map(o => o.date))
  )].sort()
  const labels = dates.map(formatDateLabel)
  const densePoints = dates.length > 140

  // const ctx = chartCanvas.value.getContext('2d')
  const canvas = chartCanvas.value
  if (!canvas || !canvas.isConnected) return
  if (runId !== chartBuildRun || !canvas.isConnected) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const opacityHex = alphaHex(chartOpacity.value)
  const datasets = observationsByLayer.map(({ layer, observations }, index) => {
    const valuesByDate = new Map(observations.map(o => [o.date, Math.round(o.value * 10000) / 10000]))
    const color = layerColor(layer, index)
    return {
      label: LAYER_CONFIG[layer]?.full_name || layer.toUpperCase(),
      data: dates.map(date => valuesByDate.get(date) ?? null),
      borderColor: color + opacityHex,
      backgroundColor: color + Math.round(chartOpacity.value * 45).toString(16).padStart(2, '0'),
      borderWidth: densePoints ? 2.1 : 2.6,
      tension: 0.35,
      pointRadius: densePoints ? 1.8 : 3,
      pointHoverRadius: densePoints ? 5 : 7,
      pointBackgroundColor: color + opacityHex,
      pointBorderColor: '#fff',
      pointBorderWidth: densePoints ? 1.2 : 1.8,
      fill: false,
      spanGaps: true,
    }
  })

  const chartConfig = {
    responsive: true,
    maintainAspectRatio: false,
    resizeDelay: 80,
    devicePixelRatio: chartCanvasWidth.value > 7000 ? 1 : Math.min(window.devicePixelRatio || 1, 1.6),
    interaction: { mode: 'index', intersect: false },
    animation: {
      duration: densePoints ? 260 : 460,
      easing: 'easeOutQuart',
    },
    transitions: {
      active: { animation: { duration: 140 } },
      resize: { animation: { duration: 180 } },
    },
    layout: { padding: { top: 8, right: 12, bottom: 6, left: 4 } },
    plugins: {
      canvasBackgroundPlugin: { color: canvasBg },
      legend: {
        display: datasets.length > 1,
        position: 'top',
        align: 'end',
        labels: {
          color: textColor,
          font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
          boxWidth: 24,
          padding: 16,
        },
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
            return v === null
              ? ` ${ctx.dataset.label}: No data`
              : ` ${ctx.dataset.label}: ${v.toFixed(4)}`
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: gridColor },
        ticks: {
          color: textColor,
          font: { size: 10, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
          maxRotation: 45,
          autoSkip: true,
          maxTicksLimit: xTickLimit(labels.length),
        },
      },
      y: {
        grid: { color: gridColor },
        ticks: {
          color: textColor,
          font: { size: 11, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
        },
        title: {
          display: true,
          text: unitLabel,
          color: textColor,
          font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
        },
      },
    },
  }

  const existingChart = chart || Chart.getChart(canvas)
  if (existingChart && existingChart.canvas === canvas && existingChart.ctx) {
    chart = existingChart
    chart.stop()
    chart.data.labels = labels
    chart.data.datasets = datasets
    chart.options = chartConfig
    try {
      chart.update('none')
      chart.resize()
    } catch (err) {
      if (isChartCanvasConnected()) console.warn('Chart update skipped:', err)
    }
    return
  }

  if (existingChart) {
    try {
      existingChart.destroy()
    } catch (err) {
      console.warn('Stale chart cleanup skipped:', err)
    }
  }

  chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets,
    },
    options: chartConfig,
  })
}

function renderSeasonComparison({ runId, textColor, gridColor, tooltipBg, tooltipBorder, unitLabel, canvasBg }) {
  if (runId !== chartBuildRun || chartDestroying || !isChartCanvasConnected()) return

  const layer = chartLayers.value[0]
  const layerRecords = chartRecordsByLayer.value[layer] || []
  const observationsBySeason = activeSeasons.value
    .map(season => ({
      season,
      observations: buildObservationSeries(layerRecords.filter(record => record.date && getSeasonId(record.date) === season)),
    }))
    .filter(item => item.observations.length > 0)

  if (observationsBySeason.length === 0) {
    error.value = 'No raster observations to display'
    return
  }

  const dateKeys = [...new Set(
    observationsBySeason.flatMap(item => item.observations.map(o => seasonDateKey(o.date)))
  )].sort((a, b) => seasonDateSortValue(a) - seasonDateSortValue(b))

  const labels = dateKeys.map(formatSeasonDateLabel)
  const canvas = chartCanvas.value
  if (!canvas || !canvas.isConnected) return
  if (runId !== chartBuildRun || !canvas.isConnected) return

  const opacityHex = alphaHex(chartOpacity.value)
  const datasets = observationsBySeason.map(({ season, observations }, index) => {
    const valuesByDateKey = new Map(
      observations.map(o => [seasonDateKey(o.date), Math.round(o.value * 10000) / 10000])
    )
    const color = SEASON_COLORS[index % SEASON_COLORS.length]
    return {
      label: season,
      data: dateKeys.map(key => valuesByDateKey.get(key) ?? null),
      borderColor: color + opacityHex,
      backgroundColor: color + Math.round(chartOpacity.value * 42).toString(16).padStart(2, '0'),
      borderWidth: 2.4,
      tension: 0.35,
      pointRadius: dateKeys.length > 90 ? 1.8 : 3,
      pointHoverRadius: 7,
      pointBackgroundColor: color + opacityHex,
      pointBorderColor: '#fff',
      pointBorderWidth: 1.8,
      fill: false,
      spanGaps: true,
    }
  })

  const chartConfig = {
    responsive: true,
    maintainAspectRatio: false,
    resizeDelay: 80,
    devicePixelRatio: chartCanvasWidth.value > 7000 ? 1 : Math.min(window.devicePixelRatio || 1, 1.6),
    interaction: { mode: 'index', intersect: false },
    animation: {
      duration: dateKeys.length > 90 ? 260 : 460,
      easing: 'easeOutQuart',
    },
    layout: { padding: { top: 8, right: 12, bottom: 6, left: 4 } },
    plugins: {
      canvasBackgroundPlugin: { color: canvasBg },
      legend: {
        display: datasets.length > 1,
        position: 'top',
        align: 'end',
        labels: {
          color: textColor,
          font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
          boxWidth: 24,
          padding: 16,
        },
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
            return v === null
              ? ` ${ctx.dataset.label}: No data`
              : ` ${ctx.dataset.label}: ${v.toFixed(4)}`
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: gridColor },
        ticks: {
          color: textColor,
          font: { size: 10, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
          maxRotation: 45,
          autoSkip: true,
          maxTicksLimit: xTickLimit(labels.length),
        },
      },
      y: {
        grid: { color: gridColor },
        ticks: {
          color: textColor,
          font: { size: 11, family: "'Inter','Segoe UI',sans-serif", weight: '500' },
        },
        title: {
          display: true,
          text: unitLabel,
          color: textColor,
          font: { size: 12, family: "'Inter','Segoe UI',sans-serif", weight: '600' },
        },
      },
    },
  }

  const existingChart = chart || Chart.getChart(canvas)
  if (existingChart && existingChart.canvas === canvas && existingChart.ctx) {
    chart = existingChart
    chart.stop()
    chart.data.labels = labels
    chart.data.datasets = datasets
    chart.options = chartConfig
    try {
      chart.update('none')
      chart.resize()
    } catch (err) {
      if (isChartCanvasConnected()) console.warn('Chart update skipped:', err)
    }
    return
  }

  if (existingChart) {
    try {
      existingChart.destroy()
    } catch (err) {
      console.warn('Stale chart cleanup skipped:', err)
    }
  }

  chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets,
    },
    options: chartConfig,
  })
}

// ── Watchers & lifecycle ──────────────────────────────────────────────────
watch(() => props.pixelData, data => {
  destroyChart()
  if (!data) {
    return
  }
  selectedSeasons.value = []
  scheduleBuildChart()
}, { flush: 'sync' })
watch(canRenderChart, canRender => {
  if (!canRender) {
    destroyChart()
    return
  }
  scheduleBuildChart()
}, { flush: 'sync' })
watch(() => props.initialLayer, layer => {
  if (!props.modelLayer && layer && layer !== selectedLayer.value) selectedLayer.value = layer
})
watch(() => props.modelLayer, layer => {
  if (layer && layer !== selectedLayer.value) selectedLayer.value = layer
  if (!layer && selectedLayer.value) selectedLayer.value = null
})
watch(() => props.modelMode, nextMode => {
  if (nextMode && nextMode !== 'monthly') emit('update:modelMode', 'monthly')
})
watch(() => props.modelOpacity, nextOpacity => {
  const normalized = clamp(Number(nextOpacity) || 0.9, 0.2, 1)
  if (normalized !== chartOpacity.value) chartOpacity.value = normalized
})
watch(() => props.visibleLayers, () => {
  if (!canRenderChart.value) destroyChart()
  scheduleBuildChart()
}, { deep: true, flush: 'post' })
watch(chartOpacity, nextOpacity => {
  emit('update:modelOpacity', nextOpacity)
  if (canRenderChart.value) scheduleBuildChart()
})
watch(selectedLayer, layer => {
  emit('update:modelLayer', layer)
  if (!canRenderChart.value) destroyChart()
  scheduleBuildChart()
}, { flush: 'post' })
watch(mode, () => {
  if (mode.value !== 'monthly') mode.value = 'monthly'
  emit('update:modelMode', 'monthly')
  scheduleBuildChart()
}, { flush: 'post' })
watch(chartCanvasWidth, () => { nextTick(scheduleChartLayout) }, { flush: 'post' })
watch(availableSeasons, seasons => {
  if (seasons.length === 0) {
    selectedSeasons.value = []
    seasonMenuOpen.value = false
  } else {
    const normalized = selectedSeasonList(seasons)
    if (normalized.join('|') !== selectedSeasons.value.join('|')) {
      selectedSeasons.value = normalized
    }
  }
}, { immediate: true })
watch(selectedSeasons, () => {
  if (!canRenderChart.value) destroyChart()
  scheduleBuildChart()
}, { deep: true, flush: 'post' })

onMounted(() => {
  componentAlive = true
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  window.addEventListener('resize', measureChartViewport)
  nextTick(() => {
    buildChart()
  })
})

onBeforeUnmount(() => {
  componentAlive = false
  chartBuildRun += 1
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  window.removeEventListener('resize', measureChartViewport)
  if (chartLayoutFrame) cancelAnimationFrame(chartLayoutFrame)
  if (chartBuildFrame) cancelAnimationFrame(chartBuildFrame)
  if (chartViewportObserver) chartViewportObserver.disconnect()
  destroyChart()
})

onUnmounted(() => {
  componentAlive = false
})
</script>

<style scoped>
/* ── Container ── */
.chart-container {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0.55rem;
  gap: 0;
  background: #ffffff;
  color: #0f172a;
  font-family: 'Inter', 'Segoe UI', sans-serif;
  border-radius: 10px;
  overflow: visible;
  box-sizing: border-box;
  animation: pixelChartIn 0.22s cubic-bezier(.2,.8,.2,1) both;
}
.chart-container.glass {
  padding: 0;
  background: transparent;
  color: #0f172a;
}
.chart-container.compact {
  gap: 0;
}

/* ── Pixel header ── */
.pixel-header {
  margin-bottom: 0;
}
.chart-container.compact .pixel-header {
  margin-bottom: 0;
}
.pixel-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.pixel-id-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(59, 159, 217, 0.1);
  border: 1px solid rgba(59, 159, 217, 0.3);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 0.78rem;
  font-weight: 700;
  color: #ffffff;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
}
.chart-container.glass .pixel-id-badge {
  background: rgba(59, 159, 217, 0.14);
  border-color: rgba(59, 159, 217, 0.36);
  color: #92cdf8;
}
.pixel-coords {
  font-size: 0.77rem;
  color: #607d8b;
  font-family: 'JetBrains Mono', monospace;
}
.chart-container.glass .pixel-coords {
  color: #9db8c9;
}

/* ── Controls (reuse DataChart styles exactly) ── */
.chart-controls {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0.35rem;
  margin-bottom: 0.4rem;
  min-width: 0;
  flex: 0 0 auto;
}
.chart-container.compact .chart-controls {
  margin-bottom: 0.35rem;
}
.control-group {
  display: flex;
  align-items: center;
  gap: 0.28rem;
  min-width: 0;
}
.layer-control {
  flex: 1 1 auto;
  align-items: center;
  flex-direction: row;
  max-width: none;
  min-width: 0;
}
.view-control {
  flex: 0 1 240px;
  flex-direction: row;
  align-items: center;
  max-width: min(100%, 280px);
}
.control-group label {
  font-size: 0.62rem;
  font-weight: 600;
  color: #475569;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}
.chart-container.glass .control-group label {
  color: #334155;
}
.selected-layer-badge {
  min-height: 28px;
  min-width: 0;
  max-width: 100%;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.24rem 0.55rem;
  border: 1px solid rgba(180, 205, 222, 0.16);
  border-radius: 8px;
  background: #fff;
  color: #111827;
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.layer-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  flex: 0 0 auto;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.08);
}
.layer-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}
.layer-tab {
  min-width: 0;
  height: 38px;
  border: 1px solid rgba(180, 205, 222, 0.12);
  border-radius: 10px;
  color: #a8bfd0;
  background: rgba(255, 255, 255, 0.055);
  font-size: 0.82rem;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}
.layer-tab:hover {
  transform: translateY(-1px);
  border-color: rgba(120, 180, 220, 0.28);
  color: #f4fbff;
}
.layer-tab.active {
  color: #041015;
  border-color: transparent;
  box-shadow: 0 12px 22px rgba(0, 0, 0, 0.18);
}
.layer-tab.savi.active { background: linear-gradient(135deg, #6ee787, #3bbd52); }
.layer-tab.kc.active   { background: linear-gradient(135deg, #70b7ff, #3679df); }
.layer-tab.cwr.active  { background: linear-gradient(135deg, #ffd36c, #f59e0b); }
.layer-tab.iwr.active  { background: linear-gradient(135deg, #d59cff, #9b5de5); }
.layer-tab.etc.active  { background: linear-gradient(135deg, #70f1f5, #19b6d2); }
.select-wrapper {
  position: relative;
  width: 100%;
}
.select {
  width: 100%;
  height: 40px;
  padding: 0.45rem 2.35rem 0.45rem 0.9rem;
  border: 1px solid rgba(180, 205, 222, 0.16);
  border-radius: 10px;
  background: #ffffff;
  font-size: 0.86rem;
  font-weight: 800;
  color: #0f172a;
  outline: none;
  cursor: pointer;
  appearance: none;
  min-width: 0;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}
.select option {
  background: #ffffff;
  color: #0f172a;
}
.select:hover { border-color: rgba(59, 159, 217, 0.45); }
.select:focus {
  border-color: rgba(59, 159, 217, 0.72);
  box-shadow: 0 0 0 4px rgba(59, 159, 217, 0.14);
}
.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: #64748b;
  display: inline-flex;
}
.season-multi-select {
  position: relative;
  width: 100%;
  min-width: 0;
  z-index: 8;
}
.season-multi-select.open {
  z-index: 40;
}
.season-select-button {
  position: relative;
  width: 100%;
  height: 40px;
  min-width: 0;
  padding: 0.45rem 2.35rem 0.45rem 0.9rem;
  border: 1px solid rgba(180, 205, 222, 0.16);
  border-radius: 10px;
  background: #ffffff;
  color: #0f172a;
  font-size: 0.84rem;
  font-weight: 800;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}
.season-select-button span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.season-select-button:hover {
  border-color: rgba(59, 159, 217, 0.45);
}
.season-select-button:focus-visible {
  outline: none;
  border-color: rgba(59, 159, 217, 0.72);
  box-shadow: 0 0 0 4px rgba(59, 159, 217, 0.14);
}
.season-select-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.season-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: max(100%, 220px);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(86px, 1fr));
  gap: 6px;
  padding: 8px;
  border: 1px solid rgba(100, 116, 139, 0.16);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18);
  overflow: visible;
  max-height: none;
  animation: seasonMenuIn 0.16s cubic-bezier(.2,.8,.2,1) both;
}
.season-option {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background: #f8fafc;
  color: #0f172a;
  font-size: 0.74rem;
  font-weight: 800;
  cursor: pointer;
  user-select: none;
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}
.season-option:hover {
  transform: translateY(-1px);
  border-color: rgba(59, 159, 217, 0.32);
  background: #eef6fb;
}
.season-option input {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  accent-color: #0284c7;
}
.season-option span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.season-option-all {
  grid-column: 1 / -1;
  background: #eef6fb;
  color: #075985;
}
.toggle-switch,
.view-badge {
  display: flex;
  background: rgba(40, 95, 150, 0.1);
  border-radius: 999px;
}
.view-badge {
  align-items: center;
  height: 28px;
  padding: 0 0.5rem;
  border: 1px solid rgba(180, 205, 222, 0.12);
  color: #111827;
  background: #fff;
  font-size: 0.7rem;
  font-weight: 800;
}
.chart-container.glass .toggle-switch {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(180, 205, 222, 0.1);
}
.toggle-option {
  height: 32px;
  padding: 0 0.95rem;
  border: none;
  background: transparent;
  border-radius: 30px;
  font-size: 0.82rem;
  font-weight: 700;
  color: #8899aa;
  cursor: pointer;
  transition: all 0.2s;
}
.toggle-option.active {
  background: #2f855a;
  color: #f0f4f8;
  box-shadow: 0 6px 16px rgba(47, 133, 90, 0.3);
}
.chart-container.glass .toggle-option.active {
  background: #3b9fd9;
  box-shadow: 0 8px 20px rgba(59, 159, 217, 0.25);
}
.opacity-control {
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 2px 0.42rem;
  border: 1px solid rgba(180, 205, 222, 0.12);
  border-radius: 8px;
  background: #fff;
  flex: 0 0 auto;
}
.opacity-control label {
  color: #111827;
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.opacity-slider {
  width: 64px;
  accent-color: #3b9fd9;
}
.opacity-value {
  width: 31px;
  text-align: center;
  color: #111827;
  font-size: 0.65rem;
  font-weight: 800;
  font-family: 'JetBrains Mono', monospace;
}

.chart-container.glass .chart-type-badge {
  background: rgba(59, 159, 217, 0.12);
  border-color: rgba(59, 159, 217, 0.24);
  color: #91d5ff;
}

/* ── Loading ── */
.loading-overlay {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 0.85rem;
  color: #8899aa;
  font-size: 0.9rem;
}
.chart-container.glass .loading-overlay {
  color: #64748b;
}
.chart-skeleton-line,
.chart-skeleton-panel,
.chart-skeleton-panel span {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.16);
}
.chart-skeleton-line {
  height: 14px;
  max-width: 100%;
}
.chart-skeleton-line.short {
  width: 42%;
}
.chart-skeleton-panel {
  height: min(280px, 46vh);
  display: grid;
  grid-template-columns: repeat(8, minmax(18px, 1fr));
  align-items: end;
  gap: 10px;
  padding: 18px;
  border: 1px solid rgba(100, 116, 139, 0.12);
}
.chart-skeleton-panel span {
  min-height: 52px;
  height: 58%;
}
.chart-skeleton-panel span:nth-child(2n) { height: 46%; }
.chart-skeleton-panel span:nth-child(3n) { height: 68%; }
.chart-skeleton-line::after,
.chart-skeleton-panel::after,
.chart-skeleton-panel span::after {
  content: "";
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.14), transparent);
  animation: shimmer 1.35s ease-in-out infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes shimmer { to { transform: translateX(100%); } }

/* ── Error / no-data ── */
.error-box {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  color: #f87171;
  font-size: 0.9rem;
  background: rgba(127, 29, 29, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: 12px;
  padding: 1.5rem;
  margin: 0.5rem 0;
}
.chart-container.glass .error-box {
  color: #fecaca;
  background: rgba(127, 29, 29, 0.16);
  border-color: rgba(248, 113, 113, 0.25);
}
.no-data-box {
  color: #64748b;
  background: rgba(100, 116, 139, 0.08);
  border-color: rgba(100, 116, 139, 0.25);
}
.chart-container.glass .no-data-box {
  color: #64748b;
  background: #f8fafc;
  border-color: rgba(100, 116, 139, 0.16);
}

/* ── Chart wrapper (reuse DataChart) ── */
.chart-wrapper {
  flex: 1;
  min-height: 0;
  height: 0;
  min-width: 0;
  position: relative;
  background: #fff;
  border: 1px solid rgba(60, 60, 60, 0.08);
  border-radius: 10px;
  padding: 0;
  overflow: hidden;
  animation: pixelChartSurfaceIn 0.28s cubic-bezier(.2,.8,.2,1) both;
}
.chart-container.glass .chart-wrapper {
  background: #fff;
  border-color: rgba(100, 116, 139, 0.14);
  border-radius: 8px;
  box-shadow: none;
}
.chart-viewport {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  position: relative;
  overflow-x: hidden;
  overflow-y: hidden;
  overscroll-behavior: contain;
  cursor: default;
  scrollbar-width: none;
}
.chart-viewport::-webkit-scrollbar {
  display: none;
}
.chart {
  display: block;
  width: 100% !important;
  height: 100% !important;
  min-width: 100%;
  box-sizing: border-box;
}

.pixel-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}
.stat-card {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(60, 60, 60, 0.08);
  border-radius: 12px;
  background: rgba(40, 95, 150, 0.06);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}
.stat-card span {
  color: #64748b;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.stat-card strong {
  color: #1b485f;
  font-size: 0.95rem;
  font-family: 'JetBrains Mono', monospace;
}
.chart-container.glass .stat-card {
  border-color: rgba(180, 205, 222, 0.1);
  background: rgba(255, 255, 255, 0.055);
}
.chart-container.glass .stat-card span {
  color: #8ba8bb;
}
.chart-container.glass .stat-card strong {
  color: #74f08b;
}

/* ── Record hint ── */
.record-hint {
  font-size: 0.68rem;
  color: #334155;
  text-align: right;
  padding: 4px 2px 0;
}
.chart-container.glass .record-hint {
  color: #334155;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .chart-container { padding: 0.65rem; }
  .chart-container.glass { padding: 0; }
  .chart-controls {
    gap: 0.35rem;
    overflow: visible;
    padding-bottom: 2px;
  }
  .control-group { width: auto; flex-shrink: 0; }
  .layer-control { max-width: none; }
  .view-control { width: 100%; max-width: 100%; }
  .toggle-switch { width: auto; }
  .toggle-option { flex: 1; }
  .select { min-width: 0; width: 100%; }
  .season-menu {
    right: auto;
    left: 0;
    width: min(100vw - 32px, 360px);
    grid-template-columns: repeat(auto-fit, minmax(82px, 1fr));
  }
  .opacity-control { grid-column: 1 / -1; width: auto; justify-content: center; }
  .opacity-slider { flex: 0 0 64px; }
  .chart-type-badge { margin-left: 0; }
  .layer-tabs { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .pixel-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 480px) {
  .layer-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .layer-tab { height: 36px; font-size: 0.78rem; }
  .season-option {
    padding: 6px 7px;
    font-size: 0.7rem;
  }
  .pixel-stats { gap: 8px; }
}

@keyframes pixelChartIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes pixelChartSurfaceIn {
  from { opacity: 0; transform: scale(0.99); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes seasonMenuIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
