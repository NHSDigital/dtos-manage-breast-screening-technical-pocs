from django.contrib import admin
from .models import Gateway, Setting, GatewayAction, Study, Series, Image

admin.site.register(Gateway)
admin.site.register(Setting)
admin.site.register(GatewayAction)
admin.site.register(Study)
admin.site.register(Series)
admin.site.register(Image)

