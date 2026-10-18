"""
WebSocket tests using Channels' WebsocketCommunicator against the in-memory
channel layer. TransactionTestCase is required because the consumer touches
the database from worker threads.
"""
from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client, TransactionTestCase, override_settings

from chat.models import Connection, Message, Room
from chat.routing import websocket_urlpatterns
from config.asgi import application as full_application

User = get_user_model()
router = URLRouter(websocket_urlpatterns)


async def connect(user, slug="general"):
    communicator = WebsocketCommunicator(router, f"/ws/chat/{slug}/")
    communicator.scope["user"] = user
    connected, code = await communicator.connect()
    return communicator, connected, code


async def receive_until(communicator, kind, timeout=1):
    """Skip events of other types (presence, typing) until `kind` arrives."""
    while True:
        event = await communicator.receive_json_from(timeout=timeout)
        if event["type"] == kind:
            return event


class ConsumerTests(TransactionTestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.carol = User.objects.create_user("carol", password="pw")
        Room.objects.get_or_create(slug="general", defaults={"name": "General"})

    async def test_anonymous_is_rejected(self):
        _, connected, code = await connect(AnonymousUser())
        self.assertFalse(connected)
        self.assertEqual(code, 4401)

    async def test_unknown_room_is_rejected(self):
        _, connected, code = await connect(self.alice, slug="nope")
        self.assertFalse(connected)
        self.assertEqual(code, 4404)

    async def test_message_is_saved_and_broadcast_to_everyone(self):
        a, ok_a, _ = await connect(self.alice)
        b, ok_b, _ = await connect(self.bob)
        self.assertTrue(ok_a and ok_b)

        await a.send_json_to({"type": "message", "content": "Hello Bob"})
        for communicator in (a, b):
            event = await receive_until(communicator, "message")
            self.assertEqual(event["author"], "alice")
            self.assertEqual(event["content"], "Hello Bob")
            self.assertFalse(event["flagged"])

        self.assertEqual(await sync_to_async(Message.objects.count)(), 1)
        await a.disconnect()
        await b.disconnect()

    async def test_moderation_masks_before_broadcast(self):
        a, _, _ = await connect(self.alice)
        await a.send_json_to({"type": "message", "content": "you idiot"})
        event = await receive_until(a, "message")
        self.assertEqual(event["content"], "you *****")
        self.assertTrue(event["flagged"])
        await a.disconnect()

    async def test_empty_message_returns_error(self):
        a, _, _ = await connect(self.alice)
        await a.send_json_to({"type": "message", "content": "   "})
        event = await receive_until(a, "error")
        self.assertIn("empty", event["message"])
        await a.disconnect()

    @override_settings(CHAT_RATE_LIMIT_MESSAGES=2, CHAT_RATE_LIMIT_WINDOW=60)
    async def test_rate_limit(self):
        a, _, _ = await connect(self.alice)
        for i in range(3):
            await a.send_json_to({"type": "message", "content": f"spam {i}"})
        await receive_until(a, "error")
        self.assertEqual(await sync_to_async(Message.objects.count)(), 2)
        await a.disconnect()

    async def test_typing_reaches_others_but_not_sender(self):
        a, _, _ = await connect(self.alice)
        b, _, _ = await connect(self.bob)
        await a.send_json_to({"type": "typing", "is_typing": True})
        event = await receive_until(b, "typing")
        self.assertEqual(event, {"type": "typing", "user": "alice", "is_typing": True})
        # alice should only ever see presence events, never her own typing
        while not await a.receive_nothing(timeout=0.2):
            self.assertNotEqual((await a.receive_json_from())["type"], "typing")
        await a.disconnect()
        await b.disconnect()

    async def test_presence_updates_on_join_and_leave(self):
        a, _, _ = await connect(self.alice)
        event = await receive_until(a, "presence")
        self.assertEqual(event["online"], ["alice"])

        b, _, _ = await connect(self.bob)
        event = await receive_until(a, "presence")
        self.assertEqual(event["online"], ["alice", "bob"])

        await b.disconnect()
        event = await receive_until(a, "presence")
        self.assertEqual(event["online"], ["alice"])
        await a.disconnect()
        self.assertEqual(await sync_to_async(Connection.objects.count)(), 0)

    async def test_dm_is_private(self):
        dm = await sync_to_async(Room.get_or_create_dm)(self.alice, self.bob)
        _, ok_bob, _ = await connect(self.bob, slug=dm.slug)
        _, ok_carol, code = await connect(self.carol, slug=dm.slug)
        self.assertTrue(ok_bob)
        self.assertFalse(ok_carol)
        self.assertEqual(code, 4403)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class FullStackAuthTests(TransactionTestCase):
    """Goes through the real ASGI app: origin check + session cookie auth."""

    def setUp(self):
        User.objects.create_user("alice", password="pw-alice-123")
        Room.objects.get_or_create(slug="general", defaults={"name": "General"})
        client = Client()
        client.login(username="alice", password="pw-alice-123")
        self.cookie = f"sessionid={client.cookies['sessionid'].value}".encode()

    async def test_logged_in_session_can_connect(self):
        communicator = WebsocketCommunicator(
            full_application, "/ws/chat/general/",
            headers=[(b"origin", b"http://localhost"), (b"cookie", self.cookie)],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_foreign_origin_is_blocked(self):
        communicator = WebsocketCommunicator(
            full_application, "/ws/chat/general/",
            headers=[(b"origin", b"http://evil.example"), (b"cookie", self.cookie)],
        )
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
