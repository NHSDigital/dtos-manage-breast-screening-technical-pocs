"""
Event processing functions for gateway events.

These functions handle the actual business logic for:
- MPPS status updates: Updates Appointment status when procedures start/complete
- Image received events: Creates Study/Series/Image records when images are stored
"""

import base64
import logging

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from gateway.models import GatewayAction, Study, Series, Image
from provider.models import Appointment, AppointmentState

logger = logging.getLogger(__name__)

# MPPS status to Appointment state mapping
STATUS_MAPPING = {
    'IN PROGRESS': AppointmentState.IN_PROGRESS.value,
    'COMPLETED': AppointmentState.COMPLETE.value,
    'DISCONTINUED': AppointmentState.CANCELLED.value,
}


async def process_mpps_event(payload: dict) -> dict:
    """
    Process an MPPS status update event and update the Appointment.

    Args:
        payload: The event payload from the gateway

    Returns:
        dict with status and action_id
    """
    try:
        event_type = payload.get("event_type")
        data = payload.get("data", {})

        if event_type != "mpps.status_update":
            logger.warning(f"Unknown event type: {event_type}")
            return {"status": "unknown_event"}

        action_id = data.get("action_id")
        accession_number = data.get("accession_number")
        mpps_status = data.get("status")

        logger.info(
            f"Received MPPS event: action_id={action_id}, "
            f"accession={accession_number}, status={mpps_status}"
        )

        # Map MPPS status to Appointment state
        appointment_state = STATUS_MAPPING.get(mpps_status)
        if not appointment_state:
            logger.warning(f"Unknown MPPS status: {mpps_status}")
            return {"status": "unknown_status", "action_id": action_id}

        @sync_to_async
        def get_action():
            try:
                return GatewayAction.objects.get(id=action_id)
            except GatewayAction.DoesNotExist:
                return None

        action = await get_action()
        if not action:
            logger.error(f"GatewayAction not found: {action_id}")
            return {"status": "action_not_found", "action_id": action_id}

        source_ref = action.payload.get("source_reference", {})
        appointment_id = source_ref.get("appointment_id")

        if not appointment_id:
            logger.error(f"No appointment_id in action payload: {action_id}")
            return {"status": "no_appointment_id", "action_id": action_id}

        @sync_to_async
        def update_appointment():
            try:
                appointment = Appointment.objects.get(id=appointment_id)
                old_state = appointment.state
                appointment.state = appointment_state
                appointment.save(update_fields=['state', 'updated_at'])
                return {
                    "status": "updated",
                    "action_id": action_id,
                    "appointment_id": str(appointment_id),
                    "old_state": old_state,
                    "new_state": appointment_state
                }
            except Appointment.DoesNotExist:
                return None

        result = await update_appointment()
        if not result:
            logger.error(f"Appointment not found: {appointment_id}")
            return {"status": "appointment_not_found", "action_id": action_id}

        logger.info(
            f"Updated appointment {appointment_id}: {result['old_state']} -> {result['new_state']}"
        )

        return result

    except Exception as e:
        logger.error(f"Error processing MPPS event: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def process_image_received_event(payload: dict) -> dict:
    """
    Process a study.image_received event and create/update Study, Series, and Image records.

    Args:
        payload: The event payload from the gateway

    Returns:
        dict with status and details
    """
    try:
        message_type = payload.get("message_type")
        parameters = payload.get("parameters", {})

        if message_type != "study.image_received":
            logger.warning(f"Unknown message type: {message_type}")
            return {"status": "unknown_message_type"}

        study_data = parameters.get("study", {})
        series_data = parameters.get("series", {})
        image_data = parameters.get("image", {})
        source_reference = payload.get("source_reference", {})

        action_id = source_reference.get("action_id")
        accession_number = study_data.get("accession_number")
        study_instance_uid = study_data.get("study_instance_uid")
        series_instance_uid = series_data.get("series_instance_uid")
        sop_instance_uid = image_data.get("sop_instance_uid")

        logger.info(
            f"Received image event: action_id={action_id}, accession={accession_number}, "
            f"study_uid={study_instance_uid}, sop_uid={sop_instance_uid}"
        )

        @sync_to_async
        def persist_image_data():
            try:
                if not action_id:
                    logger.error("No action_id in source_reference")
                    return {"status": "no_action_id"}

                try:
                    action = GatewayAction.objects.get(id=action_id)
                except GatewayAction.DoesNotExist:
                    logger.error(f"GatewayAction not found: {action_id}")
                    return {"status": "action_not_found", "action_id": action_id}

                appointment_id = action.payload.get("source_reference", {}).get("appointment_id")
                if not appointment_id:
                    logger.error(f"No appointment_id in action {action_id}")
                    return {"status": "no_appointment_id", "action_id": action_id}

                appointment = Appointment.objects.get(id=appointment_id)

                # Check if Series already exists
                try:
                    existing_series = Series.objects.select_related('study').get(series_instance_uid=series_instance_uid)
                    series = existing_series
                    study = existing_series.study
                    series_created = False
                    study_created = False
                except Series.DoesNotExist:
                    study, study_created = Study.objects.get_or_create(
                        study_instance_uid=study_instance_uid,
                        defaults={
                            "appointment": appointment,
                            "accession_number": accession_number,
                            "modality": study_data.get("modality", ""),
                            "study_date": study_data.get("study_date", ""),
                            "study_time": study_data.get("study_time", ""),
                            "study_description": study_data.get("study_description", ""),
                        }
                    )

                    series, series_created = Series.objects.get_or_create(
                        series_instance_uid=series_instance_uid,
                        defaults={
                            "study": study,
                            "series_number": series_data.get("series_number", ""),
                            "series_description": series_data.get("series_description", ""),
                        }
                    )

                # Check if Image already exists
                if Image.objects.filter(series=series, sop_instance_uid=sop_instance_uid).exists():
                    return {
                        "status": "already_exists",
                        "sop_instance_uid": sop_instance_uid,
                    }

                received_at_str = image_data.get("received_at")
                received_at = parse_datetime(received_at_str) if received_at_str else timezone.now()

                thumbnail_data = image_data.get("thumbnail", {})
                thumbnail_base64 = thumbnail_data.get("data", "")
                thumbnail_format = thumbnail_data.get("format", "jpeg")

                dose_data = image_data.get("dose", {})

                image = Image(
                    series=series,
                    sop_instance_uid=sop_instance_uid,
                    instance_number=image_data.get("instance_number", ""),
                    rows=image_data.get("dimensions", {}).get("rows", 0),
                    columns=image_data.get("dimensions", {}).get("columns", 0),
                    view_position=image_data.get("acquisition", {}).get("view_position", ""),
                    laterality=image_data.get("acquisition", {}).get("laterality", ""),
                    organ_dose=dose_data.get("organ_dose", ""),
                    entrance_dose_in_mgy=dose_data.get("entrance_dose_in_mgy", ""),
                    kvp=dose_data.get("kvp", ""),
                    exposure_in_uas=dose_data.get("exposure_in_uas", ""),
                    anode_target_material=dose_data.get("anode_target_material", ""),
                    filter_material=dose_data.get("filter_material", ""),
                    filter_thickness=dose_data.get("filter_thickness", ""),
                    received_at=received_at,
                )

                if thumbnail_base64:
                    thumbnail_bytes = base64.b64decode(thumbnail_base64)
                    filename = f"{sop_instance_uid}.{thumbnail_format}"
                    image.thumbnail.save(filename, ContentFile(thumbnail_bytes), save=False)

                image.save()

                logger.info(f"Saved image {sop_instance_uid}")

                return {
                    "status": "created",
                    "appointment_id": str(appointment.id),
                    "study_id": str(study.id),
                    "series_id": str(series.id),
                    "image_id": str(image.id),
                }

            except Appointment.DoesNotExist:
                logger.error(f"Appointment not found for accession {accession_number}")
                return {"status": "appointment_not_found", "accession_number": accession_number}
            except Exception as e:
                logger.error(f"Error persisting image data: {e}", exc_info=True)
                return {"status": "error", "error": str(e)}

        result = await persist_image_data()
        return result

    except Exception as e:
        logger.error(f"Error processing image received event: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
