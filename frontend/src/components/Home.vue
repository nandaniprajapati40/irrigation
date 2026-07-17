<template>
  <div class="home-root" :class="{ dark: isDark }">

    <!-- ══════════════════ ANIMATED BG ══════════════════ -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <div class="field-grid"></div>
      <div class="grid-overlay"></div>
      <div v-for="p in particles" :key="p.id" class="particle"
        :style="`left:${p.x}%;top:${p.y}%;animation-delay:${p.delay}s;animation-duration:${p.dur}s;width:${p.size}px;height:${p.size}px;opacity:${p.op}`">
      </div>
      <div class="orbit-ring orbit-ring-1"><div class="orbit-dot"></div></div>
      <div class="orbit-ring orbit-ring-2"><div class="orbit-dot dot-alt"></div></div>
      <div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>
    </div>

    <!-- ══════════════════ HEADER ══════════════════ -->
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
    <!-- ══════════════════ NAV ══════════════════ -->
    <nav class="nav-bar">
      <div class="nav-inner">
        
        <div class="nav-links">
          <a href="#about"  class="nav-link" @click.prevent="scrollTo('about')">About</a>
          <a href="#region" class="nav-link" @click.prevent="scrollTo('region')">Study Region</a>
          <a href="#docs"   class="nav-link" @click.prevent="$emit('docs')">Docs</a>
          <a href="#faqs"   class="nav-link" @click.prevent="$emit('faqs')">FAQs</a>
        </div>
        <button class="mobile-menu-btn" @click="mobileOpen = !mobileOpen">
          <span></span><span></span><span></span>
        </button>
      </div>
      <div class="mobile-dropdown" :class="{ open: mobileOpen }">
        <a href="#about"  class="mobile-link" @click.prevent="scrollTo('about');  mobileOpen=false">About</a>
        <a href="#why"    class="mobile-link" @click.prevent="scrollTo('why');    mobileOpen=false">Why AquaWatch</a>
        <a href="#region" class="mobile-link" @click.prevent="scrollTo('region'); mobileOpen=false">Study Region</a>
        <a class="mobile-link" @click.prevent="$emit('docs'); mobileOpen=false" style="cursor:pointer">DOCs</a>
        <button @click="$emit('launch'); mobileOpen=false" class="mobile-launch">🛰️ Launch Dashboard</button>
        <button @click="$emit('toggle-theme')" class="mobile-theme">{{ isDark ? '☀️ Light Mode' : '🌙 Dark Mode' }}</button>
      </div>
    </nav>

    <!-- ══════════════════ LIVE STATUS STRIP ══════════════════ -->
    <div class="status-strip">
      <div class="status-strip-inner">
        <span class="ss-live"><span class="ss-dot"></span>LIVE</span>
      </div>
    </div>

    <!-- ══════════════════ HERO ══════════════════ -->
    <section class="hero-section" id="about">
      <!-- Hero Background Image -->
      <div class="hero-bg-image">
        <img src="/assets/BG.png" alt="Background" class="hero-bg-img" />
        <div class="hero-bg-overlay"></div>
      </div>
      <div class="hero-inner">
        <div class="hero-badge fade-up">
          <span class="badge-dot"></span>
          Rabi Season Active · Udham Singh Nagar, Uttarakhand
        </div>
        <h1 class="hero-title fade-up" style="animation-delay:.2s">
          JAL<span class="title-accent">DRISHTI</span>
          <span class="title-sub">Crop Irrigation water requirements</span>
        </h1>
        <p class="hero-desc fade-up" style="animation-delay:.35s">
          <strong>Rabi wheat crop </strong>
        </p>
        <div class="hero-cta-row fade-up" style="animation-delay:.5s">
          <button @click="$emit('launch')" class="ss-cta">Open Map →</button>
        </div>
      </div>
    </section>

   

    <!-- ══════════════════ STUDY REGION ══════════════════ -->
    <section class="region-section" id="region">
      <div class="region-shell">
        <div class="region-header">
          <span class="section-tag">Study Region</span>
          <h2 class="section-title">Futuristic GIS Irrigation Intelligence</h2>
          <p class="section-subtitle">
            Udham Singh Nagar Rabi wheat fields monitored through satellite layers, ET tower telemetry, rainfall signals and crop water demand analytics.
          </p>
        </div>

        <div class="region-main-grid">
          <article class="region-visual-card">
            <img src="/assets/towercrop.jpg" alt="Agriculture monitoring tower in wheat field" class="region-feature-img" />
            <div class="region-image-shade"></div>
            <div class="region-scanline"></div>
            <div class="region-visual-content">
              <div class="region-kicker">
                <span class="region-live-dot"></span>
                Field Network Online
              </div>
              <h3>Udham Singh Nagar, Uttarakhand</h3>
              <div class="region-metrics">
                <div>
                  <strong>Rabi</strong>
                  <span>Wheat season</span>
                </div>
                <div>
                  <strong>ET</strong>
                  <span>Tower calibration</span>
                </div>
                <div>
                  <strong>GIS</strong>
                  <span>Spatial monitoring</span>
                </div>
              </div>
            </div>
          </article>

          <div class="region-card-grid">
            <article v-for="card in studyCards" :key="card.title" class="region-tech-card">
              <div class="rtc-top">
                <span class="rtc-icon">{{ card.icon }}</span>
                <span class="rtc-signal">{{ card.signal }}</span>
              </div>
              <h3>{{ card.title }}</h3>
              <p>{{ card.text }}</p>
            </article>
          </div>
        </div>
      </div>
    </section>

    <!-- ══════════════════ OVERVIEW STATS ══════════════════ -->
    <section class="stats-section">
      <div class="overview-grid">
        <div v-for="stat in overviewStats" :key="stat.label" class="stat-card">
          <span class="stat-icon">{{ stat.icon }}</span>
          <span class="stat-value">{{ stat.value }}</span>
          <span class="stat-label">{{ stat.label }}</span>
        </div>
      </div>
    </section>

    <!-- ══════════════════ FOOTER ══════════════════ -->
    <footer class="site-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <span></span>
          <div>
            <p class="fb-name">&nbsp;·&nbsp; Irrigation Water Requirements</p>
            <p class="fb-sub">ISRO &nbsp;·&nbsp; IIRS &nbsp;·&nbsp; Department of Space, Govt. of India</p>
          </div>
        </div>
        <div class="footer-tech">
          <span v-for="t in footerTech" :key="t.name" class="ft-badge" :title="t.role">
            {{ t.icon }} {{ t.name }}
          </span>
        </div>
        <div class="footer-links-col">
          <p class="fc">Udham Singh Nagar · Uttarakhand · Rabi Wheat</p>
        </div>
      </div>
    </footer>


  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  isDark: { type: Boolean, default: true }
})
defineEmits(['launch', 'docs', 'faqs', 'toggle-theme'])
const mobileOpen = ref(false)

function scrollTo(id) {
  const el = document.getElementById(id)
  if (!el) return
  window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 140, behavior: 'smooth' })
}

const particles = Array.from({ length: 18 }, (_, i) => ({
  id: i, x: Math.random() * 100, y: Math.random() * 100,
  delay: Math.random() * 10, dur: 8 + Math.random() * 10,
  size: 2 + Math.random() * 4, op: 0.08 + Math.random() * 0.22,
}))

const studyCards = [
  {
    icon: 'SR',
    signal: 'Terai GIS',
    title: 'Study Region',
    text: 'Canal-fed wheat belt with field boundaries, terrain context and seasonal crop masks.'
  },
  {
    icon: 'CM',
    signal: 'NDVI / LAI',
    title: 'Crop Monitoring',
    text: 'Growth stage intelligence from vegetation indices and in-season field observations.'
  },
  {
    icon: 'ET',
    signal: 'Flux Tower',
    title: 'ET Tower Data',
    text: 'Ground evapotranspiration measurements for calibration of crop water requirement maps.'
  },
  {
    icon: 'SO',
    signal: 'Satellite Stack',
    title: 'Satellite Observation',
    text: 'Multi-date remote sensing layers aligned with irrigation demand and crop vigor.'
  },
  {
    icon: 'RA',
    signal: 'Rainfall Grid',
    title: 'Rainfall Analysis',
    text: 'Rainfall variability tracked against field water stress and irrigation windows.'
  },
  {
    icon: 'WO',
    signal: 'Decision Layer',
    title: 'Water Optimization',
    text: 'Spatial recommendations to reduce waste while keeping wheat productivity stable.'
  }
]
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&family=Noto+Sans+Devanagari:wght@500;700&display=swap');

/* ──────────────────────────────────────────────────────────────────────
   THEME SYSTEM
   ────────────────────────────────────────────────────────────────────── */
.home-root {
  /* DARK THEME - Professional Slate & Deep Indigo (Modernized) */
  --bg-primary: #040814;
  --bg-secondary: #0A1128;
  --bg-tertiary: #131E3A;
  --surface: rgba(19, 30, 58, 0.4);
  --surface-hover: rgba(19, 30, 58, 0.65);
  --border: rgba(0, 212, 168, 0.15);
  --border-light: rgba(255,255,255,0.04);
  
  --text-primary: #F8FAFC;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  
  --accent-teal: #00D4A8;
  --accent-teal-glow: rgba(0, 212, 168, 0.15);
  --accent-amber: #FDE047;
  --accent-blue: #3B82F6;
  
  --card-bg: rgba(30, 41, 59, 0.5);
  
  --header-bg: #1A4A6B;
  --header-text: #FFFFFF;
  --nav-bg: #009688;
  --nav-text: #FFFFFF;
  --hero-overlay: linear-gradient(135deg, rgba(10,15,28,0.88) 0%, rgba(10,15,28,0.7) 50%, rgba(10,15,28,0.85) 100%);

  font-family: 'Inter', sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: background 0.4s ease, color 0.4s ease;
  overflow-x: hidden;
  overflow-y: auto;
  min-height: 100vh;
}

/* ── LIGHT THEME OVERRIDES ── */
.home-root:not(.dark) {
  /* LIGHT THEME - Clean, vibrant, incredibly readable */
  --bg-primary: #F8FAFC;
  --bg-secondary: #F1F5F9;
  --bg-tertiary: #E2E8F0;
  --surface: #FFFFFF;
  --surface-hover: #F8FAFC;
  --border: rgba(0, 0, 0, 0.08);
  --border-light: rgba(0, 0, 0, 0.05);
  
  --text-primary: #0F172A;
  --text-secondary: #334155;
  --text-muted: #64748B;
  
  --accent-teal: #0D9488;
  --accent-teal-glow: rgba(13, 148, 136, 0.18);
  --accent-amber: #D97706;
  --accent-blue: #2563EB;
  
  --card-bg: rgba(255, 255, 255, 0.85);
  
  --header-bg: #F8FAFC;
  --header-text: #0F172A;
  --nav-bg: #FFFFFF;
  --nav-text: #0D9488;
  --hero-overlay: linear-gradient(135deg, rgba(248,250,252,0.7) 0%, rgba(248,250,252,0.4) 50%, rgba(248,250,252,0.6) 100%);
}

h1, h2, h3, h4, h5, h6 { font-family: 'Outfit', sans-serif; }

/* ──────────────────────────────────────────────────────────────────────
   ANIMATED BACKGROUND
   ────────────────────────────────────────────────────────────────────── */
.field-grid {
  position: absolute; inset: -50% -50% -50% -50%;
  background-image:
    linear-gradient(var(--accent-teal-glow) 1px, transparent 1px),
    linear-gradient(90deg, var(--accent-teal-glow) 1px, transparent 1px);
  background-size: 60px 60px;
  opacity: 0.25;
  transform: perspective(600px) rotateX(60deg) translateY(-100px) translateZ(-200px);
  animation: gridMove 20s linear infinite;
  mask-image: radial-gradient(circle at center, black 10%, transparent 80%);
  -webkit-mask-image: radial-gradient(circle at center, black 10%, transparent 80%);
}
@keyframes gridMove {
  from { transform: perspective(600px) rotateX(60deg) translateY(0) translateZ(-200px); }
  to { transform: perspective(600px) rotateX(60deg) translateY(60px) translateZ(-200px); }
}
.grid-overlay {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at top, transparent 20%, var(--bg-primary) 80%);
}
.home-root:not(.dark) .field-grid { opacity: 0.4; }

.particle {
  position: absolute;
  background: var(--accent-teal);
  border-radius: 50%;
  animation: floatUp linear infinite;
  filter: blur(0.5px);
}
@keyframes floatUp {
  0%   { transform: translateY(0) scale(1); opacity: inherit; }
  50%  { opacity: 0.3; }
  100% { transform: translateY(-80vh) scale(0.3); opacity: 0; }
}
.orbit-ring {
  position: absolute; top: 50%; left: 50%; border-radius: 50%;
  border: 1px dashed rgba(0,212,168,0.15);
}
.orbit-ring-1 {
  width: 600px; height: 600px; margin: -300px;
  animation: orbit 45s linear infinite;
}
.orbit-ring-2 {
  width: 800px; height: 800px; margin: -400px;
  border: 1px dashed rgba(59,130,246,0.15);
  animation: orbit 60s linear infinite reverse;
}
.home-root:not(.dark) .orbit-ring { border-color: rgba(13,148,136,0.25); }
.orbit-dot {
  position: absolute; top: -5px; left: 50%; margin-left: -5px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--accent-teal);
  box-shadow: 0 0 14px var(--accent-teal);
}
.orbit-dot.dot-alt { background: var(--accent-blue); box-shadow: 0 0 14px var(--accent-blue); box-shadow: 0 0 18px rgba(59, 130, 246, 0.8); }
@keyframes orbit { to { transform: rotate(360deg); } }

@keyframes headerReveal {
  from { opacity: 0; transform: translateY(-12px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes navReveal {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.glow {
  position: absolute; border-radius: 50%;
  filter: blur(100px); pointer-events: none;
}
.g1 { width:600px;height:600px;background:var(--accent-teal-glow);top:-200px;left:-200px; }
.g2 { width:450px;height:450px;background:rgba(59,130,246,0.06);bottom:-100px;right:-100px; }
.g3 { width:350px;height:350px;background:rgba(253,224,71,0.05);top:45%;left:35%; }

/* ──────────────────────────────────────────────────────────────────────
   HEADER
   ────────────────────────────────────────────────────────────────────── */
.app-header {
  position: relative;
  z-index: 201;
  background: var(--header-bg);
  border-bottom: 1px solid rgba(0, 0, 0, 0.18);
  padding: 14px 24px;
  box-shadow: 0 3px 14px rgba(0, 0, 0, 0.25);
  transition: background 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease;
  animation: headerReveal 0.55s cubic-bezier(0.16, 1, 0.3, 1) both;
}
.app-header-inner {
  max-width: 1280px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
}
.home-root:not(.dark) .app-header {
  background: var(--header-bg);
  box-shadow: 0 3px 14px rgba(0, 0, 0, 0.22);
}


.header-logos, .header-logos-right { display: flex; align-items: center; gap: 16px; }
.header-logos-right { justify-content: flex-end; }

.iirs-logo, .gov-logo {
  height: 64px; width: auto; object-fit: contain;
  transition: transform 0.3s ease, filter 0.3s ease;
}
.iirs-logo:hover, .gov-logo:hover { transform: scale(1.05); }

.home-root:not(.dark) .iirs-logo,
.home-root:not(.dark) .gov-logo {
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.08));
}
.gov-logo { height: 60px; }

.header-center { flex: 1; text-align: center; padding: 0 8px; }
.header-center h2 {
  font-family: 'Noto Sans Devanagari', 'Outfit', sans-serif;
  font-size: clamp(1.1rem, 2vw, 1.5rem);
  font-weight: 800;
  line-height: 1.22;
  letter-spacing: 0;
  color: var(--header-text);
  margin: 0 0 4px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.header-center h3 {
  font-family: 'Inter', sans-serif;
  font-size: clamp(1.0rem, 1.6vw, 1.15rem);
  color: var(--header-text);
  opacity: 0.9;
  font-weight: 500;
  line-height: 1.25;
  letter-spacing: 0;
  margin: 0 0 2px;
}
.header-center h4 {
  font-family: 'Inter', sans-serif;
  font-size: clamp(0.8rem, 1.3vw, 0.95rem);
  color: var(--header-text);
  opacity: 0.75;
  font-weight: 400;
  line-height: 1.25;
  letter-spacing: 0;
  margin: 0;
}

/* ──────────────────────────────────────────────────────────────────────
   NAVIGATION
   ────────────────────────────────────────────────────────────────────── */
.nav-bar {
  position: sticky; top: 0; z-index: 200;
  background: var(--nav-bg);
  border-bottom: 2px solid rgba(0, 0, 0, 0.15);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.20);
  transition: background 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease;
  animation: navReveal 0.5s 0.08s cubic-bezier(0.16, 1, 0.3, 1) both;
}
.home-root:not(.dark) .nav-bar {
  background: var(--nav-bg);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.18);
}

.nav-inner {
  max-width: 1280px; margin: 0 auto; padding: 0 24px;
  height: 64px; display: flex; align-items: center;
  justify-content: center; gap: 16px;
}

.nav-links { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.nav-link {
  font-size: 0.9rem; color: var(--nav-text);
  text-decoration: none; padding: 8px 20px; border-radius: 6px;
  transition: all 0.2s ease; font-weight: 600;
  letter-spacing: 0.04em; text-transform: uppercase;
}
.nav-link { position: relative; }
.nav-link::after {
  content: ''; position: absolute; bottom: 4px; left: 50%;
  width: 0%; height: 2px; background: var(--nav-text);
  transition: all 0.3s ease; transform: translateX(-50%); border-radius: 2px;
}
.nav-link:hover { color: #FFFFFF; background: rgba(255,255,255,0.18); }
.nav-link:hover::after { width: 70%; }

.btn-launch {
  padding: 10px 24px; margin-left: 8px; border-radius: 50px;
  background: var(--accent-teal); color: #FFFFFF;
  font-family: 'Outfit', sans-serif;
  font-weight: 600; font-size: 0.9rem; border: none; cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 14px var(--accent-teal-glow);
  display: inline-flex; align-items: center;
}
.btn-launch:hover { 
  transform: translateY(-2px); 
  box-shadow: 0 6px 20px rgba(0,212,168,0.3);
  background: #05EBB8;
}

.btn-theme {
  width: 40px; height: 40px; border-radius: 50%; margin-left: 8px;
  background: var(--surface); border: 1px solid var(--border);
  cursor: pointer; font-size: 1.1rem; color: var(--text-primary); 
  display: flex; align-items: center; justify-content: center;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.btn-theme:hover { 
  border-color: var(--accent-teal); 
  transform: scale(1.08) rotate(5deg); 
  color: var(--accent-teal);
}

.mobile-menu-btn {
  display: none; flex-direction: column; gap: 6px;
  background: none; border: none; cursor: pointer; padding: 6px; margin-left: auto;
}
.mobile-menu-btn span {
  display: block; width: 24px; height: 2px;
  background: var(--text-primary); border-radius: 2px; transition: 0.3s;
}
.mobile-dropdown {
  max-height: 0; overflow: hidden; transition: max-height 0.4s ease;
  display: flex; flex-direction: column; padding: 0 24px;
  border-top: 1px solid transparent; background: var(--surface);
}
.mobile-dropdown.open { max-height: 400px; padding: 16px 24px; border-top-color: var(--border); }
.mobile-link {
  padding: 12px 0; font-size: 1rem; color: var(--text-primary);
  text-decoration: none; border-bottom: 1px solid var(--border-light);
  font-weight: 500;
}
.mobile-launch {
  margin-top: 12px; padding: 14px; border-radius: 12px;
  background: var(--accent-teal); color: #ffffff;
  font-family: 'Outfit', sans-serif;
  font-weight: 600; border: none; cursor: pointer; font-size: 1rem;
}
.mobile-theme {
  margin-top: 10px; padding: 12px; border-radius: 12px;
  border: 1px solid var(--border); background: var(--bg-tertiary);
  color: var(--text-primary); cursor: pointer; font-size: 0.95rem; font-weight: 500;
}

/* ──────────────────────────────────────────────────────────────────────
   LIVE STATUS STRIP
   ────────────────────────────────────────────────────────────────────── */
.status-strip {
  position: relative; z-index: 100;
  background: var(--accent-teal-glow);
  box-shadow: inset 0 -1px 0 var(--border-light);
  padding: 10px 24px;
}
.status-strip-inner {
  max-width: 1200px; margin: 0 auto;
  display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
}
.ss-live {
  display: flex; align-items: center; gap: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem; color: var(--accent-teal);
  font-weight: 700; letter-spacing: 0.1em; flex-shrink: 0;
  text-transform: uppercase;
}
.ss-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent-teal); animation: pulse 2s infinite; flex-shrink: 0;
  box-shadow: 0 0 10px var(--accent-teal);
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.5; transform: scale(1.4); }
}
.ss-cta {
  padding: 14px 32px;          
  border-radius: 40px;         
  background: var(--surface);
  border: 1px solid var(--border);

  font-size: 1rem;             
  font-weight: 700;
  letter-spacing: 0.04em;

  color: var(--text-primary);
  cursor: pointer;

  transition: all 0.25s ease;
}
.ss-cta:hover { border-color: var(--accent-teal); color: var(--accent-teal); box-shadow: 0 2px 8px var(--accent-teal-glow); }
.ss-cta:hover { transform: translateY(-2px); }
.ss-cta:active { transform: translateY(0); }

/* ──────────────────────────────────────────────────────────────────────
   HERO SECTION
   ────────────────────────────────────────────────────────────────────── */
.hero-section {
  position: relative; z-index: 1;
  min-height: calc(100vh - 180px);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 80px 24px 100px; text-align: center;
  overflow: hidden;
}

.hero-bg-image { position: absolute; inset: 0; z-index: 0; }
.hero-bg-img {
  width: 100%; height: 100%;
  object-fit: cover; object-position: center; display: block;
}
.hero-bg-overlay {
  position: absolute; inset: 0;
  /* Dark overlay ensures text is highly readable */
    background: var(--hero-overlay);
    transition: background 0.4s ease;
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
}

.hero-inner { position: relative; z-index: 2; max-width: 900px; margin: 0 auto; }
.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 20px; border-radius: 50px;
  border: 1px solid rgba(0, 212, 168, 0.3);
  background: rgba(10, 15, 28, 0.4);
  color: var(--accent-teal); 
  font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 24px;
  backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,0.05); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,0.05);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
.home-root:not(.dark) .hero-badge {
  background: rgba(255, 255, 255, 0.8);
  border-color: rgba(13, 148, 136, 0.3);
  color: var(--accent-teal);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}
.badge-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent-teal); animation: pulse 2s infinite; flex-shrink: 0;
}

.hero-title {
  font-family: 'Outfit', sans-serif; font-weight: 800;
  line-height: 1.05; margin-bottom: 24px;
  font-size: clamp(3rem, 8vw, 5.5rem);
  color: #FFFFFF;
  text-shadow: 0 4px 24px rgba(0,0,0,0.5), 0 0 60px rgba(0,212,168,0.25);
}
.home-root:not(.dark) .hero-title {
  color: #0F172A;
  text-shadow: 0 4px 20px rgba(255,255,255,0.8), 0 0 40px rgba(13,148,136,0.1);
}

.title-accent {
  background: linear-gradient(135deg, var(--accent-teal), #00F0FF);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 2px 8px rgba(0,212,168,0.3));
}
.home-root:not(.dark) .title-accent {
  background: linear-gradient(135deg, var(--accent-teal), #0284C7);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: none;
}

.title-sub {
  display: block; font-size: clamp(1rem, 2.5vw, 1.5rem);
  font-weight: 600; color: var(--accent-amber);
  letter-spacing: 0.15em; text-transform: uppercase; margin-top: 14px;
  text-shadow: 0 2px 10px rgba(0,0,0,0.5);
  font-family: 'Inter', sans-serif;
}
.home-root:not(.dark) .title-sub {
  color: #D97706; text-shadow: 0 1px 2px rgba(255,255,255,0.8);
}

.hero-desc {
  font-size: clamp(1rem, 1.8vw, 1.15rem);
  color: rgba(248,250,252,0.9);
  line-height: 1.8; max-width: 700px; margin: 0 auto 40px;
  text-shadow: 0 2px 8px rgba(0,0,0,0.5); font-weight: 400;
}
.home-root:not(.dark) .hero-desc {
  color: #0F172A; font-weight: 500;
  text-shadow: 0 1px 2px rgba(255,255,255,0.8);
}
.hero-desc strong { color: var(--accent-teal); font-weight: 700; }

.hero-cta-row { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
.btn-hero-secondary {
  padding: 14px 32px; border-radius: 50px;
  background: rgba(30, 41, 59, 0.4);
  color: #FFFFFF;
  font-weight: 600; font-size: 1rem;
  border: 1px solid rgba(255,255,255,0.2);
  cursor: pointer; transition: all 0.3s ease;
  backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,0.05); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,0.05);
  box-shadow: 0 8px 24px rgba(0,0,0,0.2);
}
.btn-hero-secondary:hover {
  background: rgba(255,255,255,0.1);
  border-color: var(--accent-teal);
  transform: translateY(-2px);
}
.home-root:not(.dark) .btn-hero-secondary {
  background: rgba(255,255,255,0.9);
  color: var(--text-primary);
  border: 1px solid rgba(0,0,0,0.1);
  box-shadow: 0 8px 20px rgba(0,0,0,0.05);
}
.home-root:not(.dark) .btn-hero-secondary:hover {
  background: #FFFFFF; border-color: var(--accent-teal);
  color: var(--accent-teal);
}

.fade-up { animation: fadeUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) both; }
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(30px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes cardRise {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ──────────────────────────────────────────────────────────────────────
   SHARED SECTION STYLES
   ────────────────────────────────────────────────────────────────────── */
.section-inner { max-width: 1200px; margin: 0 auto; padding: 0 24px; }
.section-header { text-align: center; margin-bottom: 60px; }
.section-tag {
  display: inline-block;
  padding: 6px 16px; border-radius: 50px;
  background: var(--accent-teal-glow);
  border: 1px solid rgba(0,212,168,0.2);
  color: var(--accent-teal);
  font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; font-weight: 600;
  letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 20px;
}
.section-title {
  font-family: 'Outfit', sans-serif; font-weight: 800;
  font-size: clamp(2rem, 4.5vw, 3rem);
  color: var(--text-primary); margin: 0 0 20px; line-height: 1.15;
  text-align: center;
}
.section-subtitle {
  font-size: clamp(1rem, 1.5vw, 1.1rem);
  color: var(--text-secondary); line-height: 1.8;
  max-width: 680px; margin: 0 auto; font-weight: 400;
}

/* ──────────────────────────────────────────────────────────────────────
   CONTENT SECTIONS
   ────────────────────────────────────────────────────────────────────── */
.content-section { position: relative; z-index: 1; padding: 100px 24px; }
.content-section:nth-child(even) { background: var(--bg-secondary); border-top: 1px solid var(--border-light); border-bottom: 1px solid var(--border-light); }


/* ──────────────────────────────────────────────────────────────────────
   STUDY REGION
   ────────────────────────────────────────────────────────────────────── */
.region-section {
  position: relative;
  z-index: 1;
  padding: 96px 24px;
  background:
    radial-gradient(circle at 12% 12%, rgba(0, 212, 168, 0.16), transparent 28%),
    radial-gradient(circle at 88% 18%, rgba(59, 130, 246, 0.15), transparent 30%),
    linear-gradient(135deg, #030711 0%, #071323 46%, #071d1c 100%);
  overflow: hidden;
  border-top: 1px solid rgba(0, 212, 168, 0.12);
  border-bottom: 1px solid rgba(0, 212, 168, 0.12);
}
.region-section::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 212, 168, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 212, 168, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: linear-gradient(to bottom, transparent, black 18%, black 78%, transparent);
  -webkit-mask-image: linear-gradient(to bottom, transparent, black 18%, black 78%, transparent);
  pointer-events: none;
}
.region-shell {
  position: relative;
  z-index: 2;
  max-width: 1220px;
  margin: 0 auto;
}
.region-header {
  max-width: 760px;
  margin: 0 auto 44px;
  text-align: center;
}
.region-header .section-tag {
  background: rgba(0, 212, 168, 0.1);
  border-color: rgba(0, 212, 168, 0.28);
  color: #70ffe3;
}
.region-header .section-title {
  color: #f8fafc;
  margin-bottom: 14px;
}
.region-header .section-subtitle {
  color: #a8b8c9;
  max-width: 720px;
}
.region-main-grid {
  display: grid;
  grid-template-columns: minmax(360px, 1.08fr) minmax(420px, 0.92fr);
  gap: 28px;
  align-items: stretch;
}
.region-visual-card {
  position: relative;
  min-height: 620px;
  border-radius: 28px;
  overflow: hidden;
  border: 1px solid rgba(112, 255, 227, 0.24);
  background: rgba(8, 18, 33, 0.72);
  box-shadow: 0 26px 70px rgba(0, 0, 0, 0.42), inset 0 1px 0 rgba(255,255,255,0.08);
}
.region-feature-img {
  width: 100%;
  height: 100%;
  min-height: inherit;
  object-fit: cover;
  object-position: center;
  display: block;
  filter: saturate(1.06) contrast(1.03);
  transition: transform 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}
.region-visual-card:hover .region-feature-img { transform: scale(1.035); }
.region-image-shade {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(3, 7, 17, 0.02) 0%, rgba(3, 7, 17, 0.46) 55%, rgba(3, 7, 17, 0.94) 100%),
    linear-gradient(90deg, rgba(0, 212, 168, 0.18), transparent 48%);
}
.region-scanline {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 0%, rgba(112, 255, 227, 0.13) 50%, transparent 100%);
  height: 34%;
  animation: regionScan 5.5s ease-in-out infinite;
  opacity: 0.55;
}
@keyframes regionScan {
  0%, 100% { transform: translateY(-85%); }
  50% { transform: translateY(250%); }
}
.region-visual-content {
  position: absolute;
  left: 28px;
  right: 28px;
  bottom: 28px;
}
.region-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(3, 7, 17, 0.56);
  border: 1px solid rgba(112, 255, 227, 0.22);
  color: #70ffe3;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}
.region-live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #00d4a8;
  box-shadow: 0 0 16px rgba(0, 212, 168, 0.9);
}
.region-visual-content h3 {
  max-width: 520px;
  margin: 18px 0 20px;
  color: #ffffff;
  font-size: clamp(1.9rem, 4vw, 3.4rem);
  line-height: 1;
  font-weight: 800;
  text-shadow: 0 14px 34px rgba(0, 0, 0, 0.55);
}
.region-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.region-metrics div {
  min-width: 0;
  padding: 14px;
  border-radius: 16px;
  background: rgba(5, 13, 26, 0.66);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}
.region-metrics strong {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  color: #70ffe3;
  font-size: 1.05rem;
  margin-bottom: 4px;
}
.region-metrics span {
  display: block;
  color: #c7d2de;
  font-size: 0.72rem;
  line-height: 1.35;
}
.region-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.region-tech-card {
  position: relative;
  min-height: 190px;
  padding: 22px;
  border-radius: 20px;
  overflow: hidden;
  background: linear-gradient(145deg, rgba(15, 29, 49, 0.78), rgba(8, 18, 33, 0.52));
  border: 1px solid rgba(148, 163, 184, 0.14);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 18px 40px rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease, background 0.25s ease;
  animation: cardRise 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
}
.region-tech-card:nth-child(2) { animation-delay: 0.06s; }
.region-tech-card:nth-child(3) { animation-delay: 0.12s; }
.region-tech-card:nth-child(4) { animation-delay: 0.18s; }
.region-tech-card:nth-child(5) { animation-delay: 0.24s; }
.region-tech-card:nth-child(6) { animation-delay: 0.30s; }
.region-tech-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 18% 18%, rgba(0, 212, 168, 0.13), transparent 36%);
  opacity: 0;
  transition: opacity 0.25s ease;
}
.region-tech-card:hover {
  transform: translateY(-6px);
  border-color: rgba(112, 255, 227, 0.42);
  background: linear-gradient(145deg, rgba(19, 39, 64, 0.88), rgba(8, 27, 42, 0.68));
  box-shadow: 0 24px 54px rgba(0, 0, 0, 0.32), 0 0 28px rgba(0, 212, 168, 0.12);
}
.region-tech-card:hover::before { opacity: 1; }
.rtc-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 26px;
}
.rtc-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 212, 168, 0.1);
  border: 1px solid rgba(0, 212, 168, 0.22);
  color: #70ffe3;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 0.86rem;
  letter-spacing: 0.04em;
}
.rtc-signal {
  color: #8aa0b5;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.region-tech-card h3 {
  position: relative;
  z-index: 1;
  color: #f8fafc;
  font-size: 1.15rem;
  font-weight: 800;
  margin: 0 0 10px;
}
.region-tech-card p {
  position: relative;
  z-index: 1;
  color: #98aabe;
  font-size: 0.9rem;
  line-height: 1.6;
  margin: 0;
}
@media (max-width: 1100px) {
  .region-main-grid {
    grid-template-columns: 1fr;
  }
  .region-visual-card {
    min-height: 500px;
  }
}
@media (max-width: 768px) {
  .region-section {
    padding: 72px 16px;
  }
  .region-header {
    margin-bottom: 30px;
  }
  .region-card-grid {
    grid-template-columns: 1fr;
  }
  .region-visual-card {
    min-height: 440px;
    border-radius: 22px;
  }
  .region-visual-content {
    left: 18px;
    right: 18px;
    bottom: 18px;
  }
  .region-metrics {
    grid-template-columns: 1fr;
  }
  .region-tech-card {
    min-height: auto;
  }
}
@media (max-width: 480px) {
  .region-visual-card {
    min-height: 380px;
  }
  .rtc-top {
    margin-bottom: 20px;
  }
}

/* ──────────────────────────────────────────────────────────────────────
   OVERVIEW STATS
   ────────────────────────────────────────────────────────────────────── */
.stats-section {
  position: relative; z-index: 1; background: var(--surface);
  border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
}
.overview-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0; }
.stat-card { cursor: default;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; padding: 32px 16px; border-right: 1px solid var(--border);
  text-align: center; transition: transform 0.25s ease, background 0.3s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}
.stat-card:last-child { border-right: none; }
.stat-card:hover { background: var(--surface-hover); transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); border-color: rgba(0,212,168,0.2) !important; border-radius: 12px; z-index: 10; position: relative; }
.stat-icon  { font-size: 1.8rem; margin-bottom: 4px; }
.stat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: clamp(1.4rem, 2.5vw, 1.8rem); font-weight: 800; color: var(--accent-teal); text-shadow: 0 0 15px rgba(0, 212, 168, 0.4);
}
.stat-label { font-size: 0.75rem; color: var(--text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; line-height: 1.4; }

/* ──────────────────────────────────────────────────────────────────────
   FOOTER
   ────────────────────────────────────────────────────────────────────── */
.site-footer {
  position: relative; z-index: 1; 
  background: #070808; /* Slate 950 - deeper, more premium dark */
  border-top: 1px solid var(--border); padding: 10px 24px 40px;
}
.home-root:not(.dark) .site-footer {
  background: #0b1827; /* Slate 100 - clean, distinct light gray */
}
.footer-inner {
  max-width: 1100px; margin: 0 auto; display: flex; flex-wrap: wrap;
  align-items: flex-start; justify-content: space-between; gap: 32px;
}
.footer-brand { display: flex; align-items: center; gap: 16px; font-size: 1.8rem; }
.fb-name { font-weight: 700; font-family: 'Outfit', sans-serif; font-size: 1.25rem; color: var(--text-primary); margin: 0 0 6px; letter-spacing: 0.05em; }
.fb-sub  { font-size: 0.8rem; color: var(--text-muted); margin: 0; }
.footer-tech { display: flex; flex-wrap: wrap; gap: 8px; max-width: 460px; }
.ft-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 50px;
  border: 1px solid var(--border); background: var(--surface);
  font-size: 0.75rem; color: var(--text-secondary); white-space: nowrap; transition: all 0.2s ease;
}
.ft-badge:hover { border-color: var(--accent-teal); color: var(--accent-teal); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(82, 165, 224, 0.05); }
.footer-links-col { display: flex; flex-direction: column; gap: 8px; align-items: flex-end; }
.fc { font-size: 0.75rem; color: var(--text-muted); margin: 0; font-family: 'JetBrains Mono', monospace; }

/* ──────────────────────────────────────────────────────────────────────
   RESPONSIVE
   ────────────────────────────────────────────────────────────────────── */
@media (max-width: 1024px) {
  .why-layout         { grid-template-columns: 1fr; }
  .why-image-wrap     { aspect-ratio: 16/7; max-height: 400px; }
  .why-grid           { grid-template-columns: repeat(2, 1fr); }
  .overview-grid      { grid-template-columns: repeat(3, 1fr); }
  .region-card        { grid-template-columns: 1fr; gap: 40px; }
  .stat-card          { border-bottom: 1px solid var(--border); }
  .stat-card:nth-child(3n) { border-right: none; }
}
@media (max-width: 768px) {
  .nav-links          { display: none; }
  .mobile-menu-btn    { display: flex; }
  .app-header-inner   { grid-template-columns: 1fr; text-align: center; gap: 10px; }
  .header-logos,
  .header-logos-right { justify-content: center; }
  .header-center h2   { font-size: clamp(1.1rem, 2vw, 1.5rem); }
  .header-center h3   { font-size: clamp(1rem, 1.6vw, 1.15rem); }
  .header-center h4   { font-size: clamp(0.8rem, 1.3vw, 0.95rem); }
  .header-logos       { min-width: 80px; }
  .iirs-logo          { height: 55px;}
  .gov-logo           { height: 55px; }
  .footer-links-col   { align-items: flex-start; }
  .overview-grid      { grid-template-columns: repeat(2, 1fr); }
  .stat-card:nth-child(2n) { border-right: none; }
  .stat-card:nth-child(3n) { border-right: 1px solid var(--border); }
}
@media (max-width: 480px) {
  .hero-title         { font-size: 2.8rem; }
  .iirs-logo          { height: 40px; }
  .gov-logo           { height: 36px; }
  .footer-inner       { flex-direction: column; align-items: center; text-align: center; }
  .footer-links-col   { align-items: center; }
  .why-grid           { grid-template-columns: 1fr; }
  .overview-grid      { grid-template-columns: repeat(2, 1fr); }
  .hero-cta-row       { flex-direction: column; align-items: center; width: 100%; }
  .btn-hero-primary, .btn-hero-secondary { width: 100%; max-width: 300px; }
}

/* ──────────────────────────────────────────────────────────────────────
   AQUABOT CHATBOT — FAB
   ────────────────────────────────────────────────────────────────────── */
.chat-fab {
  display: flex; /* Always visible on desktop now */
  position: fixed; bottom: 28px; right: 28px; z-index: 1000;
  width: 58px; height: 58px; border-radius: 50%;
  background: linear-gradient(135deg, #00D4A8, #3B82F6);
  border: none; cursor: pointer;
  box-shadow: 0 8px 28px rgba(0, 212, 168, 0.45);
  transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.3s ease;
  align-items: center; justify-content: center;
}
.chat-fab:hover { transform: scale(1.1); box-shadow: 0 12px 36px rgba(0,212,168,0.55); }
.chat-fab.active { background: linear-gradient(135deg, #ef4444, #f97316); }
.chat-fab-icon { font-size: 1.5rem; line-height: 1; }
.chat-fab-badge {
  position: absolute; top: -4px; right: -4px;
  background: #ef4444; color: #fff;
  font-size: 0.65rem; font-weight: 700;
  width: 20px; height: 20px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  border: 2px solid #fff;
}

/* ──────────────────────────────────────────────────────────────────────
   AQUABOT CHATBOT — PANEL (fixed right sidebar on desktop)
   ────────────────────────────────────────────────────────────────────── */
.chat-panel {
  position: fixed;
  bottom: 100px;
  right: 30px;
  width: 380px;
  max-height: min(700px, 80vh);
  z-index: 1500;
  display: flex;
  flex-direction: column;

  /* Glassmorphic dark background */
  background: rgba(13, 20, 42, 0.95);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(0, 212, 168, 0.25);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
  border-radius: 24px;

  opacity: 0;
  pointer-events: none;
  transform: translateY(20px) scale(0.95);
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.chat-panel.open {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0) scale(1);
}

/* Light theme override */
.home-root:not(.dark) .chat-panel {
  background: rgba(248, 250, 252, 0.98);
  border: 1px solid rgba(13, 148, 136, 0.25);
  box-shadow: 0 20px 50px rgba(0,0,0,0.15);
}

/* Removed permanent open on large desktop to allow popup behavior */

/* ── Panel Header ── */
.cp-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(0, 212, 168, 0.12);
  background: rgba(0, 212, 168, 0.05);
  flex-shrink: 0;
}
.home-root:not(.dark) .cp-header {
  border-bottom: 1px solid rgba(13,148,136,0.12);
  background: rgba(13,148,136,0.05);
}
.cp-header-left { display: flex; align-items: center; gap: 12px; }
.cp-avatar {
  width: 42px; height: 42px; border-radius: 12px;
  background: linear-gradient(135deg, rgba(0,212,168,0.2), rgba(59,130,246,0.2));
  border: 1px solid rgba(0,212,168,0.3);
  display: flex; align-items: center; justify-content: center;
  font-size: 1.4rem;
  box-shadow: 0 4px 12px rgba(0,212,168,0.15);
}
.cp-title {
  font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 1rem;
  color: #F8FAFC; letter-spacing: 0.02em;
}
.home-root:not(.dark) .cp-title { color: #0F172A; }
.cp-subtitle {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.72rem; color: #94A3B8; font-family: 'JetBrains Mono', monospace;
}
.home-root:not(.dark) .cp-subtitle { color: #64748B; }
.cp-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #00D4A8; animation: pulse 2s infinite;
  box-shadow: 0 0 8px rgba(0,212,168,0.6); flex-shrink: 0;
}
.cp-dot.thinking { background: #FDE047; box-shadow: 0 0 8px rgba(253,224,71,0.6); }
.cp-close {
  background: none; border: none; color: #64748B; cursor: pointer;
  font-size: 1rem; padding: 6px; border-radius: 8px;
  transition: all 0.2s ease;
}
.cp-close:hover { color: #ef4444; background: rgba(239,68,68,0.1); }

/* ── Suggestions ── */
.cp-suggestions {
  padding: 14px 16px 10px;
  border-bottom: 1px solid rgba(0,212,168,0.08);
  flex-shrink: 0;
}
.home-root:not(.dark) .cp-suggestions { border-bottom-color: rgba(13,148,136,0.1); }
.cp-suggest-label {
  font-size: 0.7rem; color: #64748B; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;
}
.cp-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.cp-chip {
  padding: 5px 12px; border-radius: 20px; font-size: 0.75rem;
  background: rgba(0,212,168,0.08); border: 1px solid rgba(0,212,168,0.2);
  color: #00D4A8; cursor: pointer; font-weight: 500;
  transition: all 0.2s ease; white-space: nowrap;
}
.cp-chip:hover {
  background: rgba(0,212,168,0.18); border-color: rgba(0,212,168,0.45);
  transform: translateY(-1px);
}
.home-root:not(.dark) .cp-chip {
  background: rgba(13,148,136,0.08); border-color: rgba(13,148,136,0.25);
  color: #0D9488;
}
.home-root:not(.dark) .cp-chip:hover {
  background: rgba(13,148,136,0.16); border-color: rgba(13,148,136,0.45);
}

/* ── Messages ── */
.cp-messages {
  flex: 1; overflow-y: auto; padding: 16px;
  display: flex; flex-direction: column; gap: 12px;
  scroll-behavior: smooth;
}
.cp-messages::-webkit-scrollbar { width: 4px; }
.cp-messages::-webkit-scrollbar-thumb {
  background: rgba(0,212,168,0.2); border-radius: 4px;
}

/* Welcome card */
.cp-welcome {
  display: flex; flex-direction: column; align-items: center;
  text-align: center; padding: 24px 12px; gap: 14px;
  background: rgba(0,212,168,0.05);
  border: 1px solid rgba(0,212,168,0.1);
  border-radius: 16px;
}
.home-root:not(.dark) .cp-welcome {
  background: rgba(13,148,136,0.05); border-color: rgba(13,148,136,0.1);
}
.cp-welcome-icon { font-size: 2.5rem; }
.cp-welcome-text { font-size: 0.85rem; color: #94A3B8; line-height: 1.7; }
.home-root:not(.dark) .cp-welcome-text { color: #334155; }
.cp-welcome-text strong { color: #00D4A8; }
.home-root:not(.dark) .cp-welcome-text strong { color: #0D9488; }

/* Message rows */
.cp-msg { display: flex; flex-direction: column; gap: 4px; max-width: 95%; }
.cp-msg-user { align-self: flex-end; align-items: flex-end; }
.cp-msg-bot  { align-self: flex-start; align-items: flex-start; }

.cp-bubble {
  padding: 10px 14px; border-radius: 16px; font-size: 0.82rem;
  line-height: 1.65; max-width: 100%;
}
.cp-msg-user .cp-bubble {
  background: linear-gradient(135deg, #00D4A8, #0EA5E9);
  color: #fff; border-bottom-right-radius: 4px;
  box-shadow: 0 4px 14px rgba(0,212,168,0.25);
}
.cp-msg-bot .cp-bubble {
  background: rgba(30, 41, 59, 0.7);
  border: 1px solid rgba(0,212,168,0.1);
  color: #E2E8F0; border-bottom-left-radius: 4px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.2);
}
.home-root:not(.dark) .cp-msg-bot .cp-bubble {
  background: #0b1827;
  border: 1px solid rgba(13,148,136,0.12);
  color: #334155;
  box-shadow: 0 2px 10px rgba(0,0,0,0.06);
}

/* Inline code in bot messages */
.cp-bubble-text code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  background: rgba(0,212,168,0.12);
  padding: 1px 6px; border-radius: 4px;
  color: #00D4A8;
}
.home-root:not(.dark) .cp-bubble-text code {
  background: rgba(13,148,136,0.1); color: #0D9488;
}
.cp-bubble-text ul { margin: 6px 0 0 16px; padding: 0; }
.cp-bubble-text li { margin-bottom: 3px; }

/* Typing indicator */
.cp-typing {
  display: flex; align-items: center; gap: 5px;
  padding: 12px 16px; min-width: 56px;
}
.cp-typing span {
  width: 7px; height: 7px; border-radius: 50%;
  background: #00D4A8; animation: typingBounce 1.2s infinite;
}
.cp-typing span:nth-child(2) { animation-delay: 0.2s; }
.cp-typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

/* Live data card */
.cp-data-card {
  margin-top: 8px; padding: 10px 12px;
  background: rgba(0, 212, 168, 0.06);
  border: 1px solid rgba(0, 212, 168, 0.15);
  border-radius: 10px;
}
.home-root:not(.dark) .cp-data-card {
  background: rgba(13,148,136,0.06); border-color: rgba(13,148,136,0.18);
}
.cp-data-title {
  font-size: 0.68rem; font-weight: 700; color: #00D4A8;
  text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;
  font-family: 'JetBrains Mono', monospace;
}
.home-root:not(.dark) .cp-data-title { color: #0D9488; }
.cp-data-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.cp-data-item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 6px 8px; border-radius: 8px;
  background: rgba(0,0,0,0.15);
}
.home-root:not(.dark) .cp-data-item { background: rgba(0,0,0,0.04); }
.cp-data-label {
  font-size: 0.65rem; color: #64748B; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.cp-data-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82rem; font-weight: 700; color: #00D4A8;
}
.home-root:not(.dark) .cp-data-val { color: #0D9488; }

/* Sources */
.cp-sources { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.cp-source-tag {
  font-size: 0.62rem; padding: 2px 8px; border-radius: 50px;
  background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.2);
  color: #93C5FD; font-family: 'JetBrains Mono', monospace;
}
.home-root:not(.dark) .cp-source-tag {
  background: rgba(37,99,235,0.07); border-color: rgba(37,99,235,0.15);
  color: #2563EB;
}

/* Timestamps */
.cp-time {
  font-size: 0.62rem; color: #64748B;
  font-family: 'JetBrains Mono', monospace; padding: 0 4px;
}

/* Error */
.cp-error {
  padding: 10px 16px; font-size: 0.78rem;
  background: rgba(239,68,68,0.1); border-top: 1px solid rgba(239,68,68,0.2);
  color: #FCA5A5; flex-shrink: 0;
}
.home-root:not(.dark) .cp-error { color: #DC2626; background: rgba(239,68,68,0.06); }

/* ── Input Row ── */
.cp-input-row {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid rgba(0,212,168,0.1);
  background: rgba(0,0,0,0.2);
  flex-shrink: 0;
}
.home-root:not(.dark) .cp-input-row {
  border-top-color: rgba(13,148,136,0.12); background: rgba(0,0,0,0.02);
}
.cp-input {
  flex: 1; padding: 10px 14px; border-radius: 24px;
  background: rgba(30,41,59,0.6); border: 1px solid rgba(0,212,168,0.15);
  color: #F8FAFC; font-size: 0.83rem; font-family: 'Inter', sans-serif;
  outline: none; transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.cp-input:focus {
  border-color: rgba(0,212,168,0.45);
  box-shadow: 0 0 0 3px rgba(0,212,168,0.08);
}
.cp-input::placeholder { color: #475569; }
.cp-input:disabled { opacity: 0.5; cursor: not-allowed; }
.home-root:not(.dark) .cp-input {
  background: #F8FAFC; border-color: rgba(13,148,136,0.2);
  color: #0F172A;
}
.home-root:not(.dark) .cp-input::placeholder { color: #94A3B8; }
.home-root:not(.dark) .cp-input:focus {
  border-color: rgba(13,148,136,0.5); box-shadow: 0 0 0 3px rgba(13,148,136,0.08);
}

.cp-send {
  width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #00D4A8, #0EA5E9);
  border: none; cursor: pointer; color: #fff;
  display: flex; align-items: center; justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 4px 12px rgba(0,212,168,0.3);
}
.cp-send:hover:not(:disabled) {
  transform: scale(1.08); box-shadow: 0 6px 18px rgba(0,212,168,0.4);
}
.cp-send:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

/* ── Mobile: show FAB, hide panel until open ── */
@media (max-width: 1299px) {
  .chat-fab { display: flex; }
  .chat-panel {
    width: 100%;
    max-width: 420px;
    border-radius: 24px 0 0 24px;
  }
}
@media (max-width: 480px) {
  .chat-panel {
    width: 100%; max-width: 100%;
    border-radius: 24px 24px 0 0;
    top: auto; bottom: 0;
    height: 80vh;
    border-left: none;
    border-top: 1px solid rgba(0,212,168,0.2);
  }
  .chat-fab { bottom: 20px; right: 20px; }
}
</style>
