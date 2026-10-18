"""
WebSocket consumer: one instance per open socket.

Flow for a chat message:
  browser --ws--> ChatConsumer.receive_json
          --> moderate + rate-limit --> save Message (PostgreSQL)
          --> channel_layer.group_send("room_<id>")  (Redis fan-out)
          --> every ChatConsumer in that room --> chat_message --> browser
"""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import Connection, Membership, Message, Room
from .moderation import RateLimiter, moderate

CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.room = None
        if not self.user.is_authenticated:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        slug = self.scope["url_route"]["kwargs"]["slug"]
        self.room = await self.get_room(slug)
        if self.room is None:
            await self.close(code=CLOSE_NOT_FOUND)
            return
        if not await self.join_room():
            self.room = None
            await self.close(code=CLOSE_FORBIDDEN)
            return

        self.limiter = RateLimiter()
        await self.channel_layer.group_add(self.room.group_name, self.channel_name)
        await self.accept()
        await self.add_connection()
        await self.broadcast_presence()

    async def disconnect(self, code):
        if self.room is None:
            return
        await self.remove_connection()
        await self.channel_layer.group_send(
            self.room.group_name,
            {"type": "chat.typing", "user": self.user.username, "is_typing": False, "sender": self.channel_name},
        )
        await self.channel_layer.group_discard(self.room.group_name, self.channel_name)
        await self.broadcast_presence()

    # --- Messages from the browser ---------------------------------------------
    async def receive_json(self, content, **kwargs):
        kind = content.get("type") if isinstance(content, dict) else None
        if kind == "message":
            await self.handle_message(content.get("content"))
        elif kind == "typing":
            await self.channel_layer.group_send(
                self.room.group_name,
                {
                    "type": "chat.typing",
                    "user": self.user.username,
                    "is_typing": bool(content.get("is_typing")),
                    "sender": self.channel_name,
                },
            )
        elif kind == "read":
            await self.mark_read()
        else:
            await self.send_error("Unknown event type.")

    async def handle_message(self, raw):
        if not self.limiter.allow():
            await self.send_error("You're sending messages too fast. Slow down a little.")
            return
        result = moderate(raw)
        if not result.ok:
            await self.send_error(result.error)
            return
        payload = await self.save_message(result.text, result.flagged)
        await self.channel_layer.group_send(self.room.group_name, {"type": "chat.message", "payload": payload})

    async def send_error(self, message):
        await self.send_json({"type": "error", "message": message})

    # --- Events from the channel layer (group_send) ----------------------------
    async def chat_message(self, event):
        await self.send_json(event["payload"])

    async def chat_typing(self, event):
        if event["sender"] != self.channel_name:  # don't echo to the typist
            await self.send_json({"type": "typing", "user": event["user"], "is_typing": event["is_typing"]})

    async def chat_presence(self, event):
        await self.send_json({"type": "presence", "online": event["online"]})

    async def broadcast_presence(self):
        online = await self.get_online()
        await self.channel_layer.group_send(self.room.group_name, {"type": "chat.presence", "online": online})

    # --- Database access (sync ORM wrapped for async) --------------------------
    @database_sync_to_async
    def get_room(self, slug):
        return Room.objects.filter(slug=slug).first()

    @database_sync_to_async
    def join_room(self):
        if not self.room.can_access(self.user):
            return False
        Membership.objects.get_or_create(room=self.room, user=self.user)
        return True

    @database_sync_to_async
    def add_connection(self):
        Connection.objects.update_or_create(
            channel_name=self.channel_name, defaults={"user": self.user, "room": self.room}
        )

    @database_sync_to_async
    def remove_connection(self):
        Connection.objects.filter(channel_name=self.channel_name).delete()

    @database_sync_to_async
    def get_online(self):
        return Connection.online_usernames(self.room.pk)

    @database_sync_to_async
    def save_message(self, text, flagged):
        message = Message.objects.create(room=self.room, author=self.user, content=text, is_flagged=flagged)
        Membership.objects.filter(room=self.room, user=self.user).update(last_read_at=message.created_at)
        return message.to_payload()

    @database_sync_to_async
    def mark_read(self):
        Membership.objects.filter(room=self.room, user=self.user).update(last_read_at=timezone.now())
