from django.middleware.csrf import get_token
from django.shortcuts import render
from .models import Participant
from gateway.forms import ScreeningOrderGatewayMessageForm      
from gateway.models import Gateway

def index(request):
    participants = Participant.objects.all()
    
    csrf_token = get_token(request)
    headers = ["NHS number", "First name", "Last name", "Date of birth", ""]
    rows = [
                [
                    {"text": participant.nhs_number}, 
                    {"text": participant.first_name}, 
                    {"text": participant.last_name}, 
                    {"text": participant.date_of_birth}, 
                    {"html": form_for(participant.id, csrf_token)}
                ] for participant in participants
            ]
    
    return render(request, "participant/index.jinja",
                  {"headers": headers, "rows": rows})

def form_for(participant_id, csrf_token):
    gateway_id = Gateway.objects.last().id # we'd need to think about how we get the correct gateway Id. Is there more than one per trust?
    form = ScreeningOrderGatewayMessageForm(initial={"participant_id": participant_id, "gateway_id": gateway_id})
    fields = "".join(str(field) for field in form)

    #render the fields with a button
    return  f"""
            <form method='post' action='/gateway-messages/screening-order/'>
                <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}"/>
                { fields }
                <button type='submit' class="nhsuk-button">Send to modality</button>
            </form>
            """
