<template>
  <div class="app-shell">
    <!-- Backdrop (both drawers share one) -->
    <div
      class="backdrop"
      :class="{ show: leftOpen || rightOpen }"
      @click="leftOpen = false; rightOpen = false"
    ></div>

    <!-- Left Offcanvas: Navigation -->
    <aside class="drawer drawer--left" :class="{ open: leftOpen }">
      <div class="drawer__header">
        <div class="brand">
          <span class="brand__logo">◈</span>
          <span class="brand__name">WebRTC Studio</span>
        </div>
        <button class="icon-btn" @click="leftOpen = false" aria-label="Close navigation">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <nav class="nav">
        <button
          v-for="item in menuItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: activePanel === item.key }"
          @click="selectPanel(item.key)"
        >
          <span class="nav-item__icon" v-html="item.icon"></span>
          <div class="nav-item__text">
            <span class="nav-item__label">{{ item.label }}</span>
            <span class="nav-item__caption">{{ item.caption }}</span>
          </div>
        </button>
      </nav>
    </aside>

    <!-- Right Offcanvas: Connection -->
    <aside class="drawer drawer--right" :class="{ open: rightOpen }">
      <div class="drawer__header">
        <span class="drawer__title">Connection</span>
        <button class="icon-btn" @click="rightOpen = false" aria-label="Close connection">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div class="conn-panel">
        <div class="conn-status" :data-state="webrtc.connectionState">
          <span class="conn-status__dot"></span>
          {{ connectionLabel }}
        </div>

        <div class="field">
          <label class="field__label">Signal Server</label>
          <input
            v-model="signalServerUrl"
            placeholder="ws://localhost:8481"
            class="field__input"
          />
        </div>

        <div class="field">
          <label class="field__label">Room ID</label>
          <input
            v-model="roomId"
            placeholder="Enter room id"
            class="field__input"
            @keyup.enter="joinCurrentRoom"
          />
        </div>

        <button class="join-btn" @click="joinCurrentRoom">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>
          </svg>
          Join Room
        </button>

        <p v-if="webrtc.connectionError" class="conn-error">{{ webrtc.connectionError }}</p>

        <p class="conn-hint">{{ webrtc.signalUrl || "No signal server set" }}</p>
      </div>
    </aside>

    <!-- Fixed Topbar -->
    <header class="topbar">
      <button class="icon-btn icon-btn--menu" @click="leftOpen = !leftOpen" aria-label="Open navigation">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 12h18M3 6h18M3 18h18"/>
        </svg>
      </button>

      <div class="topbar__center">
        <span class="topbar__title">{{ activePanelTitle }}</span>
      </div>

      <button
        class="icon-btn icon-btn--conn"
        :class="webrtc.connectionState"
        @click="rightOpen = !rightOpen"
        aria-label="Connection settings"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01"/>
        </svg>
      </button>
    </header>

    <!-- Fixed Footer -->
    <footer class="app-footer">
      <span>(주)에듀엠지티</span>
      <span class="app-footer__sep">·</span>
      <a href="https://www.edumgt.co.kr" target="_blank" rel="noopener">www.edumgt.co.kr</a>
    </footer>

    <!-- Main Content -->
    <main class="main">
      <Whiteboard v-if="activePanel === 'drawing'" :webrtc="webrtc" />
      <ChatBox v-else-if="activePanel === 'chat'" :webrtc="webrtc" />
      <FileBox v-else-if="activePanel === 'files'" :webrtc="webrtc" />
      <MediaPanel
        v-else-if="activePanel === 'video' || activePanel === 'screen'"
        :webrtc="webrtc"
        :local-stream="webrtc.localStream"
        :remote-streams="webrtc.remoteStreams"
        @start-camera="webrtc.startCameraShare"
        @stop-camera="webrtc.stopCameraShare"
        @start-screen="webrtc.startScreenShare"
        @stop-screen="webrtc.stopScreenShare"
      />
      <SystemPanel v-else-if="activePanel === 'system'" :webrtc="webrtc" />
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from "vue"
import ChatBox from "./components/ChatBox.vue"
import FileBox from "./components/FileBox.vue"
import MediaPanel from "./components/MediaPanel.vue"
import SystemPanel from "./components/SystemPanel.vue"
import Whiteboard from "./components/Whiteboard.vue"
import useWebRTC from "./composables/useWebRTC"

const roomId = ref("")
const joined = ref(false)
const activePanel = ref("drawing")
const leftOpen = ref(false)
const rightOpen = ref(false)

const { joinRoom, webrtc } = useWebRTC(roomId, joined)
const signalServerUrl = ref(webrtc.signalUrl)

const menuItems = [
  {
    key: "drawing",
    label: "Drawing",
    caption: "Shared whiteboard",
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`,
  },
  {
    key: "chat",
    label: "Chat",
    caption: "Room messaging",
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  },
  {
    key: "files",
    label: "Files",
    caption: "Send & receive",
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`,
  },
  {
    key: "video",
    label: "Video",
    caption: "Camera share",
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>`,
  },
  {
    key: "screen",
    label: "Screen",
    caption: "PC screen share",
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>`,
  },
  {
    key: "system",
    label: "System",
    caption: "Admin & logs",
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
  },
]

const activePanelTitle = computed(
  () => menuItems.find(item => item.key === activePanel.value)?.label || "Studio"
)

const connectionLabel = computed(() => {
  const map = { idle: "Idle", connecting: "Connecting…", connected: "Connected", error: "Error", closed: "Closed" }
  return map[webrtc.connectionState] || webrtc.connectionState
})

function joinCurrentRoom() {
  joinRoom(signalServerUrl.value)
  rightOpen.value = false
}

function selectPanel(panelKey) {
  activePanel.value = panelKey
  leftOpen.value = false
}
</script>
