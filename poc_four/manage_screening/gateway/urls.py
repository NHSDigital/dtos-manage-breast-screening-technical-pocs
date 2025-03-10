from django.urls import path
from .views import create, get, confirm

urlpatterns = [
    path("gateway-messages/screening-order/", create, name="create_screening_order_gateway"),
    path("gateway-messages/<uuid:gateway_id>/", get, name="get_gateway_messages"),
    path("gateway-messages/<uuid:gateway_id>/confirmations", confirm, name="confirm_gateway_message")
]
