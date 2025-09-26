import json
# Attempt to import Channels; provide a harmless fallback if not installed.
try:
    from channels.generic.websocket import AsyncWebsocketConsumer  # type: ignore
except ImportError:  # Fallback when django-channels is not installed / websockets unused
    class AsyncWebsocketConsumer:  # type: ignore
        channel_layer = None
        async def accept(self): pass
        async def close(self, code=None): pass
        async def send(self, *args, **kwargs): pass

from typing import Any, Dict

class UpdatesConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for pushing real‑time updates.

    Client -> Server message contract (JSON):
      {
        "action": "ping" | "broadcast" | "join" | "leave",
        "channel": "optional-alt-group-name",
        "payload": { ... arbitrary ... }
      }
    Anything not JSON will be echoed back inside {message: <raw>} for convenience.
    """
    DEFAULT_GROUP = 'updates'

    async def connect(self):  # type: ignore[override]
        # Reject if channel layer misconfigured
        if self.channel_layer is None:
            await self.close(code=4001)
            return
        await self.channel_layer.group_add(self.DEFAULT_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "group": self.DEFAULT_GROUP})

    async def disconnect(self, code):  # type: ignore[override]
        if self.channel_layer is not None:
            await self.channel_layer.group_discard(self.DEFAULT_GROUP, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):  # type: ignore[override]
        if text_data is None and bytes_data is not None:
            # Treat raw bytes as text if UTF-8, else ignore
            try:
                text_data = bytes_data.decode('utf-8')
            except Exception:
                return

        if text_data is None:
            return

        # Try to parse JSON
        try:
            data = json.loads(text_data)
            if not isinstance(data, dict):
                raise ValueError('Root not object')
        except Exception:
            # Echo raw text
            await self.send_json({"ok": True, "echo": {"message": text_data}})
            return

        action = str(data.get('action', '')).lower()
        payload: Dict[str, Any] = data.get('payload') or {}
        group = data.get('channel') or self.DEFAULT_GROUP

        # Join/Leave additional dynamic groups
        if action == 'join' and self.channel_layer is not None:
            await self.channel_layer.group_add(group, self.channel_name)
            await self.send_json({"ok": True, "joined": group})
            return
        if action == 'leave' and self.channel_layer is not None:
            await self.channel_layer.group_discard(group, self.channel_name)
            await self.send_json({"ok": True, "left": group})
            return

        if action == 'ping':
            await self.send_json({"type": "pong", "echo": payload})
            return

        if action == 'broadcast' and self.channel_layer is not None:
            await self.channel_layer.group_send(
                group,
                {
                    'type': 'broadcast',  # triggers self.broadcast
                    'payload': {
                        'type': 'update',
                        'group': group,
                        'data': payload,
                    }
                }
            )
            await self.send_json({"ok": True, "sent": True, "group": group})
            return

        # Default: acknowledge
        await self.send_json({"ok": True, "received": data})

    async def broadcast(self, event):
        # Fired by group_send with type 'broadcast'
        payload = event.get('payload', {})
        await self.send_json(payload)

    # Helper -------------------------------------------------
    async def send_json(self, data: Dict[str, Any]):
        try:
            await self.send(text_data=json.dumps(data, separators=(',', ':'), ensure_ascii=False))
        except Exception:  # swallow send errors to avoid crashing consumer
            pass
