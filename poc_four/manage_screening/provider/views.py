from django.shortcuts import render, get_object_or_404
from provider.models import Clinic, Appointment, AppointmentState
from django.middleware.csrf import get_token
from gateway.models import Gateway
from gateway.forms import ScreeningOrderGatewayMessageForm
from django.template import engines

def clinic_index(request):
    clinics = Clinic.objects.all()
    headers = ["Date", ""]
    rows = [
                [
                    {"text": clinic.date}, 
                    {"html": f'<a href="/clinic/{clinic.id}">Open</a>'}, 
                ] for clinic in clinics
            ]
    return render(request, "clinic/index.jinja", {"clinics": clinics, "headers": headers, "rows": rows})

def get_clinic(request, clinic_id):
    clinic = get_object_or_404(Clinic, id=clinic_id)
    appointments = Appointment.objects.filter(clinic_slot__clinic=clinic).order_by("clinic_slot__start_time")
    
    csrf_token = get_token(request)
    headers = ["Time", "Participant", "Date of birth", ""]
    rows = [
                [
                    {"text": appointment.clinic_slot.start_time},
                    {"text": appointment.participant}, 
                    {"text": appointment.participant.date_of_birth}, 
                    {"html": form_for(appointment.id, csrf_token, request)},
                ] for appointment in appointments
            ]
    
    return render(request, "clinic/show.jinja", 
                  {"clinic": clinic, "headers": headers, "rows": rows})

def form_for(appointment_id, csrf_token, request):
    gateway_id = Gateway.objects.last().id # we'd need to think about how we get the correct gateway Id. Is there more than one per trust?
    appointment = Appointment.objects.get(id=appointment_id)
    form = ScreeningOrderGatewayMessageForm(initial={"appointment_id": appointment_id, "gateway_id": gateway_id})
    fields = "".join(str(field) for field in form)

    previously_sent = appointment.state == AppointmentState.SENT_TO_MODALITY.value

    jinja_engine = engines['jinja2']
    form_template = jinja_engine.env.get_template('components/app/send_to_modality_button.jinja')
    macro = form_template.module.send_to_modality_button
    rendered_html = macro(request.get_full_path(), csrf_token, fields, previously_sent)

    return rendered_html

    # #render the fields with a button
    # return  f"""
    #         <form method='post' action='/gateway-messages/screening-order/'>
    #             <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}"/>
    #             <input type="hidden" name="success_url" value="{ request.get_full_path() }"/>
    #             { fields }
    #             <button type='submit' class="nhsuk-button">Send to modality</button>
    #         </form>
    #         """
