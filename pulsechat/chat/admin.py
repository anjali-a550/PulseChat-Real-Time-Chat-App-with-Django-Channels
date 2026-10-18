from django.contrib import admin

from .models import Connection, Membership, Message, Room


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_private", "created_by", "created_at")
    list_filter = ("is_private",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("room", "author", "short_content", "is_flagged", "created_at")
    list_filter = ("is_flagged", "room")
    search_fields = ("content", "author__username")

    @admin.display(description="Content")
    def short_content(self, obj):
        return obj.content[:60]


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ("user", "room", "connected_at")
