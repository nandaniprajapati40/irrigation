<template>
  <div :class="{ dark: isDark }">

    <!-- ════ HOME PAGE ════ -->
    <Home
      v-if="currentView === 'home'"
      :is-dark="isDark"
      @launch="showDashboard"
      @docs="showDOCs"
      @faqs="showFAQs"
      @toggle-theme="isDark = !isDark"
    />

    <!-- ════ FAQS PAGE ════ -->
    <FAQsView
      v-else-if="currentView === 'faqs'"
      :is-dark="isDark"
      @launch="showDashboard"
      @home="showHome"
      @docs="showDOCs"
    />

    <!-- ════ DOCS PAGE ════ -->
    <DOCsView
      v-else-if="currentView === 'docs'"
      :is-dark="isDark"
      @launch="showDashboard"
      @home="showHome"
      @faqs="showFAQs"
    />

    <!-- ════ DASHBOARD ════ -->
    <div
      v-else-if="currentView === 'dashboard'"
      class="dashboard-shell"
      :class="{ 'sidebar-drawer-open': sidebarOpen, 'compact-shell': isCompactViewport }"
    >

      <!-- Header -->
      <header class="dash-header">
        <div class="header-brand">
          <button @click="toggleSidebar" class="icon-btn menu-btn" aria-label="Toggle map controls">
            <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
            </svg>
          </button>
          <button @click="showHome" class="home-btn" aria-label="Go to home">🏠</button>
          <div class="brand-mark-group">
            <img src="/assets/iirs.png" class="dash-logo" onerror="this.style.display='none'" />
            <span class="brand-separator"></span>
            <img src="/assets/isro.png" class="dash-logo isro-logo" onerror="this.style.display='none'" />
          </div>
        </div>

        <div class="header-right">
          <!-- Weather Widget Button -->
          <button class="weather-card" @click="toggleWeather">
            <span class="wc-icon">{{ selectedWeatherEntry ? getWeatherEmoji(selectedWeatherEntry.weathercode) : '🌤️' }}</span>
            <div class="wc-center">
              <span class="wc-location">{{ userLocationName }}</span>
              <span class="wc-date">{{ formatDisplayDate(activeWeatherDate || todayISO) }}</span>
            </div>
            <span class="wc-temp">{{ selectedWeatherEntry ? Math.round(selectedWeatherEntry.tempMax) + '°C' : '--' }}</span>
          </button>

          <button class="trend-btn" @click="toggleChart" :class="{ active: chartVisible }">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 19h16M7 16V9M12 16V5M17 16v-7"/>
            </svg>
            <span>{{ chartVisible ? 'Back' : 'Crop trends' }}</span>
          </button>

          <!-- Calendar Button -->
          <button class="calendar-btn" @click="toggleCalendar" :class="{ active: calendarOpen }">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="3" y="4" width="18" height="18" rx="2" stroke-width="2"/>
              <path stroke-linecap="round" stroke-width="2" d="M16 2v4M8 2v4M3 10h18"/>
            </svg>
            <span>{{ selectedCalendarDate ? formatDisplayDate(selectedCalendarDate) : 'Today' }}</span>
          </button>
        </div>
      </header>

      <!-- Body -->
      <div class="dash-body">
        <div v-if="sidebarOpen" class="sidebar-scrim" @click="closeSidebar" aria-hidden="true"></div>

        <!-- Sidebar -->
        <aside class="sidebar-panel" :class="sidebarOpen ? 'open' : 'closed'">
          <div class="sidebar-content">
            <div class="sidebar-top">
              <div>
                <p class="sidebar-eyebrow">Workspace</p>
                <h2>Map Controls</h2>
              </div>
              <button class="sidebar-collapse-btn" type="button" @click="closeSidebar" aria-label="Collapse sidebar">
                <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 18l-6-6 6-6"/>
                </svg>
              </button>
            </div>
            <p class="sidebar-section-label">Raster Layers</p>
            <div v-for="layer in layerDefs" :key="layer.key">
              <div class="layer-card" :class="{ active: layers[layer.key] }" @click="toggleMapLayer(layer.key)">
                <div class="layer-left">
                  <span class="layer-ico">{{ layer.icon || layer.key.slice(0, 2).toUpperCase() }}</span>
                  <div>
                    <p class="layer-key">{{ layer.key.toUpperCase() }}</p>
                    <p class="layer-name">{{ layer.name }}</p>
                  </div>
                </div>
                <div class="toggle-track" :class="{ on: layers[layer.key] }">
                  <div class="toggle-thumb" :class="{ on: layers[layer.key] }"></div>
                </div>
              </div>
              <div v-if="layers[layer.key]" class="legend-strip">
                <div class="legend-labels-horizontal">
                  <span>{{ layer.minLabel }}</span>
                  <span>{{ layer.midLabel }}</span>
                  <span>{{ layer.maxLabel }}</span>
                </div>
                <div class="legend-bar-horizontal" :style="{ background: getLegendGradient(layer.key) }"
                  @mousemove="(e) => showLegendValue(e, layer.key)"
                  @mouseleave="legendValue = null"
                  @click="filterByLegendRange($event, layer.key)">
                </div>
              </div>
            </div>
            <div class="ctrl-card">
              <div class="ctrl-row">
                <span>Layer Opacity</span>
                <span class="ctrl-val">{{ Math.round(opacity * 100) }}%</span>
              </div>
              <input type="range" v-model="opacity" min="0" max="1" step="0.05" class="range-slider" />
            </div>
          </div>
        </aside>

        <!-- Map area -->
        <div class="map-area">
          <MapView
            ref="mapViewRef"
            :layers="layers"
            :forecastDays="forecastDays"
            :slot="currentslot"
            :opacity="Number(opacity)"
            :selectedDate="selectedCalendarDate"
            :selectedLayer="selectedMapLayer"
            :weatherSummary="mapWeatherSummary"
            :weatherOpen="weatherOpen"
            :isDark="isDark"
            :chartVisible="chartVisible"
            @calendar-open="calendarOpen = true"
            :availableDates="availableDates"
            @location-selected="handleLocationSelected"
            @open-weather="weatherOpen = true"
            @update:weather-open="weatherOpen = $event"
            @update:chart-visible="chartVisible = $event"
          />
          <div v-if="legendValue" class="legend-tooltip" :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }">
            {{ legendValue }}
          </div>
        </div>
      </div>

      <!-- ════ SENTINEL CALENDAR OVERLAY ════ -->
      <Teleport to="body">
        <div v-if="calendarOpen" class="calendar-float-panel" :style="{ zIndex: appWidgetZ.calendar }">
          <div class="cal-panel">
            <div class="cal-header">
              <div class="cal-title-row">
                <svg width="16" height="16" fill="none" stroke="#00D4A8" viewBox="0 0 24 24">
                  <rect x="3" y="4" width="18" height="18" rx="2" stroke-width="2"/>
                  <path stroke-linecap="round" stroke-width="2" d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
                <span class="cal-title">Field Data Calendar</span>
                <button class="cal-close" @click="calendarOpen = false">×</button>
              </div>
              <p class="cal-subtitle">
                Rabi season (Nov–Apr) · Last {{ maxSeasons }} seasons · {{ availableDates.length }} dates
              </p>

              <!-- ── Season + Month filter row ── -->
              <div class="cal-filter-row">
                <!-- Season selector -->
                <div class="cal-filter-group">
                  <label class="cal-filter-label">Season</label>
                  <div class="cal-filter-chips">
                    <button
                      class="cal-chip"
                      :class="{ active: calFilterSeason === null }"
                      @click="calFilterSeason = null">All</button>
                    <button
                      v-for="s in availableSeasons" :key="s.season"
                      class="cal-chip"
                      :class="{ active: calFilterSeason === s.season }"
                      @click="calFilterSeason = calFilterSeason === s.season ? null : s.season">
                      {{ s.season }}
                      <span class="cal-chip-count">{{ s.count }}</span>
                    </button>
                  </div>
                </div>

                <!-- Month selector (only Nov–Apr shown) -->
                <div class="cal-filter-group">
                  <label class="cal-filter-label">Month</label>
                  <div class="cal-filter-chips">
                    <button
                      class="cal-chip"
                      :class="{ active: calFilterMonth === null }"
                      @click="calFilterMonth = null">All</button>
                    <button
                      v-for="m in seasonMonthDefs" :key="m.num"
                      class="cal-chip"
                      :class="{ active: calFilterMonth === m.num }"
                      @click="calFilterMonth = calFilterMonth === m.num ? null : m.num">
                      {{ m.label }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="calLoading" class="cal-loading">
              <div class="cal-spinner"></div>
              <span>Fetching available dates…</span>
            </div>

            <div v-else class="cal-scroll">
              <div v-if="calMonths.length === 0" class="cal-empty">
                <span>No data for selected filter</span>
              </div>
              <div v-for="month in calMonths" :key="month.key" class="cal-month">
                <div class="cal-month-header">
                  <p class="cal-month-label">{{ month.label }}</p>
                  <span class="cal-month-season-badge">{{ month.season }}</span>
                </div>
                <div class="cal-grid">
                  <div v-for="d in ['Su','Mo','Tu','We','Th','Fr','Sa']" :key="d" class="cal-dow">{{ d }}</div>
                  <div v-for="n in month.startOffset" :key="'e'+n" class="cal-day cal-day-empty"></div>
                  <div v-for="day in month.days" :key="day.iso" class="cal-day" :class="{
                      'cal-day-has-data':     day.hasData,
                      'cal-day-has-forecast': day.hasForecast,
                      'cal-day-selected':     day.iso === selectedCalendarDate,
                      'cal-day-today':        day.isToday,
                      'cal-day-future':       day.isFuture,
                      'cal-day-past':         day.isPast,
                      'cal-day-clickable':    day.isSelectable,
                    }" :title="getCalendarDayTitle(day)"
                    @click="day.isSelectable && selectCalendarDate(day.iso)">
                    <span class="cal-day-num">{{ day.day }}</span>
                    <span v-if="day.hasData" class="cal-day-dot"></span>
                    <span v-else-if="day.hasForecast" class="cal-day-dot cal-day-dot-forecast"></span>
                  </div>
                </div>
              </div>
            </div>

            <div class="cal-footer" v-if="selectedCalendarDate">
              <div class="cal-sel-info">
                <span>Selected: <strong>{{ formatDisplayDate(selectedCalendarDate) }}</strong></span>
                <span class="cal-sel-badge" v-if="selectedDateLayers.length">Data available</span>
                <span class="cal-sel-badge cal-sel-badge-forecast" v-else-if="selectedDateHasForecast">Forecast</span>
                <span class="cal-sel-badge cal-sel-badge-past" v-if="selectedDateIsPast">Historical</span>
              </div>
              <button class="cal-clear-btn" @click="clearCalendarSelection">Clear</button>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, onUnmounted, watch } from 'vue'
import Home from './components/Home.vue'
import MapView from './components/MapView.vue'
import DOCsView from './components/DOCsView.vue'
import FAQsView from './components/FAQsView.vue'

const currentView = ref('home')
const isDark = ref(true)
const sidebarOpen = ref(true)
const isCompactViewport = ref(false)
const mapViewRef = ref(null)

function showDOCs()      { currentView.value = 'docs' }
function showHome()      { currentView.value = 'home' }
function showDashboard() {
  currentView.value = 'dashboard'
  syncResponsiveShell()
}
function showFAQs()      { currentView.value = 'faqs' }

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function closeSidebar() {
  sidebarOpen.value = false
}

function syncResponsiveShell() {
  if (typeof window === 'undefined') return
  const compact = window.matchMedia('(max-width: 900px)').matches
  const changedToCompact = compact && compact !== isCompactViewport.value
  isCompactViewport.value = compact
  if (changedToCompact && currentView.value === 'dashboard') {
    sidebarOpen.value = false
  }
}

// ── Layer state — now includes ETc ────────────────────────────────────────
const layers     = reactive({ savi: false, kc: false, etc: false,cwr: false, iwr: false})
const selectedMapLayer = ref(null)
const forecastDays = ref('today')
const opacity    = ref(1.0)
const chartVisible = ref(false)
const legendValue = ref(null)
const tooltipX   = ref(0)
const tooltipY   = ref(0)
const appWidgetZ = reactive({ calendar: 5200 })

// ── Sentinel Calendar State ───────────────────────────────────────────────
const calendarOpen          = ref(false)
const calLoading            = ref(false)
const availableDates        = ref([])      // [{date, slot, season, layers}]
const selectedCalendarDate  = ref(null)
const currentslot           = ref('today')
const API_BASE              = (process.env.VUE_APP_API_BASE || '').replace(/\/$/, '')
const todayISO = formatLocalISO(new Date())

function bringAppWidgetToFront(widget) {
  const nextZ = Math.max(...Object.values(appWidgetZ)) + 1
  appWidgetZ[widget] = nextZ
}

function toggleChart() {
  chartVisible.value = !chartVisible.value
}

function toggleCalendar() {
  calendarOpen.value = !calendarOpen.value
  if (calendarOpen.value) bringAppWidgetToFront('calendar')
}

function toggleMapLayer(key) {
  layers[key] = !layers[key]

  if (layers[key]) {
    selectedMapLayer.value = key
    return
  }

  if (selectedMapLayer.value === key) {
    selectedMapLayer.value = Object.keys(layers).find(layerKey => layers[layerKey]) || null
  }
}

watch(sidebarOpen, () => {
  window.setTimeout(() => {
    mapViewRef.value?.invalidateMapSize?.()
  }, 320)
})

// ── Calendar filter state ─────────────────────────────────────────────────
const calFilterSeason = ref(null)   // e.g. '2024-25' or null = all
const calFilterMonth  = ref(null)   // e.g. 11 (Nov) or null = all
const maxSeasons      = ref(5)

// Months in Rabi season, in natural display order (Nov, Dec, Jan, Feb, Mar, Apr)
const SEASON_MONTH_ORDER = [11, 12, 1, 2, 3, 4]
const MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const seasonMonthDefs = SEASON_MONTH_ORDER.map(n => ({ num: n, label: MONTH_NAMES[n] }))

// Seasons present in current data (from API)
const availableSeasons = ref([])   // [{season, count}]

// ── Weather State ─────────────────────────────────────────────────────────
const weatherOpen             = ref(false)
const weatherLoading          = ref(false)
const weatherData             = ref(null)
const weatherFetchedAt        = ref(null)
const userLocationName        = ref('Udham Singh Nagar')
const weatherLat              = ref(28.98)
const weatherLon              = ref(79.40)
const selectedWeatherDateIndex = ref(0)
const activeWeatherDate       = ref(null)
const WEATHER_FORECAST_DAYS   = 7

const weatherSources = [
  { name: 'Open-Meteo', desc: 'Daily forecast', url: 'https://open-meteo.com', icon: '🌤️' },
  { name: 'Nominatim',  desc: 'Location names', url: 'https://nominatim.openstreetmap.org', icon: '🗺️' },
  { name: 'W3C Geolocation', desc: 'Browser location', url: 'https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API', icon: '📡' },
]

const weatherEntries = computed(() => {
  if (!weatherData.value) return []
  const d = weatherData.value.daily
  return d.time.map((date, i) => ({
    date,
    weathercode: d.weathercode[i],
    tempMax:     d.temperature_2m_max[i],
    tempMin:     d.temperature_2m_min[i],
    precip:      d.precipitation_sum?.[i] ?? 0,
    windspeed:   d.windspeed_10m_max?.[i] ?? '—',
    uvindex:     d.uv_index_max?.[i] ?? '—',
  }))
})

const selectedWeatherEntry = computed(() => weatherEntries.value[selectedWeatherDateIndex.value] ?? null)
const mapWeatherSummary = computed(() => ({
  date: activeWeatherDate.value || todayISO,
  dateLabel: activeWeatherDate.value ? formatWeatherFullDate(activeWeatherDate.value) : 'Today',
  location: userLocationName.value || 'Selected Location'
}))

// ── Geocoding ─────────────────────────────────────────────────────────────
async function reverseGeocode(lat, lon) {
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=10&addressdetails=1`,
      { headers: { 'Accept-Language': 'en' } }
    )
    const data = await res.json()
    const addr = data.address
    return addr.city || addr.town || addr.village || addr.suburb || addr.district || addr.county || 'Selected Location'
  } catch { return `${lat.toFixed(2)}, ${lon.toFixed(2)}` }
}

// ── Weather fetch ─────────────────────────────────────────────────────────
async function fetchWeather(lat = null, lon = null) {
  weatherLoading.value = true
  try {
    if (lat === null || lon === null) {
      try {
        const pos = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 6000 }))
        lat = pos.coords.latitude
        lon = pos.coords.longitude
        weatherLat.value = lat
        weatherLon.value = lon
        userLocationName.value = await reverseGeocode(lat, lon)
      } catch {
        lat = weatherLat.value
        lon = weatherLon.value
        userLocationName.value = 'Udham Singh Nagar'
      }
    }
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,uv_index_max&timezone=auto&forecast_days=${WEATHER_FORECAST_DAYS}`
    const res = await fetch(url)
    weatherData.value = await res.json()
    weatherFetchedAt.value = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
    syncSelectedWeatherDate()
  } catch (e) {
    console.error('Weather fetch error:', e)
    weatherData.value = null
  } finally { weatherLoading.value = false }
}

async function fetchHistoricalWeather(lat, lon, historyDate) {
  weatherLoading.value = true
  try {
    const historyUrl = `https://archive-api.open-meteo.com/v1/archive?latitude=${lat}&longitude=${lon}&start_date=${historyDate}&end_date=${historyDate}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max&timezone=auto`
    const historyRes = await fetch(historyUrl)
    const historyData = await historyRes.json()

    const nextDay = new Date(historyDate)
    nextDay.setDate(nextDay.getDate() + 1)
    const forecastUrl = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,uv_index_max&timezone=auto&forecast_days=7`
    const forecastRes = await fetch(forecastUrl)
    const forecastData = await forecastRes.json()

    if (historyData.daily && forecastData.daily) {
      weatherData.value = {
        daily: {
          time:               [...historyData.daily.time,               ...forecastData.daily.time],
          weathercode:        [...historyData.daily.weathercode,        ...forecastData.daily.weathercode],
          temperature_2m_max: [...historyData.daily.temperature_2m_max, ...forecastData.daily.temperature_2m_max],
          temperature_2m_min: [...historyData.daily.temperature_2m_min, ...forecastData.daily.temperature_2m_min],
          precipitation_sum:  [...(historyData.daily.precipitation_sum || []), ...(forecastData.daily.precipitation_sum || [])],
          windspeed_10m_max:  [...(historyData.daily.windspeed_10m_max || []), ...(forecastData.daily.windspeed_10m_max || [])],
          uv_index_max:       [...Array(historyData.daily.time.length).fill(null), ...(forecastData.daily.uv_index_max || [])],
        }
      }
      weatherFetchedAt.value = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
      syncSelectedWeatherDate()
    }
  } catch (e) {
    console.error('Historical weather fetch error:', e)
    weatherData.value = null
  } finally { weatherLoading.value = false }
}

async function relocateWeather() {
  weatherData.value = null
  userLocationName.value = 'Locating…'
  await fetchWeather()
}

async function toggleWeather() {
  calendarOpen.value = false
  weatherOpen.value = !weatherOpen.value
  if (!weatherOpen.value) return
  if (!weatherData.value) { await fetchWeather(); return }
  syncSelectedWeatherDate()
}

async function handleLocationSelected({ lat, lon }) {
  weatherLat.value = lat
  weatherLon.value = lon
  userLocationName.value = await reverseGeocode(lat, lon)
  await fetchWeather(lat, lon)
}

// ── Weather helpers ───────────────────────────────────────────────────────
function getWeatherEmoji(code) {
  if (code === 0) return '☀️'
  if (code <= 3)  return '⛅'
  if (code <= 48) return '🌫️'
  if (code <= 55) return '🌧️'
  if (code <= 65) return '🌦️'
  if (code <= 75) return '❄️'
  if (code <= 82) return '🌦️'
  if (code <= 99) return '⛈️'
  return '🌤️'
}

function getWeatherDesc(code) {
  const map = {
    0:'Clear Sky',1:'Mainly Clear',2:'Partly Cloudy',3:'Overcast',
    45:'Foggy',48:'Rime Fog',51:'Light Drizzle',53:'Moderate Drizzle',55:'Dense Drizzle',
    61:'Slight Rain',63:'Moderate Rain',65:'Heavy Rain',
    71:'Slight Snowfall',73:'Moderate Snowfall',75:'Heavy Snowfall',
    95:'Thunderstorm',96:'T-storm + Hail',99:'T-storm + Hail'
  }
  return map[code] || 'Cloudy'
}

function formatWeatherDay(dateStr) {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short' })
}
function formatLocalISO(date) {
  return date.toLocaleDateString('en-CA')
}
function formatWeatherFullDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const today = new Date(); today.setHours(0,0,0,0)
  const target = new Date(d); target.setHours(0,0,0,0)
  if (target.toDateString() === today.toDateString()) return 'Today'
  const diff = Math.round((target - today) / 86400000)
  if (diff < 0) {
    const abs = Math.abs(diff)
    if (abs === 1) return 'Yesterday'
    if (abs <= 7)  return `${abs} days ago`
    return d.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })
  }
  if (diff === 1) return 'Tomorrow'
  return d.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })
}

function selectWeatherEntry(date, index) {
  activeWeatherDate.value = date
  selectedWeatherDateIndex.value = index
}

// ── Calendar helpers ──────────────────────────────────────────────────────
const today = ref(new Date())
const forecastDateSet = computed(() => new Set(weatherEntries.value.map(e => e.date)))

const availableDateSet = computed(() => {
  const map = new Map()
  availableDates.value.forEach(d => map.set(d.date, { layers: Array.isArray(d.layers) ? d.layers : [], slot: d.slot, season: d.season }))
  return map
})

const dateToSlotMap = computed(() => {
  const map = new Map()
  availableDates.value.forEach(d => map.set(d.date, d.slot))
  return map
})

const selectedDateLayers       = computed(() => availableDateSet.value.get(selectedCalendarDate.value)?.layers ?? [])
const selectedDateHasForecast  = computed(() => forecastDateSet.value.has(selectedCalendarDate.value))
const selectedDateIsPast = computed(() => {
  if (!selectedCalendarDate.value) return false
  const selected = new Date(selectedCalendarDate.value + 'T00:00:00')
  const todayDate = new Date(today.value); todayDate.setHours(0,0,0,0)
  return selected < todayDate
})

// ── Get season ID for a JS Date (mirrors Python logic) ───────────────────
function getSeasonId(date) {
  const m = date.getMonth() + 1  // 1-based
  const y = date.getFullYear()
  if (m >= 11) return `${y}-${String(y + 1).slice(-2)}`
  if (m <= 4)  return `${y - 1}-${String(y).slice(-2)}`
  return null   // off-season
}

// ── Build calendar months — seasonal-filtered, with optional filter ───────
const calMonths = computed(() => {
  const months = []
  const todayISO = today.value.toLocaleDateString('en-CA')

  // Collect all data dates that pass the active filters
  const filteredDataDates = new Set(
    availableDates.value
      .filter(d => {
        if (calFilterSeason.value && d.season !== calFilterSeason.value) return false
        if (calFilterMonth.value) {
          const m = parseInt(d.date.split('-')[1], 10)
          if (m !== calFilterMonth.value) return false
        }
        return true
      })
      .map(d => d.date)
  )

  if (filteredDataDates.size === 0 && calFilterSeason.value === null && calFilterMonth.value === null) {
    // No data at all — show nothing
    return []
  }

  // Determine date range to render
  // If filters are active, show only months containing filtered dates
  // Otherwise show all months from oldest to newest available date
  let datesToRender = [...filteredDataDates].sort()

  if (datesToRender.length === 0) return []

  const startDate = new Date(datesToRender[0] + 'T00:00:00')
  const endDate   = new Date(datesToRender[datesToRender.length - 1] + 'T00:00:00')

  // Walk month by month
  const cursor = new Date(startDate.getFullYear(), startDate.getMonth(), 1)
  const endMonth = new Date(endDate.getFullYear(), endDate.getMonth(), 1)

  while (cursor <= endMonth) {
    const y = cursor.getFullYear()
    const m = cursor.getMonth() + 1   // 1-based

    // Skip off-season months (May–Oct) unless filter explicitly selects one
    if (![11, 12, 1, 2, 3, 4].includes(m)) {
      cursor.setMonth(cursor.getMonth() + 1)
      continue
    }
    if (calFilterMonth.value && m !== calFilterMonth.value) {
      cursor.setMonth(cursor.getMonth() + 1)
      continue
    }

    const monthKey = `${y}-${m}`
    const seasonId = getSeasonId(cursor) || '—'

    if (calFilterSeason.value && seasonId !== calFilterSeason.value) {
      cursor.setMonth(cursor.getMonth() + 1)
      continue
    }

    const daysInMonth  = new Date(y, cursor.getMonth() + 1, 0).getDate()
    const startOffset  = new Date(y, cursor.getMonth(), 1).getDay()

    const days = []
    for (let day = 1; day <= daysInMonth; day++) {
      const iso = `${y}-${String(m).padStart(2,'0')}-${String(day).padStart(2,'0')}`
      const dateObj = new Date(iso + 'T00:00:00')
      const dateInfo = availableDateSet.value.get(iso)
      const hasForecast = forecastDateSet.value.has(iso)
      const isPast    = dateObj < today.value
      const isFuture  = dateObj > today.value
      const hasData   = filteredDataDates.has(iso) && !!dateInfo

      days.push({
        iso,
        day,
        hasData,
        hasForecast,
        isSelectable: hasData || (hasForecast && !isFuture) || isPast,
        layers:   dateInfo?.layers ?? [],
        isToday:  iso === todayISO,
        isFuture,
        isPast,
      })
    }

    months.push({
      key:         monthKey,
      label:       new Date(y, cursor.getMonth(), 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }),
      season:      seasonId,
      year:        y,
      monthNum:    m,
      startOffset,
      days,
    })

    cursor.setMonth(cursor.getMonth() + 1)
  }

  // Newest season/month first
  return months.reverse()
})

function selectCalendarDate(iso) {
  selectedCalendarDate.value = iso
  currentslot.value = dateToSlotMap.value.get(iso) || 'today'
  calendarOpen.value = false

  const selectedDate = new Date(iso + 'T00:00:00')
  const todayDate    = new Date(); todayDate.setHours(0,0,0,0)
  const isPastDate   = selectedDate < todayDate

  if (isPastDate) {
    fetchHistoricalWeather(weatherLat.value, weatherLon.value, iso)
    activeWeatherDate.value = iso
  } else {
    activeWeatherDate.value = forecastDateSet.value.has(iso) ? iso : todayISO
    syncSelectedWeatherDate()
  }
  if (forecastDateSet.value.has(iso) || isPastDate) weatherOpen.value = true
}

function syncSelectedWeatherDate() {
  if (weatherEntries.value.length === 0) { selectedWeatherDateIndex.value = 0; return }
  const targetDate = activeWeatherDate.value && forecastDateSet.value.has(activeWeatherDate.value)
    ? activeWeatherDate.value : todayISO
  const index = weatherEntries.value.findIndex(e => e.date === targetDate)
  selectedWeatherDateIndex.value = index === -1 ? 0 : index
  activeWeatherDate.value = weatherEntries.value[selectedWeatherDateIndex.value]?.date ?? todayISO
}

function getCalendarDayTitle(day) {
  if (day.hasData)     return `Data available — ${day.layers.join(', ')}`
  if (day.hasForecast) return 'Weather forecast available'
  if (day.isFuture)    return 'Future date'
  return 'No data'
}

function formatDisplayDate(iso) {
  if (!iso) return ''
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function clearCalendarSelection() {
  selectedCalendarDate.value = null
  currentslot.value = 'today'
  activeWeatherDate.value = todayISO
  syncSelectedWeatherDate()
}

// ── Load history from API ─────────────────────────────────────────────────
async function loadHistory() {
  try {
    const res  = await fetch(`${API_BASE}/api/history`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()

    maxSeasons.value     = data.max_seasons ?? 5
    availableSeasons.value = data.seasons ?? []

    availableDates.value = (data.slots || []).map(s => ({
      date:   s.date,
      slot:   s.slot,
      season: s.season || '',
      layers: Object.keys(s.obs_means || {}).filter(k => s.obs_means[k] !== null),
    }))

    if (availableDates.value.length > 0) {
      const latest = availableDates.value[0]
      selectedCalendarDate.value = latest.date
      currentslot.value = latest.slot || 'today'
    }
  } catch (e) {
    console.error('History fetch error:', e)
    availableDates.value = []
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(async () => {
  syncResponsiveShell()
  window.addEventListener('resize', syncResponsiveShell, { passive: true })
  await loadHistory()
  await fetchWeather()
})

onUnmounted(() => {
  window.removeEventListener('resize', syncResponsiveShell)
})

watch(weatherOpen, async (open) => {
  if (!open) return
  if (!weatherData.value) { await fetchWeather(); return }
  syncSelectedWeatherDate()
})

watch(calendarOpen, async (open) => {
  if (!open) return
  weatherOpen.value = false
  calLoading.value  = true
  try {
    await loadHistory()
  } finally {
    calLoading.value = false
  }
})

// ── Layer colour stops — one entry per SLD step ──────────────────────────────
const layerColorStops = {
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
  // ── Kc: 0.0 → 1.5, step 0.1 (16 stops) ─────────────────────────────────────────
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
  // ── CWR: 0 → 150 mm, multi-color palette ─────────────────────────────────────
  cwr: [
  // ── CWR 0→150  navy→cyan→lime→yellow→orange→red→purple
  { value:    0.0, color: '#0A0A2E' },
  { value:    0.1, color: '#0A0B2F' },
  { value:    0.2, color: '#0A0B30' },
  { value:    0.3, color: '#0A0C31' },
  { value:    0.4, color: '#0A0C32' },
  { value:    0.5, color: '#0A0D33' },
  { value:    0.6, color: '#0A0D34' },
  { value:    0.7, color: '#090E35' },
  { value:    0.8, color: '#090E36' },
  { value:    0.9, color: '#090F37' },
  { value:    1.0, color: '#2bfb46' },
  { value:    1.1, color: '#091039' },
  { value:    1.2, color: '#09103A' },
  { value:    1.3, color: '#09113C' },
  { value:    1.4, color: '#09113D' },
  { value:    1.5, color: '#09123E' },
  { value:    1.6, color: '#09123F' },
  { value:    1.7, color: '#091340' },
  { value:    1.8, color: '#1f20b9' },
  { value:    1.9, color: '#081442' },
  { value:    2.0, color: '#081443' },
  { value:    2.1, color: '#081544' },
  { value:    2.2, color: '#081545' },
  { value:    2.3, color: '#081646' },
  { value:    2.4, color: '#081647' },
  { value:    2.5, color: '#081748' },
  { value:    2.6, color: '#081749' },
  { value:    2.7, color: '#08184A' },
  { value:    2.8, color: '#08184B' },
  { value:    2.9, color: '#08194C' },
  { value:    3.0, color: '#08194D' },
  { value:    3.1, color: '#071A4E' },
  { value:    3.2, color: '#071A4F' },
  { value:    3.3, color: '#071B50' },
  { value:    3.4, color: '#071B51' },
  { value:    3.5, color: '#071C52' },
  { value:    3.6, color: '#071C53' },
  { value:    3.7, color: '#071D55' },
  { value:    3.8, color: '#071D56' },
  { value:    3.9, color: '#071E57' },
  { value:    4.0, color: '#071E58' },
  { value:    4.1, color: '#071F59' },
  { value:    4.2, color: '#061F5A' },
  { value:    4.3, color: '#06205B' },
  { value:    4.4, color: '#06205C' },
  { value:    4.5, color: '#06215D' },
  { value:    4.6, color: '#06215E' },
  { value:    4.7, color: '#06225F' },
  { value:    4.8, color: '#062260' },
  { value:    4.9, color: '#062361' },
  { value:    5.0, color: '#062362' },
  { value:    5.1, color: '#062463' },
  { value:    5.2, color: '#062464' },
  { value:    5.3, color: '#062565' },
  { value:    5.4, color: '#062566' },
  { value:    5.5, color: '#052667' },
  { value:    5.6, color: '#052668' },
  { value:    5.7, color: '#052769' },
  { value:    5.8, color: '#05276A' },
  { value:    5.9, color: '#05286B' },
  { value:    6.0, color: '#05286C' },
  { value:    6.1, color: '#05296E' },
  { value:    6.2, color: '#052A6F' },
  { value:    6.3, color: '#052A70' },
  { value:    6.4, color: '#052B71' },
  { value:    6.5, color: '#052B72' },
  { value:    6.6, color: '#052C73' },
  { value:    6.7, color: '#042C74' },
  { value:    6.8, color: '#042D75' },
  { value:    6.9, color: '#042D76' },
  { value:    7.0, color: '#042E77' },
  { value:    7.1, color: '#042E78' },
  { value:    7.2, color: '#042F79' },
  { value:    7.3, color: '#042F7A' },
  { value:    7.4, color: '#04307B' },
  { value:    7.5, color: '#04307C' },
  { value:    7.6, color: '#04317D' },
  { value:    7.7, color: '#04317E' },
  { value:    7.8, color: '#04327F' },
  { value:    7.9, color: '#033280' },
  { value:    8.0, color: '#033381' },
  { value:    8.1, color: '#033382' },
  { value:    8.2, color: '#033483' },
  { value:    8.3, color: '#033484' },
  { value:    8.4, color: '#033586' },
  { value:    8.5, color: '#033587' },
  { value:    8.6, color: '#033688' },
  { value:    8.7, color: '#033689' },
  { value:    8.8, color: '#03378A' },
  { value:    8.9, color: '#03378B' },
  { value:    9.0, color: '#02388C' },
  { value:    9.1, color: '#02388D' },
  { value:    9.2, color: '#02398E' },
  { value:    9.3, color: '#02398F' },
  { value:    9.4, color: '#023A90' },
  { value:    9.5, color: '#023A91' },
  { value:    9.6, color: '#023B92' },
  { value:    9.7, color: '#023B93' },
  { value:    9.8, color: '#023C94' },
  { value:    9.9, color: '#023C95' },
  { value:   10.0, color: '#023D96' },
  { value:   10.1, color: '#023D97' },
  { value:   10.2, color: '#023E98' },
  { value:   10.3, color: '#013E99' },
  { value:   10.4, color: '#013F9A' },
  { value:   10.5, color: '#013F9B' },
  { value:   10.6, color: '#01409C' },
  { value:   10.7, color: '#01409D' },
  { value:   10.8, color: '#01419E' },
  { value:   10.9, color: '#0141A0' },
  { value:   11.0, color: '#0142A1' },
  { value:   11.1, color: '#0142A2' },
  { value:   11.2, color: '#0143A3' },
  { value:   11.3, color: '#0143A4' },
  { value:   11.4, color: '#0044A5' },
  { value:   11.5, color: '#0044A6' },
  { value:   11.6, color: '#0045A7' },
  { value:   11.7, color: '#0045A8' },
  { value:   11.8, color: '#0046A9' },
  { value:   11.9, color: '#0046AA' },
  { value:   12.0, color: '#0047AB' },
  { value:   12.1, color: '#0048AC' },
  { value:   12.2, color: '#0049AC' },
  { value:   12.3, color: '#0049AD' },
  { value:   12.4, color: '#004AAD' },
  { value:   12.5, color: '#004BAE' },
  { value:   12.6, color: '#004CAE' },
  { value:   12.7, color: '#004DAF' },
  { value:   12.8, color: '#004DAF' },
  { value:   12.9, color: '#004EB0' },
  { value:   13.0, color: '#004FB1' },
  { value:   13.1, color: '#0050B1' },
  { value:   13.2, color: '#0051B2' },
  { value:   13.3, color: '#0051B2' },
  { value:   13.4, color: '#0052B3' },
  { value:   13.5, color: '#0053B3' },
  { value:   13.6, color: '#0054B4' },
  { value:   13.7, color: '#0055B5' },
  { value:   13.8, color: '#0055B5' },
  { value:   13.9, color: '#0056B6' },
  { value:   14.0, color: '#0057B6' },
  { value:   14.1, color: '#0058B7' },
  { value:   14.2, color: '#0059B7' },
  { value:   14.3, color: '#0059B8' },
  { value:   14.4, color: '#005AB8' },
  { value:   14.5, color: '#005BB9' },
  { value:   14.6, color: '#005CBA' },
  { value:   14.7, color: '#005DBA' },
  { value:   14.8, color: '#005DBB' },
  { value:   14.9, color: '#005EBB' },
  { value:   15.0, color: '#005FBC' },
  { value:   15.1, color: '#0060BC' },
  { value:   15.2, color: '#0061BD' },
  { value:   15.3, color: '#0061BD' },
  { value:   15.4, color: '#0062BE' },
  { value:   15.5, color: '#0063BF' },
  { value:   15.6, color: '#0064BF' },
  { value:   15.7, color: '#0065C0' },
  { value:   15.8, color: '#0065C0' },
  { value:   15.9, color: '#0066C1' },
  { value:   16.0, color: '#0067C1' },
  { value:   16.1, color: '#0068C2' },
  { value:   16.2, color: '#0069C3' },
  { value:   16.3, color: '#0069C3' },
  { value:   16.4, color: '#006AC4' },
  { value:   16.5, color: '#006BC4' },
  { value:   16.6, color: '#006CC5' },
  { value:   16.7, color: '#006DC5' },
  { value:   16.8, color: '#006DC6' },
  { value:   16.9, color: '#006EC6' },
  { value:   17.0, color: '#006FC7' },
  { value:   17.1, color: '#0070C8' },
  { value:   17.2, color: '#0071C8' },
  { value:   17.3, color: '#0071C9' },
  { value:   17.4, color: '#0072C9' },
  { value:   17.5, color: '#0073CA' },
  { value:   17.6, color: '#0074CA' },
  { value:   17.7, color: '#0075CB' },
  { value:   17.8, color: '#0075CB' },
  { value:   17.9, color: '#0076CC' },
  { value:   18.0, color: '#0077CD' },
  { value:   18.1, color: '#0078CD' },
  { value:   18.2, color: '#0079CE' },
  { value:   18.3, color: '#0079CE' },
  { value:   18.4, color: '#007ACF' },
  { value:   18.5, color: '#007BCF' },
  { value:   18.6, color: '#007CD0' },
  { value:   18.7, color: '#007DD1' },
  { value:   18.8, color: '#007DD1' },
  { value:   18.9, color: '#007ED2' },
  { value:   19.0, color: '#007FD2' },
  { value:   19.1, color: '#0080D3' },
  { value:   19.2, color: '#0081D3' },
  { value:   19.3, color: '#0081D4' },
  { value:   19.4, color: '#0082D4' },
  { value:   19.5, color: '#0083D5' },
  { value:   19.6, color: '#0084D6' },
  { value:   19.7, color: '#0085D6' },
  { value:   19.8, color: '#0085D7' },
  { value:   19.9, color: '#0086D7' },
  { value:   20.0, color: '#0087D8' },
  { value:   20.1, color: '#0088D8' },
  { value:   20.2, color: '#0089D9' },
  { value:   20.3, color: '#0089D9' },
  { value:   20.4, color: '#008ADA' },
  { value:   20.5, color: '#008BDB' },
  { value:   20.6, color: '#008CDB' },
  { value:   20.7, color: '#008DDC' },
  { value:   20.8, color: '#008DDC' },
  { value:   20.9, color: '#008EDD' },
  { value:   21.0, color: '#008FDD' },
  { value:   21.1, color: '#0090DE' },
  { value:   21.2, color: '#0091DF' },
  { value:   21.3, color: '#0091DF' },
  { value:   21.4, color: '#0092E0' },
  { value:   21.5, color: '#0093E0' },
  { value:   21.6, color: '#0094E1' },
  { value:   21.7, color: '#0095E1' },
  { value:   21.8, color: '#0095E2' },
  { value:   21.9, color: '#0096E2' },
  { value:   22.0, color: '#0097E3' },
  { value:   22.1, color: '#0098E4' },
  { value:   22.2, color: '#0099E4' },
  { value:   22.3, color: '#0099E5' },
  { value:   22.4, color: '#009AE5' },
  { value:   22.5, color: '#009BE6' },
  { value:   22.6, color: '#009CE6' },
  { value:   22.7, color: '#009DE7' },
  { value:   22.8, color: '#009DE7' },
  { value:   22.9, color: '#009EE8' },
  { value:   23.0, color: '#009FE9' },
  { value:   23.1, color: '#00A0E9' },
  { value:   23.2, color: '#00A1EA' },
  { value:   23.3, color: '#00A1EA' },
  { value:   23.4, color: '#00A2EB' },
  { value:   23.5, color: '#00A3EB' },
  { value:   23.6, color: '#00A4EC' },
  { value:   23.7, color: '#00A5ED' },
  { value:   23.8, color: '#00A5ED' },
  { value:   23.9, color: '#00A6EE' },
  { value:   24.0, color: '#00A7EE' },
  { value:   24.1, color: '#00A8EF' },
  { value:   24.2, color: '#00A9EF' },
  { value:   24.3, color: '#00A9F0' },
  { value:   24.4, color: '#00AAF0' },
  { value:   24.5, color: '#00ABF1' },
  { value:   24.6, color: '#00ACF2' },
  { value:   24.7, color: '#00ADF2' },
  { value:   24.8, color: '#00ADF3' },
  { value:   24.9, color: '#00AEF3' },
  { value:   25.0, color: '#00AFF4' },
  { value:   25.1, color: '#00B0F4' },
  { value:   25.2, color: '#00B1F5' },
  { value:   25.3, color: '#00B1F5' },
  { value:   25.4, color: '#00B2F6' },
  { value:   25.5, color: '#00B3F7' },
  { value:   25.6, color: '#00B4F7' },
  { value:   25.7, color: '#00B5F8' },
  { value:   25.8, color: '#00B5F8' },
  { value:   25.9, color: '#00B6F9' },
  { value:   26.0, color: '#00B7F9' },
  { value:   26.1, color: '#00B8FA' },
  { value:   26.2, color: '#00B9FB' },
  { value:   26.3, color: '#00B9FB' },
  { value:   26.4, color: '#00BAFC' },
  { value:   26.5, color: '#00BBFC' },
  { value:   26.6, color: '#00BCFD' },
  { value:   26.7, color: '#00BDFD' },
  { value:   26.8, color: '#00BDFE' },
  { value:   26.9, color: '#00BEFE' },
  { value:   27.0, color: '#00BFFF' },
  { value:   27.1, color: '#00BFFE' },
  { value:   27.2, color: '#00C0FE' },
  { value:   27.3, color: '#00C0FD' },
  { value:   27.4, color: '#00C0FD' },
  { value:   27.5, color: '#00C1FC' },
  { value:   27.6, color: '#00C1FC' },
  { value:   27.7, color: '#00C1FB' },
  { value:   27.8, color: '#00C2FB' },
  { value:   27.9, color: '#00C2FA' },
  { value:   28.0, color: '#00C3FA' },
  { value:   28.1, color: '#00C3F9' },
  { value:   28.2, color: '#00C3F9' },
  { value:   28.3, color: '#00C4F8' },
  { value:   28.4, color: '#00C4F8' },
  { value:   28.5, color: '#00C4F7' },
  { value:   28.6, color: '#00C5F6' },
  { value:   28.7, color: '#00C5F6' },
  { value:   28.8, color: '#00C5F5' },
  { value:   28.9, color: '#00C6F5' },
  { value:   29.0, color: '#00C6F4' },
  { value:   29.1, color: '#00C6F4' },
  { value:   29.2, color: '#00C7F3' },
  { value:   29.3, color: '#00C7F3' },
  { value:   29.4, color: '#00C8F2' },
  { value:   29.5, color: '#00C8F2' },
  { value:   29.6, color: '#00C8F1' },
  { value:   29.7, color: '#00C9F1' },
  { value:   29.8, color: '#00C9F0' },
  { value:   29.9, color: '#00C9F0' },
  { value:   30.0, color: '#00CAEF' },
  { value:   30.1, color: '#00CAEE' },
  { value:   30.2, color: '#00CAEE' },
  { value:   30.3, color: '#00CBED' },
  { value:   30.4, color: '#00CBED' },
  { value:   30.5, color: '#00CBEC' },
  { value:   30.6, color: '#00CCEC' },
  { value:   30.7, color: '#00CCEB' },
  { value:   30.8, color: '#00CDEB' },
  { value:   30.9, color: '#00CDEA' },
  { value:   31.0, color: '#00CDEA' },
  { value:   31.1, color: '#00CEE9' },
  { value:   31.2, color: '#00CEE9' },
  { value:   31.3, color: '#00CEE8' },
  { value:   31.4, color: '#00CFE8' },
  { value:   31.5, color: '#00CFE7' },
  { value:   31.6, color: '#00CFE6' },
  { value:   31.7, color: '#00D0E6' },
  { value:   31.8, color: '#00D0E5' },
  { value:   31.9, color: '#00D0E5' },
  { value:   32.0, color: '#00D1E4' },
  { value:   32.1, color: '#00D1E4' },
  { value:   32.2, color: '#00D1E3' },
  { value:   32.3, color: '#00D2E3' },
  { value:   32.4, color: '#00D2E2' },
  { value:   32.5, color: '#00D3E2' },
  { value:   32.6, color: '#00D3E1' },
  { value:   32.7, color: '#00D3E1' },
  { value:   32.8, color: '#00D4E0' },
  { value:   32.9, color: '#00D4E0' },
  { value:   33.0, color: '#00D4DF' },
  { value:   33.1, color: '#00D5DE' },
  { value:   33.2, color: '#00D5DE' },
  { value:   33.3, color: '#00D5DD' },
  { value:   33.4, color: '#00D6DD' },
  { value:   33.5, color: '#00D6DC' },
  { value:   33.6, color: '#00D6DC' },
  { value:   33.7, color: '#00D7DB' },
  { value:   33.8, color: '#00D7DB' },
  { value:   33.9, color: '#00D8DA' },
  { value:   34.0, color: '#00D8DA' },
  { value:   34.1, color: '#00D8D9' },
  { value:   34.2, color: '#00D9D9' },
  { value:   34.3, color: '#00D9D8' },
  { value:   34.4, color: '#00D9D8' },
  { value:   34.5, color: '#00DAD7' },
  { value:   34.6, color: '#00DAD6' },
  { value:   34.7, color: '#00DAD6' },
  { value:   34.8, color: '#00DBD5' },
  { value:   34.9, color: '#00DBD5' },
  { value:   35.0, color: '#00DBD4' },
  { value:   35.1, color: '#00DCD4' },
  { value:   35.2, color: '#00DCD3' },
  { value:   35.3, color: '#00DDD3' },
  { value:   35.4, color: '#00DDD2' },
  { value:   35.5, color: '#00DDD2' },
  { value:   35.6, color: '#00DED1' },
  { value:   35.7, color: '#00DED1' },
  { value:   35.8, color: '#00DED0' },
  { value:   35.9, color: '#00DFD0' },
  { value:   36.0, color: '#00DFCF' },
  { value:   36.1, color: '#00DFCE' },
  { value:   36.2, color: '#00E0CE' },
  { value:   36.3, color: '#00E0CD' },
  { value:   36.4, color: '#00E0CD' },
  { value:   36.5, color: '#00E1CC' },
  { value:   36.6, color: '#00E1CC' },
  { value:   36.7, color: '#00E1CB' },
  { value:   36.8, color: '#00E2CB' },
  { value:   36.9, color: '#00E2CA' },
  { value:   37.0, color: '#00E3CA' },
  { value:   37.1, color: '#00E3C9' },
  { value:   37.2, color: '#00E3C9' },
  { value:   37.3, color: '#00E4C8' },
  { value:   37.4, color: '#00E4C8' },
  { value:   37.5, color: '#00E4C7' },
  { value:   37.6, color: '#00E5C6' },
  { value:   37.7, color: '#00E5C6' },
  { value:   37.8, color: '#00E5C5' },
  { value:   37.9, color: '#00E6C5' },
  { value:   38.0, color: '#00E6C4' },
  { value:   38.1, color: '#00E6C4' },
  { value:   38.2, color: '#00E7C3' },
  { value:   38.3, color: '#00E7C3' },
  { value:   38.4, color: '#00E8C2' },
  { value:   38.5, color: '#00E8C2' },
  { value:   38.6, color: '#00E8C1' },
  { value:   38.7, color: '#00E9C1' },
  { value:   38.8, color: '#00E9C0' },
  { value:   38.9, color: '#00E9C0' },
  { value:   39.0, color: '#00EABF' },
  { value:   39.1, color: '#00EABE' },
  { value:   39.2, color: '#00EABE' },
  { value:   39.3, color: '#00EBBD' },
  { value:   39.4, color: '#00EBBD' },
  { value:   39.5, color: '#00EBBC' },
  { value:   39.6, color: '#00ECBC' },
  { value:   39.7, color: '#00ECBB' },
  { value:   39.8, color: '#00EDBB' },
  { value:   39.9, color: '#00EDBA' },
  { value:   40.0, color: '#00EDBA' },
  { value:   40.1, color: '#00EEB9' },
  { value:   40.2, color: '#00EEB9' },
  { value:   40.3, color: '#00EEB8' },
  { value:   40.4, color: '#00EFB8' },
  { value:   40.5, color: '#00EFB7' },
  { value:   40.6, color: '#00EFB6' },
  { value:   40.7, color: '#00F0B6' },
  { value:   40.8, color: '#00F0B5' },
  { value:   40.9, color: '#00F0B5' },
  { value:   41.0, color: '#00F1B4' },
  { value:   41.1, color: '#00F1B4' },
  { value:   41.2, color: '#00F1B3' },
  { value:   41.3, color: '#00F2B3' },
  { value:   41.4, color: '#00F2B2' },
  { value:   41.5, color: '#00F3B2' },
  { value:   41.6, color: '#00F3B1' },
  { value:   41.7, color: '#00F3B1' },
  { value:   41.8, color: '#00F4B0' },
  { value:   41.9, color: '#00F4B0' },
  { value:   42.0, color: '#00F4AF' },
  { value:   42.1, color: '#00F5AE' },
  { value:   42.2, color: '#00F5AE' },
  { value:   42.3, color: '#00F5AD' },
  { value:   42.4, color: '#00F6AD' },
  { value:   42.5, color: '#00F6AC' },
  { value:   42.6, color: '#00F6AC' },
  { value:   42.7, color: '#00F7AB' },
  { value:   42.8, color: '#00F7AB' },
  { value:   42.9, color: '#00F8AA' },
  { value:   43.0, color: '#00F8AA' },
  { value:   43.1, color: '#00F8A9' },
  { value:   43.2, color: '#00F9A9' },
  { value:   43.3, color: '#00F9A8' },
  { value:   43.4, color: '#00F9A8' },
  { value:   43.5, color: '#00FAA7' },
  { value:   43.6, color: '#00FAA6' },
  { value:   43.7, color: '#00FAA6' },
  { value:   43.8, color: '#00FBA5' },
  { value:   43.9, color: '#00FBA5' },
  { value:   44.0, color: '#00FBA4' },
  { value:   44.1, color: '#00FCA4' },
  { value:   44.2, color: '#00FCA3' },
  { value:   44.3, color: '#00FDA3' },
  { value:   44.4, color: '#00FDA2' },
  { value:   44.5, color: '#00FDA2' },
  { value:   44.6, color: '#00FEA1' },
  { value:   44.7, color: '#00FEA1' },
  { value:   44.8, color: '#00FEA0' },
  { value:   44.9, color: '#00FFA0' },
  { value:   45.0, color: '#00FF9F' },
  { value:   45.1, color: '#01FF9E' },
  { value:   45.2, color: '#02FF9D' },
  { value:   45.3, color: '#03FF9C' },
  { value:   45.4, color: '#04FF9B' },
  { value:   45.5, color: '#05FF9B' },
  { value:   45.6, color: '#06FF9A' },
  { value:   45.7, color: '#07FF99' },
  { value:   45.8, color: '#08FF98' },
  { value:   45.9, color: '#08FF97' },
  { value:   46.0, color: '#09FF96' },
  { value:   46.1, color: '#0AFF95' },
  { value:   46.2, color: '#0BFF94' },
  { value:   46.3, color: '#0CFF94' },
  { value:   46.4, color: '#0DFF93' },
  { value:   46.5, color: '#0EFF92' },
  { value:   46.6, color: '#0FFF91' },
  { value:   46.7, color: '#10FF90' },
  { value:   46.8, color: '#11FF8F' },
  { value:   46.9, color: '#12FF8E' },
  { value:   47.0, color: '#13FF8D' },
  { value:   47.1, color: '#14FF8C' },
  { value:   47.2, color: '#15FF8C' },
  { value:   47.3, color: '#16FF8B' },
  { value:   47.4, color: '#17FF8A' },
  { value:   47.5, color: '#18FF89' },
  { value:   47.6, color: '#19FF88' },
  { value:   47.7, color: '#1AFF87' },
  { value:   47.8, color: '#1AFF86' },
  { value:   47.9, color: '#1BFF85' },
  { value:   48.0, color: '#1CFF84' },
  { value:   48.1, color: '#1DFF84' },
  { value:   48.2, color: '#1EFF83' },
  { value:   48.3, color: '#1FFF82' },
  { value:   48.4, color: '#20FF81' },
  { value:   48.5, color: '#21FF80' },
  { value:   48.6, color: '#22FF7F' },
  { value:   48.7, color: '#23FF7E' },
  { value:   48.8, color: '#24FF7D' },
  { value:   48.9, color: '#25FF7D' },
  { value:   49.0, color: '#26FF7C' },
  { value:   49.1, color: '#27FF7B' },
  { value:   49.2, color: '#28FF7A' },
  { value:   49.3, color: '#29FF79' },
  { value:   49.4, color: '#2AFF78' },
  { value:   49.5, color: '#2AFF77' },
  { value:   49.6, color: '#2BFF76' },
  { value:   49.7, color: '#2CFF75' },
  { value:   49.8, color: '#2DFF75' },
  { value:   49.9, color: '#2EFF74' },
  { value:   50.0, color: '#2FFF73' },
  { value:   50.1, color: '#30FF72' },
  { value:   50.2, color: '#31FF71' },
  { value:   50.3, color: '#32FF70' },
  { value:   50.4, color: '#33FF6F' },
  { value:   50.5, color: '#34FF6E' },
  { value:   50.6, color: '#35FF6E' },
  { value:   50.7, color: '#36FF6D' },
  { value:   50.8, color: '#37FF6C' },
  { value:   50.9, color: '#38FF6B' },
  { value:   51.0, color: '#39FF6A' },
  { value:   51.1, color: '#3AFF69' },
  { value:   51.2, color: '#3BFF68' },
  { value:   51.3, color: '#3BFF67' },
  { value:   51.4, color: '#3CFF66' },
  { value:   51.5, color: '#3DFF66' },
  { value:   51.6, color: '#3EFF65' },
  { value:   51.7, color: '#3FFF64' },
  { value:   51.8, color: '#40FF63' },
  { value:   51.9, color: '#41FF62' },
  { value:   52.0, color: '#42FF61' },
  { value:   52.1, color: '#43FF60' },
  { value:   52.2, color: '#44FF5F' },
  { value:   52.3, color: '#45FF5F' },
  { value:   52.4, color: '#46FF5E' },
  { value:   52.5, color: '#47FF5D' },
  { value:   52.6, color: '#48FF5C' },
  { value:   52.7, color: '#49FF5B' },
  { value:   52.8, color: '#4AFF5A' },
  { value:   52.9, color: '#4BFF59' },
  { value:   53.0, color: '#4CFF58' },
  { value:   53.1, color: '#4DFF57' },
  { value:   53.2, color: '#4DFF57' },
  { value:   53.3, color: '#4EFF56' },
  { value:   53.4, color: '#4FFF55' },
  { value:   53.5, color: '#50FF54' },
  { value:   53.6, color: '#51FF53' },
  { value:   53.7, color: '#52FF52' },
  { value:   53.8, color: '#53FF51' },
  { value:   53.9, color: '#54FF50' },
  { value:   54.0, color: '#55FF50' },
  { value:   54.1, color: '#56FF4F' },
  { value:   54.2, color: '#57FF4E' },
  { value:   54.3, color: '#58FF4D' },
  { value:   54.4, color: '#59FF4C' },
  { value:   54.5, color: '#5AFF4B' },
  { value:   54.6, color: '#5BFF4A' },
  { value:   54.7, color: '#5CFF49' },
  { value:   54.8, color: '#5DFF48' },
  { value:   54.9, color: '#5DFF48' },
  { value:   55.0, color: '#5EFF47' },
  { value:   55.1, color: '#5FFF46' },
  { value:   55.2, color: '#60FF45' },
  { value:   55.3, color: '#61FF44' },
  { value:   55.4, color: '#62FF43' },
  { value:   55.5, color: '#63FF42' },
  { value:   55.6, color: '#64FF41' },
  { value:   55.7, color: '#65FF40' },
  { value:   55.8, color: '#66FF40' },
  { value:   55.9, color: '#67FF3F' },
  { value:   56.0, color: '#68FF3E' },
  { value:   56.1, color: '#69FF3D' },
  { value:   56.2, color: '#6AFF3C' },
  { value:   56.3, color: '#6BFF3B' },
  { value:   56.4, color: '#6CFF3A' },
  { value:   56.5, color: '#6DFF39' },
  { value:   56.6, color: '#6EFF39' },
  { value:   56.7, color: '#6FFF38' },
  { value:   56.8, color: '#6FFF37' },
  { value:   56.9, color: '#70FF36' },
  { value:   57.0, color: '#71FF35' },
  { value:   57.1, color: '#72FF34' },
  { value:   57.2, color: '#73FF33' },
  { value:   57.3, color: '#74FF32' },
  { value:   57.4, color: '#75FF31' },
  { value:   57.5, color: '#76FF31' },
  { value:   57.6, color: '#77FF30' },
  { value:   57.7, color: '#78FF2F' },
  { value:   57.8, color: '#79FF2E' },
  { value:   57.9, color: '#7AFF2D' },
  { value:   58.0, color: '#7BFF2C' },
  { value:   58.1, color: '#7CFF2B' },
  { value:   58.2, color: '#7DFF2A' },
  { value:   58.3, color: '#7EFF2A' },
  { value:   58.4, color: '#7FFF29' },
  { value:   58.5, color: '#80FF28' },
  { value:   58.6, color: '#80FF27' },
  { value:   58.7, color: '#81FF26' },
  { value:   58.8, color: '#82FF25' },
  { value:   58.9, color: '#83FF24' },
  { value:   59.0, color: '#84FF23' },
  { value:   59.1, color: '#85FF22' },
  { value:   59.2, color: '#86FF22' },
  { value:   59.3, color: '#87FF21' },
  { value:   59.4, color: '#88FF20' },
  { value:   59.5, color: '#89FF1F' },
  { value:   59.6, color: '#8AFF1E' },
  { value:   59.7, color: '#8BFF1D' },
  { value:   59.8, color: '#8CFF1C' },
  { value:   59.9, color: '#8DFF1B' },
  { value:   60.0, color: '#8EFF1A' },
  { value:   60.1, color: '#8FFF1A' },
  { value:   60.2, color: '#90FF19' },
  { value:   60.3, color: '#90FF18' },
  { value:   60.4, color: '#91FF17' },
  { value:   60.5, color: '#92FF16' },
  { value:   60.6, color: '#93FF15' },
  { value:   60.7, color: '#94FF14' },
  { value:   60.8, color: '#95FF13' },
  { value:   60.9, color: '#96FF13' },
  { value:   61.0, color: '#97FF12' },
  { value:   61.1, color: '#98FF11' },
  { value:   61.2, color: '#99FF10' },
  { value:   61.3, color: '#9AFF0F' },
  { value:   61.4, color: '#9BFF0E' },
  { value:   61.5, color: '#9CFF0D' },
  { value:   61.6, color: '#9DFF0C' },
  { value:   61.7, color: '#9EFF0B' },
  { value:   61.8, color: '#9FFF0B' },
  { value:   61.9, color: '#A0FF0A' },
  { value:   62.0, color: '#A1FF09' },
  { value:   62.1, color: '#A2FF08' },
  { value:   62.2, color: '#A2FF07' },
  { value:   62.3, color: '#A3FF06' },
  { value:   62.4, color: '#A4FF05' },
  { value:   62.5, color: '#A5FF04' },
  { value:   62.6, color: '#A6FF04' },
  { value:   62.7, color: '#A7FF03' },
  { value:   62.8, color: '#A8FF02' },
  { value:   62.9, color: '#A9FF01' },
  { value:   63.0, color: '#AAFF00' },
  { value:   63.1, color: '#AAFF00' },
  { value:   63.2, color: '#ABFF00' },
  { value:   63.3, color: '#ABFF00' },
  { value:   63.4, color: '#ACFE00' },
  { value:   63.5, color: '#ACFE00' },
  { value:   63.6, color: '#ADFE00' },
  { value:   63.7, color: '#ADFE00' },
  { value:   63.8, color: '#ADFE00' },
  { value:   63.9, color: '#AEFE00' },
  { value:   64.0, color: '#AEFD00' },
  { value:   64.1, color: '#AFFD00' },
  { value:   64.2, color: '#AFFD00' },
  { value:   64.3, color: '#B0FD00' },
  { value:   64.4, color: '#B0FD00' },
  { value:   64.5, color: '#B1FD00' },
  { value:   64.6, color: '#B1FC00' },
  { value:   64.7, color: '#B1FC00' },
  { value:   64.8, color: '#B2FC00' },
  { value:   64.9, color: '#B2FC00' },
  { value:   65.0, color: '#B3FC00' },
  { value:   65.1, color: '#B3FC00' },
  { value:   65.2, color: '#B4FC00' },
  { value:   65.3, color: '#B4FB00' },
  { value:   65.4, color: '#B4FB00' },
  { value:   65.5, color: '#B5FB00' },
  { value:   65.6, color: '#B5FB00' },
  { value:   65.7, color: '#B6FB00' },
  { value:   65.8, color: '#B6FB00' },
  { value:   65.9, color: '#B7FA00' },
  { value:   66.0, color: '#B7FA00' },
  { value:   66.1, color: '#B8FA00' },
  { value:   66.2, color: '#B8FA00' },
  { value:   66.3, color: '#B8FA00' },
  { value:   66.4, color: '#B9FA00' },
  { value:   66.5, color: '#B9F900' },
  { value:   66.6, color: '#BAF900' },
  { value:   66.7, color: '#BAF900' },
  { value:   66.8, color: '#BBF900' },
  { value:   66.9, color: '#BBF900' },
  { value:   67.0, color: '#BBF900' },
  { value:   67.1, color: '#BCF800' },
  { value:   67.2, color: '#BCF800' },
  { value:   67.3, color: '#BDF800' },
  { value:   67.4, color: '#BDF800' },
  { value:   67.5, color: '#BEF800' },
  { value:   67.6, color: '#BEF800' },
  { value:   67.7, color: '#BEF800' },
  { value:   67.8, color: '#BFF700' },
  { value:   67.9, color: '#BFF700' },
  { value:   68.0, color: '#C0F700' },
  { value:   68.1, color: '#C0F700' },
  { value:   68.2, color: '#C1F700' },
  { value:   68.3, color: '#C1F700' },
  { value:   68.4, color: '#C2F600' },
  { value:   68.5, color: '#C2F600' },
  { value:   68.6, color: '#C2F600' },
  { value:   68.7, color: '#C3F600' },
  { value:   68.8, color: '#C3F600' },
  { value:   68.9, color: '#C4F600' },
  { value:   69.0, color: '#C4F500' },
  { value:   69.1, color: '#C5F500' },
  { value:   69.2, color: '#C5F500' },
  { value:   69.3, color: '#C5F500' },
  { value:   69.4, color: '#C6F500' },
  { value:   69.5, color: '#C6F500' },
  { value:   69.6, color: '#C7F500' },
  { value:   69.7, color: '#C7F400' },
  { value:   69.8, color: '#C8F400' },
  { value:   69.9, color: '#C8F400' },
  { value:   70.0, color: '#C9F400' },
  { value:   70.1, color: '#C9F400' },
  { value:   70.2, color: '#C9F400' },
  { value:   70.3, color: '#CAF300' },
  { value:   70.4, color: '#CAF300' },
  { value:   70.5, color: '#CBF300' },
  { value:   70.6, color: '#CBF300' },
  { value:   70.7, color: '#CCF300' },
  { value:   70.8, color: '#CCF300' },
  { value:   70.9, color: '#CCF200' },
  { value:   71.0, color: '#CDF200' },
  { value:   71.1, color: '#CDF200' },
  { value:   71.2, color: '#CEF200' },
  { value:   71.3, color: '#CEF200' },
  { value:   71.4, color: '#CFF200' },
  { value:   71.5, color: '#CFF100' },
  { value:   71.6, color: '#CFF100' },
  { value:   71.7, color: '#D0F100' },
  { value:   71.8, color: '#D0F100' },
  { value:   71.9, color: '#D1F100' },
  { value:   72.0, color: '#D1F100' },
  { value:   72.1, color: '#D2F100' },
  { value:   72.2, color: '#D2F000' },
  { value:   72.3, color: '#D3F000' },
  { value:   72.4, color: '#D3F000' },
  { value:   72.5, color: '#D3F000' },
  { value:   72.6, color: '#D4F000' },
  { value:   72.7, color: '#D4F000' },
  { value:   72.8, color: '#D5EF00' },
  { value:   72.9, color: '#D5EF00' },
  { value:   73.0, color: '#D6EF00' },
  { value:   73.1, color: '#D6EF00' },
  { value:   73.2, color: '#D6EF00' },
  { value:   73.3, color: '#D7EF00' },
  { value:   73.4, color: '#D7EE00' },
  { value:   73.5, color: '#D8EE00' },
  { value:   73.6, color: '#D8EE00' },
  { value:   73.7, color: '#D9EE00' },
  { value:   73.8, color: '#D9EE00' },
  { value:   73.9, color: '#DAEE00' },
  { value:   74.0, color: '#DAEE00' },
  { value:   74.1, color: '#DAED00' },
  { value:   74.2, color: '#DBED00' },
  { value:   74.3, color: '#DBED00' },
  { value:   74.4, color: '#DCED00' },
  { value:   74.5, color: '#DCED00' },
  { value:   74.6, color: '#DDED00' },
  { value:   74.7, color: '#DDEC00' },
  { value:   74.8, color: '#DDEC00' },
  { value:   74.9, color: '#DEEC00' },
  { value:   75.0, color: '#DEEC00' },
  { value:   75.1, color: '#DFEC00' },
  { value:   75.2, color: '#DFEC00' },
  { value:   75.3, color: '#E0EB00' },
  { value:   75.4, color: '#E0EB00' },
  { value:   75.5, color: '#E0EB00' },
  { value:   75.6, color: '#E1EB00' },
  { value:   75.7, color: '#E1EB00' },
  { value:   75.8, color: '#E2EB00' },
  { value:   75.9, color: '#E2EA00' },
  { value:   76.0, color: '#E3EA00' },
  { value:   76.1, color: '#E3EA00' },
  { value:   76.2, color: '#E4EA00' },
  { value:   76.3, color: '#E4EA00' },
  { value:   76.4, color: '#E4EA00' },
  { value:   76.5, color: '#E5EA00' },
  { value:   76.6, color: '#E5E900' },
  { value:   76.7, color: '#E6E900' },
  { value:   76.8, color: '#E6E900' },
  { value:   76.9, color: '#E7E900' },
  { value:   77.0, color: '#E7E900' },
  { value:   77.1, color: '#E7E900' },
  { value:   77.2, color: '#E8E800' },
  { value:   77.3, color: '#E8E800' },
  { value:   77.4, color: '#E9E800' },
  { value:   77.5, color: '#E9E800' },
  { value:   77.6, color: '#EAE800' },
  { value:   77.7, color: '#EAE800' },
  { value:   77.8, color: '#EBE700' },
  { value:   77.9, color: '#EBE700' },
  { value:   78.0, color: '#EBE700' },
  { value:   78.1, color: '#ECE700' },
  { value:   78.2, color: '#ECE700' },
  { value:   78.3, color: '#EDE700' },
  { value:   78.4, color: '#EDE700' },
  { value:   78.5, color: '#EEE600' },
  { value:   78.6, color: '#EEE600' },
  { value:   78.7, color: '#EEE600' },
  { value:   78.8, color: '#EFE600' },
  { value:   78.9, color: '#EFE600' },
  { value:   79.0, color: '#F0E600' },
  { value:   79.1, color: '#F0E500' },
  { value:   79.2, color: '#F1E500' },
  { value:   79.3, color: '#F1E500' },
  { value:   79.4, color: '#F1E500' },
  { value:   79.5, color: '#F2E500' },
  { value:   79.6, color: '#F2E500' },
  { value:   79.7, color: '#F3E400' },
  { value:   79.8, color: '#F3E400' },
  { value:   79.9, color: '#F4E400' },
  { value:   80.0, color: '#F4E400' },
  { value:   80.1, color: '#F5E400' },
  { value:   80.2, color: '#F5E400' },
  { value:   80.3, color: '#F5E300' },
  { value:   80.4, color: '#F6E300' },
  { value:   80.5, color: '#F6E300' },
  { value:   80.6, color: '#F7E300' },
  { value:   80.7, color: '#F7E300' },
  { value:   80.8, color: '#F8E300' },
  { value:   80.9, color: '#F8E300' },
  { value:   81.0, color: '#F8E200' },
  { value:   81.1, color: '#F9E200' },
  { value:   81.2, color: '#F9E200' },
  { value:   81.3, color: '#FAE200' },
  { value:   81.4, color: '#FAE200' },
  { value:   81.5, color: '#FBE200' },
  { value:   81.6, color: '#FBE100' },
  { value:   81.7, color: '#FCE100' },
  { value:   81.8, color: '#FCE100' },
  { value:   81.9, color: '#FCE100' },
  { value:   82.0, color: '#FDE100' },
  { value:   82.1, color: '#FDE100' },
  { value:   82.2, color: '#FEE000' },
  { value:   82.3, color: '#FEE000' },
  { value:   82.4, color: '#FFE000' },
  { value:   82.5, color: '#FFE000' },
  { value:   82.6, color: '#FFDF00' },
  { value:   82.7, color: '#FFDF00' },
  { value:   82.8, color: '#FFDE00' },
  { value:   82.9, color: '#FFDD00' },
  { value:   83.0, color: '#FFDD00' },
  { value:   83.1, color: '#FFDC00' },
  { value:   83.2, color: '#FFDB00' },
  { value:   83.3, color: '#FFDB00' },
  { value:   83.4, color: '#FFDA00' },
  { value:   83.5, color: '#FFD900' },
  { value:   83.6, color: '#FFD900' },
  { value:   83.7, color: '#FFD800' },
  { value:   83.8, color: '#FFD700' },
  { value:   83.9, color: '#FFD700' },
  { value:   84.0, color: '#FFD600' },
  { value:   84.1, color: '#FFD500' },
  { value:   84.2, color: '#FFD400' },
  { value:   84.3, color: '#FFD400' },
  { value:   84.4, color: '#FFD300' },
  { value:   84.5, color: '#FFD200' },
  { value:   84.6, color: '#FFD200' },
  { value:   84.7, color: '#FFD100' },
  { value:   84.8, color: '#FFD000' },
  { value:   84.9, color: '#FFD000' },
  { value:   85.0, color: '#FFCF00' },
  { value:   85.1, color: '#FFCE00' },
  { value:   85.2, color: '#FFCE00' },
  { value:   85.3, color: '#FFCD00' },
  { value:   85.4, color: '#FFCC00' },
  { value:   85.5, color: '#FFCC00' },
  { value:   85.6, color: '#FFCB00' },
  { value:   85.7, color: '#FFCA00' },
  { value:   85.8, color: '#FFCA00' },
  { value:   85.9, color: '#FFC900' },
  { value:   86.0, color: '#FFC800' },
  { value:   86.1, color: '#FFC800' },
  { value:   86.2, color: '#FFC700' },
  { value:   86.3, color: '#FFC600' },
  { value:   86.4, color: '#FFC600' },
  { value:   86.5, color: '#FFC500' },
  { value:   86.6, color: '#FFC400' },
  { value:   86.7, color: '#FFC400' },
  { value:   86.8, color: '#FFC300' },
  { value:   86.9, color: '#FFC200' },
  { value:   87.0, color: '#FFC200' },
  { value:   87.1, color: '#FFC100' },
  { value:   87.2, color: '#FFC000' },
  { value:   87.3, color: '#FFBF00' },
  { value:   87.4, color: '#FFBF00' },
  { value:   87.5, color: '#FFBE00' },
  { value:   87.6, color: '#FFBD00' },
  { value:   87.7, color: '#FFBD00' },
  { value:   87.8, color: '#FFBC00' },
  { value:   87.9, color: '#FFBB00' },
  { value:   88.0, color: '#FFBB00' },
  { value:   88.1, color: '#FFBA00' },
  { value:   88.2, color: '#FFB900' },
  { value:   88.3, color: '#FFB900' },
  { value:   88.4, color: '#FFB800' },
  { value:   88.5, color: '#FFB700' },
  { value:   88.6, color: '#FFB700' },
  { value:   88.7, color: '#FFB600' },
  { value:   88.8, color: '#FFB500' },
  { value:   88.9, color: '#FFB500' },
  { value:   89.0, color: '#FFB400' },
  { value:   89.1, color: '#FFB300' },
  { value:   89.2, color: '#FFB300' },
  { value:   89.3, color: '#FFB200' },
  { value:   89.4, color: '#FFB100' },
  { value:   89.5, color: '#FFB100' },
  { value:   89.6, color: '#FFB000' },
  { value:   89.7, color: '#FFAF00' },
  { value:   89.8, color: '#FFAF00' },
  { value:   89.9, color: '#FFAE00' },
  { value:   90.0, color: '#FFAD00' },
  { value:   90.1, color: '#FFAC00' },
  { value:   90.2, color: '#FFAC00' },
  { value:   90.3, color: '#FFAB00' },
  { value:   90.4, color: '#FFAA00' },
  { value:   90.5, color: '#FFAA00' },
  { value:   90.6, color: '#FFA900' },
  { value:   90.7, color: '#FFA800' },
  { value:   90.8, color: '#FFA800' },
  { value:   90.9, color: '#FFA700' },
  { value:   91.0, color: '#FFA600' },
  { value:   91.1, color: '#FFA600' },
  { value:   91.2, color: '#FFA500' },
  { value:   91.3, color: '#FFA400' },
  { value:   91.4, color: '#FFA400' },
  { value:   91.5, color: '#FFA300' },
  { value:   91.6, color: '#FFA200' },
  { value:   91.7, color: '#FFA200' },
  { value:   91.8, color: '#FFA100' },
  { value:   91.9, color: '#FFA000' },
  { value:   92.0, color: '#FFA000' },
  { value:   92.1, color: '#FF9F00' },
  { value:   92.2, color: '#FF9E00' },
  { value:   92.3, color: '#FF9E00' },
  { value:   92.4, color: '#FF9D00' },
  { value:   92.5, color: '#FF9C00' },
  { value:   92.6, color: '#FF9C00' },
  { value:   92.7, color: '#FF9B00' },
  { value:   92.8, color: '#FF9A00' },
  { value:   92.9, color: '#FF9A00' },
  { value:   93.0, color: '#FF9900' },
  { value:   93.1, color: '#FF9800' },
  { value:   93.2, color: '#FF9700' },
  { value:   93.3, color: '#FF9700' },
  { value:   93.4, color: '#FF9600' },
  { value:   93.5, color: '#FF9500' },
  { value:   93.6, color: '#FF9500' },
  { value:   93.7, color: '#FF9400' },
  { value:   93.8, color: '#FF9300' },
  { value:   93.9, color: '#FF9300' },
  { value:   94.0, color: '#FF9200' },
  { value:   94.1, color: '#FF9100' },
  { value:   94.2, color: '#FF9100' },
  { value:   94.3, color: '#FF9000' },
  { value:   94.4, color: '#FF8F00' },
  { value:   94.5, color: '#FF8F00' },
  { value:   94.6, color: '#FF8E00' },
  { value:   94.7, color: '#FF8D00' },
  { value:   94.8, color: '#FF8D00' },
  { value:   94.9, color: '#FF8C00' },
  { value:   95.0, color: '#FF8B00' },
  { value:   95.1, color: '#FF8B00' },
  { value:   95.2, color: '#FF8A00' },
  { value:   95.3, color: '#FF8900' },
  { value:   95.4, color: '#FF8900' },
  { value:   95.5, color: '#FF8800' },
  { value:   95.6, color: '#FF8700' },
  { value:   95.7, color: '#FF8700' },
  { value:   95.8, color: '#FF8600' },
  { value:   95.9, color: '#FF8500' },
  { value:   96.0, color: '#FF8400' },
  { value:   96.1, color: '#FF8400' },
  { value:   96.2, color: '#FF8300' },
  { value:   96.3, color: '#FF8200' },
  { value:   96.4, color: '#FF8200' },
  { value:   96.5, color: '#FF8100' },
  { value:   96.6, color: '#FF8000' },
  { value:   96.7, color: '#FF8000' },
  { value:   96.8, color: '#FF7F00' },
  { value:   96.9, color: '#FF7E00' },
  { value:   97.0, color: '#FF7E00' },
  { value:   97.1, color: '#FF7D00' },
  { value:   97.2, color: '#FF7C00' },
  { value:   97.3, color: '#FF7C00' },
  { value:   97.4, color: '#FF7B00' },
  { value:   97.5, color: '#FF7A00' },
  { value:   97.6, color: '#FF7A00' },
  { value:   97.7, color: '#FF7900' },
  { value:   97.8, color: '#FF7800' },
  { value:   97.9, color: '#FF7800' },
  { value:   98.0, color: '#FF7700' },
  { value:   98.1, color: '#FF7600' },
  { value:   98.2, color: '#FF7600' },
  { value:   98.3, color: '#FF7500' },
  { value:   98.4, color: '#FF7400' },
  { value:   98.5, color: '#FF7400' },
  { value:   98.6, color: '#FF7300' },
  { value:   98.7, color: '#FF7200' },
  { value:   98.8, color: '#FF7200' },
  { value:   98.9, color: '#FF7100' },
  { value:   99.0, color: '#FF7000' },
  { value:   99.1, color: '#FF6F00' },
  { value:   99.2, color: '#FF6F00' },
  { value:   99.3, color: '#FF6E00' },
  { value:   99.4, color: '#FF6D00' },
  { value:   99.5, color: '#FF6D00' },
  { value:   99.6, color: '#FF6C00' },
  { value:   99.7, color: '#FF6B00' },
  { value:   99.8, color: '#FF6B00' },
  { value:   99.9, color: '#FF6A00' },
  { value:  100.0, color: '#FF6900' },
  { value:  100.1, color: '#FF6900' },
  { value:  100.2, color: '#FF6800' },
  { value:  100.3, color: '#FF6700' },
  { value:  100.4, color: '#FF6700' },
  { value:  100.5, color: '#FF6600' },
  { value:  100.6, color: '#FF6500' },
  { value:  100.7, color: '#FE6500' },
  { value:  100.8, color: '#FE6400' },
  { value:  100.9, color: '#FE6400' },
  { value:  101.0, color: '#FE6300' },
  { value:  101.1, color: '#FD6300' },
  { value:  101.2, color: '#FD6200' },
  { value:  101.3, color: '#FD6200' },
  { value:  101.4, color: '#FD6100' },
  { value:  101.5, color: '#FC6100' },
  { value:  101.6, color: '#FC6000' },
  { value:  101.7, color: '#FC6000' },
  { value:  101.8, color: '#FC5F00' },
  { value:  101.9, color: '#FB5F00' },
  { value:  102.0, color: '#FB5E00' },
  { value:  102.1, color: '#FB5E00' },
  { value:  102.2, color: '#FB5D00' },
  { value:  102.3, color: '#FA5D00' },
  { value:  102.4, color: '#FA5C00' },
  { value:  102.5, color: '#FA5C00' },
  { value:  102.6, color: '#FA5B00' },
  { value:  102.7, color: '#F95A00' },
  { value:  102.8, color: '#F95A00' },
  { value:  102.9, color: '#F95900' },
  { value:  103.0, color: '#F85900' },
  { value:  103.1, color: '#F85800' },
  { value:  103.2, color: '#F85800' },
  { value:  103.3, color: '#F85700' },
  { value:  103.4, color: '#F75700' },
  { value:  103.5, color: '#F75600' },
  { value:  103.6, color: '#F75600' },
  { value:  103.7, color: '#F75500' },
  { value:  103.8, color: '#F65500' },
  { value:  103.9, color: '#F65400' },
  { value:  104.0, color: '#F65400' },
  { value:  104.1, color: '#F65300' },
  { value:  104.2, color: '#F55300' },
  { value:  104.3, color: '#F55200' },
  { value:  104.4, color: '#F55200' },
  { value:  104.5, color: '#F55100' },
  { value:  104.6, color: '#F45100' },
  { value:  104.7, color: '#F45000' },
  { value:  104.8, color: '#F45000' },
  { value:  104.9, color: '#F34F00' },
  { value:  105.0, color: '#F34E00' },
  { value:  105.1, color: '#F34E00' },
  { value:  105.2, color: '#F34D00' },
  { value:  105.3, color: '#F24D00' },
  { value:  105.4, color: '#F24C00' },
  { value:  105.5, color: '#F24C00' },
  { value:  105.6, color: '#F24B00' },
  { value:  105.7, color: '#F14B00' },
  { value:  105.8, color: '#F14A00' },
  { value:  105.9, color: '#F14A00' },
  { value:  106.0, color: '#F14900' },
  { value:  106.1, color: '#F04900' },
  { value:  106.2, color: '#F04800' },
  { value:  106.3, color: '#F04800' },
  { value:  106.4, color: '#F04700' },
  { value:  106.5, color: '#EF4700' },
  { value:  106.6, color: '#EF4600' },
  { value:  106.7, color: '#EF4600' },
  { value:  106.8, color: '#EF4500' },
  { value:  106.9, color: '#EE4500' },
  { value:  107.0, color: '#EE4400' },
  { value:  107.1, color: '#EE4300' },
  { value:  107.2, color: '#ED4300' },
  { value:  107.3, color: '#ED4200' },
  { value:  107.4, color: '#ED4200' },
  { value:  107.5, color: '#ED4100' },
  { value:  107.6, color: '#EC4100' },
  { value:  107.7, color: '#EC4000' },
  { value:  107.8, color: '#EC4000' },
  { value:  107.9, color: '#EC3F00' },
  { value:  108.0, color: '#EB3F00' },
  { value:  108.1, color: '#EB3E00' },
  { value:  108.2, color: '#EB3E00' },
  { value:  108.3, color: '#EB3D00' },
  { value:  108.4, color: '#EA3D00' },
  { value:  108.5, color: '#EA3C00' },
  { value:  108.6, color: '#EA3C00' },
  { value:  108.7, color: '#EA3B00' },
  { value:  108.8, color: '#E93B00' },
  { value:  108.9, color: '#E93A00' },
  { value:  109.0, color: '#E93A00' },
  { value:  109.1, color: '#E93900' },
  { value:  109.2, color: '#E83800' },
  { value:  109.3, color: '#E83800' },
  { value:  109.4, color: '#E83700' },
  { value:  109.5, color: '#E73700' },
  { value:  109.6, color: '#E73600' },
  { value:  109.7, color: '#E73600' },
  { value:  109.8, color: '#E73500' },
  { value:  109.9, color: '#E63500' },
  { value:  110.0, color: '#E63400' },
  { value:  110.1, color: '#E63400' },
  { value:  110.2, color: '#E63300' },
  { value:  110.3, color: '#E53300' },
  { value:  110.4, color: '#E53200' },
  { value:  110.5, color: '#E53200' },
  { value:  110.6, color: '#E53100' },
  { value:  110.7, color: '#E43100' },
  { value:  110.8, color: '#E43000' },
  { value:  110.9, color: '#E43000' },
  { value:  111.0, color: '#E42F00' },
  { value:  111.1, color: '#E32F00' },
  { value:  111.2, color: '#E32E00' },
  { value:  111.3, color: '#E32E00' },
  { value:  111.4, color: '#E22D00' },
  { value:  111.5, color: '#E22C00' },
  { value:  111.6, color: '#E22C00' },
  { value:  111.7, color: '#E22B00' },
  { value:  111.8, color: '#E12B00' },
  { value:  111.9, color: '#E12A00' },
  { value:  112.0, color: '#E12A00' },
  { value:  112.1, color: '#E12900' },
  { value:  112.2, color: '#E02900' },
  { value:  112.3, color: '#E02800' },
  { value:  112.4, color: '#E02800' },
  { value:  112.5, color: '#E02700' },
  { value:  112.6, color: '#DF2700' },
  { value:  112.7, color: '#DF2600' },
  { value:  112.8, color: '#DF2600' },
  { value:  112.9, color: '#DF2500' },
  { value:  113.0, color: '#DE2500' },
  { value:  113.1, color: '#DE2400' },
  { value:  113.2, color: '#DE2400' },
  { value:  113.3, color: '#DE2300' },
  { value:  113.4, color: '#DD2300' },
  { value:  113.5, color: '#DD2200' },
  { value:  113.6, color: '#DD2100' },
  { value:  113.7, color: '#DC2100' },
  { value:  113.8, color: '#DC2000' },
  { value:  113.9, color: '#DC2000' },
  { value:  114.0, color: '#DC1F00' },
  { value:  114.1, color: '#DB1F00' },
  { value:  114.2, color: '#DB1E00' },
  { value:  114.3, color: '#DB1E00' },
  { value:  114.4, color: '#DB1D00' },
  { value:  114.5, color: '#DA1D00' },
  { value:  114.6, color: '#DA1C00' },
  { value:  114.7, color: '#DA1C00' },
  { value:  114.8, color: '#DA1B00' },
  { value:  114.9, color: '#D91B00' },
  { value:  115.0, color: '#D91A00' },
  { value:  115.1, color: '#D91A00' },
  { value:  115.2, color: '#D91900' },
  { value:  115.3, color: '#D81900' },
  { value:  115.4, color: '#D81800' },
  { value:  115.5, color: '#D81800' },
  { value:  115.6, color: '#D81700' },
  { value:  115.7, color: '#D71600' },
  { value:  115.8, color: '#D71600' },
  { value:  115.9, color: '#D71500' },
  { value:  116.0, color: '#D61500' },
  { value:  116.1, color: '#D61400' },
  { value:  116.2, color: '#D61400' },
  { value:  116.3, color: '#D61300' },
  { value:  116.4, color: '#D51300' },
  { value:  116.5, color: '#D51200' },
  { value:  116.6, color: '#D51200' },
  { value:  116.7, color: '#D51100' },
  { value:  116.8, color: '#D41100' },
  { value:  116.9, color: '#D41000' },
  { value:  117.0, color: '#D41000' },
  { value:  117.1, color: '#D40F00' },
  { value:  117.2, color: '#D30F00' },
  { value:  117.3, color: '#D30E00' },
  { value:  117.4, color: '#D30E00' },
  { value:  117.5, color: '#D30D00' },
  { value:  117.6, color: '#D20D00' },
  { value:  117.7, color: '#D20C00' },
  { value:  117.8, color: '#D20C00' },
  { value:  117.9, color: '#D10B00' },
  { value:  118.0, color: '#D10A00' },
  { value:  118.1, color: '#D10A00' },
  { value:  118.2, color: '#D10900' },
  { value:  118.3, color: '#D00900' },
  { value:  118.4, color: '#D00800' },
  { value:  118.5, color: '#D00800' },
  { value:  118.6, color: '#D00700' },
  { value:  118.7, color: '#CF0700' },
  { value:  118.8, color: '#CF0600' },
  { value:  118.9, color: '#CF0600' },
  { value:  119.0, color: '#CF0500' },
  { value:  119.1, color: '#CE0500' },
  { value:  119.2, color: '#CE0400' },
  { value:  119.3, color: '#CE0400' },
  { value:  119.4, color: '#CE0300' },
  { value:  119.5, color: '#CD0300' },
  { value:  119.6, color: '#CD0200' },
  { value:  119.7, color: '#CD0200' },
  { value:  119.8, color: '#CD0100' },
  { value:  119.9, color: '#CC0100' },
  { value:  120.0, color: '#CC0000' },
  { value:  120.1, color: '#CB0001' },
  { value:  120.2, color: '#CB0001' },
  { value:  120.3, color: '#CA0002' },
  { value:  120.4, color: '#CA0002' },
  { value:  120.5, color: '#C90003' },
  { value:  120.6, color: '#C90003' },
  { value:  120.7, color: '#C80004' },
  { value:  120.8, color: '#C80004' },
  { value:  120.9, color: '#C70005' },
  { value:  121.0, color: '#C70006' },
  { value:  121.1, color: '#C60006' },
  { value:  121.2, color: '#C60007' },
  { value:  121.3, color: '#C50007' },
  { value:  121.4, color: '#C40008' },
  { value:  121.5, color: '#C40008' },
  { value:  121.6, color: '#C30009' },
  { value:  121.7, color: '#C3000A' },
  { value:  121.8, color: '#C2000A' },
  { value:  121.9, color: '#C2000B' },
  { value:  122.0, color: '#C1000B' },
  { value:  122.1, color: '#C1000C' },
  { value:  122.2, color: '#C0000C' },
  { value:  122.3, color: '#C0000D' },
  { value:  122.4, color: '#BF000D' },
  { value:  122.5, color: '#BE000E' },
  { value:  122.6, color: '#BE000F' },
  { value:  122.7, color: '#BD000F' },
  { value:  122.8, color: '#BD0010' },
  { value:  122.9, color: '#BC0010' },
  { value:  123.0, color: '#BC0011' },
  { value:  123.1, color: '#BB0011' },
  { value:  123.2, color: '#BB0012' },
  { value:  123.3, color: '#BA0012' },
  { value:  123.4, color: '#BA0013' },
  { value:  123.5, color: '#B90014' },
  { value:  123.6, color: '#B90014' },
  { value:  123.7, color: '#B80015' },
  { value:  123.8, color: '#B70015' },
  { value:  123.9, color: '#B70016' },
  { value:  124.0, color: '#B60016' },
  { value:  124.1, color: '#B60017' },
  { value:  124.2, color: '#B50018' },
  { value:  124.3, color: '#B50018' },
  { value:  124.4, color: '#B40019' },
  { value:  124.5, color: '#B40019' },
  { value:  124.6, color: '#B3001A' },
  { value:  124.7, color: '#B3001A' },
  { value:  124.8, color: '#B2001B' },
  { value:  124.9, color: '#B2001B' },
  { value:  125.0, color: '#B1001C' },
  { value:  125.1, color: '#B0001D' },
  { value:  125.2, color: '#B0001D' },
  { value:  125.3, color: '#AF001E' },
  { value:  125.4, color: '#AF001E' },
  { value:  125.5, color: '#AE001F' },
  { value:  125.6, color: '#AE001F' },
  { value:  125.7, color: '#AD0020' },
  { value:  125.8, color: '#AD0020' },
  { value:  125.9, color: '#AC0021' },
  { value:  126.0, color: '#AC0022' },
  { value:  126.1, color: '#AB0022' },
  { value:  126.2, color: '#AB0023' },
  { value:  126.3, color: '#AA0023' },
  { value:  126.4, color: '#A90024' },
  { value:  126.5, color: '#A90024' },
  { value:  126.6, color: '#A80025' },
  { value:  126.7, color: '#A80026' },
  { value:  126.8, color: '#A70026' },
  { value:  126.9, color: '#A70027' },
  { value:  127.0, color: '#A60027' },
  { value:  127.1, color: '#A60028' },
  { value:  127.2, color: '#A50028' },
  { value:  127.3, color: '#A50029' },
  { value:  127.4, color: '#A40029' },
  { value:  127.5, color: '#A4002A' },
  { value:  127.6, color: '#A3002B' },
  { value:  127.7, color: '#A2002B' },
  { value:  127.8, color: '#A2002C' },
  { value:  127.9, color: '#A1002C' },
  { value:  128.0, color: '#A1002D' },
  { value:  128.1, color: '#A0002D' },
  { value:  128.2, color: '#A0002E' },
  { value:  128.3, color: '#9F002E' },
  { value:  128.4, color: '#9F002F' },
  { value:  128.5, color: '#9E0030' },
  { value:  128.6, color: '#9E0030' },
  { value:  128.7, color: '#9D0031' },
  { value:  128.8, color: '#9C0031' },
  { value:  128.9, color: '#9C0032' },
  { value:  129.0, color: '#9B0032' },
  { value:  129.1, color: '#9B0033' },
  { value:  129.2, color: '#9A0034' },
  { value:  129.3, color: '#9A0034' },
  { value:  129.4, color: '#990035' },
  { value:  129.5, color: '#990035' },
  { value:  129.6, color: '#980036' },
  { value:  129.7, color: '#980036' },
  { value:  129.8, color: '#970037' },
  { value:  129.9, color: '#970037' },
  { value:  130.0, color: '#960038' },
  { value:  130.1, color: '#950039' },
  { value:  130.2, color: '#950039' },
  { value:  130.3, color: '#94003A' },
  { value:  130.4, color: '#94003A' },
  { value:  130.5, color: '#93003B' },
  { value:  130.6, color: '#93003B' },
  { value:  130.7, color: '#92003C' },
  { value:  130.8, color: '#92003C' },
  { value:  130.9, color: '#91003D' },
  { value:  131.0, color: '#91003E' },
  { value:  131.1, color: '#90003E' },
  { value:  131.2, color: '#90003F' },
  { value:  131.3, color: '#8F003F' },
  { value:  131.4, color: '#8E0040' },
  { value:  131.5, color: '#8E0040' },
  { value:  131.6, color: '#8D0041' },
  { value:  131.7, color: '#8D0042' },
  { value:  131.8, color: '#8C0042' },
  { value:  131.9, color: '#8C0043' },
  { value:  132.0, color: '#8B0043' },
  { value:  132.1, color: '#8B0044' },
  { value:  132.2, color: '#8A0044' },
  { value:  132.3, color: '#8A0045' },
  { value:  132.4, color: '#890045' },
  { value:  132.5, color: '#880046' },
  { value:  132.6, color: '#880047' },
  { value:  132.7, color: '#870047' },
  { value:  132.8, color: '#870048' },
  { value:  132.9, color: '#860048' },
  { value:  133.0, color: '#860049' },
  { value:  133.1, color: '#850049' },
  { value:  133.2, color: '#85004A' },
  { value:  133.3, color: '#84004A' },
  { value:  133.4, color: '#84004B' },
  { value:  133.5, color: '#83004C' },
  { value:  133.6, color: '#83004C' },
  { value:  133.7, color: '#82004D' },
  { value:  133.8, color: '#81004D' },
  { value:  133.9, color: '#81004E' },
  { value:  134.0, color: '#80004E' },
  { value:  134.1, color: '#80004F' },
  { value:  134.2, color: '#7F0050' },
  { value:  134.3, color: '#7F0050' },
  { value:  134.4, color: '#7E0051' },
  { value:  134.5, color: '#7E0051' },
  { value:  134.6, color: '#7D0052' },
  { value:  134.7, color: '#7D0052' },
  { value:  134.8, color: '#7C0053' },
  { value:  134.9, color: '#7C0053' },
  { value:  135.0, color: '#7B0054' },
  { value:  135.1, color: '#7A0054' },
  { value:  135.2, color: '#7A0054' },
  { value:  135.3, color: '#790053' },
  { value:  135.4, color: '#780053' },
  { value:  135.5, color: '#780053' },
  { value:  135.6, color: '#770053' },
  { value:  135.7, color: '#760052' },
  { value:  135.8, color: '#760052' },
  { value:  135.9, color: '#750052' },
  { value:  136.0, color: '#750052' },
  { value:  136.1, color: '#740051' },
  { value:  136.2, color: '#730051' },
  { value:  136.3, color: '#730051' },
  { value:  136.4, color: '#720051' },
  { value:  136.5, color: '#710050' },
  { value:  136.6, color: '#710050' },
  { value:  136.7, color: '#700050' },
  { value:  136.8, color: '#6F0050' },
  { value:  136.9, color: '#6F004F' },
  { value:  137.0, color: '#6E004F' },
  { value:  137.1, color: '#6D004F' },
  { value:  137.2, color: '#6D004F' },
  { value:  137.3, color: '#6C004E' },
  { value:  137.4, color: '#6B004E' },
  { value:  137.5, color: '#6B004E' },
  { value:  137.6, color: '#6A004E' },
  { value:  137.7, color: '#6A004E' },
  { value:  137.8, color: '#69004D' },
  { value:  137.9, color: '#68004D' },
  { value:  138.0, color: '#68004D' },
  { value:  138.1, color: '#67004D' },
  { value:  138.2, color: '#66004C' },
  { value:  138.3, color: '#66004C' },
  { value:  138.4, color: '#65004C' },
  { value:  138.5, color: '#64004C' },
  { value:  138.6, color: '#64004B' },
  { value:  138.7, color: '#63004B' },
  { value:  138.8, color: '#62004B' },
  { value:  138.9, color: '#62004B' },
  { value:  139.0, color: '#61004A' },
  { value:  139.1, color: '#60004A' },
  { value:  139.2, color: '#60004A' },
  { value:  139.3, color: '#5F004A' },
  { value:  139.4, color: '#5F0049' },
  { value:  139.5, color: '#5E0049' },
  { value:  139.6, color: '#5D0049' },
  { value:  139.7, color: '#5D0049' },
  { value:  139.8, color: '#5C0048' },
  { value:  139.9, color: '#5B0048' },
  { value:  140.0, color: '#5B0048' },
  { value:  140.1, color: '#5A0048' },
  { value:  140.2, color: '#590048' },
  { value:  140.3, color: '#590047' },
  { value:  140.4, color: '#580047' },
  { value:  140.5, color: '#570047' },
  { value:  140.6, color: '#570047' },
  { value:  140.7, color: '#560046' },
  { value:  140.8, color: '#550046' },
  { value:  140.9, color: '#550046' },
  { value:  141.0, color: '#540046' },
  { value:  141.1, color: '#540045' },
  { value:  141.2, color: '#530045' },
  { value:  141.3, color: '#520045' },
  { value:  141.4, color: '#520045' },
  { value:  141.5, color: '#510044' },
  { value:  141.6, color: '#500044' },
  { value:  141.7, color: '#500044' },
  { value:  141.8, color: '#4F0044' },
  { value:  141.9, color: '#4E0043' },
  { value:  142.0, color: '#4E0043' },
  { value:  142.1, color: '#4D0043' },
  { value:  142.2, color: '#4C0043' },
  { value:  142.3, color: '#4C0042' },
  { value:  142.4, color: '#4B0042' },
  { value:  142.5, color: '#4A0042' },
  { value:  142.6, color: '#4A0042' },
  { value:  142.7, color: '#490042' },
  { value:  142.8, color: '#490041' },
  { value:  142.9, color: '#480041' },
  { value:  143.0, color: '#470041' },
  { value:  143.1, color: '#470041' },
  { value:  143.2, color: '#460040' },
  { value:  143.3, color: '#450040' },
  { value:  143.4, color: '#450040' },
  { value:  143.5, color: '#440040' },
  { value:  143.6, color: '#43003F' },
  { value:  143.7, color: '#43003F' },
  { value:  143.8, color: '#42003F' },
  { value:  143.9, color: '#41003F' },
  { value:  144.0, color: '#41003E' },
  { value:  144.1, color: '#40003E' },
  { value:  144.2, color: '#40003E' },
  { value:  144.3, color: '#3F003E' },
  { value:  144.4, color: '#3E003D' },
  { value:  144.5, color: '#3E003D' },
  { value:  144.6, color: '#3D003D' },
  { value:  144.7, color: '#3C003D' },
  { value:  144.8, color: '#3C003C' },
  { value:  144.9, color: '#3B003C' },
  { value:  145.0, color: '#3A003C' },
  { value:  145.1, color: '#3A003C' },
  { value:  145.2, color: '#39003C' },
  { value:  145.3, color: '#38003B' },
  { value:  145.4, color: '#38003B' },
  { value:  145.5, color: '#37003B' },
  { value:  145.6, color: '#36003B' },
  { value:  145.7, color: '#36003A' },
  { value:  145.8, color: '#35003A' },
  { value:  145.9, color: '#35003A' },
  { value:  146.0, color: '#34003A' },
  { value:  146.1, color: '#330039' },
  { value:  146.2, color: '#330039' },
  { value:  146.3, color: '#320039' },
  { value:  146.4, color: '#310039' },
  { value:  146.5, color: '#310038' },
  { value:  146.6, color: '#300038' },
  { value:  146.7, color: '#2F0038' },
  { value:  146.8, color: '#2F0038' },
  { value:  146.9, color: '#2E0037' },
  { value:  147.0, color: '#2D0037' },
  { value:  147.1, color: '#2D0037' },
  { value:  147.2, color: '#2C0037' },
  { value:  147.3, color: '#2B0036' },
  { value:  147.4, color: '#2B0036' },
  { value:  147.5, color: '#2A0036' },
  { value:  147.6, color: '#2A0036' },
  { value:  147.7, color: '#290036' },
  { value:  147.8, color: '#280035' },
  { value:  147.9, color: '#280035' },
  { value:  148.0, color: '#270035' },
  { value:  148.1, color: '#260035' },
  { value:  148.2, color: '#260034' },
  { value:  148.3, color: '#250034' },
  { value:  148.4, color: '#240034' },
  { value:  148.5, color: '#240034' },
  { value:  148.6, color: '#230033' },
  { value:  148.7, color: '#220033' },
  { value:  148.8, color: '#220033' },
  { value:  148.9, color: '#210033' },
  { value:  149.0, color: '#200032' },
  { value:  149.1, color: '#200032' },
  { value:  149.2, color: '#1F0032' },
  { value:  149.3, color: '#1F0032' },
  { value:  149.4, color: '#1E0031' },
  { value:  149.5, color: '#1D0031' },
  { value:  149.6, color: '#1D0031' },
  { value:  149.7, color: '#1C0031' },
  { value:  149.8, color: '#1B0030' },
  { value:  149.9, color: '#1B0030' },
  { value:  150.0, color: '#1A0030' },
  ],
  // ── IWR: 0 → 150 mm, multi-color palette ─────────────────────────────────────
  iwr: [
  // ── IWR 0→150  cream→green→teal→blue→violet→magenta→red→rust
  { value:    0.0, color: '#FFFDE7' },
  { value:    0.1, color: '#FEFDE7' },
  { value:    0.2, color: '#FEFCE6' },
  { value:    0.3, color: '#FDFCE6' },
  { value:    0.4, color: '#FDFCE5' },
  { value:    0.5, color: '#FCFCE5' },
  { value:    0.6, color: '#FBFBE4' },
  { value:    0.7, color: '#FBFBE4' },
  { value:    0.8, color: '#FAFBE4' },
  { value:    0.9, color: '#FAFBE3' },
  { value:    1.0, color: '#F9FAE3' },
  { value:    1.1, color: '#F8FAE2' },
  { value:    1.2, color: '#F8FAE2' },
  { value:    1.3, color: '#F7FAE1' },
  { value:    1.4, color: '#F7F9E1' },
  { value:    1.5, color: '#F6F9E1' },
  { value:    1.6, color: '#F5F9E0' },
  { value:    1.7, color: '#F5F9E0' },
  { value:    1.8, color: '#F4F8DF' },
  { value:    1.9, color: '#F4F8DF' },
  { value:    2.0, color: '#F3F8DE' },
  { value:    2.1, color: '#F2F8DE' },
  { value:    2.2, color: '#F2F7DE' },
  { value:    2.3, color: '#F1F7DD' },
  { value:    2.4, color: '#F1F7DD' },
  { value:    2.5, color: '#F0F6DC' },
  { value:    2.6, color: '#EFF6DC' },
  { value:    2.7, color: '#EFF6DB' },
  { value:    2.8, color: '#EEF6DB' },
  { value:    2.9, color: '#EEF5DB' },
  { value:    3.0, color: '#EDF5DA' },
  { value:    3.1, color: '#ECF5DA' },
  { value:    3.2, color: '#ECF5D9' },
  { value:    3.3, color: '#EBF4D9' },
  { value:    3.4, color: '#EBF4D8' },
  { value:    3.5, color: '#EAF4D8' },
  { value:    3.6, color: '#E9F4D8' },
  { value:    3.7, color: '#E9F3D7' },
  { value:    3.8, color: '#E8F3D7' },
  { value:    3.9, color: '#E8F3D6' },
  { value:    4.0, color: '#E7F3D6' },
  { value:    4.1, color: '#E6F2D6' },
  { value:    4.2, color: '#E6F2D5' },
  { value:    4.3, color: '#E5F2D5' },
  { value:    4.4, color: '#E5F2D4' },
  { value:    4.5, color: '#E4F1D4' },
  { value:    4.6, color: '#E3F1D3' },
  { value:    4.7, color: '#E3F1D3' },
  { value:    4.8, color: '#E2F1D3' },
  { value:    4.9, color: '#E2F0D2' },
  { value:    5.0, color: '#E1F0D2' },
  { value:    5.1, color: '#E0F0D1' },
  { value:    5.2, color: '#E0EFD1' },
  { value:    5.3, color: '#DFEFD0' },
  { value:    5.4, color: '#DFEFD0' },
  { value:    5.5, color: '#DEEFD0' },
  { value:    5.6, color: '#DDEECF' },
  { value:    5.7, color: '#DDEECF' },
  { value:    5.8, color: '#DCEECE' },
  { value:    5.9, color: '#DCEECE' },
  { value:    6.0, color: '#DBEDCD' },
  { value:    6.1, color: '#DAEDCD' },
  { value:    6.2, color: '#DAEDCD' },
  { value:    6.3, color: '#D9EDCC' },
  { value:    6.4, color: '#D9ECCC' },
  { value:    6.5, color: '#D8ECCB' },
  { value:    6.6, color: '#D7ECCB' },
  { value:    6.7, color: '#D7ECCA' },
  { value:    6.8, color: '#D6EBCA' },
  { value:    6.9, color: '#D6EBCA' },
  { value:    7.0, color: '#D5EBC9' },
  { value:    7.1, color: '#D4EBC9' },
  { value:    7.2, color: '#D4EAC8' },
  { value:    7.3, color: '#D3EAC8' },
  { value:    7.4, color: '#D3EAC7' },
  { value:    7.5, color: '#D2EAC7' },
  { value:    7.6, color: '#D1E9C7' },
  { value:    7.7, color: '#D1E9C6' },
  { value:    7.8, color: '#D0E9C6' },
  { value:    7.9, color: '#D0E8C5' },
  { value:    8.0, color: '#CFE8C5' },
  { value:    8.1, color: '#CEE8C4' },
  { value:    8.2, color: '#CEE8C4' },
  { value:    8.3, color: '#CDE7C4' },
  { value:    8.4, color: '#CDE7C3' },
  { value:    8.5, color: '#CCE7C3' },
  { value:    8.6, color: '#CBE7C2' },
  { value:    8.7, color: '#CBE6C2' },
  { value:    8.8, color: '#CAE6C1' },
  { value:    8.9, color: '#CAE6C1' },
  { value:    9.0, color: '#C9E6C1' },
  { value:    9.1, color: '#C8E5C0' },
  { value:    9.2, color: '#C8E5C0' },
  { value:    9.3, color: '#C7E5BF' },
  { value:    9.4, color: '#C7E5BF' },
  { value:    9.5, color: '#C6E4BE' },
  { value:    9.6, color: '#C5E4BE' },
  { value:    9.7, color: '#C5E4BE' },
  { value:    9.8, color: '#C4E4BD' },
  { value:    9.9, color: '#C4E3BD' },
  { value:   10.0, color: '#C3E3BC' },
  { value:   10.1, color: '#C2E3BC' },
  { value:   10.2, color: '#C2E2BB' },
  { value:   10.3, color: '#C1E2BB' },
  { value:   10.4, color: '#C1E2BB' },
  { value:   10.5, color: '#C0E2BA' },
  { value:   10.6, color: '#BFE1BA' },
  { value:   10.7, color: '#BFE1B9' },
  { value:   10.8, color: '#BEE1B9' },
  { value:   10.9, color: '#BEE1B8' },
  { value:   11.0, color: '#BDE0B8' },
  { value:   11.1, color: '#BCE0B8' },
  { value:   11.2, color: '#BCE0B7' },
  { value:   11.3, color: '#BBE0B7' },
  { value:   11.4, color: '#BBDFB6' },
  { value:   11.5, color: '#BADFB6' },
  { value:   11.6, color: '#B9DFB6' },
  { value:   11.7, color: '#B9DFB5' },
  { value:   11.8, color: '#B8DEB5' },
  { value:   11.9, color: '#B8DEB4' },
  { value:   12.0, color: '#B7DEB4' },
  { value:   12.1, color: '#B6DEB3' },
  { value:   12.2, color: '#B6DDB3' },
  { value:   12.3, color: '#B5DDB3' },
  { value:   12.4, color: '#B5DDB2' },
  { value:   12.5, color: '#B4DCB2' },
  { value:   12.6, color: '#B3DCB1' },
  { value:   12.7, color: '#B3DCB1' },
  { value:   12.8, color: '#B2DCB0' },
  { value:   12.9, color: '#B2DBB0' },
  { value:   13.0, color: '#B1DBB0' },
  { value:   13.1, color: '#B0DBAF' },
  { value:   13.2, color: '#B0DBAF' },
  { value:   13.3, color: '#AFDAAE' },
  { value:   13.4, color: '#AFDAAE' },
  { value:   13.5, color: '#AEDAAD' },
  { value:   13.6, color: '#ADDAAD' },
  { value:   13.7, color: '#ADD9AD' },
  { value:   13.8, color: '#ACD9AC' },
  { value:   13.9, color: '#ACD9AC' },
  { value:   14.0, color: '#ABD9AB' },
  { value:   14.1, color: '#AAD8AB' },
  { value:   14.2, color: '#AAD8AA' },
  { value:   14.3, color: '#A9D8AA' },
  { value:   14.4, color: '#A9D8AA' },
  { value:   14.5, color: '#A8D7A9' },
  { value:   14.6, color: '#A7D7A9' },
  { value:   14.7, color: '#A7D7A8' },
  { value:   14.8, color: '#A6D7A8' },
  { value:   14.9, color: '#A6D6A7' },
  { value:   15.0, color: '#A5D6A7' },
  { value:   15.1, color: '#A4D6A7' },
  { value:   15.2, color: '#A3D5A7' },
  { value:   15.3, color: '#A2D5A6' },
  { value:   15.4, color: '#A1D4A6' },
  { value:   15.5, color: '#A0D4A6' },
  { value:   15.6, color: '#A0D3A6' },
  { value:   15.7, color: '#9FD3A5' },
  { value:   15.8, color: '#9ED3A5' },
  { value:   15.9, color: '#9DD2A5' },
  { value:   16.0, color: '#9CD2A5' },
  { value:   16.1, color: '#9BD1A4' },
  { value:   16.2, color: '#9AD1A4' },
  { value:   16.3, color: '#99D0A4' },
  { value:   16.4, color: '#98D0A4' },
  { value:   16.5, color: '#97D0A3' },
  { value:   16.6, color: '#96CFA3' },
  { value:   16.7, color: '#95CFA3' },
  { value:   16.8, color: '#94CEA3' },
  { value:   16.9, color: '#94CEA2' },
  { value:   17.0, color: '#93CDA2' },
  { value:   17.1, color: '#92CDA2' },
  { value:   17.2, color: '#91CDA2' },
  { value:   17.3, color: '#90CCA1' },
  { value:   17.4, color: '#8FCCA1' },
  { value:   17.5, color: '#8ECBA1' },
  { value:   17.6, color: '#8DCBA1' },
  { value:   17.7, color: '#8CCAA0' },
  { value:   17.8, color: '#8BCAA0' },
  { value:   17.9, color: '#8ACAA0' },
  { value:   18.0, color: '#8AC9A0' },
  { value:   18.1, color: '#89C99F' },
  { value:   18.2, color: '#88C89F' },
  { value:   18.3, color: '#87C89F' },
  { value:   18.4, color: '#86C79F' },
  { value:   18.5, color: '#85C79E' },
  { value:   18.6, color: '#84C79E' },
  { value:   18.7, color: '#83C69E' },
  { value:   18.8, color: '#82C69E' },
  { value:   18.9, color: '#81C59D' },
  { value:   19.0, color: '#80C59D' },
  { value:   19.1, color: '#7FC49D' },
  { value:   19.2, color: '#7FC49D' },
  { value:   19.3, color: '#7EC49C' },
  { value:   19.4, color: '#7DC39C' },
  { value:   19.5, color: '#7CC39C' },
  { value:   19.6, color: '#7BC29C' },
  { value:   19.7, color: '#7AC29C' },
  { value:   19.8, color: '#79C19B' },
  { value:   19.9, color: '#78C19B' },
  { value:   20.0, color: '#77C19B' },
  { value:   20.1, color: '#76C09B' },
  { value:   20.2, color: '#75C09A' },
  { value:   20.3, color: '#74BF9A' },
  { value:   20.4, color: '#74BF9A' },
  { value:   20.5, color: '#73BE9A' },
  { value:   20.6, color: '#72BE99' },
  { value:   20.7, color: '#71BE99' },
  { value:   20.8, color: '#70BD99' },
  { value:   20.9, color: '#6FBD99' },
  { value:   21.0, color: '#6EBC98' },
  { value:   21.1, color: '#6DBC98' },
  { value:   21.2, color: '#6CBB98' },
  { value:   21.3, color: '#6BBB98' },
  { value:   21.4, color: '#6ABB97' },
  { value:   21.5, color: '#69BA97' },
  { value:   21.6, color: '#68BA97' },
  { value:   21.7, color: '#68B997' },
  { value:   21.8, color: '#67B996' },
  { value:   21.9, color: '#66B896' },
  { value:   22.0, color: '#65B896' },
  { value:   22.1, color: '#64B896' },
  { value:   22.2, color: '#63B795' },
  { value:   22.3, color: '#62B795' },
  { value:   22.4, color: '#61B695' },
  { value:   22.5, color: '#60B695' },
  { value:   22.6, color: '#5FB594' },
  { value:   22.7, color: '#5EB594' },
  { value:   22.8, color: '#5EB594' },
  { value:   22.9, color: '#5DB494' },
  { value:   23.0, color: '#5CB493' },
  { value:   23.1, color: '#5BB393' },
  { value:   23.2, color: '#5AB393' },
  { value:   23.3, color: '#59B293' },
  { value:   23.4, color: '#58B292' },
  { value:   23.5, color: '#57B292' },
  { value:   23.6, color: '#56B192' },
  { value:   23.7, color: '#55B192' },
  { value:   23.8, color: '#54B091' },
  { value:   23.9, color: '#53B091' },
  { value:   24.0, color: '#52B091' },
  { value:   24.1, color: '#52AF91' },
  { value:   24.2, color: '#51AF91' },
  { value:   24.3, color: '#50AE90' },
  { value:   24.4, color: '#4FAE90' },
  { value:   24.5, color: '#4EAD90' },
  { value:   24.6, color: '#4DAD90' },
  { value:   24.7, color: '#4CAD8F' },
  { value:   24.8, color: '#4BAC8F' },
  { value:   24.9, color: '#4AAC8F' },
  { value:   25.0, color: '#49AB8F' },
  { value:   25.1, color: '#48AB8E' },
  { value:   25.2, color: '#48AA8E' },
  { value:   25.3, color: '#47AA8E' },
  { value:   25.4, color: '#46AA8E' },
  { value:   25.5, color: '#45A98D' },
  { value:   25.6, color: '#44A98D' },
  { value:   25.7, color: '#43A88D' },
  { value:   25.8, color: '#42A88D' },
  { value:   25.9, color: '#41A78C' },
  { value:   26.0, color: '#40A78C' },
  { value:   26.1, color: '#3FA78C' },
  { value:   26.2, color: '#3EA68C' },
  { value:   26.3, color: '#3DA68B' },
  { value:   26.4, color: '#3DA58B' },
  { value:   26.5, color: '#3CA58B' },
  { value:   26.6, color: '#3BA48B' },
  { value:   26.7, color: '#3AA48A' },
  { value:   26.8, color: '#39A48A' },
  { value:   26.9, color: '#38A38A' },
  { value:   27.0, color: '#37A38A' },
  { value:   27.1, color: '#36A289' },
  { value:   27.2, color: '#35A289' },
  { value:   27.3, color: '#34A189' },
  { value:   27.4, color: '#33A189' },
  { value:   27.5, color: '#32A188' },
  { value:   27.6, color: '#31A088' },
  { value:   27.7, color: '#31A088' },
  { value:   27.8, color: '#309F88' },
  { value:   27.9, color: '#2F9F87' },
  { value:   28.0, color: '#2E9E87' },
  { value:   28.1, color: '#2D9E87' },
  { value:   28.2, color: '#2C9E87' },
  { value:   28.3, color: '#2B9D86' },
  { value:   28.4, color: '#2A9D86' },
  { value:   28.5, color: '#299C86' },
  { value:   28.6, color: '#289C86' },
  { value:   28.7, color: '#279B86' },
  { value:   28.8, color: '#269B85' },
  { value:   28.9, color: '#269B85' },
  { value:   29.0, color: '#259A85' },
  { value:   29.1, color: '#249A85' },
  { value:   29.2, color: '#239984' },
  { value:   29.3, color: '#229984' },
  { value:   29.4, color: '#219884' },
  { value:   29.5, color: '#209884' },
  { value:   29.6, color: '#1F9883' },
  { value:   29.7, color: '#1E9783' },
  { value:   29.8, color: '#1D9783' },
  { value:   29.9, color: '#1C9683' },
  { value:   30.0, color: '#1B9682' },
  { value:   30.1, color: '#1B9582' },
  { value:   30.2, color: '#1A9582' },
  { value:   30.3, color: '#199582' },
  { value:   30.4, color: '#189481' },
  { value:   30.5, color: '#179481' },
  { value:   30.6, color: '#169381' },
  { value:   30.7, color: '#159381' },
  { value:   30.8, color: '#149280' },
  { value:   30.9, color: '#139280' },
  { value:   31.0, color: '#129280' },
  { value:   31.1, color: '#119180' },
  { value:   31.2, color: '#11917F' },
  { value:   31.3, color: '#10907F' },
  { value:   31.4, color: '#0F907F' },
  { value:   31.5, color: '#0E8F7F' },
  { value:   31.6, color: '#0D8F7E' },
  { value:   31.7, color: '#0C8F7E' },
  { value:   31.8, color: '#0B8E7E' },
  { value:   31.9, color: '#0A8E7E' },
  { value:   32.0, color: '#098D7D' },
  { value:   32.1, color: '#088D7D' },
  { value:   32.2, color: '#078C7D' },
  { value:   32.3, color: '#068C7D' },
  { value:   32.4, color: '#068C7C' },
  { value:   32.5, color: '#058B7C' },
  { value:   32.6, color: '#048B7C' },
  { value:   32.7, color: '#038A7C' },
  { value:   32.8, color: '#028A7B' },
  { value:   32.9, color: '#01897B' },
  { value:   33.0, color: '#00897B' },
  { value:   33.1, color: '#00897B' },
  { value:   33.2, color: '#00897B' },
  { value:   33.3, color: '#00897C' },
  { value:   33.4, color: '#00897C' },
  { value:   33.5, color: '#00897C' },
  { value:   33.6, color: '#00897C' },
  { value:   33.7, color: '#008A7D' },
  { value:   33.8, color: '#008A7D' },
  { value:   33.9, color: '#008A7D' },
  { value:   34.0, color: '#008A7D' },
  { value:   34.1, color: '#008A7D' },
  { value:   34.2, color: '#008A7E' },
  { value:   34.3, color: '#008A7E' },
  { value:   34.4, color: '#008A7E' },
  { value:   34.5, color: '#008A7E' },
  { value:   34.6, color: '#008A7F' },
  { value:   34.7, color: '#008A7F' },
  { value:   34.8, color: '#008A7F' },
  { value:   34.9, color: '#008A7F' },
  { value:   35.0, color: '#008A80' },
  { value:   35.1, color: '#008B80' },
  { value:   35.2, color: '#008B80' },
  { value:   35.3, color: '#008B80' },
  { value:   35.4, color: '#008B80' },
  { value:   35.5, color: '#008B81' },
  { value:   35.6, color: '#008B81' },
  { value:   35.7, color: '#008B81' },
  { value:   35.8, color: '#008B81' },
  { value:   35.9, color: '#008B82' },
  { value:   36.0, color: '#008B82' },
  { value:   36.1, color: '#008B82' },
  { value:   36.2, color: '#008B82' },
  { value:   36.3, color: '#008B82' },
  { value:   36.4, color: '#008B83' },
  { value:   36.5, color: '#008C83' },
  { value:   36.6, color: '#008C83' },
  { value:   36.7, color: '#008C83' },
  { value:   36.8, color: '#008C84' },
  { value:   36.9, color: '#008C84' },
  { value:   37.0, color: '#008C84' },
  { value:   37.1, color: '#008C84' },
  { value:   37.2, color: '#008C84' },
  { value:   37.3, color: '#008C85' },
  { value:   37.4, color: '#008C85' },
  { value:   37.5, color: '#008C85' },
  { value:   37.6, color: '#008C85' },
  { value:   37.7, color: '#008C86' },
  { value:   37.8, color: '#008C86' },
  { value:   37.9, color: '#008D86' },
  { value:   38.0, color: '#008D86' },
  { value:   38.1, color: '#008D87' },
  { value:   38.2, color: '#008D87' },
  { value:   38.3, color: '#008D87' },
  { value:   38.4, color: '#008D87' },
  { value:   38.5, color: '#008D87' },
  { value:   38.6, color: '#008D88' },
  { value:   38.7, color: '#008D88' },
  { value:   38.8, color: '#008D88' },
  { value:   38.9, color: '#008D88' },
  { value:   39.0, color: '#008D89' },
  { value:   39.1, color: '#008D89' },
  { value:   39.2, color: '#008D89' },
  { value:   39.3, color: '#008E89' },
  { value:   39.4, color: '#008E89' },
  { value:   39.5, color: '#008E8A' },
  { value:   39.6, color: '#008E8A' },
  { value:   39.7, color: '#008E8A' },
  { value:   39.8, color: '#008E8A' },
  { value:   39.9, color: '#008E8B' },
  { value:   40.0, color: '#008E8B' },
  { value:   40.1, color: '#008E8B' },
  { value:   40.2, color: '#008E8B' },
  { value:   40.3, color: '#008E8B' },
  { value:   40.4, color: '#008E8C' },
  { value:   40.5, color: '#008E8C' },
  { value:   40.6, color: '#008E8C' },
  { value:   40.7, color: '#008F8C' },
  { value:   40.8, color: '#008F8D' },
  { value:   40.9, color: '#008F8D' },
  { value:   41.0, color: '#008F8D' },
  { value:   41.1, color: '#008F8D' },
  { value:   41.2, color: '#008F8E' },
  { value:   41.3, color: '#008F8E' },
  { value:   41.4, color: '#008F8E' },
  { value:   41.5, color: '#008F8E' },
  { value:   41.6, color: '#008F8E' },
  { value:   41.7, color: '#008F8F' },
  { value:   41.8, color: '#008F8F' },
  { value:   41.9, color: '#008F8F' },
  { value:   42.0, color: '#008F8F' },
  { value:   42.1, color: '#009090' },
  { value:   42.2, color: '#009090' },
  { value:   42.3, color: '#009090' },
  { value:   42.4, color: '#009090' },
  { value:   42.5, color: '#009090' },
  { value:   42.6, color: '#009091' },
  { value:   42.7, color: '#009091' },
  { value:   42.8, color: '#009091' },
  { value:   42.9, color: '#009091' },
  { value:   43.0, color: '#009092' },
  { value:   43.1, color: '#009092' },
  { value:   43.2, color: '#009092' },
  { value:   43.3, color: '#009092' },
  { value:   43.4, color: '#009092' },
  { value:   43.5, color: '#009193' },
  { value:   43.6, color: '#009193' },
  { value:   43.7, color: '#009193' },
  { value:   43.8, color: '#009193' },
  { value:   43.9, color: '#009194' },
  { value:   44.0, color: '#009194' },
  { value:   44.1, color: '#009194' },
  { value:   44.2, color: '#009194' },
  { value:   44.3, color: '#009194' },
  { value:   44.4, color: '#009195' },
  { value:   44.5, color: '#009195' },
  { value:   44.6, color: '#009195' },
  { value:   44.7, color: '#009195' },
  { value:   44.8, color: '#009196' },
  { value:   44.9, color: '#009296' },
  { value:   45.0, color: '#009296' },
  { value:   45.1, color: '#009296' },
  { value:   45.2, color: '#009297' },
  { value:   45.3, color: '#009297' },
  { value:   45.4, color: '#009297' },
  { value:   45.5, color: '#009297' },
  { value:   45.6, color: '#009297' },
  { value:   45.7, color: '#009298' },
  { value:   45.8, color: '#009298' },
  { value:   45.9, color: '#009298' },
  { value:   46.0, color: '#009298' },
  { value:   46.1, color: '#009299' },
  { value:   46.2, color: '#009299' },
  { value:   46.3, color: '#009399' },
  { value:   46.4, color: '#009399' },
  { value:   46.5, color: '#009399' },
  { value:   46.6, color: '#00939A' },
  { value:   46.7, color: '#00939A' },
  { value:   46.8, color: '#00939A' },
  { value:   46.9, color: '#00939A' },
  { value:   47.0, color: '#00939B' },
  { value:   47.1, color: '#00939B' },
  { value:   47.2, color: '#00939B' },
  { value:   47.3, color: '#00939B' },
  { value:   47.4, color: '#00939B' },
  { value:   47.5, color: '#00939C' },
  { value:   47.6, color: '#00939C' },
  { value:   47.7, color: '#00949C' },
  { value:   47.8, color: '#00949C' },
  { value:   47.9, color: '#00949D' },
  { value:   48.0, color: '#00949D' },
  { value:   48.1, color: '#00949D' },
  { value:   48.2, color: '#00949D' },
  { value:   48.3, color: '#00949E' },
  { value:   48.4, color: '#00949E' },
  { value:   48.5, color: '#00949E' },
  { value:   48.6, color: '#00949E' },
  { value:   48.7, color: '#00949E' },
  { value:   48.8, color: '#00949F' },
  { value:   48.9, color: '#00949F' },
  { value:   49.0, color: '#00949F' },
  { value:   49.1, color: '#00959F' },
  { value:   49.2, color: '#0095A0' },
  { value:   49.3, color: '#0095A0' },
  { value:   49.4, color: '#0095A0' },
  { value:   49.5, color: '#0095A0' },
  { value:   49.6, color: '#0095A0' },
  { value:   49.7, color: '#0095A1' },
  { value:   49.8, color: '#0095A1' },
  { value:   49.9, color: '#0095A1' },
  { value:   50.0, color: '#0095A1' },
  { value:   50.1, color: '#0095A2' },
  { value:   50.2, color: '#0095A2' },
  { value:   50.3, color: '#0095A2' },
  { value:   50.4, color: '#0095A2' },
  { value:   50.5, color: '#0096A2' },
  { value:   50.6, color: '#0096A3' },
  { value:   50.7, color: '#0096A3' },
  { value:   50.8, color: '#0096A3' },
  { value:   50.9, color: '#0096A3' },
  { value:   51.0, color: '#0096A4' },
  { value:   51.1, color: '#0096A4' },
  { value:   51.2, color: '#0096A4' },
  { value:   51.3, color: '#0096A4' },
  { value:   51.4, color: '#0096A5' },
  { value:   51.5, color: '#0096A5' },
  { value:   51.6, color: '#0096A5' },
  { value:   51.7, color: '#0096A5' },
  { value:   51.8, color: '#0096A5' },
  { value:   51.9, color: '#0097A6' },
  { value:   52.0, color: '#0097A6' },
  { value:   52.1, color: '#0097A6' },
  { value:   52.2, color: '#0097A6' },
  { value:   52.3, color: '#0097A7' },
  { value:   52.4, color: '#0097A7' },
  { value:   52.5, color: '#0097A7' },
  { value:   52.6, color: '#0097A7' },
  { value:   52.7, color: '#0096A7' },
  { value:   52.8, color: '#0096A7' },
  { value:   52.9, color: '#0096A8' },
  { value:   53.0, color: '#0196A8' },
  { value:   53.1, color: '#0195A8' },
  { value:   53.2, color: '#0195A8' },
  { value:   53.3, color: '#0195A8' },
  { value:   53.4, color: '#0194A8' },
  { value:   53.5, color: '#0194A8' },
  { value:   53.6, color: '#0194A9' },
  { value:   53.7, color: '#0194A9' },
  { value:   53.8, color: '#0293A9' },
  { value:   53.9, color: '#0293A9' },
  { value:   54.0, color: '#0293A9' },
  { value:   54.1, color: '#0293A9' },
  { value:   54.2, color: '#0292A9' },
  { value:   54.3, color: '#0292AA' },
  { value:   54.4, color: '#0292AA' },
  { value:   54.5, color: '#0291AA' },
  { value:   54.6, color: '#0291AA' },
  { value:   54.7, color: '#0391AA' },
  { value:   54.8, color: '#0391AA' },
  { value:   54.9, color: '#0390AA' },
  { value:   55.0, color: '#0390AA' },
  { value:   55.1, color: '#0390AB' },
  { value:   55.2, color: '#0390AB' },
  { value:   55.3, color: '#038FAB' },
  { value:   55.4, color: '#038FAB' },
  { value:   55.5, color: '#048FAB' },
  { value:   55.6, color: '#048EAB' },
  { value:   55.7, color: '#048EAB' },
  { value:   55.8, color: '#048EAC' },
  { value:   55.9, color: '#048EAC' },
  { value:   56.0, color: '#048DAC' },
  { value:   56.1, color: '#048DAC' },
  { value:   56.2, color: '#048DAC' },
  { value:   56.3, color: '#048CAC' },
  { value:   56.4, color: '#058CAC' },
  { value:   56.5, color: '#058CAD' },
  { value:   56.6, color: '#058CAD' },
  { value:   56.7, color: '#058BAD' },
  { value:   56.8, color: '#058BAD' },
  { value:   56.9, color: '#058BAD' },
  { value:   57.0, color: '#058AAD' },
  { value:   57.1, color: '#058AAD' },
  { value:   57.2, color: '#058AAE' },
  { value:   57.3, color: '#068AAE' },
  { value:   57.4, color: '#0689AE' },
  { value:   57.5, color: '#0689AE' },
  { value:   57.6, color: '#0689AE' },
  { value:   57.7, color: '#0689AE' },
  { value:   57.8, color: '#0688AE' },
  { value:   57.9, color: '#0688AE' },
  { value:   58.0, color: '#0688AF' },
  { value:   58.1, color: '#0787AF' },
  { value:   58.2, color: '#0787AF' },
  { value:   58.3, color: '#0787AF' },
  { value:   58.4, color: '#0787AF' },
  { value:   58.5, color: '#0786AF' },
  { value:   58.6, color: '#0786AF' },
  { value:   58.7, color: '#0786B0' },
  { value:   58.8, color: '#0786B0' },
  { value:   58.9, color: '#0785B0' },
  { value:   59.0, color: '#0885B0' },
  { value:   59.1, color: '#0885B0' },
  { value:   59.2, color: '#0884B0' },
  { value:   59.3, color: '#0884B0' },
  { value:   59.4, color: '#0884B1' },
  { value:   59.5, color: '#0884B1' },
  { value:   59.6, color: '#0883B1' },
  { value:   59.7, color: '#0883B1' },
  { value:   59.8, color: '#0983B1' },
  { value:   59.9, color: '#0982B1' },
  { value:   60.0, color: '#0982B1' },
  { value:   60.1, color: '#0982B2' },
  { value:   60.2, color: '#0982B2' },
  { value:   60.3, color: '#0981B2' },
  { value:   60.4, color: '#0981B2' },
  { value:   60.5, color: '#0981B2' },
  { value:   60.6, color: '#0980B2' },
  { value:   60.7, color: '#0A80B2' },
  { value:   60.8, color: '#0A80B3' },
  { value:   60.9, color: '#0A80B3' },
  { value:   61.0, color: '#0A7FB3' },
  { value:   61.1, color: '#0A7FB3' },
  { value:   61.2, color: '#0A7FB3' },
  { value:   61.3, color: '#0A7FB3' },
  { value:   61.4, color: '#0A7EB3' },
  { value:   61.5, color: '#0A7EB3' },
  { value:   61.6, color: '#0B7EB4' },
  { value:   61.7, color: '#0B7DB4' },
  { value:   61.8, color: '#0B7DB4' },
  { value:   61.9, color: '#0B7DB4' },
  { value:   62.0, color: '#0B7DB4' },
  { value:   62.1, color: '#0B7CB4' },
  { value:   62.2, color: '#0B7CB4' },
  { value:   62.3, color: '#0B7CB5' },
  { value:   62.4, color: '#0C7CB5' },
  { value:   62.5, color: '#0C7BB5' },
  { value:   62.6, color: '#0C7BB5' },
  { value:   62.7, color: '#0C7BB5' },
  { value:   62.8, color: '#0C7AB5' },
  { value:   62.9, color: '#0C7AB5' },
  { value:   63.0, color: '#0C7AB6' },
  { value:   63.1, color: '#0C7AB6' },
  { value:   63.2, color: '#0C79B6' },
  { value:   63.3, color: '#0D79B6' },
  { value:   63.4, color: '#0D79B6' },
  { value:   63.5, color: '#0D78B6' },
  { value:   63.6, color: '#0D78B6' },
  { value:   63.7, color: '#0D78B7' },
  { value:   63.8, color: '#0D78B7' },
  { value:   63.9, color: '#0D77B7' },
  { value:   64.0, color: '#0D77B7' },
  { value:   64.1, color: '#0E77B7' },
  { value:   64.2, color: '#0E76B7' },
  { value:   64.3, color: '#0E76B7' },
  { value:   64.4, color: '#0E76B8' },
  { value:   64.5, color: '#0E76B8' },
  { value:   64.6, color: '#0E75B8' },
  { value:   64.7, color: '#0E75B8' },
  { value:   64.8, color: '#0E75B8' },
  { value:   64.9, color: '#0E75B8' },
  { value:   65.0, color: '#0F74B8' },
  { value:   65.1, color: '#0F74B8' },
  { value:   65.2, color: '#0F74B9' },
  { value:   65.3, color: '#0F73B9' },
  { value:   65.4, color: '#0F73B9' },
  { value:   65.5, color: '#0F73B9' },
  { value:   65.6, color: '#0F73B9' },
  { value:   65.7, color: '#0F72B9' },
  { value:   65.8, color: '#1072B9' },
  { value:   65.9, color: '#1072BA' },
  { value:   66.0, color: '#1072BA' },
  { value:   66.1, color: '#1071BA' },
  { value:   66.2, color: '#1071BA' },
  { value:   66.3, color: '#1071BA' },
  { value:   66.4, color: '#1070BA' },
  { value:   66.5, color: '#1070BA' },
  { value:   66.6, color: '#1070BB' },
  { value:   66.7, color: '#1170BB' },
  { value:   66.8, color: '#116FBB' },
  { value:   66.9, color: '#116FBB' },
  { value:   67.0, color: '#116FBB' },
  { value:   67.1, color: '#116EBB' },
  { value:   67.2, color: '#116EBB' },
  { value:   67.3, color: '#116EBC' },
  { value:   67.4, color: '#116EBC' },
  { value:   67.5, color: '#126DBC' },
  { value:   67.6, color: '#126DBC' },
  { value:   67.7, color: '#126DBC' },
  { value:   67.8, color: '#126DBC' },
  { value:   67.9, color: '#126CBC' },
  { value:   68.0, color: '#126CBD' },
  { value:   68.1, color: '#126CBD' },
  { value:   68.2, color: '#126BBD' },
  { value:   68.3, color: '#126BBD' },
  { value:   68.4, color: '#136BBD' },
  { value:   68.5, color: '#136BBD' },
  { value:   68.6, color: '#136ABD' },
  { value:   68.7, color: '#136ABE' },
  { value:   68.8, color: '#136ABE' },
  { value:   68.9, color: '#1369BE' },
  { value:   69.0, color: '#1369BE' },
  { value:   69.1, color: '#1369BE' },
  { value:   69.2, color: '#1369BE' },
  { value:   69.3, color: '#1468BE' },
  { value:   69.4, color: '#1468BE' },
  { value:   69.5, color: '#1468BF' },
  { value:   69.6, color: '#1468BF' },
  { value:   69.7, color: '#1467BF' },
  { value:   69.8, color: '#1467BF' },
  { value:   69.9, color: '#1467BF' },
  { value:   70.0, color: '#1466BF' },
  { value:   70.1, color: '#1566BF' },
  { value:   70.2, color: '#1566C0' },
  { value:   70.3, color: '#1566C0' },
  { value:   70.4, color: '#1565C0' },
  { value:   70.5, color: '#1565C0' },
  { value:   70.6, color: '#1665C0' },
  { value:   70.7, color: '#1664C0' },
  { value:   70.8, color: '#1764BF' },
  { value:   70.9, color: '#1763BF' },
  { value:   71.0, color: '#1863BF' },
  { value:   71.1, color: '#1862BF' },
  { value:   71.2, color: '#1962BE' },
  { value:   71.3, color: '#1961BE' },
  { value:   71.4, color: '#1A61BE' },
  { value:   71.5, color: '#1A61BE' },
  { value:   71.6, color: '#1B60BD' },
  { value:   71.7, color: '#1B60BD' },
  { value:   71.8, color: '#1C5FBD' },
  { value:   71.9, color: '#1C5FBD' },
  { value:   72.0, color: '#1D5EBD' },
  { value:   72.1, color: '#1D5EBC' },
  { value:   72.2, color: '#1E5DBC' },
  { value:   72.3, color: '#1E5DBC' },
  { value:   72.4, color: '#1F5CBC' },
  { value:   72.5, color: '#1F5CBB' },
  { value:   72.6, color: '#205CBB' },
  { value:   72.7, color: '#205BBB' },
  { value:   72.8, color: '#215BBB' },
  { value:   72.9, color: '#215ABA' },
  { value:   73.0, color: '#225ABA' },
  { value:   73.1, color: '#2259BA' },
  { value:   73.2, color: '#2359BA' },
  { value:   73.3, color: '#2358BA' },
  { value:   73.4, color: '#2458B9' },
  { value:   73.5, color: '#2458B9' },
  { value:   73.6, color: '#2557B9' },
  { value:   73.7, color: '#2557B9' },
  { value:   73.8, color: '#2656B8' },
  { value:   73.9, color: '#2756B8' },
  { value:   74.0, color: '#2755B8' },
  { value:   74.1, color: '#2855B8' },
  { value:   74.2, color: '#2854B7' },
  { value:   74.3, color: '#2954B7' },
  { value:   74.4, color: '#2954B7' },
  { value:   74.5, color: '#2A53B7' },
  { value:   74.6, color: '#2A53B7' },
  { value:   74.7, color: '#2B52B6' },
  { value:   74.8, color: '#2B52B6' },
  { value:   74.9, color: '#2C51B6' },
  { value:   75.0, color: '#2C51B6' },
  { value:   75.1, color: '#2D50B5' },
  { value:   75.2, color: '#2D50B5' },
  { value:   75.3, color: '#2E4FB5' },
  { value:   75.4, color: '#2E4FB5' },
  { value:   75.5, color: '#2F4FB4' },
  { value:   75.6, color: '#2F4EB4' },
  { value:   75.7, color: '#304EB4' },
  { value:   75.8, color: '#304DB4' },
  { value:   75.9, color: '#314DB4' },
  { value:   76.0, color: '#314CB3' },
  { value:   76.1, color: '#324CB3' },
  { value:   76.2, color: '#324BB3' },
  { value:   76.3, color: '#334BB3' },
  { value:   76.4, color: '#334BB2' },
  { value:   76.5, color: '#344AB2' },
  { value:   76.6, color: '#344AB2' },
  { value:   76.7, color: '#3549B2' },
  { value:   76.8, color: '#3549B1' },
  { value:   76.9, color: '#3648B1' },
  { value:   77.0, color: '#3648B1' },
  { value:   77.1, color: '#3747B1' },
  { value:   77.2, color: '#3847B1' },
  { value:   77.3, color: '#3847B0' },
  { value:   77.4, color: '#3946B0' },
  { value:   77.5, color: '#3946B0' },
  { value:   77.6, color: '#3A45B0' },
  { value:   77.7, color: '#3A45AF' },
  { value:   77.8, color: '#3B44AF' },
  { value:   77.9, color: '#3B44AF' },
  { value:   78.0, color: '#3C43AF' },
  { value:   78.1, color: '#3C43AE' },
  { value:   78.2, color: '#3D42AE' },
  { value:   78.3, color: '#3D42AE' },
  { value:   78.4, color: '#3E42AE' },
  { value:   78.5, color: '#3E41AE' },
  { value:   78.6, color: '#3F41AD' },
  { value:   78.7, color: '#3F40AD' },
  { value:   78.8, color: '#4040AD' },
  { value:   78.9, color: '#403FAD' },
  { value:   79.0, color: '#413FAC' },
  { value:   79.1, color: '#413EAC' },
  { value:   79.2, color: '#423EAC' },
  { value:   79.3, color: '#423EAC' },
  { value:   79.4, color: '#433DAC' },
  { value:   79.5, color: '#433DAB' },
  { value:   79.6, color: '#443CAB' },
  { value:   79.7, color: '#443CAB' },
  { value:   79.8, color: '#453BAB' },
  { value:   79.9, color: '#453BAA' },
  { value:   80.0, color: '#463AAA' },
  { value:   80.1, color: '#463AAA' },
  { value:   80.2, color: '#4739AA' },
  { value:   80.3, color: '#4739A9' },
  { value:   80.4, color: '#4839A9' },
  { value:   80.5, color: '#4938A9' },
  { value:   80.6, color: '#4938A9' },
  { value:   80.7, color: '#4A37A9' },
  { value:   80.8, color: '#4A37A8' },
  { value:   80.9, color: '#4B36A8' },
  { value:   81.0, color: '#4B36A8' },
  { value:   81.1, color: '#4C35A8' },
  { value:   81.2, color: '#4C35A7' },
  { value:   81.3, color: '#4D35A7' },
  { value:   81.4, color: '#4D34A7' },
  { value:   81.5, color: '#4E34A7' },
  { value:   81.6, color: '#4E33A6' },
  { value:   81.7, color: '#4F33A6' },
  { value:   81.8, color: '#4F32A6' },
  { value:   81.9, color: '#5032A6' },
  { value:   82.0, color: '#5031A6' },
  { value:   82.1, color: '#5131A5' },
  { value:   82.2, color: '#5131A5' },
  { value:   82.3, color: '#5230A5' },
  { value:   82.4, color: '#5230A5' },
  { value:   82.5, color: '#532FA4' },
  { value:   82.6, color: '#532FA4' },
  { value:   82.7, color: '#542EA4' },
  { value:   82.8, color: '#542EA4' },
  { value:   82.9, color: '#552DA3' },
  { value:   83.0, color: '#552DA3' },
  { value:   83.1, color: '#562CA3' },
  { value:   83.2, color: '#562CA3' },
  { value:   83.3, color: '#572CA3' },
  { value:   83.4, color: '#572BA2' },
  { value:   83.5, color: '#582BA2' },
  { value:   83.6, color: '#582AA2' },
  { value:   83.7, color: '#592AA2' },
  { value:   83.8, color: '#5A29A1' },
  { value:   83.9, color: '#5A29A1' },
  { value:   84.0, color: '#5B28A1' },
  { value:   84.1, color: '#5B28A1' },
  { value:   84.2, color: '#5C28A0' },
  { value:   84.3, color: '#5C27A0' },
  { value:   84.4, color: '#5D27A0' },
  { value:   84.5, color: '#5D26A0' },
  { value:   84.6, color: '#5E26A0' },
  { value:   84.7, color: '#5E259F' },
  { value:   84.8, color: '#5F259F' },
  { value:   84.9, color: '#5F249F' },
  { value:   85.0, color: '#60249F' },
  { value:   85.1, color: '#60249E' },
  { value:   85.2, color: '#61239E' },
  { value:   85.3, color: '#61239E' },
  { value:   85.4, color: '#62229E' },
  { value:   85.5, color: '#62229D' },
  { value:   85.6, color: '#63219D' },
  { value:   85.7, color: '#63219D' },
  { value:   85.8, color: '#64209D' },
  { value:   85.9, color: '#64209D' },
  { value:   86.0, color: '#651F9C' },
  { value:   86.1, color: '#651F9C' },
  { value:   86.2, color: '#661F9C' },
  { value:   86.3, color: '#661E9C' },
  { value:   86.4, color: '#671E9B' },
  { value:   86.5, color: '#671D9B' },
  { value:   86.6, color: '#681D9B' },
  { value:   86.7, color: '#681C9B' },
  { value:   86.8, color: '#691C9A' },
  { value:   86.9, color: '#691B9A' },
  { value:   87.0, color: '#6A1B9A' },
  { value:   87.1, color: '#6B1B9A' },
  { value:   87.2, color: '#6B1B99' },
  { value:   87.3, color: '#6C1B99' },
  { value:   87.4, color: '#6C1B99' },
  { value:   87.5, color: '#6D1B98' },
  { value:   87.6, color: '#6E1B98' },
  { value:   87.7, color: '#6E1B98' },
  { value:   87.8, color: '#6F1B97' },
  { value:   87.9, color: '#701B97' },
  { value:   88.0, color: '#701B97' },
  { value:   88.1, color: '#711B96' },
  { value:   88.2, color: '#711B96' },
  { value:   88.3, color: '#721B96' },
  { value:   88.4, color: '#731B95' },
  { value:   88.5, color: '#731B95' },
  { value:   88.6, color: '#741B95' },
  { value:   88.7, color: '#741B95' },
  { value:   88.8, color: '#751B94' },
  { value:   88.9, color: '#761B94' },
  { value:   89.0, color: '#761B94' },
  { value:   89.1, color: '#771B93' },
  { value:   89.2, color: '#771B93' },
  { value:   89.3, color: '#781B93' },
  { value:   89.4, color: '#791B92' },
  { value:   89.5, color: '#791B92' },
  { value:   89.6, color: '#7A1B92' },
  { value:   89.7, color: '#7B1B91' },
  { value:   89.8, color: '#7B1B91' },
  { value:   89.9, color: '#7C1B91' },
  { value:   90.0, color: '#7C1B90' },
  { value:   90.1, color: '#7D1B90' },
  { value:   90.2, color: '#7E1B90' },
  { value:   90.3, color: '#7E1B8F' },
  { value:   90.4, color: '#7F1B8F' },
  { value:   90.5, color: '#7F1B8F' },
  { value:   90.6, color: '#801B8E' },
  { value:   90.7, color: '#811B8E' },
  { value:   90.8, color: '#811B8E' },
  { value:   90.9, color: '#821B8D' },
  { value:   91.0, color: '#821B8D' },
  { value:   91.1, color: '#831B8D' },
  { value:   91.2, color: '#841B8C' },
  { value:   91.3, color: '#841B8C' },
  { value:   91.4, color: '#851B8C' },
  { value:   91.5, color: '#861B8B' },
  { value:   91.6, color: '#861B8B' },
  { value:   91.7, color: '#871B8B' },
  { value:   91.8, color: '#871B8B' },
  { value:   91.9, color: '#881B8A' },
  { value:   92.0, color: '#891B8A' },
  { value:   92.1, color: '#891B8A' },
  { value:   92.2, color: '#8A1B89' },
  { value:   92.3, color: '#8A1B89' },
  { value:   92.4, color: '#8B1B89' },
  { value:   92.5, color: '#8C1B88' },
  { value:   92.6, color: '#8C1B88' },
  { value:   92.7, color: '#8D1B88' },
  { value:   92.8, color: '#8D1B87' },
  { value:   92.9, color: '#8E1B87' },
  { value:   93.0, color: '#8F1B87' },
  { value:   93.1, color: '#8F1B86' },
  { value:   93.2, color: '#901B86' },
  { value:   93.3, color: '#901B86' },
  { value:   93.4, color: '#911B85' },
  { value:   93.5, color: '#921B85' },
  { value:   93.6, color: '#921B85' },
  { value:   93.7, color: '#931B84' },
  { value:   93.8, color: '#941B84' },
  { value:   93.9, color: '#941B84' },
  { value:   94.0, color: '#951B83' },
  { value:   94.1, color: '#951B83' },
  { value:   94.2, color: '#961B83' },
  { value:   94.3, color: '#971B82' },
  { value:   94.4, color: '#971B82' },
  { value:   94.5, color: '#981B82' },
  { value:   94.6, color: '#981B82' },
  { value:   94.7, color: '#991B81' },
  { value:   94.8, color: '#9A1B81' },
  { value:   94.9, color: '#9A1B81' },
  { value:   95.0, color: '#9B1B80' },
  { value:   95.1, color: '#9B1B80' },
  { value:   95.2, color: '#9C1B80' },
  { value:   95.3, color: '#9D1B7F' },
  { value:   95.4, color: '#9D1B7F' },
  { value:   95.5, color: '#9E1B7F' },
  { value:   95.6, color: '#9F1B7E' },
  { value:   95.7, color: '#9F1B7E' },
  { value:   95.8, color: '#A01B7E' },
  { value:   95.9, color: '#A01B7D' },
  { value:   96.0, color: '#A11B7D' },
  { value:   96.1, color: '#A21B7D' },
  { value:   96.2, color: '#A21B7C' },
  { value:   96.3, color: '#A31B7C' },
  { value:   96.4, color: '#A31B7C' },
  { value:   96.5, color: '#A41B7B' },
  { value:   96.6, color: '#A51B7B' },
  { value:   96.7, color: '#A51B7B' },
  { value:   96.8, color: '#A61B7A' },
  { value:   96.9, color: '#A71B7A' },
  { value:   97.0, color: '#A71B7A' },
  { value:   97.1, color: '#A81B79' },
  { value:   97.2, color: '#A81B79' },
  { value:   97.3, color: '#A91B79' },
  { value:   97.4, color: '#AA1B78' },
  { value:   97.5, color: '#AA1B78' },
  { value:   97.6, color: '#AB1B78' },
  { value:   97.7, color: '#AB1B78' },
  { value:   97.8, color: '#AC1B77' },
  { value:   97.9, color: '#AD1B77' },
  { value:   98.0, color: '#AD1B77' },
  { value:   98.1, color: '#AE1B76' },
  { value:   98.2, color: '#AE1B76' },
  { value:   98.3, color: '#AF1B76' },
  { value:   98.4, color: '#B01B75' },
  { value:   98.5, color: '#B01B75' },
  { value:   98.6, color: '#B11B75' },
  { value:   98.7, color: '#B21B74' },
  { value:   98.8, color: '#B21B74' },
  { value:   98.9, color: '#B31B74' },
  { value:   99.0, color: '#B31B73' },
  { value:   99.1, color: '#B41B73' },
  { value:   99.2, color: '#B51B73' },
  { value:   99.3, color: '#B51B72' },
  { value:   99.4, color: '#B61B72' },
  { value:   99.5, color: '#B61B72' },
  { value:   99.6, color: '#B71B71' },
  { value:   99.7, color: '#B81B71' },
  { value:   99.8, color: '#B81B71' },
  { value:   99.9, color: '#B91B70' },
  { value:  100.0, color: '#B91B70' },
  { value:  100.1, color: '#BA1B70' },
  { value:  100.2, color: '#BB1B6F' },
  { value:  100.3, color: '#BB1B6F' },
  { value:  100.4, color: '#BC1B6F' },
  { value:  100.5, color: '#BC1B6E' },
  { value:  100.6, color: '#BD1B6E' },
  { value:  100.7, color: '#BE1B6E' },
  { value:  100.8, color: '#BE1B6E' },
  { value:  100.9, color: '#BF1B6D' },
  { value:  101.0, color: '#C01B6D' },
  { value:  101.1, color: '#C01B6D' },
  { value:  101.2, color: '#C11B6C' },
  { value:  101.3, color: '#C11B6C' },
  { value:  101.4, color: '#C21B6C' },
  { value:  101.5, color: '#C31B6B' },
  { value:  101.6, color: '#C31B6B' },
  { value:  101.7, color: '#C41B6B' },
  { value:  101.8, color: '#C41B6A' },
  { value:  101.9, color: '#C51B6A' },
  { value:  102.0, color: '#C61B6A' },
  { value:  102.1, color: '#C61B69' },
  { value:  102.2, color: '#C71B69' },
  { value:  102.3, color: '#C71B69' },
  { value:  102.4, color: '#C81B68' },
  { value:  102.5, color: '#C91B68' },
  { value:  102.6, color: '#C91B68' },
  { value:  102.7, color: '#CA1B67' },
  { value:  102.8, color: '#CB1B67' },
  { value:  102.9, color: '#CB1B67' },
  { value:  103.0, color: '#CC1B66' },
  { value:  103.1, color: '#CC1B66' },
  { value:  103.2, color: '#CD1B66' },
  { value:  103.3, color: '#CE1B65' },
  { value:  103.4, color: '#CE1B65' },
  { value:  103.5, color: '#CF1B65' },
  { value:  103.6, color: '#CF1B65' },
  { value:  103.7, color: '#D01B64' },
  { value:  103.8, color: '#D11B64' },
  { value:  103.9, color: '#D11B64' },
  { value:  104.0, color: '#D21B63' },
  { value:  104.1, color: '#D21B63' },
  { value:  104.2, color: '#D31B63' },
  { value:  104.3, color: '#D41B62' },
  { value:  104.4, color: '#D41B62' },
  { value:  104.5, color: '#D51B62' },
  { value:  104.6, color: '#D61B61' },
  { value:  104.7, color: '#D61B61' },
  { value:  104.8, color: '#D71B61' },
  { value:  104.9, color: '#D71B60' },
  { value:  105.0, color: '#D81B60' },
  { value:  105.1, color: '#D81B60' },
  { value:  105.2, color: '#D81B60' },
  { value:  105.3, color: '#D81B5F' },
  { value:  105.4, color: '#D81C5F' },
  { value:  105.5, color: '#D81C5F' },
  { value:  105.6, color: '#D81C5F' },
  { value:  105.7, color: '#D91C5E' },
  { value:  105.8, color: '#D91C5E' },
  { value:  105.9, color: '#D91D5E' },
  { value:  106.0, color: '#D91D5E' },
  { value:  106.1, color: '#D91D5D' },
  { value:  106.2, color: '#D91D5D' },
  { value:  106.3, color: '#D91D5D' },
  { value:  106.4, color: '#D91D5D' },
  { value:  106.5, color: '#D91E5C' },
  { value:  106.6, color: '#D91E5C' },
  { value:  106.7, color: '#D91E5C' },
  { value:  106.8, color: '#D91E5C' },
  { value:  106.9, color: '#D91E5B' },
  { value:  107.0, color: '#D91E5B' },
  { value:  107.1, color: '#DA1E5B' },
  { value:  107.2, color: '#DA1F5B' },
  { value:  107.3, color: '#DA1F5B' },
  { value:  107.4, color: '#DA1F5A' },
  { value:  107.5, color: '#DA1F5A' },
  { value:  107.6, color: '#DA1F5A' },
  { value:  107.7, color: '#DA205A' },
  { value:  107.8, color: '#DA2059' },
  { value:  107.9, color: '#DA2059' },
  { value:  108.0, color: '#DA2059' },
  { value:  108.1, color: '#DA2059' },
  { value:  108.2, color: '#DA2058' },
  { value:  108.3, color: '#DA2058' },
  { value:  108.4, color: '#DA2158' },
  { value:  108.5, color: '#DB2158' },
  { value:  108.6, color: '#DB2157' },
  { value:  108.7, color: '#DB2157' },
  { value:  108.8, color: '#DB2157' },
  { value:  108.9, color: '#DB2257' },
  { value:  109.0, color: '#DB2256' },
  { value:  109.1, color: '#DB2256' },
  { value:  109.2, color: '#DB2256' },
  { value:  109.3, color: '#DB2256' },
  { value:  109.4, color: '#DB2255' },
  { value:  109.5, color: '#DB2355' },
  { value:  109.6, color: '#DB2355' },
  { value:  109.7, color: '#DB2355' },
  { value:  109.8, color: '#DB2355' },
  { value:  109.9, color: '#DC2354' },
  { value:  110.0, color: '#DC2354' },
  { value:  110.1, color: '#DC2454' },
  { value:  110.2, color: '#DC2454' },
  { value:  110.3, color: '#DC2453' },
  { value:  110.4, color: '#DC2453' },
  { value:  110.5, color: '#DC2453' },
  { value:  110.6, color: '#DC2453' },
  { value:  110.7, color: '#DC2552' },
  { value:  110.8, color: '#DC2552' },
  { value:  110.9, color: '#DC2552' },
  { value:  111.0, color: '#DC2552' },
  { value:  111.1, color: '#DC2551' },
  { value:  111.2, color: '#DC2551' },
  { value:  111.3, color: '#DD2651' },
  { value:  111.4, color: '#DD2651' },
  { value:  111.5, color: '#DD2650' },
  { value:  111.6, color: '#DD2650' },
  { value:  111.7, color: '#DD2650' },
  { value:  111.8, color: '#DD2650' },
  { value:  111.9, color: '#DD2750' },
  { value:  112.0, color: '#DD274F' },
  { value:  112.1, color: '#DD274F' },
  { value:  112.2, color: '#DD274F' },
  { value:  112.3, color: '#DD274F' },
  { value:  112.4, color: '#DD274E' },
  { value:  112.5, color: '#DD284E' },
  { value:  112.6, color: '#DD284E' },
  { value:  112.7, color: '#DE284E' },
  { value:  112.8, color: '#DE284D' },
  { value:  112.9, color: '#DE284D' },
  { value:  113.0, color: '#DE284D' },
  { value:  113.1, color: '#DE294D' },
  { value:  113.2, color: '#DE294C' },
  { value:  113.3, color: '#DE294C' },
  { value:  113.4, color: '#DE294C' },
  { value:  113.5, color: '#DE294C' },
  { value:  113.6, color: '#DE294B' },
  { value:  113.7, color: '#DE2A4B' },
  { value:  113.8, color: '#DE2A4B' },
  { value:  113.9, color: '#DE2A4B' },
  { value:  114.0, color: '#DE2A4A' },
  { value:  114.1, color: '#DF2A4A' },
  { value:  114.2, color: '#DF2A4A' },
  { value:  114.3, color: '#DF2B4A' },
  { value:  114.4, color: '#DF2B4A' },
  { value:  114.5, color: '#DF2B49' },
  { value:  114.6, color: '#DF2B49' },
  { value:  114.7, color: '#DF2B49' },
  { value:  114.8, color: '#DF2B49' },
  { value:  114.9, color: '#DF2C48' },
  { value:  115.0, color: '#DF2C48' },
  { value:  115.1, color: '#DF2C48' },
  { value:  115.2, color: '#DF2C48' },
  { value:  115.3, color: '#DF2C47' },
  { value:  115.4, color: '#E02C47' },
  { value:  115.5, color: '#E02D47' },
  { value:  115.6, color: '#E02D47' },
  { value:  115.7, color: '#E02D46' },
  { value:  115.8, color: '#E02D46' },
  { value:  115.9, color: '#E02D46' },
  { value:  116.0, color: '#E02D46' },
  { value:  116.1, color: '#E02E45' },
  { value:  116.2, color: '#E02E45' },
  { value:  116.3, color: '#E02E45' },
  { value:  116.4, color: '#E02E45' },
  { value:  116.5, color: '#E02E45' },
  { value:  116.6, color: '#E02E44' },
  { value:  116.7, color: '#E02F44' },
  { value:  116.8, color: '#E12F44' },
  { value:  116.9, color: '#E12F44' },
  { value:  117.0, color: '#E12F43' },
  { value:  117.1, color: '#E12F43' },
  { value:  117.2, color: '#E12F43' },
  { value:  117.3, color: '#E13043' },
  { value:  117.4, color: '#E13042' },
  { value:  117.5, color: '#E13042' },
  { value:  117.6, color: '#E13042' },
  { value:  117.7, color: '#E13042' },
  { value:  117.8, color: '#E13041' },
  { value:  117.9, color: '#E13141' },
  { value:  118.0, color: '#E13141' },
  { value:  118.1, color: '#E13141' },
  { value:  118.2, color: '#E23140' },
  { value:  118.3, color: '#E23140' },
  { value:  118.4, color: '#E23140' },
  { value:  118.5, color: '#E23240' },
  { value:  118.6, color: '#E23240' },
  { value:  118.7, color: '#E2323F' },
  { value:  118.8, color: '#E2323F' },
  { value:  118.9, color: '#E2323F' },
  { value:  119.0, color: '#E2323F' },
  { value:  119.1, color: '#E2333E' },
  { value:  119.2, color: '#E2333E' },
  { value:  119.3, color: '#E2333E' },
  { value:  119.4, color: '#E2333E' },
  { value:  119.5, color: '#E2333D' },
  { value:  119.6, color: '#E3333D' },
  { value:  119.7, color: '#E3343D' },
  { value:  119.8, color: '#E3343D' },
  { value:  119.9, color: '#E3343C' },
  { value:  120.0, color: '#E3343C' },
  { value:  120.1, color: '#E3343C' },
  { value:  120.2, color: '#E3343C' },
  { value:  120.3, color: '#E3353B' },
  { value:  120.4, color: '#E3353B' },
  { value:  120.5, color: '#E3353B' },
  { value:  120.6, color: '#E3353B' },
  { value:  120.7, color: '#E3353A' },
  { value:  120.8, color: '#E3353A' },
  { value:  120.9, color: '#E3363A' },
  { value:  121.0, color: '#E4363A' },
  { value:  121.1, color: '#E4363A' },
  { value:  121.2, color: '#E43639' },
  { value:  121.3, color: '#E43639' },
  { value:  121.4, color: '#E43639' },
  { value:  121.5, color: '#E43739' },
  { value:  121.6, color: '#E43738' },
  { value:  121.7, color: '#E43738' },
  { value:  121.8, color: '#E43738' },
  { value:  121.9, color: '#E43738' },
  { value:  122.0, color: '#E43737' },
  { value:  122.1, color: '#E43837' },
  { value:  122.2, color: '#E43837' },
  { value:  122.3, color: '#E43837' },
  { value:  122.4, color: '#E53836' },
  { value:  122.5, color: '#E53836' },
  { value:  122.6, color: '#E53836' },
  { value:  122.7, color: '#E53936' },
  { value:  122.8, color: '#E53935' },
  { value:  122.9, color: '#E53935' },
  { value:  123.0, color: '#E53935' },
  { value:  123.1, color: '#E53935' },
  { value:  123.2, color: '#E53A34' },
  { value:  123.3, color: '#E63A34' },
  { value:  123.4, color: '#E63A34' },
  { value:  123.5, color: '#E63B33' },
  { value:  123.6, color: '#E63B33' },
  { value:  123.7, color: '#E63B33' },
  { value:  123.8, color: '#E63C32' },
  { value:  123.9, color: '#E73C32' },
  { value:  124.0, color: '#E73C31' },
  { value:  124.1, color: '#E73D31' },
  { value:  124.2, color: '#E73D31' },
  { value:  124.3, color: '#E73E30' },
  { value:  124.4, color: '#E73E30' },
  { value:  124.5, color: '#E83E30' },
  { value:  124.6, color: '#E83F2F' },
  { value:  124.7, color: '#E83F2F' },
  { value:  124.8, color: '#E83F2F' },
  { value:  124.9, color: '#E8402E' },
  { value:  125.0, color: '#E8402E' },
  { value:  125.1, color: '#E9402E' },
  { value:  125.2, color: '#E9412D' },
  { value:  125.3, color: '#E9412D' },
  { value:  125.4, color: '#E9412D' },
  { value:  125.5, color: '#E9422C' },
  { value:  125.6, color: '#EA422C' },
  { value:  125.7, color: '#EA422B' },
  { value:  125.8, color: '#EA432B' },
  { value:  125.9, color: '#EA432B' },
  { value:  126.0, color: '#EA432A' },
  { value:  126.1, color: '#EA442A' },
  { value:  126.2, color: '#EB442A' },
  { value:  126.3, color: '#EB4429' },
  { value:  126.4, color: '#EB4529' },
  { value:  126.5, color: '#EB4529' },
  { value:  126.6, color: '#EB4528' },
  { value:  126.7, color: '#EB4628' },
  { value:  126.8, color: '#EC4628' },
  { value:  126.9, color: '#EC4727' },
  { value:  127.0, color: '#EC4727' },
  { value:  127.1, color: '#EC4727' },
  { value:  127.2, color: '#EC4826' },
  { value:  127.3, color: '#EC4826' },
  { value:  127.4, color: '#ED4825' },
  { value:  127.5, color: '#ED4925' },
  { value:  127.6, color: '#ED4925' },
  { value:  127.7, color: '#ED4924' },
  { value:  127.8, color: '#ED4A24' },
  { value:  127.9, color: '#ED4A24' },
  { value:  128.0, color: '#EE4A23' },
  { value:  128.1, color: '#EE4B23' },
  { value:  128.2, color: '#EE4B23' },
  { value:  128.3, color: '#EE4B22' },
  { value:  128.4, color: '#EE4C22' },
  { value:  128.5, color: '#EF4C22' },
  { value:  128.6, color: '#EF4C21' },
  { value:  128.7, color: '#EF4D21' },
  { value:  128.8, color: '#EF4D21' },
  { value:  128.9, color: '#EF4D20' },
  { value:  129.0, color: '#EF4E20' },
  { value:  129.1, color: '#F04E1F' },
  { value:  129.2, color: '#F04E1F' },
  { value:  129.3, color: '#F04F1F' },
  { value:  129.4, color: '#F04F1E' },
  { value:  129.5, color: '#F0501E' },
  { value:  129.6, color: '#F0501E' },
  { value:  129.7, color: '#F1501D' },
  { value:  129.8, color: '#F1511D' },
  { value:  129.9, color: '#F1511D' },
  { value:  130.0, color: '#F1511C' },
  { value:  130.1, color: '#F1521C' },
  { value:  130.2, color: '#F1521C' },
  { value:  130.3, color: '#F2521B' },
  { value:  130.4, color: '#F2531B' },
  { value:  130.5, color: '#F2531A' },
  { value:  130.6, color: '#F2531A' },
  { value:  130.7, color: '#F2541A' },
  { value:  130.8, color: '#F35419' },
  { value:  130.9, color: '#F35419' },
  { value:  131.0, color: '#F35519' },
  { value:  131.1, color: '#F35518' },
  { value:  131.2, color: '#F35518' },
  { value:  131.3, color: '#F35618' },
  { value:  131.4, color: '#F45617' },
  { value:  131.5, color: '#F45617' },
  { value:  131.6, color: '#F45717' },
  { value:  131.7, color: '#F45716' },
  { value:  131.8, color: '#F45816' },
  { value:  131.9, color: '#F45816' },
  { value:  132.0, color: '#F55815' },
  { value:  132.1, color: '#F55915' },
  { value:  132.2, color: '#F55914' },
  { value:  132.3, color: '#F55914' },
  { value:  132.4, color: '#F55A14' },
  { value:  132.5, color: '#F55A13' },
  { value:  132.6, color: '#F65A13' },
  { value:  132.7, color: '#F65B13' },
  { value:  132.8, color: '#F65B12' },
  { value:  132.9, color: '#F65B12' },
  { value:  133.0, color: '#F65C12' },
  { value:  133.1, color: '#F75C11' },
  { value:  133.2, color: '#F75C11' },
  { value:  133.3, color: '#F75D11' },
  { value:  133.4, color: '#F75D10' },
  { value:  133.5, color: '#F75D10' },
  { value:  133.6, color: '#F75E10' },
  { value:  133.7, color: '#F85E0F' },
  { value:  133.8, color: '#F85E0F' },
  { value:  133.9, color: '#F85F0E' },
  { value:  134.0, color: '#F85F0E' },
  { value:  134.1, color: '#F85F0E' },
  { value:  134.2, color: '#F8600D' },
  { value:  134.3, color: '#F9600D' },
  { value:  134.4, color: '#F9610D' },
  { value:  134.5, color: '#F9610C' },
  { value:  134.6, color: '#F9610C' },
  { value:  134.7, color: '#F9620C' },
  { value:  134.8, color: '#F9620B' },
  { value:  134.9, color: '#FA620B' },
  { value:  135.0, color: '#FA630B' },
  { value:  135.1, color: '#FA630A' },
  { value:  135.2, color: '#FA630A' },
  { value:  135.3, color: '#FA640A' },
  { value:  135.4, color: '#FA6409' },
  { value:  135.5, color: '#FB6409' },
  { value:  135.6, color: '#FB6508' },
  { value:  135.7, color: '#FB6508' },
  { value:  135.8, color: '#FB6508' },
  { value:  135.9, color: '#FB6607' },
  { value:  136.0, color: '#FC6607' },
  { value:  136.1, color: '#FC6607' },
  { value:  136.2, color: '#FC6706' },
  { value:  136.3, color: '#FC6706' },
  { value:  136.4, color: '#FC6706' },
  { value:  136.5, color: '#FC6805' },
  { value:  136.6, color: '#FD6805' },
  { value:  136.7, color: '#FD6805' },
  { value:  136.8, color: '#FD6904' },
  { value:  136.9, color: '#FD6904' },
  { value:  137.0, color: '#FD6A04' },
  { value:  137.1, color: '#FD6A03' },
  { value:  137.2, color: '#FE6A03' },
  { value:  137.3, color: '#FE6B02' },
  { value:  137.4, color: '#FE6B02' },
  { value:  137.5, color: '#FE6B02' },
  { value:  137.6, color: '#FE6C01' },
  { value:  137.7, color: '#FE6C01' },
  { value:  137.8, color: '#FF6C01' },
  { value:  137.9, color: '#FF6D00' },
  { value:  138.0, color: '#FF6D00' },
  { value:  138.1, color: '#FD6C00' },
  { value:  138.2, color: '#FC6C01' },
  { value:  138.3, color: '#FA6B01' },
  { value:  138.4, color: '#F96B01' },
  { value:  138.5, color: '#F76A01' },
  { value:  138.6, color: '#F56A02' },
  { value:  138.7, color: '#F46902' },
  { value:  138.8, color: '#F26802' },
  { value:  138.9, color: '#F16803' },
  { value:  139.0, color: '#EF6703' },
  { value:  139.1, color: '#ED6703' },
  { value:  139.2, color: '#EC6603' },
  { value:  139.3, color: '#EA6504' },
  { value:  139.4, color: '#E86504' },
  { value:  139.5, color: '#E76404' },
  { value:  139.6, color: '#E56405' },
  { value:  139.7, color: '#E46305' },
  { value:  139.8, color: '#E26205' },
  { value:  139.9, color: '#E06206' },
  { value:  140.0, color: '#DF6106' },
  { value:  140.1, color: '#DD6106' },
  { value:  140.2, color: '#DC6006' },
  { value:  140.3, color: '#DA6007' },
  { value:  140.4, color: '#D85F07' },
  { value:  140.5, color: '#D75E07' },
  { value:  140.6, color: '#D55E08' },
  { value:  140.7, color: '#D45D08' },
  { value:  140.8, color: '#D25D08' },
  { value:  140.9, color: '#D05C08' },
  { value:  141.0, color: '#CF5C09' },
  { value:  141.1, color: '#CD5B09' },
  { value:  141.2, color: '#CC5A09' },
  { value:  141.3, color: '#CA5A0A' },
  { value:  141.4, color: '#C8590A' },
  { value:  141.5, color: '#C7590A' },
  { value:  141.6, color: '#C5580A' },
  { value:  141.7, color: '#C3570B' },
  { value:  141.8, color: '#C2570B' },
  { value:  141.9, color: '#C0560B' },
  { value:  142.0, color: '#BF560C' },
  { value:  142.1, color: '#BD550C' },
  { value:  142.2, color: '#BB550C' },
  { value:  142.3, color: '#BA540D' },
  { value:  142.4, color: '#B8530D' },
  { value:  142.5, color: '#B7530D' },
  { value:  142.6, color: '#B5520D' },
  { value:  142.7, color: '#B3520E' },
  { value:  142.8, color: '#B2510E' },
  { value:  142.9, color: '#B0500E' },
  { value:  143.0, color: '#AF500F' },
  { value:  143.1, color: '#AD4F0F' },
  { value:  143.2, color: '#AB4F0F' },
  { value:  143.3, color: '#AA4E0F' },
  { value:  143.4, color: '#A84D10' },
  { value:  143.5, color: '#A74D10' },
  { value:  143.6, color: '#A54C10' },
  { value:  143.7, color: '#A34C11' },
  { value:  143.8, color: '#A24B11' },
  { value:  143.9, color: '#A04B11' },
  { value:  144.0, color: '#9E4A12' },
  { value:  144.1, color: '#9D4912' },
  { value:  144.2, color: '#9B4912' },
  { value:  144.3, color: '#9A4812' },
  { value:  144.4, color: '#984813' },
  { value:  144.5, color: '#964713' },
  { value:  144.6, color: '#954713' },
  { value:  144.7, color: '#934614' },
  { value:  144.8, color: '#924514' },
  { value:  144.9, color: '#904514' },
  { value:  145.0, color: '#8E4414' },
  { value:  145.1, color: '#8D4415' },
  { value:  145.2, color: '#8B4315' },
  { value:  145.3, color: '#8A4215' },
  { value:  145.4, color: '#884216' },
  { value:  145.5, color: '#864116' },
  { value:  145.6, color: '#854116' },
  { value:  145.7, color: '#834016' },
  { value:  145.8, color: '#823F17' },
  { value:  145.9, color: '#803F17' },
  { value:  146.0, color: '#7E3E17' },
  { value:  146.1, color: '#7D3E18' },
  { value:  146.2, color: '#7B3D18' },
  { value:  146.3, color: '#7A3D18' },
  { value:  146.4, color: '#783C19' },
  { value:  146.5, color: '#763B19' },
  { value:  146.6, color: '#753B19' },
  { value:  146.7, color: '#733A19' },
  { value:  146.8, color: '#713A1A' },
  { value:  146.9, color: '#70391A' },
  { value:  147.0, color: '#6E381A' },
  { value:  147.1, color: '#6D381B' },
  { value:  147.2, color: '#6B371B' },
  { value:  147.3, color: '#69371B' },
  { value:  147.4, color: '#68361B' },
  { value:  147.5, color: '#66361C' },
  { value:  147.6, color: '#65351C' },
  { value:  147.7, color: '#63341C' },
  { value:  147.8, color: '#61341D' },
  { value:  147.9, color: '#60331D' },
  { value:  148.0, color: '#5E331D' },
  { value:  148.1, color: '#5D321D' },
  { value:  148.2, color: '#5B321E' },
  { value:  148.3, color: '#59311E' },
  { value:  148.4, color: '#58301E' },
  { value:  148.5, color: '#56301F' },
  { value:  148.6, color: '#552F1F' },
  { value:  148.7, color: '#532F1F' },
  { value:  148.8, color: '#512E20' },
  { value:  148.9, color: '#502D20' },
  { value:  149.0, color: '#4E2D20' },
  { value:  149.1, color: '#4C2C20' },
  { value:  149.2, color: '#4B2C21' },
  { value:  149.3, color: '#492B21' },
  { value:  149.4, color: '#482A21' },
  { value:  149.5, color: '#462A22' },
  { value:  149.6, color: '#442922' },
  { value:  149.7, color: '#432922' },
  { value:  149.8, color: '#412822' },
  { value:  149.9, color: '#402823' },
  { value:  150.0, color: '#3E2723' },
  ],
  // ── ETc: 0.0 → 15.0 mm/day, multi-color palette ──────────────────────────────
  etc: [
  // ── ETc 0→15  white→sky→teal→lime→yellow→orange→purple
  { value:    0.0, color: '#FFFFFF' },
  { value:    0.1, color: '#FCFEFF' },
  { value:    0.2, color: '#F8FDFF' },
  { value:    0.3, color: '#F5FCFF' },
  { value:    0.4, color: '#F1FAFE' },
  { value:    0.5, color: '#EEF9FE' },
  { value:    0.6, color: '#EBF8FE' },
  { value:    0.7, color: '#E7F7FE' },
  { value:    0.8, color: '#E4F6FE' },
  { value:    0.9, color: '#E1F5FE' },
  { value:    1.0, color: '#DDF3FE' },
  { value:    1.1, color: '#DAF2FE' },
  { value:    1.2, color: '#D6F1FD' },
  { value:    1.3, color: '#D3F0FD' },
  { value:    1.4, color: '#D0EFFD' },
  { value:    1.5, color: '#CCEEFD' },
  { value:    1.6, color: '#C9EDFD' },
  { value:    1.7, color: '#C6EBFD' },
  { value:    1.8, color: '#C2EAFD' },
  { value:    1.9, color: '#BFE9FC' },
  { value:    2.0, color: '#BBE8FC' },
  { value:    2.1, color: '#B8E7FC' },
  { value:    2.2, color: '#B5E6FC' },
  { value:    2.3, color: '#AFE3FB' },
  { value:    2.4, color: '#A7DFF9' },
  { value:    2.5, color: '#9FDBF7' },
  { value:    2.6, color: '#97D7F5' },
  { value:    2.7, color: '#90D2F3' },
  { value:    2.8, color: '#88CEF1' },
  { value:    2.9, color: '#80CAF0' },
  { value:    3.0, color: '#78C6EE' },
  { value:    3.1, color: '#70C2EC' },
  { value:    3.2, color: '#68BEEA' },
  { value:    3.3, color: '#60BAE8' },
  { value:    3.4, color: '#59B5E6' },
  { value:    3.5, color: '#51B1E4' },
  { value:    3.6, color: '#49ADE2' },
  { value:    3.7, color: '#41A9E0' },
  { value:    3.8, color: '#39A5DE' },
  { value:    3.9, color: '#31A1DC' },
  { value:    4.0, color: '#299DDB' },
  { value:    4.1, color: '#2199D9' },
  { value:    4.2, color: '#1A94D7' },
  { value:    4.3, color: '#1290D5' },
  { value:    4.4, color: '#0A8CD3' },
  { value:    4.5, color: '#0288D1' },
  { value:    4.6, color: '#028ACF' },
  { value:    4.7, color: '#028DCD' },
  { value:    4.8, color: '#028FCB' },
  { value:    4.9, color: '#0292C9' },
  { value:    5.0, color: '#0294C7' },
  { value:    5.1, color: '#0197C5' },
  { value:    5.2, color: '#0199C3' },
  { value:    5.3, color: '#019CC1' },
  { value:    5.4, color: '#019EBF' },
  { value:    5.5, color: '#01A0BD' },
  { value:    5.6, color: '#01A3BB' },
  { value:    5.7, color: '#01A5BA' },
  { value:    5.8, color: '#01A8B8' },
  { value:    5.9, color: '#01AAB6' },
  { value:    6.0, color: '#01ADB4' },
  { value:    6.1, color: '#01AFB2' },
  { value:    6.2, color: '#00B2B0' },
  { value:    6.3, color: '#00B4AE' },
  { value:    6.4, color: '#00B6AC' },
  { value:    6.5, color: '#00B9AA' },
  { value:    6.6, color: '#00BBA8' },
  { value:    6.7, color: '#00BEA6' },
  { value:    6.8, color: '#03C0A1' },
  { value:    6.9, color: '#08C39A' },
  { value:    7.0, color: '#0DC693' },
  { value:    7.1, color: '#12C98C' },
  { value:    7.2, color: '#18CC85' },
  { value:    7.3, color: '#1DCF7D' },
  { value:    7.4, color: '#22D176' },
  { value:    7.5, color: '#27D46F' },
  { value:    7.6, color: '#2DD768' },
  { value:    7.7, color: '#32DA61' },
  { value:    7.8, color: '#37DD59' },
  { value:    7.9, color: '#3CE052' },
  { value:    8.0, color: '#42E34B' },
  { value:    8.1, color: '#47E544' },
  { value:    8.2, color: '#4CE83D' },
  { value:    8.3, color: '#51EB35' },
  { value:    8.4, color: '#57EE2E' },
  { value:    8.5, color: '#5CF127' },
  { value:    8.6, color: '#61F420' },
  { value:    8.7, color: '#66F619' },
  { value:    8.8, color: '#6CF911' },
  { value:    8.9, color: '#71FC0A' },
  { value:    9.0, color: '#76FF03' },
  { value:    9.1, color: '#7EFD03' },
  { value:    9.2, color: '#85FA03' },
  { value:    9.3, color: '#8DF802' },
  { value:    9.4, color: '#94F602' },
  { value:    9.5, color: '#9CF402' },
  { value:    9.6, color: '#A4F102' },
  { value:    9.7, color: '#ABEF02' },
  { value:    9.8, color: '#B3ED02' },
  { value:    9.9, color: '#BBEA01' },
  { value:   10.0, color: '#C2E801' },
  { value:   10.1, color: '#CAE601' },
  { value:   10.2, color: '#D1E401' },
  { value:   10.3, color: '#D9E101' },
  { value:   10.4, color: '#E1DF01' },
  { value:   10.5, color: '#E8DD00' },
  { value:   10.6, color: '#F0DB00' },
  { value:   10.7, color: '#F7D800' },
  { value:   10.8, color: '#FFD600' },
  { value:   10.9, color: '#FFCF00' },
  { value:   11.0, color: '#FFC800' },
  { value:   11.1, color: '#FFC100' },
  { value:   11.2, color: '#FFBA00' },
  { value:   11.3, color: '#FFB300' },
  { value:   11.4, color: '#FFAC00' },
  { value:   11.5, color: '#FFA500' },
  { value:   11.6, color: '#FF9E00' },
  { value:   11.7, color: '#FF9700' },
  { value:   11.8, color: '#FF9000' },
  { value:   11.9, color: '#FF8900' },
  { value:   12.0, color: '#FF8200' },
  { value:   12.1, color: '#FF7B00' },
  { value:   12.2, color: '#FF7400' },
  { value:   12.3, color: '#FF6D00' },
  { value:   12.4, color: '#FD6A11' },
  { value:   12.5, color: '#FB6721' },
  { value:   12.6, color: '#F96432' },
  { value:   12.7, color: '#F76143' },
  { value:   12.8, color: '#F55E54' },
  { value:   12.9, color: '#F35B64' },
  { value:   13.0, color: '#F15875' },
  { value:   13.1, color: '#EE5586' },
  { value:   13.2, color: '#EC5297' },
  { value:   13.3, color: '#EA4FA7' },
  { value:   13.4, color: '#E84CB8' },
  { value:   13.5, color: '#E649C9' },
  { value:   13.6, color: '#E446DA' },
  { value:   13.7, color: '#E243EA' },
  { value:   13.8, color: '#E040FB' },
  { value:   13.9, color: '#D03BEA' },
  { value:   14.0, color: '#BF35D9' },
  { value:   14.1, color: '#AF30C8' },
  { value:   14.2, color: '#9E2BB7' },
  { value:   14.3, color: '#8D25A6' },
  { value:   14.4, color: '#7D2095' },
  { value:   14.5, color: '#6D1B85' },
  { value:   14.6, color: '#5C1574' },
  { value:   14.7, color: '#4C1063' },
  { value:   14.8, color: '#3B0B52' },
  { value:   14.9, color: '#2A0541' },
  { value:   15.0, color: '#1A0030' },
  ],
}

function getLegendGradient(key) {
  const stops = layerColorStops[key]
  if (!stops) return '#888'
  const n = stops.length
  const parts = stops.map((s, i) => {
    const p1 = (i / n * 100).toFixed(3)
    const p2 = ((i + 1) / n * 100).toFixed(3)
    return `${s.color} ${p1}%, ${s.color} ${p2}%`
  })
  return `linear-gradient(to right, ${parts.join(', ')})`
}

// ── Layer definitions (with ETc) ──────────────────────────────────────────
const layerDefs = [
  { key:'savi', icon:'', name:'Soil Adjusted Vegetation Index',            maxLabel:'1.0',     midLabel:'0.0',     minLabel:'-1.0'  },
  { key:'kc',   icon:'', name:'Crop Coefficient',                 maxLabel:'1.5',     midLabel:'0.75',    minLabel:'0.0'   },
  { key:'etc',  icon:'', name:'Evapotranspiration',  maxLabel:'15 mm/d', midLabel:'7.5 mm/d', minLabel:'0 mm/d' },
  { key:'cwr',  icon:'', name:'Crop Water Requirement',  maxLabel:'150 mm',  midLabel:'75 mm',   minLabel:'0 mm'  },
  { key:'iwr',  icon:'', name:'Irrigation Water Requirement', maxLabel:'150 mm', midLabel:'75 mm', minLabel:'0 mm' },
  
]

const legendBreakpoints = {
  savi: [-1,-0.9,-0.8,-0.7,-0.6,-0.5,-0.4,-0.3,-0.2,-0.1,0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1],
  kc:   [0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1,1.1,1.2,1.3,1.4,1.5],
  cwr:  [0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1,1.1,1.2,1.3,1.4,1.5,1.6,1.7,1.8,1.9,2,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,3,3.1,3.2,3.3,3.4,3.5,3.6,3.7,3.8,3.9,4,4.1,4.2,4.3,4.4,4.5,4.6,4.7,4.8,4.9,5,5.1,5.2,5.3,5.4,5.5,5.6,5.7,5.8,5.9,6,6.1,6.2,6.3,6.4,6.5,6.6,6.7,6.8,6.9,7,7.1,7.2,7.3,7.4,7.5,7.6,7.7,7.8,7.9,8,8.1,8.2,8.3,8.4,8.5,8.6,8.7,8.8,8.9,9,9.1,9.2,9.3,9.4,9.5,9.6,9.7,9.8,9.9,10,10.1,10.2,10.3,10.4,10.5,10.6,10.7,10.8,10.9,11,11.1,11.2,11.3,11.4,11.5,11.6,11.7,11.8,11.9,12,12.1,12.2,12.3,12.4,12.5,12.6,12.7,12.8,12.9,13,13.1,13.2,13.3,13.4,13.5,13.6,13.7,13.8,13.9,14,14.1,14.2,14.3,14.4,14.5,14.6,14.7,14.8,14.9,15,15.1,15.2,15.3,15.4,15.5,15.6,15.7,15.8,15.9,16,16.1,16.2,16.3,16.4,16.5,16.6,16.7,16.8,16.9,17,17.1,17.2,17.3,17.4,17.5,17.6,17.7,17.8,17.9,18,18.1,18.2,18.3,18.4,18.5,18.6,18.7,18.8,18.9,19,19.1,19.2,19.3,19.4,19.5,19.6,19.7,19.8,19.9,20,20.1,20.2,20.3,20.4,20.5,20.6,20.7,20.8,20.9,21,21.1,21.2,21.3,21.4,21.5,21.6,21.7,21.8,21.9,22,22.1,22.2,22.3,22.4,22.5,22.6,22.7,22.8,22.9,23,23.1,23.2,23.3,23.4,23.5,23.6,23.7,23.8,23.9,24,24.1,24.2,24.3,24.4,24.5,24.6,24.7,24.8,24.9,25,25.1,25.2,25.3,25.4,25.5,25.6,25.7,25.8,25.9,26,26.1,26.2,26.3,26.4,26.5,26.6,26.7,26.8,26.9,27,27.1,27.2,27.3,27.4,27.5,27.6,27.7,27.8,27.9,28,28.1,28.2,28.3,28.4,28.5,28.6,28.7,28.8,28.9,29,29.1,29.2,29.3,29.4,29.5,29.6,29.7,29.8,29.9,30,30.1,30.2,30.3,30.4,30.5,30.6,30.7,30.8,30.9,31,31.1,31.2,31.3,31.4,31.5,31.6,31.7,31.8,31.9,32,32.1,32.2,32.3,32.4,32.5,32.6,32.7,32.8,32.9,33,33.1,33.2,33.3,33.4,33.5,33.6,33.7,33.8,33.9,34,34.1,34.2,34.3,34.4,34.5,34.6,34.7,34.8,34.9,35,35.1,35.2,35.3,35.4,35.5,35.6,35.7,35.8,35.9,36,36.1,36.2,36.3,36.4,36.5,36.6,36.7,36.8,36.9,37,37.1,37.2,37.3,37.4,37.5,37.6,37.7,37.8,37.9,38,38.1,38.2,38.3,38.4,38.5,38.6,38.7,38.8,38.9,39,39.1,39.2,39.3,39.4,39.5,39.6,39.7,39.8,39.9,40,40.1,40.2,40.3,40.4,40.5,40.6,40.7,40.8,40.9,41,41.1,41.2,41.3,41.4,41.5,41.6,41.7,41.8,41.9,42,42.1,42.2,42.3,42.4,42.5,42.6,42.7,42.8,42.9,43,43.1,43.2,43.3,43.4,43.5,43.6,43.7,43.8,43.9,44,44.1,44.2,44.3,44.4,44.5,44.6,44.7,44.8,44.9,45,45.1,45.2,45.3,45.4,45.5,45.6,45.7,45.8,45.9,46,46.1,46.2,46.3,46.4,46.5,46.6,46.7,46.8,46.9,47,47.1,47.2,47.3,47.4,47.5,47.6,47.7,47.8,47.9,48,48.1,48.2,48.3,48.4,48.5,48.6,48.7,48.8,48.9,49,49.1,49.2,49.3,49.4,49.5,49.6,49.7,49.8,49.9,50,50.1,50.2,50.3,50.4,50.5,50.6,50.7,50.8,50.9,51,51.1,51.2,51.3,51.4,51.5,51.6,51.7,51.8,51.9,52,52.1,52.2,52.3,52.4,52.5,52.6,52.7,52.8,52.9,53,53.1,53.2,53.3,53.4,53.5,53.6,53.7,53.8,53.9,54,54.1,54.2,54.3,54.4,54.5,54.6,54.7,54.8,54.9,55,55.1,55.2,55.3,55.4,55.5,55.6,55.7,55.8,55.9,56,56.1,56.2,56.3,56.4,56.5,56.6,56.7,56.8,56.9,57,57.1,57.2,57.3,57.4,57.5,57.6,57.7,57.8,57.9,58,58.1,58.2,58.3,58.4,58.5,58.6,58.7,58.8,58.9,59,59.1,59.2,59.3,59.4,59.5,59.6,59.7,59.8,59.9,60,60.1,60.2,60.3,60.4,60.5,60.6,60.7,60.8,60.9,61,61.1,61.2,61.3,61.4,61.5,61.6,61.7,61.8,61.9,62,62.1,62.2,62.3,62.4,62.5,62.6,62.7,62.8,62.9,63,63.1,63.2,63.3,63.4,63.5,63.6,63.7,63.8,63.9,64,64.1,64.2,64.3,64.4,64.5,64.6,64.7,64.8,64.9,65,65.1,65.2,65.3,65.4,65.5,65.6,65.7,65.8,65.9,66,66.1,66.2,66.3,66.4,66.5,66.6,66.7,66.8,66.9,67,67.1,67.2,67.3,67.4,67.5,67.6,67.7,67.8,67.9,68,68.1,68.2,68.3,68.4,68.5,68.6,68.7,68.8,68.9,69,69.1,69.2,69.3,69.4,69.5,69.6,69.7,69.8,69.9,70,70.1,70.2,70.3,70.4,70.5,70.6,70.7,70.8,70.9,71,71.1,71.2,71.3,71.4,71.5,71.6,71.7,71.8,71.9,72,72.1,72.2,72.3,72.4,72.5,72.6,72.7,72.8,72.9,73,73.1,73.2,73.3,73.4,73.5,73.6,73.7,73.8,73.9,74,74.1,74.2,74.3,74.4,74.5,74.6,74.7,74.8,74.9,75,75.1,75.2,75.3,75.4,75.5,75.6,75.7,75.8,75.9,76,76.1,76.2,76.3,76.4,76.5,76.6,76.7,76.8,76.9,77,77.1,77.2,77.3,77.4,77.5,77.6,77.7,77.8,77.9,78,78.1,78.2,78.3,78.4,78.5,78.6,78.7,78.8,78.9,79,79.1,79.2,79.3,79.4,79.5,79.6,79.7,79.8,79.9,80,80.1,80.2,80.3,80.4,80.5,80.6,80.7,80.8,80.9,81,81.1,81.2,81.3,81.4,81.5,81.6,81.7,81.8,81.9,82,82.1,82.2,82.3,82.4,82.5,82.6,82.7,82.8,82.9,83,83.1,83.2,83.3,83.4,83.5,83.6,83.7,83.8,83.9,84,84.1,84.2,84.3,84.4,84.5,84.6,84.7,84.8,84.9,85,85.1,85.2,85.3,85.4,85.5,85.6,85.7,85.8,85.9,86,86.1,86.2,86.3,86.4,86.5,86.6,86.7,86.8,86.9,87,87.1,87.2,87.3,87.4,87.5,87.6,87.7,87.8,87.9,88,88.1,88.2,88.3,88.4,88.5,88.6,88.7,88.8,88.9,89,89.1,89.2,89.3,89.4,89.5,89.6,89.7,89.8,89.9,90,90.1,90.2,90.3,90.4,90.5,90.6,90.7,90.8,90.9,91,91.1,91.2,91.3,91.4,91.5,91.6,91.7,91.8,91.9,92,92.1,92.2,92.3,92.4,92.5,92.6,92.7,92.8,92.9,93,93.1,93.2,93.3,93.4,93.5,93.6,93.7,93.8,93.9,94,94.1,94.2,94.3,94.4,94.5,94.6,94.7,94.8,94.9,95,95.1,95.2,95.3,95.4,95.5,95.6,95.7,95.8,95.9,96,96.1,96.2,96.3,96.4,96.5,96.6,96.7,96.8,96.9,97,97.1,97.2,97.3,97.4,97.5,97.6,97.7,97.8,97.9,98,98.1,98.2,98.3,98.4,98.5,98.6,98.7,98.8,98.9,99,99.1,99.2,99.3,99.4,99.5,99.6,99.7,99.8,99.9,100,100.1,100.2,100.3,100.4,100.5,100.6,100.7,100.8,100.9,101,101.1,101.2,101.3,101.4,101.5,101.6,101.7,101.8,101.9,102,102.1,102.2,102.3,102.4,102.5,102.6,102.7,102.8,102.9,103,103.1,103.2,103.3,103.4,103.5,103.6,103.7,103.8,103.9,104,104.1,104.2,104.3,104.4,104.5,104.6,104.7,104.8,104.9,105,105.1,105.2,105.3,105.4,105.5,105.6,105.7,105.8,105.9,106,106.1,106.2,106.3,106.4,106.5,106.6,106.7,106.8,106.9,107,107.1,107.2,107.3,107.4,107.5,107.6,107.7,107.8,107.9,108,108.1,108.2,108.3,108.4,108.5,108.6,108.7,108.8,108.9,109,109.1,109.2,109.3,109.4,109.5,109.6,109.7,109.8,109.9,110,110.1,110.2,110.3,110.4,110.5,110.6,110.7,110.8,110.9,111,111.1,111.2,111.3,111.4,111.5,111.6,111.7,111.8,111.9,112,112.1,112.2,112.3,112.4,112.5,112.6,112.7,112.8,112.9,113,113.1,113.2,113.3,113.4,113.5,113.6,113.7,113.8,113.9,114,114.1,114.2,114.3,114.4,114.5,114.6,114.7,114.8,114.9,115,115.1,115.2,115.3,115.4,115.5,115.6,115.7,115.8,115.9,116,116.1,116.2,116.3,116.4,116.5,116.6,116.7,116.8,116.9,117,117.1,117.2,117.3,117.4,117.5,117.6,117.7,117.8,117.9,118,118.1,118.2,118.3,118.4,118.5,118.6,118.7,118.8,118.9,119,119.1,119.2,119.3,119.4,119.5,119.6,119.7,119.8,119.9,120,120.1,120.2,120.3,120.4,120.5,120.6,120.7,120.8,120.9,121,121.1,121.2,121.3,121.4,121.5,121.6,121.7,121.8,121.9,122,122.1,122.2,122.3,122.4,122.5,122.6,122.7,122.8,122.9,123,123.1,123.2,123.3,123.4,123.5,123.6,123.7,123.8,123.9,124,124.1,124.2,124.3,124.4,124.5,124.6,124.7,124.8,124.9,125,125.1,125.2,125.3,125.4,125.5,125.6,125.7,125.8,125.9,126,126.1,126.2,126.3,126.4,126.5,126.6,126.7,126.8,126.9,127,127.1,127.2,127.3,127.4,127.5,127.6,127.7,127.8,127.9,128,128.1,128.2,128.3,128.4,128.5,128.6,128.7,128.8,128.9,129,129.1,129.2,129.3,129.4,129.5,129.6,129.7,129.8,129.9,130,130.1,130.2,130.3,130.4,130.5,130.6,130.7,130.8,130.9,131,131.1,131.2,131.3,131.4,131.5,131.6,131.7,131.8,131.9,132,132.1,132.2,132.3,132.4,132.5,132.6,132.7,132.8,132.9,133,133.1,133.2,133.3,133.4,133.5,133.6,133.7,133.8,133.9,134,134.1,134.2,134.3,134.4,134.5,134.6,134.7,134.8,134.9,135,135.1,135.2,135.3,135.4,135.5,135.6,135.7,135.8,135.9,136,136.1,136.2,136.3,136.4,136.5,136.6,136.7,136.8,136.9,137,137.1,137.2,137.3,137.4,137.5,137.6,137.7,137.8,137.9,138,138.1,138.2,138.3,138.4,138.5,138.6,138.7,138.8,138.9,139,139.1,139.2,139.3,139.4,139.5,139.6,139.7,139.8,139.9,140,140.1,140.2,140.3,140.4,140.5,140.6,140.7,140.8,140.9,141,141.1,141.2,141.3,141.4,141.5,141.6,141.7,141.8,141.9,142,142.1,142.2,142.3,142.4,142.5,142.6,142.7,142.8,142.9,143,143.1,143.2,143.3,143.4,143.5,143.6,143.7,143.8,143.9,144,144.1,144.2,144.3,144.4,144.5,144.6,144.7,144.8,144.9,145,145.1,145.2,145.3,145.4,145.5,145.6,145.7,145.8,145.9,146,146.1,146.2,146.3,146.4,146.5,146.6,146.7,146.8,146.9,147,147.1,147.2,147.3,147.4,147.5,147.6,147.7,147.8,147.9,148,148.1,148.2,148.3,148.4,148.5,148.6,148.7,148.8,148.9,149,149.1,149.2,149.3,149.4,149.5,149.6,149.7,149.8,149.9,150],
  iwr:  [0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1,1.1,1.2,1.3,1.4,1.5,1.6,1.7,1.8,1.9,2,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,3,3.1,3.2,3.3,3.4,3.5,3.6,3.7,3.8,3.9,4,4.1,4.2,4.3,4.4,4.5,4.6,4.7,4.8,4.9,5,5.1,5.2,5.3,5.4,5.5,5.6,5.7,5.8,5.9,6,6.1,6.2,6.3,6.4,6.5,6.6,6.7,6.8,6.9,7,7.1,7.2,7.3,7.4,7.5,7.6,7.7,7.8,7.9,8,8.1,8.2,8.3,8.4,8.5,8.6,8.7,8.8,8.9,9,9.1,9.2,9.3,9.4,9.5,9.6,9.7,9.8,9.9,10,10.1,10.2,10.3,10.4,10.5,10.6,10.7,10.8,10.9,11,11.1,11.2,11.3,11.4,11.5,11.6,11.7,11.8,11.9,12,12.1,12.2,12.3,12.4,12.5,12.6,12.7,12.8,12.9,13,13.1,13.2,13.3,13.4,13.5,13.6,13.7,13.8,13.9,14,14.1,14.2,14.3,14.4,14.5,14.6,14.7,14.8,14.9,15,15.1,15.2,15.3,15.4,15.5,15.6,15.7,15.8,15.9,16,16.1,16.2,16.3,16.4,16.5,16.6,16.7,16.8,16.9,17,17.1,17.2,17.3,17.4,17.5,17.6,17.7,17.8,17.9,18,18.1,18.2,18.3,18.4,18.5,18.6,18.7,18.8,18.9,19,19.1,19.2,19.3,19.4,19.5,19.6,19.7,19.8,19.9,20,20.1,20.2,20.3,20.4,20.5,20.6,20.7,20.8,20.9,21,21.1,21.2,21.3,21.4,21.5,21.6,21.7,21.8,21.9,22,22.1,22.2,22.3,22.4,22.5,22.6,22.7,22.8,22.9,23,23.1,23.2,23.3,23.4,23.5,23.6,23.7,23.8,23.9,24,24.1,24.2,24.3,24.4,24.5,24.6,24.7,24.8,24.9,25,25.1,25.2,25.3,25.4,25.5,25.6,25.7,25.8,25.9,26,26.1,26.2,26.3,26.4,26.5,26.6,26.7,26.8,26.9,27,27.1,27.2,27.3,27.4,27.5,27.6,27.7,27.8,27.9,28,28.1,28.2,28.3,28.4,28.5,28.6,28.7,28.8,28.9,29,29.1,29.2,29.3,29.4,29.5,29.6,29.7,29.8,29.9,30,30.1,30.2,30.3,30.4,30.5,30.6,30.7,30.8,30.9,31,31.1,31.2,31.3,31.4,31.5,31.6,31.7,31.8,31.9,32,32.1,32.2,32.3,32.4,32.5,32.6,32.7,32.8,32.9,33,33.1,33.2,33.3,33.4,33.5,33.6,33.7,33.8,33.9,34,34.1,34.2,34.3,34.4,34.5,34.6,34.7,34.8,34.9,35,35.1,35.2,35.3,35.4,35.5,35.6,35.7,35.8,35.9,36,36.1,36.2,36.3,36.4,36.5,36.6,36.7,36.8,36.9,37,37.1,37.2,37.3,37.4,37.5,37.6,37.7,37.8,37.9,38,38.1,38.2,38.3,38.4,38.5,38.6,38.7,38.8,38.9,39,39.1,39.2,39.3,39.4,39.5,39.6,39.7,39.8,39.9,40,40.1,40.2,40.3,40.4,40.5,40.6,40.7,40.8,40.9,41,41.1,41.2,41.3,41.4,41.5,41.6,41.7,41.8,41.9,42,42.1,42.2,42.3,42.4,42.5,42.6,42.7,42.8,42.9,43,43.1,43.2,43.3,43.4,43.5,43.6,43.7,43.8,43.9,44,44.1,44.2,44.3,44.4,44.5,44.6,44.7,44.8,44.9,45,45.1,45.2,45.3,45.4,45.5,45.6,45.7,45.8,45.9,46,46.1,46.2,46.3,46.4,46.5,46.6,46.7,46.8,46.9,47,47.1,47.2,47.3,47.4,47.5,47.6,47.7,47.8,47.9,48,48.1,48.2,48.3,48.4,48.5,48.6,48.7,48.8,48.9,49,49.1,49.2,49.3,49.4,49.5,49.6,49.7,49.8,49.9,50,50.1,50.2,50.3,50.4,50.5,50.6,50.7,50.8,50.9,51,51.1,51.2,51.3,51.4,51.5,51.6,51.7,51.8,51.9,52,52.1,52.2,52.3,52.4,52.5,52.6,52.7,52.8,52.9,53,53.1,53.2,53.3,53.4,53.5,53.6,53.7,53.8,53.9,54,54.1,54.2,54.3,54.4,54.5,54.6,54.7,54.8,54.9,55,55.1,55.2,55.3,55.4,55.5,55.6,55.7,55.8,55.9,56,56.1,56.2,56.3,56.4,56.5,56.6,56.7,56.8,56.9,57,57.1,57.2,57.3,57.4,57.5,57.6,57.7,57.8,57.9,58,58.1,58.2,58.3,58.4,58.5,58.6,58.7,58.8,58.9,59,59.1,59.2,59.3,59.4,59.5,59.6,59.7,59.8,59.9,60,60.1,60.2,60.3,60.4,60.5,60.6,60.7,60.8,60.9,61,61.1,61.2,61.3,61.4,61.5,61.6,61.7,61.8,61.9,62,62.1,62.2,62.3,62.4,62.5,62.6,62.7,62.8,62.9,63,63.1,63.2,63.3,63.4,63.5,63.6,63.7,63.8,63.9,64,64.1,64.2,64.3,64.4,64.5,64.6,64.7,64.8,64.9,65,65.1,65.2,65.3,65.4,65.5,65.6,65.7,65.8,65.9,66,66.1,66.2,66.3,66.4,66.5,66.6,66.7,66.8,66.9,67,67.1,67.2,67.3,67.4,67.5,67.6,67.7,67.8,67.9,68,68.1,68.2,68.3,68.4,68.5,68.6,68.7,68.8,68.9,69,69.1,69.2,69.3,69.4,69.5,69.6,69.7,69.8,69.9,70,70.1,70.2,70.3,70.4,70.5,70.6,70.7,70.8,70.9,71,71.1,71.2,71.3,71.4,71.5,71.6,71.7,71.8,71.9,72,72.1,72.2,72.3,72.4,72.5,72.6,72.7,72.8,72.9,73,73.1,73.2,73.3,73.4,73.5,73.6,73.7,73.8,73.9,74,74.1,74.2,74.3,74.4,74.5,74.6,74.7,74.8,74.9,75,75.1,75.2,75.3,75.4,75.5,75.6,75.7,75.8,75.9,76,76.1,76.2,76.3,76.4,76.5,76.6,76.7,76.8,76.9,77,77.1,77.2,77.3,77.4,77.5,77.6,77.7,77.8,77.9,78,78.1,78.2,78.3,78.4,78.5,78.6,78.7,78.8,78.9,79,79.1,79.2,79.3,79.4,79.5,79.6,79.7,79.8,79.9,80,80.1,80.2,80.3,80.4,80.5,80.6,80.7,80.8,80.9,81,81.1,81.2,81.3,81.4,81.5,81.6,81.7,81.8,81.9,82,82.1,82.2,82.3,82.4,82.5,82.6,82.7,82.8,82.9,83,83.1,83.2,83.3,83.4,83.5,83.6,83.7,83.8,83.9,84,84.1,84.2,84.3,84.4,84.5,84.6,84.7,84.8,84.9,85,85.1,85.2,85.3,85.4,85.5,85.6,85.7,85.8,85.9,86,86.1,86.2,86.3,86.4,86.5,86.6,86.7,86.8,86.9,87,87.1,87.2,87.3,87.4,87.5,87.6,87.7,87.8,87.9,88,88.1,88.2,88.3,88.4,88.5,88.6,88.7,88.8,88.9,89,89.1,89.2,89.3,89.4,89.5,89.6,89.7,89.8,89.9,90,90.1,90.2,90.3,90.4,90.5,90.6,90.7,90.8,90.9,91,91.1,91.2,91.3,91.4,91.5,91.6,91.7,91.8,91.9,92,92.1,92.2,92.3,92.4,92.5,92.6,92.7,92.8,92.9,93,93.1,93.2,93.3,93.4,93.5,93.6,93.7,93.8,93.9,94,94.1,94.2,94.3,94.4,94.5,94.6,94.7,94.8,94.9,95,95.1,95.2,95.3,95.4,95.5,95.6,95.7,95.8,95.9,96,96.1,96.2,96.3,96.4,96.5,96.6,96.7,96.8,96.9,97,97.1,97.2,97.3,97.4,97.5,97.6,97.7,97.8,97.9,98,98.1,98.2,98.3,98.4,98.5,98.6,98.7,98.8,98.9,99,99.1,99.2,99.3,99.4,99.5,99.6,99.7,99.8,99.9,100,100.1,100.2,100.3,100.4,100.5,100.6,100.7,100.8,100.9,101,101.1,101.2,101.3,101.4,101.5,101.6,101.7,101.8,101.9,102,102.1,102.2,102.3,102.4,102.5,102.6,102.7,102.8,102.9,103,103.1,103.2,103.3,103.4,103.5,103.6,103.7,103.8,103.9,104,104.1,104.2,104.3,104.4,104.5,104.6,104.7,104.8,104.9,105,105.1,105.2,105.3,105.4,105.5,105.6,105.7,105.8,105.9,106,106.1,106.2,106.3,106.4,106.5,106.6,106.7,106.8,106.9,107,107.1,107.2,107.3,107.4,107.5,107.6,107.7,107.8,107.9,108,108.1,108.2,108.3,108.4,108.5,108.6,108.7,108.8,108.9,109,109.1,109.2,109.3,109.4,109.5,109.6,109.7,109.8,109.9,110,110.1,110.2,110.3,110.4,110.5,110.6,110.7,110.8,110.9,111,111.1,111.2,111.3,111.4,111.5,111.6,111.7,111.8,111.9,112,112.1,112.2,112.3,112.4,112.5,112.6,112.7,112.8,112.9,113,113.1,113.2,113.3,113.4,113.5,113.6,113.7,113.8,113.9,114,114.1,114.2,114.3,114.4,114.5,114.6,114.7,114.8,114.9,115,115.1,115.2,115.3,115.4,115.5,115.6,115.7,115.8,115.9,116,116.1,116.2,116.3,116.4,116.5,116.6,116.7,116.8,116.9,117,117.1,117.2,117.3,117.4,117.5,117.6,117.7,117.8,117.9,118,118.1,118.2,118.3,118.4,118.5,118.6,118.7,118.8,118.9,119,119.1,119.2,119.3,119.4,119.5,119.6,119.7,119.8,119.9,120,120.1,120.2,120.3,120.4,120.5,120.6,120.7,120.8,120.9,121,121.1,121.2,121.3,121.4,121.5,121.6,121.7,121.8,121.9,122,122.1,122.2,122.3,122.4,122.5,122.6,122.7,122.8,122.9,123,123.1,123.2,123.3,123.4,123.5,123.6,123.7,123.8,123.9,124,124.1,124.2,124.3,124.4,124.5,124.6,124.7,124.8,124.9,125,125.1,125.2,125.3,125.4,125.5,125.6,125.7,125.8,125.9,126,126.1,126.2,126.3,126.4,126.5,126.6,126.7,126.8,126.9,127,127.1,127.2,127.3,127.4,127.5,127.6,127.7,127.8,127.9,128,128.1,128.2,128.3,128.4,128.5,128.6,128.7,128.8,128.9,129,129.1,129.2,129.3,129.4,129.5,129.6,129.7,129.8,129.9,130,130.1,130.2,130.3,130.4,130.5,130.6,130.7,130.8,130.9,131,131.1,131.2,131.3,131.4,131.5,131.6,131.7,131.8,131.9,132,132.1,132.2,132.3,132.4,132.5,132.6,132.7,132.8,132.9,133,133.1,133.2,133.3,133.4,133.5,133.6,133.7,133.8,133.9,134,134.1,134.2,134.3,134.4,134.5,134.6,134.7,134.8,134.9,135,135.1,135.2,135.3,135.4,135.5,135.6,135.7,135.8,135.9,136,136.1,136.2,136.3,136.4,136.5,136.6,136.7,136.8,136.9,137,137.1,137.2,137.3,137.4,137.5,137.6,137.7,137.8,137.9,138,138.1,138.2,138.3,138.4,138.5,138.6,138.7,138.8,138.9,139,139.1,139.2,139.3,139.4,139.5,139.6,139.7,139.8,139.9,140,140.1,140.2,140.3,140.4,140.5,140.6,140.7,140.8,140.9,141,141.1,141.2,141.3,141.4,141.5,141.6,141.7,141.8,141.9,142,142.1,142.2,142.3,142.4,142.5,142.6,142.7,142.8,142.9,143,143.1,143.2,143.3,143.4,143.5,143.6,143.7,143.8,143.9,144,144.1,144.2,144.3,144.4,144.5,144.6,144.7,144.8,144.9,145,145.1,145.2,145.3,145.4,145.5,145.6,145.7,145.8,145.9,146,146.1,146.2,146.3,146.4,146.5,146.6,146.7,146.8,146.9,147,147.1,147.2,147.3,147.4,147.5,147.6,147.7,147.8,147.9,148,148.1,148.2,148.3,148.4,148.5,148.6,148.7,148.8,148.9,149,149.1,149.2,149.3,149.4,149.5,149.6,149.7,149.8,149.9,150],
  etc:  [0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1,1.1,1.2,1.3,1.4,1.5,1.6,1.7,1.8,1.9,2,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,3,3.1,3.2,3.3,3.4,3.5,3.6,3.7,3.8,3.9,4,4.1,4.2,4.3,4.4,4.5,4.6,4.7,4.8,4.9,5,5.1,5.2,5.3,5.4,5.5,5.6,5.7,5.8,5.9,6,6.1,6.2,6.3,6.4,6.5,6.6,6.7,6.8,6.9,7,7.1,7.2,7.3,7.4,7.5,7.6,7.7,7.8,7.9,8,8.1,8.2,8.3,8.4,8.5,8.6,8.7,8.8,8.9,9,9.1,9.2,9.3,9.4,9.5,9.6,9.7,9.8,9.9,10,10.1,10.2,10.3,10.4,10.5,10.6,10.7,10.8,10.9,11,11.1,11.2,11.3,11.4,11.5,11.6,11.7,11.8,11.9,12,12.1,12.2,12.3,12.4,12.5,12.6,12.7,12.8,12.9,13,13.1,13.2,13.3,13.4,13.5,13.6,13.7,13.8,13.9,14,14.1,14.2,14.3,14.4,14.5,14.6,14.7,14.8,14.9,15],
}
const legendRanges = {
  savi: { min: -1,  max: 1   },
  kc:   { min:  0,  max: 1.5 },
  cwr:  { min:  0,  max: 150 },
  iwr:  { min:  0,  max: 150 },
  etc:  { min:  0,  max: 15  },
}

function showLegendValue(e, layer) {
  const rect = e.currentTarget.getBoundingClientRect()
  const pct  = (e.clientX - rect.left) / rect.width
  const b    = legendBreakpoints[layer]
  const idx  = Math.min(b.length - 2, Math.max(0, Math.floor(pct * (b.length - 1))))
  legendValue.value = `${layer.toUpperCase()}: ${b[idx]} – ${b[idx + 1] ?? b[idx]}`
  tooltipX.value = e.clientX + 12
  tooltipY.value = e.clientY - 10
}

function filterByLegendRange(e, layer) {
  if (!mapViewRef.value?.applyFilter) return
  const rect = e.currentTarget.getBoundingClientRect()
  const pct  = (e.clientX - rect.left) / rect.width
  const r    = legendRanges[layer]
  const v    = r.min + pct * (r.max - r.min)
  const d    = 0.1
}
</script>
<style>
:root {
  --brand-primary: #2f855a;
  --brand-primary-10: rgba(47, 133, 90, 0.1);
  --brand-primary-16: rgba(47, 133, 90, 0.16);
  --brand-primary-24: rgba(47, 133, 90, 0.24);
  --brand-primary-32: rgba(47, 133, 90, 0.32);
  --brand-primary-45: rgba(47, 133, 90, 0.45);
  --brand-accent: #2b6cb0;
  --brand-accent-soft: #7fb3d5;
  --brand-surface: #102235;
  --brand-surface-2: #142b40;
  --brand-surface-3: #1b354d;
  --brand-border: rgba(179, 205, 224, 0.18);
  --brand-text: #edf4f8;
  --brand-text-soft: #b9cada;
  --brand-text-muted: #88a0b8;
  --brand-warning: #d69e2e;
  --dashboard-header-height: 64px;
  --sidebar-width: clamp(296px, 25vw, 356px);

  /* ETc purple-cyan palette vars */
  --etc-purple-deep: #4A148C;
  --etc-purple-mid:  #8E24AA;
  --etc-pink:        #CE93D8;
  --etc-cyan-light:  #B2EBF2;
  --etc-cyan:        #26C6DA;
  --etc-blue-deep:   #0D47A1;
}

.dashboard-shell {
  font-family: 'Space Grotesk', sans-serif;
  background:
    radial-gradient(circle at top left, rgba(43, 108, 176, 0.16), transparent 28%),
    linear-gradient(180deg, #0b1827 0%, #102133 46%, #0d1a29 100%);
  color: var(--brand-text);
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  min-height: min(560px, 100dvh);
  overflow: hidden;
  animation: dashboardIn 0.34s cubic-bezier(.2,.8,.2,1) both;
}

@keyframes dashboardIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Header ── */
.dash-header {
  min-height: var(--dashboard-header-height);
  background: rgba(8, 20, 32, 0.94);
  border-bottom: 1px solid var(--brand-border);
  display: flex;
  align-items: center;
  padding: 10px clamp(10px, 1.7vw, 18px);
  gap: 14px;
  flex-shrink: 0;
  z-index: 120;
  box-shadow: 0 12px 34px rgba(2, 8, 16, 0.24);
  backdrop-filter: blur(16px) saturate(1.15);
  -webkit-backdrop-filter: blur(16px) saturate(1.15);
  animation: dashboardHeaderIn 0.32s 0.06s cubic-bezier(.2,.8,.2,1) both;
}
@keyframes dashboardHeaderIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
.header-brand {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: clamp(6px, 1.2vw, 12px);
  flex: 0 0 auto;
}
.brand-mark-group {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: clamp(8px, 1.4vw, 14px);
}
.dash-logo {
  height: clamp(28px, 4vw, 38px);
  max-width: clamp(52px, 8vw, 92px);
  object-fit: contain;
  flex-shrink: 0;
}
.brand-separator { width:1px; height:32px; background:var(--brand-border); flex-shrink:0; }
.header-titles { position:absolute; left:50%; transform:translateX(-50%); text-align:center; }
.header-title { font-size:.82rem; color:#93c5aa; font-family:'JetBrains Mono',monospace; font-weight:600; text-transform:uppercase; letter-spacing:.08em; white-space:nowrap; margin:0; }
.header-right {
  min-width: 0;
  margin-left: auto;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  gap:10px;
  flex:1 1 auto;
  overflow-x:auto;
  overflow-y:hidden;
  scrollbar-width:none;
  -webkit-overflow-scrolling: touch;
}
.header-right::-webkit-scrollbar { display:none; }
.trend-btn { display:flex; align-items:center; justify-content:center; gap:8px; min-height:38px; padding:8px 14px; border-radius:50px; border:1px solid var(--brand-border); background:rgba(255,255,255,.06); color:var(--brand-text-soft); font-size:.75rem; font-family:'JetBrains Mono',monospace; font-weight:600; cursor:pointer; transition:transform .2s ease, border-color .2s ease, background .2s ease, color .2s ease, box-shadow .2s ease; white-space:nowrap; flex:0 0 auto; }
.trend-btn:hover { border-color:var(--brand-primary-45); color:#d8e7f1; background:rgba(255,255,255,.09); transform:translateY(-1px); }
.trend-btn.active { border-color:var(--brand-primary); color:#dff3e7; background:var(--brand-primary-16); box-shadow:0 10px 24px rgba(47, 133, 90, 0.12); }
.calendar-btn { display:flex; align-items:center; justify-content:center; gap:8px; min-height:38px; padding:6px 14px; border-radius:50px; border:1px solid rgba(127, 179, 213, 0.28); background:rgba(127, 179, 213, 0.12); color:#d3e5f2; font-size:.75rem; font-family:'JetBrains Mono',monospace; font-weight:600; cursor:pointer; transition:transform .2s ease, border-color .2s ease, background .2s ease; white-space:nowrap; flex:0 0 auto; }
.calendar-btn:hover, .calendar-btn.active { background:rgba(127, 179, 213, 0.18); border-color:rgba(127, 179, 213, 0.46); transform:translateY(-1px); }
.icon-btn { width:38px; height:38px; border-radius:10px; display:flex; align-items:center; justify-content:center; background:transparent; border:none; cursor:pointer; color:var(--brand-text-muted); transition:all .2s; flex-shrink:0; }
.icon-btn:hover { color:#fff; background:rgba(255,255,255,.08); }
.home-btn { width:38px; height:38px; display:flex; align-items:center; justify-content:center; border-radius:10px; font-size:.9rem; font-family:'JetBrains Mono',monospace; font-weight:500; color:var(--brand-text-muted); background:transparent; border:1px solid transparent; cursor:pointer; white-space:nowrap; transition:all .2s ease; }
.home-btn:hover { color:#cbe6d7; border-color:var(--brand-primary-32); background:var(--brand-primary-10); transform:translateY(-1px); }

/* ── Body / Sidebar / Map ── */
.dash-body { flex:1; display:flex; overflow:hidden; min-height:0; position:relative; isolation:isolate; }
.sidebar-scrim { display:none; }
.sidebar-panel { width:0; background:linear-gradient(180deg, rgba(9, 22, 35, 0.98), rgba(16, 40, 55, 0.96)); border-right:1px solid var(--brand-border); overflow:hidden; transition:width .28s ease, transform .28s ease, box-shadow .28s ease; flex-shrink:0; z-index:80; box-shadow:10px 0 34px rgba(3, 10, 18, 0); }
.sidebar-panel.open { width:var(--sidebar-width); box-shadow:10px 0 34px rgba(3, 10, 18, 0.2); }
.sidebar-panel.closed { width:0; }
.sidebar-content { width:var(--sidebar-width); min-width:min(280px, 100vw); height:100%; padding:clamp(14px, 1.55vw, 20px); overflow-y:auto; scrollbar-width:thin; scrollbar-color:rgba(127, 179, 213, 0.28) transparent; }
.sidebar-content::-webkit-scrollbar { width:5px; }
.sidebar-content::-webkit-scrollbar-thumb { background:rgba(127, 179, 213, 0.24); border-radius:999px; }
.sidebar-top { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:18px; padding:14px; border:1px solid rgba(185, 202, 218, 0.12); border-radius:16px; background:linear-gradient(135deg, rgba(47, 133, 90, 0.16), rgba(59, 159, 217, 0.1)); box-shadow:inset 0 1px 0 rgba(255,255,255,.06); }
.sidebar-eyebrow { margin:0 0 3px; color:#96d8b0; font-size:.64rem; font-family:'JetBrains Mono',monospace; font-weight:700; text-transform:uppercase; letter-spacing:.13em; }
.sidebar-top h2 { margin:0; font-size:1rem; color:#f5fbff; letter-spacing:0; }
.sidebar-collapse-btn { width:32px; height:32px; border-radius:10px; border:1px solid rgba(185, 202, 218, 0.15); background:rgba(255,255,255,.06); color:#d8e7f1; display:flex; align-items:center; justify-content:center; cursor:pointer; transition:all .2s ease; }
.sidebar-collapse-btn:hover { background:rgba(255,255,255,.11); transform:translateX(-1px); }
.sidebar-section-label { font-size:.7rem; color:var(--brand-text-muted); font-family:'JetBrains Mono',monospace; font-weight:700; text-transform:uppercase; letter-spacing:.12em; margin:0 0 12px; padding:0 2px; }
.layer-card { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:64px; padding:12px 14px; border-radius:12px; border:1px solid rgba(185, 202, 218, 0.12); background:rgba(255,255,255,.045); cursor:pointer; margin-bottom:10px; box-shadow:inset 0 1px 0 rgba(255,255,255,.03); transition:transform .2s ease, border-color .2s ease, background .2s ease, box-shadow .2s ease; }
.sidebar-panel.open .layer-card { animation: layerCardIn 0.24s cubic-bezier(.2,.8,.2,1) both; }
@keyframes layerCardIn {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}
.layer-card:hover { transform:translateX(3px); border-color:rgba(127, 179, 213, 0.28); background:rgba(255,255,255,.07); box-shadow:0 12px 24px rgba(3, 10, 18, 0.18); }
.layer-card.active { border-color:var(--brand-primary-45); background:linear-gradient(135deg, rgba(47, 133, 90, 0.2), rgba(59, 159, 217, 0.1)); box-shadow:0 12px 28px rgba(47, 133, 90, 0.1); }
.layer-left { display:flex; align-items:center; gap:12px; min-width:0; }
.layer-left > div { min-width:0; }
.layer-ico { width:34px; height:34px; border-radius:12px; display:flex; align-items:center; justify-content:center; flex:0 0 auto; background:rgba(127, 179, 213, 0.12); border:1px solid rgba(127, 179, 213, 0.18); color:#dceef8; font-size:.7rem; font-family:'JetBrains Mono',monospace; font-weight:800; letter-spacing:0; }
.layer-card.active .layer-ico { background:rgba(47, 133, 90, 0.28); border-color:rgba(47, 133, 90, 0.36); color:#ecfff4; }
.layer-key { font-size:.9rem; font-weight:700; margin:0; }
.layer-name { font-size:.72rem; color:var(--brand-text-muted); margin:2px 0 0; line-height:1.35; }
.toggle-track { width:44px; height:22px; border-radius:12px; background:#415a71; position:relative; flex-shrink:0; transition:background .2s ease, box-shadow .2s ease; }
.toggle-track.on { background:var(--brand-primary); box-shadow:0 0 0 4px rgba(47, 133, 90, 0.12); }
.toggle-thumb { position:absolute; top:2px; left:2px; width:18px; height:18px; border-radius:50%; background:white; transition:left .2s ease, transform .2s ease; box-shadow:0 2px 8px rgba(0,0,0,.22); }
.toggle-thumb.on { left:24px; }

/* Legend strips */
.legend-strip { padding:10px 12px 14px; margin:0 10px 10px; background:rgba(8, 20, 32, 0.44); border:1px solid rgba(185, 202, 218, 0.08); border-radius:12px; animation: legendStripIn 0.2s cubic-bezier(.2,.8,.2,1) both; }
@keyframes legendStripIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
.legend-labels-horizontal { display:flex; justify-content:space-between; margin-bottom:4px; }
.legend-labels-horizontal span { font-size:.65rem; color:var(--brand-text-muted); font-family:'JetBrains Mono',monospace; }
.legend-bar-horizontal { width:100%; height:28px; border-radius:6px; cursor:pointer; }
/* Legend gradients now generated dynamically via getLegendGradient() */

.legend-tooltip { position:fixed; background:rgba(8, 18, 30, 0.96); color:var(--brand-text); font-size:.75rem; padding:6px 14px; border-radius:8px; pointer-events:none; z-index:9999; font-family:'JetBrains Mono',monospace; white-space:nowrap; border:1px solid var(--brand-border); }

/* Opacity control */
.ctrl-card { margin-top:16px; padding:14px 16px; border-radius:14px; border:1px solid rgba(185, 202, 218, 0.12); background:rgba(255,255,255,.04); }
.ctrl-row { display:flex; justify-content:space-between; margin-bottom:10px; font-size:.85rem; color:var(--brand-text-muted); }
.ctrl-val { color:#cfe9da; font-weight:700; }
.range-slider { width:100%; height:5px; border-radius:3px; appearance:none; background:#415a71; }
.range-slider::-webkit-slider-thumb { appearance:none; width:18px; height:18px; border-radius:50%; background:var(--brand-primary); cursor:pointer; border:2px solid #f7fbfd; }
.map-area { flex:1 1 auto; position:relative; overflow:hidden; min-width:0; min-height:0; animation: mapAreaIn 0.38s 0.1s cubic-bezier(.2,.8,.2,1) both; }
@keyframes mapAreaIn {
  from { opacity: 0; transform: scale(0.995); }
  to { opacity: 1; transform: scale(1); }
}

/* ── Calendar overlay ── */
.calendar-float-panel {
  position: fixed;
  top: 60px;
  right: 40px;
  z-index: 5000;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  pointer-events: none;
}
.calendar-float-panel .cal-panel {
  pointer-events: auto;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 24px;
  width: min(460px, 96vw);
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: calSlideDown .2s;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
}

@keyframes calSlideDown { from{opacity:0;transform:translateY(-18px)} to{opacity:1;transform:translateY(0)} }
@keyframes slideInWeatherRight { from{opacity:0;transform:translateX(30px)} to{opacity:1;transform:translateX(0)} }
@keyframes calSpin { to{transform:rotate(360deg)} }

.cal-header { padding:18px 22px 14px; border-bottom:1px solid rgba(0,0,0,0.08); background:linear-gradient(180deg, rgba(0,0,0,0.02), rgba(0,0,0,0)); }
.cal-title-row { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.cal-title { font-size:1rem; font-weight:700; flex:1; color:#1a202c; }
.cal-close { width:30px; height:30px; background:rgba(0,0,0,0.04); border:1px solid rgba(0,0,0,0.1); border-radius:50%; color:#4a5568; cursor:pointer; display:flex; align-items:center; justify-content:center; }
.cal-close:hover { background:rgba(18, 209, 184, 0.14); color:#1a6659; border-color:rgba(18, 209, 184, 0.24); }
.cal-subtitle { font-size:.76rem; color:#4a5568; margin:0 0 12px; }

/* ── Calendar filter chips ── */
.cal-filter-row { display:flex; flex-direction:column; gap:8px; }
.cal-filter-group { display:flex; flex-direction:column; gap:4px; }
.cal-filter-label { font-size:.66rem; font-weight:700; color:#4a5568; text-transform:uppercase; letter-spacing:.06em; }
.cal-filter-chips { display:flex; flex-wrap:wrap; gap:5px; }
.cal-chip {
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(0,0,0,0.12);
  background: rgba(255,255,255,0.6);
  color: #2d3748;
  font-size: .7rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all .15s;
}
.cal-chip:hover { background: rgba(47, 133, 90, 0.08); border-color: rgba(47, 133, 90, 0.3); }
.cal-chip.active { background: linear-gradient(135deg, #2f855a, #38a169); color: #fff; border-color: #2f855a; box-shadow: 0 2px 8px rgba(47, 133, 90, 0.24); }
.cal-chip-count { font-size:.62rem; opacity:.8; }

/* ── Calendar grid / months ── */
.cal-scroll { overflow-y:auto; flex:1; padding:14px 22px 20px; display:flex; flex-direction:column; gap:20px; }
.cal-empty { padding:48px; text-align:center; color:#718096; font-size:.85rem; }
.cal-month-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.cal-month-label { font-size:.92rem; font-weight:700; color:#1a202c; margin:0; }
.cal-month-season-badge { font-size:.66rem; padding:2px 8px; border-radius:999px; background:rgba(47, 133, 90, 0.12); color:#22543d; border:1px solid rgba(47, 133, 90, 0.22); font-weight:600; }
.cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:5px; }
.cal-dow { font-size:.66rem; color:#4a5568; text-align:center; padding:4px 0; letter-spacing:.04em; }
.cal-day { height:46px; border-radius:12px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#f7fafc; border:1px solid rgba(0, 0, 0, 0.08); transition:all .18s ease; }
.cal-day-num { font-size:.82rem; color:#2d3748; }
.cal-day-dot { width:7px; height:7px; border-radius:50%; background:#2f855a; margin-top:4px; box-shadow:0 0 0 4px rgba(47, 133, 90, 0.12); }
.cal-day-dot-forecast { background:#3182ce; box-shadow:none; }
.cal-day-has-data { background:linear-gradient(180deg, #c6f6d5 0%, #9ae6b4 100%); border-color:rgba(47, 133, 90, 0.34); }
.cal-day-has-data .cal-day-num { color:#1a202c; font-weight:700; }
.cal-day-has-forecast { background:rgba(66, 153, 225, 0.12); border-color:rgba(49, 130, 206, 0.24); }
.cal-day-has-forecast .cal-day-num { color:#1a365d; }
.cal-day-clickable { cursor:pointer; }
.cal-day-clickable:hover { transform:translateY(-1px); border-color:rgba(47, 133, 90, 0.4); }
.cal-day-selected { background:linear-gradient(180deg, #48bb78 0%, #38a169 100%)!important; border-color:#2f855a!important; box-shadow:0 0 0 1px rgba(47, 133, 90, 0.3), 0 10px 24px rgba(0, 0, 0, 0.15); }
.cal-day-selected .cal-day-num { color:#ffffff; font-weight:800; }
.cal-day-today { border-color:rgba(237, 137, 54, 0.8); }
.cal-day-empty { background:transparent; border-color:transparent; }
.cal-day-future { opacity:.5; cursor:not-allowed; }
.cal-day-past { opacity:.75; }
.cal-loading { display:flex; justify-content:center; gap:14px; padding:48px; color:#4a5568; }
.cal-spinner { width:22px; height:22px; border:2px solid rgba(47, 133, 90, 0.18); border-top-color:var(--brand-primary); border-radius:50%; animation:calSpin .8s linear infinite; }
.cal-footer { padding:12px 22px; border-top:1px solid rgba(0,0,0,0.08); display:flex; justify-content:space-between; gap:12px; background:rgba(247, 250, 252, 0.8); }
.cal-sel-info { display:flex; gap:8px; font-size:.8rem; color:#2d3748; align-items:center; flex-wrap:wrap; }
.cal-sel-badge { padding:3px 8px; border-radius:999px; background:rgba(47, 133, 90, 0.14); border:1px solid rgba(47, 133, 90, 0.24); color:#22543d; font-size:.68rem; }
.cal-sel-badge-forecast { background:rgba(49, 130, 206, 0.14); border-color:rgba(49, 130, 206, 0.24); color:#1a365d; }
.cal-sel-badge-past { background:rgba(128, 90, 213, 0.14); border-color:rgba(128, 90, 213, 0.24); color:#44337a; }
.cal-clear-btn { padding:7px 14px; border-radius:10px; border:1px solid rgba(0, 0, 0, 0.12); background:rgba(255,255,255,0.8); color:#2d3748; cursor:pointer; }
.cal-clear-btn:hover { background:rgba(0,0,0,.06); }

/* ── Weather panel ── */
.weather-panel-wrapper { position:fixed; top:0; right:0; bottom:0; z-index:5000; display:flex; align-items:center; justify-content:flex-end; pointer-events:none; }
.weather-panel { background:linear-gradient(180deg, #102235 0%, #132a40 100%); border:1px solid var(--brand-border); border-radius:24px; width:min(520px,96vw); max-height:88vh; display:flex; flex-direction:column; overflow:hidden; animation:slideInWeatherRight .28s ease; box-shadow:0 28px 70px rgba(4, 10, 18, 0.46); pointer-events:all; margin-right:20px; margin-bottom:20px; }
.weather-header { padding:18px 20px 14px; border-bottom:1px solid rgba(255,255,255,.06); }
.weather-title-row { display:flex; align-items:center; gap:14px; }
.weather-main-icon { font-size:2rem; }
.weather-title-meta { flex:1; }
.weather-title { font-size:1rem; font-weight:700; color:#fff; display:flex; flex-direction:column; gap:2px; }
.weather-today-label { font-size:.72rem; font-weight:400; color:var(--brand-text-muted); }
.weather-loc-row { display:flex; align-items:center; gap:8px; font-size:.75rem; color:var(--brand-text-muted); flex-wrap:wrap; }
.weather-locate-btn { display:flex; align-items:center; gap:4px; padding:4px 10px; border-radius:20px; border:1px solid rgba(47, 133, 90, 0.26); background:rgba(47, 133, 90, 0.12); color:#dcefe4; font-size:.65rem; cursor:pointer; }
.weather-loading { display:flex; justify-content:center; align-items:center; gap:12px; padding:60px; color:var(--brand-text-soft); }
.weather-content { overflow-y:auto; flex:1; padding:18px 20px; }
.weather-today-card { background:linear-gradient(135deg, rgba(17, 78, 105, 0.34), rgba(47, 133, 90, 0.18)); border:1px solid rgba(127, 179, 213, 0.24); border-radius:18px; padding:16px; display:flex; justify-content:space-between; margin-bottom:20px; }
.today-left { display:flex; flex-direction:column; gap:4px; }
.today-temp { font-size:2.2rem; font-weight:700; color:#d8f0e1; line-height:1; }
.today-desc { font-size:.9rem; color:#edf4f8; }
.today-date-label { font-size:.72rem; color:var(--brand-text-soft); }
.today-meta { display:flex; flex-direction:column; gap:6px; font-size:.74rem; color:var(--brand-text-soft); text-align:right; }
.forecast-label { font-size:.74rem; color:var(--brand-text-soft); text-transform:uppercase; margin:0 0 10px; letter-spacing:.06em; }
.forecast-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:6px; margin-bottom:20px; }
.forecast-day-card { background:rgba(255,255,255,.04); border:1px solid rgba(185, 202, 218, 0.08); border-radius:14px; padding:10px 8px; display:flex; flex-direction:column; align-items:center; gap:5px; cursor:pointer; transition:all .18s; }
.forecast-day-card:hover { transform:translateY(-1px); border-color:rgba(127, 179, 213, 0.2); }
.fc-card-selected { background:rgba(47, 133, 90, 0.14)!important; border-color:rgba(47, 133, 90, 0.28)!important; }
.fc-day { font-size:.62rem; color:var(--brand-text-muted); }
.fc-icon { font-size:1.1rem; }
.fc-temp { font-size:.82rem; font-weight:700; color:#fff; }
.fc-precip { font-size:.6rem; color:#8fd3ff; }
.wth-sources-section { margin-top:20px; padding-top:12px; border-top:1px solid rgba(255,255,255,.07); }
.wth-sources-inline { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:0; }
.wth-source-inline-link { font-size:.7rem; color:rgba(190, 205, 219, 0.72); text-decoration:none; }
.wth-source-inline-link:hover { color:#dce9f2; text-decoration:underline; }
.wth-source-sep { display:inline-block; margin:0 8px; color:rgba(190, 205, 219, 0.48); }
.wth-update-note { font-size:.64rem; color:var(--brand-text-muted); text-align:right; margin:8px 0 0; }
.weather-error { padding:40px; text-align:center; color:var(--brand-text-soft); }
.retry-btn { margin-top:12px; padding:6px 16px; border-radius:10px; border:1px solid var(--brand-primary-32); background:var(--brand-primary-10); color:#dcefe4; cursor:pointer; }
.weather-card { display:flex; align-items:center; gap:10px; min-width:0; max-width:min(280px, 40vw); min-height:38px; padding:7px 13px; border-radius:50px; background:rgba(255,255,255,.06); border:1px solid var(--brand-border); color:var(--brand-text); cursor:pointer; transition:transform .2s ease, border-color .2s ease, background .2s ease; flex:0 1 auto; }
.weather-card:hover { background:rgba(255,255,255,.1); border-color:rgba(127, 179, 213, 0.22); }
.wc-icon { font-size:1.2rem; line-height:1; }
.wc-center { min-width:0; display:flex; flex-direction:column; line-height:1.2; }
.wc-location { max-width:132px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:.7rem; color:var(--brand-text-soft); }
.wc-date { font-size:.65rem; color:#dcefe4; font-weight:600; }
.wc-temp { flex:0 0 auto; font-size:.95rem; font-weight:700; color:#f7fbfd; }

/* ── Responsive ── */
@media (max-width:1024px) {
  :root {
    --sidebar-width: min(320px, 88vw);
  }
  .dash-header {
    gap: 10px;
  }
  .weather-card {
    padding: 8px 11px;
  }
  .wc-location {
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

@media (max-width:900px) {
  .dashboard-shell {
    min-height: 100dvh;
  }
  .sidebar-scrim {
    position:absolute;
    inset:0;
    display:block;
    z-index:70;
    background:rgba(2, 8, 15, 0.36);
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
    animation: sidebarScrimIn .2s ease both;
  }
  @keyframes sidebarScrimIn {
    from { opacity:0; }
    to { opacity:1; }
  }
  .sidebar-panel {
    position:absolute;
    top:0;
    bottom:0;
    left:0;
    width:var(--sidebar-width);
    transform:translateX(-105%);
    box-shadow:18px 0 54px rgba(3, 10, 18, 0.4);
    border-right-color:rgba(185, 202, 218, 0.2);
  }
  .sidebar-panel.open {
    width:var(--sidebar-width);
    transform:translateX(0);
  }
  .sidebar-panel.closed {
    width:var(--sidebar-width);
    transform:translateX(-105%);
    pointer-events:none;
  }
  .sidebar-content {
    width:var(--sidebar-width);
  }
  .map-area {
    flex:1 1 auto;
  }
}

@media (max-width:760px) {
  :root {
    --dashboard-header-height: 108px;
  }
  .dash-header {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
    padding: 8px 10px 9px;
  }
  .header-brand {
    width: 100%;
    justify-content: space-between;
  }
  .brand-mark-group {
    flex: 1 1 auto;
    justify-content: center;
    gap: 10px;
  }
  .dash-logo {
    height: 30px;
    max-width: 84px;
  }
  .header-right {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
    gap: 7px;
    padding-bottom: 1px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .header-right::-webkit-scrollbar { display: none; }
  .header-right > * { scroll-snap-align: start; flex-shrink: 0; }
  .weather-card {
    flex: 0 0 auto;
    max-width: none;
    min-width: 152px;
  }
  .wc-location { max-width: 84px; }
  .header-titles { display: none; }
  .forecast-grid { grid-template-columns: repeat(4,1fr); }
  .trend-btn { padding: 8px 12px; }
  .calendar-float-panel { top: 76px; right: 16px; }
  .weather-panel-wrapper { align-items: flex-end; justify-content: flex-end; padding: 76px 16px 16px; }
  .weather-panel { width: calc(100% - 32px); max-width: 420px; margin: 0 0 16px; }
  .calendar-float-panel .cal-panel {
    max-height: calc(100dvh - 96px);
  }
}

@media (max-width: 620px) {
  :root {
    --dashboard-header-height: 106px;
  }
  .dash-header {
    padding: 7px 9px 8px;
    gap: 5px;
  }
  .weather-card {
    min-width: 138px;
  }
  .wc-location { max-width: 72px; }
}

@media (max-width:480px) {
  :root {
    --dashboard-header-height: 100px;
    --sidebar-width: min(330px, calc(100vw - 24px));
  }
  .dash-header {
    min-height: var(--dashboard-header-height);
    padding: 7px 8px 8px;
    gap: 5px;
  }
  .header-brand {
    gap: 5px;
  }
  .dash-logo {
    height: 26px;
    max-width: 72px;
  }
  .isro-logo {
    max-width: 52px;
  }
  .brand-separator { height: 24px; }
  .header-right {
    gap: 5px;
  }
  .weather-card {
    min-width: auto;
    padding: 7px 9px;
  }
  .wc-center { display: none; }
  .forecast-grid { grid-template-columns: repeat(2,1fr); }
  .trend-btn { padding: 7px 10px; font-size: 0.72rem; }
  .calendar-btn { padding: 7px 10px; font-size: 0.72rem; }
  .calendar-float-panel { top: 68px; right: 10px; left: 10px; justify-content: center; }
  .weather-panel-wrapper { padding: 68px 10px 10px; }
  .weather-panel { width: calc(100% - 20px); max-width: 100%; margin: 0 0 10px; }
  .calendar-float-panel .cal-panel {
    width: calc(100vw - 20px);
    max-height: calc(100dvh - 84px);
    border-radius: 18px;
  }
  .cal-header { padding: 14px 14px 12px; }
  .cal-scroll { padding: 12px 14px 16px; gap: 16px; }
  .cal-day {
    height: clamp(34px, 10.5vw, 42px);
    border-radius: 10px;
  }
  .cal-footer {
    padding: 10px 14px;
    flex-direction: column;
    align-items: stretch;
  }
  .cal-clear-btn { width: 100%; }
  .cal-filter-chips { gap: 4px; }
  .sidebar-content { padding: 12px; }
  .sidebar-top { padding: 12px; margin-bottom: 14px; }
  .layer-card { min-height: 56px; padding: 10px 12px; margin-bottom: 8px; }
  .layer-ico { width: 32px; height: 32px; border-radius: 10px; }
  .legend-strip { margin: 0 6px 8px; padding: 9px 10px 12px; }
  .ctrl-card { margin-top: 12px; padding: 12px; }
}

@media (max-width:380px) {
  :root {
    --dashboard-header-height: 95px;
  }
  .isro-logo, .brand-separator { display: none; }
  .dash-header { gap: 4px; }
  .icon-btn, .home-btn { min-width: 34px; width: 34px; }
  .trend-btn, .calendar-btn {
    min-width: 0;
    padding: 7px 9px;
    font-size: 0.7rem;
  }
  .trend-btn span, .calendar-btn span {
    display: none;
  }
  .trend-btn svg, .calendar-btn svg { margin: 0; }
  .wc-temp { font-size: 0.88rem; }
}

@media (max-width: 320px) {
  :root {
    --sidebar-width: calc(100vw - 16px);
  }
  .dash-header { padding: 6px 7px; }
  .weather-card { padding: 6px 8px; min-width: 0; }
  .wc-icon { font-size: 1rem; }
  .wc-temp { font-size: 0.82rem; }
}

@media (max-height:760px) and (min-width:481px) {
  .sidebar-content { padding: 14px; }
  .sidebar-top { margin-bottom: 12px; padding: 12px; }
  .sidebar-section-label { margin-bottom: 8px; }
  .layer-card { min-height: 56px; padding: 10px 12px; margin-bottom: 8px; }
  .legend-strip { padding: 8px 10px 10px; margin-bottom: 8px; }
  .legend-bar-horizontal { height: 22px; }
  .ctrl-card { margin-top: 10px; padding: 12px; }
}

@media (max-height: 600px) {
  :root {
    --dashboard-header-height: clamp(48px, 8vh, 60px);
  }
  .dash-header {
    min-height: var(--dashboard-header-height);
    padding: 5px clamp(8px, 1.5vw, 16px);
    gap: 8px;
  }
  .dash-logo { height: clamp(22px, 4vh, 30px); }
  .brand-separator { height: clamp(18px, 3.5vh, 26px); }
  .sidebar-top { margin-bottom: 8px; padding: 10px; }
  .layer-card { min-height: 50px; padding: 8px 10px; margin-bottom: 6px; }
}

@media (prefers-reduced-motion: reduce) {
  .dashboard-shell,
  .dash-header,
  .map-area,
  .sidebar-panel.open .layer-card,
  .legend-strip,
  .calendar-float-panel .cal-panel,
  .weather-panel {
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
</style>