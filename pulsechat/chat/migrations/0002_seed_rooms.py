from django.db import migrations

ROOMS = [
    ("General", "general", "Company-wide chatter and announcements"),
    ("Python", "python", "Django, async, and everything Python"),
    ("Random", "random", "Memes, music and off-topic"),
]


def create_rooms(apps, schema_editor):
    Room = apps.get_model("chat", "Room")
    for name, slug, description in ROOMS:
        Room.objects.get_or_create(slug=slug, defaults={"name": name, "description": description})


def remove_rooms(apps, schema_editor):
    apps.get_model("chat", "Room").objects.filter(slug__in=[s for _, s, _ in ROOMS]).delete()


class Migration(migrations.Migration):
    dependencies = [("chat", "0001_initial")]
    operations = [migrations.RunPython(create_rooms, remove_rooms)]
