<!-- MapView.vue -->
<template>
  <div class="map-container">
    <div id="map" ref="mapEl" class="map"></div>

    <div
      class="basemap-switcher-control"
      role="radiogroup"
      aria-label="Basemap selector"
      @pointerdown.stop
      @click.stop
      @dblclick.stop
    >
      <button
        v-for="style in mapStyles"
        :key="style.name"
        type="button"
        class="basemap-card"
        :class="{ active: currentMapStyle === style.name }"
        :aria-pressed="currentMapStyle === style.name"
        :title="`Switch to ${style.name}`"
        @click="selectMapStyle(style.name)"
      >
        <span class="basemap-card-thumb">
          <img :src="style.thumbnail" :alt="`${style.name} preview`" loading="lazy" />
        </span>
        <span class="basemap-card-name">{{ style.name }}</span>
      </button>
    </div>


    <button
      class="location-btn"
      @click="getCurrentLocation"
      :class="{ loading: isLocating }"
      :disabled="isLocating"
      :title="isLocating ? 'Detecting your location' : 'Use current location'"
      :aria-label="isLocating ? 'Detecting your location' : 'Use current location'"
    >
      <span class="location-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1">
          <circle cx="12" cy="12" r="3.5" />
          <path stroke-linecap="round" d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
        </svg>
      </span>
      <span class="location-spinner" v-if="isLocating" aria-hidden="true"></span>
    </button>

    <!-- Selected Point Icon (Top of bottom-left group) -->

    <!-- Unified Pixel Popup (hover follows cursor, click pins the same card) -->
    <div
      class="pixel-value-popup"
      v-if="showUnifiedPixelPopup"
      :class="{ pinned: unifiedPopupPinned, light: !isDarkMode }"
      :style="{
        left: unifiedPopupPosition.x + 'px',
        top: unifiedPopupPosition.y + 'px',
        zIndex: widgetZ.popup
      }"
      @pointerdown.stop="bringWidgetToFront('popup')"
    >
      <button
        v-if="unifiedPopupPinned"
        class="pixel-popup-close"
        type="button"
        @click="closeUnifiedPixelPopup"
        aria-label="Close pixel popup"
      >×</button>
      <div class="pixel-popup-head">
        <span class="pixel-popup-kicker">{{ unifiedPopupPinned ? 'Selected pixel' : 'Pixel preview' }}</span>
        <span v-if="unifiedPopupDate" class="pixel-popup-date">{{ unifiedPopupDate }}</span>
      </div>

      <div v-if="unifiedPopupLoading" class="pixel-popup-loading">
        Fetching pixel values...
      </div>

      <div v-else-if="unifiedPopupRows.length > 0" class="pixel-popup-table">
        <div class="pixel-popup-table-head" :class="{ 'with-forecast': showForecastPopupColumns }">
          <span>Layer</span>
          <span>Today</span>
          <template v-if="showForecastPopupColumns">
            <span>5 Day</span>
            <span>10 Day</span>
            <span>15 Day</span>
          </template>
        </div>
        <div v-for="row in unifiedPopupRows" :key="row.layer" class="pixel-popup-row" :class="{ 'with-forecast': showForecastPopupColumns }">
          <span class="pixel-popup-layer">{{ row.label }}</span>
          <span class="pixel-popup-value">{{ row.today }}</span>
          <template v-if="showForecastPopupColumns">
            <template v-if="row.forecastAllowed">
              <span class="pixel-popup-value forecast">{{ row.five }}</span>
              <span class="pixel-popup-value forecast">{{ row.ten }}</span>
              <span class="pixel-popup-value forecast">{{ row.fifteen }}</span>
            </template>
            <template v-else>
              <span class="pixel-popup-empty-cell" aria-hidden="true"></span>
              <span class="pixel-popup-empty-cell" aria-hidden="true"></span>
              <span class="pixel-popup-empty-cell" aria-hidden="true"></span>
            </template>
          </template>
        </div>
      </div>

      <div v-else class="pixel-popup-empty">
        No layer data here
      </div>
    </div>

    <!-- Live Mouse Coordinate Display -->
    <div class="mouse-coordinate-display" v-if="hoverCoords">
      {{ hoverCoords.lng }}, {{ hoverCoords.lat }}
    </div>

    <!-- Chart Panel (draggable + resizable) -->
    <Transition name="map-widget" appear>
      <div
        class="chart-panel"
        :class="{
          'chart-dragging': chartDragging,
          'chart-resizing': chartResizing,
          'chart-maximized': chartWidgetMaximized,
          'chart-minimized': chartWidgetMinimized
        }"
        v-if="props.chartVisible"
        :style="chartWidgetStyle"
        @pointerdown.stop="bringWidgetToFront('chart')"
      >
        <!-- Drag header -->
        <div class="chart-panel-header" @pointerdown="startChartDrag">
          <div class="chart-panel-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M4 19h16M7 16V9M12 16V5M17 16v-7"/>
            </svg>
            <span>Crop Trends</span>
          </div>
          <div class="chart-panel-actions">
            <button
              class="chart-panel-action"
              @click.stop="toggleChartMinimized"
              :title="chartWidgetMinimized ? 'Restore' : 'Minimize'"
            >
              <svg v-if="chartWidgetMinimized" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3">
                <path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/>
                <path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
              </svg>
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
            <button
              class="chart-panel-action"
              @click.stop="toggleChartMaximized"
              :title="chartWidgetMaximized ? 'Restore' : 'Maximize'"
            >
              <svg v-if="chartWidgetMaximized" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M8 3v5H3"/><path d="M16 3v5h5"/>
                <path d="M8 21v-5H3"/><path d="M16 21v-5h5"/>
              </svg>
              <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/>
                <path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
              </svg>
            </button>
            <button
              class="chart-panel-action chart-panel-close"
              @click.stop="emit('update:chart-visible', false)"
              title="Close"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Chart body -->
        <div class="chart-panel-body" v-show="!chartWidgetMinimized">
          <DataChart
            title="Wheat Crop Parameters - Historical Data"
            :initial-layer="props.selectedLayer || activeLayers[0]?.name || 'cwr'"
            :is-dark="false"
            :show-boundary-data="true"
          />
        </div>

        <!-- Resize handles -->
        <div
          v-for="handle in chartResizeHandles"
          v-show="!chartWidgetMinimized && !chartWidgetMaximized"
          :key="handle"
          :class="['chart-resize-handle', `chart-resize-${handle}`]"
          @pointerdown.stop.prevent="startChartResize(handle, $event)"
        ></div>
      </div>
    </Transition>

    <!-- Weather Panel -->
    <!-- <Transition name="map-widget" appear>
      <div
        class="weather-panel"
        v-if="weatherVisible"
        :style="{ zIndex: widgetZ.weather }"
        @pointerdown.stop="bringWidgetToFront('weather')"
      >
        <button class="close-btn" @click="weatherVisible = false">×</button>
        <div class="weather-content">
          <h2 class="weather-title">🌤️ Weather Forecast</h2>
        
        <div class="weather-header">
          <div class="weather-location-info">
            <p class="location-name">{{ props.weatherSummary?.location || 'Selected Location' }}</p>
            <p class="location-coords" v-if="pointData">
              {{ pointData.lat?.toFixed(4) }}°N, {{ pointData.lon?.toFixed(4) }}°E
            </p>
          </div>
          <p class="weather-date">{{ props.weatherSummary?.dateLabel || 'Today' }}</p>
        </div>

        <div class="weather-grid">
          <div class="weather-card" v-if="props.weatherSummary?.temperature">
            <span class="weather-icon">🌡️</span>
            <span class="weather-label">Temperature</span>
            <span class="weather-value">{{ props.weatherSummary.temperature }}°C</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.humidity">
            <span class="weather-icon">💧</span>
            <span class="weather-label">Humidity</span>
            <span class="weather-value">{{ props.weatherSummary.humidity }}%</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.windSpeed">
            <span class="weather-icon">💨</span>
            <span class="weather-label">Wind Speed</span>
            <span class="weather-value">{{ props.weatherSummary.windSpeed }} m/s</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.rainfall">
            <span class="weather-icon">🌧️</span>
            <span class="weather-label">Rainfall</span>
            <span class="weather-value">{{ props.weatherSummary.rainfall }} mm</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.solarRadiation">
            <span class="weather-icon">☀️</span>
            <span class="weather-label">Solar Radiation</span>
            <span class="weather-value">{{ props.weatherSummary.solarRadiation }} MJ/m²</span>
          </div>
          <div class="weather-card" v-if="props.weatherSummary?.windDirection">
            <span class="weather-icon">🧭</span>
            <span class="weather-label">Wind Direction</span>
            <span class="weather-value">{{ props.weatherSummary.windDirection }}°</span>
          </div>
        </div>

        <p v-if="!props.weatherSummary" class="no-weather-data">
          No weather data available for this location.
        </p>
        </div>
      </div>
    </Transition> -->
    <!-- ── Floating Pixel Trend Widget ─────────────────────────────────── -->
    <Transition name="pixel-widget-fade" appear>
      <aside
        class="pixel-trend-widget"
        :class="{
          minimized: pixelWidgetMinimized,
          maximized: pixelWidgetMaximized,
          dragging: pixelWidgetDragging,
          resizing: pixelWidgetResizing
        }"
        :style="pixelWidgetStyle"
        v-if="showPixelWidget"
        aria-live="polite"
        @pointerdown.stop="bringWidgetToFront('pixel')"
      >
        <div class="pixel-widget-header" @pointerdown="startPixelWidgetDrag">
          <div class="pixel-widget-title">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2.2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            <span>Pixel Time Series</span>
          </div>
          <div class="pixel-widget-actions">
            <button
              class="pixel-widget-action"
              @click="togglePixelWidgetMinimized"
              :aria-label="pixelWidgetMinimized ? 'Restore pixel chart' : 'Minimize pixel chart'"
              :title="pixelWidgetMinimized ? 'Restore' : 'Minimize'"
            >
              <svg v-if="pixelWidgetMinimized" width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2.3">
                <path d="M8 3H5a2 2 0 0 0-2 2v3"/>
                <path d="M16 3h3a2 2 0 0 1 2 2v3"/>
                <path d="M8 21H5a2 2 0 0 1-2-2v-3"/>
                <path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2.5">
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </button>
            <button
              class="pixel-widget-action"
              @click="togglePixelWidgetMaximized"
              :aria-label="pixelWidgetMaximized ? 'Restore graph window' : 'Maximize graph window'"
              :title="pixelWidgetMaximized ? 'Restore' : 'Maximize'"
            >
              <svg v-if="pixelWidgetMaximized" width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2.2">
                <path d="M8 3v5H3"/>
                <path d="M16 3v5h5"/>
                <path d="M8 21v-5H3"/>
                <path d="M16 21v-5h5"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2.2">
                <path d="M8 3H5a2 2 0 0 0-2 2v3"/>
                <path d="M16 3h3a2 2 0 0 1 2 2v3"/>
                <path d="M8 21H5a2 2 0 0 1-2-2v-3"/>
                <path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
              </svg>
            </button>
            <button
              class="pixel-widget-action close"
              @click="closePixelWidget"
              aria-label="Close pixel chart"
              title="Close"
            >
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        <div class="pixel-widget-body" v-show="!pixelWidgetMinimized">
          <div v-if="pixelTimeSeriesLoading" class="pixel-widget-loading" aria-busy="true">
            <div class="pixel-loading-copy">
              <strong>Reading raster pixels</strong>
              <span>Refreshing the time series for this location…</span>
            </div>
            <div class="pixel-loading-grid">
              <span></span>
              <span></span>
            </div>
            <div class="pixel-loading-chart">
              <span v-for="n in 10" :key="n"></span>
            </div>
          </div>

          <div v-else-if="pixelTimeSeriesError" class="pixel-widget-error">
            <strong>Unable to load pixel trend</strong>
            <span>{{ pixelTimeSeriesError }}</span>
          </div>

          <PixelChart
            v-else-if="pixelTimeSeries"
            v-model:modelLayer="pixelWidgetLayer"
            v-model:modelMode="pixelWidgetMode"
            :pixelData="pixelTimeSeries"
            :initialLayer="pixelWidgetLayer || activeLayers[0]?.name || null"
            :visibleLayers="activeLayers.map(layer => layer.name)"
            theme="glass"
            compact
            class="pixel-widget-chart"
          />

          <div v-else class="pixel-widget-empty">
            Click a raster pixel to load SAVI, KC, CWR, IWR, and ETC trends.
          </div>
        </div>

        <div
          v-for="handle in pixelResizeHandles"
          v-show="!pixelWidgetMinimized && !pixelWidgetMaximized"
          :key="handle"
          :class="['pixel-resize-handle', `pixel-resize-${handle}`]"
          @pointerdown.stop.prevent="startPixelWidgetResize(handle, $event)"
        ></div>
      </aside>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, onUnmounted, watch, computed } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import DataChart from './DataChart.vue'
import PixelChart from './PixelChart.vue'
//const API_BASE = (process.env.VUE_APP_API_BASE || '').replace(/\/$/, '')
const API_BASE = "http://localhost:8000"
const pixelTimeSeries         = ref(null)   // /api/pixel-timeseries response
const showPixelWidget         = ref(false)
const pixelWidgetMinimized    = ref(false)
const pixelTimeSeriesLoading  = ref(false)
const pixelTimeSeriesError    = ref(null)
const selectedPixelLocation   = ref(null)
const pixelWidgetLayer        = ref(null)
const pixelWidgetMode         = ref('date')
const pixelWidgetMaximized    = ref(false)
const pixelWidgetDragging     = ref(false)
const pixelWidgetResizing     = ref(false)
const pixelWidgetFrame        = reactive({
  x: 0,
  y: 84,
  width: 760,
  height: 650,
  initialized: false,
})
const showInfoPanel = ref(true)
const pixelResizeHandles      = ['n', 'e', 's', 'w', 'ne', 'nw', 'se', 'sw']
const pixelRequestGroup       = `${Date.now()}-${Math.random().toString(36).slice(2)}`
let pixelTimeSeriesRequestId  = 0
let pixelTimeSeriesSequence   = 0
let pixelTimeSeriesController = null
let pointDataRequestId        = 0
let pointDataController       = null
let hoverPointRequestId       = 0
let hoverPointController      = null
let mapClickRequestId         = 0
let pixelWidgetPointerState   = null
let hoverFrame                = null
let hoverFetchTimer           = null
let lastHoverFetchAt          = 0
let pendingHoverPoint         = null
let pixelWidgetContainerObserver = null

// ── Chart Panel drag/resize state ─────────────────────────────────────────
const chartDragging        = ref(false)
const chartResizing        = ref(false)
const chartWidgetMaximized = ref(false)
const chartWidgetMinimized = ref(false)
const chartFrame = reactive({
  x: 0, y: 0, width: 0, height: 0, initialized: false
})
const CHART_WIDGET_GUTTER       = 12
const CHART_WIDGET_MIN_WIDTH    = 340
const CHART_WIDGET_MIN_HEIGHT   = 220
const CHART_WIDGET_DEFAULT_WIDTH  = 760
const CHART_WIDGET_DEFAULT_HEIGHT = 520
const CHART_WIDGET_HEADER_HEIGHT  = 40
const chartResizeHandles = ['n', 'e', 's', 'w', 'ne', 'nw', 'se', 'sw']
let chartPointerState = null

const PIXEL_WIDGET_GUTTER = 12
const PIXEL_WIDGET_MIN_WIDTH = 320
const PIXEL_WIDGET_MIN_HEIGHT = 260
const PIXEL_WIDGET_DEFAULT_WIDTH = 500
const PIXEL_WIDGET_DEFAULT_HEIGHT = 360
const PIXEL_WIDGET_MINIMIZED_HEIGHT = 44
const HOVER_FETCH_INTERVAL_MS = 180
const POINT_CACHE_LIMIT = 220
const PIXEL_TS_CACHE_LIMIT = 40
const pointDataCache = new Map()
const pixelTimeSeriesCache = new Map()

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function getMapContainerRect() {
  const container = mapEl.value?.closest('.map-container')
  return container?.getBoundingClientRect() || {
    width: window.innerWidth,
    height: window.innerHeight,
  }
}

function getPixelWidgetLimits() {
  const rect = getMapContainerRect()
  const maxWidth = Math.max(280, rect.width - PIXEL_WIDGET_GUTTER * 2)
  const maxHeight = Math.max(260, rect.height - PIXEL_WIDGET_GUTTER * 2)
  return {
    containerWidth: rect.width,
    containerHeight: rect.height,
    minWidth: Math.min(PIXEL_WIDGET_MIN_WIDTH, maxWidth),
    minHeight: Math.min(PIXEL_WIDGET_MIN_HEIGHT, maxHeight),
    maxWidth,
    maxHeight,
  }
}

function clampPixelWidgetFrame() {
  const limits = getPixelWidgetLimits()
  pixelWidgetFrame.width = clamp(pixelWidgetFrame.width, limits.minWidth, limits.maxWidth)
  pixelWidgetFrame.height = clamp(pixelWidgetFrame.height, limits.minHeight, limits.maxHeight)
  pixelWidgetFrame.x = clamp(
    pixelWidgetFrame.x,
    PIXEL_WIDGET_GUTTER,
    Math.max(PIXEL_WIDGET_GUTTER, limits.containerWidth - pixelWidgetFrame.width - PIXEL_WIDGET_GUTTER)
  )
  pixelWidgetFrame.y = clamp(
    pixelWidgetFrame.y,
    PIXEL_WIDGET_GUTTER,
    Math.max(PIXEL_WIDGET_GUTTER, limits.containerHeight - pixelWidgetFrame.height - PIXEL_WIDGET_GUTTER)
  )
}

function ensurePixelWidgetFrame() {
  const limits = getPixelWidgetLimits()
  if (!pixelWidgetFrame.initialized) {
    pixelWidgetFrame.width = clamp(PIXEL_WIDGET_DEFAULT_WIDTH, limits.minWidth, limits.maxWidth)
    pixelWidgetFrame.height = clamp(PIXEL_WIDGET_DEFAULT_HEIGHT, limits.minHeight, limits.maxHeight)
    pixelWidgetFrame.x = Math.max(PIXEL_WIDGET_GUTTER, limits.containerWidth - pixelWidgetFrame.width - 18)
    pixelWidgetFrame.y = clamp(84, PIXEL_WIDGET_GUTTER, Math.max(PIXEL_WIDGET_GUTTER, limits.containerHeight - pixelWidgetFrame.height - PIXEL_WIDGET_GUTTER))
    pixelWidgetFrame.initialized = true
  }
  clampPixelWidgetFrame()
}

const pixelWidgetStyle = computed(() => {
  if (pixelWidgetMaximized.value) {
    return {
      left: `${PIXEL_WIDGET_GUTTER}px`,
      top: `${PIXEL_WIDGET_GUTTER}px`,
      width: `calc(100% - ${PIXEL_WIDGET_GUTTER * 2}px)`,
      height: `calc(100% - ${PIXEL_WIDGET_GUTTER * 2}px)`,
      zIndex: widgetZ.pixel,
    }
  }

  const width = pixelWidgetMinimized.value
    ? Math.min(pixelWidgetFrame.width, 420)
    : pixelWidgetFrame.width

  return {
    left: `${pixelWidgetFrame.x}px`,
    top: `${pixelWidgetFrame.y}px`,
    width: `${width}px`,
    height: `${pixelWidgetMinimized.value ? PIXEL_WIDGET_MINIMIZED_HEIGHT : pixelWidgetFrame.height}px`,
    zIndex: widgetZ.pixel,
  }
})

function schedulePixelChartResize() {
  nextTick(() => {
    requestAnimationFrame(() => {
      clampPixelWidgetFrame()
      window.dispatchEvent(new CustomEvent('resize', {
        detail: { pixelWidgetSynthetic: true },
      }))
    })
  })
}

function togglePixelWidgetMinimized() {
  if (pixelWidgetMaximized.value) pixelWidgetMaximized.value = false
  pixelWidgetMinimized.value = !pixelWidgetMinimized.value
  schedulePixelChartResize()
}

function togglePixelWidgetMaximized() {
  ensurePixelWidgetFrame()
  if (pixelWidgetMinimized.value) pixelWidgetMinimized.value = false
  pixelWidgetMaximized.value = !pixelWidgetMaximized.value
  schedulePixelChartResize()
}

function startPixelWidgetDrag(event) {
  if (event.button !== 0) return
  if (pixelWidgetMaximized.value) return
  if (event.target.closest('button, select, input, textarea, .pixel-resize-handle')) return

  ensurePixelWidgetFrame()
  event.preventDefault()
  pixelWidgetDragging.value = true
  pixelWidgetPointerState = {
    type: 'drag',
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    x: pixelWidgetFrame.x,
    y: pixelWidgetFrame.y,
    width: pixelWidgetFrame.width,
    height: pixelWidgetFrame.height,
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', movePixelWidgetPointer)
  window.addEventListener('pointerup', stopPixelWidgetPointer)
  window.addEventListener('pointercancel', stopPixelWidgetPointer)
}

function startPixelWidgetResize(handle, event) {
  if (event.button !== 0 || pixelWidgetMaximized.value || pixelWidgetMinimized.value) return

  ensurePixelWidgetFrame()
  pixelWidgetResizing.value = true
  pixelWidgetPointerState = {
    type: 'resize',
    handle,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    x: pixelWidgetFrame.x,
    y: pixelWidgetFrame.y,
    width: pixelWidgetFrame.width,
    height: pixelWidgetFrame.height,
  }
  window.addEventListener('pointermove', movePixelWidgetPointer)
  window.addEventListener('pointerup', stopPixelWidgetPointer)
  window.addEventListener('pointercancel', stopPixelWidgetPointer)
}

function movePixelWidgetPointer(event) {
  if (!pixelWidgetPointerState || event.pointerId !== pixelWidgetPointerState.pointerId) return

  const dx = event.clientX - pixelWidgetPointerState.startX
  const dy = event.clientY - pixelWidgetPointerState.startY

  if (pixelWidgetPointerState.type === 'drag') {
    pixelWidgetFrame.x = pixelWidgetPointerState.x + dx
    pixelWidgetFrame.y = pixelWidgetPointerState.y + dy
    clampPixelWidgetFrame()
    return
  }

  const limits = getPixelWidgetLimits()
  const handle = pixelWidgetPointerState.handle
  const right = pixelWidgetPointerState.x + pixelWidgetPointerState.width
  const bottom = pixelWidgetPointerState.y + pixelWidgetPointerState.height
  let nextX = pixelWidgetPointerState.x
  let nextY = pixelWidgetPointerState.y
  let nextWidth = pixelWidgetPointerState.width
  let nextHeight = pixelWidgetPointerState.height

  if (handle.includes('e')) {
    nextWidth = clamp(
      pixelWidgetPointerState.width + dx,
      limits.minWidth,
      limits.containerWidth - pixelWidgetPointerState.x - PIXEL_WIDGET_GUTTER
    )
  }
  if (handle.includes('s')) {
    nextHeight = clamp(
      pixelWidgetPointerState.height + dy,
      limits.minHeight,
      limits.containerHeight - pixelWidgetPointerState.y - PIXEL_WIDGET_GUTTER
    )
  }
  if (handle.includes('w')) {
    nextWidth = clamp(
      pixelWidgetPointerState.width - dx,
      limits.minWidth,
      right - PIXEL_WIDGET_GUTTER
    )
    nextX = right - nextWidth
  }
  if (handle.includes('n')) {
    nextHeight = clamp(
      pixelWidgetPointerState.height - dy,
      limits.minHeight,
      bottom - PIXEL_WIDGET_GUTTER
    )
    nextY = bottom - nextHeight
  }

  pixelWidgetFrame.x = nextX
  pixelWidgetFrame.y = nextY
  pixelWidgetFrame.width = nextWidth
  pixelWidgetFrame.height = nextHeight
  clampPixelWidgetFrame()
  schedulePixelChartResize()
}

function stopPixelWidgetPointer() {
  if (!pixelWidgetPointerState) return

  pixelWidgetDragging.value = false
  pixelWidgetResizing.value = false
  pixelWidgetPointerState = null
  window.removeEventListener('pointermove', movePixelWidgetPointer)
  window.removeEventListener('pointerup', stopPixelWidgetPointer)
  window.removeEventListener('pointercancel', stopPixelWidgetPointer)
  schedulePixelChartResize()
}

// ── Chart Panel drag/resize ────────────────────────────────────────────────
function getChartContainerRect() {
  const container = mapEl.value?.closest('.map-container')
  return container?.getBoundingClientRect() || { width: window.innerWidth, height: window.innerHeight }
}

function clampChartFrame() {
  const rect = getChartContainerRect()
  const maxW = Math.max(CHART_WIDGET_MIN_WIDTH, rect.width - CHART_WIDGET_GUTTER * 2)
  const maxH = Math.max(CHART_WIDGET_MIN_HEIGHT, rect.height - CHART_WIDGET_GUTTER * 2)
  chartFrame.width  = Math.min(Math.max(chartFrame.width,  CHART_WIDGET_MIN_WIDTH),  maxW)
  chartFrame.height = Math.min(Math.max(chartFrame.height, CHART_WIDGET_MIN_HEIGHT), maxH)
  chartFrame.x = Math.min(Math.max(chartFrame.x, CHART_WIDGET_GUTTER), Math.max(CHART_WIDGET_GUTTER, rect.width  - chartFrame.width  - CHART_WIDGET_GUTTER))
  chartFrame.y = Math.min(Math.max(chartFrame.y, CHART_WIDGET_GUTTER), Math.max(CHART_WIDGET_GUTTER, rect.height - chartFrame.height - CHART_WIDGET_GUTTER))
}

function ensureChartFrame() {
  if (!chartFrame.initialized) {
    const rect = getChartContainerRect()
    chartFrame.width  = Math.min(CHART_WIDGET_DEFAULT_WIDTH,  Math.max(CHART_WIDGET_MIN_WIDTH,  rect.width  - CHART_WIDGET_GUTTER * 2))
    chartFrame.height = Math.min(CHART_WIDGET_DEFAULT_HEIGHT, Math.max(CHART_WIDGET_MIN_HEIGHT, rect.height - CHART_WIDGET_GUTTER * 2))
    chartFrame.x = Math.max(CHART_WIDGET_GUTTER, Math.round((rect.width  - chartFrame.width)  / 2))
    chartFrame.y = Math.max(CHART_WIDGET_GUTTER, Math.round((rect.height - chartFrame.height) / 2))
    chartFrame.initialized = true
  }
  clampChartFrame()
}

const chartWidgetStyle = computed(() => {
  if (chartWidgetMaximized.value) {
    return {
      left: `${CHART_WIDGET_GUTTER}px`, top: `${CHART_WIDGET_GUTTER}px`,
      width: `calc(100% - ${CHART_WIDGET_GUTTER * 2}px)`,
      height: `calc(100% - ${CHART_WIDGET_GUTTER * 2}px)`,
      zIndex: widgetZ.chart,
    }
  }
  return {
    left: `${chartFrame.x}px`,
    top:  `${chartFrame.y}px`,
    width:  `${chartFrame.width}px`,
    height: `${chartWidgetMinimized.value ? CHART_WIDGET_HEADER_HEIGHT : chartFrame.height}px`,
    zIndex: widgetZ.chart,
  }
})

function toggleChartMinimized() {
  if (chartWidgetMaximized.value) chartWidgetMaximized.value = false
  chartWidgetMinimized.value = !chartWidgetMinimized.value
  nextTick(() => window.dispatchEvent(new Event('resize')))
}
function toggleChartMaximized() {
  ensureChartFrame()
  if (chartWidgetMinimized.value) chartWidgetMinimized.value = false
  chartWidgetMaximized.value = !chartWidgetMaximized.value
  nextTick(() => window.dispatchEvent(new Event('resize')))
}

function startChartDrag(event) {
  if (event.button !== 0 || chartWidgetMaximized.value) return
  if (event.target.closest('button, .chart-resize-handle')) return
  ensureChartFrame()
  event.preventDefault()
  chartDragging.value = true
  chartPointerState = {
    type: 'drag', pointerId: event.pointerId,
    startX: event.clientX, startY: event.clientY,
    x: chartFrame.x, y: chartFrame.y,
    width: chartFrame.width, height: chartFrame.height,
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', moveChartPointer)
  window.addEventListener('pointerup', stopChartPointer)
  window.addEventListener('pointercancel', stopChartPointer)
}

function startChartResize(handle, event) {
  if (event.button !== 0 || chartWidgetMaximized.value || chartWidgetMinimized.value) return
  ensureChartFrame()
  chartResizing.value = true
  chartPointerState = {
    type: 'resize', handle, pointerId: event.pointerId,
    startX: event.clientX, startY: event.clientY,
    x: chartFrame.x, y: chartFrame.y,
    width: chartFrame.width, height: chartFrame.height,
  }
  window.addEventListener('pointermove', moveChartPointer)
  window.addEventListener('pointerup', stopChartPointer)
  window.addEventListener('pointercancel', stopChartPointer)
}

function moveChartPointer(event) {
  if (!chartPointerState || event.pointerId !== chartPointerState.pointerId) return
  const dx = event.clientX - chartPointerState.startX
  const dy = event.clientY - chartPointerState.startY

  if (chartPointerState.type === 'drag') {
    chartFrame.x = chartPointerState.x + dx
    chartFrame.y = chartPointerState.y + dy
    clampChartFrame()
    return
  }

  const rect = getChartContainerRect()
  const maxW = Math.max(CHART_WIDGET_MIN_WIDTH, rect.width  - CHART_WIDGET_GUTTER * 2)
  const maxH = Math.max(CHART_WIDGET_MIN_HEIGHT, rect.height - CHART_WIDGET_GUTTER * 2)
  const { handle } = chartPointerState
  const right  = chartPointerState.x + chartPointerState.width
  const bottom = chartPointerState.y + chartPointerState.height
  let nx = chartPointerState.x, ny = chartPointerState.y
  let nw = chartPointerState.width, nh = chartPointerState.height

  if (handle.includes('e')) nw = Math.min(Math.max(chartPointerState.width + dx, CHART_WIDGET_MIN_WIDTH), rect.width - chartPointerState.x - CHART_WIDGET_GUTTER)
  if (handle.includes('s')) nh = Math.min(Math.max(chartPointerState.height + dy, CHART_WIDGET_MIN_HEIGHT), rect.height - chartPointerState.y - CHART_WIDGET_GUTTER)
  if (handle.includes('w')) { nw = Math.min(Math.max(chartPointerState.width - dx, CHART_WIDGET_MIN_WIDTH), maxW); nx = right - nw }
  if (handle.includes('n')) { nh = Math.min(Math.max(chartPointerState.height - dy, CHART_WIDGET_MIN_HEIGHT), maxH); ny = bottom - nh }

  chartFrame.x = nx; chartFrame.y = ny
  chartFrame.width = nw; chartFrame.height = nh
  clampChartFrame()
  nextTick(() => window.dispatchEvent(new Event('resize')))
}

function stopChartPointer() {
  if (!chartPointerState) return
  chartDragging.value = false
  chartResizing.value = false
  chartPointerState = null
  window.removeEventListener('pointermove', moveChartPointer)
  window.removeEventListener('pointerup', stopChartPointer)
  window.removeEventListener('pointercancel', stopChartPointer)
  nextTick(() => window.dispatchEvent(new Event('resize')))
}

function handlePixelWidgetViewportResize(event) {
  if (event?.detail?.pixelWidgetSynthetic) return
  if (!pixelWidgetFrame.initialized) return
  clampPixelWidgetFrame()
  schedulePixelChartResize()
}

function abortPixelTimeSeriesRequest() {
  if (pixelTimeSeriesController) {
    pixelTimeSeriesController.abort()
    pixelTimeSeriesController = null
  }
}

function boundedCacheSet(cache, key, value, limit) {
  if (cache.has(key)) cache.delete(key)
  cache.set(key, value)
  while (cache.size > limit) {
    const oldestKey = cache.keys().next().value
    cache.delete(oldestKey)
  }
}

function pointCacheKey(lat, lon, slot = props.slot) {
  return `${slot || 'today'}:${Number(lat).toFixed(6)}:${Number(lon).toFixed(6)}`
}

function pixelTimeSeriesQueryKey(lat, lon) {
  return `query:${Number(lat).toFixed(6)}:${Number(lon).toFixed(6)}`
}

function preparePixelWidgetLoading(lat, lon) {
  pixelTimeSeriesRequestId = Date.now() * 1000 + (++pixelTimeSeriesSequence)
  abortPixelTimeSeriesRequest()
  ensurePixelWidgetFrame()
  selectedPixelLocation.value = { lat: Number(lat), lon: Number(lon) }
  pixelWidgetLayer.value = props.selectedLayer || activeLayers.value[0]?.name || null
  pixelWidgetMode.value = 'date'
  showPixelWidget.value = true
  bringWidgetToFront('pixel')
  pixelWidgetMinimized.value = false
  pixelTimeSeriesLoading.value = true
  pixelTimeSeriesError.value = null
  pixelTimeSeries.value = null
}

async function fetchPixelTimeSeries(lat, lon, { pixelId = null } = {}) {
  const requestId = Date.now() * 1000 + (++pixelTimeSeriesSequence)
  pixelTimeSeriesRequestId = requestId
  abortPixelTimeSeriesRequest()
  const queryKey = pixelTimeSeriesQueryKey(lat, lon)
  const pixelKey = pixelId ? `pixel:${pixelId}` : null
  const cached = (pixelKey && pixelTimeSeriesCache.get(pixelKey)) || pixelTimeSeriesCache.get(queryKey)

  const controller = new AbortController()
  pixelTimeSeriesController = controller
  ensurePixelWidgetFrame()
  selectedPixelLocation.value = { lat: Number(lat), lon: Number(lon) }
  showPixelWidget.value = true
  bringWidgetToFront('pixel')
  pixelWidgetMinimized.value = false
  pixelTimeSeriesLoading.value = !cached
  pixelTimeSeriesError.value   = null
  pixelTimeSeries.value        = cached || null

  if (cached) {
    pixelTimeSeriesController = null
    return cached
  }
 
  try {
    pixelWidgetLayer.value = props.selectedLayer || activeLayers.value[0]?.name || null
    pixelWidgetMode.value = 'date'

    const params = new URLSearchParams({
      lat: String(lat),
      lon: String(lon),
      request_group: pixelRequestGroup,
      request_id: String(requestId),
    })
    const res = await fetch(
      `${API_BASE}/api/pixel-timeseries?${params.toString()}`,
      { signal: controller.signal, cache: 'no-store' }
    )
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err?.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    if (requestId === pixelTimeSeriesRequestId) {
      pixelTimeSeries.value = data
      boundedCacheSet(pixelTimeSeriesCache, queryKey, data, PIXEL_TS_CACHE_LIMIT)
      if (data?.pixel_id) {
        boundedCacheSet(pixelTimeSeriesCache, `pixel:${data.pixel_id}`, data, PIXEL_TS_CACHE_LIMIT)
      }
    }
    return data
  } catch (err) {
    if (err.name === 'AbortError') return
    console.error('[pixel-ts] fetch error:', err)
    if (requestId === pixelTimeSeriesRequestId) {
      pixelTimeSeriesError.value = err.message || 'Failed to load pixel timeseries'
    }
  } finally {
    if (requestId === pixelTimeSeriesRequestId) {
      pixelTimeSeriesLoading.value = false
      if (pixelTimeSeriesController === controller) {
        pixelTimeSeriesController = null
      }
    }
  }
  return null
}

function closePixelWidget() {
  pixelTimeSeriesRequestId = Date.now() * 1000 + (++pixelTimeSeriesSequence)
  abortPixelTimeSeriesRequest()
  showPixelWidget.value = false
  pixelWidgetMinimized.value = false
  pixelTimeSeriesLoading.value = false
  pixelTimeSeriesError.value = null
  pixelTimeSeries.value = null
  selectedPixelLocation.value = null
  clearSelectedPixelMarker()
}

function clearSelectedPixelMarker() {
  if (selectedPixelMarker && map) {
    map.removeLayer(selectedPixelMarker)
  }
  selectedPixelMarker = null
}

function updateSelectedPixelMarker(lat, lon) {
  if (!map || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon))) return
  clearSelectedPixelMarker()
  selectedPixelMarker = L.marker([Number(lat), Number(lon)], {
    interactive: false,
    keyboard: false,
    zIndexOffset: 1400,
    icon: L.divIcon({
      className: 'selected-pixel-marker',
      html: '<span class="selected-pixel-ring"></span><span class="selected-pixel-core"></span>',
      iconSize: [34, 34],
      iconAnchor: [17, 17],
    }),
  }).addTo(map)
}
 

const props = defineProps({
  layers: {
    type: Object,
    default: () => ({ savi: false, kc: false, etc: false, cwr: false, iwr: false })
  },
  forecastDays: {
    type: String,
    default: 'today'
  },
  slot: {
    type: String,
    default: 'today'
  },
  opacity: {
    type: Number,
    default: 1.0
  },
  selectedDate: {
    type: String,
    default: null
  },
  availableDates: {
    type: Array,
    default: () => []
  },
  weatherSummary: {
    type: Object,
    default: null
  },
  selectedLayer: {
    type: String,
    default: null
  },
  weatherOpen: {
    type: Boolean,
    default: false
  },
  chartVisible: {
    type: Boolean,
    default: false
  },
  isDark: {
    type: Boolean,
    default: true   // dashboard is dark by default
  }
})

const emit = defineEmits(['location-selected', 'calendar-open', 'open-weather', 'update:chart-visible', 'update:weather-open'])

// Add slot to date map for display
const slotToDateMap = ref({})
const weatherVisible = ref(false)

// Create slotToDateMap from availableDates
watch(() => props.availableDates, (dates) => {
  const map = {}
  dates.forEach(d => {
    if (d.slot && d.date) {
      map[d.slot] = d.date
    }
  })
  slotToDateMap.value = map
}, { immediate: true })

watch(() => props.selectedLayer, (layer) => {
  pixelWidgetLayer.value = layer || activeLayers.value[0]?.name || null

  if (layer && pixelTimeSeries.value) {
    showPixelWidget.value = true
    bringWidgetToFront('pixel')
    pixelWidgetMinimized.value = false
  }
})

watch(() => props.chartVisible, visible => {
  if (visible) {
    ensureChartFrame()
    bringWidgetToFront('chart')
  }
})

watch(() => props.weatherOpen, visible => {
  weatherVisible.value = visible
}, { immediate: true })

watch(weatherVisible, visible => {
  emit('update:weather-open', visible)
  if (visible) emit('open-weather')
  if (visible) bringWidgetToFront('weather')
})

watch(showPixelWidget, visible => {
  if (visible) bringWidgetToFront('pixel')
})

const mapEl = ref(null)
let map
let baseLayer = null
let retiringBaseLayer = null
let basemapTransitionFrame = null
let boundaryLayer = null
let wmsLayers = {}
let gisScaleControl = null
const pointData = ref(null)
const forecastData = ref(null)

const isForecastLoading = ref(false)
const boundaryLoaded = ref(false)
const currentMapStyle = ref('Satellite')
// isDarkMode is now derived from the isDark prop passed by App.vue
const isDarkMode = computed(() => props.isDark)
const isLocating = ref(false)
const locationError = ref(null)
let userLocationMarker = null
let selectedPixelMarker = null

// Unified pixel popup state
const hoverPointData = ref(null)
const hoverCoords = ref(null)
const unifiedPopupPinned = ref(false)
const unifiedPopupLoading = ref(false)
const unifiedPopupPosition = ref({ x: 16, y: 16 })
const highestZIndex = ref(2400)
const widgetZ = reactive({
  chart: 2410,
  weather: 2420,
  popup: 2430,
  pixel: 2440,
})

// Forecast window state: null = observed, '5day' | '10day' | '15day' = forecast
const selectedWindow = ref(null)
// Separate WMS layer ref for kc forecast overlay
let kcForecastLayer = null

function bringWidgetToFront(widget) {
  if (!Object.prototype.hasOwnProperty.call(widgetZ, widget)) return
  highestZIndex.value += 1
  widgetZ[widget] = highestZIndex.value
}

// Map style options
const mapStyles = [
  {
    name: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri',
    thumbnail: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/4/8/8'
  },
  {
    name: 'Street Map',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap',
    thumbnail: 'https://a.tile.openstreetmap.org/4/8/8.png'
  },
  {
    name: 'Terrain',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
    attribution: '© Esri',
    thumbnail: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/4/8/8'
  },
  {
    name: 'Dark Map',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '© CartoDB',
    thumbnail: 'https://b.basemaps.cartocdn.com/dark_all/4/8/8.png'
  },
]

// GeoServer configuration
// const GEOSERVER_URL = '/geoserver'
const GEOSERVER_URL = 'http://localhost:8080/geoserver'
const WORKSPACE = 'irrigation'
const MAP_MIN_ZOOM = 8
const MAP_MAX_ZOOM = 17
const MAP_BOUNDARY_PADDING = 0.12

const layerConfigs = {
  savi: { name: 'savi', displayName: 'SAVI',        style: 'savi_style' },
  kc:   { name: 'kc',   displayName: 'Kc',          style: 'kc_style'  },
  cwr:  { name: 'cwr',  displayName: 'CWR (mm)',     style: 'cwr_style' },
  iwr:  { name: 'iwr',  displayName: 'IWR (mm)',     style: 'iwr_style' },
  etc:  { name: 'etc',  displayName: 'ETc (mm/day)', style: 'etc_style' },
}
const FORECAST_POPUP_LAYERS = new Set(['cwr', 'iwr'])

// Create WMS layer - using the current slot
function createWMSLayer(layerKey) {
  const config = layerConfigs[layerKey]
  const slot = props.slot || 'today'
  const geoLayerName = `${layerKey}_${slot}`

  return L.tileLayer.wms(`${GEOSERVER_URL}/${WORKSPACE}/wms`, {
    layers: `irrigation:${geoLayerName}`,
    styles: config.style,
    format: 'image/png',
    transparent: true,
    version: '1.3.0',
    crs: L.CRS.EPSG3857,
    opacity: props.opacity,
    tiled: true,
    maxZoom: MAP_MAX_ZOOM
  })
}

function refreshWMSLayers() {
  Object.keys(wmsLayers).forEach(key => {
    if (map && map.hasLayer(wmsLayers[key])) {
      map.removeLayer(wmsLayers[key])
    }
    wmsLayers[key] = createWMSLayer(key)
    if (props.layers[key] && map) {
      wmsLayers[key].addTo(map)
    }
  })
  // Refresh kc forecast overlay when slot changes
  refreshKcForecastLayer()
}

// Create the Kc forecast WMS layer for a specific window
function createKcForecastWMSLayer(window) {
  const slot = props.slot || 'today'
  const geoLayerName = `kc_${slot}_${window}`
  return L.tileLayer.wms(`${GEOSERVER_URL}/${WORKSPACE}/wms`, {
    layers: `irrigation:${geoLayerName}`,
    styles: 'kc_style',
    format: 'image/png',
    transparent: true,
    version: '1.3.0',
    crs: L.CRS.EPSG3857,
    opacity: props.opacity,
    tiled: true,
    maxZoom: MAP_MAX_ZOOM
  })
}

// Toggle between observed kc layer and forecast kc layer
function refreshKcForecastLayer() {
  if (!map) return

  // Remove existing forecast overlay
  if (kcForecastLayer && map.hasLayer(kcForecastLayer)) {
    map.removeLayer(kcForecastLayer)
    kcForecastLayer = null
  }

  if (!selectedWindow.value || !props.layers.kc) return

  // Hide the observed kc history layer
  if (wmsLayers.kc && map.hasLayer(wmsLayers.kc)) {
    map.removeLayer(wmsLayers.kc)
  }

  // Show forecast kc layer
  kcForecastLayer = createKcForecastWMSLayer(selectedWindow.value)
  kcForecastLayer.addTo(map)
}

function normalizePointResponse(data) {
  if (!data) return null
  return {
    lat: Number(data.lat),
    lon: Number(data.lon),
    queryLat: Number(data.query_lat ?? data.queryLat ?? data.lat),
    queryLon: Number(data.query_lon ?? data.queryLon ?? data.lon),
    pixelId: data.pixel_id || data.pixelId || null,
    row: data.row ?? null,
    col: data.col ?? null,
    acquisition_date: data.acquisition_date || 'N/A',
    values: data.values || {},
    forecast: data.forecast || {},
    slot: data.slot || props.slot || 'today',
  }
}

function setSelectedPointData(data) {
  const normalized = normalizePointResponse(data)
  if (!normalized) {
    pointData.value = null
    forecastData.value = {}
    return null
  }
  pointData.value = normalized
  forecastData.value = normalized.forecast || {}
  return normalized
}

async function requestPointData(lat, lon, { signal, slot = props.slot } = {}) {
  const key = pointCacheKey(lat, lon, slot)
  const cached = pointDataCache.get(key)
  if (cached) return cached

  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    slot: slot || 'today',
  })
  const pointRes = await fetch(
    `${API_BASE}/api/point?${params.toString()}`,
    { signal, cache: 'no-store' }
  )
  if (!pointRes.ok) {
    const err = await pointRes.json().catch(() => ({}))
    throw new Error(err?.detail || `HTTP ${pointRes.status}`)
  }
  const data = await pointRes.json()
  const normalized = normalizePointResponse(data)
  boundedCacheSet(pointDataCache, key, normalized, POINT_CACHE_LIMIT)
  if (normalized?.pixelId) {
    boundedCacheSet(pointDataCache, `${slot || 'today'}:pixel:${normalized.pixelId}`, normalized, POINT_CACHE_LIMIT)
  }
  return normalized
}

// Fetch selected point data for click/location workflows.
async function fetchPointData(lat, lon) {
  const requestId = ++pointDataRequestId
  if (pointDataController) {
    pointDataController.abort()
  }
  const controller = new AbortController()
  pointDataController = controller

  try {
    const data = await requestPointData(lat, lon, { signal: controller.signal })
    if (requestId === pointDataRequestId) {
      setSelectedPointData(data)
      return data
    }
    return null
  } catch (err) {
    if (err.name === 'AbortError') return null
    console.error("Point fetch error:", err)
    if (requestId === pointDataRequestId) {
      pointData.value = null
      forecastData.value = {}
    }
    return null
  } finally {
    if (pointDataController === controller) {
      pointDataController = null
    }
  }
}

// Watch for slot changes to refresh layers and fetch point data
watch(() => props.slot, async (newSlot) => {
  if (newSlot) {
    refreshWMSLayers()
    // If we have a current point, refresh its data
    if (pointData.value && pointData.value.lat && pointData.value.lon) {
      await fetchPointData(pointData.value.lat, pointData.value.lon)
    }
  }
}, { immediate: true })

// Watch for selectedWindow changes — swap kc between observed and forecast layer
watch(selectedWindow, () => {
  refreshKcForecastLayer()
})

// Watch for layer toggles
watch(() => props.layers, (val) => {
  if (!map) return
  Object.keys(wmsLayers).forEach(key => {
    if (val[key]) {
      // For kc, only show the history layer if no forecast window is selected
      if (key === 'kc' && selectedWindow.value) {
        // kc forecast overlay handles visibility; hide history layer
        if (map.hasLayer(wmsLayers[key])) map.removeLayer(wmsLayers[key])
        refreshKcForecastLayer()
      } else {
        if (!map.hasLayer(wmsLayers[key])) wmsLayers[key].addTo(map)
        // If kc was just enabled and forecast was active, refresh overlay
        if (key === 'kc') refreshKcForecastLayer()
      }
    } else {
      if (map.hasLayer(wmsLayers[key])) map.removeLayer(wmsLayers[key])
      // If kc was disabled, also remove forecast overlay
      if (key === 'kc' && kcForecastLayer && map.hasLayer(kcForecastLayer)) {
        map.removeLayer(kcForecastLayer)
        kcForecastLayer = null
      }
    }
  })

  pixelWidgetLayer.value = props.selectedLayer || activeLayers.value[0]?.name || null
  if (pixelTimeSeries.value && activeLayers.value.length > 0) {
    showPixelWidget.value = true
    pixelWidgetMinimized.value = false
  }
}, { deep: true })

// Watch for opacity changes
watch(() => props.opacity, (val) => {
  const op = Number(val) || 1
  Object.entries(wmsLayers).forEach(([key, layer]) => {
    if (props.layers[key] && layer) {
      layer.setOpacity(op)
    }
  })
})

// ── Color maps — interpolated from GeoServer SLD anchor stops ─────────────
// Used ONLY for the info-panel chip background colour (not for WMS tile rendering).
const colorMaps = {
  // ── SAVI: -1.0 → 1.0, step 0.1 (21 stops) ──────────────────────────────────
  savi: [
  // SAVI -1.0→1.0 step 0.1  (21 stops)
  { value:       -1, color: '#8B0000' },
  { value:     -0.9, color: '#9E0B00' },
  { value:     -0.8, color: '#B21700' },
  { value:     -0.7, color: '#C52200' },
  { value:     -0.6, color: '#D82E00' },
  { value:     -0.5, color: '#EC3900' },
  { value:     -0.4, color: '#FF4500' },
  { value:     -0.3, color: '#FF5D00' },
  { value:     -0.2, color: '#FF7500' },
  { value:     -0.1, color: '#FF8D00' },
  { value:        0, color: '#FFA500' },
  { value:      0.1, color: '#FFD200' },
  { value:      0.2, color: '#FFFF00' },
  { value:      0.3, color: '#D6FF17' },
  { value:      0.4, color: '#ADFF2F' },
  { value:      0.5, color: '#68C529' },
  { value:      0.6, color: '#228B22' },
  { value:      0.7, color: '#117811' },
  { value:      0.8, color: '#006400' },
  { value:      0.9, color: '#004C00' },
  { value:        1, color: '#003300' },
  ],
  // ── Kc: 0.0 → 1.5, step 0.1 (16 stops) ─────────────────────────────────────
  kc: [
  // Kc   0.0→1.5  step 0.1  (16 stops)
  { value:        0, color: '#FFD700' },
  { value:      0.1, color: '#F3C60B' },
  { value:      0.2, color: '#E6B615' },
  { value:      0.3, color: '#DAA520' },
  { value:      0.4, color: '#B5CA58' },
  { value:      0.5, color: '#90EE90' },
  { value:      0.6, color: '#71E371' },
  { value:      0.7, color: '#51D851' },
  { value:      0.8, color: '#32CD32' },
  { value:      0.9, color: '#2AAC2A' },
  { value:        1, color: '#228B22' },
  { value:      1.1, color: '#0B710B' },
  { value:      1.2, color: '#2E5A06' },
  { value:      1.3, color: '#8B4513' },
  { value:      1.4, color: '#733909' },
  { value:      1.5, color: '#5C2E00' },
  ],
  // ── CWR: 0 → 150 mm, step 0.1 (1501 stops) ─────────────────────────────────
  cwr: [
  // CWR  0→150    step 0.1  (1501 stops)
  { value:        0, color: '#00C853' },
  { value:      0.1, color: '#01C853' },
  { value:      0.2, color: '#01C853' },
  { value:      0.3, color: '#02C852' },
  { value:      0.4, color: '#02C852' },
  { value:      0.5, color: '#03C852' },
  { value:      0.6, color: '#04C852' },
  { value:      0.7, color: '#04C851' },
  { value:      0.8, color: '#05C951' },
  { value:      0.9, color: '#05C950' },
  { value:        1, color: '#2bfb46' },
  { value:      1.1, color: '#07C950' },
  { value:      1.2, color: '#07C94F' },
  { value:      1.3, color: '#08CA4F' },
  { value:      1.4, color: '#08CA4E' },
  { value:      1.5, color: '#09CA4E' },
  { value:      1.6, color: '#0ACA4E' },
  { value:      1.7, color: '#0ACA4E' },
  { value:      1.8, color: '#1f20b9' },
  { value:      1.9, color: '#0BCA4D' },
  { value:        2, color: '#0CCA4D' },
  { value:      2.1, color: '#0CCA4D' },
  { value:      2.2, color: '#0DCA4D' },
  { value:      2.3, color: '#0DCA4C' },
  { value:      2.4, color: '#0ECA4C' },
  { value:      2.5, color: '#0ECA4C' },
  { value:      2.6, color: '#0FCA4C' },
  { value:      2.7, color: '#0FCA4C' },
  { value:      2.8, color: '#10CB4B' },
  { value:      2.9, color: '#10CB4B' },
  { value:        3, color: '#11CB4B' },
  { value:      3.1, color: '#12CB4B' },
  { value:      3.2, color: '#12CB4B' },
  { value:      3.3, color: '#13CC4A' },
  { value:      3.4, color: '#13CC4A' },
  { value:      3.5, color: '#14CC4A' },
  { value:      3.6, color: '#15CC4A' },
  { value:      3.7, color: '#15CC49' },
  { value:      3.8, color: '#16CC49' },
  { value:      3.9, color: '#16CC48' },
  { value:        4, color: '#17CC48' },
  { value:      4.1, color: '#18CC48' },
  { value:      4.2, color: '#18CC47' },
  { value:      4.3, color: '#19CD47' },
  { value:      4.4, color: '#19CD46' },
  { value:      4.5, color: '#1ACD46' },
  { value:      4.6, color: '#1BCD46' },
  { value:      4.7, color: '#1BCD46' },
  { value:      4.8, color: '#1CCE45' },
  { value:      4.9, color: '#1CCE45' },
  { value:        5, color: '#1DCE45' },
  { value:      5.1, color: '#1ECE45' },
  { value:      5.2, color: '#1ECE45' },
  { value:      5.3, color: '#1FCE44' },
  { value:      5.4, color: '#1FCE44' },
  { value:      5.5, color: '#20CE44' },
  { value:      5.6, color: '#21CE44' },
  { value:      5.7, color: '#21CE43' },
  { value:      5.8, color: '#22CF43' },
  { value:      5.9, color: '#22CF42' },
  { value:        6, color: '#23CF42' },
  { value:      6.1, color: '#24CF42' },
  { value:      6.2, color: '#24CF41' },
  { value:      6.3, color: '#25D041' },
  { value:      6.4, color: '#25D040' },
  { value:      6.5, color: '#26D040' },
  { value:      6.6, color: '#27D040' },
  { value:      6.7, color: '#27D040' },
  { value:      6.8, color: '#28D03F' },
  { value:      6.9, color: '#28D03F' },
  { value:        7, color: '#29D03F' },
  { value:      7.1, color: '#2AD03F' },
  { value:      7.2, color: '#2AD03F' },
  { value:      7.3, color: '#2BD03E' },
  { value:      7.4, color: '#2BD03E' },
  { value:      7.5, color: '#2CD03E' },
  { value:      7.6, color: '#2CD03E' },
  { value:      7.7, color: '#2DD03E' },
  { value:      7.8, color: '#2DD13D' },
  { value:      7.9, color: '#2ED13D' },
  { value:        8, color: '#2ED13D' },
  { value:      8.1, color: '#2FD13D' },
  { value:      8.2, color: '#2FD13D' },
  { value:      8.3, color: '#30D23C' },
  { value:      8.4, color: '#30D23C' },
  { value:      8.5, color: '#31D23C' },
  { value:      8.6, color: '#32D23C' },
  { value:      8.7, color: '#32D23B' },
  { value:      8.8, color: '#33D23B' },
  { value:      8.9, color: '#33D23A' },
  { value:        9, color: '#34D23A' },
  { value:      9.1, color: '#35D23A' },
  { value:      9.2, color: '#35D239' },
  { value:      9.3, color: '#36D239' },
  { value:      9.4, color: '#36D238' },
  { value:      9.5, color: '#37D238' },
  { value:      9.6, color: '#38D238' },
  { value:      9.7, color: '#38D238' },
  { value:      9.8, color: '#39D337' },
  { value:      9.9, color: '#39D337' },
  { value:       10, color: '#3AD337' },
  { value:     10.1, color: '#3BD337' },
  { value:     10.2, color: '#3BD337' },
  { value:     10.3, color: '#3CD436' },
  { value:     10.4, color: '#3CD436' },
  { value:     10.5, color: '#3DD436' },
  { value:     10.6, color: '#3ED436' },
  { value:     10.7, color: '#3ED435' },
  { value:     10.8, color: '#3FD435' },
  { value:     10.9, color: '#3FD434' },
  { value:       11, color: '#40D434' },
  { value:     11.1, color: '#41D434' },
  { value:     11.2, color: '#41D434' },
  { value:     11.3, color: '#42D433' },
  { value:     11.4, color: '#42D433' },
  { value:     11.5, color: '#43D433' },
  { value:     11.6, color: '#44D433' },
  { value:     11.7, color: '#44D433' },
  { value:     11.8, color: '#45D532' },
  { value:     11.9, color: '#45D532' },
  { value:       12, color: '#46D532' },
  { value:     12.1, color: '#46D532' },
  { value:     12.2, color: '#47D531' },
  { value:     12.3, color: '#47D631' },
  { value:     12.4, color: '#48D630' },
  { value:     12.5, color: '#48D630' },
  { value:     12.6, color: '#49D630' },
  { value:     12.7, color: '#49D630' },
  { value:     12.8, color: '#4AD72F' },
  { value:     12.9, color: '#4AD72F' },
  { value:       13, color: '#4BD72F' },
  { value:     13.1, color: '#4CD72F' },
  { value:     13.2, color: '#4CD72F' },
  { value:     13.3, color: '#4DD82E' },
  { value:     13.4, color: '#4DD82E' },
  { value:     13.5, color: '#4ED82E' },
  { value:     13.6, color: '#4FD82E' },
  { value:     13.7, color: '#4FD82D' },
  { value:     13.8, color: '#50D82D' },
  { value:     13.9, color: '#50D82C' },
  { value:       14, color: '#51D82C' },
  { value:     14.1, color: '#52D82C' },
  { value:     14.2, color: '#52D82C' },
  { value:     14.3, color: '#53D82B' },
  { value:     14.4, color: '#53D82B' },
  { value:     14.5, color: '#54D82B' },
  { value:     14.6, color: '#55D82B' },
  { value:     14.7, color: '#55D82B' },
  { value:     14.8, color: '#56D92A' },
  { value:     14.9, color: '#56D92A' },
  { value:       15, color: '#57D92A' },
  { value:     15.1, color: '#58D92A' },
  { value:     15.2, color: '#58D929' },
  { value:     15.3, color: '#59DA29' },
  { value:     15.4, color: '#59DA28' },
  { value:     15.5, color: '#5ADA28' },
  { value:     15.6, color: '#5BDA28' },
  { value:     15.7, color: '#5BDA28' },
  { value:     15.8, color: '#5CDA27' },
  { value:     15.9, color: '#5CDA27' },
  { value:       16, color: '#5DDA27' },
  { value:     16.1, color: '#5EDA27' },
  { value:     16.2, color: '#5EDA27' },
  { value:     16.3, color: '#5FDA26' },
  { value:     16.4, color: '#5FDA26' },
  { value:     16.5, color: '#60DA26' },
  { value:     16.6, color: '#61DA26' },
  { value:     16.7, color: '#61DA25' },
  { value:     16.8, color: '#62DB25' },
  { value:     16.9, color: '#62DB24' },
  { value:       17, color: '#63DB24' },
  { value:     17.1, color: '#64DB24' },
  { value:     17.2, color: '#64DB23' },
  { value:     17.3, color: '#65DC23' },
  { value:     17.4, color: '#65DC22' },
  { value:     17.5, color: '#66DC22' },
  { value:     17.6, color: '#66DC22' },
  { value:     17.7, color: '#67DC22' },
  { value:     17.8, color: '#67DD21' },
  { value:     17.9, color: '#68DD21' },
  { value:       18, color: '#68DD21' },
  { value:     18.1, color: '#69DD21' },
  { value:     18.2, color: '#69DD21' },
  { value:     18.3, color: '#6ADE20' },
  { value:     18.4, color: '#6ADE20' },
  { value:     18.5, color: '#6BDE20' },
  { value:     18.6, color: '#6CDE20' },
  { value:     18.7, color: '#6CDE20' },
  { value:     18.8, color: '#6DDE1F' },
  { value:     18.9, color: '#6DDE1F' },
  { value:       19, color: '#6EDE1F' },
  { value:     19.1, color: '#6FDE1F' },
  { value:     19.2, color: '#6FDE1F' },
  { value:     19.3, color: '#70DE1E' },
  { value:     19.4, color: '#70DE1E' },
  { value:     19.5, color: '#71DE1E' },
  { value:     19.6, color: '#72DE1E' },
  { value:     19.7, color: '#72DE1D' },
  { value:     19.8, color: '#73DF1D' },
  { value:     19.9, color: '#73DF1C' },
  { value:       20, color: '#74DF1C' },
  { value:     20.1, color: '#75DF1C' },
  { value:     20.2, color: '#75DF1B' },
  { value:     20.3, color: '#76E01B' },
  { value:     20.4, color: '#76E01A' },
  { value:     20.5, color: '#77E01A' },
  { value:     20.6, color: '#78E01A' },
  { value:     20.7, color: '#78E01A' },
  { value:     20.8, color: '#79E019' },
  { value:     20.9, color: '#79E019' },
  { value:       21, color: '#7AE019' },
  { value:     21.1, color: '#7BE019' },
  { value:     21.2, color: '#7BE019' },
  { value:     21.3, color: '#7CE018' },
  { value:     21.4, color: '#7CE018' },
  { value:     21.5, color: '#7DE018' },
  { value:     21.6, color: '#7EE018' },
  { value:     21.7, color: '#7EE017' },
  { value:     21.8, color: '#7FE117' },
  { value:     21.9, color: '#7FE116' },
  { value:       22, color: '#80E116' },
  { value:     22.1, color: '#80E116' },
  { value:     22.2, color: '#81E116' },
  { value:     22.3, color: '#81E215' },
  { value:     22.4, color: '#82E215' },
  { value:     22.5, color: '#82E215' },
  { value:     22.6, color: '#83E215' },
  { value:     22.7, color: '#83E215' },
  { value:     22.8, color: '#84E214' },
  { value:     22.9, color: '#84E214' },
  { value:       23, color: '#85E214' },
  { value:     23.1, color: '#86E214' },
  { value:     23.2, color: '#86E213' },
  { value:     23.3, color: '#87E213' },
  { value:     23.4, color: '#87E212' },
  { value:     23.5, color: '#88E212' },
  { value:     23.6, color: '#89E212' },
  { value:     23.7, color: '#89E212' },
  { value:     23.8, color: '#8AE311' },
  { value:     23.9, color: '#8AE311' },
  { value:       24, color: '#8BE311' },
  { value:     24.1, color: '#8CE311' },
  { value:     24.2, color: '#8CE311' },
  { value:     24.3, color: '#8DE410' },
  { value:     24.4, color: '#8DE410' },
  { value:     24.5, color: '#8EE410' },
  { value:     24.6, color: '#8FE410' },
  { value:     24.7, color: '#8FE40F' },
  { value:     24.8, color: '#90E40F' },
  { value:     24.9, color: '#90E40E' },
  { value:       25, color: '#91E40E' },
  { value:     25.1, color: '#92E40E' },
  { value:     25.2, color: '#92E40D' },
  { value:     25.3, color: '#93E50D' },
  { value:     25.4, color: '#93E50C' },
  { value:     25.5, color: '#94E50C' },
  { value:     25.6, color: '#95E50C' },
  { value:     25.7, color: '#95E50C' },
  { value:     25.8, color: '#96E60B' },
  { value:     25.9, color: '#96E60B' },
  { value:       26, color: '#97E60B' },
  { value:     26.1, color: '#98E60B' },
  { value:     26.2, color: '#98E60B' },
  { value:     26.3, color: '#99E60A' },
  { value:     26.4, color: '#99E60A' },
  { value:     26.5, color: '#9AE60A' },
  { value:     26.6, color: '#9BE60A' },
  { value:     26.7, color: '#9BE609' },
  { value:     26.8, color: '#9CE709' },
  { value:     26.9, color: '#9CE708' },
  { value:       27, color: '#9DE708' },
  { value:     27.1, color: '#9EE708' },
  { value:     27.2, color: '#9EE708' },
  { value:     27.3, color: '#9FE807' },
  { value:     27.4, color: '#9FE807' },
  { value:     27.5, color: '#A0E807' },
  { value:     27.6, color: '#A0E807' },
  { value:     27.7, color: '#A1E807' },
  { value:     27.8, color: '#A1E806' },
  { value:     27.9, color: '#A2E806' },
  { value:       28, color: '#A2E806' },
  { value:     28.1, color: '#A3E806' },
  { value:     28.2, color: '#A3E805' },
  { value:     28.3, color: '#A4E805' },
  { value:     28.4, color: '#A4E804' },
  { value:     28.5, color: '#A5E804' },
  { value:     28.6, color: '#A6E804' },
  { value:     28.7, color: '#A6E804' },
  { value:     28.8, color: '#A7E903' },
  { value:     28.9, color: '#A7E903' },
  { value:       29, color: '#A8E903' },
  { value:     29.1, color: '#A9E903' },
  { value:     29.2, color: '#A9E903' },
  { value:     29.3, color: '#AAEA02' },
  { value:     29.4, color: '#AAEA02' },
  { value:     29.5, color: '#ABEA02' },
  { value:     29.6, color: '#ACEA02' },
  { value:     29.7, color: '#ACEA01' },
  { value:     29.8, color: '#ADEA01' },
  { value:     29.9, color: '#ADEA00' },
  { value:       30, color: '#AEEA00' },
  { value:     30.1, color: '#AEEA00' },
  { value:     30.2, color: '#AFEA00' },
  { value:     30.3, color: '#AFEA00' },
  { value:     30.4, color: '#B0EA00' },
  { value:     30.5, color: '#B0EA00' },
  { value:     30.6, color: '#B0EA00' },
  { value:     30.7, color: '#B0EA00' },
  { value:     30.8, color: '#B1E900' },
  { value:     30.9, color: '#B1E900' },
  { value:       31, color: '#B1E900' },
  { value:     31.1, color: '#B1E900' },
  { value:     31.2, color: '#B1E900' },
  { value:     31.3, color: '#B2E900' },
  { value:     31.4, color: '#B2E900' },
  { value:     31.5, color: '#B2E900' },
  { value:     31.6, color: '#B2E900' },
  { value:     31.7, color: '#B2E900' },
  { value:     31.8, color: '#B3E900' },
  { value:     31.9, color: '#B3E900' },
  { value:       32, color: '#B3E900' },
  { value:     32.1, color: '#B3E900' },
  { value:     32.2, color: '#B3E900' },
  { value:     32.3, color: '#B4E800' },
  { value:     32.4, color: '#B4E800' },
  { value:     32.5, color: '#B4E800' },
  { value:     32.6, color: '#B4E800' },
  { value:     32.7, color: '#B5E800' },
  { value:     32.8, color: '#B5E800' },
  { value:     32.9, color: '#B6E800' },
  { value:       33, color: '#B6E800' },
  { value:     33.1, color: '#B6E800' },
  { value:     33.2, color: '#B7E800' },
  { value:     33.3, color: '#B7E800' },
  { value:     33.4, color: '#B8E800' },
  { value:     33.5, color: '#B8E800' },
  { value:     33.6, color: '#B8E800' },
  { value:     33.7, color: '#B8E800' },
  { value:     33.8, color: '#B9E700' },
  { value:     33.9, color: '#B9E700' },
  { value:       34, color: '#B9E700' },
  { value:     34.1, color: '#B9E700' },
  { value:     34.2, color: '#B9E700' },
  { value:     34.3, color: '#BAE600' },
  { value:     34.4, color: '#BAE600' },
  { value:     34.5, color: '#BAE600' },
  { value:     34.6, color: '#BAE600' },
  { value:     34.7, color: '#BBE600' },
  { value:     34.8, color: '#BBE600' },
  { value:     34.9, color: '#BCE600' },
  { value:       35, color: '#BCE600' },
  { value:     35.1, color: '#BCE600' },
  { value:     35.2, color: '#BCE600' },
  { value:     35.3, color: '#BDE600' },
  { value:     35.4, color: '#BDE600' },
  { value:     35.5, color: '#BDE600' },
  { value:     35.6, color: '#BDE600' },
  { value:     35.7, color: '#BDE600' },
  { value:     35.8, color: '#BEE600' },
  { value:     35.9, color: '#BEE600' },
  { value:       36, color: '#BEE600' },
  { value:     36.1, color: '#BEE600' },
  { value:     36.2, color: '#BFE600' },
  { value:     36.3, color: '#BFE600' },
  { value:     36.4, color: '#C0E600' },
  { value:     36.5, color: '#C0E600' },
  { value:     36.6, color: '#C0E600' },
  { value:     36.7, color: '#C0E600' },
  { value:     36.8, color: '#C1E500' },
  { value:     36.9, color: '#C1E500' },
  { value:       37, color: '#C1E500' },
  { value:     37.1, color: '#C1E500' },
  { value:     37.2, color: '#C1E500' },
  { value:     37.3, color: '#C2E400' },
  { value:     37.4, color: '#C2E400' },
  { value:     37.5, color: '#C2E400' },
  { value:     37.6, color: '#C2E400' },
  { value:     37.7, color: '#C3E400' },
  { value:     37.8, color: '#C3E400' },
  { value:     37.9, color: '#C4E400' },
  { value:       38, color: '#C4E400' },
  { value:     38.1, color: '#C4E400' },
  { value:     38.2, color: '#C4E400' },
  { value:     38.3, color: '#C5E400' },
  { value:     38.4, color: '#C5E400' },
  { value:     38.5, color: '#C5E400' },
  { value:     38.6, color: '#C5E400' },
  { value:     38.7, color: '#C5E400' },
  { value:     38.8, color: '#C6E400' },
  { value:     38.9, color: '#C6E400' },
  { value:       39, color: '#C6E400' },
  { value:     39.1, color: '#C6E400' },
  { value:     39.2, color: '#C7E400' },
  { value:     39.3, color: '#C7E400' },
  { value:     39.4, color: '#C8E400' },
  { value:     39.5, color: '#C8E400' },
  { value:     39.6, color: '#C8E400' },
  { value:     39.7, color: '#C8E400' },
  { value:     39.8, color: '#C9E300' },
  { value:     39.9, color: '#C9E300' },
  { value:       40, color: '#C9E300' },
  { value:     40.1, color: '#C9E300' },
  { value:     40.2, color: '#C9E300' },
  { value:     40.3, color: '#CAE200' },
  { value:     40.4, color: '#CAE200' },
  { value:     40.5, color: '#CAE200' },
  { value:     40.6, color: '#CAE200' },
  { value:     40.7, color: '#CBE200' },
  { value:     40.8, color: '#CBE200' },
  { value:     40.9, color: '#CCE200' },
  { value:       41, color: '#CCE200' },
  { value:     41.1, color: '#CCE200' },
  { value:     41.2, color: '#CCE200' },
  { value:     41.3, color: '#CDE200' },
  { value:     41.4, color: '#CDE200' },
  { value:     41.5, color: '#CDE200' },
  { value:     41.6, color: '#CDE200' },
  { value:     41.7, color: '#CDE200' },
  { value:     41.8, color: '#CEE200' },
  { value:     41.9, color: '#CEE200' },
  { value:       42, color: '#CEE200' },
  { value:     42.1, color: '#CEE200' },
  { value:     42.2, color: '#CFE200' },
  { value:     42.3, color: '#CFE200' },
  { value:     42.4, color: '#D0E200' },
  { value:     42.5, color: '#D0E200' },
  { value:     42.6, color: '#D0E200' },
  { value:     42.7, color: '#D0E200' },
  { value:     42.8, color: '#D1E100' },
  { value:     42.9, color: '#D1E100' },
  { value:       43, color: '#D1E100' },
  { value:     43.1, color: '#D1E100' },
  { value:     43.2, color: '#D1E100' },
  { value:     43.3, color: '#D2E100' },
  { value:     43.4, color: '#D2E100' },
  { value:     43.5, color: '#D2E100' },
  { value:     43.6, color: '#D2E100' },
  { value:     43.7, color: '#D3E100' },
  { value:     43.8, color: '#D3E100' },
  { value:     43.9, color: '#D4E100' },
  { value:       44, color: '#D4E100' },
  { value:     44.1, color: '#D4E100' },
  { value:     44.2, color: '#D4E100' },
  { value:     44.3, color: '#D5E000' },
  { value:     44.4, color: '#D5E000' },
  { value:     44.5, color: '#D5E000' },
  { value:     44.6, color: '#D5E000' },
  { value:     44.7, color: '#D5E000' },
  { value:     44.8, color: '#D6E000' },
  { value:     44.9, color: '#D6E000' },
  { value:       45, color: '#D6E000' },
  { value:     45.1, color: '#D6E000' },
  { value:     45.2, color: '#D7E000' },
  { value:     45.3, color: '#D7E000' },
  { value:     45.4, color: '#D8E000' },
  { value:     45.5, color: '#D8E000' },
  { value:     45.6, color: '#D8E000' },
  { value:     45.7, color: '#D8E000' },
  { value:     45.8, color: '#D9DF00' },
  { value:     45.9, color: '#D9DF00' },
  { value:       46, color: '#D9DF00' },
  { value:     46.1, color: '#D9DF00' },
  { value:     46.2, color: '#D9DF00' },
  { value:     46.3, color: '#DADF00' },
  { value:     46.4, color: '#DADF00' },
  { value:     46.5, color: '#DADF00' },
  { value:     46.6, color: '#DADF00' },
  { value:     46.7, color: '#DBDF00' },
  { value:     46.8, color: '#DBDF00' },
  { value:     46.9, color: '#DCDF00' },
  { value:       47, color: '#DCDF00' },
  { value:     47.1, color: '#DCDF00' },
  { value:     47.2, color: '#DDDF00' },
  { value:     47.3, color: '#DDDE00' },
  { value:     47.4, color: '#DEDE00' },
  { value:     47.5, color: '#DEDE00' },
  { value:     47.6, color: '#DEDE00' },
  { value:     47.7, color: '#DEDE00' },
  { value:     47.8, color: '#DFDE00' },
  { value:     47.9, color: '#DFDE00' },
  { value:       48, color: '#DFDE00' },
  { value:     48.1, color: '#DFDE00' },
  { value:     48.2, color: '#DFDE00' },
  { value:     48.3, color: '#E0DE00' },
  { value:     48.4, color: '#E0DE00' },
  { value:     48.5, color: '#E0DE00' },
  { value:     48.6, color: '#E0DE00' },
  { value:     48.7, color: '#E0DE00' },
  { value:     48.8, color: '#E1DE00' },
  { value:     48.9, color: '#E1DE00' },
  { value:       49, color: '#E1DE00' },
  { value:     49.1, color: '#E1DE00' },
  { value:     49.2, color: '#E1DE00' },
  { value:     49.3, color: '#E2DE00' },
  { value:     49.4, color: '#E2DE00' },
  { value:     49.5, color: '#E2DE00' },
  { value:     49.6, color: '#E2DE00' },
  { value:     49.7, color: '#E3DE00' },
  { value:     49.8, color: '#E3DD00' },
  { value:     49.9, color: '#E4DD00' },
  { value:       50, color: '#E4DD00' },
  { value:     50.1, color: '#E4DD00' },
  { value:     50.2, color: '#E5DD00' },
  { value:     50.3, color: '#E5DC00' },
  { value:     50.4, color: '#E6DC00' },
  { value:     50.5, color: '#E6DC00' },
  { value:     50.6, color: '#E6DC00' },
  { value:     50.7, color: '#E6DC00' },
  { value:     50.8, color: '#E7DC00' },
  { value:     50.9, color: '#E7DC00' },
  { value:       51, color: '#E7DC00' },
  { value:     51.1, color: '#E7DC00' },
  { value:     51.2, color: '#E7DC00' },
  { value:     51.3, color: '#E8DC00' },
  { value:     51.4, color: '#E8DC00' },
  { value:     51.5, color: '#E8DC00' },
  { value:     51.6, color: '#E8DC00' },
  { value:     51.7, color: '#E8DC00' },
  { value:     51.8, color: '#E9DC00' },
  { value:     51.9, color: '#E9DC00' },
  { value:       52, color: '#E9DC00' },
  { value:     52.1, color: '#E9DC00' },
  { value:     52.2, color: '#E9DC00' },
  { value:     52.3, color: '#EADC00' },
  { value:     52.4, color: '#EADC00' },
  { value:     52.5, color: '#EADC00' },
  { value:     52.6, color: '#EADC00' },
  { value:     52.7, color: '#EBDC00' },
  { value:     52.8, color: '#EBDB00' },
  { value:     52.9, color: '#ECDB00' },
  { value:       53, color: '#ECDB00' },
  { value:     53.1, color: '#ECDB00' },
  { value:     53.2, color: '#EDDB00' },
  { value:     53.3, color: '#EDDA00' },
  { value:     53.4, color: '#EEDA00' },
  { value:     53.5, color: '#EEDA00' },
  { value:     53.6, color: '#EEDA00' },
  { value:     53.7, color: '#EEDA00' },
  { value:     53.8, color: '#EFDA00' },
  { value:     53.9, color: '#EFDA00' },
  { value:       54, color: '#EFDA00' },
  { value:     54.1, color: '#EFDA00' },
  { value:     54.2, color: '#EFDA00' },
  { value:     54.3, color: '#F0DA00' },
  { value:     54.4, color: '#F0DA00' },
  { value:     54.5, color: '#F0DA00' },
  { value:     54.6, color: '#F0DA00' },
  { value:     54.7, color: '#F1DA00' },
  { value:     54.8, color: '#F1DA00' },
  { value:     54.9, color: '#F2DA00' },
  { value:       55, color: '#F2DA00' },
  { value:     55.1, color: '#F2DA00' },
  { value:     55.2, color: '#F2DA00' },
  { value:     55.3, color: '#F3DA00' },
  { value:     55.4, color: '#F3DA00' },
  { value:     55.5, color: '#F3DA00' },
  { value:     55.6, color: '#F3DA00' },
  { value:     55.7, color: '#F3DA00' },
  { value:     55.8, color: '#F4D900' },
  { value:     55.9, color: '#F4D900' },
  { value:       56, color: '#F4D900' },
  { value:     56.1, color: '#F4D900' },
  { value:     56.2, color: '#F5D900' },
  { value:     56.3, color: '#F5D800' },
  { value:     56.4, color: '#F6D800' },
  { value:     56.5, color: '#F6D800' },
  { value:     56.6, color: '#F6D800' },
  { value:     56.7, color: '#F6D800' },
  { value:     56.8, color: '#F7D800' },
  { value:     56.9, color: '#F7D800' },
  { value:       57, color: '#F7D800' },
  { value:     57.1, color: '#F7D800' },
  { value:     57.2, color: '#F7D800' },
  { value:     57.3, color: '#F8D800' },
  { value:     57.4, color: '#F8D800' },
  { value:     57.5, color: '#F8D800' },
  { value:     57.6, color: '#F8D800' },
  { value:     57.7, color: '#F9D800' },
  { value:     57.8, color: '#F9D700' },
  { value:     57.9, color: '#FAD700' },
  { value:       58, color: '#FAD700' },
  { value:     58.1, color: '#FAD700' },
  { value:     58.2, color: '#FAD700' },
  { value:     58.3, color: '#FBD700' },
  { value:     58.4, color: '#FBD700' },
  { value:     58.5, color: '#FBD700' },
  { value:     58.6, color: '#FBD700' },
  { value:     58.7, color: '#FBD700' },
  { value:     58.8, color: '#FCD700' },
  { value:     58.9, color: '#FCD700' },
  { value:       59, color: '#FCD700' },
  { value:     59.1, color: '#FCD700' },
  { value:     59.2, color: '#FDD700' },
  { value:     59.3, color: '#FDD600' },
  { value:     59.4, color: '#FED600' },
  { value:     59.5, color: '#FED600' },
  { value:     59.6, color: '#FED600' },
  { value:     59.7, color: '#FED600' },
  { value:     59.8, color: '#FFD600' },
  { value:     59.9, color: '#FFD600' },
  { value:       60, color: '#FFD600' },
  { value:     60.1, color: '#FFD600' },
  { value:     60.2, color: '#FFD500' },
  { value:     60.3, color: '#FFD500' },
  { value:     60.4, color: '#FFD400' },
  { value:     60.5, color: '#FFD400' },
  { value:     60.6, color: '#FFD400' },
  { value:     60.7, color: '#FFD300' },
  { value:     60.8, color: '#FFD300' },
  { value:     60.9, color: '#FFD200' },
  { value:       61, color: '#FFD200' },
  { value:     61.1, color: '#FFD200' },
  { value:     61.2, color: '#FFD100' },
  { value:     61.3, color: '#FFD100' },
  { value:     61.4, color: '#FFD000' },
  { value:     61.5, color: '#FFD000' },
  { value:     61.6, color: '#FFD000' },
  { value:     61.7, color: '#FFD000' },
  { value:     61.8, color: '#FFCF00' },
  { value:     61.9, color: '#FFCF00' },
  { value:       62, color: '#FFCF00' },
  { value:     62.1, color: '#FFCF00' },
  { value:     62.2, color: '#FFCF00' },
  { value:     62.3, color: '#FFCE00' },
  { value:     62.4, color: '#FFCE00' },
  { value:     62.5, color: '#FFCE00' },
  { value:     62.6, color: '#FFCE00' },
  { value:     62.7, color: '#FFCD00' },
  { value:     62.8, color: '#FFCD00' },
  { value:     62.9, color: '#FFCC00' },
  { value:       63, color: '#FFCC00' },
  { value:     63.1, color: '#FFCC00' },
  { value:     63.2, color: '#FFCB00' },
  { value:     63.3, color: '#FFCB00' },
  { value:     63.4, color: '#FFCA00' },
  { value:     63.5, color: '#FFCA00' },
  { value:     63.6, color: '#FFCA00' },
  { value:     63.7, color: '#FFC900' },
  { value:     63.8, color: '#FFC900' },
  { value:     63.9, color: '#FFC800' },
  { value:       64, color: '#FFC800' },
  { value:     64.1, color: '#FFC800' },
  { value:     64.2, color: '#FFC700' },
  { value:     64.3, color: '#FFC700' },
  { value:     64.4, color: '#FFC600' },
  { value:     64.5, color: '#FFC600' },
  { value:     64.6, color: '#FFC600' },
  { value:     64.7, color: '#FFC500' },
  { value:     64.8, color: '#FFC500' },
  { value:     64.9, color: '#FFC400' },
  { value:       65, color: '#FFC400' },
  { value:     65.1, color: '#FFC400' },
  { value:     65.2, color: '#FFC300' },
  { value:     65.3, color: '#FFC300' },
  { value:     65.4, color: '#FFC200' },
  { value:     65.5, color: '#FFC200' },
  { value:     65.6, color: '#FFC200' },
  { value:     65.7, color: '#FFC200' },
  { value:     65.8, color: '#FFC100' },
  { value:     65.9, color: '#FFC100' },
  { value:       66, color: '#FFC100' },
  { value:     66.1, color: '#FFC100' },
  { value:     66.2, color: '#FFC100' },
  { value:     66.3, color: '#FFC000' },
  { value:     66.4, color: '#FFC000' },
  { value:     66.5, color: '#FFC000' },
  { value:     66.6, color: '#FFC000' },
  { value:     66.7, color: '#FFBF00' },
  { value:     66.8, color: '#FFBF00' },
  { value:     66.9, color: '#FFBE00' },
  { value:       67, color: '#FFBE00' },
  { value:     67.1, color: '#FFBE00' },
  { value:     67.2, color: '#FFBD00' },
  { value:     67.3, color: '#FFBD00' },
  { value:     67.4, color: '#FFBC00' },
  { value:     67.5, color: '#FFBC00' },
  { value:     67.6, color: '#FFBC00' },
  { value:     67.7, color: '#FFBB00' },
  { value:     67.8, color: '#FFBB00' },
  { value:     67.9, color: '#FFBA00' },
  { value:       68, color: '#FFBA00' },
  { value:     68.1, color: '#FFBA00' },
  { value:     68.2, color: '#FFB900' },
  { value:     68.3, color: '#FFB900' },
  { value:     68.4, color: '#FFB800' },
  { value:     68.5, color: '#FFB800' },
  { value:     68.6, color: '#FFB800' },
  { value:     68.7, color: '#FFB700' },
  { value:     68.8, color: '#FFB700' },
  { value:     68.9, color: '#FFB600' },
  { value:       69, color: '#FFB600' },
  { value:     69.1, color: '#FFB600' },
  { value:     69.2, color: '#FFB500' },
  { value:     69.3, color: '#FFB500' },
  { value:     69.4, color: '#FFB400' },
  { value:     69.5, color: '#FFB400' },
  { value:     69.6, color: '#FFB400' },
  { value:     69.7, color: '#FFB400' },
  { value:     69.8, color: '#FFB300' },
  { value:     69.9, color: '#FFB300' },
  { value:       70, color: '#FFB300' },
  { value:     70.1, color: '#FFB300' },
  { value:     70.2, color: '#FFB300' },
  { value:     70.3, color: '#FFB200' },
  { value:     70.4, color: '#FFB200' },
  { value:     70.5, color: '#FFB200' },
  { value:     70.6, color: '#FFB200' },
  { value:     70.7, color: '#FFB100' },
  { value:     70.8, color: '#FFB100' },
  { value:     70.9, color: '#FFB000' },
  { value:       71, color: '#FFB000' },
  { value:     71.1, color: '#FFB000' },
  { value:     71.2, color: '#FFAF00' },
  { value:     71.3, color: '#FFAF00' },
  { value:     71.4, color: '#FFAE00' },
  { value:     71.5, color: '#FFAE00' },
  { value:     71.6, color: '#FFAE00' },
  { value:     71.7, color: '#FFAD00' },
  { value:     71.8, color: '#FFAD00' },
  { value:     71.9, color: '#FFAC00' },
  { value:       72, color: '#FFAC00' },
  { value:     72.1, color: '#FFAC00' },
  { value:     72.2, color: '#FFAB00' },
  { value:     72.3, color: '#FFAB00' },
  { value:     72.4, color: '#FFAA00' },
  { value:     72.5, color: '#FFAA00' },
  { value:     72.6, color: '#FFAA00' },
  { value:     72.7, color: '#FFA900' },
  { value:     72.8, color: '#FFA900' },
  { value:     72.9, color: '#FFA800' },
  { value:       73, color: '#FFA800' },
  { value:     73.1, color: '#FFA800' },
  { value:     73.2, color: '#FFA700' },
  { value:     73.3, color: '#FFA700' },
  { value:     73.4, color: '#FFA600' },
  { value:     73.5, color: '#FFA600' },
  { value:     73.6, color: '#FFA600' },
  { value:     73.7, color: '#FFA600' },
  { value:     73.8, color: '#FFA500' },
  { value:     73.9, color: '#FFA500' },
  { value:       74, color: '#FFA500' },
  { value:     74.1, color: '#FFA500' },
  { value:     74.2, color: '#FFA500' },
  { value:     74.3, color: '#FFA400' },
  { value:     74.4, color: '#FFA400' },
  { value:     74.5, color: '#FFA400' },
  { value:     74.6, color: '#FFA400' },
  { value:     74.7, color: '#FFA300' },
  { value:     74.8, color: '#FFA300' },
  { value:     74.9, color: '#FFA200' },
  { value:       75, color: '#FFA200' },
  { value:     75.1, color: '#FFA200' },
  { value:     75.2, color: '#FFA100' },
  { value:     75.3, color: '#FFA100' },
  { value:     75.4, color: '#FFA000' },
  { value:     75.5, color: '#FFA000' },
  { value:     75.6, color: '#FFA000' },
  { value:     75.7, color: '#FF9F00' },
  { value:     75.8, color: '#FF9F00' },
  { value:     75.9, color: '#FF9E00' },
  { value:       76, color: '#FF9E00' },
  { value:     76.1, color: '#FF9E00' },
  { value:     76.2, color: '#FF9D00' },
  { value:     76.3, color: '#FF9D00' },
  { value:     76.4, color: '#FF9C00' },
  { value:     76.5, color: '#FF9C00' },
  { value:     76.6, color: '#FF9C00' },
  { value:     76.7, color: '#FF9B00' },
  { value:     76.8, color: '#FF9B00' },
  { value:     76.9, color: '#FF9A00' },
  { value:       77, color: '#FF9A00' },
  { value:     77.1, color: '#FF9A00' },
  { value:     77.2, color: '#FF9900' },
  { value:     77.3, color: '#FF9900' },
  { value:     77.4, color: '#FF9800' },
  { value:     77.5, color: '#FF9800' },
  { value:     77.6, color: '#FF9800' },
  { value:     77.7, color: '#FF9800' },
  { value:     77.8, color: '#FF9700' },
  { value:     77.9, color: '#FF9700' },
  { value:       78, color: '#FF9700' },
  { value:     78.1, color: '#FF9700' },
  { value:     78.2, color: '#FF9700' },
  { value:     78.3, color: '#FF9600' },
  { value:     78.4, color: '#FF9600' },
  { value:     78.5, color: '#FF9600' },
  { value:     78.6, color: '#FF9600' },
  { value:     78.7, color: '#FF9500' },
  { value:     78.8, color: '#FF9500' },
  { value:     78.9, color: '#FF9400' },
  { value:       79, color: '#FF9400' },
  { value:     79.1, color: '#FF9400' },
  { value:     79.2, color: '#FF9300' },
  { value:     79.3, color: '#FF9300' },
  { value:     79.4, color: '#FF9200' },
  { value:     79.5, color: '#FF9200' },
  { value:     79.6, color: '#FF9200' },
  { value:     79.7, color: '#FF9100' },
  { value:     79.8, color: '#FF9100' },
  { value:     79.9, color: '#FF9000' },
  { value:       80, color: '#FF9000' },
  { value:     80.1, color: '#FF9000' },
  { value:     80.2, color: '#FF8F00' },
  { value:     80.3, color: '#FF8F00' },
  { value:     80.4, color: '#FF8E00' },
  { value:     80.5, color: '#FF8E00' },
  { value:     80.6, color: '#FF8E00' },
  { value:     80.7, color: '#FF8D00' },
  { value:     80.8, color: '#FF8D00' },
  { value:     80.9, color: '#FF8C00' },
  { value:       81, color: '#FF8C00' },
  { value:     81.1, color: '#FF8C00' },
  { value:     81.2, color: '#FF8B00' },
  { value:     81.3, color: '#FF8B00' },
  { value:     81.4, color: '#FF8A00' },
  { value:     81.5, color: '#FF8A00' },
  { value:     81.6, color: '#FF8A00' },
  { value:     81.7, color: '#FF8A00' },
  { value:     81.8, color: '#FF8900' },
  { value:     81.9, color: '#FF8900' },
  { value:       82, color: '#FF8900' },
  { value:     82.1, color: '#FF8900' },
  { value:     82.2, color: '#FF8900' },
  { value:     82.3, color: '#FF8800' },
  { value:     82.4, color: '#FF8800' },
  { value:     82.5, color: '#FF8800' },
  { value:     82.6, color: '#FF8800' },
  { value:     82.7, color: '#FF8700' },
  { value:     82.8, color: '#FF8700' },
  { value:     82.9, color: '#FF8600' },
  { value:       83, color: '#FF8600' },
  { value:     83.1, color: '#FF8600' },
  { value:     83.2, color: '#FF8500' },
  { value:     83.3, color: '#FF8500' },
  { value:     83.4, color: '#FF8400' },
  { value:     83.5, color: '#FF8400' },
  { value:     83.6, color: '#FF8400' },
  { value:     83.7, color: '#FF8300' },
  { value:     83.8, color: '#FF8300' },
  { value:     83.9, color: '#FF8200' },
  { value:       84, color: '#FF8200' },
  { value:     84.1, color: '#FF8200' },
  { value:     84.2, color: '#FF8100' },
  { value:     84.3, color: '#FF8100' },
  { value:     84.4, color: '#FF8000' },
  { value:     84.5, color: '#FF8000' },
  { value:     84.6, color: '#FF8000' },
  { value:     84.7, color: '#FF7F00' },
  { value:     84.8, color: '#FF7F00' },
  { value:     84.9, color: '#FF7E00' },
  { value:       85, color: '#FF7E00' },
  { value:     85.1, color: '#FF7E00' },
  { value:     85.2, color: '#FF7D00' },
  { value:     85.3, color: '#FF7D00' },
  { value:     85.4, color: '#FF7C00' },
  { value:     85.5, color: '#FF7C00' },
  { value:     85.6, color: '#FF7C00' },
  { value:     85.7, color: '#FF7C00' },
  { value:     85.8, color: '#FF7B00' },
  { value:     85.9, color: '#FF7B00' },
  { value:       86, color: '#FF7B00' },
  { value:     86.1, color: '#FF7B00' },
  { value:     86.2, color: '#FF7B00' },
  { value:     86.3, color: '#FF7A00' },
  { value:     86.4, color: '#FF7A00' },
  { value:     86.5, color: '#FF7A00' },
  { value:     86.6, color: '#FF7A00' },
  { value:     86.7, color: '#FF7900' },
  { value:     86.8, color: '#FF7900' },
  { value:     86.9, color: '#FF7800' },
  { value:       87, color: '#FF7800' },
  { value:     87.1, color: '#FF7800' },
  { value:     87.2, color: '#FF7700' },
  { value:     87.3, color: '#FF7700' },
  { value:     87.4, color: '#FF7600' },
  { value:     87.5, color: '#FF7600' },
  { value:     87.6, color: '#FF7600' },
  { value:     87.7, color: '#FF7500' },
  { value:     87.8, color: '#FF7500' },
  { value:     87.9, color: '#FF7400' },
  { value:       88, color: '#FF7400' },
  { value:     88.1, color: '#FF7400' },
  { value:     88.2, color: '#FF7300' },
  { value:     88.3, color: '#FF7300' },
  { value:     88.4, color: '#FF7200' },
  { value:     88.5, color: '#FF7200' },
  { value:     88.6, color: '#FF7200' },
  { value:     88.7, color: '#FF7100' },
  { value:     88.8, color: '#FF7100' },
  { value:     88.9, color: '#FF7000' },
  { value:       89, color: '#FF7000' },
  { value:     89.1, color: '#FF7000' },
  { value:     89.2, color: '#FF6F00' },
  { value:     89.3, color: '#FF6F00' },
  { value:     89.4, color: '#FF6E00' },
  { value:     89.5, color: '#FF6E00' },
  { value:     89.6, color: '#FF6E00' },
  { value:     89.7, color: '#FF6E00' },
  { value:     89.8, color: '#FF6D00' },
  { value:     89.9, color: '#FF6D00' },
  { value:       90, color: '#FF6D00' },
  { value:     90.1, color: '#FF6D00' },
  { value:     90.2, color: '#FF6D00' },
  { value:     90.3, color: '#FE6C00' },
  { value:     90.4, color: '#FE6C00' },
  { value:     90.5, color: '#FE6C00' },
  { value:     90.6, color: '#FE6C00' },
  { value:     90.7, color: '#FE6C00' },
  { value:     90.8, color: '#FE6B00' },
  { value:     90.9, color: '#FE6B00' },
  { value:       91, color: '#FE6B00' },
  { value:     91.1, color: '#FE6B00' },
  { value:     91.2, color: '#FE6B00' },
  { value:     91.3, color: '#FE6A00' },
  { value:     91.4, color: '#FE6A00' },
  { value:     91.5, color: '#FE6A00' },
  { value:     91.6, color: '#FE6A00' },
  { value:     91.7, color: '#FE6A00' },
  { value:     91.8, color: '#FD6900' },
  { value:     91.9, color: '#FD6900' },
  { value:       92, color: '#FD6900' },
  { value:     92.1, color: '#FD6900' },
  { value:     92.2, color: '#FD6900' },
  { value:     92.3, color: '#FC6800' },
  { value:     92.4, color: '#FC6800' },
  { value:     92.5, color: '#FC6800' },
  { value:     92.6, color: '#FC6800' },
  { value:     92.7, color: '#FC6700' },
  { value:     92.8, color: '#FC6700' },
  { value:     92.9, color: '#FC6600' },
  { value:       93, color: '#FC6600' },
  { value:     93.1, color: '#FC6600' },
  { value:     93.2, color: '#FC6600' },
  { value:     93.3, color: '#FC6500' },
  { value:     93.4, color: '#FC6500' },
  { value:     93.5, color: '#FC6500' },
  { value:     93.6, color: '#FC6500' },
  { value:     93.7, color: '#FC6500' },
  { value:     93.8, color: '#FB6400' },
  { value:     93.9, color: '#FB6400' },
  { value:       94, color: '#FB6400' },
  { value:     94.1, color: '#FB6400' },
  { value:     94.2, color: '#FB6400' },
  { value:     94.3, color: '#FA6300' },
  { value:     94.4, color: '#FA6300' },
  { value:     94.5, color: '#FA6300' },
  { value:     94.6, color: '#FA6300' },
  { value:     94.7, color: '#FA6300' },
  { value:     94.8, color: '#FA6200' },
  { value:     94.9, color: '#FA6200' },
  { value:       95, color: '#FA6200' },
  { value:     95.1, color: '#FA6200' },
  { value:     95.2, color: '#FA6200' },
  { value:     95.3, color: '#F96100' },
  { value:     95.4, color: '#F96100' },
  { value:     95.5, color: '#F96100' },
  { value:     95.6, color: '#F96100' },
  { value:     95.7, color: '#F96100' },
  { value:     95.8, color: '#F86000' },
  { value:     95.9, color: '#F86000' },
  { value:       96, color: '#F86000' },
  { value:     96.1, color: '#F86000' },
  { value:     96.2, color: '#F86000' },
  { value:     96.3, color: '#F85F00' },
  { value:     96.4, color: '#F85F00' },
  { value:     96.5, color: '#F85F00' },
  { value:     96.6, color: '#F85F00' },
  { value:     96.7, color: '#F85F00' },
  { value:     96.8, color: '#F75E00' },
  { value:     96.9, color: '#F75E00' },
  { value:       97, color: '#F75E00' },
  { value:     97.1, color: '#F75E00' },
  { value:     97.2, color: '#F75D00' },
  { value:     97.3, color: '#F65D00' },
  { value:     97.4, color: '#F65C00' },
  { value:     97.5, color: '#F65C00' },
  { value:     97.6, color: '#F65C00' },
  { value:     97.7, color: '#F65C00' },
  { value:     97.8, color: '#F65B00' },
  { value:     97.9, color: '#F65B00' },
  { value:       98, color: '#F65B00' },
  { value:     98.1, color: '#F65B00' },
  { value:     98.2, color: '#F65B00' },
  { value:     98.3, color: '#F65A00' },
  { value:     98.4, color: '#F65A00' },
  { value:     98.5, color: '#F65A00' },
  { value:     98.6, color: '#F65A00' },
  { value:     98.7, color: '#F65A00' },
  { value:     98.8, color: '#F55900' },
  { value:     98.9, color: '#F55900' },
  { value:       99, color: '#F55900' },
  { value:     99.1, color: '#F55900' },
  { value:     99.2, color: '#F55900' },
  { value:     99.3, color: '#F45800' },
  { value:     99.4, color: '#F45800' },
  { value:     99.5, color: '#F45800' },
  { value:     99.6, color: '#F45800' },
  { value:     99.7, color: '#F45800' },
  { value:     99.8, color: '#F45700' },
  { value:     99.9, color: '#F45700' },
  { value:      100, color: '#F45700' },
  { value:    100.1, color: '#F45700' },
  { value:    100.2, color: '#F45700' },
  { value:    100.3, color: '#F45600' },
  { value:    100.4, color: '#F45600' },
  { value:    100.5, color: '#F45600' },
  { value:    100.6, color: '#F45600' },
  { value:    100.7, color: '#F45600' },
  { value:    100.8, color: '#F35500' },
  { value:    100.9, color: '#F35500' },
  { value:      101, color: '#F35500' },
  { value:    101.1, color: '#F35500' },
  { value:    101.2, color: '#F35500' },
  { value:    101.3, color: '#F25400' },
  { value:    101.4, color: '#F25400' },
  { value:    101.5, color: '#F25400' },
  { value:    101.6, color: '#F25400' },
  { value:    101.7, color: '#F25400' },
  { value:    101.8, color: '#F25300' },
  { value:    101.9, color: '#F25300' },
  { value:      102, color: '#F25300' },
  { value:    102.1, color: '#F25300' },
  { value:    102.2, color: '#F25300' },
  { value:    102.3, color: '#F15200' },
  { value:    102.4, color: '#F15200' },
  { value:    102.5, color: '#F15200' },
  { value:    102.6, color: '#F15200' },
  { value:    102.7, color: '#F15200' },
  { value:    102.8, color: '#F05100' },
  { value:    102.9, color: '#F05100' },
  { value:      103, color: '#F05100' },
  { value:    103.1, color: '#F05100' },
  { value:    103.2, color: '#F05100' },
  { value:    103.3, color: '#F05000' },
  { value:    103.4, color: '#F05000' },
  { value:    103.5, color: '#F05000' },
  { value:    103.6, color: '#F05000' },
  { value:    103.7, color: '#F05000' },
  { value:    103.8, color: '#EF4F00' },
  { value:    103.9, color: '#EF4F00' },
  { value:      104, color: '#EF4F00' },
  { value:    104.1, color: '#EF4F00' },
  { value:    104.2, color: '#EF4F00' },
  { value:    104.3, color: '#EE4E00' },
  { value:    104.4, color: '#EE4E00' },
  { value:    104.5, color: '#EE4E00' },
  { value:    104.6, color: '#EE4E00' },
  { value:    104.7, color: '#EE4D00' },
  { value:    104.8, color: '#EE4D00' },
  { value:    104.9, color: '#EE4C00' },
  { value:      105, color: '#EE4C00' },
  { value:    105.1, color: '#EE4C00' },
  { value:    105.2, color: '#EE4C00' },
  { value:    105.3, color: '#EE4B00' },
  { value:    105.4, color: '#EE4B00' },
  { value:    105.5, color: '#EE4B00' },
  { value:    105.6, color: '#EE4B00' },
  { value:    105.7, color: '#EE4B00' },
  { value:    105.8, color: '#ED4A00' },
  { value:    105.9, color: '#ED4A00' },
  { value:      106, color: '#ED4A00' },
  { value:    106.1, color: '#ED4A00' },
  { value:    106.2, color: '#ED4A00' },
  { value:    106.3, color: '#EC4900' },
  { value:    106.4, color: '#EC4900' },
  { value:    106.5, color: '#EC4900' },
  { value:    106.6, color: '#EC4900' },
  { value:    106.7, color: '#EC4900' },
  { value:    106.8, color: '#EC4800' },
  { value:    106.9, color: '#EC4800' },
  { value:      107, color: '#EC4800' },
  { value:    107.1, color: '#EC4800' },
  { value:    107.2, color: '#EC4800' },
  { value:    107.3, color: '#EB4700' },
  { value:    107.4, color: '#EB4700' },
  { value:    107.5, color: '#EB4700' },
  { value:    107.6, color: '#EB4700' },
  { value:    107.7, color: '#EB4700' },
  { value:    107.8, color: '#EA4600' },
  { value:    107.9, color: '#EA4600' },
  { value:      108, color: '#EA4600' },
  { value:    108.1, color: '#EA4600' },
  { value:    108.2, color: '#EA4600' },
  { value:    108.3, color: '#EA4500' },
  { value:    108.4, color: '#EA4500' },
  { value:    108.5, color: '#EA4500' },
  { value:    108.6, color: '#EA4500' },
  { value:    108.7, color: '#EA4500' },
  { value:    108.8, color: '#E94400' },
  { value:    108.9, color: '#E94400' },
  { value:      109, color: '#E94400' },
  { value:    109.1, color: '#E94400' },
  { value:    109.2, color: '#E94400' },
  { value:    109.3, color: '#E84300' },
  { value:    109.4, color: '#E84300' },
  { value:    109.5, color: '#E84300' },
  { value:    109.6, color: '#E84300' },
  { value:    109.7, color: '#E84300' },
  { value:    109.8, color: '#E84200' },
  { value:    109.9, color: '#E84200' },
  { value:      110, color: '#E84200' },
  { value:    110.1, color: '#E84200' },
  { value:    110.2, color: '#E84200' },
  { value:    110.3, color: '#E84100' },
  { value:    110.4, color: '#E84100' },
  { value:    110.5, color: '#E84100' },
  { value:    110.6, color: '#E84100' },
  { value:    110.7, color: '#E84100' },
  { value:    110.8, color: '#E74000' },
  { value:    110.9, color: '#E74000' },
  { value:      111, color: '#E74000' },
  { value:    111.1, color: '#E74000' },
  { value:    111.2, color: '#E74000' },
  { value:    111.3, color: '#E63F00' },
  { value:    111.4, color: '#E63F00' },
  { value:    111.5, color: '#E63F00' },
  { value:    111.6, color: '#E63F00' },
  { value:    111.7, color: '#E63F00' },
  { value:    111.8, color: '#E63E00' },
  { value:    111.9, color: '#E63E00' },
  { value:      112, color: '#E63E00' },
  { value:    112.1, color: '#E63E00' },
  { value:    112.2, color: '#E63D00' },
  { value:    112.3, color: '#E63D00' },
  { value:    112.4, color: '#E63C00' },
  { value:    112.5, color: '#E63C00' },
  { value:    112.6, color: '#E63C00' },
  { value:    112.7, color: '#E63C00' },
  { value:    112.8, color: '#E53B00' },
  { value:    112.9, color: '#E53B00' },
  { value:      113, color: '#E53B00' },
  { value:    113.1, color: '#E53B00' },
  { value:    113.2, color: '#E53B00' },
  { value:    113.3, color: '#E43A00' },
  { value:    113.4, color: '#E43A00' },
  { value:    113.5, color: '#E43A00' },
  { value:    113.6, color: '#E43A00' },
  { value:    113.7, color: '#E43A00' },
  { value:    113.8, color: '#E43900' },
  { value:    113.9, color: '#E43900' },
  { value:      114, color: '#E43900' },
  { value:    114.1, color: '#E43900' },
  { value:    114.2, color: '#E43900' },
  { value:    114.3, color: '#E33800' },
  { value:    114.4, color: '#E33800' },
  { value:    114.5, color: '#E33800' },
  { value:    114.6, color: '#E33800' },
  { value:    114.7, color: '#E33800' },
  { value:    114.8, color: '#E23700' },
  { value:    114.9, color: '#E23700' },
  { value:      115, color: '#E23700' },
  { value:    115.1, color: '#E23700' },
  { value:    115.2, color: '#E23700' },
  { value:    115.3, color: '#E23600' },
  { value:    115.4, color: '#E23600' },
  { value:    115.5, color: '#E23600' },
  { value:    115.6, color: '#E23600' },
  { value:    115.7, color: '#E23600' },
  { value:    115.8, color: '#E13500' },
  { value:    115.9, color: '#E13500' },
  { value:      116, color: '#E13500' },
  { value:    116.1, color: '#E13500' },
  { value:    116.2, color: '#E13500' },
  { value:    116.3, color: '#E03400' },
  { value:    116.4, color: '#E03400' },
  { value:    116.5, color: '#E03400' },
  { value:    116.6, color: '#E03400' },
  { value:    116.7, color: '#E03400' },
  { value:    116.8, color: '#E03300' },
  { value:    116.9, color: '#E03300' },
  { value:      117, color: '#E03300' },
  { value:    117.1, color: '#E03300' },
  { value:    117.2, color: '#E03300' },
  { value:    117.3, color: '#E03200' },
  { value:    117.4, color: '#E03200' },
  { value:    117.5, color: '#E03200' },
  { value:    117.6, color: '#E03200' },
  { value:    117.7, color: '#E03100' },
  { value:    117.8, color: '#DF3100' },
  { value:    117.9, color: '#DF3000' },
  { value:      118, color: '#DF3000' },
  { value:    118.1, color: '#DF3000' },
  { value:    118.2, color: '#DF3000' },
  { value:    118.3, color: '#DE2F00' },
  { value:    118.4, color: '#DE2F00' },
  { value:    118.5, color: '#DE2F00' },
  { value:    118.6, color: '#DE2F00' },
  { value:    118.7, color: '#DE2F00' },
  { value:    118.8, color: '#DE2E00' },
  { value:    118.9, color: '#DE2E00' },
  { value:      119, color: '#DE2E00' },
  { value:    119.1, color: '#DE2E00' },
  { value:    119.2, color: '#DE2E00' },
  { value:    119.3, color: '#DE2D00' },
  { value:    119.4, color: '#DE2D00' },
  { value:    119.5, color: '#DE2D00' },
  { value:    119.6, color: '#DE2D00' },
  { value:    119.7, color: '#DE2D00' },
  { value:    119.8, color: '#DD2C00' },
  { value:    119.9, color: '#DD2C00' },
  { value:      120, color: '#DD2C00' },
  { value:    120.1, color: '#DC2C00' },
  { value:    120.2, color: '#DC2C00' },
  { value:    120.3, color: '#DB2B00' },
  { value:    120.4, color: '#DB2B00' },
  { value:    120.5, color: '#DA2B00' },
  { value:    120.6, color: '#DA2B00' },
  { value:    120.7, color: '#D92B00' },
  { value:    120.8, color: '#D92A00' },
  { value:    120.9, color: '#D82A00' },
  { value:      121, color: '#D82A00' },
  { value:    121.1, color: '#D82A00' },
  { value:    121.2, color: '#D72A00' },
  { value:    121.3, color: '#D72A00' },
  { value:    121.4, color: '#D62A00' },
  { value:    121.5, color: '#D62A00' },
  { value:    121.6, color: '#D52A00' },
  { value:    121.7, color: '#D52A00' },
  { value:    121.8, color: '#D42900' },
  { value:    121.9, color: '#D42900' },
  { value:      122, color: '#D32900' },
  { value:    122.1, color: '#D32900' },
  { value:    122.2, color: '#D22900' },
  { value:    122.3, color: '#D22800' },
  { value:    122.4, color: '#D12800' },
  { value:    122.5, color: '#D12800' },
  { value:    122.6, color: '#D12800' },
  { value:    122.7, color: '#D02800' },
  { value:    122.8, color: '#D02800' },
  { value:    122.9, color: '#CF2800' },
  { value:      123, color: '#CF2800' },
  { value:    123.1, color: '#CE2800' },
  { value:    123.2, color: '#CE2800' },
  { value:    123.3, color: '#CD2700' },
  { value:    123.4, color: '#CD2700' },
  { value:    123.5, color: '#CC2700' },
  { value:    123.6, color: '#CC2700' },
  { value:    123.7, color: '#CB2700' },
  { value:    123.8, color: '#CB2600' },
  { value:    123.9, color: '#CA2600' },
  { value:      124, color: '#CA2600' },
  { value:    124.1, color: '#CA2600' },
  { value:    124.2, color: '#C92600' },
  { value:    124.3, color: '#C92500' },
  { value:    124.4, color: '#C82500' },
  { value:    124.5, color: '#C82500' },
  { value:    124.6, color: '#C72500' },
  { value:    124.7, color: '#C72500' },
  { value:    124.8, color: '#C62400' },
  { value:    124.9, color: '#C62400' },
  { value:      125, color: '#C52400' },
  { value:    125.1, color: '#C42400' },
  { value:    125.2, color: '#C42400' },
  { value:    125.3, color: '#C32400' },
  { value:    125.4, color: '#C32400' },
  { value:    125.5, color: '#C22400' },
  { value:    125.6, color: '#C22400' },
  { value:    125.7, color: '#C12400' },
  { value:    125.8, color: '#C12300' },
  { value:    125.9, color: '#C02300' },
  { value:      126, color: '#C02300' },
  { value:    126.1, color: '#C02300' },
  { value:    126.2, color: '#BF2300' },
  { value:    126.3, color: '#BF2200' },
  { value:    126.4, color: '#BE2200' },
  { value:    126.5, color: '#BE2200' },
  { value:    126.6, color: '#BD2200' },
  { value:    126.7, color: '#BD2200' },
  { value:    126.8, color: '#BC2200' },
  { value:    126.9, color: '#BC2200' },
  { value:      127, color: '#BB2200' },
  { value:    127.1, color: '#BB2200' },
  { value:    127.2, color: '#BA2200' },
  { value:    127.3, color: '#BA2100' },
  { value:    127.4, color: '#B92100' },
  { value:    127.5, color: '#B92100' },
  { value:    127.6, color: '#B92100' },
  { value:    127.7, color: '#B82100' },
  { value:    127.8, color: '#B82000' },
  { value:    127.9, color: '#B72000' },
  { value:      128, color: '#B72000' },
  { value:    128.1, color: '#B62000' },
  { value:    128.2, color: '#B62000' },
  { value:    128.3, color: '#B51F00' },
  { value:    128.4, color: '#B51F00' },
  { value:    128.5, color: '#B41F00' },
  { value:    128.6, color: '#B41F00' },
  { value:    128.7, color: '#B31F00' },
  { value:    128.8, color: '#B31E00' },
  { value:    128.9, color: '#B21E00' },
  { value:      129, color: '#B21E00' },
  { value:    129.1, color: '#B21E00' },
  { value:    129.2, color: '#B11E00' },
  { value:    129.3, color: '#B11E00' },
  { value:    129.4, color: '#B01E00' },
  { value:    129.5, color: '#B01E00' },
  { value:    129.6, color: '#AF1E00' },
  { value:    129.7, color: '#AF1E00' },
  { value:    129.8, color: '#AE1D00' },
  { value:    129.9, color: '#AE1D00' },
  { value:      130, color: '#AD1D00' },
  { value:    130.1, color: '#AC1D00' },
  { value:    130.2, color: '#AC1D00' },
  { value:    130.3, color: '#AB1C00' },
  { value:    130.4, color: '#AB1C00' },
  { value:    130.5, color: '#AA1C00' },
  { value:    130.6, color: '#AA1C00' },
  { value:    130.7, color: '#A91C00' },
  { value:    130.8, color: '#A91C00' },
  { value:    130.9, color: '#A81C00' },
  { value:      131, color: '#A81C00' },
  { value:    131.1, color: '#A81C00' },
  { value:    131.2, color: '#A71C00' },
  { value:    131.3, color: '#A71B00' },
  { value:    131.4, color: '#A61B00' },
  { value:    131.5, color: '#A61B00' },
  { value:    131.6, color: '#A61B00' },
  { value:    131.7, color: '#A51B00' },
  { value:    131.8, color: '#A51A00' },
  { value:    131.9, color: '#A41A00' },
  { value:      132, color: '#A41A00' },
  { value:    132.1, color: '#A41A00' },
  { value:    132.2, color: '#A31A00' },
  { value:    132.3, color: '#A31A00' },
  { value:    132.4, color: '#A21A00' },
  { value:    132.5, color: '#A21A00' },
  { value:    132.6, color: '#A11A00' },
  { value:    132.7, color: '#A11A00' },
  { value:    132.8, color: '#A01900' },
  { value:    132.9, color: '#A01900' },
  { value:      133, color: '#9F1900' },
  { value:    133.1, color: '#9E1900' },
  { value:    133.2, color: '#9E1900' },
  { value:    133.3, color: '#9D1800' },
  { value:    133.4, color: '#9D1800' },
  { value:    133.5, color: '#9C1800' },
  { value:    133.6, color: '#9C1800' },
  { value:    133.7, color: '#9B1800' },
  { value:    133.8, color: '#9B1700' },
  { value:    133.9, color: '#9A1700' },
  { value:      134, color: '#9A1700' },
  { value:    134.1, color: '#9A1700' },
  { value:    134.2, color: '#991700' },
  { value:    134.3, color: '#991600' },
  { value:    134.4, color: '#981600' },
  { value:    134.5, color: '#981600' },
  { value:    134.6, color: '#981600' },
  { value:    134.7, color: '#971600' },
  { value:    134.8, color: '#971600' },
  { value:    134.9, color: '#961600' },
  { value:      135, color: '#961600' },
  { value:    135.1, color: '#961600' },
  { value:    135.2, color: '#951600' },
  { value:    135.3, color: '#951600' },
  { value:    135.4, color: '#941600' },
  { value:    135.5, color: '#941600' },
  { value:    135.6, color: '#931600' },
  { value:    135.7, color: '#931600' },
  { value:    135.8, color: '#921500' },
  { value:    135.9, color: '#921500' },
  { value:      136, color: '#911500' },
  { value:    136.1, color: '#901500' },
  { value:    136.2, color: '#901500' },
  { value:    136.3, color: '#8F1400' },
  { value:    136.4, color: '#8F1400' },
  { value:    136.5, color: '#8E1400' },
  { value:    136.6, color: '#8E1400' },
  { value:    136.7, color: '#8D1400' },
  { value:    136.8, color: '#8D1300' },
  { value:    136.9, color: '#8C1300' },
  { value:      137, color: '#8C1300' },
  { value:    137.1, color: '#8C1300' },
  { value:    137.2, color: '#8B1300' },
  { value:    137.3, color: '#8B1200' },
  { value:    137.4, color: '#8A1200' },
  { value:    137.5, color: '#8A1200' },
  { value:    137.6, color: '#891200' },
  { value:    137.7, color: '#891200' },
  { value:    137.8, color: '#881200' },
  { value:    137.9, color: '#881200' },
  { value:      138, color: '#871200' },
  { value:    138.1, color: '#871200' },
  { value:    138.2, color: '#861200' },
  { value:    138.3, color: '#861100' },
  { value:    138.4, color: '#851100' },
  { value:    138.5, color: '#851100' },
  { value:    138.6, color: '#851100' },
  { value:    138.7, color: '#841100' },
  { value:    138.8, color: '#841000' },
  { value:    138.9, color: '#831000' },
  { value:      139, color: '#831000' },
  { value:    139.1, color: '#821000' },
  { value:    139.2, color: '#821000' },
  { value:    139.3, color: '#811000' },
  { value:    139.4, color: '#811000' },
  { value:    139.5, color: '#801000' },
  { value:    139.6, color: '#801000' },
  { value:    139.7, color: '#7F1000' },
  { value:    139.8, color: '#7F0F00' },
  { value:    139.9, color: '#7E0F00' },
  { value:      140, color: '#7E0F00' },
  { value:    140.1, color: '#7E0F00' },
  { value:    140.2, color: '#7D0F00' },
  { value:    140.3, color: '#7D0E00' },
  { value:    140.4, color: '#7C0E00' },
  { value:    140.5, color: '#7C0E00' },
  { value:    140.6, color: '#7B0E00' },
  { value:    140.7, color: '#7B0E00' },
  { value:    140.8, color: '#7A0E00' },
  { value:    140.9, color: '#7A0E00' },
  { value:      141, color: '#790E00' },
  { value:    141.1, color: '#780E00' },
  { value:    141.2, color: '#780E00' },
  { value:    141.3, color: '#770D00' },
  { value:    141.4, color: '#770D00' },
  { value:    141.5, color: '#760D00' },
  { value:    141.6, color: '#760D00' },
  { value:    141.7, color: '#750D00' },
  { value:    141.8, color: '#750C00' },
  { value:    141.9, color: '#740C00' },
  { value:      142, color: '#740C00' },
  { value:    142.1, color: '#740C00' },
  { value:    142.2, color: '#730C00' },
  { value:    142.3, color: '#730B00' },
  { value:    142.4, color: '#720B00' },
  { value:    142.5, color: '#720B00' },
  { value:    142.6, color: '#720B00' },
  { value:    142.7, color: '#710B00' },
  { value:    142.8, color: '#710A00' },
  { value:    142.9, color: '#700A00' },
  { value:      143, color: '#700A00' },
  { value:    143.1, color: '#700A00' },
  { value:    143.2, color: '#6F0A00' },
  { value:    143.3, color: '#6F0A00' },
  { value:    143.4, color: '#6E0A00' },
  { value:    143.5, color: '#6E0A00' },
  { value:    143.6, color: '#6D0A00' },
  { value:    143.7, color: '#6D0A00' },
  { value:    143.8, color: '#6C0900' },
  { value:    143.9, color: '#6C0900' },
  { value:      144, color: '#6B0900' },
  { value:    144.1, color: '#6A0900' },
  { value:    144.2, color: '#6A0900' },
  { value:    144.3, color: '#690800' },
  { value:    144.4, color: '#690800' },
  { value:    144.5, color: '#680800' },
  { value:    144.6, color: '#680800' },
  { value:    144.7, color: '#670800' },
  { value:    144.8, color: '#670800' },
  { value:    144.9, color: '#660800' },
  { value:      145, color: '#660800' },
  { value:    145.1, color: '#660800' },
  { value:    145.2, color: '#650800' },
  { value:    145.3, color: '#650700' },
  { value:    145.4, color: '#640700' },
  { value:    145.5, color: '#640700' },
  { value:    145.6, color: '#630700' },
  { value:    145.7, color: '#630700' },
  { value:    145.8, color: '#620600' },
  { value:    145.9, color: '#620600' },
  { value:      146, color: '#610600' },
  { value:    146.1, color: '#600600' },
  { value:    146.2, color: '#600600' },
  { value:    146.3, color: '#5F0500' },
  { value:    146.4, color: '#5F0500' },
  { value:    146.5, color: '#5E0500' },
  { value:    146.6, color: '#5E0500' },
  { value:    146.7, color: '#5D0500' },
  { value:    146.8, color: '#5D0400' },
  { value:    146.9, color: '#5C0400' },
  { value:      147, color: '#5C0400' },
  { value:    147.1, color: '#5C0400' },
  { value:    147.2, color: '#5B0400' },
  { value:    147.3, color: '#5B0400' },
  { value:    147.4, color: '#5A0400' },
  { value:    147.5, color: '#5A0400' },
  { value:    147.6, color: '#5A0400' },
  { value:    147.7, color: '#590400' },
  { value:    147.8, color: '#590300' },
  { value:    147.9, color: '#580300' },
  { value:      148, color: '#580300' },
  { value:    148.1, color: '#580300' },
  { value:    148.2, color: '#570300' },
  { value:    148.3, color: '#570200' },
  { value:    148.4, color: '#560200' },
  { value:    148.5, color: '#560200' },
  { value:    148.6, color: '#550200' },
  { value:    148.7, color: '#550200' },
  { value:    148.8, color: '#540200' },
  { value:    148.9, color: '#540200' },
  { value:      149, color: '#530200' },
  { value:    149.1, color: '#520200' },
  { value:    149.2, color: '#520200' },
  { value:    149.3, color: '#510100' },
  { value:    149.4, color: '#510100' },
  { value:    149.5, color: '#500100' },
  { value:    149.6, color: '#500100' },
  { value:    149.7, color: '#4F0100' },
  { value:    149.8, color: '#4F0000' },
  { value:    149.9, color: '#4E0000' },
  { value:      150, color: '#4E0000' },
  ],
  // ── IWR: 0 → 150 mm, step 0.1 (1501 stops) ─────────────────────────────────
  iwr: [
  // IWR  0→150    step 0.1  (1501 stops)
  { value:        0, color: '#E0F7FA' },
  { value:      0.1, color: '#DFF7FA' },
  { value:      0.2, color: '#DEF7FA' },
  { value:      0.3, color: '#DEF6FA' },
  { value:      0.4, color: '#DDF6FA' },
  { value:      0.5, color: '#DCF6FA' },
  { value:      0.6, color: '#DBF6FA' },
  { value:      0.7, color: '#DAF6FA' },
  { value:      0.8, color: '#DAF5F9' },
  { value:      0.9, color: '#D9F5F9' },
  { value:        1, color: '#D8F5F9' },
  { value:      1.1, color: '#D7F5F9' },
  { value:      1.2, color: '#D6F5F9' },
  { value:      1.3, color: '#D6F4F8' },
  { value:      1.4, color: '#D5F4F8' },
  { value:      1.5, color: '#D4F4F8' },
  { value:      1.6, color: '#D3F4F8' },
  { value:      1.7, color: '#D3F4F8' },
  { value:      1.8, color: '#D2F3F7' },
  { value:      1.9, color: '#D2F3F7' },
  { value:        2, color: '#D1F3F7' },
  { value:      2.1, color: '#D0F3F7' },
  { value:      2.2, color: '#D0F3F7' },
  { value:      2.3, color: '#CFF2F6' },
  { value:      2.4, color: '#CFF2F6' },
  { value:      2.5, color: '#CEF2F6' },
  { value:      2.6, color: '#CDF2F6' },
  { value:      2.7, color: '#CCF2F6' },
  { value:      2.8, color: '#CCF1F6' },
  { value:      2.9, color: '#CBF1F6' },
  { value:        3, color: '#CAF1F6' },
  { value:      3.1, color: '#C9F1F6' },
  { value:      3.2, color: '#C8F1F6' },
  { value:      3.3, color: '#C8F0F6' },
  { value:      3.4, color: '#C7F0F6' },
  { value:      3.5, color: '#C6F0F6' },
  { value:      3.6, color: '#C5F0F6' },
  { value:      3.7, color: '#C4F0F6' },
  { value:      3.8, color: '#C4EFF5' },
  { value:      3.9, color: '#C3EFF5' },
  { value:        4, color: '#C2EFF5' },
  { value:      4.1, color: '#C1EFF5' },
  { value:      4.2, color: '#C0EFF5' },
  { value:      4.3, color: '#C0EEF4' },
  { value:      4.4, color: '#BFEEF4' },
  { value:      4.5, color: '#BEEEF4' },
  { value:      4.6, color: '#BDEEF4' },
  { value:      4.7, color: '#BCEDF4' },
  { value:      4.8, color: '#BCEDF4' },
  { value:      4.9, color: '#BBECF4' },
  { value:        5, color: '#BAECF4' },
  { value:      5.1, color: '#B9ECF4' },
  { value:      5.2, color: '#B8ECF4' },
  { value:      5.3, color: '#B8EBF3' },
  { value:      5.4, color: '#B7EBF3' },
  { value:      5.5, color: '#B6EBF3' },
  { value:      5.6, color: '#B5EBF3' },
  { value:      5.7, color: '#B5EBF3' },
  { value:      5.8, color: '#B4EAF2' },
  { value:      5.9, color: '#B4EAF2' },
  { value:        6, color: '#B3EAF2' },
  { value:      6.1, color: '#B2EAF2' },
  { value:      6.2, color: '#B2EAF2' },
  { value:      6.3, color: '#B1E9F2' },
  { value:      6.4, color: '#B1E9F2' },
  { value:      6.5, color: '#B0E9F2' },
  { value:      6.6, color: '#AFE9F2' },
  { value:      6.7, color: '#AEE9F2' },
  { value:      6.8, color: '#AEE8F1' },
  { value:      6.9, color: '#ADE8F1' },
  { value:        7, color: '#ACE8F1' },
  { value:      7.1, color: '#ABE8F1' },
  { value:      7.2, color: '#AAE8F1' },
  { value:      7.3, color: '#AAE7F0' },
  { value:      7.4, color: '#A9E7F0' },
  { value:      7.5, color: '#A8E7F0' },
  { value:      7.6, color: '#A7E7F0' },
  { value:      7.7, color: '#A6E7F0' },
  { value:      7.8, color: '#A6E6F0' },
  { value:      7.9, color: '#A5E6F0' },
  { value:        8, color: '#A4E6F0' },
  { value:      8.1, color: '#A3E6F0' },
  { value:      8.2, color: '#A2E6F0' },
  { value:      8.3, color: '#A2E5EF' },
  { value:      8.4, color: '#A1E5EF' },
  { value:      8.5, color: '#A0E5EF' },
  { value:      8.6, color: '#9FE5EF' },
  { value:      8.7, color: '#9EE5EF' },
  { value:      8.8, color: '#9EE4EE' },
  { value:      8.9, color: '#9DE4EE' },
  { value:        9, color: '#9CE4EE' },
  { value:      9.1, color: '#9BE4EE' },
  { value:      9.2, color: '#9AE4EE' },
  { value:      9.3, color: '#9AE3EE' },
  { value:      9.4, color: '#99E3EE' },
  { value:      9.5, color: '#98E3EE' },
  { value:      9.6, color: '#97E3EE' },
  { value:      9.7, color: '#97E3EE' },
  { value:      9.8, color: '#96E2ED' },
  { value:      9.9, color: '#96E2ED' },
  { value:       10, color: '#95E2ED' },
  { value:     10.1, color: '#94E2ED' },
  { value:     10.2, color: '#94E2ED' },
  { value:     10.3, color: '#93E1EC' },
  { value:     10.4, color: '#93E1EC' },
  { value:     10.5, color: '#92E1EC' },
  { value:     10.6, color: '#91E1EC' },
  { value:     10.7, color: '#90E1EC' },
  { value:     10.8, color: '#90E0EC' },
  { value:     10.9, color: '#8FE0EC' },
  { value:       11, color: '#8EE0EC' },
  { value:     11.1, color: '#8DE0EC' },
  { value:     11.2, color: '#8CE0EC' },
  { value:     11.3, color: '#8CDFEC' },
  { value:     11.4, color: '#8BDFEC' },
  { value:     11.5, color: '#8ADFEC' },
  { value:     11.6, color: '#89DFEC' },
  { value:     11.7, color: '#88DFEC' },
  { value:     11.8, color: '#88DEEB' },
  { value:     11.9, color: '#87DEEB' },
  { value:       12, color: '#86DEEB' },
  { value:     12.1, color: '#85DEEB' },
  { value:     12.2, color: '#84DEEB' },
  { value:     12.3, color: '#84DDEA' },
  { value:     12.4, color: '#83DDEA' },
  { value:     12.5, color: '#82DDEA' },
  { value:     12.6, color: '#81DDEA' },
  { value:     12.7, color: '#81DDEA' },
  { value:     12.8, color: '#80DCE9' },
  { value:     12.9, color: '#80DCE9' },
  { value:       13, color: '#7FDCE9' },
  { value:     13.1, color: '#7EDCE9' },
  { value:     13.2, color: '#7DDCE9' },
  { value:     13.3, color: '#7DDBE8' },
  { value:     13.4, color: '#7CDBE8' },
  { value:     13.5, color: '#7BDBE8' },
  { value:     13.6, color: '#7ADBE8' },
  { value:     13.7, color: '#79DBE8' },
  { value:     13.8, color: '#79DAE8' },
  { value:     13.9, color: '#78DAE8' },
  { value:       14, color: '#77DAE8' },
  { value:     14.1, color: '#76DAE8' },
  { value:     14.2, color: '#76DAE8' },
  { value:     14.3, color: '#75D9E8' },
  { value:     14.4, color: '#75D9E8' },
  { value:     14.5, color: '#74D9E8' },
  { value:     14.6, color: '#73D9E8' },
  { value:     14.7, color: '#72D9E8' },
  { value:     14.8, color: '#72D8E7' },
  { value:     14.9, color: '#71D8E7' },
  { value:       15, color: '#70D8E7' },
  { value:     15.1, color: '#6FD8E7' },
  { value:     15.2, color: '#6ED7E7' },
  { value:     15.3, color: '#6ED7E6' },
  { value:     15.4, color: '#6DD6E6' },
  { value:     15.5, color: '#6CD6E6' },
  { value:     15.6, color: '#6BD6E6' },
  { value:     15.7, color: '#6BD6E6' },
  { value:     15.8, color: '#6AD5E6' },
  { value:     15.9, color: '#6AD5E6' },
  { value:       16, color: '#69D5E6' },
  { value:     16.1, color: '#68D5E6' },
  { value:     16.2, color: '#67D5E6' },
  { value:     16.3, color: '#67D4E6' },
  { value:     16.4, color: '#66D4E6' },
  { value:     16.5, color: '#65D4E6' },
  { value:     16.6, color: '#64D4E6' },
  { value:     16.7, color: '#63D4E6' },
  { value:     16.8, color: '#63D3E5' },
  { value:     16.9, color: '#62D3E5' },
  { value:       17, color: '#61D3E5' },
  { value:     17.1, color: '#60D3E5' },
  { value:     17.2, color: '#60D3E5' },
  { value:     17.3, color: '#5FD2E4' },
  { value:     17.4, color: '#5FD2E4' },
  { value:     17.5, color: '#5ED2E4' },
  { value:     17.6, color: '#5DD2E4' },
  { value:     17.7, color: '#5CD2E4' },
  { value:     17.8, color: '#5CD1E3' },
  { value:     17.9, color: '#5BD1E3' },
  { value:       18, color: '#5AD1E3' },
  { value:     18.1, color: '#59D1E3' },
  { value:     18.2, color: '#58D1E3' },
  { value:     18.3, color: '#58D0E2' },
  { value:     18.4, color: '#57D0E2' },
  { value:     18.5, color: '#56D0E2' },
  { value:     18.6, color: '#55D0E2' },
  { value:     18.7, color: '#54D0E2' },
  { value:     18.8, color: '#54CFE2' },
  { value:     18.9, color: '#53CFE2' },
  { value:       19, color: '#52CFE2' },
  { value:     19.1, color: '#51CFE2' },
  { value:     19.2, color: '#50CFE2' },
  { value:     19.3, color: '#50CEE2' },
  { value:     19.4, color: '#4FCEE2' },
  { value:     19.5, color: '#4ECEE2' },
  { value:     19.6, color: '#4DCEE2' },
  { value:     19.7, color: '#4DCEE2' },
  { value:     19.8, color: '#4CCDE1' },
  { value:     19.9, color: '#4CCDE1' },
  { value:       20, color: '#4BCDE1' },
  { value:     20.1, color: '#4ACDE1' },
  { value:     20.2, color: '#4ACDE1' },
  { value:     20.3, color: '#49CCE0' },
  { value:     20.4, color: '#49CCE0' },
  { value:     20.5, color: '#48CCE0' },
  { value:     20.6, color: '#47CCE0' },
  { value:     20.7, color: '#46CCE0' },
  { value:     20.8, color: '#46CBE0' },
  { value:     20.9, color: '#45CBE0' },
  { value:       21, color: '#44CBE0' },
  { value:     21.1, color: '#43CBE0' },
  { value:     21.2, color: '#42CBE0' },
  { value:     21.3, color: '#42CADF' },
  { value:     21.4, color: '#41CADF' },
  { value:     21.5, color: '#40CADF' },
  { value:     21.6, color: '#3FCADF' },
  { value:     21.7, color: '#3ECADF' },
  { value:     21.8, color: '#3EC9DE' },
  { value:     21.9, color: '#3DC9DE' },
  { value:       22, color: '#3CC9DE' },
  { value:     22.1, color: '#3BC9DE' },
  { value:     22.2, color: '#3AC9DE' },
  { value:     22.3, color: '#3AC8DE' },
  { value:     22.4, color: '#39C8DE' },
  { value:     22.5, color: '#38C8DE' },
  { value:     22.6, color: '#37C8DE' },
  { value:     22.7, color: '#36C8DE' },
  { value:     22.8, color: '#36C7DD' },
  { value:     22.9, color: '#35C7DD' },
  { value:       23, color: '#34C7DD' },
  { value:     23.1, color: '#33C7DD' },
  { value:     23.2, color: '#32C7DD' },
  { value:     23.3, color: '#32C6DC' },
  { value:     23.4, color: '#31C6DC' },
  { value:     23.5, color: '#30C6DC' },
  { value:     23.6, color: '#2FC6DC' },
  { value:     23.7, color: '#2FC6DC' },
  { value:     23.8, color: '#2EC5DC' },
  { value:     23.9, color: '#2EC5DC' },
  { value:       24, color: '#2DC5DC' },
  { value:     24.1, color: '#2CC5DC' },
  { value:     24.2, color: '#2CC5DC' },
  { value:     24.3, color: '#2BC4DB' },
  { value:     24.4, color: '#2BC4DB' },
  { value:     24.5, color: '#2AC4DB' },
  { value:     24.6, color: '#29C4DB' },
  { value:     24.7, color: '#28C3DB' },
  { value:     24.8, color: '#28C3DA' },
  { value:     24.9, color: '#27C2DA' },
  { value:       25, color: '#26C2DA' },
  { value:     25.1, color: '#25C2DA' },
  { value:     25.2, color: '#24C2DA' },
  { value:     25.3, color: '#24C1DA' },
  { value:     25.4, color: '#23C1DA' },
  { value:     25.5, color: '#22C1DA' },
  { value:     25.6, color: '#21C1DA' },
  { value:     25.7, color: '#20C1DA' },
  { value:     25.8, color: '#20C0D9' },
  { value:     25.9, color: '#1FC0D9' },
  { value:       26, color: '#1EC0D9' },
  { value:     26.1, color: '#1DC0D9' },
  { value:     26.2, color: '#1CC0D9' },
  { value:     26.3, color: '#1CBFD8' },
  { value:     26.4, color: '#1BBFD8' },
  { value:     26.5, color: '#1ABFD8' },
  { value:     26.6, color: '#19BFD8' },
  { value:     26.7, color: '#18BFD8' },
  { value:     26.8, color: '#18BED8' },
  { value:     26.9, color: '#17BED8' },
  { value:       27, color: '#16BED8' },
  { value:     27.1, color: '#15BED8' },
  { value:     27.2, color: '#14BED8' },
  { value:     27.3, color: '#14BDD8' },
  { value:     27.4, color: '#13BDD8' },
  { value:     27.5, color: '#12BDD8' },
  { value:     27.6, color: '#11BDD8' },
  { value:     27.7, color: '#11BDD8' },
  { value:     27.8, color: '#10BCD7' },
  { value:     27.9, color: '#10BCD7' },
  { value:       28, color: '#0FBCD7' },
  { value:     28.1, color: '#0EBCD7' },
  { value:     28.2, color: '#0EBCD7' },
  { value:     28.3, color: '#0DBBD6' },
  { value:     28.4, color: '#0DBBD6' },
  { value:     28.5, color: '#0CBBD6' },
  { value:     28.6, color: '#0BBBD6' },
  { value:     28.7, color: '#0ABBD6' },
  { value:     28.8, color: '#0ABAD5' },
  { value:     28.9, color: '#09BAD5' },
  { value:       29, color: '#08BAD5' },
  { value:     29.1, color: '#07BAD5' },
  { value:     29.2, color: '#06BAD5' },
  { value:     29.3, color: '#06B9D4' },
  { value:     29.4, color: '#05B9D4' },
  { value:     29.5, color: '#04B9D4' },
  { value:     29.6, color: '#03B9D4' },
  { value:     29.7, color: '#02B9D4' },
  { value:     29.8, color: '#02B8D4' },
  { value:     29.9, color: '#01B8D4' },
  { value:       30, color: '#00B8D4' },
  { value:     30.1, color: '#00B8D4' },
  { value:     30.2, color: '#00B7D3' },
  { value:     30.3, color: '#00B7D3' },
  { value:     30.4, color: '#00B6D2' },
  { value:     30.5, color: '#00B6D2' },
  { value:     30.6, color: '#00B6D2' },
  { value:     30.7, color: '#00B6D1' },
  { value:     30.8, color: '#00B5D1' },
  { value:     30.9, color: '#00B5D0' },
  { value:       31, color: '#00B5D0' },
  { value:     31.1, color: '#00B5D0' },
  { value:     31.2, color: '#00B5CF' },
  { value:     31.3, color: '#00B4CF' },
  { value:     31.4, color: '#00B4CE' },
  { value:     31.5, color: '#00B4CE' },
  { value:     31.6, color: '#00B4CE' },
  { value:     31.7, color: '#00B3CE' },
  { value:     31.8, color: '#00B3CD' },
  { value:     31.9, color: '#00B2CD' },
  { value:       32, color: '#00B2CD' },
  { value:     32.1, color: '#00B2CD' },
  { value:     32.2, color: '#00B1CC' },
  { value:     32.3, color: '#00B1CC' },
  { value:     32.4, color: '#00B0CB' },
  { value:     32.5, color: '#00B0CB' },
  { value:     32.6, color: '#00B0CB' },
  { value:     32.7, color: '#00B0CA' },
  { value:     32.8, color: '#00AFCA' },
  { value:     32.9, color: '#00AFC9' },
  { value:       33, color: '#00AFC9' },
  { value:     33.1, color: '#00AFC9' },
  { value:     33.2, color: '#00AFC8' },
  { value:     33.3, color: '#00AEC8' },
  { value:     33.4, color: '#00AEC7' },
  { value:     33.5, color: '#00AEC7' },
  { value:     33.6, color: '#00AEC7' },
  { value:     33.7, color: '#00ADC6' },
  { value:     33.8, color: '#00ADC6' },
  { value:     33.9, color: '#00ACC5' },
  { value:       34, color: '#00ACC5' },
  { value:     34.1, color: '#00ACC5' },
  { value:     34.2, color: '#00ACC5' },
  { value:     34.3, color: '#00ABC4' },
  { value:     34.4, color: '#00ABC4' },
  { value:     34.5, color: '#00ABC4' },
  { value:     34.6, color: '#00ABC4' },
  { value:     34.7, color: '#00ABC3' },
  { value:     34.8, color: '#00AAC3' },
  { value:     34.9, color: '#00AAC2' },
  { value:       35, color: '#00AAC2' },
  { value:     35.1, color: '#00AAC2' },
  { value:     35.2, color: '#00A9C1' },
  { value:     35.3, color: '#00A9C1' },
  { value:     35.4, color: '#00A8C0' },
  { value:     35.5, color: '#00A8C0' },
  { value:     35.6, color: '#00A8C0' },
  { value:     35.7, color: '#00A8BF' },
  { value:     35.8, color: '#00A7BF' },
  { value:     35.9, color: '#00A7BE' },
  { value:       36, color: '#00A7BE' },
  { value:     36.1, color: '#00A7BE' },
  { value:     36.2, color: '#00A7BD' },
  { value:     36.3, color: '#00A6BD' },
  { value:     36.4, color: '#00A6BC' },
  { value:     36.5, color: '#00A6BC' },
  { value:     36.6, color: '#00A6BC' },
  { value:     36.7, color: '#00A5BB' },
  { value:     36.8, color: '#00A5BB' },
  { value:     36.9, color: '#00A4BA' },
  { value:       37, color: '#00A4BA' },
  { value:     37.1, color: '#00A4BA' },
  { value:     37.2, color: '#00A3B9' },
  { value:     37.3, color: '#00A3B9' },
  { value:     37.4, color: '#00A2B8' },
  { value:     37.5, color: '#00A2B8' },
  { value:     37.6, color: '#00A2B8' },
  { value:     37.7, color: '#00A2B7' },
  { value:     37.8, color: '#00A1B7' },
  { value:     37.9, color: '#00A1B6' },
  { value:       38, color: '#00A1B6' },
  { value:     38.1, color: '#00A1B6' },
  { value:     38.2, color: '#00A1B5' },
  { value:     38.3, color: '#00A0B5' },
  { value:     38.4, color: '#00A0B4' },
  { value:     38.5, color: '#00A0B4' },
  { value:     38.6, color: '#00A0B4' },
  { value:     38.7, color: '#009FB4' },
  { value:     38.8, color: '#009FB3' },
  { value:     38.9, color: '#009EB3' },
  { value:       39, color: '#009EB3' },
  { value:     39.1, color: '#009EB3' },
  { value:     39.2, color: '#009DB2' },
  { value:     39.3, color: '#009DB2' },
  { value:     39.4, color: '#009CB1' },
  { value:     39.5, color: '#009CB1' },
  { value:     39.6, color: '#009CB1' },
  { value:     39.7, color: '#009CB0' },
  { value:     39.8, color: '#009BB0' },
  { value:     39.9, color: '#009BAF' },
  { value:       40, color: '#009BAF' },
  { value:     40.1, color: '#009BAF' },
  { value:     40.2, color: '#009BAE' },
  { value:     40.3, color: '#009AAE' },
  { value:     40.4, color: '#009AAD' },
  { value:     40.5, color: '#009AAD' },
  { value:     40.6, color: '#009AAD' },
  { value:     40.7, color: '#0099AC' },
  { value:     40.8, color: '#0099AC' },
  { value:     40.9, color: '#0098AB' },
  { value:       41, color: '#0098AB' },
  { value:     41.1, color: '#0098AB' },
  { value:     41.2, color: '#0097AA' },
  { value:     41.3, color: '#0097AA' },
  { value:     41.4, color: '#0096A9' },
  { value:     41.5, color: '#0096A9' },
  { value:     41.6, color: '#0096A9' },
  { value:     41.7, color: '#0096A8' },
  { value:     41.8, color: '#0095A8' },
  { value:     41.9, color: '#0095A7' },
  { value:       42, color: '#0095A7' },
  { value:     42.1, color: '#0095A7' },
  { value:     42.2, color: '#0095A7' },
  { value:     42.3, color: '#0094A6' },
  { value:     42.4, color: '#0094A6' },
  { value:     42.5, color: '#0094A6' },
  { value:     42.6, color: '#0094A6' },
  { value:     42.7, color: '#0093A5' },
  { value:     42.8, color: '#0093A5' },
  { value:     42.9, color: '#0092A4' },
  { value:       43, color: '#0092A4' },
  { value:     43.1, color: '#0092A4' },
  { value:     43.2, color: '#0091A3' },
  { value:     43.3, color: '#0091A3' },
  { value:     43.4, color: '#0090A2' },
  { value:     43.5, color: '#0090A2' },
  { value:     43.6, color: '#0090A2' },
  { value:     43.7, color: '#0090A1' },
  { value:     43.8, color: '#008FA1' },
  { value:     43.9, color: '#008FA0' },
  { value:       44, color: '#008FA0' },
  { value:     44.1, color: '#008FA0' },
  { value:     44.2, color: '#008F9F' },
  { value:     44.3, color: '#008E9F' },
  { value:     44.4, color: '#008E9E' },
  { value:     44.5, color: '#008E9E' },
  { value:     44.6, color: '#008E9E' },
  { value:     44.7, color: '#008D9D' },
  { value:     44.8, color: '#008D9D' },
  { value:     44.9, color: '#008C9C' },
  { value:       45, color: '#008C9C' },
  { value:     45.1, color: '#008C9C' },
  { value:     45.2, color: '#008B9B' },
  { value:     45.3, color: '#008B9B' },
  { value:     45.4, color: '#008A9A' },
  { value:     45.5, color: '#008A9A' },
  { value:     45.6, color: '#008A9A' },
  { value:     45.7, color: '#008A99' },
  { value:     45.8, color: '#008999' },
  { value:     45.9, color: '#008998' },
  { value:       46, color: '#008998' },
  { value:     46.1, color: '#008998' },
  { value:     46.2, color: '#008997' },
  { value:     46.3, color: '#008897' },
  { value:     46.4, color: '#008896' },
  { value:     46.5, color: '#008896' },
  { value:     46.6, color: '#008896' },
  { value:     46.7, color: '#008795' },
  { value:     46.8, color: '#008795' },
  { value:     46.9, color: '#008694' },
  { value:       47, color: '#008694' },
  { value:     47.1, color: '#008694' },
  { value:     47.2, color: '#008593' },
  { value:     47.3, color: '#008593' },
  { value:     47.4, color: '#008492' },
  { value:     47.5, color: '#008492' },
  { value:     47.6, color: '#008492' },
  { value:     47.7, color: '#008492' },
  { value:     47.8, color: '#008391' },
  { value:     47.9, color: '#008391' },
  { value:       48, color: '#008391' },
  { value:     48.1, color: '#008391' },
  { value:     48.2, color: '#008390' },
  { value:     48.3, color: '#008290' },
  { value:     48.4, color: '#00828F' },
  { value:     48.5, color: '#00828F' },
  { value:     48.6, color: '#00828F' },
  { value:     48.7, color: '#00818E' },
  { value:     48.8, color: '#00818E' },
  { value:     48.9, color: '#00808D' },
  { value:       49, color: '#00808D' },
  { value:     49.1, color: '#00808D' },
  { value:     49.2, color: '#007F8C' },
  { value:     49.3, color: '#007F8C' },
  { value:     49.4, color: '#007E8B' },
  { value:     49.5, color: '#007E8B' },
  { value:     49.6, color: '#007E8B' },
  { value:     49.7, color: '#007E8A' },
  { value:     49.8, color: '#007D8A' },
  { value:     49.9, color: '#007D89' },
  { value:       50, color: '#007D89' },
  { value:     50.1, color: '#007D89' },
  { value:     50.2, color: '#007D88' },
  { value:     50.3, color: '#007C88' },
  { value:     50.4, color: '#007C87' },
  { value:     50.5, color: '#007C87' },
  { value:     50.6, color: '#007C87' },
  { value:     50.7, color: '#007B86' },
  { value:     50.8, color: '#007B86' },
  { value:     50.9, color: '#007A85' },
  { value:       51, color: '#007A85' },
  { value:     51.1, color: '#007A85' },
  { value:     51.2, color: '#007985' },
  { value:     51.3, color: '#007984' },
  { value:     51.4, color: '#007884' },
  { value:     51.5, color: '#007884' },
  { value:     51.6, color: '#007884' },
  { value:     51.7, color: '#007883' },
  { value:     51.8, color: '#007783' },
  { value:     51.9, color: '#007782' },
  { value:       52, color: '#007782' },
  { value:     52.1, color: '#007782' },
  { value:     52.2, color: '#007781' },
  { value:     52.3, color: '#007681' },
  { value:     52.4, color: '#007680' },
  { value:     52.5, color: '#007680' },
  { value:     52.6, color: '#007680' },
  { value:     52.7, color: '#00757F' },
  { value:     52.8, color: '#00757F' },
  { value:     52.9, color: '#00747E' },
  { value:       53, color: '#00747E' },
  { value:     53.1, color: '#00747E' },
  { value:     53.2, color: '#00737D' },
  { value:     53.3, color: '#00737D' },
  { value:     53.4, color: '#00727C' },
  { value:     53.5, color: '#00727C' },
  { value:     53.6, color: '#00727C' },
  { value:     53.7, color: '#00727B' },
  { value:     53.8, color: '#00717B' },
  { value:     53.9, color: '#00717A' },
  { value:       54, color: '#00717A' },
  { value:     54.1, color: '#00717A' },
  { value:     54.2, color: '#007179' },
  { value:     54.3, color: '#007079' },
  { value:     54.4, color: '#007078' },
  { value:     54.5, color: '#007078' },
  { value:     54.6, color: '#007078' },
  { value:     54.7, color: '#006F77' },
  { value:     54.8, color: '#006F77' },
  { value:     54.9, color: '#006E76' },
  { value:       55, color: '#006E76' },
  { value:     55.1, color: '#006E76' },
  { value:     55.2, color: '#006E75' },
  { value:     55.3, color: '#006D75' },
  { value:     55.4, color: '#006D74' },
  { value:     55.5, color: '#006D74' },
  { value:     55.6, color: '#006D74' },
  { value:     55.7, color: '#006D74' },
  { value:     55.8, color: '#006C73' },
  { value:     55.9, color: '#006C73' },
  { value:       56, color: '#006C73' },
  { value:     56.1, color: '#006C73' },
  { value:     56.2, color: '#006B72' },
  { value:     56.3, color: '#006B72' },
  { value:     56.4, color: '#006A71' },
  { value:     56.5, color: '#006A71' },
  { value:     56.6, color: '#006A71' },
  { value:     56.7, color: '#006A70' },
  { value:     56.8, color: '#006970' },
  { value:     56.9, color: '#00696F' },
  { value:       57, color: '#00696F' },
  { value:     57.1, color: '#00696F' },
  { value:     57.2, color: '#00696E' },
  { value:     57.3, color: '#00686E' },
  { value:     57.4, color: '#00686D' },
  { value:     57.5, color: '#00686D' },
  { value:     57.6, color: '#00686D' },
  { value:     57.7, color: '#00676C' },
  { value:     57.8, color: '#00676C' },
  { value:     57.9, color: '#00666B' },
  { value:       58, color: '#00666B' },
  { value:     58.1, color: '#00666B' },
  { value:     58.2, color: '#00656B' },
  { value:     58.3, color: '#00656A' },
  { value:     58.4, color: '#00646A' },
  { value:     58.5, color: '#00646A' },
  { value:     58.6, color: '#00646A' },
  { value:     58.7, color: '#006469' },
  { value:     58.8, color: '#006369' },
  { value:     58.9, color: '#006368' },
  { value:       59, color: '#006368' },
  { value:     59.1, color: '#006368' },
  { value:     59.2, color: '#006367' },
  { value:     59.3, color: '#006267' },
  { value:     59.4, color: '#006266' },
  { value:     59.5, color: '#006266' },
  { value:     59.6, color: '#006266' },
  { value:     59.7, color: '#006165' },
  { value:     59.8, color: '#006165' },
  { value:     59.9, color: '#006064' },
  { value:       60, color: '#006064' },
  { value:     60.1, color: '#006064' },
  { value:     60.2, color: '#006064' },
  { value:     60.3, color: '#015F65' },
  { value:     60.4, color: '#015F65' },
  { value:     60.5, color: '#015F65' },
  { value:     60.6, color: '#015F65' },
  { value:     60.7, color: '#015F65' },
  { value:     60.8, color: '#025E66' },
  { value:     60.9, color: '#025E66' },
  { value:       61, color: '#025E66' },
  { value:     61.1, color: '#025E66' },
  { value:     61.2, color: '#025D66' },
  { value:     61.3, color: '#025D66' },
  { value:     61.4, color: '#025C66' },
  { value:     61.5, color: '#025C66' },
  { value:     61.6, color: '#025C66' },
  { value:     61.7, color: '#025C66' },
  { value:     61.8, color: '#035B67' },
  { value:     61.9, color: '#035B67' },
  { value:       62, color: '#035B67' },
  { value:     62.1, color: '#035B67' },
  { value:     62.2, color: '#035B67' },
  { value:     62.3, color: '#045A68' },
  { value:     62.4, color: '#045A68' },
  { value:     62.5, color: '#045A68' },
  { value:     62.6, color: '#045A68' },
  { value:     62.7, color: '#045A68' },
  { value:     62.8, color: '#055968' },
  { value:     62.9, color: '#055968' },
  { value:       63, color: '#055968' },
  { value:     63.1, color: '#055968' },
  { value:     63.2, color: '#055968' },
  { value:     63.3, color: '#065869' },
  { value:     63.4, color: '#065869' },
  { value:     63.5, color: '#065869' },
  { value:     63.6, color: '#065869' },
  { value:     63.7, color: '#065869' },
  { value:     63.8, color: '#06576A' },
  { value:     63.9, color: '#06576A' },
  { value:       64, color: '#06576A' },
  { value:     64.1, color: '#06576A' },
  { value:     64.2, color: '#06576A' },
  { value:     64.3, color: '#07566B' },
  { value:     64.4, color: '#07566B' },
  { value:     64.5, color: '#07566B' },
  { value:     64.6, color: '#07566B' },
  { value:     64.7, color: '#07556B' },
  { value:     64.8, color: '#08556C' },
  { value:     64.9, color: '#08546C' },
  { value:       65, color: '#08546C' },
  { value:     65.1, color: '#08546C' },
  { value:     65.2, color: '#08546C' },
  { value:     65.3, color: '#09536C' },
  { value:     65.4, color: '#09536C' },
  { value:     65.5, color: '#09536C' },
  { value:     65.6, color: '#09536C' },
  { value:     65.7, color: '#09536C' },
  { value:     65.8, color: '#0A526D' },
  { value:     65.9, color: '#0A526D' },
  { value:       66, color: '#0A526D' },
  { value:     66.1, color: '#0A526D' },
  { value:     66.2, color: '#0A526D' },
  { value:     66.3, color: '#0A516E' },
  { value:     66.4, color: '#0A516E' },
  { value:     66.5, color: '#0A516E' },
  { value:     66.6, color: '#0A516E' },
  { value:     66.7, color: '#0A516E' },
  { value:     66.8, color: '#0B506E' },
  { value:     66.9, color: '#0B506E' },
  { value:       67, color: '#0B506E' },
  { value:     67.1, color: '#0B506E' },
  { value:     67.2, color: '#0B506E' },
  { value:     67.3, color: '#0C4F6F' },
  { value:     67.4, color: '#0C4F6F' },
  { value:     67.5, color: '#0C4F6F' },
  { value:     67.6, color: '#0C4F6F' },
  { value:     67.7, color: '#0C4F6F' },
  { value:     67.8, color: '#0D4E70' },
  { value:     67.9, color: '#0D4E70' },
  { value:       68, color: '#0D4E70' },
  { value:     68.1, color: '#0D4E70' },
  { value:     68.2, color: '#0D4D70' },
  { value:     68.3, color: '#0E4D71' },
  { value:     68.4, color: '#0E4C71' },
  { value:     68.5, color: '#0E4C71' },
  { value:     68.6, color: '#0E4C71' },
  { value:     68.7, color: '#0E4C71' },
  { value:     68.8, color: '#0E4B72' },
  { value:     68.9, color: '#0E4B72' },
  { value:       69, color: '#0E4B72' },
  { value:     69.1, color: '#0E4B72' },
  { value:     69.2, color: '#0E4B72' },
  { value:     69.3, color: '#0F4A72' },
  { value:     69.4, color: '#0F4A72' },
  { value:     69.5, color: '#0F4A72' },
  { value:     69.6, color: '#0F4A72' },
  { value:     69.7, color: '#0F4A72' },
  { value:     69.8, color: '#104973' },
  { value:     69.9, color: '#104973' },
  { value:       70, color: '#104973' },
  { value:     70.1, color: '#104973' },
  { value:     70.2, color: '#104973' },
  { value:     70.3, color: '#114874' },
  { value:     70.4, color: '#114874' },
  { value:     70.5, color: '#114874' },
  { value:     70.6, color: '#114874' },
  { value:     70.7, color: '#114874' },
  { value:     70.8, color: '#124775' },
  { value:     70.9, color: '#124775' },
  { value:       71, color: '#124775' },
  { value:     71.1, color: '#124775' },
  { value:     71.2, color: '#124775' },
  { value:     71.3, color: '#124676' },
  { value:     71.4, color: '#124676' },
  { value:     71.5, color: '#124676' },
  { value:     71.6, color: '#124676' },
  { value:     71.7, color: '#124576' },
  { value:     71.8, color: '#134576' },
  { value:     71.9, color: '#134476' },
  { value:       72, color: '#134476' },
  { value:     72.1, color: '#134476' },
  { value:     72.2, color: '#134476' },
  { value:     72.3, color: '#144377' },
  { value:     72.4, color: '#144377' },
  { value:     72.5, color: '#144377' },
  { value:     72.6, color: '#144377' },
  { value:     72.7, color: '#144377' },
  { value:     72.8, color: '#154278' },
  { value:     72.9, color: '#154278' },
  { value:       73, color: '#154278' },
  { value:     73.1, color: '#154278' },
  { value:     73.2, color: '#154278' },
  { value:     73.3, color: '#164178' },
  { value:     73.4, color: '#164178' },
  { value:     73.5, color: '#164178' },
  { value:     73.6, color: '#164178' },
  { value:     73.7, color: '#164178' },
  { value:     73.8, color: '#174079' },
  { value:     73.9, color: '#174079' },
  { value:       74, color: '#174079' },
  { value:     74.1, color: '#174079' },
  { value:     74.2, color: '#174079' },
  { value:     74.3, color: '#183F7A' },
  { value:     74.4, color: '#183F7A' },
  { value:     74.5, color: '#183F7A' },
  { value:     74.6, color: '#183F7A' },
  { value:     74.7, color: '#183F7A' },
  { value:     74.8, color: '#183E7B' },
  { value:     74.9, color: '#183E7B' },
  { value:       75, color: '#183E7B' },
  { value:     75.1, color: '#183E7B' },
  { value:     75.2, color: '#183D7B' },
  { value:     75.3, color: '#193D7C' },
  { value:     75.4, color: '#193C7C' },
  { value:     75.5, color: '#193C7C' },
  { value:     75.6, color: '#193C7C' },
  { value:     75.7, color: '#193C7C' },
  { value:     75.8, color: '#1A3B7D' },
  { value:     75.9, color: '#1A3B7D' },
  { value:       76, color: '#1A3B7D' },
  { value:     76.1, color: '#1A3B7D' },
  { value:     76.2, color: '#1A3B7D' },
  { value:     76.3, color: '#1B3A7E' },
  { value:     76.4, color: '#1B3A7E' },
  { value:     76.5, color: '#1B3A7E' },
  { value:     76.6, color: '#1B3A7E' },
  { value:     76.7, color: '#1B3A7E' },
  { value:     76.8, color: '#1C397E' },
  { value:     76.9, color: '#1C397E' },
  { value:       77, color: '#1C397E' },
  { value:     77.1, color: '#1C397E' },
  { value:     77.2, color: '#1C397E' },
  { value:     77.3, color: '#1D387F' },
  { value:     77.4, color: '#1D387F' },
  { value:     77.5, color: '#1D387F' },
  { value:     77.6, color: '#1D387F' },
  { value:     77.7, color: '#1D387F' },
  { value:     77.8, color: '#1E3780' },
  { value:     77.9, color: '#1E3780' },
  { value:       78, color: '#1E3780' },
  { value:     78.1, color: '#1E3780' },
  { value:     78.2, color: '#1E3780' },
  { value:     78.3, color: '#1E3680' },
  { value:     78.4, color: '#1E3680' },
  { value:     78.5, color: '#1E3680' },
  { value:     78.6, color: '#1E3680' },
  { value:     78.7, color: '#1E3580' },
  { value:     78.8, color: '#1F3581' },
  { value:     78.9, color: '#1F3481' },
  { value:       79, color: '#1F3481' },
  { value:     79.1, color: '#1F3481' },
  { value:     79.2, color: '#1F3481' },
  { value:     79.3, color: '#203382' },
  { value:     79.4, color: '#203382' },
  { value:     79.5, color: '#203382' },
  { value:     79.6, color: '#203382' },
  { value:     79.7, color: '#203382' },
  { value:     79.8, color: '#213283' },
  { value:     79.9, color: '#213283' },
  { value:       80, color: '#213283' },
  { value:     80.1, color: '#213283' },
  { value:     80.2, color: '#213283' },
  { value:     80.3, color: '#223184' },
  { value:     80.4, color: '#223184' },
  { value:     80.5, color: '#223184' },
  { value:     80.6, color: '#223184' },
  { value:     80.7, color: '#223184' },
  { value:     80.8, color: '#233084' },
  { value:     80.9, color: '#233084' },
  { value:       81, color: '#233084' },
  { value:     81.1, color: '#233084' },
  { value:     81.2, color: '#232F84' },
  { value:     81.3, color: '#242F85' },
  { value:     81.4, color: '#242E85' },
  { value:     81.5, color: '#242E85' },
  { value:     81.6, color: '#242E85' },
  { value:     81.7, color: '#242E85' },
  { value:     81.8, color: '#242D86' },
  { value:     81.9, color: '#242D86' },
  { value:       82, color: '#242D86' },
  { value:     82.1, color: '#242D86' },
  { value:     82.2, color: '#242D86' },
  { value:     82.3, color: '#252C87' },
  { value:     82.4, color: '#252C87' },
  { value:     82.5, color: '#252C87' },
  { value:     82.6, color: '#252C87' },
  { value:     82.7, color: '#252C87' },
  { value:     82.8, color: '#262B88' },
  { value:     82.9, color: '#262B88' },
  { value:       83, color: '#262B88' },
  { value:     83.1, color: '#262B88' },
  { value:     83.2, color: '#262B88' },
  { value:     83.3, color: '#262A88' },
  { value:     83.4, color: '#262A88' },
  { value:     83.5, color: '#262A88' },
  { value:     83.6, color: '#262A88' },
  { value:     83.7, color: '#262A88' },
  { value:     83.8, color: '#272989' },
  { value:     83.9, color: '#272989' },
  { value:       84, color: '#272989' },
  { value:     84.1, color: '#272989' },
  { value:     84.2, color: '#272989' },
  { value:     84.3, color: '#28288A' },
  { value:     84.4, color: '#28288A' },
  { value:     84.5, color: '#28288A' },
  { value:     84.6, color: '#28288A' },
  { value:     84.7, color: '#28278A' },
  { value:     84.8, color: '#29278A' },
  { value:     84.9, color: '#29268A' },
  { value:       85, color: '#29268A' },
  { value:     85.1, color: '#29268A' },
  { value:     85.2, color: '#29268A' },
  { value:     85.3, color: '#2A258B' },
  { value:     85.4, color: '#2A258B' },
  { value:     85.5, color: '#2A258B' },
  { value:     85.6, color: '#2A258B' },
  { value:     85.7, color: '#2A258B' },
  { value:     85.8, color: '#2B248C' },
  { value:     85.9, color: '#2B248C' },
  { value:       86, color: '#2B248C' },
  { value:     86.1, color: '#2B248C' },
  { value:     86.2, color: '#2B248C' },
  { value:     86.3, color: '#2C238D' },
  { value:     86.4, color: '#2C238D' },
  { value:     86.5, color: '#2C238D' },
  { value:     86.6, color: '#2C238D' },
  { value:     86.7, color: '#2C238D' },
  { value:     86.8, color: '#2C228E' },
  { value:     86.9, color: '#2C228E' },
  { value:       87, color: '#2C228E' },
  { value:     87.1, color: '#2C228E' },
  { value:     87.2, color: '#2C228E' },
  { value:     87.3, color: '#2D218E' },
  { value:     87.4, color: '#2D218E' },
  { value:     87.5, color: '#2D218E' },
  { value:     87.6, color: '#2D218E' },
  { value:     87.7, color: '#2D218E' },
  { value:     87.8, color: '#2E208F' },
  { value:     87.9, color: '#2E208F' },
  { value:       88, color: '#2E208F' },
  { value:     88.1, color: '#2E208F' },
  { value:     88.2, color: '#2E1F8F' },
  { value:     88.3, color: '#2E1F90' },
  { value:     88.4, color: '#2E1E90' },
  { value:     88.5, color: '#2E1E90' },
  { value:     88.6, color: '#2E1E90' },
  { value:     88.7, color: '#2E1E90' },
  { value:     88.8, color: '#2F1D90' },
  { value:     88.9, color: '#2F1D90' },
  { value:       89, color: '#2F1D90' },
  { value:     89.1, color: '#2F1D90' },
  { value:     89.2, color: '#2F1D90' },
  { value:     89.3, color: '#301C91' },
  { value:     89.4, color: '#301C91' },
  { value:     89.5, color: '#301C91' },
  { value:     89.6, color: '#301C91' },
  { value:     89.7, color: '#301C91' },
  { value:     89.8, color: '#311B92' },
  { value:     89.9, color: '#311B92' },
  { value:       90, color: '#311B92' },
  { value:     90.1, color: '#311B92' },
  { value:     90.2, color: '#311B92' },
  { value:     90.3, color: '#321B92' },
  { value:     90.4, color: '#321B92' },
  { value:     90.5, color: '#321B92' },
  { value:     90.6, color: '#321B92' },
  { value:     90.7, color: '#331B92' },
  { value:     90.8, color: '#331B92' },
  { value:     90.9, color: '#341B92' },
  { value:       91, color: '#341B92' },
  { value:     91.1, color: '#341B92' },
  { value:     91.2, color: '#341B92' },
  { value:     91.3, color: '#351B92' },
  { value:     91.4, color: '#351B92' },
  { value:     91.5, color: '#351B92' },
  { value:     91.6, color: '#351B92' },
  { value:     91.7, color: '#351B92' },
  { value:     91.8, color: '#361B93' },
  { value:     91.9, color: '#361B93' },
  { value:       92, color: '#361B93' },
  { value:     92.1, color: '#361B93' },
  { value:     92.2, color: '#361B93' },
  { value:     92.3, color: '#371B94' },
  { value:     92.4, color: '#371B94' },
  { value:     92.5, color: '#371B94' },
  { value:     92.6, color: '#371B94' },
  { value:     92.7, color: '#371B94' },
  { value:     92.8, color: '#381B94' },
  { value:     92.9, color: '#381B94' },
  { value:       93, color: '#381B94' },
  { value:     93.1, color: '#381B94' },
  { value:     93.2, color: '#391B94' },
  { value:     93.3, color: '#391B94' },
  { value:     93.4, color: '#3A1B94' },
  { value:     93.5, color: '#3A1B94' },
  { value:     93.6, color: '#3A1B94' },
  { value:     93.7, color: '#3A1B94' },
  { value:     93.8, color: '#3B1B94' },
  { value:     93.9, color: '#3B1B94' },
  { value:       94, color: '#3B1B94' },
  { value:     94.1, color: '#3B1B94' },
  { value:     94.2, color: '#3B1B94' },
  { value:     94.3, color: '#3C1C94' },
  { value:     94.4, color: '#3C1C94' },
  { value:     94.5, color: '#3C1C94' },
  { value:     94.6, color: '#3C1C94' },
  { value:     94.7, color: '#3D1C94' },
  { value:     94.8, color: '#3D1C94' },
  { value:     94.9, color: '#3E1C94' },
  { value:       95, color: '#3E1C94' },
  { value:     95.1, color: '#3E1C94' },
  { value:     95.2, color: '#3E1C94' },
  { value:     95.3, color: '#3F1C94' },
  { value:     95.4, color: '#3F1C94' },
  { value:     95.5, color: '#3F1C94' },
  { value:     95.6, color: '#3F1C94' },
  { value:     95.7, color: '#3F1C94' },
  { value:     95.8, color: '#401C95' },
  { value:     95.9, color: '#401C95' },
  { value:       96, color: '#401C95' },
  { value:     96.1, color: '#401C95' },
  { value:     96.2, color: '#401C95' },
  { value:     96.3, color: '#411C96' },
  { value:     96.4, color: '#411C96' },
  { value:     96.5, color: '#411C96' },
  { value:     96.6, color: '#411C96' },
  { value:     96.7, color: '#411C96' },
  { value:     96.8, color: '#421C96' },
  { value:     96.9, color: '#421C96' },
  { value:       97, color: '#421C96' },
  { value:     97.1, color: '#421C96' },
  { value:     97.2, color: '#431C96' },
  { value:     97.3, color: '#431C96' },
  { value:     97.4, color: '#441C96' },
  { value:     97.5, color: '#441C96' },
  { value:     97.6, color: '#441C96' },
  { value:     97.7, color: '#441C96' },
  { value:     97.8, color: '#451C96' },
  { value:     97.9, color: '#451C96' },
  { value:       98, color: '#451C96' },
  { value:     98.1, color: '#451C96' },
  { value:     98.2, color: '#451C96' },
  { value:     98.3, color: '#461C96' },
  { value:     98.4, color: '#461C96' },
  { value:     98.5, color: '#461C96' },
  { value:     98.6, color: '#461C96' },
  { value:     98.7, color: '#471C96' },
  { value:     98.8, color: '#471C96' },
  { value:     98.9, color: '#481C96' },
  { value:       99, color: '#481C96' },
  { value:     99.1, color: '#481C96' },
  { value:     99.2, color: '#481C96' },
  { value:     99.3, color: '#491C96' },
  { value:     99.4, color: '#491C96' },
  { value:     99.5, color: '#491C96' },
  { value:     99.6, color: '#491C96' },
  { value:     99.7, color: '#491C96' },
  { value:     99.8, color: '#4A1C97' },
  { value:     99.9, color: '#4A1C97' },
  { value:      100, color: '#4A1C97' },
  { value:    100.1, color: '#4A1C97' },
  { value:    100.2, color: '#4A1C97' },
  { value:    100.3, color: '#4B1C98' },
  { value:    100.4, color: '#4B1C98' },
  { value:    100.5, color: '#4B1C98' },
  { value:    100.6, color: '#4B1C98' },
  { value:    100.7, color: '#4B1C98' },
  { value:    100.8, color: '#4C1C98' },
  { value:    100.9, color: '#4C1C98' },
  { value:      101, color: '#4C1C98' },
  { value:    101.1, color: '#4C1C98' },
  { value:    101.2, color: '#4D1C98' },
  { value:    101.3, color: '#4D1C98' },
  { value:    101.4, color: '#4E1C98' },
  { value:    101.5, color: '#4E1C98' },
  { value:    101.6, color: '#4E1C98' },
  { value:    101.7, color: '#4E1C98' },
  { value:    101.8, color: '#4F1C98' },
  { value:    101.9, color: '#4F1C98' },
  { value:      102, color: '#4F1C98' },
  { value:    102.1, color: '#4F1C98' },
  { value:    102.2, color: '#4F1C98' },
  { value:    102.3, color: '#501C98' },
  { value:    102.4, color: '#501C98' },
  { value:    102.5, color: '#501C98' },
  { value:    102.6, color: '#501C98' },
  { value:    102.7, color: '#501C98' },
  { value:    102.8, color: '#511D99' },
  { value:    102.9, color: '#511D99' },
  { value:      103, color: '#511D99' },
  { value:    103.1, color: '#511D99' },
  { value:    103.2, color: '#511D99' },
  { value:    103.3, color: '#521D99' },
  { value:    103.4, color: '#521D99' },
  { value:    103.5, color: '#521D99' },
  { value:    103.6, color: '#521D99' },
  { value:    103.7, color: '#531D99' },
  { value:    103.8, color: '#531D99' },
  { value:    103.9, color: '#541D99' },
  { value:      104, color: '#541D99' },
  { value:    104.1, color: '#541D99' },
  { value:    104.2, color: '#541D99' },
  { value:    104.3, color: '#551D9A' },
  { value:    104.4, color: '#551D9A' },
  { value:    104.5, color: '#551D9A' },
  { value:    104.6, color: '#551D9A' },
  { value:    104.7, color: '#551D9A' },
  { value:    104.8, color: '#561D9A' },
  { value:    104.9, color: '#561D9A' },
  { value:      105, color: '#561D9A' },
  { value:    105.1, color: '#561D9A' },
  { value:    105.2, color: '#561D9A' },
  { value:    105.3, color: '#571D9A' },
  { value:    105.4, color: '#571D9A' },
  { value:    105.5, color: '#571D9A' },
  { value:    105.6, color: '#571D9A' },
  { value:    105.7, color: '#571D9A' },
  { value:    105.8, color: '#581D9B' },
  { value:    105.9, color: '#581D9B' },
  { value:      106, color: '#581D9B' },
  { value:    106.1, color: '#581D9B' },
  { value:    106.2, color: '#591D9B' },
  { value:    106.3, color: '#591D9B' },
  { value:    106.4, color: '#5A1D9B' },
  { value:    106.5, color: '#5A1D9B' },
  { value:    106.6, color: '#5A1D9B' },
  { value:    106.7, color: '#5A1D9B' },
  { value:    106.8, color: '#5B1D9B' },
  { value:    106.9, color: '#5B1D9B' },
  { value:      107, color: '#5B1D9B' },
  { value:    107.1, color: '#5B1D9B' },
  { value:    107.2, color: '#5B1D9B' },
  { value:    107.3, color: '#5C1E9C' },
  { value:    107.4, color: '#5C1E9C' },
  { value:    107.5, color: '#5C1E9C' },
  { value:    107.6, color: '#5C1E9C' },
  { value:    107.7, color: '#5C1E9C' },
  { value:    107.8, color: '#5D1E9C' },
  { value:    107.9, color: '#5D1E9C' },
  { value:      108, color: '#5D1E9C' },
  { value:    108.1, color: '#5D1E9C' },
  { value:    108.2, color: '#5D1E9C' },
  { value:    108.3, color: '#5E1E9C' },
  { value:    108.4, color: '#5E1E9C' },
  { value:    108.5, color: '#5E1E9C' },
  { value:    108.6, color: '#5E1E9C' },
  { value:    108.7, color: '#5F1E9C' },
  { value:    108.8, color: '#5F1E9C' },
  { value:    108.9, color: '#601E9C' },
  { value:      109, color: '#601E9C' },
  { value:    109.1, color: '#601E9C' },
  { value:    109.2, color: '#601E9C' },
  { value:    109.3, color: '#611E9C' },
  { value:    109.4, color: '#611E9C' },
  { value:    109.5, color: '#611E9C' },
  { value:    109.6, color: '#611E9C' },
  { value:    109.7, color: '#611E9C' },
  { value:    109.8, color: '#621E9D' },
  { value:    109.9, color: '#621E9D' },
  { value:      110, color: '#621E9D' },
  { value:    110.1, color: '#621E9D' },
  { value:    110.2, color: '#621E9D' },
  { value:    110.3, color: '#631E9E' },
  { value:    110.4, color: '#631E9E' },
  { value:    110.5, color: '#631E9E' },
  { value:    110.6, color: '#631E9E' },
  { value:    110.7, color: '#631E9E' },
  { value:    110.8, color: '#641E9E' },
  { value:    110.9, color: '#641E9E' },
  { value:      111, color: '#641E9E' },
  { value:    111.1, color: '#641E9E' },
  { value:    111.2, color: '#651E9E' },
  { value:    111.3, color: '#651E9E' },
  { value:    111.4, color: '#661E9E' },
  { value:    111.5, color: '#661E9E' },
  { value:    111.6, color: '#661E9E' },
  { value:    111.7, color: '#661E9E' },
  { value:    111.8, color: '#671E9E' },
  { value:    111.9, color: '#671E9E' },
  { value:      112, color: '#671E9E' },
  { value:    112.1, color: '#671E9E' },
  { value:    112.2, color: '#671E9E' },
  { value:    112.3, color: '#681E9E' },
  { value:    112.4, color: '#681E9E' },
  { value:    112.5, color: '#681E9E' },
  { value:    112.6, color: '#681E9E' },
  { value:    112.7, color: '#691E9E' },
  { value:    112.8, color: '#691E9E' },
  { value:    112.9, color: '#6A1E9E' },
  { value:      113, color: '#6A1E9E' },
  { value:    113.1, color: '#6A1E9E' },
  { value:    113.2, color: '#6A1E9E' },
  { value:    113.3, color: '#6B1E9E' },
  { value:    113.4, color: '#6B1E9E' },
  { value:    113.5, color: '#6B1E9E' },
  { value:    113.6, color: '#6B1E9E' },
  { value:    113.7, color: '#6B1E9E' },
  { value:    113.8, color: '#6C1E9F' },
  { value:    113.9, color: '#6C1E9F' },
  { value:      114, color: '#6C1E9F' },
  { value:    114.1, color: '#6C1E9F' },
  { value:    114.2, color: '#6C1E9F' },
  { value:    114.3, color: '#6D1EA0' },
  { value:    114.4, color: '#6D1EA0' },
  { value:    114.5, color: '#6D1EA0' },
  { value:    114.6, color: '#6D1EA0' },
  { value:    114.7, color: '#6D1EA0' },
  { value:    114.8, color: '#6E1EA0' },
  { value:    114.9, color: '#6E1EA0' },
  { value:      115, color: '#6E1EA0' },
  { value:    115.1, color: '#6E1EA0' },
  { value:    115.2, color: '#6F1EA0' },
  { value:    115.3, color: '#6F1EA0' },
  { value:    115.4, color: '#701EA0' },
  { value:    115.5, color: '#701EA0' },
  { value:    115.6, color: '#701EA0' },
  { value:    115.7, color: '#701EA0' },
  { value:    115.8, color: '#711FA0' },
  { value:    115.9, color: '#711FA0' },
  { value:      116, color: '#711FA0' },
  { value:    116.1, color: '#711FA0' },
  { value:    116.2, color: '#711FA0' },
  { value:    116.3, color: '#721FA0' },
  { value:    116.4, color: '#721FA0' },
  { value:    116.5, color: '#721FA0' },
  { value:    116.6, color: '#721FA0' },
  { value:    116.7, color: '#731FA0' },
  { value:    116.8, color: '#731FA0' },
  { value:    116.9, color: '#741FA0' },
  { value:      117, color: '#741FA0' },
  { value:    117.1, color: '#741FA0' },
  { value:    117.2, color: '#741FA0' },
  { value:    117.3, color: '#751FA0' },
  { value:    117.4, color: '#751FA0' },
  { value:    117.5, color: '#751FA0' },
  { value:    117.6, color: '#751FA0' },
  { value:    117.7, color: '#751FA0' },
  { value:    117.8, color: '#761FA1' },
  { value:    117.9, color: '#761FA1' },
  { value:      118, color: '#761FA1' },
  { value:    118.1, color: '#761FA1' },
  { value:    118.2, color: '#761FA1' },
  { value:    118.3, color: '#771FA2' },
  { value:    118.4, color: '#771FA2' },
  { value:    118.5, color: '#771FA2' },
  { value:    118.6, color: '#771FA2' },
  { value:    118.7, color: '#771FA2' },
  { value:    118.8, color: '#781FA2' },
  { value:    118.9, color: '#781FA2' },
  { value:      119, color: '#781FA2' },
  { value:    119.1, color: '#781FA2' },
  { value:    119.2, color: '#791FA2' },
  { value:    119.3, color: '#791FA2' },
  { value:    119.4, color: '#7A1FA2' },
  { value:    119.5, color: '#7A1FA2' },
  { value:    119.6, color: '#7A1FA2' },
  { value:    119.7, color: '#7A1FA2' },
  { value:    119.8, color: '#7B1FA2' },
  { value:    119.9, color: '#7B1FA2' },
  { value:      120, color: '#7B1FA2' },
  { value:    120.1, color: '#7B1FA2' },
  { value:    120.2, color: '#7C1FA2' },
  { value:    120.3, color: '#7C1EA1' },
  { value:    120.4, color: '#7D1EA1' },
  { value:    120.5, color: '#7D1EA1' },
  { value:    120.6, color: '#7D1EA1' },
  { value:    120.7, color: '#7E1EA1' },
  { value:    120.8, color: '#7E1EA0' },
  { value:    120.9, color: '#7F1EA0' },
  { value:      121, color: '#7F1EA0' },
  { value:    121.1, color: '#7F1EA0' },
  { value:    121.2, color: '#801E9F' },
  { value:    121.3, color: '#801E9F' },
  { value:    121.4, color: '#811E9E' },
  { value:    121.5, color: '#811E9E' },
  { value:    121.6, color: '#811E9E' },
  { value:    121.7, color: '#821E9E' },
  { value:    121.8, color: '#821D9D' },
  { value:    121.9, color: '#831D9D' },
  { value:      122, color: '#831D9D' },
  { value:    122.1, color: '#831D9D' },
  { value:    122.2, color: '#841D9D' },
  { value:    122.3, color: '#841C9C' },
  { value:    122.4, color: '#851C9C' },
  { value:    122.5, color: '#851C9C' },
  { value:    122.6, color: '#851C9C' },
  { value:    122.7, color: '#861C9B' },
  { value:    122.8, color: '#861C9B' },
  { value:    122.9, color: '#871C9A' },
  { value:      123, color: '#871C9A' },
  { value:    123.1, color: '#871C9A' },
  { value:    123.2, color: '#881C9A' },
  { value:    123.3, color: '#881C99' },
  { value:    123.4, color: '#891C99' },
  { value:    123.5, color: '#891C99' },
  { value:    123.6, color: '#891C99' },
  { value:    123.7, color: '#8A1C99' },
  { value:    123.8, color: '#8A1B98' },
  { value:    123.9, color: '#8B1B98' },
  { value:      124, color: '#8B1B98' },
  { value:    124.1, color: '#8C1B98' },
  { value:    124.2, color: '#8C1B98' },
  { value:    124.3, color: '#8D1A97' },
  { value:    124.4, color: '#8D1A97' },
  { value:    124.5, color: '#8E1A97' },
  { value:    124.6, color: '#8E1A97' },
  { value:    124.7, color: '#8F1A97' },
  { value:    124.8, color: '#8F1A96' },
  { value:    124.9, color: '#901A96' },
  { value:      125, color: '#901A96' },
  { value:    125.1, color: '#901A96' },
  { value:    125.2, color: '#911A95' },
  { value:    125.3, color: '#911A95' },
  { value:    125.4, color: '#921A94' },
  { value:    125.5, color: '#921A94' },
  { value:    125.6, color: '#921A94' },
  { value:    125.7, color: '#931A94' },
  { value:    125.8, color: '#931993' },
  { value:    125.9, color: '#941993' },
  { value:      126, color: '#941993' },
  { value:    126.1, color: '#941993' },
  { value:    126.2, color: '#951993' },
  { value:    126.3, color: '#951892' },
  { value:    126.4, color: '#961892' },
  { value:    126.5, color: '#961892' },
  { value:    126.6, color: '#961892' },
  { value:    126.7, color: '#971891' },
  { value:    126.8, color: '#971891' },
  { value:    126.9, color: '#981890' },
  { value:      127, color: '#981890' },
  { value:    127.1, color: '#981890' },
  { value:    127.2, color: '#991890' },
  { value:    127.3, color: '#99188F' },
  { value:    127.4, color: '#9A188F' },
  { value:    127.5, color: '#9A188F' },
  { value:    127.6, color: '#9A188F' },
  { value:    127.7, color: '#9B188F' },
  { value:    127.8, color: '#9B178E' },
  { value:    127.9, color: '#9C178E' },
  { value:      128, color: '#9C178E' },
  { value:    128.1, color: '#9C178E' },
  { value:    128.2, color: '#9D178E' },
  { value:    128.3, color: '#9D168D' },
  { value:    128.4, color: '#9E168D' },
  { value:    128.5, color: '#9E168D' },
  { value:    128.6, color: '#9E168D' },
  { value:    128.7, color: '#9F168D' },
  { value:    128.8, color: '#9F168C' },
  { value:    128.9, color: '#A0168C' },
  { value:      129, color: '#A0168C' },
  { value:    129.1, color: '#A0168C' },
  { value:    129.2, color: '#A1168B' },
  { value:    129.3, color: '#A1168B' },
  { value:    129.4, color: '#A2168A' },
  { value:    129.5, color: '#A2168A' },
  { value:    129.6, color: '#A2168A' },
  { value:    129.7, color: '#A3168A' },
  { value:    129.8, color: '#A31589' },
  { value:    129.9, color: '#A41589' },
  { value:      130, color: '#A41589' },
  { value:    130.1, color: '#A41589' },
  { value:    130.2, color: '#A51589' },
  { value:    130.3, color: '#A51488' },
  { value:    130.4, color: '#A61488' },
  { value:    130.5, color: '#A61488' },
  { value:    130.6, color: '#A61488' },
  { value:    130.7, color: '#A71487' },
  { value:    130.8, color: '#A71487' },
  { value:    130.9, color: '#A81486' },
  { value:      131, color: '#A81486' },
  { value:    131.1, color: '#A81486' },
  { value:    131.2, color: '#A91486' },
  { value:    131.3, color: '#A91485' },
  { value:    131.4, color: '#AA1485' },
  { value:    131.5, color: '#AA1485' },
  { value:    131.6, color: '#AA1485' },
  { value:    131.7, color: '#AB1485' },
  { value:    131.8, color: '#AB1384' },
  { value:    131.9, color: '#AC1384' },
  { value:      132, color: '#AC1384' },
  { value:    132.1, color: '#AC1384' },
  { value:    132.2, color: '#AD1384' },
  { value:    132.3, color: '#AD1283' },
  { value:    132.4, color: '#AE1283' },
  { value:    132.5, color: '#AE1283' },
  { value:    132.6, color: '#AE1283' },
  { value:    132.7, color: '#AF1283' },
  { value:    132.8, color: '#AF1282' },
  { value:    132.9, color: '#B01282' },
  { value:      133, color: '#B01282' },
  { value:    133.1, color: '#B01282' },
  { value:    133.2, color: '#B11281' },
  { value:    133.3, color: '#B11281' },
  { value:    133.4, color: '#B21280' },
  { value:    133.5, color: '#B21280' },
  { value:    133.6, color: '#B21280' },
  { value:    133.7, color: '#B31280' },
  { value:    133.8, color: '#B3117F' },
  { value:    133.9, color: '#B4117F' },
  { value:      134, color: '#B4117F' },
  { value:    134.1, color: '#B4117F' },
  { value:    134.2, color: '#B5117F' },
  { value:    134.3, color: '#B5107E' },
  { value:    134.4, color: '#B6107E' },
  { value:    134.5, color: '#B6107E' },
  { value:    134.6, color: '#B6107E' },
  { value:    134.7, color: '#B7107D' },
  { value:    134.8, color: '#B7107D' },
  { value:    134.9, color: '#B8107C' },
  { value:      135, color: '#B8107C' },
  { value:    135.1, color: '#B8107C' },
  { value:    135.2, color: '#B9107C' },
  { value:    135.3, color: '#B90F7B' },
  { value:    135.4, color: '#BA0F7B' },
  { value:    135.5, color: '#BA0F7B' },
  { value:    135.6, color: '#BA0F7B' },
  { value:    135.7, color: '#BB0F7B' },
  { value:    135.8, color: '#BB0E7A' },
  { value:    135.9, color: '#BC0E7A' },
  { value:      136, color: '#BC0E7A' },
  { value:    136.1, color: '#BC0E7A' },
  { value:    136.2, color: '#BD0E7A' },
  { value:    136.3, color: '#BD0E79' },
  { value:    136.4, color: '#BE0E79' },
  { value:    136.5, color: '#BE0E79' },
  { value:    136.6, color: '#BE0E79' },
  { value:    136.7, color: '#BF0E79' },
  { value:    136.8, color: '#BF0D78' },
  { value:    136.9, color: '#C00D78' },
  { value:      137, color: '#C00D78' },
  { value:    137.1, color: '#C00D78' },
  { value:    137.2, color: '#C10D77' },
  { value:    137.3, color: '#C10C77' },
  { value:    137.4, color: '#C20C76' },
  { value:    137.5, color: '#C20C76' },
  { value:    137.6, color: '#C20C76' },
  { value:    137.7, color: '#C30C76' },
  { value:    137.8, color: '#C30C75' },
  { value:    137.9, color: '#C40C75' },
  { value:      138, color: '#C40C75' },
  { value:    138.1, color: '#C40C75' },
  { value:    138.2, color: '#C50C75' },
  { value:    138.3, color: '#C50C74' },
  { value:    138.4, color: '#C60C74' },
  { value:    138.5, color: '#C60C74' },
  { value:    138.6, color: '#C60C74' },
  { value:    138.7, color: '#C70C73' },
  { value:    138.8, color: '#C70B73' },
  { value:    138.9, color: '#C80B72' },
  { value:      139, color: '#C80B72' },
  { value:    139.1, color: '#C80B72' },
  { value:    139.2, color: '#C90B72' },
  { value:    139.3, color: '#C90A71' },
  { value:    139.4, color: '#CA0A71' },
  { value:    139.5, color: '#CA0A71' },
  { value:    139.6, color: '#CA0A71' },
  { value:    139.7, color: '#CB0A71' },
  { value:    139.8, color: '#CB0A70' },
  { value:    139.9, color: '#CC0A70' },
  { value:      140, color: '#CC0A70' },
  { value:    140.1, color: '#CC0A70' },
  { value:    140.2, color: '#CD0A70' },
  { value:    140.3, color: '#CD0A6F' },
  { value:    140.4, color: '#CE0A6F' },
  { value:    140.5, color: '#CE0A6F' },
  { value:    140.6, color: '#CE0A6F' },
  { value:    140.7, color: '#CF0A6F' },
  { value:    140.8, color: '#CF096E' },
  { value:    140.9, color: '#D0096E' },
  { value:      141, color: '#D0096E' },
  { value:    141.1, color: '#D0096E' },
  { value:    141.2, color: '#D1096D' },
  { value:    141.3, color: '#D1086D' },
  { value:    141.4, color: '#D2086C' },
  { value:    141.5, color: '#D2086C' },
  { value:    141.6, color: '#D2086C' },
  { value:    141.7, color: '#D3086C' },
  { value:    141.8, color: '#D3086B' },
  { value:    141.9, color: '#D4086B' },
  { value:      142, color: '#D4086B' },
  { value:    142.1, color: '#D4086B' },
  { value:    142.2, color: '#D5086B' },
  { value:    142.3, color: '#D5086A' },
  { value:    142.4, color: '#D6086A' },
  { value:    142.5, color: '#D6086A' },
  { value:    142.6, color: '#D6086A' },
  { value:    142.7, color: '#D70869' },
  { value:    142.8, color: '#D70769' },
  { value:    142.9, color: '#D80768' },
  { value:      143, color: '#D80768' },
  { value:    143.1, color: '#D80768' },
  { value:    143.2, color: '#D90768' },
  { value:    143.3, color: '#D90667' },
  { value:    143.4, color: '#DA0667' },
  { value:    143.5, color: '#DA0667' },
  { value:    143.6, color: '#DA0667' },
  { value:    143.7, color: '#DB0667' },
  { value:    143.8, color: '#DB0666' },
  { value:    143.9, color: '#DC0666' },
  { value:      144, color: '#DC0666' },
  { value:    144.1, color: '#DC0666' },
  { value:    144.2, color: '#DD0666' },
  { value:    144.3, color: '#DD0665' },
  { value:    144.4, color: '#DE0665' },
  { value:    144.5, color: '#DE0665' },
  { value:    144.6, color: '#DE0665' },
  { value:    144.7, color: '#DF0665' },
  { value:    144.8, color: '#DF0564' },
  { value:    144.9, color: '#E00564' },
  { value:      145, color: '#E00564' },
  { value:    145.1, color: '#E00564' },
  { value:    145.2, color: '#E10563' },
  { value:    145.3, color: '#E10463' },
  { value:    145.4, color: '#E20462' },
  { value:    145.5, color: '#E20462' },
  { value:    145.6, color: '#E30462' },
  { value:    145.7, color: '#E30462' },
  { value:    145.8, color: '#E40461' },
  { value:    145.9, color: '#E40461' },
  { value:      146, color: '#E50461' },
  { value:    146.1, color: '#E50461' },
  { value:    146.2, color: '#E60461' },
  { value:    146.3, color: '#E60460' },
  { value:    146.4, color: '#E70460' },
  { value:    146.5, color: '#E70460' },
  { value:    146.6, color: '#E70460' },
  { value:    146.7, color: '#E8045F' },
  { value:    146.8, color: '#E8035F' },
  { value:    146.9, color: '#E9035E' },
  { value:      147, color: '#E9035E' },
  { value:    147.1, color: '#E9035E' },
  { value:    147.2, color: '#EA035E' },
  { value:    147.3, color: '#EA025D' },
  { value:    147.4, color: '#EB025D' },
  { value:    147.5, color: '#EB025D' },
  { value:    147.6, color: '#EB025D' },
  { value:    147.7, color: '#EC025D' },
  { value:    147.8, color: '#EC025C' },
  { value:    147.9, color: '#ED025C' },
  { value:      148, color: '#ED025C' },
  { value:    148.1, color: '#ED025C' },
  { value:    148.2, color: '#EE025C' },
  { value:    148.3, color: '#EE025B' },
  { value:    148.4, color: '#EF025B' },
  { value:    148.5, color: '#EF025B' },
  { value:    148.6, color: '#EF025B' },
  { value:    148.7, color: '#F0025B' },
  { value:    148.8, color: '#F0015A' },
  { value:    148.9, color: '#F1015A' },
  { value:      149, color: '#F1015A' },
  { value:    149.1, color: '#F1015A' },
  { value:    149.2, color: '#F20159' },
  { value:    149.3, color: '#F20059' },
  { value:    149.4, color: '#F30058' },
  { value:    149.5, color: '#F30058' },
  { value:    149.6, color: '#F30058' },
  { value:    149.7, color: '#F40058' },
  { value:    149.8, color: '#F40057' },
  { value:    149.9, color: '#F50057' },
  { value:      150, color: '#F50057' },
  ],
  // ── ETc: 0.0 → 15.0 mm/day, step 0.1 (151 stops) ──────────────────────────
  etc: [
  // ETc  0.0→15.0 step 0.1  (151 stops)
  { value:        0, color: '#EDE7F6' },
  { value:      0.1, color: '#E9E2F4' },
  { value:      0.2, color: '#E5DDF2' },
  { value:      0.3, color: '#E2D9F1' },
  { value:      0.4, color: '#DED4EF' },
  { value:      0.5, color: '#DACFED' },
  { value:      0.6, color: '#D6CAEB' },
  { value:      0.7, color: '#D3C5EA' },
  { value:      0.8, color: '#CFC1E8' },
  { value:      0.9, color: '#CCBCE7' },
  { value:        1, color: '#C8B7E5' },
  { value:      1.1, color: '#C4B2E3' },
  { value:      1.2, color: '#C1ADE1' },
  { value:      1.3, color: '#BDA9E0' },
  { value:      1.4, color: '#BAA4DE' },
  { value:      1.5, color: '#B69FDC' },
  { value:      1.6, color: '#B29ADA' },
  { value:      1.7, color: '#AE95D8' },
  { value:      1.8, color: '#AB91D7' },
  { value:      1.9, color: '#A78CD5' },
  { value:        2, color: '#A387D3' },
  { value:      2.1, color: '#9F82D1' },
  { value:      2.2, color: '#9B7DD0' },
  { value:      2.3, color: '#9879CE' },
  { value:      2.4, color: '#9474CD' },
  { value:      2.5, color: '#906FCB' },
  { value:      2.6, color: '#8C6AC9' },
  { value:      2.7, color: '#8965C7' },
  { value:      2.8, color: '#8561C6' },
  { value:      2.9, color: '#825CC4' },
  { value:        3, color: '#7E57C2' },
  { value:      3.1, color: '#7A57C2' },
  { value:      3.2, color: '#7758C2' },
  { value:      3.3, color: '#7358C2' },
  { value:      3.4, color: '#7059C2' },
  { value:      3.5, color: '#6C59C2' },
  { value:      3.6, color: '#695AC2' },
  { value:      3.7, color: '#655AC2' },
  { value:      3.8, color: '#625BC1' },
  { value:      3.9, color: '#5E5BC1' },
  { value:        4, color: '#5B5CC1' },
  { value:      4.1, color: '#585CC1' },
  { value:      4.2, color: '#545DC1' },
  { value:      4.3, color: '#515DC1' },
  { value:      4.4, color: '#4D5EC1' },
  { value:      4.5, color: '#4A5EC1' },
  { value:      4.6, color: '#465EC1' },
  { value:      4.7, color: '#435FC1' },
  { value:      4.8, color: '#3F5FC1' },
  { value:      4.9, color: '#3C60C1' },
  { value:        5, color: '#3860C1' },
  { value:      5.1, color: '#3461C1' },
  { value:      5.2, color: '#3161C1' },
  { value:      5.3, color: '#2D62C0' },
  { value:      5.4, color: '#2A62C0' },
  { value:      5.5, color: '#2663C0' },
  { value:      5.6, color: '#2363C0' },
  { value:      5.7, color: '#1F64C0' },
  { value:      5.8, color: '#1C64C0' },
  { value:      5.9, color: '#1865C0' },
  { value:        6, color: '#1565C0' },
  { value:      6.1, color: '#1466BE' },
  { value:      6.2, color: '#1467BD' },
  { value:      6.3, color: '#1368BB' },
  { value:      6.4, color: '#1369BA' },
  { value:      6.5, color: '#126AB8' },
  { value:      6.6, color: '#116BB6' },
  { value:      6.7, color: '#106CB5' },
  { value:      6.8, color: '#106DB3' },
  { value:      6.9, color: '#0F6EB2' },
  { value:        7, color: '#0E6FB0' },
  { value:      7.1, color: '#0D70AE' },
  { value:      7.2, color: '#0C71AD' },
  { value:      7.3, color: '#0C72AB' },
  { value:      7.4, color: '#0B73AA' },
  { value:      7.5, color: '#0A74A8' },
  { value:      7.6, color: '#0975A6' },
  { value:      7.7, color: '#0976A4' },
  { value:      7.8, color: '#0877A3' },
  { value:      7.9, color: '#0878A1' },
  { value:        8, color: '#07799F' },
  { value:      8.1, color: '#067A9D' },
  { value:      8.2, color: '#067B9C' },
  { value:      8.3, color: '#057C9A' },
  { value:      8.4, color: '#057D99' },
  { value:      8.5, color: '#047E97' },
  { value:      8.6, color: '#037F95' },
  { value:      8.7, color: '#028094' },
  { value:      8.8, color: '#028192' },
  { value:      8.9, color: '#018291' },
  { value:        9, color: '#00838F' },
  { value:      9.1, color: '#008693' },
  { value:      9.2, color: '#008997' },
  { value:      9.3, color: '#008D9A' },
  { value:      9.4, color: '#00909E' },
  { value:      9.5, color: '#0093A2' },
  { value:      9.6, color: '#0096A6' },
  { value:      9.7, color: '#009AA9' },
  { value:      9.8, color: '#009DAD' },
  { value:      9.9, color: '#00A1B0' },
  { value:       10, color: '#00A4B4' },
  { value:     10.1, color: '#00A7B8' },
  { value:     10.2, color: '#00AABC' },
  { value:     10.3, color: '#00AEBF' },
  { value:     10.4, color: '#00B1C3' },
  { value:     10.5, color: '#00B4C7' },
  { value:     10.6, color: '#00B7CB' },
  { value:     10.7, color: '#00BACF' },
  { value:     10.8, color: '#00BED2' },
  { value:     10.9, color: '#00C1D6' },
  { value:       11, color: '#00C4DA' },
  { value:     11.1, color: '#00C7DE' },
  { value:     11.2, color: '#00CBE1' },
  { value:     11.3, color: '#00CEE5' },
  { value:     11.4, color: '#00D2E8' },
  { value:     11.5, color: '#00D5EC' },
  { value:     11.6, color: '#00D8F0' },
  { value:     11.7, color: '#00DBF4' },
  { value:     11.8, color: '#00DFF7' },
  { value:     11.9, color: '#00E2FB' },
  { value:       12, color: '#00E5FF' },
  { value:     12.1, color: '#04E5FC' },
  { value:     12.2, color: '#07E6FA' },
  { value:     12.3, color: '#0BE6F7' },
  { value:     12.4, color: '#0EE7F5' },
  { value:     12.5, color: '#12E7F2' },
  { value:     12.6, color: '#15E7EF' },
  { value:     12.7, color: '#19E8EC' },
  { value:     12.8, color: '#1CE8EA' },
  { value:     12.9, color: '#20E9E7' },
  { value:       13, color: '#23E9E4' },
  { value:     13.1, color: '#26E9E1' },
  { value:     13.2, color: '#2AE9DE' },
  { value:     13.3, color: '#2DEADC' },
  { value:     13.4, color: '#31EAD9' },
  { value:     13.5, color: '#34EAD6' },
  { value:     13.6, color: '#38EAD3' },
  { value:     13.7, color: '#3BEBD1' },
  { value:     13.8, color: '#3FEBCE' },
  { value:     13.9, color: '#42ECCC' },
  { value:       14, color: '#46ECC9' },
  { value:     14.1, color: '#4AECC6' },
  { value:     14.2, color: '#4DEDC4' },
  { value:     14.3, color: '#51EDC1' },
  { value:     14.4, color: '#54EEBF' },
  { value:     14.5, color: '#58EEBC' },
  { value:     14.6, color: '#5BEEB9' },
  { value:     14.7, color: '#5FEFB6' },
  { value:     14.8, color: '#62EFB4' },
  { value:     14.9, color: '#66F0B1' },
  { value:       15, color: '#69F0AE' },
  ],
}
// Computed active layers based on props
const activeLayers = computed(() => {
  return Object.keys(props.layers)
    .filter(key => props.layers[key])
    .map(key => layerConfigs[key])
})

// Get color for a specific value; pass isCumulative=true for CWR/IWR forecast totals
function getColorForValue(layerName, value, isCumulative = false) {
  if (value === undefined || value === null) return '#808080'
  const colorMap = colorMaps[layerName]
  if (!colorMap) return '#808080'
  let closest = colorMap[0]
  let minDiff = Math.abs(value - closest.value)
  for (let i = 1; i < colorMap.length; i++) {
    const diff = Math.abs(value - colorMap[i].value)
    if (diff < minDiff) { minDiff = diff; closest = colorMap[i] }
  }
  return closest.color
}

// Get style object for value display
function getValueStyle(layerName, value, isCumulative = false) {
  const bgColor = getColorForValue(layerName, value, isCumulative)
  const textColor = getTextColor(bgColor)
  return {
    backgroundColor: bgColor,
    padding: '4px 8px',
    borderRadius: '4px',
    fontWeight: 'bold',
    color: textColor,
    display: 'inline-block',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
  }
}

// Determine text color based on background luminance
function getTextColor(hexColor) {
  const r = parseInt(hexColor.slice(1, 3), 16)
  const g = parseInt(hexColor.slice(3, 5), 16)
  const b = parseInt(hexColor.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.5 ? '#000000' : '#ffffff'
}

// Format number
function format(val) {
  return typeof val === 'number' ? val.toFixed(3) : "-"
}

// Select forecast window for Kc layer
function selectForecastWindow(window) {
  selectedWindow.value = selectedWindow.value === window ? null : window
}

// Select map style
function selectMapStyle(styleName) {
  if (currentMapStyle.value === styleName) return
  currentMapStyle.value = styleName
  changeMapStyle(styleName)
}

// Change map base style
function changeMapStyle(styleName) {
  if (!map) return
  const style = mapStyles.find(s => s.name === styleName)
  if (!style) return

  if (basemapTransitionFrame) {
    cancelAnimationFrame(basemapTransitionFrame)
    basemapTransitionFrame = null
  }

  if (retiringBaseLayer && map.hasLayer(retiringBaseLayer)) {
    map.removeLayer(retiringBaseLayer)
  }
  retiringBaseLayer = baseLayer && map.hasLayer(baseLayer) ? baseLayer : null
  if (retiringBaseLayer) retiringBaseLayer.setOpacity(1)

  const nextBaseLayer = L.tileLayer(style.url, {
    attribution: style.attribution,
    maxZoom: MAP_MAX_ZOOM,
    maxNativeZoom: 19
  })
  nextBaseLayer.setOpacity(retiringBaseLayer ? 0 : 1)
  nextBaseLayer.addTo(map)
  baseLayer = nextBaseLayer

  if (boundaryLayer) {
    boundaryLayer.bringToFront()
  }

  Object.keys(wmsLayers).forEach(key => {
    if (props.layers[key] && map.hasLayer(wmsLayers[key])) {
      wmsLayers[key].bringToFront()
    }
  })

  if (!retiringBaseLayer) return

  const duration = 240
  const start = performance.now()
  const fadeBaseLayer = (now) => {
    const progress = Math.min((now - start) / duration, 1)
    nextBaseLayer.setOpacity(progress)

    if (progress < 1) {
      basemapTransitionFrame = requestAnimationFrame(fadeBaseLayer)
      return
    }

    if (retiringBaseLayer && map.hasLayer(retiringBaseLayer)) {
      map.removeLayer(retiringBaseLayer)
    }
    retiringBaseLayer = null
    basemapTransitionFrame = null
  }
  basemapTransitionFrame = requestAnimationFrame(fadeBaseLayer)
}

// Load boundary
async function loadBoundary() {
  try {
    const res = await fetch(`${API_BASE}/api/boundary`)
    const data = await res.json()

    if (boundaryLayer) {
      map.removeLayer(boundaryLayer)
    }

    boundaryLayer = L.geoJSON(data.geojson, {
      style: {
        color: '#19c7a6',
        weight: 2.5,
        fill: false,
        opacity: 0.9,
        dashArray: '7, 5'
      }
    }).addTo(map)

    const bounds = boundaryLayer.getBounds()
    const paddedBounds = bounds.pad(MAP_BOUNDARY_PADDING)
    const fitZoom = map.getBoundsZoom(bounds, false, L.point(40, 40))
    map.setMinZoom(Math.min(MAP_MIN_ZOOM, fitZoom))
    map.setMaxZoom(MAP_MAX_ZOOM)
    map.setMaxBounds(paddedBounds)
    map.options.maxBoundsViscosity = 1.0
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: MAP_MAX_ZOOM - 1 })
    boundaryLoaded.value = true
  } catch (err) {
    console.error("Boundary load failed:", err)
  }
}

// Unit label per layer. Observed CWR/IWR are daily rates; forecast windows are totals.
function layerUnit(name, kind = 'today') {
  if (kind === 'forecast') {
    return { cwr: 'mm', iwr: 'mm' }[name] ?? ''
  }
  return { savi: '', kc: '', cwr: 'mm/day', iwr: 'mm/day', etc: 'mm/day' }[name] ?? ''
}

function formatPopupValue(value, unit = '') {
  const numeric = Number(value)
  if (value == null || !Number.isFinite(numeric)) return '--'
  const suffix = unit ? ` ${unit}` : ''
  return `${numeric.toFixed(3)}${suffix}`
}

function getPopupForecastValue(layerName, windowKey, data) {
  if (!FORECAST_POPUP_LAYERS.has(layerName)) return null
  if (!data?.forecast) return null
  return data.forecast?.[layerName]?.[windowKey] ?? null
}

const unifiedPopupData = computed(() => unifiedPopupPinned.value ? pointData.value : hoverPointData.value)

const unifiedPopupDate = computed(() => {
  const data = unifiedPopupData.value
  return data?.acquisition_date || slotToDateMap.value[props.slot] || ''
})

const unifiedPopupRows = computed(() => {
  const data = unifiedPopupData.value
  if (!data) return []

  return activeLayers.value
    .map(layer => {
      const todayUnit = layerUnit(layer.name)
      const forecastUnit = layerUnit(layer.name, 'forecast')
      const forecastAllowed = FORECAST_POPUP_LAYERS.has(layer.name)
      return {
        layer: layer.name,
        label: layer.displayName,
        forecastAllowed,
        today: formatPopupValue(data.values?.[layer.name], todayUnit),
        five: forecastAllowed ? formatPopupValue(getPopupForecastValue(layer.name, '5day', data), forecastUnit) : '',
        ten: forecastAllowed ? formatPopupValue(getPopupForecastValue(layer.name, '10day', data), forecastUnit) : '',
        fifteen: forecastAllowed ? formatPopupValue(getPopupForecastValue(layer.name, '15day', data), forecastUnit) : '',
      }
    })
    .filter(row => row.today !== '--' || (row.forecastAllowed && [row.five, row.ten, row.fifteen].some(value => value !== '--')))
})

const showForecastPopupColumns = computed(() => {
  return unifiedPopupRows.value.some(row => row.forecastAllowed)
})

const showUnifiedPixelPopup = computed(() => {
  if (unifiedPopupPinned.value) return true
  return Boolean(hoverPointData.value && unifiedPopupRows.value.length > 0)
})

function closeUnifiedPixelPopup() {
  unifiedPopupPinned.value = false
  unifiedPopupLoading.value = false
}

function clampUnifiedPopupPosition(point, { pinned = false } = {}) {
  const { x, y } = point
  const rect = mapEl.value?.getBoundingClientRect()
  if (!rect) return { x, y }

  const margin = 14
  const width = Math.min(480, Math.max(280, rect.width - margin * 2))
  const estimatedHeight = showForecastPopupColumns.value ? 230 : 170

  if (pinned) {
    return {
      x: clamp(x, margin + width / 2, Math.max(margin + width / 2, rect.width - margin - width / 2)),
      y: clamp(y, margin + estimatedHeight, Math.max(margin + estimatedHeight, rect.height - margin)),
    }
  }

  return {
    x: clamp(x, margin, Math.max(margin, rect.width - width - margin - 12)),
    y: clamp(y, margin, Math.max(margin, rect.height - estimatedHeight - margin - 12)),
  }
}

// Check if point is within boundary
function isPointInBoundary(lat, lon) {
  if (!boundaryLayer) return false
  const bounds = boundaryLayer.getBounds()
  return bounds.contains([lat, lon])
}

// Get current location and show info panel
async function getCurrentLocation() {
  if (!navigator.geolocation) {
    alert('Geolocation is not supported by your browser')
    return
  }

  isLocating.value = true
  locationError.value = null

  if (userLocationMarker) {
    map.removeLayer(userLocationMarker)
    userLocationMarker = null
  }

  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      })
    })

    const { latitude, longitude } = position.coords
    
    if (!isPointInBoundary(latitude, longitude)) {
      alert('Your location is outside the study area boundary')
      return
    }

    await fetchPointData(latitude, longitude)
    map.flyTo([latitude, longitude], 12, { duration: 1.5 })
    emit('location-selected', { lat: latitude, lon: longitude })

    userLocationMarker = L.marker([latitude, longitude], {
      icon: L.divIcon({
        className: 'blue-dot-marker',
        html: '<div class="blue-dot"></div><div class="pulse-ring"></div>',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
      })
    }).addTo(map).bindPopup('Your current location').openPopup()

    setTimeout(() => {
      if (userLocationMarker && map.hasLayer(userLocationMarker)) {
        map.removeLayer(userLocationMarker)
        userLocationMarker = null
      }
    }, 8000)

  } catch (error) {
    console.error('Error getting location:', error)
    locationError.value = error.message
    
    let errorMessage = 'Unable to get your location. '
    switch(error.code) {
      case error.PERMISSION_DENIED:
        errorMessage += 'Please enable location access.'
        break
      case error.POSITION_UNAVAILABLE:
        errorMessage += 'Location information is unavailable.'
        break
      case error.TIMEOUT:
        errorMessage += 'Location request timed out.'
        break
      default:
        errorMessage += 'An unknown error occurred.'
    }
    alert(errorMessage)
  } finally {
    isLocating.value = false
  }
}

// Handle map click
async function onMapClick(e) {
  const clickId = ++mapClickRequestId
  const { lat, lng } = e.latlng

  unifiedPopupPinned.value = true
  bringWidgetToFront('popup')
  unifiedPopupLoading.value = true
  hoverPointData.value = null
  if (e.containerPoint) {
    unifiedPopupPosition.value = clampUnifiedPopupPosition({
      x: e.containerPoint.x + 14,
      y: e.containerPoint.y + 14,
    }, { pinned: true })
  }
 
  // ── Fetch exact backend raster pixel, then graph that pixel center ─────
  const selectedPoint = await fetchPointData(lat, lng)
  if (clickId !== mapClickRequestId) return
  unifiedPopupLoading.value = false
  emit('location-selected', { lat, lon: lng })
  if (selectedPoint?.lat && selectedPoint?.lon) {
    updateSelectedPixelMarker(selectedPoint.lat, selectedPoint.lon)
    fetchPixelTimeSeries(selectedPoint.lat, selectedPoint.lon, { pixelId: selectedPoint.pixelId })
  } else {
    updateSelectedPixelMarker(lat, lng)
    fetchPixelTimeSeries(lat, lng)
  }
 
  // ── Show info panel for new point ────────────────────────
  showInfoPanel.value = true
 
  if (!selectedPoint && clickId === mapClickRequestId) {
    unifiedPopupLoading.value = false
  }
}

function activeHoverLayer() {
  const preferred = props.selectedLayer && props.layers[props.selectedLayer]
    ? layerConfigs[props.selectedLayer]
    : null
  return preferred || activeLayers.value[0] || null
}

function setHoverValueFromPoint(data) {
  const layer = activeHoverLayer()
  const hasActiveValue = Boolean(layer && data?.values?.[layer.name] != null)
  const hasAnyActiveData = activeLayers.value.some(activeLayer => {
    if (data?.values?.[activeLayer.name] != null) return true
    return ['5day', '10day', '15day'].some(windowKey => getPopupForecastValue(activeLayer.name, windowKey, data) != null)
  })

  if (!hasActiveValue && !hasAnyActiveData) {
    hoverPointData.value = null
    return
  }
  hoverPointData.value = data
}

async function fetchHoverPointValue(lat, lon) {
  if (unifiedPopupPinned.value) return
  const layer = activeHoverLayer()
  if (!layer) {
    hoverPointData.value = null
    return
  }

  const requestId = ++hoverPointRequestId
  if (hoverPointController) {
    hoverPointController.abort()
  }
  const controller = new AbortController()
  hoverPointController = controller

  try {
    const data = await requestPointData(lat, lon, { signal: controller.signal })
    if (requestId === hoverPointRequestId) {
      setHoverValueFromPoint(data)
    }
  } catch (error) {
    if (error.name !== 'AbortError' && requestId === hoverPointRequestId) {
      hoverPointData.value = null
    }
  } finally {
    if (hoverPointController === controller) {
      hoverPointController = null
    }
  }
}

function scheduleHoverFetch(lat, lng) {
  if (unifiedPopupPinned.value) return
  pendingHoverPoint = { lat, lng }
  const elapsed = performance.now() - lastHoverFetchAt
  const delay = Math.max(0, HOVER_FETCH_INTERVAL_MS - elapsed)

  if (hoverFetchTimer) return

  hoverFetchTimer = window.setTimeout(() => {
    hoverFetchTimer = null
    if (!pendingHoverPoint) return
    const point = pendingHoverPoint
    pendingHoverPoint = null
    lastHoverFetchAt = performance.now()
    fetchHoverPointValue(point.lat, point.lng)
  }, delay)
}

function clearHoverState() {
  hoverPointData.value = null
  hoverCoords.value = null
  pendingHoverPoint = null
  if (hoverFrame) {
    cancelAnimationFrame(hoverFrame)
    hoverFrame = null
  }
  if (hoverFetchTimer) {
    clearTimeout(hoverFetchTimer)
    hoverFetchTimer = null
  }
  if (hoverPointController) {
    hoverPointController.abort()
    hoverPointController = null
  }
}

// Handle map mouse move for lightweight hover value and coordinates display.
function onMapMouseMove(e) {
  if (unifiedPopupPinned.value) return
  if (hoverFrame) cancelAnimationFrame(hoverFrame)
  hoverFrame = requestAnimationFrame(() => {
    hoverFrame = null
    const { lat, lng } = e.latlng

    if (e.originalEvent && mapEl.value) {
      const rect = mapEl.value.getBoundingClientRect()
      unifiedPopupPosition.value = clampUnifiedPopupPosition({
        x: e.originalEvent.clientX - rect.left,
        y: e.originalEvent.clientY - rect.top
      })
    }

    hoverCoords.value = { lat: lat.toFixed(4), lng: lng.toFixed(4) }
    scheduleHoverFetch(lat, lng)
  })
}

function formatGroupedNumber(value) {
  return Math.round(value).toLocaleString('en-US')
}

function formatScaleDistance(meters) {
  if (meters >= 1000) {
    const km = meters / 1000
    return `${km >= 10 ? formatGroupedNumber(km) : Number(km.toFixed(1)).toString()} km`
  }

  return `${formatGroupedNumber(meters)} m`
}

function getNiceScaleDistance(maxMeters) {
  if (!Number.isFinite(maxMeters) || maxMeters <= 0) return 1

  const exponent = Math.floor(Math.log10(maxMeters))
  const power = Math.pow(10, exponent)
  const fraction = maxMeters / power
  const niceFractions = [1, 2, 4, 5, 8]
  const niceFraction = niceFractions.reduce((best, current) => (
    current <= fraction ? current : best
  ), 1)

  return niceFraction * power
}

function getScaleSegmentCount(totalMeters) {
  const exponent = Math.floor(Math.log10(totalMeters))
  const leading = Math.round(totalMeters / Math.pow(10, exponent))

  if (leading === 1 || leading === 5) return 5
  return 4
}

function buildGisScaleControl() {
  const GisScaleControl = L.Control.extend({
    options: {
      position: 'bottomleft',
      maxWidth: 220,
      minWidth: 72
    },

    onAdd(controlMap) {
      this._map = controlMap
      this._container = L.DomUtil.create('div', 'leaflet-control gis-scale-control')
      this._ratio = L.DomUtil.create('div', 'gis-scale-ratio', this._container)
      this._labels = L.DomUtil.create('div', 'gis-scale-labels', this._container)
      this._bar = L.DomUtil.create('div', 'gis-scale-bar', this._container)
      L.DomEvent.disableClickPropagation(this._container)
      L.DomEvent.disableScrollPropagation(this._container)
      this._update = this._update.bind(this)
      this._scheduleUpdate = this._scheduleUpdate.bind(this)
      this._map.on('zoom zoomend move moveend resize', this._scheduleUpdate, this)
      requestAnimationFrame(this._update)
      return this._container
    },

    onRemove(controlMap) {
      controlMap.off('zoom zoomend move moveend resize', this._scheduleUpdate, this)
      if (this._pendingUpdate) cancelAnimationFrame(this._pendingUpdate)
    },

    _scheduleUpdate() {
      if (this._pendingUpdate) return
      this._pendingUpdate = requestAnimationFrame(() => {
        this._pendingUpdate = null
        this._update()
      })
    },

    _update() {
      if (!this._map || !this._container) return

      const size = this._map.getSize()
      if (!size.x || !size.y) return

      const center = this._map.latLngToContainerPoint(this._map.getCenter())
      const samplePixels = Math.min(120, Math.max(48, size.x * 0.18))
      const leftPoint = L.point(center.x - samplePixels / 2, center.y)
      const rightPoint = L.point(center.x + samplePixels / 2, center.y)
      const leftLatLng = this._map.containerPointToLatLng(leftPoint)
      const rightLatLng = this._map.containerPointToLatLng(rightPoint)
      const metersPerPixel = this._map.distance(leftLatLng, rightLatLng) / samplePixels

      if (!Number.isFinite(metersPerPixel) || metersPerPixel <= 0) return

      const maxWidth = Math.min(this.options.maxWidth, Math.max(this.options.minWidth, size.x * 0.36))
      const totalMeters = getNiceScaleDistance(maxWidth * metersPerPixel)
      const barWidth = totalMeters / metersPerPixel
      const segmentCount = getScaleSegmentCount(totalMeters)
      const ratioDenominator = metersPerPixel * (96 / 0.0254)

      this._container.style.width = `${Math.round(barWidth)}px`
      this._ratio.textContent = `1:${formatGroupedNumber(ratioDenominator)}`
      this._labels.innerHTML = ''
      this._bar.innerHTML = ''

      for (let index = 0; index <= segmentCount; index += 1) {
        const label = L.DomUtil.create('span', 'gis-scale-label', this._labels)
        label.textContent = index === 0
          ? '0'
          : formatScaleDistance((totalMeters / segmentCount) * index)
        label.style.left = `${(index / segmentCount) * 100}%`
      }

      for (let index = 0; index < segmentCount; index += 1) {
        const segment = L.DomUtil.create('span', 'gis-scale-segment', this._bar)
        segment.style.width = `${100 / segmentCount}%`
      }
    }
  })

  return new GisScaleControl()
}

// Apply filter method (exposed to parent)
function applyFilter(layer, filter) {
  if (wmsLayers[layer]) {
    wmsLayers[layer].setParams({
      CQL_FILTER: filter
    })
  }
}

// Initialize map
// onMounted(() => {
//   map = L.map(mapEl.value, {
//     center: [29.0, 79.4],
//     zoom: 9,
//     maxZoom: 22,
//     minZoom: 5,
//     zoomControl: true
//   })

onMounted(() => {
  map = L.map(mapEl.value, {
    center: [29.0, 79.4],
    zoom: 9,
    maxZoom: MAP_MAX_ZOOM,
    minZoom: MAP_MIN_ZOOM,
    zoomControl: true,
    maxBoundsViscosity: 1.0,
    bounceAtZoomLimits: false
  })

  gisScaleControl = buildGisScaleControl()
  gisScaleControl.addTo(map)

  const defaultStyle = mapStyles[0]
  baseLayer = L.tileLayer(defaultStyle.url, {
    attribution: defaultStyle.attribution,
    maxZoom: MAP_MAX_ZOOM,
    maxNativeZoom: 19
  }).addTo(map)

  const labels = L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png',
    {
      attribution: '© CartoDB',
      pane: 'overlayPane',
      maxZoom: MAP_MAX_ZOOM
    }
  )
  labels.addTo(map)

  // Create WMS layers
  wmsLayers.savi = createWMSLayer('savi')
  wmsLayers.kc = createWMSLayer('kc')
  wmsLayers.cwr = createWMSLayer('cwr')
  wmsLayers.iwr = createWMSLayer('iwr')
  wmsLayers.etc = createWMSLayer('etc')

  loadBoundary()
  map.on('click', onMapClick)
  map.on('mousemove', onMapMouseMove)
  map.on('mouseout', clearHoverState)
  window.addEventListener('resize', handlePixelWidgetViewportResize)
  if (typeof ResizeObserver !== 'undefined') {
    pixelWidgetContainerObserver = new ResizeObserver(handlePixelWidgetViewportResize)
    const observedContainer = mapEl.value?.closest('.map-container') || mapEl.value
    if (observedContainer) pixelWidgetContainerObserver.observe(observedContainer)
  }
})

// Clean up
onUnmounted(() => {
  stopPixelWidgetPointer()
  abortPixelTimeSeriesRequest()
  if (basemapTransitionFrame) {
    cancelAnimationFrame(basemapTransitionFrame)
    basemapTransitionFrame = null
  }
  if (pointDataController) {
    pointDataController.abort()
    pointDataController = null
  }
  clearHoverState()
  window.removeEventListener('resize', handlePixelWidgetViewportResize)
  if (pixelWidgetContainerObserver) {
    pixelWidgetContainerObserver.disconnect()
    pixelWidgetContainerObserver = null
  }
  if (userLocationMarker && map) {
    map.removeLayer(userLocationMarker)
  }
  clearSelectedPixelMarker()
  if (map) {
    map.off('click', onMapClick)
    map.off('mousemove', onMapMouseMove)
    map.off('mouseout', clearHoverState)
    if (gisScaleControl) {
      gisScaleControl.remove()
      gisScaleControl = null
    }
    map.remove()
  }
})

defineExpose({
  invalidateMapSize: () => {
    if (map) {
      setTimeout(() => {
        map.invalidateSize()
        if (boundaryLayer) {
          map.fitBounds(boundaryLayer.getBounds())
        }
      }, 100)
    }
  },
  applyFilter
})
</script>

<style scoped>

.map-container {
  width: 100%;
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
  font-family: 'Space Grotesk', 'JetBrains Mono', sans-serif;
  background:
    radial-gradient(circle at top right, rgba(25, 199, 166, 0.08), transparent 24%),
    linear-gradient(180deg, #050810 0%, #080c14 100%);
  isolation: isolate;
}

#map {
  width: 100%;
  height: 100%;
  min-height: 0;
  background: #0a0f14;
}

/* ─── Shared pill / card base ───────────────────────────── */
.pill-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: 50px;
  border: 1px solid rgba(200, 210, 220, 0.12);
  background: rgba(10, 15, 20, 0.9);
  backdrop-filter: blur(14px);
  color: #d0dbe5;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.3);
  transition: all 0.2s ease;
  white-space: nowrap;
}
.pill-btn:hover {
  border-color: rgba(47, 133, 90, 0.5);
  color: #3b9fd9;
  transform: translateY(-2px);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.4);
}

/* ─── Basemap Thumbnail Switcher ─────────────────────────── */
.basemap-switcher-control {
  position: absolute;
  left: 50%;
  bottom: 18px;
  z-index: 1050;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100% - 32px);
  padding: 8px;
  overflow-x: auto;
  overflow-y: visible;
  border: 1px solid rgba(214, 232, 246, 0.16);
  border-radius: 12px;
  background: rgba(5, 10, 17, 0.64);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(16px) saturate(1.18);
  -webkit-backdrop-filter: blur(16px) saturate(1.18);
  pointer-events: auto;
  transform: translateX(-50%);
  scrollbar-width: none;
  max-inline-size: min(520px, calc(100% - 32px));
}
.basemap-switcher-control::-webkit-scrollbar {
  display: none;
}

.basemap-card {
  position: relative;
  width: 86px;
  flex: 0 0 auto;
  padding: 4px;
  border: 1px solid rgba(226, 240, 252, 0.12);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.045);
  opacity: 0.68;
  filter: brightness(0.78) saturate(0.9);
  cursor: pointer;
  outline: none;
  transform-origin: center bottom;
  transition:
    transform 0.18s ease,
    opacity 0.18s ease,
    filter 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease;
}

.basemap-card-thumb {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 9px;
  overflow: hidden;
  background: #0c131c;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.basemap-card-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.basemap-card-name {
  position: absolute;
  right: 8px;
  bottom: 7px;
  left: 8px;
  display: block;
  min-width: 0;
  padding: 2px 5px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.58);
  color: #f7fbff;
  font-size: 0.62rem;
  font-weight: 700;
  line-height: 1.15;
  text-align: center;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.basemap-card:hover,
.basemap-card:focus-visible {
  opacity: 1;
  filter: brightness(1.1) saturate(1.08);
  transform: scale(1.045);
  border-color: rgba(157, 213, 255, 0.42);
  background: rgba(255, 255, 255, 0.08);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.32);
}

.basemap-card.active {
  z-index: 1;
  opacity: 1;
  filter: brightness(1.08) saturate(1.08);
  transform: scale(1.07);
  border-color: rgba(92, 205, 255, 0.92);
  background: rgba(3, 12, 22, 0.76);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.2),
    0 0 22px rgba(59, 159, 217, 0.5),
    0 12px 26px rgba(0, 0, 0, 0.38);
}

.basemap-card.active:hover,
.basemap-card.active:focus-visible {
  filter: brightness(1.16) saturate(1.12);
  transform: scale(1.085);
}

/* ─── Info Panel ────────────────────────────────────────── */
.info-panel {
  position: absolute;
  bottom: 70px;
  left: 16px;
  background:
    linear-gradient(180deg, rgba(5, 8, 14, 0.96), rgba(8, 12, 18, 0.94)),
    radial-gradient(circle at top right, rgba(25, 199, 166, 0.08), transparent 34%);
  backdrop-filter: blur(16px);
  padding: 14px 14px 12px;
  border-radius: 18px;
  border: 1px solid rgba(200, 210, 220, 0.1);
  z-index: 1000;
  width: min(92vw, 360px);
  min-width: 240px;
  max-width: 92vw;
  max-height: 72vh;
  overflow-y: auto;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.45);
  color: #f0f4f8;
  scrollbar-width: thin;
  scrollbar-color: rgba(47, 133, 90, 0.3) transparent;
  transition: all 0.3s ease;
}

.info-panel.light {
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(47, 133, 90, 0.24);
  color: #1e293b;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
}

.info-panel.light h3 { color: #2f855a; }
.info-panel.light .meta-row { background: rgba(0, 0, 0, 0.04); }
.info-panel.light .meta-label { color: #64748b; }
.info-panel.light .meta-val { color: #0f172a; }
.info-panel.light .sentinel-date { color: #2f855a; }
.info-panel.light .coord-val { color: #334155; }
.info-panel.light .fc-item { background: rgba(0, 0, 0, 0.03); }
.info-panel.light .fc-label { color: #64748b; }
.info-panel.light .value-section { border-top-color: rgba(0, 0, 0, 0.08); }
.info-panel.light .value-section h4 { color: #334155; }
.info-panel.light .loading-hint { color: #64748b; }
.info-panel.light .close-btn { background: rgba(0, 0, 0, 0.05); border-color: rgba(0, 0, 0, 0.1); color: #64748b; }
.info-panel.light .close-btn:hover { background: rgba(47, 133, 90, 0.1); color: #2f855a; border-color: rgba(47, 133, 90, 0.28); }
.info-panel::-webkit-scrollbar { width: 4px; }
.info-panel::-webkit-scrollbar-thumb { background: rgba(47, 133, 90, 0.2); border-radius: 2px; }

.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(200, 210, 220, 0.06);
  margin-bottom: 6px;
  font-family: 'JetBrains Mono', monospace;
}
.meta-icon  { font-size: 0.84rem; flex-shrink: 0; }
.meta-label { color: #8899aa; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.62rem; flex-shrink: 0; }
.meta-val   { margin-left: auto; font-weight: 600; text-align: right; font-size: 0.68rem; color: #d0dbe5; }
.sentinel-date { color: #3b9fd9; }
.coord-val     { color: #8899aa; font-size: 0.66rem; }
.weather-row { cursor: pointer; }
.weather-link {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.weather-date-line { color: #d0dbe5; }
.weather-location-line { color: #3b9fd9; font-size: 0.66rem; }
.info-panel.light .weather-date-line { color: #0f172a; }
.info-panel.light .weather-location-line { color: #2f855a; }

.forecast-grid {
  display: flex;
  flex-direction: row;
  gap: 5px;
  overflow-x: auto;
  padding: 2px 0 6px;
  scrollbar-width: none;
}
.forecast-grid::-webkit-scrollbar { display: none; }

.fc-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 5px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  min-width: 64px;
  flex: 1;
  transition: all 0.2s ease;
  border: 1px solid rgba(200, 210, 220, 0.06);
}
.fc-item[onclick], .fc-item:has(.value) { cursor: pointer; }
.fc-item:hover { background: rgba(47, 133, 90, 0.1); border-color: rgba(47, 133, 90, 0.2); }

.fc-item--active {
  background: rgba(47, 133, 90, 0.2) !important;
  border-color: rgba(47, 133, 90, 0.4) !important;
}

.fc-label {
  font-size: 0.58rem;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
.observed-label { color: #3b9fd9; font-weight: 600; }
.fc-na { opacity: 0.5; }
.unit {
  font-style: normal;
  font-size: 0.64rem;
  opacity: 0.75;
  margin-left: 3px;
}
.nodata-chip {
  font-size: 0.66rem;
  color: #8899aa;
  font-style: italic;
  font-family: 'JetBrains Mono', monospace;
}
.nodata-hint {
  font-size: 0.68rem;
  color: #8899aa;
  font-style: italic;
  margin: 4px 0 0;
  padding: 5px 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 10px;
}
.model-tag {
  font-size: 0.62rem;
  color: #3A5A7A;
  font-family: 'JetBrains Mono', monospace;
  text-align: right;
  margin: 2px 0 0;
  padding: 0 4px;
}
.loading-hint {
  font-size: 0.7rem;
  color: #8ca6b8;
  text-align: center;
  margin: 8px 0 0;
  font-style: italic;
}

.close-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(170, 199, 216, 0.12);
  font-size: 0.95rem;
  line-height: 1;
  cursor: pointer;
  color: #8ca6b8;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}
.close-btn:hover { background: rgba(25, 199, 166, 0.12); color: #88f2db; border-color: rgba(25, 199, 166, 0.28); }

.info-panel h3 {
  margin: 0 0 8px 0;
  color: #effbff;
  font-size: 0.88rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-family: 'JetBrains Mono', monospace;
}

.info-panel p {
  font-size: 0.72rem;
  color: #8ca6b8;
  margin: 0 0 8px;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(255, 255, 255, 0.04) !important;
  padding: 5px 8px;
  border-radius: 10px;
}

.value-section {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(170, 199, 216, 0.1);
}

.value-section h4 {
  margin: 0 0 8px 0;
  font-size: 0.72rem;
  font-weight: 700;
  color: #b9cfdd;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  font-family: 'JetBrains Mono', monospace;
}

.value {
  font-weight: 700;
  font-size: 0.85rem;
  display: inline-block;
  transition: transform 0.2s;
  border-radius: 6px;
  padding: 3px 7px;
}
.value:hover { transform: scale(1.05); }

/* ─── Location Button ───────────────────────────────────── */
.location-btn {
  position: absolute;
  bottom: 30px;
  right: 20px;
  z-index: 1000;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 52px;
  height: 52px;
  padding: 0;
  border-radius: 16px;
  border: 1px solid rgba(170, 199, 216, 0.14);
  background:
    radial-gradient(circle at 50% 50%, rgba(25, 199, 166, 0.18), transparent 58%),
    rgba(9, 23, 34, 0.86);
  backdrop-filter: blur(14px);
  color: #eaf6fc;
  cursor: pointer;
  box-shadow: 0 14px 34px rgba(1, 10, 17, 0.24);
  transition: all 0.2s ease;
}
.location-btn:hover {
  border-color: rgba(25, 199, 166, 0.38);
  color: #88f2db;
  transform: translateY(-2px);
  box-shadow: 0 18px 38px rgba(1, 10, 17, 0.26);
}
.location-btn.loading { opacity: 0.65; cursor: wait; }
.location-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.location-btn:disabled:hover { transform: none; border-color: rgba(170, 199, 216, 0.14); color: #eaf6fc; }
.location-icon {
  display: inline-flex;
  width: 24px;
  height: 24px;
}
.location-icon svg {
  width: 100%;
  height: 100%;
}
.location-spinner {
  position: absolute;
  inset: 10px;
  border: 2px solid rgba(170, 199, 216, 0.14);
  border-top-color: #19c7a6;
  border-radius: 50%;
  animation: locateSpin 0.85s linear infinite;
}

@keyframes locateSpin {
  to { transform: rotate(360deg); }
}

.selected-point-icon {
  position: absolute;
  right: 20px;
  bottom: 92px;
  z-index: 1000;
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(170, 199, 216, 0.14);
  border-radius: 14px;
  background: rgba(9, 23, 34, 0.82);
  color: #eaf6fc;
  cursor: pointer;
  box-shadow: 0 14px 34px rgba(1, 10, 17, 0.2);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}
.selected-point-icon:hover {
  transform: translateY(-2px);
  border-color: rgba(25, 199, 166, 0.36);
  background: rgba(13, 39, 52, 0.9);
}
.point-icon {
  font-size: 1rem;
  line-height: 1;
}

/* ─── Chart Panel (draggable + resizable) ───────────────── */
.chart-panel {
  position: absolute;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid rgba(100, 116, 139, 0.2);
  border-radius: 14px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22), 0 0 0 1px rgba(100,116,139,0.06);
  overflow: hidden;
  min-width: 0;
  min-height: 0;
  touch-action: none;
  user-select: none;
  transition: box-shadow 0.18s ease, border-color 0.18s ease;
}

.chart-panel.chart-dragging,
.chart-panel.chart-resizing {
  box-shadow: 0 32px 80px rgba(15, 23, 42, 0.32);
  border-color: rgba(59, 159, 217, 0.4);
  cursor: grabbing;
}

/* Drag header */
.chart-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 40px;
  min-height: 40px;
  padding: 0 10px 0 14px;
  background: #0d1319;
  border-bottom: 1px solid rgba(100, 116, 139, 0.14);
  cursor: grab;
  flex-shrink: 0;
  border-radius: 13px 13px 0 0;
}

.chart-panel.chart-dragging .chart-panel-header { cursor: grabbing; }
.chart-panel.chart-maximized .chart-panel-header { cursor: default; }

.chart-panel-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #d0dbe5;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  font-family: 'JetBrains Mono', 'Space Grotesk', sans-serif;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.chart-panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.chart-panel-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid rgba(170, 199, 216, 0.12);
  border-radius: 7px;
  background: rgba(255,255,255,0.06);
  color: #8899aa;
  cursor: pointer;
  padding: 0;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.chart-panel-action:hover {
  background: rgba(255,255,255,0.12);
  color: #d0dbe5;
  border-color: rgba(170, 199, 216, 0.24);
}

.chart-panel-action.chart-panel-close:hover {
  background: rgba(239, 68, 68, 0.18);
  color: #fca5a5;
  border-color: rgba(239, 68, 68, 0.3);
}

/* Chart body */
.chart-panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Resize handles (mirrors pixel-widget approach) */
.chart-resize-handle {
  position: absolute;
  z-index: 4;
  touch-action: none;
}
.chart-resize-n, .chart-resize-s { left: 14px; right: 14px; height: 14px; cursor: ns-resize; }
.chart-resize-n { top: -6px; }
.chart-resize-s { bottom: -6px; }
.chart-resize-e, .chart-resize-w { top: 46px; bottom: 14px; width: 14px; cursor: ew-resize; }
.chart-resize-e { right: -6px; }
.chart-resize-w { left: -6px; }
.chart-resize-ne, .chart-resize-nw, .chart-resize-se, .chart-resize-sw { width: 22px; height: 22px; }
.chart-resize-ne { top: -7px; right: -7px; cursor: nesw-resize; }
.chart-resize-nw { top: -7px; left: -7px; cursor: nwse-resize; }
.chart-resize-se { bottom: -7px; right: -7px; cursor: nwse-resize; }
.chart-resize-sw { bottom: -7px; left: -7px; cursor: nesw-resize; }

@keyframes panelFloatIn {
  from { opacity: 0; transform: scale(0.96) translateY(8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}

.map-widget-enter-active,
.map-widget-leave-active {
  transition: opacity 0.22s ease, transform 0.24s cubic-bezier(.2,.8,.2,1);
}

.map-widget-enter-from,
.map-widget-leave-to {
  opacity: 0;
}

.map-widget-enter-from.chart-panel,
.map-widget-leave-to.chart-panel {
  transform: scale(0.96) translateY(8px);
}

.map-widget-enter-from.weather-panel,
.map-widget-leave-to.weather-panel {
  transform: translateY(-50%) translateX(22px) scale(0.98);
}

/* responsive: on small screens snap to near-full-width */
@media (max-width: 768px) {
  .chart-panel {
    border-radius: 12px;
  }
}
@media (max-width: 480px) {
  .chart-panel {
    border-radius: 10px;
  }
  .chart-panel-header {
    height: 38px;
    min-height: 38px;
    padding: 0 8px 0 12px;
  }
}

/* ─── Weather Panel ───────────────────────────────────────── */
.weather-panel {
  position: absolute;
  top: 50%;
  right: 20px;
  transform: translateY(-50%);
  width: min(340px, calc(100% - 32px));
  max-height: min(85vh, calc(100% - 32px));
  background: linear-gradient(180deg, rgba(10, 25, 36, 0.96), rgba(14, 32, 45, 0.94));
  backdrop-filter: blur(20px);
  border: 1px solid rgba(170, 199, 216, 0.14);
  border-radius: 20px;
  z-index: 2000;
  box-shadow: 0 24px 70px rgba(1, 10, 17, 0.28), 0 0 0 1px rgba(170, 199, 216, 0.04);
  overflow-y: auto;
  animation: slideInRight 0.28s ease;
  scrollbar-width: thin;
  scrollbar-color: rgba(47, 133, 90, 0.3) transparent;
}

.weather-panel::-webkit-scrollbar {
  width: 4px;
}

.weather-panel::-webkit-scrollbar-thumb {
  background: rgba(47, 133, 90, 0.2);
  border-radius: 2px;
}

@keyframes slideInRight {
  from { opacity: 0; transform: translateY(-50%) translateX(30px); }
  to   { opacity: 1; transform: translateY(-50%) translateX(0); }
}

.weather-panel > .close-btn {
  z-index: 2001;
  top: 12px;
  right: 12px;
}

.weather-content {
  padding: 20px 18px;
}

.weather-title {
  margin: 0 0 16px 0;
  color: #effbff;
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  font-family: 'JetBrains Mono', monospace;
}

.weather-header {
  margin-bottom: 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(170, 199, 216, 0.1);
}

.weather-location-info {
  margin-bottom: 8px;
}

.location-name {
  margin: 0;
  color: #d0dbe5;
  font-size: 0.82rem;
  font-weight: 600;
}

.location-coords {
  margin: 2px 0 0 0;
  color: #8899aa;
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
}

.weather-date {
  margin: 0;
  color: #3b9fd9;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.weather-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}

.weather-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(200, 210, 220, 0.08);
  transition: all 0.2s ease;
}

.weather-card:hover {
  background: rgba(47, 133, 90, 0.12);
  border-color: rgba(47, 133, 90, 0.2);
  transform: translateY(-2px);
  box-shadow: 0 12px 24px rgba(1, 10, 17, 0.18);
}

.weather-icon {
  font-size: 1.6rem;
}

.weather-label {
  font-size: 0.65rem;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-family: 'JetBrains Mono', monospace;
  text-align: center;
}

.weather-value {
  font-size: 0.9rem;
  color: #3b9fd9;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.no-weather-data {
  text-align: center;
  color: #8899aa;
  font-style: italic;
  font-size: 0.75rem;
  margin: 12px 0 0 0;
}

.leaflet-tile { image-rendering: auto; }

/* ─── Blue Dot Marker ───────────────────────────────────── */
:global(.blue-dot-marker) { position: relative; }
:global(.blue-dot) {
  width: 16px; height: 16px;
  background: #19c7a6;
  border: 3px solid white;
  border-radius: 50%;
  position: absolute; top: 4px; left: 4px;
  z-index: 2;
  box-shadow: 0 0 12px rgba(25, 199, 166, 0.45);
}
:global(.pulse-ring) {
  width: 32px; height: 32px;
  background: rgba(25, 199, 166, 0.22);
  border-radius: 50%;
  position: absolute; top: -4px; left: -4px;
  animation: markerPulse 1.5s ease-out infinite;
  z-index: 1;
}
@keyframes markerPulse {
  0%   { transform: scale(0.5); opacity: 0.5; }
  50%  { transform: scale(1.2); opacity: 0.3; }
  100% { transform: scale(1.5); opacity: 0; }
}

:global(.selected-pixel-marker) {
  position: relative;
  pointer-events: none;
}
:global(.selected-pixel-ring),
:global(.selected-pixel-core) {
  position: absolute;
  left: 50%;
  top: 50%;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}
:global(.selected-pixel-ring) {
  width: 34px;
  height: 34px;
  border: 3px solid #ffffff;
  background: rgba(14, 165, 233, 0.2);
  box-shadow:
    0 0 0 4px rgba(14, 165, 233, 0.28),
    0 0 22px rgba(14, 165, 233, 0.62);
  animation: selectedPixelPulse 1.55s ease-out infinite;
}
:global(.selected-pixel-core) {
  width: 10px;
  height: 10px;
  background: #0284c7;
  border: 2px solid #ffffff;
  box-shadow: 0 2px 10px rgba(2, 132, 199, 0.55);
}
@keyframes selectedPixelPulse {
  0% { transform: translate(-50%, -50%) scale(0.72); opacity: 0.95; }
  70% { transform: translate(-50%, -50%) scale(1.16); opacity: 0.32; }
  100% { transform: translate(-50%, -50%) scale(1.22); opacity: 0.08; }
}

/* ─── Responsive ────────────────────────────────────────── */
@media (max-width: 768px) {
  .basemap-switcher-control { bottom: 12px; max-width: calc(100% - 20px); padding: 7px; gap: 7px; }
  .basemap-card { width: 78px; }
  .basemap-card-name { font-size: 0.58rem; right: 7px; left: 7px; }
  .info-panel { left: 10px; right: 10px; bottom: 10px; width: auto; max-width: none; max-height: 42vh; }
  .location-btn { right: 14px; bottom: 94px; width: 48px; height: 48px; }
  .selected-point-icon { right: 14px; bottom: 150px; width: 44px; height: 44px; }
  .weather-panel { right: 10px; width: calc(100% - 20px); max-width: 340px; }
}

@media (max-width: 480px) {
  .basemap-switcher-control { bottom: 10px; justify-content: flex-start; }
  .basemap-card { width: 72px; padding: 3px; }
  .basemap-card-name { bottom: 6px; padding: 2px 4px; font-size: 0.55rem; }
  .info-panel { padding: 14px 14px 12px; border-radius: 18px; }
  .location-btn { right: 12px; bottom: 88px; width: 46px; height: 46px; border-radius: 14px; }
  .selected-point-icon { right: 12px; bottom: 140px; width: 42px; height: 42px; border-radius: 13px; }
  .weather-panel { right: 8px; width: calc(100% - 16px); max-width: 290px; }
  .weather-grid { grid-template-columns: 1fr; }
}
/* ─── Kc Forecast Window Bar ────────────────────────────────────────── */
.forecast-window-bar {
  position: absolute;
  top: 62px;
  right: 16px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(200, 210, 220, 0.1);
  background: rgba(5, 8, 14, 0.92);
  backdrop-filter: blur(14px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
  animation: dropdownFadeIn 0.18s ease;
}

.fw-label {
  font-size: 0.68rem;
  font-weight: 700;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-family: 'JetBrains Mono', monospace;
  padding-right: 6px;
  border-right: 1px solid rgba(255,255,255,0.06);
  margin-right: 4px;
}

.fw-btn {
  padding: 5px 11px;
  border-radius: 50px;
  border: 1px solid transparent;
  background: transparent;
  color: #8899aa;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  font-family: 'Space Grotesk', sans-serif;
  white-space: nowrap;
}
.fw-btn:hover {
  background: rgba(47, 133, 90, 0.15);
  color: #d0dbe5;
}
.fw-btn.active {
  background: rgba(47, 133, 90, 0.25);
  border-color: rgba(47, 133, 90, 0.5);
  color: #3b9fd9;
  box-shadow: 0 0 10px rgba(47, 133, 90, 0.2);
}

.fc-label--active {
  color: #3b9fd9 !important;
  font-weight: 700;
}

/* Forecast window bar responsive */
@media (max-width: 768px) {
  .forecast-window-bar {
    top: 54px;
    right: 10px;
    padding: 5px 8px;
    gap: 2px;
  }
  .fw-btn { padding: 4px 8px; font-size: 0.68rem; }
}

@media (max-width: 480px) {
  .forecast-window-bar { gap: 1px; }
  .fw-label { display: none; }
  .fw-btn { padding: 4px 7px; font-size: 0.65rem; }
}

/* ─── Unified Pixel Popup ───────────────────────────────── */
.pixel-value-popup {
  position: absolute;
  z-index: 2100;
  width: min(480px, calc(100% - 28px));
  max-width: calc(100% - 28px);
  transform: translate(12px, 12px);
  color: #1f2937;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(100, 116, 139, 0.18);
  border-radius: 12px;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18);
  backdrop-filter: blur(12px) saturate(145%);
  overflow: hidden;
  pointer-events: none;
  transition: left 0.08s ease-out, top 0.08s ease-out, opacity 0.18s ease, transform 0.18s ease;
  animation: pixelPopupIn 0.18s cubic-bezier(.2,.8,.2,1);
}

@keyframes pixelPopupIn {
  from { opacity: 0; transform: translate(12px, 18px) scale(0.98); }
  to { opacity: 1; transform: translate(12px, 12px) scale(1); }
}

.pixel-value-popup.pinned {
  pointer-events: auto;
  transform: translate(-50%, calc(-100% - 18px));
  animation-name: pixelPinnedPopupIn;
}

@keyframes pixelPinnedPopupIn {
  from { opacity: 0; transform: translate(-50%, calc(-100% - 10px)) scale(0.98); }
  to { opacity: 1; transform: translate(-50%, calc(-100% - 18px)) scale(1); }
}

.pixel-value-popup.pinned::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -7px;
  width: 14px;
  height: 14px;
  background: rgba(255, 255, 255, 0.96);
  border-right: 1px solid rgba(100, 116, 139, 0.18);
  border-bottom: 1px solid rgba(100, 116, 139, 0.18);
  transform: translateX(-50%) rotate(45deg);
}

.pixel-popup-close {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  width: 24px;
  height: 24px;
  border: 1px solid rgba(100, 116, 139, 0.18);
  border-radius: 7px;
  background: #f8fafc;
  color: #64748b;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.pixel-popup-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 38px 9px 12px;
  border-bottom: 1px solid rgba(100, 116, 139, 0.14);
  background: #f8fafc;
}

.pixel-popup-kicker,
.pixel-popup-date,
.pixel-popup-table-head,
.pixel-popup-layer,
.pixel-popup-value,
.pixel-popup-loading,
.pixel-popup-empty {
  font-family: 'JetBrains Mono', monospace;
}

.pixel-popup-kicker {
  color: #334155;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.pixel-popup-date {
  color: #0284c7;
  font-size: 0.68rem;
  font-weight: 800;
  white-space: nowrap;
}

.pixel-popup-table {
  padding: 8px;
}

.pixel-popup-table-head,
.pixel-popup-row {
  display: grid;
  grid-template-columns: minmax(88px, 1.05fr) minmax(76px, 0.85fr);
  gap: 8px;
  align-items: center;
}

.pixel-popup-table-head.with-forecast,
.pixel-popup-row.with-forecast {
  grid-template-columns: minmax(88px, 1.05fr) minmax(76px, 0.85fr) repeat(3, minmax(56px, 0.7fr));
}

.pixel-popup-table-head {
  padding: 0 6px 6px;
  color: #64748b;
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.pixel-popup-row {
  padding: 7px 6px;
  border-top: 1px solid rgba(100, 116, 139, 0.1);
  border-radius: 8px;
  transition: background 0.16s ease, transform 0.16s ease;
  animation: pixelPopupRowIn 0.18s cubic-bezier(.2,.8,.2,1) both;
}

.pixel-popup-row:hover {
  background: rgba(14, 165, 233, 0.06);
  transform: translateX(2px);
}

@keyframes pixelPopupRowIn {
  from { opacity: 0; transform: translateY(3px); }
  to { opacity: 1; transform: translateY(0); }
}

.pixel-popup-layer {
  color: #334155;
  font-size: 0.7rem;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pixel-popup-value {
  color: #0f766e;
  font-size: 0.68rem;
  font-weight: 800;
  white-space: nowrap;
}

.pixel-popup-value.forecast {
  color: #0369a1;
}

.pixel-popup-empty-cell {
  min-height: 1px;
  border-radius: 6px;
  background: rgba(148, 163, 184, 0.08);
  opacity: 0.45;
}

.pixel-popup-loading,
.pixel-popup-empty {
  padding: 14px 16px;
  color: #64748b;
  font-size: 0.74rem;
}

/* ─── Floating Pixel Trend Widget ──────────────────────────────── */
.pixel-trend-widget {
  position: absolute;
  z-index: 2600;
  min-width: min(320px, calc(100% - 24px));
  min-height: 44px;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: 1px solid rgba(100, 116, 139, 0.18);
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(18px) saturate(135%);
  -webkit-backdrop-filter: blur(18px) saturate(135%);
  box-shadow:
    0 24px 54px rgba(15, 23, 42, 0.18),
    0 0 0 1px rgba(255, 255, 255, 0.45);
  color: #0f172a;
  overflow: hidden;
  transform-origin: top right;
  transition:
    left 0.2s ease,
    top 0.2s ease,
    width 0.2s ease,
    height 0.2s ease,
    border-radius 0.2s ease,
    box-shadow 0.2s ease,
    opacity 0.2s ease,
    transform 0.22s cubic-bezier(.2,.8,.2,1);
  touch-action: none;
  animation: widgetLiftIn 0.24s cubic-bezier(.2,.8,.2,1);
}

@keyframes widgetLiftIn {
  from { opacity: 0; transform: translateY(12px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.pixel-trend-widget::before {
  content: none;
}

.pixel-trend-widget.dragging,
.pixel-trend-widget.resizing {
  transition: none;
  user-select: none;
}

.pixel-trend-widget.maximized {
  border-radius: 12px;
}

.pixel-trend-widget.minimized {
  box-shadow:
    0 18px 50px rgba(1, 10, 17, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.pixel-widget-header {
  position: relative;
  z-index: 2;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 10px 7px 14px;
  border-bottom: 1px solid rgba(100, 116, 139, 0.14);
  background: #f8fafc;
  flex-shrink: 0;
  cursor: grab;
  touch-action: none;
}
.pixel-trend-widget.dragging .pixel-widget-header {
  cursor: grabbing;
}
.pixel-trend-widget.minimized .pixel-widget-header {
  border-bottom-color: transparent;
}

.pixel-widget-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font-size: 0.84rem;
  font-weight: 800;
  letter-spacing: 0.01em;
}
.pixel-widget-title svg { color: #0284c7; flex-shrink: 0; }

.pixel-widget-actions {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}
.pixel-widget-action {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(100, 116, 139, 0.18);
  border-radius: 8px;
  color: #475569;
  background: #ffffff;
  cursor: pointer;
  transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease;
  touch-action: manipulation;
}
.pixel-widget-action svg {
  width: 14px;
  height: 14px;
}
.pixel-widget-action:hover {
  transform: translateY(-1px);
  background: rgba(14, 165, 233, 0.1);
  color: #0369a1;
  box-shadow: 0 8px 18px rgba(14, 165, 233, 0.12);
}
.pixel-widget-action.close:hover {
  background: rgba(248, 113, 113, 0.18);
  color: #fecaca;
}

.pixel-widget-body {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.pixel-widget-meta {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(170px, 0.42fr);
  gap: 10px;
}
.pixel-meta-card {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid rgba(180, 205, 222, 0.1);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.055);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pixel-meta-card .meta-label {
  color: #73b7ff;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.pixel-meta-card strong {
  color: #eef8fc;
  font-size: 0.84rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pixel-meta-card.source .meta-label { color: #67e08f; }

.pixel-widget-loading,
.pixel-widget-error,
.pixel-widget-empty {
  flex: 1;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1px solid rgba(100, 116, 139, 0.14);
  border-radius: 10px;
  background: #f8fafc;
  padding: 24px;
}
.pixel-widget-loading {
  align-items: stretch;
  justify-content: flex-start;
  gap: 12px;
  text-align: left;
}
.pixel-loading-copy,
.pixel-widget-error {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.pixel-widget-loading strong,
.pixel-widget-error strong {
  color: #0f172a;
  font-size: 0.95rem;
}
.pixel-widget-loading span,
.pixel-widget-error span,
.pixel-widget-empty {
  color: #64748b;
  font-size: 0.86rem;
}
.pixel-widget-error {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.25);
  background: rgba(127, 29, 29, 0.16);
}
.pixel-loading-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.72fr);
  gap: 10px;
}
.pixel-loading-grid span,
.pixel-loading-chart,
.pixel-loading-chart span {
  position: relative;
  overflow: hidden;
  border-radius: 10px;
  background: rgba(148, 163, 184, 0.16)
}
.pixel-loading-grid span {
  height: 50px;
}
.pixel-loading-chart {
  flex: 1;
  min-height: 190px;
  display: grid;
  grid-template-columns: repeat(10, minmax(16px, 1fr));
  align-items: end;
  gap: 10px;
  padding: 18px;
  border: 1px solid rgba(100, 116, 139, 0.12);
}
.pixel-loading-chart span {
  min-height: 54px;
  height: 52%;
}
.pixel-loading-chart span:nth-child(2n) { height: 72%; }
.pixel-loading-chart span:nth-child(3n) { height: 38%; }
.pixel-loading-grid span::after,
.pixel-loading-chart::after,
.pixel-loading-chart span::after {
  content: "";
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.14), transparent);
  animation: shimmer 1.35s ease-in-out infinite;
}

@keyframes shimmer { to { transform: translateX(100%); } }

.pixel-widget-chart {
  flex: 1;
  min-height: 0;
}

.pixel-resize-handle {
  position: absolute;
  z-index: 4;
  touch-action: none;
}
.pixel-resize-n,
.pixel-resize-s {
  left: 14px;
  right: 14px;
  height: 14px;
  cursor: ns-resize;
}
.pixel-resize-n { top: -6px; }
.pixel-resize-s { bottom: -6px; }
.pixel-resize-e,
.pixel-resize-w {
  top: 14px;
  bottom: 14px;
  width: 14px;
  cursor: ew-resize;
}
.pixel-resize-e { right: -6px; }
.pixel-resize-w { left: -6px; }
.pixel-resize-ne,
.pixel-resize-nw,
.pixel-resize-se,
.pixel-resize-sw {
  width: 22px;
  height: 22px;
}
.pixel-resize-ne { top: -7px; right: -7px; cursor: nesw-resize; }
.pixel-resize-nw { top: -7px; left: -7px; cursor: nwse-resize; }
.pixel-resize-se { bottom: -7px; right: -7px; cursor: nwse-resize; }
.pixel-resize-sw { bottom: -7px; left: -7px; cursor: nesw-resize; }

.pixel-widget-fade-enter-active,
.pixel-widget-fade-leave-active {
  transition: opacity 0.22s ease, transform 0.24s cubic-bezier(.2,.8,.2,1);
}
.pixel-widget-fade-enter-from,
.pixel-widget-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.94);
}
.pixel-widget-fade-enter-to,
.pixel-widget-fade-leave-from {
  opacity: 1;
  transform: translateY(0) scale(1);
}

@media (max-width: 768px) {
  .pixel-trend-widget {
    border-radius: 12px;
  }
  .pixel-widget-meta {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .pixel-trend-widget {
    border-radius: 12px;
  }
  .pixel-widget-header {
    padding: 10px 10px 10px 14px;
  }
  .pixel-widget-body {
    padding: 10px;
  }
}

/* ─── GIS Map Overlays ───────────────────────────────────── */
.mouse-coordinate-display {
  position: absolute;
  top: 12px;
  left: 52px;
  z-index: 1000;
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #fff;
  font-family: 'JetBrains Mono', 'Roboto Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: 0;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.95);
  pointer-events: none;
}

:global(.gis-scale-control) {
  margin-left: 14px !important;
  margin-bottom: 22px !important;
  background: transparent;
  border: 0;
  box-shadow: none;
  color: #fff;
  font-family: 'JetBrains Mono', 'Roboto Mono', monospace;
  pointer-events: none;
  text-shadow:
    0 1px 2px rgba(0, 0, 0, 0.95),
    0 0 2px rgba(0, 0, 0, 0.9);
}

:global(.gis-scale-ratio) {
  margin-bottom: 4px;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  text-align: center;
  white-space: nowrap;
}

:global(.gis-scale-labels) {
  position: relative;
  height: 14px;
  margin-bottom: 1px;
}

:global(.gis-scale-label) {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

:global(.gis-scale-label:first-child) {
  transform: translateX(0);
}

:global(.gis-scale-label:last-child) {
  transform: translateX(-100%);
}

:global(.gis-scale-bar) {
  display: flex;
  width: 100%;
  height: 9px;
  overflow: hidden;
  border: 1px solid rgba(20, 20, 20, 0.9);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.28),
    0 1px 2px rgba(0, 0, 0, 0.5);
}

:global(.gis-scale-segment) {
  display: block;
  height: 100%;
  border-right: 1px solid rgba(20, 20, 20, 0.82);
}

:global(.gis-scale-segment:nth-child(odd)) {
  background: rgba(255, 255, 255, 0.96);
}

:global(.gis-scale-segment:nth-child(even)) {
  background: rgba(123, 130, 131, 0.9);
}

:global(.gis-scale-segment:last-child) {
  border-right: 0;
}

/* ─── Responsive adjustments ────────────────────────────────────────── */
@media (max-width: 768px) {
  .info-panel-btn {
    bottom: 10px;
    left: 10px;
    width: 44px;
    height: 44px;
  }
  .pixel-value-popup {
    width: min(360px, calc(100% - 20px));
    transform: translate(8px, 8px);
  }
  .pixel-popup-table-head,
  .pixel-popup-row {
    grid-template-columns: minmax(76px, 1fr) minmax(74px, 0.85fr);
    gap: 5px;
  }
  .pixel-popup-table-head.with-forecast,
  .pixel-popup-row.with-forecast {
    grid-template-columns: minmax(72px, 0.9fr) minmax(70px, 0.82fr) repeat(3, minmax(42px, 0.6fr));
  }
  .mouse-coordinate-display {
    top: 10px;
    left: 50px;
    font-size: 10px;
  }
  :global(.gis-scale-control) {
    margin-left: 10px !important;
    margin-bottom: 16px !important;
  }
}

@media (max-width: 480px) {
  .info-panel-btn {
    width: 42px;
    height: 42px;
  }
  .pixel-value-popup {
    width: min(310px, calc(100% - 16px));
    font-size: 0.92rem;
  }
  .pixel-popup-table {
    padding: 6px;
  }
  .pixel-popup-table-head,
  .pixel-popup-row {
    font-size: 0.6rem;
    grid-template-columns: minmax(64px, 0.95fr) minmax(70px, 0.85fr);
  }
  .pixel-popup-table-head.with-forecast,
  .pixel-popup-row.with-forecast {
    grid-template-columns: minmax(58px, 0.9fr) minmax(64px, 0.82fr) repeat(3, minmax(32px, 0.54fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .basemap-card,
  .location-btn,
  .pixel-value-popup,
  .pixel-popup-row,
  .pixel-trend-widget,
  .pixel-widget-action,
  .chart-panel,
  .weather-panel {
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
 
</style>
