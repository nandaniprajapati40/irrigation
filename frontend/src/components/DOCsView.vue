<!-- DOCsView.vue -->
<template>
  <div class="wiki-root">
    <header class="app-header">
      <div class="app-header-inner">
        <div class="header-logos">
          <img src="/assets/logo1.png" class="iirs-logo" onerror="this.style.display='none'" />
          <img src="/assets/isro.png" class="iirs-logo" onerror="this.style.display='none'" />
        </div>
        <div class="header-center">
          <h2>भारतीय अंतरिक्ष अनुसंधान संगठन, अंतरिक्ष विभाग</h2>
          <h3>Indian Space Research Organisation, Department of Space</h3>
          <h4>भारत सरकार / Government of India</h4>
        </div>
        <div class="header-logos header-logos-right">
          <img src="/assets/iirs.png" class="iirs-logo" onerror="this.style.display='none'" />
          <img src="/assets/india.png" class="gov-logo" onerror="this.style.display='none'" />
        </div>
      </div>
    </header>

    <nav class="nav-bar">
      <div class="nav-inner">
        <div class="nav-links">
          <button class="nav-link" @click="$emit('home')">Home</button>
          <button class="nav-link active" @click="$emit('docs')">Docs</button>
          <button class="nav-link" @click="$emit('faqs')">FAQs</button>
        </div>
      </div>
    </nav>

    <main class="article-shell">
      

      <div class="search-wrap">
        <span class="search-icon">Search 🔍 </span>
        <input
          v-model="query"
          type="search"
          class="search-input"
          placeholder="Search this"
          autocomplete="off"
        />
        <button v-if="query" class="clear-btn" @click="query = ''">Clear</button>
      </div>

      <p v-if="query" class="search-status">
        Showing {{ filteredBlocks.length }} matching topic{{ filteredBlocks.length === 1 ? '' : 's' }} for "{{ query }}".
      </p>

      <article class="wiki-article">
        <aside class="fact-box">
          <img src="/assets/about.png" alt="JalDrishti irrigation monitoring" onerror="this.style.display='none'" />
          <dl>
            <div>
              <dt>Purpose</dt>
              <dd>Smart irrigation planning</dd>
            </div>
            <div>
              <dt>Focus crop</dt>
              <dd>Rabi wheat</dd>
            </div>
            <div>
              <dt>Study area</dt>
              <dd>Udham Singh Nagar, Uttarakhand</dd>
            </div>
            <div>
              <dt>Main outputs</dt>
              <dd>CWR, IWR, SAVI, NDVI, Kc</dd>
            </div>
          </dl>
        </aside>

        <section v-for="block in filteredBlocks" :key="block.title" class="article-block">
          <h2 v-html="highlight(block.title)"></h2>
          <p v-for="text in block.paragraphs" :key="text" v-html="highlight(text)"></p>
          <ul v-if="block.points" class="plain-list">
            <li v-for="point in block.points" :key="point" v-html="highlight(point)"></li>
          </ul>
        </section>

        <section v-if="filteredBlocks.length === 0" class="empty-state">
          <h2>No matching content found</h2>
          <p>Try searching with a simpler word such as water, crop, map, graph, farmer, or satellite.</p>
        </section>
      </article>
    </main>

    <footer class="site-footer">
      <div class="footer-inner">
        <p><strong>JalDrishti</strong> · Irrigation Water Requirements</p>
        <p>ISRO · IIRS · Department of Space, Government of India</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

defineProps({ isDark: { type: Boolean, default: false } })
defineEmits(['home', 'launch', 'docs', 'faqs'])

const query = ref('')

const articleBlocks = [
  {
    title: 'Introduction',
    paragraphs: [
      'JalDrishti is an intelligent irrigation monitoring platform that helps people understand how much water a crop needs and when irrigation may be required. It is designed for farmers, researchers, agricultural officers, and water resource managers who need clear information for better irrigation decisions.',
      'The name combines two Sanskrit and Hindi words: Jal, meaning water, and Drishti, meaning vision or insight. Together, JalDrishti means a vision for smart water management.'
    ]
  },
  {
    title: 'What JalDrishti Does',
    paragraphs: [
      'The system works like a digital guide for crop water needs. It studies field conditions, weather information, and satellite-based crop indicators, then presents the results through maps, charts, and simple values.',
      'Instead of asking users to understand complex data files, JalDrishti turns agricultural and environmental data into practical information that can support irrigation planning.'
    ],
    points: [
      'Monitors irrigation conditions across agricultural areas.',
      'Estimates Crop Water Requirement, also called CWR.',
      'Shows map layers that help users compare different parts of a region.',
      'Creates pixel-level graphs so users can study changes at a specific location.',
      'Supports water conservation and precision agriculture.'
    ]
  },
  {
    title: 'Why It Is Useful',
    paragraphs: [
      'Crops do not need the same amount of water every day. Young plants need less water, actively growing crops need more, and mature crops need less again. Rainfall, soil moisture, temperature, and crop health also change the amount of irrigation required.',
      'JalDrishti helps reduce guesswork. By showing where water demand is high or low, it can help avoid over-irrigation, save groundwater, reduce pumping cost, and support healthier crop growth.'
    ]
  },
  {
    title: 'Crop Water Requirement',
    paragraphs: [
      'Crop Water Requirement, or CWR, means the total amount of water a crop needs for healthy growth. Irrigation Water Requirement, or IWR, means the water that must be supplied through irrigation after considering rainfall and other available moisture.',
      'In simple words: if the crop needs water and rainfall is not enough, irrigation is required. JalDrishti helps estimate this need for different crop stages and different locations.'
    ],
    points: [
      'Evapotranspiration shows how much water is lost from soil and plants.',
      'Vegetation indices show whether the crop appears healthy and active.',
      'Climatic conditions such as temperature and rainfall affect daily water demand.',
      'Crop coefficient, or Kc, helps adjust water demand according to crop growth stage.'
    ]
  },
  {
    title: 'Interactive Geospatial Dashboard',
    paragraphs: [
      'The dashboard provides a map-based view of agricultural areas. Users can view raster layers, explore irrigation zones, inspect crop condition, and understand how water requirement changes across the study region.',
      'The map is useful because water need is not always the same in every field. Two nearby areas may have different crop growth, soil condition, or irrigation demand.'
    ]
  },
  {
    title: 'Raster Layers Explained',
    paragraphs: [
      'JalDrishti uses raster data, which means the map is divided into many small cells or pixels. Each pixel stores a value, such as crop health or water requirement. This allows the system to show detailed variation across a region.'
    ],
    points: [
      'SAVI and NDVI help indicate vegetation condition and crop greenness.',
      'CWR shows the water needed by the crop.',
      'IWR shows the irrigation water that may need to be supplied.',
      'Kc represents crop growth stage and water use behavior.',
      'These layers make it easier to compare field conditions visually.'
    ]
  },
  {
    title: 'Pixel-Level Analytics',
    paragraphs: [
      'A user can click a particular point on the map to study the values for that location. JalDrishti can then show how the selected pixel changed over time.',
      'This is helpful for local analysis. For example, a researcher can compare crop condition across multiple dates, while an irrigation planner can check whether a specific area is showing higher water demand.'
    ]
  },
  {
    title: 'Time-Series Graphs',
    paragraphs: [
      'Time-series graphs show how crop and irrigation values change day by day, week by week, or across a full season. These graphs make trends easier to understand than raw numbers.',
      'The platform supports graph widgets that help users monitor daily analysis, weekly changes, seasonal irrigation trends, and historical crop performance.'
    ]
  },
  {
    title: 'Data Management',
    paragraphs: [
      'JalDrishti stores processed raster details, map layer information, and extracted analytical results in databases. This makes it possible to retrieve past records and compare historical agricultural conditions.',
      'The system may use databases such as MongoDB and MySQL depending on the type of data being stored.'
    ]
  },
  {
    title: 'Technologies Used',
    paragraphs: [
      'JalDrishti is built as a web-based geospatial platform. The user-facing part is made with modern web technologies, while the processing side uses tools for satellite data, raster analysis, databases, and charts.',
      'For non-technical users, the important point is simple: these technologies work together so that complex satellite and weather data can be shown as easy maps, graphs, and irrigation indicators.'
    ],
    points: [
      'Frontend tools create the website, dashboard, map interface, and charts.',
      'Backend tools process requests and connect the dashboard with data.',
      'GIS tools handle satellite images, raster files, and map services.',
      'Analytics tools help calculate crop indicators and water requirement values.',
      'Cloud and infrastructure tools help run and manage the system.'
    ]
  },
  {
    title: 'System Architecture',
    paragraphs: [
      'The platform follows a layered structure. First, data is collected from satellite images, raster datasets, and weather sources. Next, the data is processed to calculate crop and irrigation indicators. Then it is stored for future use. Finally, the results are displayed through maps, charts, and dashboard tools.',
      'This layered approach keeps the system organized and makes it easier to expand in the future.'
    ]
  },
  {
    title: 'Applications',
    paragraphs: [
      'JalDrishti can support precision agriculture, smart irrigation planning, agricultural research, water resource management, crop monitoring, and drought assessment.',
      'It is especially useful in regions where irrigation water is limited or where crop water demand changes quickly during the growing season.'
    ]
  },
  {
    title: 'Benefits',
    paragraphs: [
      'The main benefit of JalDrishti is better decision-making. It helps users understand when irrigation is needed, where water demand is higher, and how crop conditions are changing over time.',
      'By supporting efficient irrigation planning, the platform can help reduce water wastage, improve crop productivity, and support sustainable agriculture.'
    ]
  },
  {
    title: 'Future Enhancements',
    paragraphs: [
      'Future development can make JalDrishti even more useful by adding AI-based irrigation prediction, real-time IoT sensor data, mobile application support, automated drought alerts, weather forecast integration, and 3D agricultural visualization.',
      'These additions would help the platform move from monitoring current conditions to giving stronger forward-looking irrigation guidance.'
    ]
  },
  {
    title: 'Conclusion',
    paragraphs: [
      'JalDrishti is a modern irrigation intelligence platform that combines geospatial analysis, remote sensing, weather information, and interactive visualization. Its goal is to make crop water requirement information clear, useful, and accessible.',
      'By helping users understand irrigation demand in near real time, JalDrishti supports smarter agricultural practices, better water management, and more sustainable use of natural resources.'
    ]
  }
]

const filteredBlocks = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return articleBlocks

  return articleBlocks.filter((block) => {
    const haystack = [
      block.title,
      ...block.paragraphs,
      ...(block.points || [])
    ].join(' ').toLowerCase()

    return haystack.includes(term)
  })
})

function highlight(text) {
  const term = query.value.trim()
  if (!term) return text

  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>')
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Devanagari:wght@500;700&display=swap');

.wiki-root {
  --header-bg: #1A4A6B;
  --header-text: #FFFFFF;
  --nav-bg: #009688;
  --nav-text: #FFFFFF;
  min-height: 100vh;
  background: #ffffff;
  color: #1f2937;
  font-family: 'Inter', sans-serif;
}

.app-header {
  position: relative;
  z-index: 201;
  background: var(--header-bg);
  border-bottom: 1px solid rgba(0, 0, 0, 0.18);
  padding: 14px 24px;
  box-shadow: 0 3px 14px rgba(0, 0, 0, 0.25);
  transition: background 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease;
}

.app-header-inner {
  max-width: 1280px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
}

.header-logos,
.header-logos-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-logos-right {
  justify-content: flex-end;
}

.iirs-logo,
.gov-logo {
  height: 64px;
  width: auto;
  object-fit: contain;
  transition: transform 0.3s ease, filter 0.3s ease;
}
.iirs-logo:hover,
.gov-logo:hover { transform: scale(1.05); }

.gov-logo {
  height: 60px;
}

.header-center {
  flex: 1;
  text-align: center;
  padding: 0 8px;
}

.header-center h2 {
  margin: 0 0 4px;
  color: var(--header-text);
  font-family: 'Outfit', sans-serif;
  font-size: clamp(1.1rem, 2vw, 1.5rem);
  font-weight: 800;
  text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

.header-center h3 {
  margin: 0 0 2px;
  color: var(--header-text);
  opacity: 0.9;
  font-size: clamp(1.0rem, 1.6vw, 1.15rem);
  font-weight: 500;
}

.header-center h4 {
  margin: 0;
  color: var(--header-text);
  opacity: 0.75;
  font-size: clamp(0.8rem, 1.3vw, 0.95rem);
  font-weight: 400;
}

.nav-bar {
  position: sticky;
  top: 0;
  z-index: 200;
  background: var(--nav-bg);
  border-bottom: 2px solid rgba(0, 0, 0, 0.15);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.20);
  transition: background 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease;
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

.nav-links {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.nav-link {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--nav-text);
  cursor: pointer;
  font-family: 'Inter', sans-serif;
  font-size: 0.9rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 8px 20px;
  position: relative;
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

.nav-link:hover,
.nav-link.active {
  background: rgba(255, 255, 255, 0.18);
  color: #ffffff;
}

.nav-link:hover::after,
.nav-link.active::after { width: 70%; }

.article-shell {
  max-width: 1040px;
  margin: 0 auto;
  padding: 40px 24px 60px;
}

.article-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid #d7dee8;
  padding-bottom: 22px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #0f766e;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: #ffffff;
  font-size: clamp(2.5rem, 6vw, 4.5rem);
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0;
}

.subtitle {
  margin: 12px 0 0;
  color: #ffffff;
  font-size: clamp(1rem, 2vw, 1.25rem);
  font-weight: 600;
}

.quick-links {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.quick-links button,
.clear-btn {
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #ffffff;
  color: #0f766e;
  cursor: pointer;
  font: inherit;
  font-weight: 700;
  padding: 9px 14px;
}

.quick-links button:hover,
.clear-btn:hover {
  border-color: #0f766e;
  background: #f0fdfa;
}

.search-wrap {
  margin: 24px 0 8px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
  padding: 10px 12px;
}

.search-icon {
  color: #0f766e;
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.search-input {
  min-width: 0;
  border: 0;
  outline: none;
  background: transparent;
  color: #111827;
  font: inherit;
  font-size: 0.98rem;
}

.search-status {
  margin: 0 0 18px;
  color: #64748b;
  font-size: 0.9rem;
}

.wiki-article {
  margin-top: 28px;
  color: #1f2937;
  font-size: 1.02rem;
  line-height: 1.75;
}

.fact-box {
  float: right;
  width: min(300px, 42%);
  margin: 0 0 24px 32px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  overflow: hidden;
  background: #f8fafc;
}

.fact-box img {
  display: block;
  width: 100%;
  height: 170px;
  object-fit: cover;
  background: #e2e8f0;
}

.fact-box dl {
  margin: 0;
}

.fact-box div {
  display: grid;
  grid-template-columns: 105px 1fr;
  gap: 10px;
  border-top: 1px solid #e2e8f0;
  padding: 10px 12px;
}

.fact-box dt {
  color: #334155;
  font-weight: 800;
}

.fact-box dd {
  margin: 0;
  color: #475569;
}

.article-block {
  margin-bottom: 28px;
}

.article-block h2,
.empty-state h2 {
  margin: 0 0 10px;
  border-bottom: 1px solid #d7dee8;
  color: #111827;
  font-size: 1.45rem;
  font-weight: 800;
  line-height: 1.35;
  padding-bottom: 6px;
}

.article-block p,
.empty-state p {
  margin: 0 0 13px;
}

.plain-list {
  margin: 8px 0 0 22px;
  padding: 0;
}

.plain-list li {
  margin-bottom: 6px;
}

:deep(mark) {
  border-radius: 3px;
  background: #fef08a;
  color: inherit;
  padding: 0 2px;
}

.empty-state {
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  padding: 24px;
  background: #f8fafc;
}

.site-footer {
  border-top: 1px solid #d7dee8;
  background: #f8fafc;
  padding: 24px;
}

.footer-inner {
  max-width: 1040px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  color: #64748b;
  font-size: 0.9rem;
}

.footer-inner p {
  margin: 0;
}

@media (max-width: 760px) {
  .app-header-inner {
    grid-template-columns: 1fr;
    text-align: center;
  }

  .header-logos,
  .header-logos-right {
    justify-content: center;
  }

  .iirs-logo {
    height: 44px;
  }

  .gov-logo {
    height: 40px;
  }

  .article-top {
    flex-direction: column;
  }

  .quick-links {
    width: 100%;
  }

  .quick-links button {
    flex: 1;
  }

  .search-wrap {
    grid-template-columns: 1fr auto;
  }

  .search-icon {
    grid-column: 1 / -1;
  }

  .fact-box {
    float: none;
    width: 100%;
    margin: 0 0 24px;
  }
}
</style>
