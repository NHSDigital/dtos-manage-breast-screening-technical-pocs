from django.contrib import admin
from .models import Gateway, Setting, Message

admin.site.register(Gateway)
admin.site.register(Setting)
admin.site.register(Message)

