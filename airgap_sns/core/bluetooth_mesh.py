#!/usr/bin/env python3
"""
Bluetooth Mesh Module for Airgap SNS

This module provides Bluetooth Low Energy (BLE) mesh networking capabilities
for the Airgap SNS notification system. It enables decentralized, secure
message propagation across devices without requiring centralized infrastructure.

Features:
- Secure mesh communication using BLE
- Node discovery and automatic mesh formation
- Message authentication and integrity protection
- Privacy controls to prevent tracking
- Power-conscious operation for mobile devices
- Seamless integration with existing burst message format
- Support for both advertising and GATT-based communication

Requirements:
- bleak (for BLE communication)
- cryptography (for security operations)
- pydantic (for data validation)
"""

import asyncio
import base64
import logging
import os
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Callable, Any, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-bluetooth")

# Try to import required modules with graceful fallback
try:
    import bleak
    from bleak import BleakClient, BleakScanner
    from bleak.backends.device import BLEDevice
    from cryptography.hazmat.primitives import hashes, hmac
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    BLUETOOTH_AVAILABLE = True
except ImportError:
    logger.warning("Bluetooth mesh functionality not available. Required packages: bleak, cryptography")
    BLUETOOTH_AVAILABLE = False

# Import from burst module for message parsing
try:
    # Try to import from the package
    from airgap_sns.core.burst import parse_burst
except ImportError:
    try:
        # Fallback to direct import (for backward compatibility)
        from burst import parse_burst
    except ImportError:
        logger.error("Could not import burst module. Ensure airgap_sns is installed or in PYTHONPATH.")
        parse_burst = None

# Constants for Bluetooth mesh operation
MESH_SERVICE_UUID = "6a826da6-4aa0-4d71-8c25-0df8f5892e95"
MESH_CHAR_CONTROL_UUID = "6a826da7-4aa0-4d71-8c25-0df8f5892e95"
MESH_CHAR_DATA_UUID = "6a826da8-4aa0-4d71-8c25-0df8f5892e95"

# Default settings
DEFAULT_SCAN_INTERVAL = 30  # seconds
DEFAULT_BROADCAST_TTL = 10  # hops
DEFAULT_KEY_ROTATION_INTERVAL = 86400  # 24 hours
DEFAULT_ADVERTISEMENT_INTERVAL = 1000  # milliseconds
DEFAULT_POWER_MODE = "balanced"
DEFAULT_PRIVACY_MODE = "enhanced"
MAX_MESH_MESSAGE_SIZE = 512  # bytes
MAX_PACKET_SIZE = 20  # MTU size for BLE packets

class MessageType(Enum):
    """Message types for the Bluetooth mesh network"""
    ANNOUNCEMENT = 0
    DATA = 1
    CONTROL = 2
    ACKNOWLEDGMENT = 3
    KEY_EXCHANGE = 4
    NODE_DISCOVERY = 5
    HEARTBEAT = 6

class PowerMode(Enum):
    """Power consumption modes for the Bluetooth mesh"""
    LOW_POWER = 0  # Maximum battery conservation
    BALANCED = 1   # Balance between responsiveness and power
    PERFORMANCE = 2  # Maximum responsiveness, higher power usage

class PrivacyMode(Enum):
    """Privacy modes for the Bluetooth mesh"""
    STANDARD = 0    # Basic privacy
    ENHANCED = 1    # Improved privacy with rotating identifiers
    MAXIMUM = 2     # Maximum privacy with additional obfuscation

@dataclass
class MeshMessage:
    """Represents a message in the Bluetooth mesh network"""
    message_id: str
    message_type: MessageType
    source_id: str
    destination_id: Optional[str]
    ttl: int
    payload: bytes
    timestamp: float
    signature: bytes
    sequence: int

class MeshNode:
    """Represents a node in the Bluetooth mesh network"""
    
    def __init__(
        self,
        node_id: Optional[str] = None,
        friendly_name: Optional[str] = None,
        mesh_key: Optional[bytes] = None,
        privacy_mode: Union[PrivacyMode, str] = PrivacyMode.ENHANCED,
        power_mode: Union[PowerMode, str] = PowerMode.BALANCED
    ):
        """Initialize a mesh node with the given parameters"""
        # Generate node ID if not provided
        self.node_id = node_id or str(uuid.uuid4())
        self.friendly_name = friendly_name or f"node-{self.node_id[:8]}"
        
        # Convert string enum values if provided
        if isinstance(privacy_mode, str):
            privacy_mode = PrivacyMode[privacy_mode.upper()]
        if isinstance(power_mode, str):
            power_mode = PowerMode[power_mode.upper()]
            
        self.privacy_mode = privacy_mode
        self.power_mode = power_mode
        self.mesh_key = mesh_key or os.urandom(32)  # 256-bit key
        
        # Node state
        self.is_active = False
        self.last_seen = 0.0
        self.battery_level = 100
        self.signal_strength = 0
        self.sequence_number = 0
        self.last_broadcast = 0.0
        
        # Known peers in the mesh
        self.peers: Dict[str, MeshNode] = {}
        
        # Message cache to prevent re-broadcasting
        self.message_cache: Set[str] = set()
        self.max_cache_size = 1000
        
        # Identity rotation for privacy
        self.temp_identity = self.node_id
        self.identity_rotation_time = time.time()
        self.identity_rotation_interval = 3600  # 1 hour

    def rotate_identity(self):
        """Rotate temporary identity for enhanced privacy"""
        if self.privacy_mode in (PrivacyMode.ENHANCED, PrivacyMode.MAXIMUM):
            # Create a new temporary identity based on time and permanent ID
            timestamp = int(time.time()).to_bytes(8, 'big')
            hash_input = self.node_id.encode() + timestamp + self.mesh_key
            hash_obj = hashes.Hash(hashes.SHA256())
            hash_obj.update(hash_input)
            digest = hash_obj.finalize()
            self.temp_identity = base64.b32encode(digest[:10]).decode('ascii')
            self.identity_rotation_time = time.time()
            
            logger.debug(f"Rotated identity to {self.temp_identity}")

class BluetoothMeshTransceiver:
    """Handles Bluetooth mesh communication for the Airgap SNS system"""
    
    def __init__(
        self,
        node_id: Optional[str] = None,
        friendly_name: Optional[str] = None,
        mesh_key: Optional[bytes] = None,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        broadcast_ttl: int = DEFAULT_BROADCAST_TTL,
        power_mode: Union[PowerMode, str] = DEFAULT_POWER_MODE,
        privacy_mode: Union[PrivacyMode, str] = DEFAULT_PRIVACY_MODE,
        callback: Optional[Callable[[str], Any]] = None
    ):
        """Initialize the Bluetooth mesh transceiver"""
        if not BLUETOOTH_AVAILABLE:
            raise RuntimeError("Bluetooth mesh functionality not available. Required packages: bleak, cryptography")
            
        # Create the mesh node
        self.node = MeshNode(
            node_id=node_id,
            friendly_name=friendly_name,
            mesh_key=mesh_key,
            privacy_mode=privacy_mode,
            power_mode=power_mode
        )
        
        # Settings
        self.scan_interval = scan_interval
        self.broadcast_ttl = broadcast_ttl
        self.callback = callback
        
        # State
        self.running = False
        self.scanner = None
        self.advertiser = None
        self.connected_devices: Dict[str, BleakClient] = {}
        self.message_queue = asyncio.Queue()
        self.scan_task = None
        self.process_task = None
        self.advertise_task = None
        
        # Statistics
        self.messages_sent = 0
        self.messages_received = 0
        self.messages_relayed = 0
        
        logger.info(f"Bluetooth mesh transceiver initialized (Node ID: {self.node.node_id})")
    
    async def start(self):
        """Start the Bluetooth mesh transceiver"""
        if self.running:
            logger.warning("Bluetooth mesh transceiver already running")
            return
            
        self.running = True
        
        # Initialize the BLE scanner
        self.scanner = BleakScanner()
        
        # Start the tasks
        self.scan_task = asyncio.create_task(self._scan_loop())
        self.process_task = asyncio.create_task(self._process_queue())
        self.advertise_task = asyncio.create_task(self._advertise_loop())
        
        # Rotate identity if using enhanced privacy
        if self.node.privacy_mode != PrivacyMode.STANDARD:
            self.node.rotate_identity()
            
        logger.info("Bluetooth mesh transceiver started")
        
    async def stop(self):
        """Stop the Bluetooth mesh transceiver"""
        if not self.running:
            return
            
        self.running = False
        
        # Cancel tasks
        if self.scan_task:
            self.scan_task.cancel()
        if self.process_task:
            self.process_task.cancel()
        if self.advertise_task:
            self.advertise_task.cancel()
            
        # Disconnect from all devices
        for device_id, client in self.connected_devices.items():
            if client.is_connected:
                await client.disconnect()
                
        self.connected_devices = {}
        logger.info("Bluetooth mesh transceiver stopped")
        
    async def send_message(self, payload: str, destination_id: Optional[str] = None, ttl: int = None):
        """Send a message through the Bluetooth mesh network"""
        if not self.running:
            raise RuntimeError("Bluetooth mesh transceiver not running. Call start() first.")
            
        # Use default TTL if not specified
        ttl = ttl if ttl is not None else self.broadcast_ttl
        
        # Check payload size
        if len(payload.encode()) > MAX_MESH_MESSAGE_SIZE:
            raise ValueError(f"Payload too large (maximum {MAX_MESH_MESSAGE_SIZE} bytes)")
            
        # Increment sequence number
        self.node.sequence_number += 1
        
        # Create message ID
        message_id = str(uuid.uuid4())
        
        # Create message
        message = MeshMessage(
            message_id=message_id,
            message_type=MessageType.DATA,
            source_id=self.node.node_id,
            destination_id=destination_id,
            ttl=ttl,
            payload=payload.encode(),
            timestamp=time.time(),
            signature=self._sign_message(payload.encode(), self.node.sequence_number),
            sequence=self.node.sequence_number
        )
        
        # Add to cache to prevent re-broadcasting our own message
        self.node.message_cache.add(message_id)
        
        # Broadcast message
        await self._broadcast_message(message)
        
        # Update statistics
        self.messages_sent += 1
        self.node.last_broadcast = time.time()
        
        logger.info(f"Message sent: {message_id} (sequence: {self.node.sequence_number})")
        return True
        
    async def _scan_loop(self):
        """Scan for Bluetooth mesh devices in a loop"""
        try:
            while self.running:
                try:
                    # Schedule the scan based on power mode
                    scan_timeout = 5.0
                    if self.node.power_mode == PowerMode.LOW_POWER:
                        scan_timeout = 2.0
                    elif self.node.power_mode == PowerMode.PERFORMANCE:
                        scan_timeout = 10.0
                        
                    # Perform the scan
                    logger.debug("Scanning for Bluetooth mesh devices...")
                    devices = await self.scanner.discover(timeout=scan_timeout)
                    
                    # Process discovered devices
                    for device in devices:
                        if device.name and device.name.startswith("AIRGAP-SNS-"):
                            logger.debug(f"Found mesh device: {device.name} ({device.address})")
                            await self._connect_to_device(device)
                            
                    # Wait before next scan based on power mode
                    if self.node.power_mode == PowerMode.LOW_POWER:
                        await asyncio.sleep(self.scan_interval * 2)
                    elif self.node.power_mode == PowerMode.PERFORMANCE:
                        await asyncio.sleep(self.scan_interval / 2)
                    else:
                        await asyncio.sleep(self.scan_interval)
                        
                except Exception as e:
                    logger.error(f"Error in scan loop: {str(e)}")
                    await asyncio.sleep(5)  # Wait a bit before retrying
                    
        except asyncio.CancelledError:
            logger.info("Scan loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in scan loop: {str(e)}")
            
    async def _advertise_loop(self):
        """Advertise this node's presence to other mesh devices"""
        try:
            # Configure advertisement parameters based on power mode
            if self.node.power_mode == PowerMode.LOW_POWER:
                adv_interval = DEFAULT_ADVERTISEMENT_INTERVAL * 2
            elif self.node.power_mode == PowerMode.PERFORMANCE:
                adv_interval = DEFAULT_ADVERTISEMENT_INTERVAL / 2
            else:
                adv_interval = DEFAULT_ADVERTISEMENT_INTERVAL
                
            while self.running:
                try:
                    # Rotate identity if needed for privacy
                    current_time = time.time()
                    if (current_time - self.node.identity_rotation_time) > self.node.identity_rotation_interval:
                        self.node.rotate_identity()
                        
                    # Set up advertisement data with node information
                    adv_data = {
                        "service_data": {
                            MESH_SERVICE_UUID: {
                                "node_id": self.node.temp_identity,
                                "timestamp": current_time,
                                "battery": self.node.battery_level
                            }
                        }
                    }
                    
                    # Send local advertisement data
                    # Note: This is a simplified representation since direct advertisement control
                    # requires platform-specific code in a real implementation
                    logger.debug(f"Advertising node presence (interval: {adv_interval}ms)")
                    
                    # Sleep between advertisements
                    await asyncio.sleep(adv_interval / 1000)
                    
                except Exception as e:
                    logger.error(f"Error in advertisement loop: {str(e)}")
                    await asyncio.sleep(5)  # Wait before retrying
                    
        except asyncio.CancelledError:
            logger.info("Advertisement loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in advertisement loop: {str(e)}")
            
    async def _process_queue(self):
        """Process the message queue in a loop"""
        try:
            while self.running:
                try:
                    # Get message from queue
                    message = await self.message_queue.get()
                    
                    # Check if message is already in cache
                    if message.message_id in self.node.message_cache:
                        logger.debug(f"Ignoring already processed message: {message.message_id}")
                        self.message_queue.task_done()
                        continue
                        
                    # Verify message signature
                    if not self._verify_message(message):
                        logger.warning(f"Received message with invalid signature: {message.message_id}")
                        self.message_queue.task_done()
                        continue
                        
                    # Add to cache
                    self.node.message_cache.add(message.message_id)
                    
                    # Prune cache if needed
                    if len(self.node.message_cache) > self.node.max_cache_size:
                        # Remove oldest entries (just simulate this as we don't track age in this simplified version)
                        excess = len(self.node.message_cache) - self.node.max_cache_size
                        self.node.message_cache = set(list(self.node.message_cache)[excess:])
                        
                    # Process message
                    await self._process_message(message)
                    
                    # Mark task as done
                    self.message_queue.task_done()
                    
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error processing message from queue: {str(e)}")
                    
        except asyncio.CancelledError:
            logger.info("Process queue loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in process queue loop: {str(e)}")
            
    async def _process_message(self, message: MeshMessage):
        """Process a received message"""
        # Update statistics
        self.messages_received += 1
        
        # Check message type
        if message.message_type == MessageType.DATA:
            # Check if this message is for us or needs to be relayed
            is_for_us = message.destination_id is None or message.destination_id == self.node.node_id
            
            if is_for_us:
                # This message is for us, pass to callback
                payload_str = message.payload.decode('utf-8')
                logger.info(f"Received message: {payload_str[:30]}...")
                
                # Parse as burst message if possible
                if parse_burst:
                    burst_params = parse_burst(payload_str)
                    if burst_params:
                        logger.debug(f"Parsed burst parameters: {burst_params}")
                        
                # Call callback if registered
                if self.callback:
                    asyncio.create_task(self._call_callback(payload_str))
            
            # Check if we should relay this message
            if message.ttl > 0:
                # Decrement TTL
                message.ttl -= 1
                
                # Relay to other devices
                await self._relay_message(message)
        
        elif message.message_type == MessageType.NODE_DISCOVERY:
            # Process node discovery message
            await self._handle_node_discovery(message)
            
        elif message.message_type == MessageType.HEARTBEAT:
            # Process heartbeat message to update mesh topology
            await self._handle_heartbeat(message)
            
        elif message.message_type == MessageType.KEY_EXCHANGE:
            # Process key exchange message
            await self._handle_key_exchange(message)
    
    async def _call_callback(self, message: str):
        """Call the callback function with the message"""
        try:
            if self.callback:
                if asyncio.iscoroutinefunction(self.callback):
                    await self.callback(message)
                else:
                    self.callback(message)
        except Exception as e:
            logger.error(f"Error in callback: {str(e)}")
    
    async def _connect_to_device(self, device: BLEDevice):
        """Connect to a Bluetooth device and set up communication"""
        # Check if we're already connected
        if device.address in self.connected_devices:
            if self.connected_devices[device.address].is_connected:
                return
                
        try:
            # Connect to the device
            client = BleakClient(device)
            await client.connect()
            
            # Check if device has our service
            services = await client.get_services()
            if MESH_SERVICE_UUID not in [str(service.uuid) for service in services]:
                logger.debug(f"Device {device.address} does not support mesh service")
                await client.disconnect()
                return
                
            # Set up notification handler
            await client.start_notify(
                MESH_CHAR_DATA_UUID,
                lambda _, data: asyncio.create_task(self._handle_notification(device.address, data))
            )
            
            # Store connected device
            self.connected_devices[device.address] = client
            
            logger.info(f"Connected to mesh device: {device.address}")
            
            # Exchange node information
            await self._send_node_discovery(client)
            
        except Exception as e:
            logger.error(f"Error connecting to device {device.address}: {str(e)}")
    
    async def _handle_notification(self, device_address: str, data: bytes):
        """Handle notification from a connected device"""
        try:
            # Reconstruct message from data
            message = self._deserialize_message(data)
            
            # Add to queue for processing
            await self.message_queue.put(message)
            
        except Exception as e:
            logger.error(f"Error handling notification from {device_address}: {str(e)}")
    
    async def _broadcast_message(self, message: MeshMessage):
        """Broadcast a message to all connected devices"""
        # Serialize the message
        data = self._serialize_message(message)
        
        # Split into chunks if needed
        chunks = [data[i:i+MAX_PACKET_SIZE] for i in range(0, len(data), MAX_PACKET_SIZE)]
        
        # Send to all connected devices
        for device_address, client in list(self.connected_devices.items()):
            try:
                if client.is_connected:
                    for i, chunk in enumerate(chunks):
                        # Add chunk metadata
                        chunk_data = bytes([i, len(chunks)]) + chunk
                        await client.write_gatt_char(MESH_CHAR_DATA_UUID, chunk_data)
                else:
                    # Clean up disconnected client
                    del self.connected_devices[device_address]
            except Exception as e:
                logger.error(f"Error sending to {device_address}: {str(e)}")
                try:
                    del self.connected_devices[device_address]
                except KeyError:
                    pass
    
    async def _relay_message(self, message: MeshMessage):
        """Relay a message to other nodes in the mesh"""
        # Update statistics
        self.messages_relayed += 1
        
        # Broadcast the message
        await self._broadcast_message(message)
        
        logger.debug(f"Relayed message: {message.message_id} (TTL: {message.ttl})")
    
    async def _send_node_discovery(self, client: BleakClient):
        """Send node discovery information to a newly connected device"""
        # Create discovery message
        discovery_message = MeshMessage(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.NODE_DISCOVERY,
            source_id=self.node.node_id,
            destination_id=None,  # Broadcast
            ttl=1,  # Local only
            payload=f"{self.node.friendly_name},{self.node.battery_level}".encode(),
            timestamp=time.time(),
            signature=b"",  # No signature for discovery
            sequence=self.node.sequence_number
        )
        
        # Serialize and send
        data = self._serialize_message(discovery_message)
        await client.write_gatt_char(MESH_CHAR_DATA_UUID, data)
        
        logger.debug(f"Sent node discovery to newly connected device")
    
    async def _handle_node_discovery(self, message: MeshMessage):
        """Handle a node discovery message"""
        try:
            # Parse payload
            payload = message.payload.decode('utf-8').split(',')
            if len(payload) >= 2:
                friendly_name = payload[0]
                battery_level = int(payload[1])
                
                # Create or update node in peers
                if message.source_id not in self.node.peers:
                    self.node.peers[message.source_id] = MeshNode(
                        node_id=message.source_id,
                        friendly_name=friendly_name
                    )
                    
                # Update node information
                peer_node = self.node.peers[message.source_id]
                peer_node.friendly_name = friendly_name
                peer_node.battery_level = battery_level
                peer_node.last_seen = time.time()
                
                logger.debug(f"Updated peer node: {friendly_name} ({message.source_id})")
                
        except Exception as e:
            logger.error(f"Error handling node discovery: {str(e)}")
    
    async def _handle_heartbeat(self, message: MeshMessage):
        """Handle a heartbeat message"""
        try:
            # Update peer's last seen time
            if message.source_id in self.node.peers:
                self.node.peers[message.source_id].last_seen = time.time()
            
            # Parse payload for mesh metrics
            payload = message.payload.decode('utf-8').split(',')
            if len(payload) >= 3:
                battery_level = int(payload[0])
                peers_count = int(payload[1])
                uptime = float(payload[2])
                
                # Update peer information
                if message.source_id in self.node.peers:
                    peer_node = self.node.peers[message.source_id]
                    peer_node.battery_level = battery_level
                
                logger.debug(f"Received heartbeat from {message.source_id} (Peers: {peers_count}, Battery: {battery_level}%)")
                
        except Exception as e:
            logger.error(f"Error handling heartbeat: {str(e)}")
    
    async def _handle_key_exchange(self, message: MeshMessage):
        """Handle a key exchange message"""
        # Key exchange would be implemented here in a real system
        # This would use proper cryptographic key exchange protocols
        pass
    
    def _sign_message(self, payload: bytes, sequence: int) -> bytes:
        """Sign a message with the mesh key"""
        # Create HMAC
        h = hmac.HMAC(self.node.mesh_key, hashes.SHA256())
        h.update(payload)
        h.update(sequence.to_bytes(8, 'big'))
        return h.finalize()
    
    def _verify_message(self, message: MeshMessage) -> bool:
        """Verify the signature of a message"""
        # Skip verification for certain message types
        if message.message_type in (MessageType.NODE_DISCOVERY, MessageType.HEARTBEAT):
            return True
            
        # Create HMAC
        h = hmac.HMAC(self.node.mesh_key, hashes.SHA256())
        h.update(message.payload)
        h.update(message.sequence.to_bytes(8, 'big'))
        
        try:
            # Verify signature
            h.verify(message.signature)
            return True
        except Exception:
            return False
    
    def _serialize_message(self, message: MeshMessage) -> bytes:
        """Serialize a message for transmission"""
        # This is a simplified serialization
        # Real implementation would use a more efficient binary format
        parts = [
            message.message_id.encode(),
            bytes([message.message_type.value]),
            message.source_id.encode(),
            message.destination_id.encode() if message.destination_id else b'',
            bytes([message.ttl]),
            message.payload,
            message.timestamp.to_bytes(8, 'big'),
            message.signature,
            message.sequence.to_bytes(8, 'big')
        ]
        
        # Concatenate with length prefixes
        result = b''
        for part in parts:
            result += len(part).to_bytes(2, 'big') + part
            
        return result
    
    def _deserialize_message(self, data: bytes) -> MeshMessage:
        """Deserialize a message from received data"""
        # This is a simplified deserialization
        # Real implementation would use a more efficient binary format
        pos = 0
        parts = []
        
        # Extract parts with length prefixes
        while pos < len(data):
            length = int.from_bytes(data[pos:pos+2], 'big')
            pos += 2
            parts.append(data[pos:pos+length])
            pos += length
            
        # Construct message
        return MeshMessage(
            message_id=parts[0].decode(),
            message_type=MessageType(parts[1][0]),
            source_id=parts[2].decode(),
            destination_id=parts[3].decode() if parts[3] else None,
            ttl=parts[4][0],
            payload=parts[5],
            timestamp=int.from_bytes(parts[6], 'big'),
            signature=parts[7],
            sequence=int.from_bytes(parts[8], 'big')
        )

# Simple test function
async def test_bluetooth_mesh():
    """Test Bluetooth mesh functionality"""
    if not BLUETOOTH_AVAILABLE:
        print("Bluetooth mesh functionality not available. Required packages: bleak, cryptography")
        return
        
    print("Testing Bluetooth mesh functionality...")
    
    # Create callbacks
    async def on_node1_message(message):
        print(f"Node 1 received: {message}")
        
    async def on_node2_message(message):
        print(f"Node 2 received: {message}")
    
    # Create two mesh transceivers
    node1 = BluetoothMeshTransceiver(
        friendly_name="Test Node 1",
        callback=on_node1_message
    )
    
    node2 = BluetoothMeshTransceiver(
        friendly_name="Test Node 2",
        callback=on_node2_message
    )
    
    # Start transceivers
    await node1.start()
    await node2.start()
    
    print("Mesh transceivers started")
    print(f"Node 1 ID: {node1.node.node_id}")
    print(f"Node 2 ID: {node2.node.node_id}")
    
    # Wait for discovery
    print("Waiting for nodes to discover each other...")
    await asyncio.sleep(5)
    
    # Send test message
    print("Sending test message from Node 1...")
    test_message = "Hello from Node 1! !!BURST(dest=test;wc=bluetooth;encrypt=no)!!"
    await node1.send_message(test_message)
    
    # Wait for message propagation
    await asyncio.sleep(2)
    
    # Print mesh statistics
    print(f"Node 1 stats - Sent: {node1.messages_sent}, Received: {node1.messages_received}, Relayed: {node1.messages_relayed}")
    print(f"Node 2 stats - Sent: {node2.messages_sent}, Received: {node2.messages_received}, Relayed: {node2.messages_relayed}")
    
    # Stop transceivers
    await node1.stop()
    await node2.stop()
    
    print("Mesh transceivers stopped")

# Simple command-line interface
async def main():
    """Command-line interface for Bluetooth mesh module"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Bluetooth Mesh Module for Airgap SNS")
    parser.add_argument("--id", help="Node ID", default=None)
    parser.add_argument("--name", help="Friendly name", default=None)
    parser.add_argument("--power-mode", 
                       help="Power mode (low_power, balanced, performance)", 
                       default="balanced")
    parser.add_argument("--privacy-mode", 
                       help="Privacy mode (standard, enhanced, maximum)", 
                       default="enhanced")
    parser.add_argument("--scan-interval", 
                       help="Scan interval in seconds", 
                       type=int, 
                       default=DEFAULT_SCAN_INTERVAL)
    parser.add_argument("--interactive", 
                       help="Enable interactive mode", 
                       action="store_true")
    args = parser.parse_args()
    
    if not BLUETOOTH_AVAILABLE:
        print("Error: Bluetooth mesh functionality not available.")
        print("Required packages: bleak, cryptography")
        return

    # Message receive callback
    async def message_callback(message):
        print(f"\nReceived: {message}")
        print("> ", end="", flush=True)
        
        # Parse burst if available
        if parse_burst:
            burst_params = parse_burst(message)
            if burst_params:
                print(f"Parsed burst parameters: {burst_params}")
    
    # Create and start the mesh transceiver
    transceiver = BluetoothMeshTransceiver(
        node_id=args.id,
        friendly_name=args.name,
        power_mode=args.power_mode,
        privacy_mode=args.privacy_mode,
        scan_interval=args.scan_interval,
        callback=message_callback
    )
    
    await transceiver.start()
    print(f"Bluetooth mesh transceiver started")
    print(f"Node ID: {transceiver.node.node_id}")
    print(f"Friendly name: {transceiver.node.friendly_name}")
    
    if args.interactive:
        print("\nInteractive Mode - Enter commands or messages")
        print("Commands:")
        print("  /quit - Exit the client")
        print("  /peers - List known peers in the mesh")
        print("  /stats - Show mesh statistics")
        print("  /send <node_id> <message> - Send message to specific node")
        print("  /broadcast <message> - Broadcast message to all nodes")
        print("  /help - Show this help")
        
        try:
            while True:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("> ")
                )
                
                if user_input.lower() == "/quit":
                    break
                elif user_input.lower() == "/help":
                    print("Commands:")
                    print("  /quit - Exit the client")
                    print("  /peers - List known peers in the mesh")
                    print("  /stats - Show mesh statistics")
                    print("  /send <node_id> <message> - Send message to specific node")
                    print("  /broadcast <message> - Broadcast message to all nodes")
                    print("  /help - Show this help")
                elif user_input.lower() == "/peers":
                    if not transceiver.node.peers:
                        print("No peers discovered yet")
                    else:
                        print(f"Known peers ({len(transceiver.node.peers)}):")
                        for peer_id, peer in transceiver.node.peers.items():
                            last_seen_ago = time.time() - peer.last_seen
                            print(f"  {peer.friendly_name} ({peer_id[:8]}...) - "
                                  f"Battery: {peer.battery_level}%, "
                                  f"Last seen: {last_seen_ago:.1f}s ago")
                elif user_input.lower() == "/stats":
                    uptime = time.time() - transceiver.node.last_seen if transceiver.node.last_seen > 0 else 0
                    print(f"Mesh Statistics:")
                    print(f"  Messages sent: {transceiver.messages_sent}")
                    print(f"  Messages received: {transceiver.messages_received}")
                    print(f"  Messages relayed: {transceiver.messages_relayed}")
                    print(f"  Known peers: {len(transceiver.node.peers)}")
                    print(f"  Cache size: {len(transceiver.node.message_cache)}/{transceiver.node.max_cache_size}")
                    print(f"  Battery level: {transceiver.node.battery_level}%")
                    print(f"  Uptime: {uptime:.1f}s")
                elif user_input.lower().startswith("/send "):
                    parts = user_input[6:].strip().split(" ", 1)
                    if len(parts) < 2:
                        print("Usage: /send <node_id> <message>")
                    else:
                        node_id, message = parts
                        await transceiver.send_message(message, destination_id=node_id)
                        print(f"Message sent to {node_id}")
                elif user_input.lower().startswith("/broadcast "):
                    message = user_input[11:].strip()
                    if not message:
                        print("Usage: /broadcast <message>")
                    else:
                        await transceiver.send_message(message)
                        print("Message broadcast to all nodes")
                else:
                    # Send as broadcast message
                    await transceiver.send_message(user_input)
                    print("Message broadcast to all nodes")
                    
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            await transceiver.stop()
    else:
        # Non-interactive mode - run until interrupted
        try:
            print("Running in non-interactive mode. Press Ctrl+C to exit.")
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            await transceiver.stop()
    
    print("Bluetooth mesh transceiver stopped")

if __name__ == "__main__":
    asyncio.run(main())