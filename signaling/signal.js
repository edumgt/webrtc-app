import { networkInterfaces } from "node:os"
import { WebSocketServer } from "ws"

const host = process.env.SIGNAL_HOST ?? "0.0.0.0"
const port = Number.parseInt(process.env.SIGNAL_PORT ?? "3001", 10)

const wss = new WebSocketServer({ host, port })

wss.on("connection", ws => {
  ws.on("message", message => {
    wss.clients.forEach(client => {
      if (client !== ws && client.readyState === 1) {
        client.send(message.toString())
      }
    })
  })
})

function getNetworkAddresses() {
  const nets = networkInterfaces()
  const addresses = []

  Object.values(nets).forEach(netList => {
    netList?.forEach(net => {
      if (net.family === "IPv4" && !net.internal) {
        addresses.push(net.address)
      }
    })
  })

  return addresses
}

console.log(`✅ Signaling server listening on ws://${host}:${port}`)
for (const ip of getNetworkAddresses()) {
  console.log(`   ↳ ws://${ip}:${port}`)
}
