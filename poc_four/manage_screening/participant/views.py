from django.shortcuts import render
from .models import Details

def index(request):
    details = Details.objects.all()

    headers = ["NHS number", "First name", "Last name", "Date of birth",]
    rows = [[detail.nhs_number, detail.first_name, detail.last_name, detail.date_of_birth] for detail in details]
    return render(request, "participant/index.jinja",
                  {"headers": headers, "rows": rows})
