<template>
  <div class="file-shell">
    <h3 class="font-bold mb-2">File Transfer</h3>
    <input type="file" @change="sendFile" class="mb-3 block w-full"/>
    <ul class="space-y-2">
      <li v-for="(file, i) in receivedFiles" :key="i">
        <a :href="file.url" :download="file.name" class="text-blue-600 underline">
          {{ file.name }}
        </a>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"

const props = defineProps({ webrtc: Object })
const receivedFiles = ref([])

onMounted(() => {
  props.webrtc.onFile((file) => {
    receivedFiles.value.push(file)
  })
})

function sendFile(event) {
  const file = event.target.files[0]
  if (!file) return
  props.webrtc.sendFile(file)
}
</script>
