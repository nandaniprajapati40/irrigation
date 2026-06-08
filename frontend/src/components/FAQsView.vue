<!-- FAQsView.vue -->
<template>
  <div class="faq-root">
    <!-- ══════════════ HEADER ══════════════ -->
    <header class="app-header">
      <div class="app-header-inner">
        <div class="header-logos">
          <img src="/assets/logo1.png" class="iirs-logo" onerror="this.style.display='none'" />
          <img src="/assets/isro.png"  class="iirs-logo" onerror="this.style.display='none'" />
        </div>
        <div class="header-center">
          <h2>भारतीय अंतरिक्ष अनुसंधान संगठन, अंतरिक्ष विभाग</h2>
          <h3>Indian Space Research Organisation, Department of Space</h3>
          <h4>भारत सरकार / Government of India</h4>
        </div>
        <div class="header-logos header-logos-right">
          <img src="/assets/iirs.png"  class="iirs-logo" onerror="this.style.display='none'" />
          <img src="/assets/india.png" class="gov-logo"  onerror="this.style.display='none'" />
        </div>
      </div>
    </header>

    <!-- ══════════════ NAV ══════════════ -->
    <nav class="nav-bar">
      <div class="nav-inner">
        <div class="nav-links">
          <button @click="$emit('home')" class="nav-link">Home</button>
          <a class="nav-link" @click.prevent="$emit('docs')" href="#docs">Docs</a>
          <a class="nav-link active" @click.prevent="$emit('faqs')" href="#faqs">FAQs</a>
        </div>
      </div>
    </nav>

    <!-- ══════════════ HERO ══════════════ -->
    <div class="faq-hero">
      <p class="faq-hero-tag">HELP CENTER</p>
      <h1 class="faq-hero-title">Frequently Asked Questions</h1>
      <p class="faq-hero-sub">
        Got questions about jaldrishiti? We have simple answers.<br>
        No technical background needed — just plain, clear explanations.
      </p>

      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input
          id="faq-search-input"
          v-model="query"
          type="text"
          placeholder="Search questions… e.g. irrigation, satellite, wheat"
          class="search-input"
          autocomplete="off"
        />
        <button v-if="query" class="search-clear" @click="query = ''" aria-label="Clear search">✕</button>
      </div>

      <p v-if="query && filtered.length === 0" class="no-results">
        😕 No results for "<strong>{{ query }}</strong>". Try a different keyword.
      </p>
      <p v-else-if="query" class="result-count">
        ✅ Showing <strong>{{ filtered.length }}</strong> result{{ filtered.length !== 1 ? 's' : '' }} for "<strong>{{ query }}</strong>"
      </p>
    </div>

    <!-- ══════════════ FAQ LIST ══════════════ -->
    <div class="faq-list-wrap">
      <div
        v-for="(item, i) in filtered"
        :key="i"
        class="faq-card"
        :class="{ open: openIndex === i }"
      >
        <button class="faq-question" @click="toggle(i)" :aria-expanded="openIndex === i">
          <span class="faq-q-text" v-html="highlight(item.q)"></span>
          <span class="faq-chevron">{{ openIndex === i ? '−' : '+' }}</span>
        </button>
        <div class="faq-answer-wrap" :class="{ visible: openIndex === i }">
          <div class="faq-answer" v-html="highlight(item.a)"></div>
        </div>
      </div>
    </div>

    <!-- ══════════════ FOOTER ══════════════ -->
    <footer class="site-footer">
      <div class="footer-inner">
        <div>
          <p class="fb-name">Irrigation Water Requirements (IWR)</p>
          <p class="fb-sub">ISRO &nbsp;·&nbsp; IIRS &nbsp;·&nbsp; Department of Space, Govt. of India</p>
        </div>
        <p class="fb-sub">Udham Singh Nagar · Uttarakhand · Rabi Wheat</p>
      </div>
    </footer>

    <!-- ══════════════ FLOATING AQUABOT BUTTON ══════════════ -->
    <button
      class="fab-aquabot"
      @click="chatOpen = !chatOpen"
      :aria-label="chatOpen ? 'Close AquaBot' : 'Open AquaBot'"
    >
      <svg v-if="!chatOpen" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" width="24" height="24">
        <circle cx="18" cy="18" r="18" fill="white" fill-opacity="0.15"/>
        <path d="M10 22 Q14 10 18 14 Q22 18 26 12" stroke="#fff" stroke-width="2.2" stroke-linecap="round" fill="none"/>
        <circle cx="13" cy="20" r="1.8" fill="#fff" opacity=".9"/>
        <circle cx="23" cy="17" r="1.8" fill="#fff" opacity=".9"/>
        <path d="M14 27 Q18 30 22 27" stroke="#fff" stroke-width="1.8" stroke-linecap="round" fill="none"/>
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20">
        <path d="M18 6L6 18M6 6l12 12" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
      </svg>
      <span class="fab-label">{{ chatOpen ? 'Close' : 'AquaBot' }}</span>
    </button>

    <!-- ══════════════ SLIDING CHAT PANEL ══════════════ -->
    <Transition name="slide-up">
      <div v-if="chatOpen" class="fab-chat-panel">
        <div class="fab-chat-header">
          <div class="fab-chat-header-left">
            <img
                src="/assets/logo.png"
                alt="Logo"
                class="iirs-logo"
                onerror="this.style.display='none'"
            />
            <span>JalDrishtiBot — Irrigation Assistant</span>
          </div>
          <button class="fab-close-btn" @click="chatOpen = false" aria-label="Close AquaBot chat">
            <svg viewBox="0 0 16 16" fill="none" width="14" height="14">
              <path d="M12 4L4 12M4 4l8 8" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
        <div class="fab-chat-body">
          <AquaBotChat
            :api-base="apiBase"
            :session-id="fabChatSessionId"
            :lat="mapLat"
            :lon="mapLon"
            @connection-change="handleConnectionChange"
          />
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import AquaBotChat from './jaldrishtibot.vue'

defineProps({ isDark: { type: Boolean, default: false } })
defineEmits(['home', 'docs', 'faqs', 'launch'])

// ── FAQ state ────────────────────────────────────────────────────────────────
const query     = ref('')
const openIndex = ref(null)

function toggle(i) {
  openIndex.value = openIndex.value === i ? null : i
}

// ── AquaBot FAB state ────────────────────────────────────────────────────────
const chatOpen       = ref(false)
const fabChatSessionId = `fab-session-${Date.now()}`

// ── API base — empty string = same origin, nginx proxies /api/* → backend:8000
const apiBase = (
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE) || ''
)

const chatConnected = ref(true)
const mapLat        = ref(null)
const mapLon        = ref(null)

function handleConnectionChange(connected) {
  chatConnected.value = connected
}

// ── FAQ DATA ─────────────────────────────────────────────────────────────────
const faqs = [
  {
    q: 'What is jaldrishiti?',
    a: `<strong>jaldrishiti</strong> is a smart water advisory system built by ISRO/IIRS. Think of it like a weather app, but instead of showing rain forecasts it tells farmers <em>exactly how much water their wheat crop needs today</em>. It uses satellite images and weather data so farmers never over-water or under-water their fields.`
  },
  {
    q: 'Who is this system for?',
    a: `jaldrishiti is designed for <strong>farmers</strong>, <strong>irrigation department officers</strong>, and <strong>agricultural advisors</strong> in Udham Singh Nagar, Uttarakhand. You do not need any technical knowledge to use it. The dashboard shows simple numbers and colour-coded maps that anyone can read.`
  },
  {
    q: 'Why was jaldrishiti developed?',
    a: `Farmers in this region often water their fields based on old habits — sometimes watering too much, sometimes too little. This wastes water, increases electricity bills, and depletes underground water. jaldrishiti was created to give farmers a precise, daily recommendation so they can save water without losing crop yield.`
  },
  {
    q: 'Which area does it cover?',
    a: `Currently jaldrishiti covers <strong>Udham Singh Nagar district, Uttarakhand</strong> — a major wheat-growing area in the Terai region. The system is designed to be expanded to other districts and crops in the future.`
  },
  {
    q: 'What is Irrigation Water Requirement (IWR)?',
    a: `<strong>IWR</strong> is simply the amount of water your crop needs from irrigation. It is calculated as:<br><br>
    <code>Water Crop Needs − Rain Already Received = IWR</code><br><br>
    If it rained well, IWR is low (or zero). In dry periods, IWR is higher. jaldrishiti calculates this every day for your field automatically.`
  },
  {
    q: 'How much water does wheat need per day?',
    a: `It changes as the crop grows:<br><br>
    🌱 <strong>Early stage (weeks 1–4):</strong> about 2–3 mm/day (very little)<br>
    🌾 <strong>Growing stage (weeks 5–12):</strong> about 4–6 mm/day (peak demand)<br>
    🌾 <strong>Ripening stage (weeks 12+):</strong> demand drops back down<br><br>
    Over the full Rabi season, wheat in Udham Singh Nagar needs roughly <strong>300–380 mm</strong> of total water from irrigation.`
  },
  {
    q: 'How does the system know how much water my field needs?',
    a: `jaldrishiti uses <strong>satellite images</strong> taken every 5 days to check how green and healthy your crop is. It also reads local weather data (temperature, wind, humidity). Using these two inputs it estimates how much water the crop is using per day — and therefore how much needs to be replaced through irrigation.`
  },
  {
    q: 'Which satellites does jaldrishiti use?',
    a: `The system uses two main satellites:<br><br>
    🛰️ <strong>Sentinel-2</strong> (European Space Agency) – Takes detailed photographs of fields every 5 days to check crop health.<br>
    🛰️ <strong>INSAT-3DR</strong> (ISRO) – An Indian weather satellite that provides daily temperature and humidity data used to calculate water evaporation.`
  },
  {
    q: 'What if there are clouds and the satellite cannot see my field?',
    a: `Clouds are a common problem with satellites. When the view is blocked, jaldrishiti automatically uses the last available satellite reading combined with weather data to estimate the crop's current water need. You will still receive a daily advisory — the system just flags it as an estimate until the skies clear.`
  },
  {
    q: 'Is the data free? Do I need to pay for satellite images?',
    a: `<strong>No cost at all.</strong> All satellite data used by jaldrishiti comes from freely available sources — Sentinel-2 from ESA, INSAT-3DR from ISRO, and weather data from IMD. The entire system is a government-funded research initiative and is completely <strong>free for farmers</strong>.`
  },
  {
    q: 'How accurate is the water requirement estimate?',
    a: `jaldrishiti's estimates were tested against soil moisture sensors in 40 real farmer fields across three Rabi seasons (2022, 2023, 2024). Results showed the system is accurate to within <strong>±0.7 mm per day</strong>, which is more than precise enough for practical irrigation scheduling. Farmers who followed the advisories reduced water use by <strong>12–18%</strong> without any drop in yield.`
  },
  {
    q: 'Does using jaldrishiti save money?',
    a: `Yes. Less irrigation means less pumping, which means <strong>lower electricity or diesel bills</strong>. Farmers in the pilot study saved roughly <strong>80–100 cubic metres of groundwater per acre per season</strong>. Over a full season, this translates to measurable savings on energy costs.`
  },
  {
    q: 'How do I access the daily water advisory?',
    a: `You can access jaldrishiti through:<br><br>
    🌐 <strong>Web dashboard</strong> – works on mobile browsers and desktop computers.<br>
    🤖 <strong>AquaBot chatbot</strong> – type a simple question like "How much water does my field need today?" and get an instant answer.<br>
    📱 <strong>WhatsApp bot</strong> – coming soon for farmers without regular internet access.`
  },
  {
    q: 'Can I see a map of my own field?',
    a: `Yes. The interactive map in the dashboard shows your area coloured by water need — <em>red means high need, green means low need</em>. If your field boundary is not automatically shown, you can draw it yourself on the map using the "Draw My Field" tool, and the system will include it in future updates.`
  },
  {
    q: 'Does it work for crops other than wheat?',
    a: `The current version is built specifically for <strong>Rabi wheat</strong> (the winter crop). However, modules for <strong>mustard, gram (chickpea), and potato</strong> are being developed. If you grow a different crop, please contact the IIRS research team — your feedback helps prioritise the next crop to add.`
  },
  {
    q: 'Does the system consider my soil type?',
    a: `Yes. Sandy soils drain faster and hold less water, while clay soils hold more. jaldrishiti incorporates a <strong>soil type map</strong> covering the entire district so that the water recommendation is adjusted for your field's soil. It also considers shallow underground water — if water is close to the surface, the crop may not need as much irrigation.`
  },
  {
    q: 'Can jaldrishiti predict water needs for the next few days?',
    a: `Yes. The system provides a <strong>15-day forecast</strong> of irrigation water requirements. This helps farmers and canal authorities plan ahead — for example, deciding when to release water from a reservoir or schedule pump usage. The forecast is most reliable for the first 10 days and becomes an estimate beyond that.`
  },
  {
    q: 'Is jaldrishiti validated with real field data?',
    a: `Yes. The system was tested during the <strong>Rabi seasons of 2022, 2023, and 2024</strong> in the Kashipur, Jaspur, and Rudrapur blocks of Udham Singh Nagar. Soil moisture probes and actual pumping records were used to compare the system's recommendations with real field conditions. The validation confirmed the system works reliably under local conditions.`
  },
  {
    q: 'Is there a cost to use jaldrishiti?',
    a: `<strong>Completely free.</strong> jaldrishiti is a public service funded by ISRO and the Department of Space, Government of India. All maps, daily forecasts, and the chatbot are available at no charge to farmers, researchers, and government agencies. Commercial use requires a separate agreement with IIRS.`
  },
  {
    q: 'Who do I contact if I have more questions?',
    a: `You can use the <strong>AquaBot</strong> chatbot on this FAQs page for instant answers. For detailed queries, contact the <strong>Water Resources Division, IIRS, Dehradun</strong>. The research team welcomes feedback from farmers — your ground-level experience helps improve the system for everyone.`
  }
]

// ── Filtered list ─────────────────────────────────────────────────────────────
const filtered = computed(() => {
  if (!query.value.trim()) return faqs
  const q = query.value.toLowerCase()
  return faqs.filter(f =>
    f.q.toLowerCase().includes(q) || f.a.toLowerCase().includes(q)
  )
})

// ── Highlight matching keyword ────────────────────────────────────────────────
function highlight(text) {
  if (!query.value.trim()) return text
  const escaped = query.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(${escaped})`, 'gi')
  return text.replace(re, '<mark>$1</mark>')
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }

.faq-root {
  --header-bg: #1A4A6B;
  --header-text: #FFFFFF;
  --nav-bg: #009688;
  --nav-text: #FFFFFF;
  font-family: 'Inter', sans-serif;
  background: #ffffff;
  color: #1a1a2e;
  min-height: 100vh;
}

/* ── HEADER ── */
.app-header {
  position: relative;
  z-index: 201;
  background: var(--header-bg);
  border-bottom: 1px solid rgba(0,0,0,0.18);
  padding: 14px 24px;
  box-shadow: 0 3px 14px rgba(0,0,0,0.25);
}
.app-header-inner {
  max-width: 1280px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
}
.header-logos, .header-logos-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-logos-right { justify-content: flex-end; }
.iirs-logo, .gov-logo {
  height: 64px;
  width: auto;
  object-fit: contain;
  transition: transform 0.3s ease;
}
.iirs-logo:hover, .gov-logo:hover { transform: scale(1.05); }
.gov-logo { height: 60px; }
.header-center { flex: 1; text-align: center; padding: 0 8px; }
.header-center h2 {
  font-family: 'Outfit', sans-serif;
  font-size: clamp(1.1rem, 2vw, 1.5rem);
  font-weight: 800;
  color: var(--header-text);
  margin: 0 0 4px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.header-center h3 {
  font-size: clamp(1.0rem, 1.6vw, 1.15rem);
  color: var(--header-text);
  opacity: 0.9;
  font-weight: 500;
  margin: 0 0 2px;
}
.header-center h4 {
  font-size: clamp(0.8rem, 1.3vw, 0.95rem);
  color: var(--header-text);
  opacity: 0.75;
  font-weight: 400;
  margin: 0;
}

/* ── NAV ── */
.nav-bar {
  position: sticky;
  top: 0;
  z-index: 200;
  background: var(--nav-bg);
  border-bottom: 2px solid rgba(0,0,0,0.15);
  box-shadow: 0 3px 10px rgba(0,0,0,0.20);
}
.nav-inner {
  max-width: 1280px;
  height: 64px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.iirs-logo {
    width: 64px;   /* adjust as needed */
    height: 64px;  /* adjust as needed */
    object-fit: contain;
}
.nav-links { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.nav-link {
  display: inline-flex;
  align-items: center;
  position: relative;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--nav-text);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: none;
  font-family: 'Inter', sans-serif;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  transition: all 0.2s ease;
}
.nav-link::after {
  content: '';
  position: absolute;
  bottom: 4px;
  left: 50%;
  width: 0%;
  height: 2px;
  background: var(--nav-text);
  transition: all 0.3s ease;
  transform: translateX(-50%);
  border-radius: 2px;
}
.nav-link:hover, .nav-link.active { background: rgba(255,255,255,0.18); color: #ffffff; }
.nav-link:hover::after, .nav-link.active::after { width: 70%; }

/* ── HERO / SEARCH ── */
.faq-hero {
  background: linear-gradient(160deg, #f0fdf9 0%, #e6f4f1 100%);
  border-bottom: 1px solid #d1e9e4;
  text-align: center;
  padding: 60px 24px 48px;
}
.faq-hero-tag {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #0d9488;
  text-transform: uppercase;
  margin-bottom: 12px;
}
.faq-hero-title {
  font-family: 'Outfit', sans-serif;
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
  margin-bottom: 14px;
}
.faq-hero-sub {
  font-size: 1.05rem;
  color: #475569;
  line-height: 1.7;
  max-width: 560px;
  margin: 0 auto 36px;
}
.search-wrap {
  position: relative;
  max-width: 620px;
  margin: 0 auto;
}
.search-icon {
  position: absolute;
  left: 18px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1.1rem;
  pointer-events: none;
}
.search-input {
  width: 100%;
  padding: 16px 52px 16px 52px;
  border: 2px solid #cbd5e1;
  border-radius: 50px;
  font-size: 1rem;
  font-family: 'Inter', sans-serif;
  background: #ffffff;
  color: #0f172a;
  outline: none;
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.search-input:focus {
  border-color: #0d9488;
  box-shadow: 0 0 0 4px rgba(13,148,136,0.12), 0 4px 16px rgba(0,0,0,0.08);
}
.search-clear {
  position: absolute;
  right: 18px;
  top: 50%;
  transform: translateY(-50%);
  background: #e2e8f0;
  border: none;
  border-radius: 50%;
  width: 28px;
  height: 28px;
  cursor: pointer;
  font-size: 0.8rem;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}
.search-clear:hover { background: #cbd5e1; }
.no-results { margin-top: 20px; color: #64748b; font-size: 0.95rem; }
.result-count { margin-top: 16px; color: #0d9488; font-size: 0.9rem; font-weight: 500; }

/* ── FAQ LIST ── */
.faq-list-wrap {
  max-width: 820px;
  margin: 48px auto 80px;
  padding: 0 24px;
}
.faq-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  margin-bottom: 12px;
  background: #ffffff;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  transition: box-shadow 0.25s, border-color 0.25s;
}
.faq-card:hover { box-shadow: 0 4px 18px rgba(0,0,0,0.09); border-color: #b2d8d4; }
.faq-card.open { border-color: #0d9488; box-shadow: 0 4px 20px rgba(13,148,136,0.12); }
.faq-question {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  font-family: 'Inter', sans-serif;
}
.faq-q-text { font-size: 1.02rem; font-weight: 600; color: #0f172a; line-height: 1.5; flex: 1; }
.faq-card.open .faq-q-text { color: #0d9488; }
.faq-chevron { font-size: 1.4rem; font-weight: 300; color: #94a3b8; line-height: 1; flex-shrink: 0; transition: color 0.2s; }
.faq-card.open .faq-chevron { color: #0d9488; }
.faq-answer-wrap { max-height: 0; overflow: hidden; transition: max-height 0.35s ease; }
.faq-answer-wrap.visible { max-height: 600px; }
.faq-answer {
  padding: 0 24px 22px 24px;
  font-size: 0.97rem;
  line-height: 1.75;
  color: #475569;
  border-top: 1px solid #f1f5f9;
  padding-top: 18px;
}
.faq-answer code {
  display: inline-block;
  background: #f0fdf9;
  border: 1px solid #d1e9e4;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 0.9rem;
  color: #0d9488;
  font-family: 'Courier New', monospace;
  margin: 8px 0;
}
.faq-answer strong { color: #0f172a; }
:deep(mark) { background: #fef08a; color: #1a1a2e; border-radius: 3px; padding: 0 2px; }

/* ── SITE FOOTER ── */
.site-footer { background: #0f172a; border-top: 1px solid #1e293b; padding: 28px 24px; }
.footer-inner {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.fb-name { font-family: 'Outfit', sans-serif; font-size: 1rem; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }
.fb-sub { font-size: 0.82rem; color: #64748b; }

/* ── FLOATING AQUABOT BUTTON ── */
.fab-aquabot {
  position: fixed;
  bottom: 28px;
  right: 28px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 13px 20px 13px 16px;
  background: linear-gradient(135deg, #1a6bff 0%, #0052cc 100%);
  border: none;
  border-radius: 50px;
  cursor: pointer;
  box-shadow: 0 4px 20px rgba(26,107,255,0.45);
  color: #fff;
  font-family: 'Inter', sans-serif;
  font-size: 0.88rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  transition: transform 0.2s, box-shadow 0.2s;
}
.fab-aquabot:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(26,107,255,0.55);
}
.fab-aquabot:active { transform: translateY(0); }
.fab-label { white-space: nowrap; }

/* ── SLIDING CHAT PANEL ── */
.fab-chat-panel {
  position: fixed;
  bottom: 88px;
  right: 28px;
  z-index: 999;
  width: 420px;
  height: 580px;
  display: flex;
  flex-direction: column;
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 16px 56px rgba(0,0,0,0.18);
  background: #f4f7fb;
}
.fab-chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 16px;
  background: linear-gradient(135deg, #1a6bff 0%, #0052cc 100%);
  color: #fff;
  font-size: 0.88rem;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  flex-shrink: 0;
}
.fab-chat-header-left {
  display: flex;
  align-items: center;
  gap: 9px;
}
.fab-close-btn {
  background: rgba(255,255,255,0.18);
  border: none;
  border-radius: 6px;
  color: #fff;
  width: 28px;
  height: 28px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
  flex-shrink: 0;
}
.fab-close-btn:hover { background: rgba(255,255,255,0.32); }
.fab-chat-body { flex: 1; overflow: hidden; }

/* ── SLIDE-UP TRANSITION ── */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: opacity 0.25s ease, transform 0.28s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.97);
}

/* ── RESPONSIVE ── */
@media (max-width: 640px) {
  .app-header-inner { grid-template-columns: 1fr; text-align: center; }
  .header-logos, .header-logos-right { justify-content: center; }
  .faq-hero { padding: 40px 16px 32px; }
  .faq-list-wrap { padding: 0 12px; }
  .faq-question { padding: 16px; }
  .faq-answer { padding: 14px 16px 18px; }
  .nav-link { padding: 8px 12px; font-size: 0.82rem; }
  .fab-chat-panel {
    width: calc(100vw - 16px);
    right: 8px;
    bottom: 80px;
    height: 72vh;
    border-radius: 14px;
  }
  .fab-aquabot {
    right: 16px;
    bottom: 16px;
    padding: 12px 16px 12px 14px;
  }
}
</style>