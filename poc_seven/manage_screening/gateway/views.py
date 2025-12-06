from django.shortcuts import redirect
from gateway.forms import ScreeningOrderGatewayActionForm
from django.http import HttpResponse, JsonResponse
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

            # Return JSON for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'redirect_url': success_url})

            return redirect(success_url)
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            return HttpResponse("Form is not valid")


