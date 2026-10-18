from django import forms

from .models import Room


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Room name", "maxlength": 80}),
            "description": forms.TextInput(attrs={"placeholder": "What's it about? (optional)"}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if len(name) < 2:
            raise forms.ValidationError("Room name needs at least 2 characters.")
        if Room.objects.filter(name__iexact=name, is_private=False).exists():
            raise forms.ValidationError("A room with that name already exists.")
        return name
