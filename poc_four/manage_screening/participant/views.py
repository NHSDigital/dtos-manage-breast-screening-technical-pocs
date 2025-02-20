from django.shortcuts import render
from .models import Participant

def index(request):
    participants = Participant.objects.all()

    headers = ["NHS number", "First name", "Last name", "Date of birth",]
    rows = [[participant.nhs_number, participant.first_name, participant.last_name, participant.date_of_birth] for participant in participants]

    return render(request, "participant/index.jinja",
                  {"headers": headers, "rows": rows})
