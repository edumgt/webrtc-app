function getWebSocketProtocol() {
  return window.location.protocol === "https:" ? "wss" : "ws"
}

function getRuntimeConfig() {
  return window.__APP_CONFIG__ || {}
}

export function buildSignalUrl(overrideSignalUrl = "") {
  const manualUrl = overrideSignalUrl?.trim()
  const runtimeEnvUrl = getRuntimeConfig().VITE_SIGNAL_URL?.trim()
  const buildEnvUrl = import.meta.env.VITE_SIGNAL_URL?.trim()
  const envUrl = manualUrl || runtimeEnvUrl || buildEnvUrl

  if (envUrl) {
    if (envUrl.startsWith("ws://") || envUrl.startsWith("wss://")) {
      return envUrl
    }

    return `${getWebSocketProtocol()}://${envUrl}`
  }

  const host = window.location.hostname || "localhost"
  const port = getRuntimeConfig().VITE_SIGNAL_PORT || import.meta.env.VITE_SIGNAL_PORT || "3001"
  return `${getWebSocketProtocol()}://${host}:${port}`
}
