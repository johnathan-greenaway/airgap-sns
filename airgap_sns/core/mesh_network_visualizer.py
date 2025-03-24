#!/usr/bin/env python3
"""
Mesh Network Visualizer for Airgap SNS

This module provides a visual representation of the Airgap SNS mesh network,
showing nodes, connections, and network topology. It distinguishes between
different connection types (Bluetooth, Audio, WebSocket) and provides
real-time updates of the network state.

Features:
- Real-time visualization of the mesh network
- Distinct visual representation for different connection types
- Node status monitoring (battery level, signal strength, etc.)
- Interactive interface for exploring the network
- Connection quality metrics
- Ability to simulate message propagation
- Support for exporting network topology
"""

import asyncio
import logging
import json
import time
import os
import argparse
import math
import random
from typing import Dict, List, Set, Tuple, Optional, Any, Union
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-visualizer")

# Try to import required visualization modules
try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    import matplotlib.patches as patches
    import networkx as nx
    from matplotlib.lines import Line2D
    VISUALIZATION_AVAILABLE = True
except ImportError:
    logger.warning("Visualization functionality not available. Required packages: matplotlib, networkx")
    VISUALIZATION_AVAILABLE = False

# Try to import tkinter for interactive GUI
try:
    import tkinter as tk
    from tkinter import ttk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    GUI_AVAILABLE = True
except ImportError:
    logger.warning("GUI functionality not available. Required package: tkinter")
    GUI_AVAILABLE = False

# Try to import required airgap_sns modules
try:
    from airgap_sns.client.client import NotificationClient
    from airgap_sns.core.burst import parse_burst
except ImportError:
    try:
        from client import NotificationClient
        from burst import parse_burst
    except ImportError:
        logger.error("Could not import airgap_sns modules. Ensure airgap_sns is installed or in PYTHONPATH.")
        NotificationClient = None
        parse_burst = None

# Connection type definitions
class ConnectionType:
    WEBSOCKET = "websocket"
    BLUETOOTH = "bluetooth"
    AUDIO = "audio"
    UNKNOWN = "unknown"

# Connection colors
CONNECTION_COLORS = {
    ConnectionType.WEBSOCKET: "blue",
    ConnectionType.BLUETOOTH: "green",
    ConnectionType.AUDIO: "red",
    ConnectionType.UNKNOWN: "gray"
}

# Node status
class NodeStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"

# Node status colors
NODE_STATUS_COLORS = {
    NodeStatus.ACTIVE: "green",
    NodeStatus.INACTIVE: "red",
    NodeStatus.UNKNOWN: "gray"
}

class MeshNode:
    """Represents a node in the mesh network"""
    
    def __init__(
        self,
        node_id: str,
        friendly_name: Optional[str] = None,
        node_type: str = "client",
        battery_level: int = 100,
        last_seen: float = 0.0,
        position: Optional[Tuple[float, float]] = None
    ):
        """Initialize a mesh node"""
        self.node_id = node_id
        self.friendly_name = friendly_name or node_id[:8]
        self.node_type = node_type  # client, server, gateway, etc.
        self.battery_level = battery_level
        self.last_seen = last_seen
        self.status = NodeStatus.UNKNOWN
        self.connections: Dict[str, MeshConnection] = {}
        self.position = position or (random.uniform(0, 10), random.uniform(0, 10))
        self.metadata: Dict[str, Any] = {}
        
    def update_status(self, current_time: float = None) -> str:
        """Update node status based on last seen time"""
        if current_time is None:
            current_time = time.time()
            
        if self.last_seen == 0:
            self.status = NodeStatus.UNKNOWN
        elif current_time - self.last_seen < 300:  # 5 minutes
            self.status = NodeStatus.ACTIVE
        else:
            self.status = NodeStatus.INACTIVE
            
        return self.status
        
    def add_connection(self, connection: 'MeshConnection') -> None:
        """Add a connection to this node"""
        self.connections[connection.connection_id] = connection
        
    def remove_connection(self, connection_id: str) -> bool:
        """Remove a connection from this node"""
        if connection_id in self.connections:
            del self.connections[connection_id]
            return True
        return False
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary"""
        return {
            "node_id": self.node_id,
            "friendly_name": self.friendly_name,
            "node_type": self.node_type,
            "battery_level": self.battery_level,
            "last_seen": self.last_seen,
            "status": self.status,
            "position": self.position,
            "connections": [conn.to_dict() for conn in self.connections.values()],
            "metadata": self.metadata
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MeshNode':
        """Create node from dictionary"""
        node = cls(
            node_id=data["node_id"],
            friendly_name=data.get("friendly_name"),
            node_type=data.get("node_type", "client"),
            battery_level=data.get("battery_level", 100),
            last_seen=data.get("last_seen", 0.0),
            position=tuple(data.get("position", (0, 0)))
        )
        node.status = data.get("status", NodeStatus.UNKNOWN)
        node.metadata = data.get("metadata", {})
        return node

class MeshConnection:
    """Represents a connection between two nodes in the mesh network"""
    
    def __init__(
        self,
        connection_id: str,
        source_id: str,
        target_id: str,
        connection_type: str = ConnectionType.UNKNOWN,
        signal_strength: int = 0,
        last_active: float = 0.0,
        latency: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize a mesh connection"""
        self.connection_id = connection_id
        self.source_id = source_id
        self.target_id = target_id
        self.connection_type = connection_type
        self.signal_strength = signal_strength  # 0-100
        self.last_active = last_active
        self.latency = latency  # milliseconds
        self.metadata = metadata or {}
        self.messages_sent = 0
        self.messages_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.active = True
        
    def update_activity(self, current_time: float = None) -> bool:
        """Update connection activity status based on last active time"""
        if current_time is None:
            current_time = time.time()
            
        # Connection is considered inactive after 5 minutes of no activity
        self.active = (current_time - self.last_active) < 300
        return self.active
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert connection to dictionary"""
        return {
            "connection_id": self.connection_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "connection_type": self.connection_type,
            "signal_strength": self.signal_strength,
            "last_active": self.last_active,
            "latency": self.latency,
            "metadata": self.metadata,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "active": self.active
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MeshConnection':
        """Create connection from dictionary"""
        conn = cls(
            connection_id=data["connection_id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            connection_type=data.get("connection_type", ConnectionType.UNKNOWN),
            signal_strength=data.get("signal_strength", 0),
            last_active=data.get("last_active", 0.0),
            latency=data.get("latency", 0.0),
            metadata=data.get("metadata", {})
        )
        conn.messages_sent = data.get("messages_sent", 0)
        conn.messages_received = data.get("messages_received", 0)
        conn.bytes_sent = data.get("bytes_sent", 0)
        conn.bytes_received = data.get("bytes_received", 0)
        conn.active = data.get("active", True)
        return conn

class MeshNetworkMap:
    """Represents the entire mesh network topology"""
    
    def __init__(self):
        """Initialize the mesh network map"""
        self.nodes: Dict[str, MeshNode] = {}
        self.connections: Dict[str, MeshConnection] = {}
        self.last_update = 0.0
        self.metadata: Dict[str, Any] = {}
        
    def add_node(self, node: MeshNode) -> None:
        """Add a node to the network"""
        self.nodes[node.node_id] = node
        self.last_update = time.time()
        
    def remove_node(self, node_id: str) -> None:
        """Remove a node from the network"""
        if node_id in self.nodes:
            # Remove all connections for this node
            connections_to_remove = []
            for conn_id, conn in self.connections.items():
                if conn.source_id == node_id or conn.target_id == node_id:
                    connections_to_remove.append(conn_id)
                    
            for conn_id in connections_to_remove:
                self.remove_connection(conn_id)
                
            # Remove the node
            del self.nodes[node_id]
            self.last_update = time.time()
            
    def add_connection(self, connection: MeshConnection) -> None:
        """Add a connection to the network"""
        self.connections[connection.connection_id] = connection
        
        # Add connection to source and target nodes
        if connection.source_id in self.nodes:
            self.nodes[connection.source_id].add_connection(connection)
            
        if connection.target_id in self.nodes:
            # Create a reversed connection for the target node
            reversed_conn = MeshConnection(
                connection_id=f"{connection.connection_id}-reverse",
                source_id=connection.target_id,
                target_id=connection.source_id,
                connection_type=connection.connection_type,
                signal_strength=connection.signal_strength,
                last_active=connection.last_active,
                latency=connection.latency,
                metadata=connection.metadata
            )
            self.nodes[connection.target_id].add_connection(reversed_conn)
            
        self.last_update = time.time()
        
    def remove_connection(self, connection_id: str) -> None:
        """Remove a connection from the network"""
        if connection_id in self.connections:
            conn = self.connections[connection_id]
            
            # Remove from source and target nodes
            if conn.source_id in self.nodes:
                self.nodes[conn.source_id].remove_connection(connection_id)
                
            if conn.target_id in self.nodes:
                self.nodes[conn.target_id].remove_connection(f"{connection_id}-reverse")
                
            # Remove from connections dict
            del self.connections[connection_id]
            self.last_update = time.time()
            
    def update_node(self, node_id: str, **kwargs) -> None:
        """Update a node's properties"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            for key, value in kwargs.items():
                if hasattr(node, key):
                    setattr(node, key, value)
            
            self.last_update = time.time()
            
    def update_connection(self, connection_id: str, **kwargs) -> None:
        """Update a connection's properties"""
        if connection_id in self.connections:
            conn = self.connections[connection_id]
            for key, value in kwargs.items():
                if hasattr(conn, key):
                    setattr(conn, key, value)
                    
            # Update the reversed connection too
            reversed_id = f"{connection_id}-reverse"
            if conn.target_id in self.nodes:
                target_node = self.nodes[conn.target_id]
                if reversed_id in target_node.connections:
                    reversed_conn = target_node.connections[reversed_id]
                    for key, value in kwargs.items():
                        if hasattr(reversed_conn, key) and key not in ("source_id", "target_id"):
                            setattr(reversed_conn, key, value)
                            
            self.last_update = time.time()
            
    def get_nodes_by_connection_type(self, connection_type: str) -> List[MeshNode]:
        """Get nodes that have at least one connection of the specified type"""
        result = []
        for node in self.nodes.values():
            for conn in node.connections.values():
                if conn.connection_type == ConnectionType.BLUETOOTH:
                if conn.connection_type == connection_type:
                    return True
        return False
        
    def get_connection_by_type(self, connection_type: str) -> List[MeshConnection]:
        """Get all connections of a specific type"""
        result = []
        for conn in self.connections.values():
            if conn.connection_type == connection_type:
                result.append(conn)
        return result
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the network map to a dictionary"""
        return {
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "connections": {conn_id: conn.to_dict() for conn_id, conn in self.connections.items()},
            "last_update": self.last_update,
            "metadata": self.metadata
        }
        
    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load the network map from a dictionary"""
        # Clear existing data
        self.nodes = {}
        self.connections = {}
        
        # Load nodes first
        for node_id, node_data in data.get("nodes", {}).items():
            node = MeshNode.from_dict(node_data)
            self.nodes[node_id] = node
            
        # Load connections
        for conn_id, conn_data in data.get("connections", {}).items():
            conn = MeshConnection.from_dict(conn_data)
            self.connections[conn_id] = conn
            
        # Load metadata
        self.last_update = data.get("last_update", time.time())
        self.metadata = data.get("metadata", {})
        
    def save_to_file(self, filename: str) -> bool:
        """Save the network map to a JSON file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            logger.info(f"Network map saved to {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to save network map: {str(e)}")
            return False
            
    def load_from_file(self, filename: str) -> bool:
        """Load the network map from a JSON file"""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            self.from_dict(data)
            logger.info(f"Network map loaded from {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to load network map: {str(e)}")
            return False
            
    def update_statuses(self) -> None:
        """Update the status of all nodes and connections"""
        current_time = time.time()
        
        # Update node statuses
        for node in self.nodes.values():
            node.update_status(current_time)
            
        # Update connection statuses
        for conn in self.connections.values():
            conn.update_activity(current_time)
            
    def simulate_message_propagation(self, 
                                    source_id: str, 
                                    message: str, 
                                    max_hops: int = 5) -> Dict[str, Any]:
        """Simulate message propagation through the network"""
        if source_id not in self.nodes:
            return {"success": False, "error": "Source node not found"}
            
        visited = set()
        queue = [(source_id, 0)]  # (node_id, hop_count)
        path = {source_id: None}  # node_id -> previous_node_id
        
        while queue:
            current_id, hops = queue.pop(0)
            
            # Skip if already visited or exceeds max hops
            if current_id in visited or hops > max_hops:
                continue
                
            visited.add(current_id)
            
            # Get connections for current node
            current_node = self.nodes[current_id]
            for conn_id, conn in current_node.connections.items():
                if not conn.active:
                    continue  # Skip inactive connections
                    
                target_id = conn.target_id
                if target_id not in visited:
                    queue.append((target_id, hops + 1))
                    path[target_id] = current_id
        
        # Build propagation report
        result = {
            "success": True,
            "source_id": source_id,
            "message": message,
            "reached_nodes": list(visited),
            "unreached_nodes": [n for n in self.nodes if n not in visited],
            "path": path,
            "max_hops": max_hops,
            "propagation_time": time.time()
        }
        
        return result

class MeshNetworkVisualizer:
    """Visualizes the mesh network using matplotlib and networkx"""
    
    def __init__(self, network_map: MeshNetworkMap):
        """Initialize the visualizer"""
        if not VISUALIZATION_AVAILABLE:
            raise RuntimeError("Visualization functionality not available. Required packages: matplotlib, networkx")
            
        self.network_map = network_map
        self.fig = None
        self.ax = None
        self.graph = None
        self.pos = None
        self.node_colors = []
        self.node_sizes = []
        self.edge_colors = []
        self.edge_widths = []
        self.labels = {}
        self.ani = None
        self.paused = False
        
    def build_graph(self) -> nx.Graph:
        """Build a networkx graph from the network map"""
        # Create a new directed graph
        G = nx.DiGraph()
        
        # Add nodes
        for node_id, node in self.network_map.nodes.items():
            G.add_node(node_id, 
                      pos=node.position,
                      status=node.status,
                      battery=node.battery_level,
                      last_seen=node.last_seen,
                      node_type=node.node_type,
                      friendly_name=node.friendly_name)
        
        # Add edges
        for conn_id, conn in self.network_map.connections.items():
            G.add_edge(conn.source_id, 
                      conn.target_id,
                      connection_type=conn.connection_type,
                      signal_strength=conn.signal_strength,
                      latency=conn.latency,
                      active=conn.active,
                      last_active=conn.last_active)
        
        return G
        
    def update_graph(self) -> None:
        """Update the graph with the latest network data"""
        self.graph = self.build_graph()
        
        # Update positions
        self.pos = {}
        for node_id, node in self.network_map.nodes.items():
            self.pos[node_id] = node.position
            
        # Update node colors based on status
        self.node_colors = []
        for node in self.graph.nodes():
            status = self.graph.nodes[node]["status"]
            self.node_colors.append(NODE_STATUS_COLORS.get(status, "gray"))
            
        # Update node sizes based on battery level or importance
        self.node_sizes = []
        for node in self.graph.nodes():
            battery = self.graph.nodes[node]["battery"]
            size = 300 + (battery * 2)  # Scale based on battery
            self.node_sizes.append(size)
            
        # Update edge colors based on connection type
        self.edge_colors = []
        for u, v, data in self.graph.edges(data=True):
            conn_type = data["connection_type"]
            self.edge_colors.append(CONNECTION_COLORS.get(conn_type, "gray"))
            
        # Update edge widths based on signal strength
        self.edge_widths = []
        for u, v, data in self.graph.edges(data=True):
            signal = data["signal_strength"]
            width = 1 + (signal / 20)  # Scale based on signal
            self.edge_widths.append(width)
            
        # Update labels
        self.labels = {}
        for node in self.graph.nodes():
            self.labels[node] = self.graph.nodes[node]["friendly_name"]
        
    def initialize_plot(self, figsize: Tuple[int, int] = (10, 8)) -> None:
        """Initialize the plot"""
        # Create figure and axis
        self.fig, self.ax = plt.subplots(figsize=figsize)
        self.fig.suptitle("Airgap SNS Mesh Network Visualizer", fontsize=16)
        
        # Set up axis
        self.ax.set_axis_off()
        
        # Update graph data
        self.update_graph()
        
    def draw_network(self) -> None:
        """Draw the network graph"""
        if not self.fig or not self.ax:
            self.initialize_plot()
            
        # Clear the current axes
        self.ax.clear()
        
        # Update graph data
        self.update_graph()
        
        # Draw nodes
        nx.draw_networkx_nodes(
            self.graph, 
            self.pos, 
            ax=self.ax,
            node_color=self.node_colors,
            node_size=self.node_sizes,
            alpha=0.8
        )
        
        # Draw edges
        nx.draw_networkx_edges(
            self.graph, 
            self.pos, 
            ax=self.ax,
            edge_color=self.edge_colors,
            width=self.edge_widths,
            arrowsize=10,
            alpha=0.6
        )
        
        # Draw labels
        nx.draw_networkx_labels(
            self.graph, 
            self.pos, 
            ax=self.ax,
            labels=self.labels,
            font_size=8,
            font_weight="bold"
        )
        
        # Add legend for connection types
        legend_elements = [
            Line2D([0], [0], color=color, lw=2, label=conn_type)
            for conn_type, color in CONNECTION_COLORS.items()
        ]
        self.ax.legend(handles=legend_elements, loc="upper right")
        
        # Add title with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ax.set_title(f"Last Updated: {timestamp}")
        
        # Add node count info
        active_nodes = sum(1 for n in self.network_map.nodes.values() if n.status == NodeStatus.ACTIVE)
        total_nodes = len(self.network_map.nodes)
        self.ax.text(
            0.02, 0.02, 
            f"Active Nodes: {active_nodes}/{total_nodes}",
            transform=self.ax.transAxes,
            fontsize=10
        )
        
        # Draw
        self.fig.canvas.draw()
        
    def animate(self, interval: int = 1000) -> None:
        """Animate the network visualization with automatic updates"""
        if not self.fig or not self.ax:
            self.initialize_plot()
            
        def update(frame):
            if not self.paused:
                self.network_map.update_statuses()
                self.draw_network()
            return self.ax,
            
        self.ani = animation.FuncAnimation(
            self.fig, 
            update, 
            interval=interval,
            blit=True
        )
        
    def show(self, interactive: bool = False) -> None:
        """Show the visualization"""
        if not self.fig or not self.ax:
            self.initialize_plot()
            self.draw_network()
            
        if interactive and GUI_AVAILABLE:
            self.create_interactive_ui()
        else:
            plt.show()
            
    def create_interactive_ui(self) -> None:
        """Create an interactive UI with tkinter"""
        if not GUI_AVAILABLE:
            raise RuntimeError("GUI functionality not available. Required package: tkinter")
            
        root = tk.Tk()
        root.title("Airgap SNS Mesh Network Visualizer")
        root.geometry("1200x800")
        
        # Create main frame
        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create canvas for the plot
        canvas = FigureCanvasTkAgg(self.fig, master=main_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Create control frame
        control_frame = ttk.Frame(root, padding=10)
        control_frame.pack(fill=tk.X)
        
        # Add control buttons
        refresh_btn = ttk.Button(control_frame, text="Refresh", 
                               command=self.draw_network)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Toggle animation button
        def toggle_animation():
            self.paused = not self.paused
            if self.paused:
                toggle_btn.config(text="Resume Animation")
            else:
                toggle_btn.config(text="Pause Animation")
                
        toggle_btn = ttk.Button(control_frame, text="Pause Animation", 
                              command=toggle_animation)
        toggle_btn.pack(side=tk.LEFT, padx=5)
        
        # Add save button
        def save_network():
            filename = "mesh_network.json"
            self.network_map.save_to_file(filename)
            tk.messagebox.showinfo("Save Network", f"Network saved to {filename}")
            
        save_btn = ttk.Button(control_frame, text="Save Network", 
                            command=save_network)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        # Add simulation button
        def simulate_message():
            # Get a random source node
            if not self.network_map.nodes:
                tk.messagebox.showinfo("Simulation", "No nodes in network")
                return
                
            source_id = random.choice(list(self.network_map.nodes.keys()))
            message = f"Test message at {datetime.now().strftime('%H:%M:%S')}"
            
            # Run simulation
            result = self.network_map.simulate_message_propagation(
                source_id, message, max_hops=5
            )
            
            # Show result
            reached = len(result["reached_nodes"])
            unreached = len(result["unreached_nodes"])
            tk.messagebox.showinfo(
                "Simulation Results", 
                f"Message from {source_id}\nReached: {reached} nodes\nUnreached: {unreached} nodes"
            )
            
        sim_btn = ttk.Button(control_frame, text="Simulate Message", 
                           command=simulate_message)
        sim_btn.pack(side=tk.LEFT, padx=5)
        
        # Add status label
        status_var = tk.StringVar()
        status_var.set("Ready")
        status_label = ttk.Label(control_frame, textvariable=status_var)
        status_label.pack(side=tk.RIGHT, padx=5)
        
        # Start animation
        self.animate(interval=2000)
        
        # Start the main loop
        root.mainloop()
        
    def save_image(self, filename: str) -> bool:
        """Save the current visualization as an image"""
        if not self.fig:
            logger.error("No figure to save")
            return False
            
        try:
            self.fig.savefig(filename, dpi=300, bbox_inches="tight")
            logger.info(f"Visualization saved to {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to save visualization: {str(e)}")
            return False

class NetworkClient:
    """Client for connecting to airgap-sns and monitoring the mesh network"""
    
    def __init__(
        self,
        client_id: str,
        uri: str = "ws://localhost:9000/ws/",
        update_interval: int = 10.0,
        auto_save: bool = True,
        save_file: str = "mesh_network.json"
    ):
        """Initialize the network client"""
        self.client_id = client_id
        self.uri = uri
        self.update_interval = update_interval
        self.auto_save = auto_save
        self.save_file = save_file
        self.network_map = MeshNetworkMap()
        self.visualizer = None
        self.client = None
        self.running = False
        
    async def connect(self) -> bool:
        """Connect to the notification server"""
        try:
            # Import client
            if NotificationClient is None:
                raise ImportError("Could not import NotificationClient")
                
            # Create and connect client
            self.client = NotificationClient(
                uri=self.uri,
                client_id=self.client_id
            )
            
            # Register handlers
            self.client.register_handler("network_update", self._handle_network_update)
            self.client.register_handler("node_update", self._handle_node_update)
            self.client.register_handler("connection_update", self._handle_connection_update)
            
            # Connect
            success = await self.client.connect()
            if success:
                logger.info(f"Connected to {self.uri} as {self.client_id}")
            else:
                logger.error(f"Failed to connect to {self.uri}")
                
            return success
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False
            
    async def _handle_network_update(self, message: str) -> None:
        """Handle network update messages"""
        try:
            # Parse message as JSON
            data = json.loads(message)
            
            # Update network map
            self.network_map.from_dict(data)
            logger.info(f"Updated network map with {len(self.network_map.nodes)} nodes and {len(self.network_map.connections)} connections")
            
            # Auto-save if enabled
            if self.auto_save:
                self.network_map.save_to_file(self.save_file)
                
        except Exception as e:
            logger.error(f"Error handling network update: {str(e)}")
            
    async def _handle_node_update(self, message: str) -> None:
        """Handle node update messages"""
        try:
            # Parse message as JSON
            data = json.loads(message)
            node_id = data.get("node_id")
            
            if not node_id:
                logger.warning("Node update missing node_id")
                return
                
            # Check if node exists
            if node_id in self.network_map.nodes:
                # Update existing node
                self.network_map.update_node(node_id, **data)
                logger.info(f"Updated node: {node_id}")
            else:
                # Create new node
                node = MeshNode.from_dict(data)
                self.network_map.add_node(node)
                logger.info(f"Added new node: {node_id}")
                
            # Auto-save if enabled
            if self.auto_save:
                self.network_map.save_to_file(self.save_file)
                
        except Exception as e:
            logger.error(f"Error handling node update: {str(e)}")
            
    async def _handle_connection_update(self, message: str) -> None:
        """Handle connection update messages"""
        try:
            # Parse message as JSON
            data = json.loads(message)
            conn_id = data.get("connection_id")
            
            if not conn_id:
                logger.warning("Connection update missing connection_id")
                return
                
            # Check if connection exists
            if conn_id in self.network_map.connections:
                # Update existing connection
                self.network_map.update_connection(conn_id, **data)
                logger.info(f"Updated connection: {conn_id}")
            else:
                # Create new connection
                conn = MeshConnection.from_dict(data)
                self.network_map.add_connection(conn)
                logger.info(f"Added new connection: {conn_id}")
                
            # Auto-save if enabled
            if self.auto_save:
                self.network_map.save_to_file(self.save_file)
                
        except Exception as e:
            logger.error(f"Error handling connection update: {str(e)}")
            
    async def request_network_update(self) -> bool:
        """Request a full network update from the server"""
        if not self.client:
            logger.error("Not connected to server")
            return False
            
        try:
            # Create burst message
            burst = self.client.create_burst_message(
                dest="server",
                type="network_request"
            )
            
            # Send request
            success = await self.client.send_burst(burst)
            if success:
                logger.info("Network update requested")
            else:
                logger.error("Failed to request network update")
                
            return success
            
        except Exception as e:
            logger.error(f"Error requesting network update: {str(e)}")
            return False
            
    async def run(self) -> None:
        """Run the network client"""
        # Connect to server
        if not await self.connect():
            return
            
        self.running = True
        
        # Create visualizer
        if VISUALIZATION_AVAILABLE:
            self.visualizer = MeshNetworkVisualizer(self.network_map)
            
        # Load existing network data if available
        if os.path.exists(self.save_file):
            self.network_map.load_from_file(self.save_file)
            logger.info(f"Loaded network data from {self.save_file}")
            
        # Request initial network update
        await self.request_network_update()
        
        # Start update task and websocket listener
        try:
            # Create and run tasks
            update_task = asyncio.create_task(self._update_loop())
            listen_task = asyncio.create_task(self.client.listen())
            
            # Wait for tasks to complete
            await asyncio.gather(update_task, listen_task)
            
        except asyncio.CancelledError:
            logger.info("Client tasks cancelled")
        except Exception as e:
            logger.error(f"Error in client: {str(e)}")
        finally:
            # Clean up
            self.running = False
            if self.client:
                await self.client.close()
            
    async def _update_loop(self) -> None:
        """Periodic update loop"""
        try:
            while self.running:
                # Request network update periodically
                await self.request_network_update()
                
                # Wait for next update
                await asyncio.sleep(self.update_interval)
                
        except asyncio.CancelledError:
            logger.info("Update loop cancelled")
            raise
            
    def stop(self) -> None:
        """Stop the network client"""
        self.running = False
        
    def show_visualization(self, interactive: bool = True) -> None:
        """Show the network visualization"""
        if not VISUALIZATION_AVAILABLE:
            logger.error("Visualization not available")
            return
            
        if not self.visualizer:
            self.visualizer = MeshNetworkVisualizer(self.network_map)
            
        # Show visualization
        self.visualizer.show(interactive=interactive)

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Airgap SNS Mesh Network Visualizer")
    parser.add_argument("--id", default="visualizer", help="Client ID")
    parser.add_argument("--uri", default="ws://localhost:9000/ws/", help="Server URI")
    parser.add_argument("--interval", type=float, default=10.0, help="Update interval in seconds")
    parser.add_argument("--load", default="mesh_network.json", help="Load network from file")
    parser.add_argument("--no-auto-save", action="store_true", help="Disable auto-save")
    parser.add_argument("--no-interactive", action="store_true", help="Disable interactive mode")
    parser.add_argument("--offline", action="store_true", help="Run in offline mode (no server connection)")
    parser.add_argument("--simulate", type=int, default=0, help="Simulate network with N nodes")
    return parser.parse_args()

async def main_async() -> None:
    """Main async entry point"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Check for offline mode
    if args.offline:
        # Create network map
        network_map = MeshNetworkMap()
        
        # Load from file if specified
        if os.path.exists(args.load):
            network_map.load_from_file(args.load)
            logger.info(f"Loaded network from {args.load}")
            
        # Simulate nodes if requested
        if args.simulate > 0:
            _simulate_network(network_map, args.simulate)
            logger.info(f"Simulated network with {args.simulate} nodes")
            
        # Create visualizer
        if VISUALIZATION_AVAILABLE:
            visualizer = MeshNetworkVisualizer(network_map)
            visualizer.show(interactive=not args.no_interactive)
        else:
            logger.error("Visualization not available")
            
    else:
        # Create network client
        client = NetworkClient(
            client_id=args.id,
            uri=args.uri,
            update_interval=args.interval,
            auto_save=not args.no_auto_save,
            save_file=args.load
        )
        
        # Simulate nodes if requested
        if args.simulate > 0:
            _simulate_network(client.network_map, args.simulate)
            logger.info(f"Simulated network with {args.simulate} nodes")
            
        # Run in background
        client_task = asyncio.create_task(client.run())
        
        try:
            # Show visualization if available
            if VISUALIZATION_AVAILABLE:
                # Give client time to connect and get updates
                await asyncio.sleep(2)
                client.show_visualization(interactive=not args.no_interactive)
            else:
                # Just run the client
                await client_task
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            # Clean up
            client.stop()
            client_task.cancel()
            try:
                await client_task
            except asyncio.CancelledError:
                pass

def _simulate_network(network_map: MeshNetworkMap, num_nodes: int) -> None:
    """Simulate a network with random nodes and connections"""
    # Create nodes
    for i in range(num_nodes):
        node_id = f"node-{i:03d}"
        node_type = random.choice(["client", "server", "gateway", "router"])
        battery = random.randint(10, 100)
        pos = (random.uniform(0, 10), random.uniform(0, 10))
        
        node = MeshNode(
            node_id=node_id,
            friendly_name=f"Node {i}",
            node_type=node_type,
            battery_level=battery,
            last_seen=time.time() - random.uniform(0, 300),
            position=pos
        )
        
        network_map.add_node(node)
    
    # Create connections (approximately 2-4 per node)
    nodes = list(network_map.nodes.keys())
    for node_id in nodes:
        # Number of connections for this node
        num_conn = random.randint(2, min(4, len(nodes) - 1))
        
        # Create connections
        for j in range(num_conn):
            # Pick a random target node
            target_candidates = [n for n in nodes if n != node_id]
            if not target_candidates:
                continue
                
            target_id = random.choice(target_candidates)
            
            # Pick a random connection type
            conn_type = random.choice([
                ConnectionType.WEBSOCKET,
                ConnectionType.BLUETOOTH,
                ConnectionType.AUDIO
            ])
            
            # Create connection
            conn_id = f"{node_id}-to-{target_id}"
            conn = MeshConnection(
                connection_id=conn_id,
                source_id=node_id,
                target_id=target_id,
                connection_type=conn_type,
                signal_strength=random.randint(30, 100),
                last_active=time.time() - random.uniform(0, 60),
                latency=random.uniform(10, 200)
            )
            
            network_map.add_connection(conn)
    
    # Update all statuses
    network_map.update_statuses()

def main() -> None:
    """Main entry point"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")

if __name__ == "__main__":
    main()