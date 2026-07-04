#!/usr/bin/env python3
"""
TDMA Network API - client library for the hybrid TDMA/CSMA protocol.

Matches the wire protocol of TDMA_server.py (newline-delimited text).
Provides a clean Python interface for:
  - Connecting to the TDMA server and receiving slot configuration
  - Querying slot assignments
  - Sending timestamped packets aligned with TDMA slots

Usage:
    from tdma_api import TDMAClient

    client = TDMAClient(server_host="192.168.13.1")
    client.connect_and_configure()

    for slot in client.slots:
        if slot.allocated_to == client.node_id:
            print(f"Slot {slot.slot_id} at {slot.start_us}us")
"""

import logging
import socket
import struct
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("tdma_api")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TDMASlot:
    """A single TDMA time slot assignment."""
    slot_id: int
    allocated_to: int = -1    # robot ID (-1 = unassigned)
    start_us: int = 0         # start time in microseconds (TSF timer)
    duration_us: int = 0      # slot duration in microseconds

    def is_active(self, current_us: int) -> bool:
        """Check if this slot is currently active at the given TSF time."""
        return self.start_us <= current_us < (self.start_us + self.duration_us)


@dataclass
class TDMAConfig:
    """Parsed TDMA slot configuration for one node."""
    node_id: int
    session1_slots: List[int] = field(default_factory=list)
    session2_slots: List[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TDMA Client
# ---------------------------------------------------------------------------

class TDMAClient:
    """
    Client for the TDMA slot configuration server.

    Connects to TDMA_server.py, receives slot assignments via the
    newline-delimited text protocol, and provides helpers for
    timestamped packet transmission via the FPGA misc device.

    Parameters
    ----------
    server_host : str
        IP address of the TDMA server (AP).
    server_port : int
        TCP port (default: 9999).
    misc_device : str or None
        Path to the TDMA misc device (default: /dev/my_misc).
        Set to None for dry-run mode.
    """

    TOTAL_SLOTS = 30
    SESSION1_SLOTS = 6
    SESSION2_SLOTS = 4
    SESSION1_DRIVER_OFFSET = 1
    SESSION2_DRIVER_OFFSET = 20

    def __init__(self, server_host: str = "192.168.13.1",
                 server_port: int = 9999,
                 misc_device: Optional[str] = "/dev/my_misc"):
        self.server_host = server_host
        self.server_port = server_port
        self.misc_device = misc_device
        self.config: Optional[TDMAConfig] = None
        self._sock: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Connection & configuration
    # ------------------------------------------------------------------

    def connect_and_configure(self, timeout: float = 10.0) -> bool:
        """Connect to the TDMA server and receive slot configuration.

        Returns True on success, False on failure.
        """
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(timeout)
            self._sock.connect((self.server_host, self.server_port))

            node_id_str = self._recv_line()
            if not node_id_str:
                logger.error("No node ID received")
                return False
            node_id = int(node_id_str)

            s1_str = self._recv_line()
            s1_slots = [int(s) for s in s1_str.split()] if s1_str else []

            s2_str = self._recv_line()
            s2_slots = [int(s) for s in s2_str.split()] if s2_str else []

            self.config = TDMAConfig(
                node_id=node_id,
                session1_slots=s1_slots,
                session2_slots=s2_slots,
            )
            self._sock.close()
            self._sock = None

            logger.info("Configured node %d: s1=%s s2=%s",
                        node_id, s1_slots, s2_slots)
            return True

        except (socket.timeout, ConnectionRefusedError, OSError, ValueError) as e:
            logger.error("Configuration failed: %s", e)
            self._cleanup()
            return False

    def disconnect(self):
        """Close the connection if still open."""
        self._cleanup()

    # ------------------------------------------------------------------
    # Slot queries
    # ------------------------------------------------------------------

    @property
    def node_id(self) -> Optional[int]:
        """Return the assigned node ID, or None if not configured."""
        return self.config.node_id if self.config else None

    @property
    def slots(self) -> List[TDMASlot]:
        """Return all slot assignments as TDMASlot objects.

        Session-1 slots (TDMA data) are indices 0..5.
        Session-2 slots (control) are indices 6..9.
        """
        if not self.config:
            return []
        result = []
        for idx in self.config.session1_slots:
            result.append(TDMASlot(
                slot_id=idx, allocated_to=self.config.node_id,
            ))
        for idx in self.config.session2_slots:
            result.append(TDMASlot(
                slot_id=idx + self.SESSION1_SLOTS,
                allocated_to=self.config.node_id,
            ))
        return result

    def has_slot(self, slot_index: int) -> bool:
        """Check if this node owns a specific slot index."""
        if not self.config:
            return False
        all_slots = (self.config.session1_slots +
                     [s + self.SESSION1_SLOTS for s in self.config.session2_slots])
        return slot_index in all_slots

    def bitmap_value(self) -> int:
        """Compute the FPGA register bitmap for this node's slot assignment."""
        if not self.config:
            return 0
        bitmap = [0] * self.TOTAL_SLOTS
        for idx in self.config.session1_slots:
            if 0 <= idx < self.SESSION1_SLOTS:
                bitmap[self.SESSION1_DRIVER_OFFSET + idx] = 1
        for idx in self.config.session2_slots:
            if 0 <= idx < self.SESSION2_SLOTS:
                bitmap[self.SESSION2_DRIVER_OFFSET + idx] = 1
        value = 0
        for idx, bit in enumerate(bitmap):
            if bit:
                value |= (1 << idx)
        return value

    # ------------------------------------------------------------------
    # Packet transmission
    # ------------------------------------------------------------------

    def send_in_slot(self, slot_id: int, payload: bytes,
                     target_time_us: int = 0) -> bool:
        """Queue a packet for transmission in a specific TDMA slot.

        Parameters
        ----------
        slot_id : int
            The TDMA slot to use.
        payload : bytes
            Raw payload bytes.
        target_time_us : int
            Target TSF transmission time (0 = immediate).

        Returns True if queued successfully.
        """
        if self.misc_device is None:
            logger.info("DRY-RUN: slot=%d len=%d", slot_id, len(payload))
            return True

        header = struct.pack("<II", target_time_us, slot_id)
        packet = header + payload
        try:
            with open(self.misc_device, "wb") as f:
                f.write(packet)
            return True
        except OSError as e:
            logger.error("Send failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.connect_and_configure()
        return self

    def __exit__(self, *args):
        self.disconnect()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _recv_line(self) -> str:
        """Read a newline-delimited line from the socket."""
        buf = b''
        while True:
            ch = self._sock.recv(1)
            if not ch or ch == b'\n':
                break
            buf += ch
        return buf.decode().strip()

    def _cleanup(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def quick_connect(server_host: str = "192.168.13.1",
                  server_port: int = 9999) -> TDMAClient:
    """One-line connect + configure. Returns a configured TDMAClient."""
    client = TDMAClient(server_host=server_host, server_port=server_port)
    if not client.connect_and_configure():
        raise ConnectionError(f"Could not configure via {server_host}:{server_port}")
    return client

