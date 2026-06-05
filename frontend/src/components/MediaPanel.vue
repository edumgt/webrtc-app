<template>
  <div class="media-panel" :class="{ 'media-panel--compact': compact }">
    <div class="media-panel__actions">
      <button class="primary-button" @click="$emit('start-camera')">Start Camera</button>
      <button class="ghost-button" @click="$emit('stop-camera')">Stop Camera</button>
      <button class="primary-button primary-button--secondary" @click="$emit('start-screen')">Share Screen</button>
      <button class="ghost-button" @click="$emit('stop-screen')">Stop Screen</button>
    </div>

    <div class="media-panel__grid">
      <article class="stream-card">
        <div class="stream-card__header">
          <div>
            <p class="stream-card__eyebrow">Local</p>
            <h4>Your stream</h4>
          </div>
          <span class="stream-card__badge" :class="{ 'is-live': !!localStream }">
            {{ localStream ? "Live" : "Idle" }}
          </span>
        </div>
        <video ref="localVideoRef" autoplay playsinline muted class="stream-card__video"></video>
      </article>

      <article
        v-for="stream in remoteStreams"
        :key="stream.id"
        class="stream-card"
      >
        <div class="stream-card__header">
          <div>
            <p class="stream-card__eyebrow">Remote</p>
            <h4>{{ stream.label }}</h4>
          </div>
          <span class="stream-card__badge is-live">Live</span>
        </div>
        <video
          :ref="element => setRemoteVideoRef(stream.id, element)"
          autoplay
          playsinline
          class="stream-card__video"
        ></video>
      </article>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from "vue"

const props = defineProps({
  localStream: { type: Object, default: null },
  remoteStreams: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
  webrtc: { type: Object, default: null },
})

defineEmits(["start-camera", "stop-camera", "start-screen", "stop-screen"])

const localVideoRef = ref(null)
const remoteVideoRefs = new Map()

function setRemoteVideoRef(streamId, element) {
  if (!element) {
    remoteVideoRefs.delete(streamId)
    return
  }

  remoteVideoRefs.set(streamId, element)
  bindRemoteStream(streamId)
}

function bindRemoteStream(streamId) {
  const target = remoteVideoRefs.get(streamId)
  const stream = props.remoteStreams.find(item => item.id === streamId)?.stream

  if (target && stream && target.srcObject !== stream) {
    target.srcObject = stream
  }
}

watch(
  () => props.localStream,
  stream => {
    if (localVideoRef.value && localVideoRef.value.srcObject !== stream) {
      localVideoRef.value.srcObject = stream || null
    }
  },
  { immediate: true }
)

onMounted(() => {
  if (localVideoRef.value && props.localStream) {
    localVideoRef.value.srcObject = props.localStream
  }
})

watch(
  () => props.remoteStreams,
  async streams => {
    await nextTick()
    streams.forEach(item => bindRemoteStream(item.id))
  },
  { immediate: true, deep: true }
)
</script>
