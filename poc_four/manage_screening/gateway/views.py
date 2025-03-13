from django.shortcuts import render
from gateway.forms import ScreeningOrderGatewayMessageForm
from django.http import HttpResponse
from django.shortcuts import redirect
from gateway.models import Message
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.exceptions import SuspiciousOperation


def create(request):
    if request.method == "POST":
        form = ScreeningOrderGatewayMessageForm(request.POST)
        success_url = request.POST.get('success_url')

        if not (url_has_allowed_host_and_scheme(success_url, allowed_hosts={request.get_host()})):
            raise SuspiciousOperation("Invalid redirect URL: URL must be from the same host.")

        if form.is_valid():
            form.save()
            return redirect(success_url)
        else:
            return HttpResponse("Form is not valid")

def get(request, gateway_id):
    messages = Message.objects.filter(gateway_id=gateway_id, delivered_at__isnull=True)
    response_data = [
            {
                "message_id": msg.id,
                "type": msg.type,
                "payload": msg.payload,
                "destination": msg.destination
            } for msg in messages]
    #mark them all delivered
    messages.update(delivered_at=timezone.now())
    return JsonResponse(response_data, safe=False)

@csrf_exempt # Disable CSRF protection for this view. In production we'd split these endpoints into separate apps that require some machine authentication and use the rest framework
def confirm(request, gateway_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

        message_id = data.get("message_id")

        print(f"Message ID: {message_id}")
        if message_id:
            message = Message.objects.get(id=message_id)
            message.confirmed_at = timezone.now()
            message.save()
            return JsonResponse({"message_id": message_id})
    return HttpResponse(status=400)
