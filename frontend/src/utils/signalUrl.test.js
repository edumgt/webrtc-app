import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { buildSignalUrl } from "./signalUrl"

function setWindow({ protocol = "http:", hostname = "localhost", config = {} } = {}) {
  globalThis.window = {
    location: { protocol, hostname },
    __APP_CONFIG__: config,
  }
}

describe("buildSignalUrl", () => {
  beforeEach(() => {
    setWindow()
    vi.stubEnv("VITE_SIGNAL_URL", "")
    vi.stubEnv("VITE_SIGNAL_PORT", "")
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    delete globalThis.window
  })

  it("falls back to current host and default port 3001", () => {
    expect(buildSignalUrl()).toBe("ws://localhost:3001")
  })

  it("uses wss when the page is served over https", () => {
    setWindow({ protocol: "https:", hostname: "app.example.com" })
    expect(buildSignalUrl()).toBe("wss://app.example.com:3001")
  })

  it("prefers a manual override over runtime and build env", () => {
    setWindow({ config: { VITE_SIGNAL_URL: "wss://runtime.example.com" } })
    vi.stubEnv("VITE_SIGNAL_URL", "wss://build.example.com")
    expect(buildSignalUrl("  ws://manual.example.com:9000 ")).toBe("ws://manual.example.com:9000")
  })

  it("prefers runtime config over build-time env", () => {
    setWindow({ config: { VITE_SIGNAL_URL: "wss://runtime.example.com" } })
    vi.stubEnv("VITE_SIGNAL_URL", "wss://build.example.com")
    expect(buildSignalUrl()).toBe("wss://runtime.example.com")
  })

  it("adds the protocol when the env url has none", () => {
    setWindow({ protocol: "https:" })
    vi.stubEnv("VITE_SIGNAL_URL", "lb.example.com:3001")
    expect(buildSignalUrl()).toBe("wss://lb.example.com:3001")
  })

  it("uses runtime VITE_SIGNAL_PORT for the fallback url", () => {
    setWindow({ hostname: "10.0.0.5", config: { VITE_SIGNAL_PORT: "8481" } })
    expect(buildSignalUrl()).toBe("ws://10.0.0.5:8481")
  })
})
