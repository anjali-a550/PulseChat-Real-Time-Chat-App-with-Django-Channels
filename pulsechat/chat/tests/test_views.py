from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from chat.models import Membership, Message, Room

User = get_user_model()


class ViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-alice-123")
        self.bob = User.objects.create_user("bob", password="pw-bob-123")
        self.carol = User.objects.create_user("carol", password="pw-carol-123")
        self.general = Room.objects.get(slug="general")  # created by the seed migration

    def test_login_required(self):
        response = self.client.get(reverse("chat:room", args=["general"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_signup_logs_in_and_redirects(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "dave", "password1": "s3cure-Passw0rd!", "password2": "s3cure-Passw0rd!"},
        )
        self.assertRedirects(response, reverse("chat:home"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="dave").exists())

    def test_room_page_renders_history_and_joins(self):
        Message.objects.create(room=self.general, author=self.bob, content="hi alice")
        self.client.force_login(self.alice)
        response = self.client.get(reverse("chat:room", args=["general"]))
        self.assertContains(response, "hi alice")
        self.assertTrue(Membership.objects.filter(room=self.general, user=self.alice).exists())

    def test_create_room(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("chat:create_room"), {"name": "Django Devs", "description": "talk"})
        room = Room.objects.get(name="Django Devs")
        self.assertRedirects(response, reverse("chat:room", args=[room.slug]), fetch_redirect_response=False)
        self.assertEqual(room.slug, "django-devs")

    def test_duplicate_room_name_rejected(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("chat:create_room"), {"name": "general"})
        self.assertEqual(Room.objects.filter(name__iexact="general").count(), 1)

    def test_dm_is_created_once_and_private(self):
        self.client.force_login(self.alice)
        self.client.get(reverse("chat:start_dm", args=["bob"]))
        self.client.get(reverse("chat:start_dm", args=["bob"]))
        dm = Room.objects.get(is_private=True)
        self.assertEqual(Room.objects.filter(is_private=True).count(), 1)
        self.client.force_login(self.carol)
        response = self.client.get(reverse("chat:room", args=[dm.slug]))
        self.assertEqual(response.status_code, 404)

    def test_unread_count_in_sidebar(self):
        self.client.force_login(self.alice)
        self.client.get(reverse("chat:room", args=["general"]))  # alice reads general
        Message.objects.create(room=self.general, author=self.bob, content="one")
        Message.objects.create(room=self.general, author=self.bob, content="two")
        python = Room.objects.get(slug="python")
        response = self.client.get(reverse("chat:room", args=[python.slug]))
        general = next(r for r in response.context["public_rooms"] if r.slug == "general")
        self.assertEqual(general.unread, 2)

    @override_settings(CHAT_HISTORY_PAGE_SIZE=2)
    def test_history_api_pages_backwards(self):
        ids = [Message.objects.create(room=self.general, author=self.bob, content=f"m{i}").pk for i in range(5)]
        self.client.force_login(self.alice)
        url = reverse("chat:message_history", args=["general"])
        page = self.client.get(url, {"before": ids[4]}).json()
        self.assertEqual([m["content"] for m in page["messages"]], ["m2", "m3"])
        self.assertTrue(page["has_more"])
        last = self.client.get(url, {"before": ids[1]}).json()
        self.assertEqual([m["content"] for m in last["messages"]], ["m0"])
        self.assertFalse(last["has_more"])

    def test_history_api_blocks_outsiders_of_dm(self):
        dm = Room.get_or_create_dm(self.alice, self.bob)
        self.client.force_login(self.carol)
        response = self.client.get(reverse("chat:message_history", args=[dm.slug]))
        self.assertEqual(response.status_code, 404)

    def test_healthz(self):
        self.assertEqual(self.client.get("/healthz/").json(), {"status": "ok"})
