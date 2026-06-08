<template>
  <div class="jaldrishtibot-chat">
    <!-- Header -->
    

    <!-- Messages Area -->
    <div class="messages-area" ref="messagesArea">
      <!-- Welcome -->
      <div v-if="messages.length === 0" class="welcome-screen">
        <div class="welcome-icon">
          <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="32" cy="32" r="30" fill="url(#wGrad)" opacity=".15"/>
            <path d="M18 38 Q24 18 32 24 Q40 30 46 18" stroke="url(#wGrad)" stroke-width="3" stroke-linecap="round" fill="none"/>
            <circle cx="22" cy="35" r="3" fill="url(#wGrad)"/>
            <circle cx="42" cy="28" r="3" fill="url(#wGrad)"/>
            <defs>
              <linearGradient id="wGrad" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
                <stop stop-color="#1a6bff"/>
                <stop offset="1" stop-color="#00c6ff"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h2 class="welcome-title">Hi, I'm JalDrishtiBot</h2>
        <p class="welcome-sub">Ask me about irrigation, crop water requirements, SAVI, CWR, IWR, or field conditions.</p>
        <p v-if="lat && lon" class="welcome-location">
          📍 Field location: {{ lat.toFixed(4) }}, {{ lon.toFixed(4) }}
        </p>
        <div class="suggestion-chips">
          <button
            v-for="s in suggestions"
            :key="s"
            class="chip"
            @click="sendSuggestion(s)"
          >{{ s }}</button>
        </div>
      </div>

      <!-- Message List -->
      <TransitionGroup name="msg" tag="div" class="message-list">
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['message-row', msg.role]"
        >
          <div v-if="msg.role === 'assistant'" class="msg-avatar">
            <svg viewBox="0 0 28 28" fill="none"><circle cx="14" cy="14" r="14" fill="url(#a2)"/><path d="M8 17 Q11 8 14 11 Q17 14 20 9" stroke="#fff" stroke-width="1.8" stroke-linecap="round" fill="none"/><circle cx="10" cy="16" r="1.4" fill="#fff"/><circle cx="18" cy="13" r="1.4" fill="#fff"/><defs><linearGradient id="a2" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse"><stop stop-color="#1a6bff"/><stop offset="1" stop-color="#00c6ff"/></linearGradient></defs></svg>
          </div>
          <div class="message-content-wrap">
            <div :class="['bubble', msg.role, { streaming: msg.streaming, editing: msg.editing }]">
              <template v-if="msg.editing">
                <textarea
                  v-model="msg.editText"
                  class="edit-textarea"
                  @keydown.enter.exact.prevent="saveEdit(msg)"
                  @keydown.escape="cancelEdit(msg)"
                  ref="editTextarea"
                  rows="3"
                ></textarea>
                <div class="edit-actions">
                  <button class="edit-btn save" @click="saveEdit(msg)">Save & Resend</button>
                  <button class="edit-btn cancel" @click="cancelEdit(msg)">Cancel</button>
                </div>
              </template>
              <template v-else>
                <div class="bubble-text" v-html="formatText(msg.content)"></div>
                <span v-if="msg.streaming" class="cursor-blink">▌</span>
              </template>
            </div>

            <!-- Sources -->
            <!-- <div v-if="msg.sources && msg.sources.length" class="sources-row">
              <span class="sources-label">Sources:</span>
              <span v-for="s in msg.sources" :key="s" class="source-tag">{{ s }}</span>
            </div> -->

            <!-- Timestamp + Actions -->
            <div class="msg-meta">
              <span class="timestamp">{{ formatTime(msg.timestamp) }}</span>
              <div class="msg-actions" v-if="!msg.streaming">
                <button class="meta-btn" title="Copy" @click="copyMessage(msg)">
                  <svg viewBox="0 0 16 16" fill="none"><rect x="5" y="5" width="9" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M3 11V3a1 1 0 011-1h8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
                  <span class="meta-label">{{ msg.copied ? 'Copied!' : 'Copy' }}</span>
                </button>
                <button
                  v-if="msg.role === 'user'"
                  class="meta-btn"
                  title="Edit"
                  @click="startEdit(msg)"
                >
                  <svg viewBox="0 0 16 16" fill="none"><path d="M11.5 2.5l2 2-8 8-3 1 1-3 8-8z" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  <span class="meta-label">Edit</span>
                </button>
                <button
                  class="meta-btn danger"
                  title="Delete"
                  @click="deleteMessage(msg.id)"
                >
                  <svg viewBox="0 0 16 16" fill="none"><path d="M3 4h10M6 4V2h4v2M5 4l.6 9h4.8L11 4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  <span class="meta-label">Delete</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- Typing indicator -->
      <div v-if="isTyping && !currentStream" class="message-row assistant typing-row">
        <div class="msg-avatar">
          <svg viewBox="0 0 28 28" fill="none"><circle cx="14" cy="14" r="14" fill="url(#a3)"/><path d="M8 17 Q11 8 14 11 Q17 14 20 9" stroke="#fff" stroke-width="1.8" stroke-linecap="round" fill="none"/><defs><linearGradient id="a3" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse"><stop stop-color="#1a6bff"/><stop offset="1" stop-color="#00c6ff"/></linearGradient></defs></svg>
        </div>
        <div class="bubble assistant typing-bubble">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      </div>
    </div>

    <!-- Input Area -->
    <div class="input-area">
      <div class="input-wrap" :class="{ focused: inputFocused }">
        <textarea
          ref="inputRef"
          v-model="userInput"
          placeholder="Ask about irrigation, CWR, IWR, crop stages…"
          class="chat-input"
          rows="1"
          :disabled="isLoading"
          @focus="inputFocused = true"
          @blur="inputFocused = false"
          @keydown.enter.exact.prevent="sendMessage"
          @keydown.shift.enter="addNewline"
          @input="autoResize"
        ></textarea>
        <button
          class="send-btn"
          :class="{ active: userInput.trim() }"
          :disabled="!userInput.trim() || isLoading"
          @click="sendMessage"
        >
          <svg v-if="!isLoading" viewBox="0 0 20 20" fill="none">
            <path d="M3 10L17 10M11 4l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <svg v-else class="spin" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="2" stroke-dasharray="22 10" stroke-linecap="round"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'JalDrishtiBotChat',

  props: {
    //
    // KEY FIX: Default is now '' (empty string = same origin).
    //
    // In Docker the stack is:
    //   browser → nginx:80 → (proxies /api/*) → backend:8000
    //
    // Using '' means fetch('/api/chat/stream') hits nginx on whatever
    // host/port the user is on — localhost, a dev tunnel, or production —
    // and nginx forwards it internally to the backend container.
    //
    // No VITE_API_BASE env var is needed unless you want to point at a
    // completely different host (e.g. a remote staging backend).
    //
    apiBase: {
      type: String,
      default: () =>
        (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE) ||
        ''   // ← same-origin; nginx proxy handles /api/* → backend:8000
    },
    sessionId: {
      type: String,
      default: () => `session-${Date.now()}`
    },
    lat: {
      type: Number,
      default: null
    },
    lon: {
      type: Number,
      default: null
    }
  },

  emits: ['connection-change'],

  data() {
    return {
      messages: [],
      userInput: '',
      isLoading: false,
      isTyping: false,
      isConnected: true,
      inputFocused: false,
      currentStream: null,
      abortController: null,
      suggestions: [
        'What is the current CWR?',
        'Explain crop water requirements',
        'What growth stage is wheat in?',
        'How is IWR calculated?'
      ]
    }
  },

  watch: {
    isConnected(val) {
      this.$emit('connection-change', val)
    }
  },

  methods: {
    uid() {
      return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    },

    formatTime(ts) {
      if (!ts) return ''
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    },

    formatText(text) {
      if (!text) return ''
      return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>')
    },

    autoResize() {
      const el = this.$refs.inputRef
      if (!el) return
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 140) + 'px'
    },

    addNewline() {
      this.userInput += '\n'
      this.$nextTick(this.autoResize)
    },

    scrollToBottom(smooth = true) {
      this.$nextTick(() => {
        const el = this.$refs.messagesArea
        if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
      })
    },

    parseSseEvents(chunk) {
      return chunk
        .split(/\n\s*\n/)
        .map(block => {
          const event = { type: 'message', data: '' }
          block.split('\n').forEach(line => {
            if (line.startsWith('event:')) {
              event.type = line.slice(6).trim() || 'message'
            } else if (line.startsWith('data:')) {
              event.data += (event.data ? '\n' : '') + line.slice(5).trimStart()
            }
          })
          return event.data ? event : null
        })
        .filter(Boolean)
    },

    buildHistory() {
      return this.messages
        .filter(m => !m.streaming && m.content && m.content.trim() && ['user', 'assistant'].includes(m.role))
        .slice(-8)
        .map(m => ({ role: m.role, content: m.content }))
    },

    // Resolves the base URL for API calls.
    // '' (empty string) means same-origin — nginx on port 80 proxies /api/* to backend:8000.
    // A non-empty apiBase prop overrides this (e.g. for pointing at a remote host).
    resolvedApiBase() {
      return (this.apiBase || '').replace(/\/$/, '')
    },

    async sendMessage() {
      const text = this.userInput.trim()
      if (!text || this.isLoading) return

      const userMsg = {
        id: this.uid(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
        editing: false,
        editText: '',
        copied: false
      }
      this.messages.push(userMsg)
      this.userInput = ''
      this.$nextTick(() => {
        if (this.$refs.inputRef) {
          this.$refs.inputRef.style.height = 'auto'
        }
      })
      this.scrollToBottom()

      await this.callStream(text)
    },

    async callStream(query) {
      if (this.abortController) {
        this.abortController.abort()
      }
      this.abortController = new AbortController()

      this.isLoading = true
      this.isTyping = true

      const botMsg = {
        id: this.uid(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        streaming: true,
        sources: [],
        copied: false,
        editing: false,
        editText: ''
      }
      this.messages.push(botMsg)
      this.currentStream = botMsg.id

      const payload = {
        query,
        session_id: this.sessionId,
        history: this.buildHistory()
      }
      if (this.lat != null && this.lon != null &&
          isFinite(this.lat) && isFinite(this.lon)) {
        payload.lat = this.lat
        payload.lon = this.lon
      }

      try {
        const response = await fetch(
          `${this.resolvedApiBase()}/api/chat/stream`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: this.abortController.signal
          }
        )

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        if (!response.body) {
          throw new Error('Streaming response body is not available in this browser')
        }

        this.isTyping = false
        this.isConnected = true

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const parts = buffer.split(/\n\s*\n/)
          buffer = parts.pop() || ''

          for (const evt of this.parseSseEvents(parts.join('\n\n'))) {
            this.handleStreamEvent(botMsg.id, evt)
          }
          this.scrollToBottom(false)
        }

        buffer += decoder.decode()
        for (const evt of this.parseSseEvents(buffer)) {
          this.handleStreamEvent(botMsg.id, evt)
        }

      } catch (err) {
        if (err.name === 'AbortError') {
          const idx = this.messages.findIndex(m => m.id === botMsg.id)
          if (idx !== -1) this.messages.splice(idx, 1)
          return
        }

        console.error('[JalDrishtiBot] stream error:', err)
        this.isConnected = false

        const idx = this.messages.findIndex(m => m.id === botMsg.id)
        if (idx !== -1) {
          const userFacingError = err.message.startsWith('HTTP 5')
            ? 'The server encountered an error. Please try again in a moment.'
            : err.message.startsWith('HTTP 4')
            ? 'Request was rejected by the server. Please check your query and try again.'
            : 'Could not reach the server. Please check your connection and try again.'
          this.messages[idx].content = userFacingError
          this.messages[idx].streaming = false
        }
      } finally {
        const idx = this.messages.findIndex(m => m.id === botMsg.id)
        if (idx !== -1) this.messages[idx].streaming = false
        this.isLoading = false
        this.isTyping = false
        this.currentStream = null
        this.abortController = null
        this.scrollToBottom()
      }
    },

    handleStreamEvent(msgId, streamEvent) {
      const idx = this.messages.findIndex(m => m.id === msgId)
      if (idx === -1) return

      let evt
      try {
        evt = JSON.parse(streamEvent.data)
      } catch {
        return
      }

      if (streamEvent.type === 'token') {
        this.messages[idx].content += evt.content || ''
      } else if (streamEvent.type === 'done') {
        if (!this.messages[idx].content && evt.answer) {
          this.messages[idx].content = evt.answer
        }
        if (evt.sources) this.messages[idx].sources = evt.sources
        this.messages[idx].streaming = false
        this.isConnected = true
      } else if (streamEvent.type === 'meta') {
        if (evt.sources && evt.sources.length) {
          const existing = new Set(this.messages[idx].sources || [])
          evt.sources.forEach(s => existing.add(s))
          this.messages[idx].sources = Array.from(existing)
        }
      } else if (streamEvent.type === 'error') {
        this.messages[idx].content = evt.error || 'Sorry, I could not generate an answer right now.'
        this.messages[idx].streaming = false
        this.isConnected = false
      }
    },

    sendSuggestion(text) {
      this.userInput = text
      this.$nextTick(() => this.sendMessage())
    },

    async copyMessage(msg) {
      try {
        await navigator.clipboard.writeText(msg.content)
        msg.copied = true
        setTimeout(() => { msg.copied = false }, 2000)
      } catch {}
    },

    startEdit(msg) {
      msg.editText = msg.content
      msg.editing = true
      this.$nextTick(() => {
        const els = this.$refs.editTextarea
        if (els) {
          const el = Array.isArray(els) ? els[0] : els
          if (el) el.focus()
        }
      })
    },

    cancelEdit(msg) {
      msg.editing = false
      msg.editText = ''
    },

    saveEdit(msg) {
      const newText = msg.editText.trim()
      if (!newText) return
      msg.content = newText
      msg.editing = false
      msg.editText = ''

      const idx = this.messages.findIndex(m => m.id === msg.id)
      if (idx !== -1) {
        this.messages.splice(idx + 1)
        this.$nextTick(() => this.callStream(newText))
      }
    },

    deleteMessage(id) {
      const idx = this.messages.findIndex(m => m.id === id)
      if (idx !== -1) this.messages.splice(idx, 1)
    },

    clearChat() {
      if (this.abortController) {
        this.abortController.abort()
      }
      this.messages = []
      this.isLoading = false
      this.isTyping = false
      this.currentStream = null
      this.abortController = null
    }
  },

  mounted() {
    this.$nextTick(() => {
      if (this.$refs.inputRef) this.$refs.inputRef.focus()
    })
  },

  beforeUnmount() {
    if (this.abortController) {
      this.abortController.abort()
    }
  }
}
</script>

<style scoped>
/* ── Variables ── */
.jaldrishtibot-chat {
  --blue-1: #1a6bff;
  --blue-2: #00c6ff;
  --blue-3: #e8f1ff;
  --bg: #f4f7fb;
  --surface: #ffffff;
  --border: #e1e8f0;
  --text-1: #0f1923;
  --text-2: #5a6a7a;
  --text-3: #9aaabb;
  --danger: #e5474b;
  --radius: 16px;
  --radius-sm: 8px;
  --shadow: 0 2px 12px rgba(26,107,255,.10);
  --shadow-lg: 0 8px 32px rgba(26,107,255,.15);

  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
  background: var(--bg);
  font-family: 'DM Sans', 'Nunito', system-ui, sans-serif;
  color: var(--text-1);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}

/* ── Header ── */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: linear-gradient(135deg, var(--blue-1) 0%, #0052cc 100%);
  color: #fff;
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.bot-avatar { width: 38px; height: 38px; flex-shrink: 0; }
.bot-avatar svg { width: 100%; height: 100%; }
.header-info { display: flex; flex-direction: column; gap: 2px; }
.bot-name { font-size: 15px; font-weight: 700; letter-spacing: .3px; }
.bot-status { font-size: 11.5px; opacity: .85; display: flex; align-items: center; gap: 5px; }
.status-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: rgba(255,255,255,.4);
  transition: background .3s;
}
.status-dot.active { background: #4ade80; box-shadow: 0 0 0 2px rgba(74,222,128,.3); }
.header-actions { display: flex; gap: 6px; }
.icon-btn {
  width: 32px; height: 32px;
  border: none; background: rgba(255,255,255,.15);
  border-radius: 8px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: #fff; transition: background .2s;
}
.icon-btn:hover { background: rgba(255,255,255,.28); }
.icon-btn svg { width: 17px; height: 17px; }

/* ── Messages ── */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px 8px;
  scroll-behavior: smooth;
}
.messages-area::-webkit-scrollbar { width: 5px; }
.messages-area::-webkit-scrollbar-track { background: transparent; }
.messages-area::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

/* Welcome */
.welcome-screen {
  display: flex; flex-direction: column; align-items: center;
  padding: 36px 20px 16px; text-align: center;
}
.welcome-icon { width: 72px; height: 72px; margin-bottom: 16px; }
.welcome-title {
  font-size: 22px; font-weight: 800;
  background: linear-gradient(135deg, var(--blue-1), var(--blue-2));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  margin: 0 0 8px;
}
.welcome-sub { color: var(--text-2); font-size: 14px; max-width: 320px; line-height: 1.6; margin: 0 0 8px; }
.welcome-location {
  font-size: 12px; color: var(--text-3); margin: 0 0 16px;
  background: var(--blue-3); padding: 4px 12px; border-radius: 20px;
}
.suggestion-chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 12px; }
.chip {
  padding: 7px 14px; border: 1.5px solid var(--blue-1);
  background: transparent; color: var(--blue-1);
  border-radius: 20px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all .2s;
}
.chip:hover { background: var(--blue-1); color: #fff; }

/* Message rows */
.message-list { display: flex; flex-direction: column; gap: 16px; }
.message-row { display: flex; align-items: flex-start; gap: 10px; }
.message-row.user { flex-direction: row-reverse; }
.msg-avatar { width: 28px; height: 28px; flex-shrink: 0; margin-top: 2px; }
.msg-avatar svg { width: 100%; height: 100%; }
.message-content-wrap { display: flex; flex-direction: column; gap: 4px; max-width: 80%; }
.message-row.user .message-content-wrap { align-items: flex-end; }

/* Bubbles */
.bubble {
  padding: 11px 15px;
  border-radius: 18px;
  font-size: 14px; line-height: 1.65;
  word-break: break-word;
  position: relative;
}
.bubble.assistant {
  background: var(--surface);
  border: 1px solid var(--border);
  border-top-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0,0,0,.05);
  color: var(--text-1);
}
.bubble.user {
  background: linear-gradient(135deg, var(--blue-1), #009688);
  color: #fff;
  border-top-right-radius: 4px;
}
.bubble.streaming { border-color: var(--blue-2); }
.bubble.editing { padding: 10px; background: #fff; border: 1.5px solid var(--blue-1); }

.bubble-text :deep(code) {
  background: rgba(26,107,255,.08); color: var(--blue-1);
  padding: 1px 5px; border-radius: 4px; font-size: 12.5px;
  font-family: 'JetBrains Mono', monospace;
}
.bubble-text :deep(strong) { font-weight: 700; }

/* Cursor blink */
.cursor-blink {
  display: inline-block; color: var(--blue-1);
  animation: blink .7s step-end infinite;
}
@keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0; } }

/* Typing */
.typing-bubble {
  padding: 14px 18px !important;
  display: flex; gap: 5px; align-items: center;
}
.dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--blue-2);
  animation: bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,80%,100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }

/* Sources */
.sources-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 0 2px; }
.sources-label { font-size: 11px; color: var(--text-3); font-weight: 600; }
.source-tag {
  padding: 2px 8px; background: var(--blue-3);
  color: var(--blue-1); border-radius: 10px; font-size: 11px; font-weight: 600;
}

/* Meta + Actions */
.msg-meta { display: flex; align-items: center; gap: 10px; padding: 0 2px; }
.timestamp { font-size: 11px; color: var(--text-3); }
.msg-actions { display: flex; gap: 4px; opacity: 0; transition: opacity .2s; }
.message-row:hover .msg-actions { opacity: 1; }
.meta-btn {
  display: flex; align-items: center; gap: 3px;
  padding: 3px 7px; border: 1px solid var(--border);
  background: var(--surface); border-radius: 6px;
  font-size: 11.5px; color: var(--text-2); cursor: pointer;
  transition: all .15s;
}
.meta-btn svg { width: 12px; height: 12px; }
.meta-btn:hover { background: var(--blue-3); border-color: var(--blue-1); color: var(--blue-1); }
.meta-btn.danger:hover { background: #fff0f0; border-color: var(--danger); color: var(--danger); }

/* Edit */
.edit-textarea {
  width: 100%; min-width: 240px;
  border: none; outline: none; resize: none;
  background: transparent; font: inherit; color: var(--text-1);
  font-size: 14px; line-height: 1.5;
}
.edit-actions { display: flex; gap: 8px; margin-top: 8px; justify-content: flex-end; }
.edit-btn {
  padding: 5px 14px; border-radius: 8px; border: none;
  font-size: 12.5px; font-weight: 600; cursor: pointer; transition: all .15s;
}
.edit-btn.save { background: var(--blue-1); color: #fff; }
.edit-btn.save:hover { background: #009688; }
.edit-btn.cancel { background: var(--border); color: var(--text-2); }
.edit-btn.cancel:hover { background: #d0d8e4; }

/* ── Input Area ── */
.input-area {
  padding: 10px 14px 12px;
  background: var(--surface);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.input-wrap {
  display: flex; align-items: flex-end; gap: 8px;
  background: var(--bg);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 8px 8px 8px 14px;
  transition: border-color .2s, box-shadow .2s;
}
.input-wrap.focused {
  border-color: var(--blue-1);
  box-shadow: 0 0 0 3px rgba(26,107,255,.12);
}
.chat-input {
  flex: 1; border: none; outline: none; background: transparent;
  font: inherit; font-size: 14px; color: var(--text-1);
  resize: none; line-height: 1.5; max-height: 140px;
  overflow-y: auto;
}
.chat-input::placeholder { color: var(--text-3); }
.chat-input:disabled { opacity: .6; }
.send-btn {
  width: 36px; height: 36px; flex-shrink: 0;
  border: none; background: var(--border);
  border-radius: 10px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-3); transition: all .2s;
}
.send-btn.active { background: var(--blue-1); color: #fff; box-shadow: 0 2px 8px rgba(26,107,255,.35); }
.send-btn:disabled { cursor: not-allowed; }
.send-btn svg { width: 17px; height: 17px; }
.spin { animation: spin .9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.input-hint { font-size: 11px; color: var(--text-3); margin: 5px 0 0 2px; }

/* ── Transitions ── */
.msg-enter-active { animation: slideIn .25s ease; }
@keyframes slideIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Responsive ── */
@media (max-width: 500px) {
  .message-content-wrap { max-width: 92%; }
  .welcome-title { font-size: 18px; }
  .suggestion-chips { flex-direction: column; align-items: center; }
}
</style>