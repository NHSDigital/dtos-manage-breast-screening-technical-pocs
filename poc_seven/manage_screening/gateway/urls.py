from django.urls import path
from .views import create

urlpatterns = [
    path("gateway-actions/screening-order/", create, name="create_screening_order_gateway_action"),
]
