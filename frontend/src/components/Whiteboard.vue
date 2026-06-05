<template>
  <section class="board-shell">
    <div class="board-toolbar">
      <div class="board-toolbar__group">
        <button
          class="tool-chip"
          :class="{ 'is-active': tool === 'pen' }"
          @click="tool = 'pen'"
        >
          Pencil
        </button>
        <button
          class="tool-chip"
          :class="{ 'is-active': tool === 'eraser' }"
          @click="tool = 'eraser'"
        >
          Eraser
        </button>
      </div>

      <div class="board-toolbar__group">
        <label class="color-picker">
          <span>Color</span>
          <input v-model="strokeColor" type="color" :disabled="tool === 'eraser'" />
        </label>
        <label class="range-picker">
          <span>Width {{ lineWidth }}</span>
          <input v-model="lineWidth" type="range" min="1" max="24" />
        </label>
      </div>

      <button class="ghost-button" @click="clearBoard">Clear</button>
    </div>

    <div class="board-stage">
      <canvas
        ref="board"
        width="1440"
        height="860"
        class="board-canvas"
        @mousedown="startDraw"
        @mousemove="drawing"
        @mouseup="endDraw"
        @mouseleave="endDraw"
      ></canvas>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"

const props = defineProps({ webrtc: Object })
const board = ref(null)
const tool = ref("pen")
const strokeColor = ref("#0f172a")
const lineWidth = ref(4)

let ctx
let drawingFlag = false

onMounted(() => {
  ctx = board.value.getContext("2d")
  applyBrush()

  props.webrtc.onDraw((data) => {
    if (!ctx) return

    if (data.type === "clear") {
      ctx.clearRect(0, 0, board.value.width, board.value.height)
      return
    }

    ctx.save()
    ctx.lineCap = "round"
    ctx.lineJoin = "round"
    ctx.strokeStyle = data.color || "#0f172a"
    ctx.lineWidth = data.lineWidth || 4
    ctx.globalCompositeOperation = data.tool === "eraser" ? "destination-out" : "source-over"

    if (data.type === "start") {
      ctx.beginPath()
      ctx.moveTo(data.x, data.y)
    } else if (data.type === "draw") {
      ctx.lineTo(data.x, data.y)
      ctx.stroke()
    } else if (data.type === "end") {
      ctx.closePath()
    }

    ctx.restore()
  })
})

watch([tool, strokeColor, lineWidth], applyBrush)

function applyBrush() {
  if (!ctx) return
  ctx.lineCap = "round"
  ctx.lineJoin = "round"
  ctx.lineWidth = Number(lineWidth.value)
  ctx.strokeStyle = strokeColor.value
  ctx.globalCompositeOperation = tool.value === "eraser" ? "destination-out" : "source-over"
}

function payload(base) {
  return {
    ...base,
    tool: tool.value,
    color: strokeColor.value,
    lineWidth: Number(lineWidth.value),
  }
}

function startDraw(e) {
  drawingFlag = true
  applyBrush()
  ctx.beginPath()
  ctx.moveTo(e.offsetX, e.offsetY)
  props.webrtc.broadcastDraw(payload({ type: "start", x: e.offsetX, y: e.offsetY }))
}

function drawing(e) {
  if (!drawingFlag) return
  applyBrush()
  ctx.lineTo(e.offsetX, e.offsetY)
  ctx.stroke()
  props.webrtc.broadcastDraw(payload({ type: "draw", x: e.offsetX, y: e.offsetY }))
}

function endDraw() {
  if (!drawingFlag) return
  drawingFlag = false
  ctx.closePath()
  props.webrtc.broadcastDraw(payload({ type: "end" }))
}

function clearBoard() {
  if (!ctx) return
  ctx.clearRect(0, 0, board.value.width, board.value.height)
  props.webrtc.broadcastDraw({ type: "clear" })
}
</script>
