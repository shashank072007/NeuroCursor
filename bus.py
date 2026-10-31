"""Event Bus and Message Sequencing for FLUX Backend.
Provides thread-safe broadcasting to bounded client queues,
maintains per-message-type sequence counters, and provides
latest-of-each-type snapshots on connect (G14).
"""

import time
import queue
import threading
from typing import Dict, Any, List, Set, Tuple

_seq_counters: Dict[str, int] = {}
_seq_lock = threading.Lock()


def next_seq(msg_type: str) -> int:
    """Return the next strictly increasing sequence number for the given message type."""
    with _seq_lock:
        current = _seq_counters.get(msg_type, 0) + 1
        _seq_counters[msg_type] = current
        return current


def make_msg(msg_type: str, **fields) -> Dict[str, Any]:
    """Helper creating a compliant FLUX envelope message.
    Envelope: v=1, type, seq, ts, plus arbitrary payload fields.
    """
    # If ts is already provided (e.g. source capture ts for frame), use it; else current time
    ts = fields.pop("ts", None)
    if ts is None:
        ts = round(time.time(), 3)
    
    # If seq is explicitly provided (e.g. for re-emitted undo actions with same seq), use it
    seq = fields.pop("seq", None)
    if seq is None:
        seq = next_seq(msg_type)

    return {
        "v": 1,
        "type": msg_type,
        "seq": seq,
        "ts": ts,
        **fields
    }


class EventBus:
    """Thread-safe event broadcaster with bounded subscriber queues and snapshot cache."""

    def __init__(self, queue_maxsize: int = 30):
        self.queue_maxsize = queue_maxsize
        self._subscribers: Set[queue.Queue] = set()
        self._latest: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def broadcast(self, msg: Dict[str, Any]) -> None:
        """Broadcast message to all connected subscribers and update snapshot cache."""
        with self._lock:
            # Cache the latest message of this type
            msg_type = msg.get("type", "unknown")
            self._latest[msg_type] = msg

            # Dispatch to subscribers
            dead_subscribers = []
            for q in list(self._subscribers):
                try:
                    if q.full():
                        try:
                            # Drop the oldest message to keep pipe responsive
                            q.get_nowait()
                        except queue.Empty:
                            pass
                    q.put_nowait(msg)
                except Exception:
                    dead_subscribers.append(q)

            for dead in dead_subscribers:
                self._subscribers.discard(dead)

    def subscribe(self) -> Tuple[queue.Queue, List[Dict[str, Any]]]:
        """Register a new SSE subscriber. Returns (queue, snapshot_messages).
        Snapshot contains the latest message of each type (G14).
        """
        q: queue.Queue = queue.Queue(maxsize=self.queue_maxsize)
        with self._lock:
            self._subscribers.add(q)
            # Order snapshot meaningfully if types exist
            type_order = ["status", "ui_state", "channels", "effort", "guard", "action", "frame"]
            snapshot = []
            for t in type_order:
                if t in self._latest:
                    snapshot.append(self._latest[t])
            # Add any other cached types
            for t, msg in self._latest.items():
                if t not in type_order:
                    snapshot.append(msg)
            return q, snapshot

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a disconnected subscriber queue."""
        with self._lock:
            self._subscribers.discard(q)

    def get_latest(self, msg_type: str) -> Any:
        with self._lock:
            return self._latest.get(msg_type)


# Global event bus singleton
bus = EventBus()
