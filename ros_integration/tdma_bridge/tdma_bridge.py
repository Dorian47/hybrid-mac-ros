#!/usr/bin/env python3
"""
TDMA-ROS Bridge Node

Integrates the TDMA slot scheduler with ROS-based robotic control.
This node runs on each robot and:

1. Subscribes to ROS control topics such as /cmd_vel.
2. Communicates with the TDMA management layer to obtain slot configuration.
3. Queues and transmits control commands through the TDMA data UDP port.
4. Prints delivery statistics for cross-layer monitoring.

Architecture:
    ROS Control App
         |
         | publish
         v
    tdma_bridge -- TCP/socket --> TDMA_server (slot allocator)
         |
         | UDP port 10000
         v
    SDR driver -- RF --> Air

Usage:
    # Run TDMA_server.py separately on the AP before starting this bridge.
    python3 tdma_bridge.py --role sta --sdr-ip 192.168.13.1 --robot-id 1
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# ROS imports (graceful degradation if ROS not installed)
# ---------------------------------------------------------------------------
try:
    import rospy
    from geometry_msgs.msg import Twist
    HAS_ROS = True
except ImportError:
    rospy = None
    Twist = None
    HAS_ROS = False


# ===================================================================
# Data structures
# ===================================================================

@dataclass
class TDMASlot:
    """A single TDMA slot assignment."""
    slot_id: int
    start_time_us: int       # local TSF timer, microseconds
    duration_us: int
    allocated_to: int        # robot ID


@dataclass
class TDMAFrame:
    """One superframe worth of TDMA slot assignments."""
    frame_id: int
    beacon_time_us: int
    slots: list = field(default_factory=list)
    tdma_duration_us: int = 0
    csma_ctl_duration_us: int = 0
    csma_gen_duration_us: int = 0


@dataclass
class ControlCommand:
    """A queued robot control command waiting for its TDMA slot."""
    seq: int
    topic: str
    payload: bytes
    deadline_us: int          # absolute TSF deadline
    created_us: int           # when the command was queued


# ===================================================================
# TDMA Management Protocol (simple socket-based)
# ===================================================================

class TDMAManagementClient:
    """
    Communicates with TDMA_server.py over TCP to receive slot configuration.

    Protocol: newline-delimited text (matches TDMA_server.py).
    Server sends: node_id\n  s1_slots\n  s2_slots\n  then closes.
    """

    def __init__(self, server_host: str, server_port: int = 9999,
                 robot_id: int = 1, role: str = "sta"):
        self.server_host = server_host
        self.server_port = server_port
        self.robot_id = robot_id
        self.role = role
        self._sock: Optional[socket.socket] = None
        self.config: Optional[dict] = None

    def connect_and_configure(self, timeout: float = 10.0) -> bool:
        """Connect, receive slot config, disconnect. Returns True on success."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(timeout)
            self._sock.connect((self.server_host, self.server_port))

            node_id_str = self._recv_line()
            if not node_id_str:
                return False
            node_id = int(node_id_str)

            s1_str = self._recv_line()
            s1 = [int(s) for s in s1_str.split()] if s1_str else []

            s2_str = self._recv_line()
            s2 = [int(s) for s in s2_str.split()] if s2_str else []

            self._sock.close()
            self._sock = None

            self.config = {"node_id": node_id, "s1": s1, "s2": s2}
            print(f"[tdma_bridge] Configured node {node_id}: s1={s1} s2={s2}")
            return True

        except (socket.timeout, ConnectionRefusedError, OSError, ValueError) as e:
            print(f"[tdma_bridge] Config failed: {e}")
            self.close()
            return False

    def close(self):
        if self._sock:
            try: self._sock.close()
            except OSError: pass
            self._sock = None

    def _recv_line(self) -> str:
        buf = b''
        while True:
            ch = self._sock.recv(1)
            if not ch or ch == b'\n':
                break
            buf += ch
        return buf.decode().strip()


# ===================================================================
# TDMA-aligned command queue
# ===================================================================

class TDMACommandQueue:
    """
    Priority queue for robot control commands.
    Commands are dequeued in TDMA-slot order and transmitted
    at the scheduled transmission time.
    """

    def __init__(self, max_queue_len: int = 32):
        self.max_queue_len = max_queue_len
        self._queue: deque = deque(maxlen=max_queue_len)
        self._seq_counter = 0
        self._dropped_count = 0
        self._lock = threading.Lock()

    def enqueue(self, topic: str, payload: bytes, deadline_us: int,
                created_us: int) -> int:
        """Add a command to the queue. Returns sequence number."""
        with self._lock:
            seq = self._seq_counter
            self._seq_counter += 1
            if len(self._queue) >= self.max_queue_len:
                self._dropped_count += 1
            cmd = ControlCommand(
                seq=seq, topic=topic, payload=payload,
                deadline_us=deadline_us, created_us=created_us,
            )
            self._queue.append(cmd)
            return seq

    def dequeue(self) -> Optional[ControlCommand]:
        """Get the next command for the upcoming TDMA slot."""
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    def expire_before(self, now_us: int) -> list:
        """Remove and return all commands whose deadline has passed."""
        expired = []
        with self._lock:
            while self._queue and self._queue[0].deadline_us < now_us:
                expired.append(self._queue.popleft())
        return expired

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    @property
    def dropped_count(self) -> int:
        return self._dropped_count


# ===================================================================
# SDR data interface
# ===================================================================

class SDRInterface:
    """
    Sends mission-critical command packets through the normal network stack.

    The Openwifi driver maps UDP/TCP port 10000 to the TDMA data queue. Slot
    timing is handled in the driver; the bridge never writes command payloads
    to /dev/my_misc, which is reserved for slot-allocation configuration.
    """

    def __init__(self, target_host: str, target_port: int = 10000):
        self.target_host = target_host
        self.target_port = target_port
        self._sock: Optional[socket.socket] = None

    def open(self):
        """Open the UDP socket used for command transmission."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_at_time(self, payload: bytes, target_time_us: int,
                     slot_id: int) -> bool:
        """
        Send a command packet. target_time_us and slot_id are retained for API
        compatibility; timestamp selection is performed by the Openwifi driver.
        """
        if self._sock is None:
            self.open()
        try:
            self._sock.sendto(payload, (self.target_host, self.target_port))
            return True
        except OSError as e:
            print(f"[tdma_bridge] TX failed: {e}")
            return False

    def get_current_tsf(self) -> int:
        """Return a local monotonic timestamp in microseconds for deadlines."""
        return int(time.monotonic() * 1_000_000)

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None


# ===================================================================
# Main TDMA-ROS Bridge
# ===================================================================

class TDMAROSBridge:
    """
    Core bridge that connects ROS control topics to the TDMA slot scheduler
    and SDR packet injection.
    """

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.role = args.role
        self.robot_id = args.robot_id

        # Components
        self.tdma_client = TDMAManagementClient(
            server_host=args.sdr_ip,
            server_port=args.sdr_port,
            robot_id=args.robot_id,
            role=args.role,
        )
        self.cmd_queue = TDMACommandQueue(max_queue_len=args.queue_len)
        self.sdr = SDRInterface(
            target_host=args.tx_host or args.sdr_ip,
            target_port=args.tx_port,
        )

        # State
        self.current_frame: Optional[TDMAFrame] = None
        self._running = False
        self._slot_thread: Optional[threading.Thread] = None
        self._stats = {
            "tx_total": 0, "tx_success": 0,
            "missed_deadline": 0, "queued_dropped": 0,
        }

    # ---- ROS callbacks ----
    def _cmd_vel_callback(self, msg: Twist):
        """Called when a new velocity command is published."""
        now_us = self.sdr.get_current_tsf()
        deadline_us = now_us + int(self.args.deadline_ms * 1000)

        # Serialise Twist to compact binary (linear.x, angular.z)
        payload = struct.pack("<ff", msg.linear.x, msg.angular.z)

        seq = self.cmd_queue.enqueue(
            topic="/cmd_vel", payload=payload,
            deadline_us=deadline_us, created_us=now_us,
        )

        if HAS_ROS:
            rospy.logdebug(f"[tdma_bridge] Queued cmd_vel seq={seq} "
                           f"deadline={deadline_us}us")

    # ---- Slot scheduling thread ----
    def _slot_worker(self):
        """Dequeue commands and transmit via SDR interface.

        The FPGA hardware handles slot timing; this thread simply sends
        commands through the UDP data port as they become available.
        """
        print("[tdma_bridge] Slot worker started.")
        slot_id = 0
        while self._running:
            now_us = self.sdr.get_current_tsf()

            # Expire overdue commands
            expired = self.cmd_queue.expire_before(now_us)
            self._stats["missed_deadline"] += len(expired)
            self._stats["queued_dropped"] = self.cmd_queue.dropped_count
            for cmd in expired:
                print(f"[tdma_bridge] MISSED DEADLINE seq={cmd.seq} "
                      f"topic={cmd.topic}")

            # Dequeue and send next command
            cmd = self.cmd_queue.dequeue()
            if cmd is not None:
                success = self.sdr.send_at_time(
                    payload=cmd.payload,
                    target_time_us=0,
                    slot_id=slot_id,
                )
                self._stats["tx_total"] += 1
                if success:
                    self._stats["tx_success"] += 1
                slot_id = (slot_id + 1) % 10

            time.sleep(0.001)

    # ---- Public API ----
    def start(self):
        """Start the bridge: connect TDMA server, open SDR, launch threads."""
        print(f"[tdma_bridge] Starting (role={self.role}, "
              f"robot_id={self.robot_id})")

        # Connect to TDMA management and receive slot config
        if not self.tdma_client.connect_and_configure():
            print("[tdma_bridge] ERROR: Failed to configure TDMA slots")
            return

        # Open SDR interface
        self.sdr.open()

        # Start slot worker thread
        self._running = True
        self._slot_thread = threading.Thread(target=self._slot_worker,
                                             daemon=True, name="slot-worker")
        self._slot_thread.start()

        # Start ROS node if available
        if HAS_ROS and self.args.use_ros:
            rospy.init_node("tdma_bridge", anonymous=True, disable_signals=True)
            rospy.Subscriber("/cmd_vel", Twist, self._cmd_vel_callback,
                             queue_size=1)
            print("[tdma_bridge] ROS node initialized, subscribed to /cmd_vel")
        elif self.args.use_ros:
            print("[tdma_bridge] WARNING: ROS not found; running without ROS subscribers.")

        print("[tdma_bridge] Bridge running. Press Ctrl+C to stop.")

        # Main loop: keep alive
        try:
            while self._running:
                if HAS_ROS and self.args.use_ros and not rospy.is_shutdown():
                    rospy.sleep(0.1)
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Graceful shutdown."""
        print("[tdma_bridge] Shutting down...")
        self._running = False
        if self._slot_thread:
            self._slot_thread.join(timeout=2.0)
        self.tdma_client.close()
        self.sdr.close()
        print(f"[tdma_bridge] Stats: {json.dumps(self._stats, indent=2)}")

    def get_stats(self) -> dict:
        return dict(self._stats)


# ===================================================================
# CLI entry point
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description="TDMA-ROS Bridge - Integrates TDMA slot scheduling "
                    "with ROS robotic control and SDR packet injection.")

    # Role
    parser.add_argument("--role", choices=["ap", "sta"], default="sta",
                        help="Node role label for logs. Run TDMA_server.py separately on the AP.")

    # Networking
    parser.add_argument("--sdr-ip", default="192.168.13.1",
                        help="IP of the TDMA management server (default: 192.168.13.1).")
    parser.add_argument("--sdr-port", type=int, default=9999,
                        help="TCP port of TDMA management server (default: 9999).")

    # Robot identity
    parser.add_argument("--robot-id", type=int, default=1,
                        help="Unique robot ID for slot assignment (default: 1).")

    # Data plane
    parser.add_argument("--tx-host", default=None,
                        help="UDP destination for command packets (default: --sdr-ip).")
    parser.add_argument("--tx-port", type=int, default=10000,
                        help="UDP destination port mapped to TDMA data queue (default: 10000).")

    # Deadlines
    parser.add_argument("--deadline-ms", type=float, default=100.0,
                        help="Command deadline in milliseconds (default: 100).")
    parser.add_argument("--queue-len", type=int, default=32,
                        help="Max command queue length (default: 32).")

    # ROS
    parser.add_argument("--use-ros", action="store_true", default=True,
                        help="Enable ROS integration (default: True).")
    parser.add_argument("--no-ros", action="store_false", dest="use_ros",
                        help="Disable ROS subscribers and run only the bridge loop.")

    args = parser.parse_args()

    bridge = TDMAROSBridge(args)
    bridge.start()


if __name__ == "__main__":
    main()

