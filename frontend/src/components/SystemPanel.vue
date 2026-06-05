<template>
  <section class="system-shell">
    <div class="system-grid">
      <article class="system-card">
        <p class="system-card__eyebrow">Room</p>
        <h3>{{ webrtc.activeRoomId || "Not joined" }}</h3>
        <p>현재 세션이 사용 중인 방 식별자입니다.</p>
      </article>

      <article class="system-card">
        <p class="system-card__eyebrow">Signal Server</p>
        <h3 class="system-card__break">{{ webrtc.signalUrl || "Not set" }}</h3>
        <p>브라우저가 현재 붙으려는 WebSocket signaling 대상입니다.</p>
      </article>

      <article class="system-card">
        <p class="system-card__eyebrow">Transport</p>
        <h3>{{ transportLabel }}</h3>
        <p>현재 접속 URL 기준으로 추정한 signaling transport 입니다.</p>
      </article>

      <article class="system-card">
        <p class="system-card__eyebrow">Peers</p>
        <h3>{{ webrtc.peerCount }}</h3>
        <p>활성 RTCPeerConnection 수와 원격 스트림 상태를 추적합니다.</p>
      </article>
    </div>

    <div class="system-analysis">
      <article class="system-panel">
        <div class="system-panel__header">
          <div>
            <p class="system-card__eyebrow">Signal Usage</p>
            <h3>Runtime Status</h3>
          </div>
          <span class="system-badge" :data-state="webrtc.connectionState">{{ webrtc.connectionState }}</span>
        </div>
        <ul class="system-list">
          <li>Connection: {{ webrtc.connectionState }}</li>
          <li>Remote Streams: {{ webrtc.remoteStreams.length }}</li>
          <li>Recent Logs: {{ webrtc.eventLogs.length }}</li>
          <li>Signal Protocol: {{ transportLabel }}</li>
        </ul>
      </article>

      <article class="system-panel">
        <div class="system-panel__header">
          <div>
            <p class="system-card__eyebrow">CloudWatch Analysis</p>
            <h3>Admin Insight</h3>
          </div>
          <button class="ghost-button" @click="refreshCloudWatchData">Refresh</button>
        </div>
        <ul class="system-list">
          <li>{{ analysis.summary }}</li>
          <li>{{ analysis.signal }}</li>
          <li>{{ analysis.ice }}</li>
          <li>{{ analysis.sdp }}</li>
        </ul>
        <p class="system-panel__hint">
          {{ cloudWatchStatus }}
        </p>
      </article>
    </div>

    <div class="system-chart-grid">
      <article class="system-panel">
        <div class="system-panel__header">
          <div>
            <p class="system-card__eyebrow">Resource Distribution</p>
            <h3>Service Error Share</h3>
          </div>
        </div>
        <apexchart
          type="donut"
          height="300"
          :options="resourceChartOptions"
          :series="resourceSeries"
        />
      </article>

      <article class="system-panel">
        <div class="system-panel__header">
          <div>
            <p class="system-card__eyebrow">Time Series</p>
            <h3>CloudWatch Volume Trend</h3>
          </div>
        </div>
        <apexchart
          type="area"
          height="300"
          :options="timelineChartOptions"
          :series="timelineSeriesData"
        />
      </article>

      <article class="system-panel">
        <div class="system-panel__header">
          <div>
            <p class="system-card__eyebrow">Radar</p>
            <h3>Operational Readiness</h3>
          </div>
        </div>
        <apexchart
          type="radar"
          height="300"
          :options="radarChartOptions"
          :series="radarSeries"
        />
      </article>
    </div>

    <article class="system-panel">
      <div class="system-panel__header">
        <div>
          <p class="system-card__eyebrow">Event Stream</p>
          <h3>Recent WebRTC Logs</h3>
        </div>
      </div>
      <div class="log-table">
        <div v-for="entry in recentLogRows" :key="entry.id" class="log-row">
          <span class="log-row__scope">{{ entry.scope }}</span>
          <div class="log-row__body">
            <strong>{{ entry.message }}</strong>
            <p>{{ entry.createdAt }}</p>
            <pre v-if="entry.details">{{ JSON.stringify(entry.details, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import VueApexCharts from "vue3-apexcharts"

const props = defineProps({
  webrtc: { type: Object, required: true },
})

const apexchart = VueApexCharts
const cloudWatchPayload = ref(null)
const cloudWatchRecent = ref([])
const cloudWatchStatus = ref("CloudWatch API not queried yet. Showing frontend-derived sample data.")

const transportLabel = computed(() => {
  if (props.webrtc.signalUrl?.startsWith("wss://")) return "WSS / 443-style secure WebSocket"
  if (props.webrtc.signalUrl?.startsWith("ws://")) return "WS / explicit WebSocket"
  return "Unknown"
})

const analysis = computed(() => {
  const logs = recentLogRows.value || []
  const hasSignalOpen = logs.some(entry => entry.message.includes("WebSocket connected"))
  const hasOffer = logs.some(entry => entry.message.includes("offer"))
  const hasAnswer = logs.some(entry => entry.message.includes("answer"))
  const hasIce = logs.some(entry => entry.scope === "ice" || entry.message.includes("ICE"))

  return {
    summary: hasSignalOpen
      ? "Signal channel is opening successfully from the browser."
      : "Signal open log is missing. Check LoadBalancer, DNS, or WebSocket endpoint reachability.",
    signal: hasOffer || hasAnswer
      ? "SDP signaling messages are flowing through the room."
      : "SDP exchange logs are missing. Check join-room delivery and signaling relay logs in CloudWatch.",
    ice: hasIce
      ? "ICE candidates are being generated or received."
      : "ICE activity is missing. Inspect STUN/TURN reachability and browser network restrictions.",
    sdp: hasOffer && hasAnswer
      ? "Offer/Answer pair detected. Media negotiation likely reached peer setup phase."
      : "Offer/Answer pair incomplete. Compare frontend event order with signaling pod logs in CloudWatch.",
  }
})

const fallbackTimeseriesSeries = computed(() => {
  const recentLogs = [...(props.webrtc.eventLogs || [])].slice(0, 12).reverse()
  const signalPoints = recentLogs.map((entry, index) => [
    new Date(Date.now() - (recentLogs.length - index) * 5 * 60 * 1000).toISOString(),
    entry.scope === "signal" ? 1 : 0,
  ])
  const icePoints = recentLogs.map((entry, index) => [
    new Date(Date.now() - (recentLogs.length - index) * 5 * 60 * 1000).toISOString(),
    entry.scope === "ice" ? 1 : 0,
  ])
  const sdpPoints = recentLogs.map((entry, index) => [
    new Date(Date.now() - (recentLogs.length - index) * 5 * 60 * 1000).toISOString(),
    entry.scope === "sdp" ? 1 : 0,
  ])

  return [
    { name: "frontend_signal", data: signalPoints },
    { name: "signaling_ice", data: icePoints },
    { name: "signaling_sdp", data: sdpPoints },
  ]
})

const timeseriesSource = computed(() => cloudWatchPayload.value?.series?.length ? cloudWatchPayload.value.series : fallbackTimeseriesSeries.value)

const resourceSeries = computed(() => {
  const frontendErrors = timeseriesSource.value
    .filter(item => item.name.includes("frontend"))
    .reduce((sum, item) => sum + item.data.reduce((acc, [, value]) => acc + value, 0), 0)
  const signalingErrors = timeseriesSource.value
    .filter(item => item.name.includes("signaling") || item.name.includes("ice") || item.name.includes("sdp"))
    .reduce((sum, item) => sum + item.data.reduce((acc, [, value]) => acc + value, 0), 0)
  const localWarnings = Math.max(props.webrtc.eventLogs.length, 1)

  return [
    Math.max(frontendErrors, 1),
    Math.max(signalingErrors, 1),
    Math.max(Math.min(localWarnings, 24), 1),
  ]
})

const resourceChartOptions = computed(() => ({
  chart: {
    toolbar: { show: false },
    background: "transparent",
  },
  labels: ["frontend_errors", "signaling_errors", "frontend_event_buffer"],
  colors: ["#0058a3", "#ffda1a", "#0f766e"],
  legend: {
    position: "bottom",
    fontFamily: "Segoe UI, Noto Sans KR, sans-serif",
  },
  stroke: { colors: ["#ffffff"] },
  dataLabels: { enabled: true },
}))

const timelineChartOptions = computed(() => ({
  chart: {
    toolbar: { show: false },
    background: "transparent",
    zoom: { enabled: false },
  },
  colors: ["#0058a3", "#0f766e", "#ff9900"],
  dataLabels: { enabled: false },
  stroke: { curve: "smooth", width: 3 },
  fill: {
    type: "gradient",
    gradient: {
      shadeIntensity: 1,
      opacityFrom: 0.3,
      opacityTo: 0.06,
    },
  },
  xaxis: {
    type: "datetime",
    labels: { datetimeUTC: false, style: { colors: "#64748b" } },
  },
  yaxis: {
    min: 0,
    labels: { style: { colors: "#64748b" } },
  },
  grid: {
    borderColor: "rgba(148, 163, 184, 0.18)",
  },
  legend: {
    position: "top",
    horizontalAlign: "left",
    fontFamily: "Segoe UI, Noto Sans KR, sans-serif",
  },
}))

const timelineSeriesData = computed(() => {
  return timeseriesSource.value.map((item) => ({
    name: item.name,
    data: item.data.map(([timestamp, value]) => ({
      x: new Date(timestamp).getTime(),
      y: value,
    })),
  }))
})

const radarSeries = computed(() => [{
  name: "Operational Score",
  data: [
    props.webrtc.connectionState === "connected" ? 88 : 42,
    cloudWatchPayload.value?.series?.length ? 92 : 38,
    props.webrtc.peerCount > 0 ? 74 : 30,
    props.webrtc.remoteStreams.length > 0 ? 80 : 28,
    recentLogRows.value.some(entry => entry.scope === "ice" || entry.message.includes("ICE")) ? 76 : 34,
    recentLogRows.value.some(entry => entry.scope === "sdp" || entry.message.includes("offer") || entry.message.includes("answer")) ? 82 : 36,
  ],
}])

const radarChartOptions = computed(() => ({
  chart: {
    toolbar: { show: false },
    background: "transparent",
  },
  xaxis: {
    categories: ["Signal", "CloudWatch API", "Peers", "Media", "ICE", "SDP"],
    labels: {
      style: {
        colors: ["#475569", "#475569", "#475569", "#475569", "#475569", "#475569"],
        fontFamily: "Segoe UI, Noto Sans KR, sans-serif",
      },
    },
  },
  yaxis: {
    show: false,
    min: 0,
    max: 100,
  },
  fill: {
    opacity: 0.24,
    colors: ["#7c3aed"],
  },
  stroke: {
    width: 2,
    colors: ["#7c3aed"],
  },
  markers: {
    size: 4,
    colors: ["#7c3aed"],
  },
}))

const recentLogRows = computed(() => {
  if (cloudWatchRecent.value.length) {
    return cloudWatchRecent.value.map((entry, index) => ({
      id: `cw-${index}-${entry.timestamp || entry.createdAt || index}`,
      scope: entry.service || "cloudwatch",
      message: entry.event || entry.message || "recent_log",
      createdAt: entry.timestamp || entry.createdAt || new Date().toISOString(),
      details: entry,
    }))
  }

  return props.webrtc.eventLogs || []
})

async function refreshCloudWatchData() {
  try {
    cloudWatchStatus.value = "Loading CloudWatch-style JSON from /api/log-timeseries and /api/log-recent..."

    const [timeseriesResponse, recentResponse] = await Promise.all([
      fetch("/api/log-timeseries?rangeMinutes=60&binMinutes=5"),
      fetch("/api/log-recent?limit=20"),
    ])

    if (!timeseriesResponse.ok || !recentResponse.ok) {
      throw new Error(`HTTP ${timeseriesResponse.status}/${recentResponse.status}`)
    }

    cloudWatchPayload.value = await timeseriesResponse.json()
    const recentPayload = await recentResponse.json()
    cloudWatchRecent.value = recentPayload.recentLogs || recentPayload.logs || []
    cloudWatchStatus.value = "CloudWatch API payload connected. Charts are rendered from backend JSON."
  } catch (error) {
    cloudWatchPayload.value = null
    cloudWatchRecent.value = []
    cloudWatchStatus.value = "CloudWatch API unavailable. Falling back to frontend-derived sample metrics."
    console.warn("[SystemPanel] CloudWatch API fetch failed", error)
  }
}

onMounted(() => {
  refreshCloudWatchData()
})
</script>
