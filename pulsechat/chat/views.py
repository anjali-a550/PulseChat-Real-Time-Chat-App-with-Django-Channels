from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import RoomForm
from .models import Membership, Message, Room

User = get_user_model()


def sidebar_context(user, current=None):
    """Rooms, DMs and people for the left sidebar, with unread counts in one query."""
    unread = dict(
        Message.objects.filter(
            room__memberships__user=user,
            created_at__gt=F("room__memberships__last_read_at"),
        )
        .exclude(author=user)
        .values_list("room")
        .annotate(n=Count("id"))
    )
    public_rooms = list(Room.objects.filter(is_private=False))
    dms = list(Room.objects.filter(is_private=True, memberships__user=user).prefetch_related("memberships__user"))
    for room in public_rooms + dms:
        room.unread = 0 if current and room.pk == current.pk else unread.get(room.pk, 0)
    for dm in dms:
        partner = dm.dm_partner(user)
        dm.label = partner.username if partner else dm.name
    return {
        "public_rooms": public_rooms,
        "dms": dms,
        "people": User.objects.exclude(pk=user.pk).order_by("username")[:50],
        "room_form": RoomForm(),
        "current_room": current,
    }


@login_required
def home(request):
    first = Room.objects.filter(is_private=False).first()
    if first:
        return redirect("chat:room", slug=first.slug)
    return render(request, "chat/room.html", sidebar_context(request.user))


@login_required
def room(request, slug):
    room = get_object_or_404(Room, slug=slug)
    if not room.can_access(request.user):
        raise Http404("Room not found")
    Membership.objects.update_or_create(
        room=room, user=request.user, defaults={"last_read_at": timezone.now()}
    )
    page = settings.CHAT_HISTORY_PAGE_SIZE
    recent = list(room.messages.select_related("author").order_by("-id")[: page + 1])
    has_more = len(recent) > page
    history = [m.to_payload() for m in reversed(recent[:page])]
    context = sidebar_context(request.user, current=room)
    context.update(
        {
            "room": room,
            "room_title": room.dm_partner(request.user).username if room.is_private and room.dm_partner(request.user) else room.name,
            "history": history,
            "has_more": has_more,
        }
    )
    return render(request, "chat/room.html", context)


@login_required
@require_POST
def create_room(request):
    form = RoomForm(request.POST)
    if not form.is_valid():
        messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
        return redirect("chat:home")
    room = form.save(commit=False)
    room.slug = Room.unique_slug(room.name)
    room.created_by = request.user
    room.save()
    Membership.objects.create(room=room, user=request.user)
    return redirect("chat:room", slug=room.slug)


@login_required
def start_dm(request, username):
    other = get_object_or_404(User, username=username)
    if other == request.user:
        return redirect("chat:home")
    room = Room.get_or_create_dm(request.user, other)
    return redirect("chat:room", slug=room.slug)


@login_required
@require_GET
def message_history(request, slug):
    """GET /api/rooms/<slug>/messages/?before=<id> — older messages, newest page first."""
    room = get_object_or_404(Room, slug=slug)
    if not room.can_access(request.user):
        return JsonResponse({"error": "not found"}, status=404)
    page = settings.CHAT_HISTORY_PAGE_SIZE
    qs = room.messages.select_related("author").order_by("-id")
    before = request.GET.get("before")
    if before:
        if not before.isdigit():
            return JsonResponse({"error": "before must be a message id"}, status=400)
        qs = qs.filter(id__lt=int(before))
    batch = list(qs[: page + 1])
    return JsonResponse(
        {
            "messages": [m.to_payload() for m in reversed(batch[:page])],
            "has_more": len(batch) > page,
        }
    )


def healthz(request):
    return JsonResponse({"status": "ok"})
