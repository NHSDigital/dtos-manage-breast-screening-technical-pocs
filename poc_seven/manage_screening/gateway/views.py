from django.shortcuts import redirect
from gateway.forms import ScreeningOrderGatewayActionForm
from django.http import HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.exceptions import SuspiciousOperation


def create(request):
    if request.method == "POST":
        form = ScreeningOrderGatewayActionForm(request.POST)
        success_url = request.POST.get('success_url')

        if not (url_has_allowed_host_and_scheme(success_url, allowed_hosts={request.get_host()})):
            raise SuspiciousOperation("Invalid redirect URL: URL must be from the same host.")

        if form.is_valid():
            form.save()
            return redirect(success_url)
        else:
            return HttpResponse("Form is not valid")


