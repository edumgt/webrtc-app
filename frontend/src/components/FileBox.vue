<template>
  <div class="file-shell">
    <h3 class="file-title">File Transfer</h3>

    <!-- Drop zone / file picker -->
    <label
      class="drop-zone"
      :class="{ 'drop-zone--active': dragging, 'drop-zone--selected': selectedFile }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <input type="file" class="drop-zone__input" @change="onPick" />
      <div v-if="!selectedFile" class="drop-zone__placeholder">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
        </svg>
        <span>파일을 끌어다 놓거나 클릭해서 선택</span>
      </div>
      <div v-else class="drop-zone__info">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <div class="drop-zone__name">{{ selectedFile.name }}</div>
        <div class="drop-zone__size">{{ formatSize(selectedFile.size) }}</div>
      </div>
    </label>

    <!-- Send button -->
    <button
      class="send-btn"
      :disabled="!selectedFile || sending"
      @click="sendSelectedFile"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <line x1="22" y1="2" x2="11" y2="13"/>
        <polygon points="22 2 15 22 11 13 2 9 22 2"/>
      </svg>
      {{ sending ? '전송 중…' : '파일 전송' }}
    </button>

    <!-- Progress bar -->
    <div v-if="sending" class="progress-bar">
      <div class="progress-bar__fill" :style="{ width: progress + '%' }"></div>
    </div>

    <!-- Received files -->
    <div v-if="receivedFiles.length" class="received-section">
      <h4 class="received-title">받은 파일</h4>
      <ul class="received-list">
        <li v-for="(file, i) in receivedFiles" :key="i" class="received-item">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <a :href="file.url" :download="file.name" class="received-item__link">{{ file.name }}</a>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"

const props = defineProps({ webrtc: Object })
const receivedFiles = ref([])
const selectedFile = ref(null)
const sending = ref(false)
const dragging = ref(false)
const progress = ref(0)

onMounted(() => {
  props.webrtc.onFile((file) => {
    receivedFiles.value.push(file)
  })
})

function onPick(event) {
  selectedFile.value = event.target.files[0] || null
}

function onDrop(event) {
  dragging.value = false
  selectedFile.value = event.dataTransfer.files[0] || null
}

async function sendSelectedFile() {
  if (!selectedFile.value || sending.value) return
  sending.value = true
  progress.value = 0
  try {
    await props.webrtc.sendFile(selectedFile.value, (p) => {
      progress.value = p
    })
  } finally {
    sending.value = false
    progress.value = 0
    selectedFile.value = null
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B"
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
  return (bytes / (1024 * 1024)).toFixed(1) + " MB"
}
</script>

<style scoped>
.file-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  height: 100%;
  box-sizing: border-box;
}

.file-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, #f1f5f9);
  margin: 0;
}

/* Drop zone */
.drop-zone {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed var(--border, #334155);
  border-radius: 12px;
  padding: 32px 16px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  background: var(--surface-2, #1e293b);
  position: relative;
}

.drop-zone:hover,
.drop-zone--active {
  border-color: var(--accent, #6366f1);
  background: rgba(99, 102, 241, 0.06);
}

.drop-zone--selected {
  border-color: var(--accent, #6366f1);
}

.drop-zone__input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
  width: 100%;
  height: 100%;
}

.drop-zone__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--text-muted, #94a3b8);
  font-size: 13px;
  text-align: center;
  pointer-events: none;
}

.drop-zone__info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  pointer-events: none;
  color: var(--text-primary, #f1f5f9);
}

.drop-zone__name {
  font-weight: 600;
  font-size: 14px;
  word-break: break-all;
  text-align: center;
  max-width: 240px;
}

.drop-zone__size {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
}

/* Send button */
.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: 10px;
  background: var(--accent, #6366f1);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.1s;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.88;
}

.send-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Progress bar */
.progress-bar {
  height: 6px;
  border-radius: 4px;
  background: var(--surface-2, #1e293b);
  overflow: hidden;
}

.progress-bar__fill {
  height: 100%;
  background: var(--accent, #6366f1);
  border-radius: 4px;
  transition: width 0.2s;
}

/* Received files */
.received-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.received-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted, #94a3b8);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.received-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.received-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--surface-2, #1e293b);
  color: var(--text-muted, #94a3b8);
}

.received-item__link {
  color: var(--accent, #6366f1);
  text-decoration: none;
  font-size: 13px;
  word-break: break-all;
}

.received-item__link:hover {
  text-decoration: underline;
}
</style>
