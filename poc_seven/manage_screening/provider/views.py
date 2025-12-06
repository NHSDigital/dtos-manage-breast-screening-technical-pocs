from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from provider.models import Clinic, Appointment, AppointmentState
from django.middleware.csrf import get_token
from gateway.models import Gateway
from gateway.forms import ScreeningOrderGatewayActionForm
from django.template import engines
from django.utils import timezone
import json
import time
from datetime import timedelta

def clinic_index(request):
    clinics = Clinic.objects.all()
    headers = ["Date", ""]
    rows = [
                [
                    {"text": clinic.date.strftime('%d/%m/%Y')},
                    {"html": f'<a href="/clinic/{clinic.id}">Open</a>'},
                ] for clinic in clinics
            ]
    return render(request, "clinic/index.jinja", {"clinics": clinics, "headers": headers, "rows": rows})

def get_clinic(request, clinic_id):
    clinic = get_object_or_404(Clinic, id=clinic_id)
    appointments = Appointment.objects.filter(clinic_slot__clinic=clinic).order_by("clinic_slot__start_time")

    csrf_token = get_token(request)
    headers = ["Time", "Participant", "Date of birth", "Status", ""]
    rows = [
                [
                    {"text": appointment.clinic_slot.start_time.strftime('%H:%M')},
                    {"html": f'<a href="/clinic/{clinic.id}/appointment/{appointment.id}">{appointment.participant}</a>'},
                    {"text": appointment.participant.date_of_birth.strftime('%d/%m/%Y')},
                    {"html": f'<span class="appointment-status" data-appointment-id="{appointment.id}">{format_status(appointment.state)}</span>'},
                    {"html": form_for(appointment.id, csrf_token, request)},
                ] for appointment in appointments
            ]

    return render(request, "clinic/show.jinja",
                  {"clinic": clinic, "headers": headers, "rows": rows})

def format_status(state):
    """Format appointment state for display"""
    status_map = {
        'pending': ('Pending', 'nhsuk-tag--grey'),
        'arrived': ('Arrived', 'nhsuk-tag--blue'),
        'checked_in': ('Checked In', 'nhsuk-tag--blue'),
        'sent_to_modality': ('Sent to Modality', 'nhsuk-tag--purple'),
        'in_progress': ('In Progress', 'nhsuk-tag--yellow'),
        'complete': ('Complete', 'nhsuk-tag--green'),
        'cancelled': ('Cancelled', 'nhsuk-tag--red'),
    }
    label, tag_class = status_map.get(state, (state.replace('_', ' ').title(), ''))
    return f'<strong class="nhsuk-tag {tag_class}">{label}</strong>'

def appointment_statuses(request, clinic_id):
    """API endpoint to get current appointment statuses for a clinic"""
    clinic = get_object_or_404(Clinic, id=clinic_id)
    appointments = Appointment.objects.filter(clinic_slot__clinic=clinic)

    statuses = {
        str(appointment.id): {
            'state': appointment.state,
            'html': format_status(appointment.state)
        }
        for appointment in appointments
    }

    return JsonResponse(statuses)

def get_appointment(request, clinic_id, appointment_id):
    """View for individual appointment detail page"""
    from gateway.models import Study, Image
    from collections import defaultdict

    clinic = get_object_or_404(Clinic, id=clinic_id)
    appointment = get_object_or_404(Appointment, id=appointment_id, clinic_slot__clinic=clinic)

    # Get all images for this appointment
    images = Image.objects.filter(
        series__study__appointment=appointment
    ).select_related('series__study').order_by('series__series_instance_uid', 'instance_number', 'received_at')

    # Group images by laterality, then by series
    images_by_laterality = defaultdict(lambda: defaultdict(list))

    for image in images:
        laterality = image.laterality.upper() if image.laterality else 'UNKNOWN'
        series_id = image.series.id
        view_position = image.view_position if image.view_position else 'N/A'

        images_by_laterality[laterality][series_id].append({
            'image': image,
            'view_position': view_position
        })

    # Convert to list format for template
    # Order: Right (R) first (displays on left), then Left (L) (displays on right) - reversed for display
    laterality_order = ['R', 'L', 'UNKNOWN']
    organized_images = []

    for laterality in laterality_order:
        if laterality in images_by_laterality:
            series_groups = []
            for series_id, image_list in images_by_laterality[laterality].items():
                if image_list:
                    # Get view position from first image in series
                    view_position = image_list[0]['view_position']
                    series_groups.append({
                        'series_id': series_id,
                        'view_position': view_position,
                        'images': [item['image'] for item in image_list],
                        'count': len(image_list)
                    })

            if series_groups:
                # Display laterality opposite to anatomical position (right appears on left of screen)
                display_laterality = 'Right breast' if laterality == 'R' else 'Left breast' if laterality == 'L' else 'Unknown'
                organized_images.append({
                    'laterality': laterality,
                    'laterality_display': display_laterality,
                    'series_groups': series_groups
                })

    return render(request, "clinic/appointment.jinja", {
        "clinic": clinic,
        "appointment": appointment,
        "participant": appointment.participant,
        "organized_images": organized_images,
        "has_images": len(images) > 0,
        "format_status": format_status
    })

def appointment_images(request, clinic_id, appointment_id):
    """API endpoint to get images for an appointment"""
    from gateway.models import Image

    clinic = get_object_or_404(Clinic, id=clinic_id)
    appointment = get_object_or_404(Appointment, id=appointment_id, clinic_slot__clinic=clinic)

    # Get all images for this appointment through Study -> Series -> Image
    # Order by series first (groups images from same series together),
    # then by instance_number within each series
    images = Image.objects.filter(
        series__study__appointment=appointment
    ).select_related('series__study').order_by('series__series_instance_uid', 'instance_number', 'received_at')

    image_data = []
    for image in images:
        image_data.append({
            'id': str(image.id),
            'series_id': str(image.series.id),
            'thumbnail_url': image.thumbnail.url if image.thumbnail else None,
            'instance_number': image.instance_number,
            'laterality': image.laterality.upper() if image.laterality else 'N/A',
            'view_position': image.view_position if image.view_position else 'N/A',
            'received_at': image.received_at.strftime('%d/%m/%Y %H:%M')
        })

    return JsonResponse({'images': image_data})

def appointment_images_stream(request, clinic_id, appointment_id):
    """SSE endpoint to stream real-time image updates"""
    from gateway.models import Image

    clinic = get_object_or_404(Clinic, id=clinic_id)
    appointment = get_object_or_404(Appointment, id=appointment_id, clinic_slot__clinic=clinic)

    def event_stream():
        """Generator function that yields SSE formatted data"""
        last_check = timezone.now() - timedelta(seconds=1)

        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        while True:
            try:
                # Check for new images since last check
                # Order by series to group images from same series together
                new_images = Image.objects.filter(
                    series__study__appointment=appointment,
                    created_at__gt=last_check
                ).select_related('series__study').order_by('series__series_instance_uid', 'instance_number', 'received_at')

                if new_images.exists():
                    for image in new_images:
                        study = image.series.study
                        image_data = {
                            'type': 'new_image',
                            'study': {
                                'id': str(study.id),
                                'accession_number': study.accession_number,
                                'study_date': study.study_date,
                                'study_time': study.study_time
                            },
                            'image': {
                                'id': str(image.id),
                                'series_id': str(image.series.id),
                                'thumbnail_url': image.thumbnail.url if image.thumbnail else None,
                                'instance_number': image.instance_number,
                                'laterality': image.laterality.upper() if image.laterality else 'N/A',
                                'view_position': image.view_position if image.view_position else 'N/A',
                                'received_at': image.received_at.strftime('%d/%m/%Y %H:%M')
                            }
                        }
                        yield f"data: {json.dumps(image_data)}\n\n"

                last_check = timezone.now()

                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"

                time.sleep(0.2) #check 5 times per second

            except Exception as e:
                # Log error but continue streaming
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                time.sleep(1)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable buffering in nginx
    return response

def appointment_status_stream(request, clinic_id, appointment_id):
    """SSE endpoint to stream real-time appointment status updates"""
    clinic = get_object_or_404(Clinic, id=clinic_id)
    appointment = get_object_or_404(Appointment, id=appointment_id, clinic_slot__clinic=clinic)

    def event_stream():
        """Generator function that yields SSE formatted status updates"""
        last_state = appointment.state

        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        while True:
            try:
                # Refresh appointment from database
                appointment.refresh_from_db()

                # Check if status has changed
                if appointment.state != last_state:
                    status_data = {
                        'type': 'status_change',
                        'state': appointment.state,
                        'html': format_status(appointment.state)
                    }
                    yield f"data: {json.dumps(status_data)}\n\n"
                    last_state = appointment.state

                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"

                time.sleep(0.5)  # Check twice per second

            except Exception as e:
                # Log error but continue streaming
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                time.sleep(1)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable buffering in nginx
    return response

def clinic_statuses_stream(request, clinic_id):
    """SSE endpoint to stream real-time status updates for all appointments in a clinic"""
    clinic = get_object_or_404(Clinic, id=clinic_id)

    def event_stream():
        """Generator function that yields SSE formatted status updates for all appointments"""
        # Track last known state for each appointment
        appointment_states = {}

        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"

        while True:
            try:
                # Get all appointments for this clinic
                appointments = Appointment.objects.filter(clinic_slot__clinic=clinic)

                # Check each appointment for state changes
                for appointment in appointments:
                    appointment_id = str(appointment.id)
                    current_state = appointment.state

                    # Check if this is a new appointment or state has changed
                    if appointment_id not in appointment_states or appointment_states[appointment_id] != current_state:
                        status_data = {
                            'type': 'status_change',
                            'appointment_id': appointment_id,
                            'state': current_state,
                            'html': format_status(current_state)
                        }
                        yield f"data: {json.dumps(status_data)}\n\n"
                        appointment_states[appointment_id] = current_state

                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"

                time.sleep(0.5)  # Check twice per second

            except Exception as e:
                # Log error but continue streaming
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                time.sleep(1)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable buffering in nginx
    return response

def form_for(appointment_id, csrf_token, request):
    appointment = Appointment.objects.get(id=appointment_id)

    # Don't show button if appointment is complete
    if appointment.state == AppointmentState.COMPLETE.value:
        return ""

    gateway_id = Gateway.objects.last().id # we'd need to think about how we get the correct gateway Id. Is there more than one per trust?
    form = ScreeningOrderGatewayActionForm(initial={"appointment_id": appointment_id, "gateway_id": gateway_id})
    fields = "".join(str(field) for field in form)

    previously_sent = appointment.state == AppointmentState.SENT_TO_MODALITY.value

    jinja_engine = engines['jinja2']
    form_template = jinja_engine.env.get_template('components/app/send_to_modality_button.jinja')
    macro = form_template.module.send_to_modality_button
    rendered_html = macro(request.get_full_path(), csrf_token, fields, previously_sent)

    return rendered_html

    # #render the fields with a button
    # return  f"""
    #         <form method='post' action='/gateway-actions/screening-order/'>
    #             <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}"/>
    #             <input type="hidden" name="success_url" value="{ request.get_full_path() }"/>
    #             { fields }
    #             <button type='submit' class="nhsuk-button">Send to modality</button>
    #         </form>
    #         """
