from django.urls import path
from .views import create

urlpatterns = [
    path("gateway-messages/screening-order/", create, name="create_screening_order_gateway"),
]
