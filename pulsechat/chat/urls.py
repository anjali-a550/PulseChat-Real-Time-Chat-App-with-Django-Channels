from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.home, name="home"),
    path("rooms/new/", views.create_room, name="create_room"),
    path("rooms/<slug:slug>/", views.room, name="room"),
    path("dm/<str:username>/", views.start_dm, name="start_dm"),
    path("api/rooms/<slug:slug>/messages/", views.message_history, name="message_history"),
]
