from django.shortcuts import render
from gateway.forms import ScreeningOrderGatewayMessageForm
from django.http import HttpResponse
from django.shortcuts import redirect


def create(request):
    if request.method == "POST":
        form = ScreeningOrderGatewayMessageForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("/")
        else:
            return HttpResponse("Form is not valid")
