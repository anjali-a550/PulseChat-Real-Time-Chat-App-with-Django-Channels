from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Room(models.Model):
    """A chat room. Public rooms are open to everyone; private rooms are DMs."""

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)
    is_private = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="rooms_created"
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="Membership", related_name="chat_rooms"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def group_name(self):
        """Name of the Channels group that every socket in this room joins."""
        return f"room_{self.pk}"

    @classmethod
    def unique_slug(cls, name):
        base = slugify(name)[:90] or "room"
        slug, n = base, 2
        while cls.objects.filter(slug=slug).exists():
            slug, n = f"{base}-{n}", n + 1
        return slug

    @classmethod
    def get_or_create_dm(cls, user_a, user_b):
        """Return the one private room shared by two users, creating it if needed."""
        low, high = sorted([user_a.pk, user_b.pk])
        slug = f"dm-{low}-{high}"
        room, created = cls.objects.get_or_create(
            slug=slug,
            defaults={"name": f"{user_a.username} & {user_b.username}", "is_private": True, "created_by": user_a},
        )
        if created:
            Membership.objects.bulk_create(
                [Membership(room=room, user=user_a), Membership(room=room, user=user_b)]
            )
        return room

    def can_access(self, user):
        if not user.is_authenticated:
            return False
        if not self.is_private:
            return True
        return self.memberships.filter(user=user).exists()

    def dm_partner(self, user):
        """For a DM, the other person in it."""
        other = self.memberships.exclude(user=user).select_related("user").first()
        return other.user if other else None


class Membership(models.Model):
    """Links a user to a room and remembers how far they have read."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["room", "user"], name="unique_membership")]

    def __str__(self):
        return f"{self.user} in {self.room}"


class Message(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages")
    content = models.TextField()
    is_flagged = models.BooleanField(default=False, help_text="Moderation masked part of this message.")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["room", "created_at"])]

    def __str__(self):
        return f"{self.author}: {self.content[:40]}"

    def to_payload(self):
        """The JSON shape sent to browsers, over WebSocket and the history API."""
        return {
            "type": "message",
            "id": self.pk,
            "room": self.room_id,
            "author": self.author.username,
            "content": self.content,
            "flagged": self.is_flagged,
            "created_at": self.created_at.isoformat(),
        }


class Connection(models.Model):
    """
    One row per open WebSocket. Presence (who is online in a room) is read from
    this table, so it stays correct across several server processes.
    """

    channel_name = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connections")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="connections")
    connected_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def online_usernames(cls, room_id):
        return sorted(
            set(cls.objects.filter(room_id=room_id).values_list("user__username", flat=True))
        )
