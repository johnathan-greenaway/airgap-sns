# airgap_sns_pico.py - Enhanced with better BLE and Wi-Fi support
import network
import socket
import time
import machine
import ubinascii
import uasyncio as asyncio
import json
import urandom
import gc

# Optional BLE import with better error handling
try:
    from machine import Pin
    import bluetooth
    from ble_advertising import advertising_payload
    from micropython import const
    
    _IRQ_CENTRAL_CONNECT = const(1)
    _IRQ_CENTRAL_DISCONNECT = const(2)
    _IRQ_GATTS_WRITE = const(3)
    
    # Define service
    _AIRGAP_UUID = bluetooth.UUID("81c30e5c-304b-4f1b-b704-68c3baef0e0f")
    _MSG_CHAR = (bluetooth.UUID("3f7b0a8c-2d54-42d2-8e5d-2e2aca6ad550"), 
                 bluetooth.FLAG_WRITE | bluetooth.FLAG_NOTIFY)
    _AIRGAP_SERVICE = (_AIRGAP_UUID, (_MSG_CHAR,))
    
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False

# Generate a unique ID based on Pico's hardware
NODE_ID = ubinascii.hexlify(machine.unique_id()).decode()

# LED for status indication
led = machine.Pin("LED", machine.Pin.OUT)

# Battery level monitor (if available)
try:
    battery_adc = machine.ADC(26)  # Adjust pin as needed
    BATTERY_MONITOR_AVAILABLE = True
except:
    BATTERY_MONITOR_AVAILABLE = False

# Connection types
class ConnectionType:
    WIFI = 0
    BLUETOOTH = 1
    AUDIO = 2
    UNKNOWN = 3

# Connection colors (for future display integration)
CONNECTION_COLORS = {
    ConnectionType.WIFI: 0x0000FF,      # Blue
    ConnectionType.BLUETOOTH: 0x00FF00, # Green
    ConnectionType.AUDIO: 0xFF0000,     # Red
    ConnectionType.UNKNOWN: 0x888888    # Gray
}

# Node status
class NodeStatus:
    ACTIVE = 0
    INACTIVE = 1
    UNKNOWN = 2

# Simple MeshConnection implementation
class MeshConnection:
    def __init__(self, connection_id, source_id, target_id, connection_type=ConnectionType.UNKNOWN):
        self.connection_id = connection_id
        self.source_id = source_id
        self.target_id = target_id
        self.connection_type = connection_type
        self.signal_strength = 100
        self.last_active = time.time()
        self.active = True
        
    def update_activity(self):
        # Connection is considered inactive after 5 minutes of no activity
        self.active = (time.time() - self.last_active) < 300
        return self.active
        
    def to_dict(self):
        return {
            "connection_id": self.connection_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "connection_type": self.connection_type,
            "signal_strength": self.signal_strength,
            "last_active": self.last_active,
            "active": self.active
        }

# Simple MeshNode implementation
class MeshNode:
    def __init__(self, node_id, friendly_name=None):
        self.node_id = node_id
        self.friendly_name = friendly_name or f"pico-{node_id[-4:]}"
        self.battery_level = 100
        self.last_seen = time.time()
        self.status = NodeStatus.UNKNOWN
        self.connections = {}
        
    def update_status(self):
        current_time = time.time()
        if self.last_seen == 0:
            self.status = NodeStatus.UNKNOWN
        elif current_time - self.last_seen < 300:  # 5 minutes
            self.status = NodeStatus.ACTIVE
        else:
            self.status = NodeStatus.INACTIVE
        return self.status
        
    def add_connection(self, connection):
        self.connections[connection.connection_id] = connection
        
    def remove_connection(self, connection_id):
        if connection_id in self.connections:
            del self.connections[connection_id]
            return True
        return False
        
    def to_dict(self):
        return {
            "node_id": self.node_id,
            "friendly_name": self.friendly_name,
            "battery_level": self.battery_level,
            "last_seen": self.last_seen,
            "status": self.status,
            "connections": [conn.to_dict() for conn in self.connections.values()]
        }

# Burst message parsing
def parse_burst(text):
    try:
        if not text.startswith("!!BURST(") or not text.endswith(")!!"):
            return None
            
        params_str = text[8:-3]  # Extract content between !!BURST( and )!!
        params = {}
        for pair in params_str.split(';'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key.strip()] = value.strip()
                
        return params
    except:
        return None

# Create a properly formatted burst message
def create_burst_message(**kwargs):
    params = []
    for key, value in kwargs.items():
        if value is not None:
            params.append(f"{key}={value}")
    return f"!!BURST({';'.join(params)})!!"

# Simple WebSocket client implementation
class WebSocketClient:
    def __init__(self, uri, node_id):
        self.uri = uri
        self.node_id = node_id
        self.websocket = None
        self.connected = False
        self.handlers = {}
        
    async def connect(self):
        try:
            host, port = self._parse_uri(self.uri)
            reader, writer = await asyncio.open_connection(host, port)
            
            # Perform WebSocket handshake
            writer.write(b'GET /ws/%s HTTP/1.1\r\n' % self.node_id.encode())
            writer.write(b'Host: %s\r\n' % host.encode())
            writer.write(b'Upgrade: websocket\r\n')
            writer.write(b'Connection: Upgrade\r\n')
            writer.write(b'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n')
            writer.write(b'Sec-WebSocket-Version: 13\r\n\r\n')
            await writer.drain()
            
            # Read response (simplified - in a real implementation we would parse this)
            response = await reader.read(1024)
            
            self.websocket = (reader, writer)
            self.connected = True
            print(f"Connected to {self.uri} as {self.node_id}")
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False
            
    def _parse_uri(self, uri):
        # Simple URI parser
        if uri.startswith("ws://"):
            uri = uri[5:]
        elif uri.startswith("wss://"):
            uri = uri[6:]
            
        if "/" in uri:
            uri = uri.split("/")[0]
            
        if ":" in uri:
            host, port = uri.split(":")
            return host, int(port)
        else:
            return uri, 80
    
    async def send(self, message):
        if not self.websocket:
            return False
            
        try:
            _, writer = self.websocket
            # Simplified WebSocket framing
            writer.write(b'\x81')  # Text frame
            length = len(message)
            
            if length < 126:
                writer.write(bytes([length]))
            elif length <= 0xFFFF:
                writer.write(b'\x7E')
                writer.write(bytes([length >> 8, length & 0xFF]))
            else:
                writer.write(b'\x7F')
                writer.write(bytes([0, 0, 0, 0, length >> 24, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF]))
                
            writer.write(message.encode())
            await writer.drain()
            return True
        except Exception as e:
            print(f"Send error: {e}")
            self.connected = False
            return False
    
    async def receive(self):
        if not self.websocket:
            return None
            
        try:
            reader, _ = self.websocket
            
            # Simplified WebSocket frame parsing
            frame = await reader.read(2)
            if not frame:
                self.connected = False
                return None
                
            opcode = frame[0] & 0x0F
            mask = (frame[1] & 0x80) != 0
            length = frame[1] & 0x7F
            
            if length == 126:
                length_bytes = await reader.read(2)
                length = (length_bytes[0] << 8) | length_bytes[1]
            elif length == 127:
                length_bytes = await reader.read(8)
                length = 0
                for i in range(8):
                    length = (length << 8) | length_bytes[i]
            
            if mask:
                mask_bytes = await reader.read(4)
            
            data = await reader.read(length)
            
            if mask:
                # Apply mask
                decoded = bytearray(length)
                for i in range(length):
                    decoded[i] = data[i] ^ mask_bytes[i % 4]
                return decoded.decode()
            else:
                return data.decode()
        except Exception as e:
            print(f"Receive error: {e}")
            self.connected = False
            return None
    
    async def listen(self, handler):
        while self.connected:
            message = await self.receive()
            if message:
                await handler(message)
            else:
                break
                
        self.connected = False
        
    async def close(self):
        if self.websocket:
            _, writer = self.websocket
            writer.close()
            await writer.wait_closed()
            self.websocket = None
            self.connected = False

# BLE Server implementation
class BLEServer:
    def __init__(self, name, node_id, message_handler=None):
        if not BLE_AVAILABLE:
            raise RuntimeError("BLE not available")
            
        self.name = name
        self.node_id = node_id
        self.message_handler = message_handler
        self.connected_devices = set()
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq_handler)
        
        # Register services
        ((self.msg_handle,),) = self.ble.gatts_register_services((_AIRGAP_SERVICE,))
        
        # Advertising payload
        self.adv_payload = advertising_payload(
            name=name, 
            services=[_AIRGAP_UUID],
            appearance=0
        )
        
        # Start advertising
        self.advertise()
        
    def _irq_handler(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            # A central has connected to this peripheral
            conn_handle, addr_type, addr = data
            self.connected_devices.add(conn_handle)
            print(f"BLE: Central connected: {addr}")
            
        elif event == _IRQ_CENTRAL_DISCONNECT:
            # A central has disconnected from this peripheral
            conn_handle, addr_type, addr = data
            if conn_handle in self.connected_devices:
                self.connected_devices.remove(conn_handle)
            self.advertise()
            print(f"BLE: Central disconnected: {addr}")
            
        elif event == _IRQ_GATTS_WRITE:
            # A client has written to a characteristic or descriptor
            conn_handle, attr_handle = data
            if attr_handle == self.msg_handle:
                data = self.ble.gatts_read(self.msg_handle)
                if data and self.message_handler:
                    asyncio.create_task(self.message_handler(data.decode()))
    
    def advertise(self):
        self.ble.gap_advertise(100000, self.adv_payload)
        print(f"BLE: Advertising as {self.name}")
    
    def send_message(self, message, conn_handle=None):
        # Encode message
        message_bytes = message.encode()
        
        # Set the message value
        self.ble.gatts_write(self.msg_handle, message_bytes)
        
        # Notify connected devices
        if conn_handle is not None:
            if conn_handle in self.connected_devices:
                self.ble.gatts_notify(conn_handle, self.msg_handle)
                return True
            return False
        else:
            # Notify all connected devices
            success = False
            for handle in self.connected_devices:
                self.ble.gatts_notify(handle, self.msg_handle)
                success = True
            return success
    
    def close(self):
        # Stop advertising
        self.ble.gap_advertise(None)
        self.ble.active(False)

# Airgap SNS Pico client
class AirgapSNSPico:
    def __init__(self, config=None):
        self.config = config or {}
        self.node_id = NODE_ID
        self.friendly_name = self.config.get("friendly_name", f"Pico-{self.node_id[-4:]}")
        self.ws_uri = self.config.get("ws_uri", "ws://localhost:9000/ws/")
        self.ws_client = None
        self.local_node = MeshNode(self.node_id, self.friendly_name)
        self.neighbors = {}
        self.audio_enabled = self.config.get("audio_enabled", False)
        self.ble_enabled = self.config.get("ble_enabled", False) and BLE_AVAILABLE
        self.ble_server = None
        self.wlan = None
        self.running = False
        self.heartbeat_interval = self.config.get("heartbeat_interval", 10)
        self.discovery_interval = self.config.get("discovery_interval", 30)
        self.message_queue = asyncio.Queue(10)  # Buffer for messages
        
    async def connect_wifi(self, ssid, password):
        print(f"Connecting to Wi-Fi: {ssid}...")
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.connect(ssid, password)
        
        # Wait for connection with timeout
        max_wait = 10
        while max_wait > 0:
            if self.wlan.status() < 0 or self.wlan.status() >= 3:
                break
            max_wait -= 1
            print('Waiting for connection...')
            await asyncio.sleep(1)
        
        # Handle connection error
        if self.wlan.status() != 3:
            print('Wi-Fi connection failed')
            return False
        
        status = self.wlan.ifconfig()
        print(f'Connected to Wi-Fi. IP: {status[0]}')
        return True
    
    def setup_ble(self):
        if not self.ble_enabled:
            return False
            
        try:
            self.ble_server = BLEServer(
                name=self.friendly_name,
                node_id=self.node_id,
                message_handler=self.handle_ble_message
            )
            print("BLE server initialized")
            return True
        except Exception as e:
            print(f"BLE setup error: {e}")
            self.ble_enabled = False
            return False
            
    async def handle_ble_message(self, message):
        # Process messages received via BLE
        print(f"BLE message received: {message}")
        # Put in queue for processing
        await self.message_queue.put(("ble", message))
        
    async def connect_ws(self):
        # Create WebSocket client
        self.ws_client = WebSocketClient(self.ws_uri, self.node_id)
        return await self.ws_client.connect()
        
    async def process_message(self, source, message):
        try:
            # Check if it's a burst message
            params = parse_burst(message)
            if params:
                # Process based on message type
                msg_type = params.get("type", "default")
                source_id = params.get("source")
                
                if msg_type == "heartbeat":
                    await self.handle_heartbeat(params, message, source)
                elif msg_type == "discovery":
                    await self.handle_discovery(params, message, source)
                elif msg_type == "node_info":
                    await self.handle_node_info(params, message, source)
                elif msg_type == "relay":
                    await self.handle_relay(params, message, source)
                else:
                    print(f"Received message type {msg_type} from {source}: {message}")
                    
                # Forward to other networks if needed
                if source == "websocket" and self.ble_enabled and self.ble_server:
                    # Forward from WebSocket to BLE
                    self.ble_server.send_message(message)
                elif source == "ble" and self.ws_client and self.ws_client.connected:
                    # Forward from BLE to WebSocket
                    await self.ws_client.send(message)
            else:
                print(f"Received non-burst message from {source}: {message}")
        except Exception as e:
            print(f"Error processing message: {e}")
            
    async def handle_heartbeat(self, params, message, source):
        source_id = params.get("source")
        if source_id and source_id != self.node_id:
            if source_id in self.neighbors:
                # Update last seen time
                self.neighbors[source_id].last_seen = time.time()
            else:
                # Request node info
                await self.request_node_info(source_id)
                
    async def handle_discovery(self, params, message, source):
        source_id = params.get("source")
        if source_id and source_id != self.node_id:
            # Respond with our info
            await self.send_node_info(target=source_id)
            
    async def handle_node_info(self, params, message, source):
        source_id = params.get("source")
        if source_id and source_id != self.node_id:
            try:
                # Extract node info from message
                start = message.find("{")
                end = message.rfind("}")
                if start >= 0 and end > start:
                    node_data = json.loads(message[start:end+1])
                    
                    # Create or update node
                    if source_id in self.neighbors:
                        node = self.neighbors[source_id]
                        node.friendly_name = node_data.get("friendly_name", node.friendly_name)
                        node.battery_level = node_data.get("battery_level", node.battery_level)
                        node.last_seen = time.time()
                    else:
                        node = MeshNode(source_id, node_data.get("friendly_name"))
                        node.battery_level = node_data.get("battery_level", 100)
                        node.last_seen = time.time()
                        self.neighbors[source_id] = node
                        
                    # Create connection if not exists
                    conn_id = f"{self.node_id}-to-{source_id}"
                    conn_type = ConnectionType.BLUETOOTH if source == "ble" else ConnectionType.WIFI
                    
                    if conn_id not in self.local_node.connections:
                        conn = MeshConnection(
                            conn_id, 
                            self.node_id, 
                            source_id, 
                            conn_type
                        )
                        self.local_node.add_connection(conn)
                    else:
                        # Update existing connection
                        self.local_node.connections[conn_id].last_active = time.time()
                        self.local_node.connections[conn_id].active = True
                        
                    print(f"Updated node info for {source_id} via {source}")
            except Exception as e:
                print(f"Error parsing node info: {e}")
                
    async def handle_relay(self, params, message, source):
        target_id = params.get("dest")
        if target_id:
            # Relay to specific target if we know them
            if target_id in self.neighbors:
                conn = self.local_node.connections.get(f"{self.node_id}-to-{target_id}")
                if conn:
                    if conn.connection_type == ConnectionType.BLUETOOTH and self.ble_enabled:
                        self.ble_server.send_message(message)
                    elif conn.connection_type == ConnectionType.WIFI and self.ws_client and self.ws_client.connected:
                        await self.ws_client.send(message)
        
    async def request_node_info(self, target_id):
        message = create_burst_message(
            type="node_info_request",
            source=self.node_id,
            dest=target_id
        )
        await self.send_message(message)
        
    async def send_node_info(self, target=None):
        # Create node info message
        node_data = self.local_node.to_dict()
        node_json = json.dumps(node_data, separators=(',', ':'))  # Compact JSON
        
        message = create_burst_message(
            type="node_info",
            source=self.node_id,
            dest=target or "broadcast"
        )
        
        # Combine message with JSON data
        full_message = f"{node_json} {message}"
        await self.send_message(full_message)
        
    async def send_heartbeat(self):
        message = create_burst_message(
            type="heartbeat",
            source=self.node_id
        )
        await self.send_message(message)
        
    async def send_discovery(self):
        message = create_burst_message(
            type="discovery",
            source=self.node_id
        )
        await self.send_message(message)
        
    async def send_message(self, message):
        success = False
        
        # Send via WebSocket if connected
        if self.ws_client and self.ws_client.connected:
            ws_success = await self.ws_client.send(message)
            success = success or ws_success
            
        # Send via BLE if enabled
        if self.ble_enabled and self.ble_server:
            ble_success = self.ble_server.send_message(message)
            success = success or ble_success
            
        return success
        
    async def update_battery_level(self):
        if BATTERY_MONITOR_AVAILABLE:
            # Read from ADC and convert to percentage
            # This is a simplified example - actual implementation depends on your hardware
            raw = battery_adc.read_u16()
            voltage = raw * 3.3 / 65535
            # Map voltage to percentage (adjust based on your battery)
            percentage = int((voltage - 3.0) * 100 / (4.2 - 3.0))
            percentage = max(0, min(100, percentage))
            self.local_node.battery_level = percentage
            
    async def heartbeat_task(self):
        while self.running:
            led.on()  # Flash LED to indicate heartbeat
            
            # Update battery level
            await self.update_battery_level()
            
            # Send heartbeat
            await self.send_heartbeat()
            
            # Garbage collection to free memory
            gc.collect()
            
            led.off()
            await asyncio.sleep(self.heartbeat_interval)
            
    async def discovery_task(self):
        while self.running:
            # Send discovery message
            await self.send_discovery()
            
            # Update node info
            await self.send_node_info()
            
            # Update node statuses
            self.local_node.update_status()
            for node in self.neighbors.values():
                node.update_status()
                
            # Clean up inactive connections
            inactive_connections = []
            for conn_id, conn in self.local_node.connections.items():
                if not conn.update_activity():
                    inactive_connections.append(conn_id)
                    
            for conn_id in inactive_connections:
                self.local_node.remove_connection(conn_id)
                
            await asyncio.sleep(self.discovery_interval)
    
    async def message_processor_task(self):
        """Process messages from the queue"""
        while self.running:
            try:
                source, message = await self.message_queue.get()
                await self.process_message(source, message)
            except Exception as e:
                print(f"Error processing message from queue: {e}")
            await asyncio.sleep(0.1)  # Small delay to prevent CPU hogging
    
    async def ws_listener_task(self):
        """Listen for WebSocket messages"""
        while self.running and self.ws_client and self.ws_client.connected:
            try:
                message = await self.ws_client.receive()
                if message:
                    await self.message_queue.put(("websocket", message))
                else:
                    # Reconnect if disconnected
                    print("WebSocket disconnected, attempting to reconnect...")
                    await self.connect_ws()
                    await asyncio.sleep(5)  # Wait before trying again
            except Exception as e:
                print(f"WebSocket listener error: {e}")
                await asyncio.sleep(1)
            
    async def run(self):
        self.running = True
        
        # Set up BLE if enabled
        if self.ble_enabled:
            self.setup_ble()
        
        # Create tasks
        tasks = []
        
        # Message processor task
        processor_task = asyncio.create_task(self.message_processor_task())
        tasks.append(processor_task)
        
        # WebSocket listener task if connected
        if self.ws_client and self.ws_client.connected:
            ws_task = asyncio.create_task(self.ws_listener_task())
            tasks.append(ws_task)
        
        # Start heartbeat and discovery tasks
        heartbeat_task = asyncio.create_task(self.heartbeat_task())
        discovery_task = asyncio.create_task(self.discovery_task())
        tasks.append(heartbeat_task)
        tasks.append(discovery_task)
        
        try:
            # Wait for tasks to complete
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            if self.ws_client:
                await self.ws_client.close()
            if self.ble_enabled and self.ble_server:
                self.ble_server.close()
            
    def stop(self):
        self.running = False

# Main function
async def main():
    # Configuration
    config = {
        "friendly_name": "PicoMesh1",
        "ws_uri": "ws://192.168.1.100:9000/ws/",
        "heartbeat_interval": 10,
        "discovery_interval": 30,
        "ble_enabled": True
    }
    
    # Create Airgap SNS Pico client
    client = AirgapSNSPico(config)
    
    # Connect to Wi-Fi
    if not await client.connect_wifi("YOUR_SSID", "YOUR_PASSWORD"):
        print("Failed to connect to Wi-Fi")
        # Continue anyway - we can still use BLE
    
    # Connect to WebSocket server if Wi-Fi connected
    if client.wlan and client.wlan.isconnected():
        if not await client.connect_ws():
            print("Failed to connect to server")
            # Continue anyway - we can still use BLE
    
    # Run client
    try:
        await client.run()cl
    except KeyboardInterrupt:
        print("Interrupted by user")                           
    finally:
        client.stop()

# Entry point
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
        machine.reset()  # Reset the Pico on unhandled exception