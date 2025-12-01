#!/usr/bin/env python3
"""
Test script for DICOM Modality Worklist Server

This script tests the worklist server by sending C-FIND queries
and optionally testing MPPS functionality.

Usage:
    python3 test_worklist.py [options]

Requirements:
    uv sync
    uv run python test_worklist.py [options]
"""

import sys
import argparse
from datetime import datetime
from pynetdicom import AE, debug_logger
from pynetdicom.sop_class import (
    ModalityWorklistInformationFind,
    Verification,
    ModalityPerformedProcedureStep
)
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

# Enable debug logging if needed
# debug_logger()


def test_echo(host, port, ae_title):
    """Test DICOM connectivity with C-ECHO."""
    print(f"\n{'='*60}")
    print("Testing DICOM Echo (C-ECHO)")
    print(f"{'='*60}")

    ae = AE(ae_title='TEST_SCU')
    ae.add_requested_context(Verification)

    assoc = ae.associate(host, port, ae_title=ae_title)

    if assoc.is_established:
        status = assoc.send_c_echo()
        if status and status.Status == 0x0000:
            print("✓ Echo successful - connection OK")
        else:
            print(f"✗ Echo failed with status: {status}")
        assoc.release()
        return True
    else:
        print("✗ Failed to establish association")
        return False


def test_worklist_query(host, port, ae_title, modality='MG', date=None):
    """Query the worklist server for scheduled procedures."""
    print(f"\n{'='*60}")
    print("Testing Worklist Query (C-FIND)")
    print(f"{'='*60}")

    if date is None:
        date = datetime.now().strftime('%Y%m%d')

    ae = AE(ae_title='TEST_SCU')
    ae.add_requested_context(ModalityWorklistInformationFind)

    # Build the C-FIND query dataset
    ds = Dataset()

    # Patient identification
    ds.PatientName = '*'
    ds.PatientID = '*'
    ds.PatientBirthDate = ''
    ds.PatientSex = ''

    # Scheduled Procedure Step
    sps = Dataset()
    sps.Modality = modality
    sps.ScheduledStationAETitle = ''
    sps.ScheduledProcedureStepStartDate = date
    sps.ScheduledProcedureStepStartTime = ''
    sps.ScheduledPerformingPhysicianName = ''
    sps.ScheduledProcedureStepDescription = ''
    sps.ScheduledProcedureStepID = ''

    ds.ScheduledProcedureStepSequence = [sps]

    # Requested Procedure
    ds.AccessionNumber = ''
    ds.RequestedProcedureDescription = ''
    ds.RequestedProcedureID = ''
    ds.StudyInstanceUID = ''

    print(f"\nQuery parameters:")
    print(f"  Modality: {modality}")
    print(f"  Date: {date}")

    # Send the query
    assoc = ae.associate(host, port, ae_title=ae_title)

    if assoc.is_established:
        print("\n✓ Association established")
        print("\nWorklist items found:\n")

        responses = assoc.send_c_find(ds, ModalityWorklistInformationFind)
        count = 0

        for (status, identifier) in responses:
            if status and status.Status == 0xFF00:  # Pending (has results)
                count += 1
                print(f"{'─'*60}")
                print(f"Item #{count}")
                print(f"{'─'*60}")
                print(f"  Patient Name:    {identifier.get('PatientName', 'N/A')}")
                print(f"  Patient ID:      {identifier.get('PatientID', 'N/A')}")
                print(f"  Birth Date:      {identifier.get('PatientBirthDate', 'N/A')}")
                print(f"  Sex:             {identifier.get('PatientSex', 'N/A')}")
                print(f"  Accession #:     {identifier.get('AccessionNumber', 'N/A')}")
                print(f"  Study Instance:  {identifier.get('StudyInstanceUID', 'N/A')}")

                if 'ScheduledProcedureStepSequence' in identifier:
                    sps = identifier.ScheduledProcedureStepSequence[0]
                    print(f"  Modality:        {sps.get('Modality', 'N/A')}")
                    print(f"  Scheduled Date:  {sps.get('ScheduledProcedureStepStartDate', 'N/A')}")
                    print(f"  Scheduled Time:  {sps.get('ScheduledProcedureStepStartTime', 'N/A')}")
                    print(f"  Description:     {sps.get('ScheduledProcedureStepDescription', 'N/A')}")
                print()

        print(f"{'='*60}")
        print(f"Total worklist items: {count}")
        print(f"{'='*60}")

        assoc.release()
        return count > 0
    else:
        print("✗ Failed to establish association")
        return False


def test_mpps_create(host, port, ae_title):
    """Test MPPS N-CREATE (start of procedure)."""
    print(f"\n{'='*60}")
    print("Testing MPPS Create (N-CREATE)")
    print(f"{'='*60}")
    print("\nNote: This is a basic test. Full MPPS testing requires")
    print("      a valid worklist item and proper sequence setup.")

    ae = AE(ae_title='TEST_SCU')
    ae.add_requested_context(ModalityPerformedProcedureStep)

    assoc = ae.associate(host, port, ae_title=ae_title)

    if assoc.is_established:
        print("✓ Association established")

        # Create a basic MPPS dataset
        ds = Dataset()
        ds.PerformedProcedureStepStatus = 'IN PROGRESS'
        ds.Modality = 'MG'

        # Scheduled Step Attributes Sequence (required)
        sps = Dataset()
        sps.AccessionNumber = 'ACC001'
        sps.StudyInstanceUID = generate_uid()
        ds.ScheduledStepAttributesSequence = [sps]

        mpps_uid = generate_uid()

        try:
            # Send N-CREATE
            status, created_ds = assoc.send_n_create(
                ds,
                ModalityPerformedProcedureStep,
                mpps_uid
            )

            if status and status.Status == 0x0000:
                print(f"✓ MPPS N-CREATE successful")
                print(f"  MPPS Instance UID: {mpps_uid}")
            else:
                print(f"✗ MPPS N-CREATE failed with status: {status}")
        except Exception as e:
            print(f"✗ MPPS N-CREATE error: {e}")

        assoc.release()
        return True
    else:
        print("✗ Failed to establish association")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Test DICOM Modality Worklist Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic test
  python3 test_worklist.py

  # Test specific modality
  python3 test_worklist.py -m MG

  # Test with specific date
  python3 test_worklist.py -d 20240315

  # Include MPPS test
  python3 test_worklist.py --mpps

  # Custom server
  python3 test_worklist.py -H 192.168.1.100 -p 4243 -a CUSTOM_AET
        """
    )

    parser.add_argument('-H', '--host', default='localhost',
                        help='Worklist server hostname (default: localhost)')
    parser.add_argument('-p', '--port', type=int, default=4243,
                        help='Worklist server port (default: 4243)')
    parser.add_argument('-a', '--aet', default='SCREENING_MWL',
                        help='Worklist server AE Title (default: SCREENING_MWL)')
    parser.add_argument('-m', '--modality', default='MG',
                        help='Modality to query (default: MG)')
    parser.add_argument('-d', '--date',
                        help='Date to query (YYYYMMDD, default: today)')
    parser.add_argument('--mpps', action='store_true',
                        help='Also test MPPS functionality')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose debug logging')

    args = parser.parse_args()

    if args.verbose:
        debug_logger()

    print(f"\n{'#'*60}")
    print("DICOM Modality Worklist Server Test")
    print(f"{'#'*60}")
    print(f"\nServer: {args.host}:{args.port}")
    print(f"AE Title: {args.aet}")

    # Test 1: Echo
    echo_ok = test_echo(args.host, args.port, args.aet)

    if not echo_ok:
        print("\n✗ Echo test failed. Check that the server is running.")
        print("  Try: docker-compose ps")
        print("       docker-compose logs")
        sys.exit(1)

    # Test 2: Worklist query
    worklist_ok = test_worklist_query(args.host, args.port, args.aet,
                                      args.modality, args.date)

    if not worklist_ok:
        print("\n⚠ No worklist items found (this may be expected)")

    # Test 3: MPPS (optional)
    if args.mpps:
        mpps_ok = test_mpps_create(args.host, args.port, args.aet)

    print(f"\n{'#'*60}")
    print("Test Summary")
    print(f"{'#'*60}")
    print(f"  Echo (C-ECHO):           {'✓ PASS' if echo_ok else '✗ FAIL'}")
    print(f"  Worklist (C-FIND):       {'✓ PASS' if worklist_ok else '⚠ NO DATA'}")
    if args.mpps:
        print(f"  MPPS (N-CREATE):         {'✓ PASS' if mpps_ok else '✗ FAIL'}")
    print(f"{'#'*60}\n")


if __name__ == '__main__':
    main()
