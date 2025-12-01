#!/usr/bin/env python3
"""
Test script for PACS server (C-ECHO and C-STORE)
"""

import sys
import argparse
from datetime import datetime
from pynetdicom import AE, debug_logger
from pynetdicom.sop_class import Verification, CTImageStorage, MRImageStorage, DigitalMammographyXRayImageStorageForPresentation
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian

# Enable debugging if needed
# debug_logger()


def create_test_dicom_file(modality='MG'):
    """Create a minimal test DICOM file."""
    # File meta information
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = DigitalMammographyXRayImageStorageForPresentation
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    # Main dataset
    ds = Dataset()
    ds.file_meta = file_meta
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    # Patient module
    ds.PatientName = "TEST^PACS^PATIENT"
    ds.PatientID = "TEST001"
    ds.PatientBirthDate = "19800101"
    ds.PatientSex = "F"

    # Study module
    ds.StudyInstanceUID = generate_uid()
    ds.StudyDate = datetime.now().strftime("%Y%m%d")
    ds.StudyTime = datetime.now().strftime("%H%M%S")
    ds.AccessionNumber = "ACC_TEST_001"
    ds.StudyID = "1"
    ds.StudyDescription = "Test Study for PACS"

    # Series module
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = "1"
    ds.Modality = modality
    ds.SeriesDescription = f"Test {modality} Series"

    # Image module
    ds.SOPClassUID = DigitalMammographyXRayImageStorageForPresentation
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.InstanceNumber = "1"

    # Mammography-specific fields (if modality is MG)
    if modality == 'MG':
        ds.ViewPosition = "CC"  # Cranio-Caudal view
        ds.ImageLaterality = "R"  # Right breast

    # Minimal image data (required for storage)
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 100
    ds.Columns = 100
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = b'\x00' * (100 * 100)  # Minimal pixel data

    return ds


def test_echo(host='localhost', port=4244, ae_title='SCREENING_PACS'):
    """Test C-ECHO (DICOM ping)."""
    print("="*60)
    print("Testing C-ECHO (DICOM Verification)")
    print("="*60)

    # Create application entity
    ae = AE(ae_title='TEST_SCU')
    ae.add_requested_context(Verification)

    # Associate with peer AE
    print(f"Connecting to {host}:{port} (AET: {ae_title})...")
    assoc = ae.associate(host, port, ae_title=ae_title)

    if assoc.is_established:
        print("✓ Association established")

        # Send C-ECHO
        status = assoc.send_c_echo()

        if status:
            print(f"✓ C-ECHO successful - Status: 0x{status.Status:04X}")
            result = True
        else:
            print("✗ C-ECHO failed")
            result = False

        # Release association
        assoc.release()
        print("✓ Association released")
    else:
        print("✗ Association rejected or failed")
        result = False

    return result


def test_store(host='localhost', port=4244, ae_title='SCREENING_PACS', modality='MG'):
    """Test C-STORE (DICOM image storage)."""
    print("\n" + "="*60)
    print("Testing C-STORE (DICOM Image Storage)")
    print("="*60)

    # Create test DICOM file
    print(f"Creating test {modality} DICOM file...")
    ds = create_test_dicom_file(modality=modality)
    print(f"  Patient: {ds.PatientName}")
    print(f"  Study UID: {ds.StudyInstanceUID}")
    print(f"  SOP Instance UID: {ds.SOPInstanceUID}")

    # Create application entity
    ae = AE(ae_title='TEST_SCU')
    ae.add_requested_context(DigitalMammographyXRayImageStorageForPresentation)

    # Associate with peer AE
    print(f"\nConnecting to {host}:{port} (AET: {ae_title})...")
    assoc = ae.associate(host, port, ae_title=ae_title)

    if assoc.is_established:
        print("✓ Association established")

        # Send C-STORE
        print("Sending C-STORE request...")
        status = assoc.send_c_store(ds)

        if status:
            print(f"✓ C-STORE successful - Status: 0x{status.Status:04X}")
            result = True
        else:
            print("✗ C-STORE failed")
            result = False

        # Release association
        assoc.release()
        print("✓ Association released")
    else:
        print("✗ Association rejected or failed")
        result = False

    return result


def main():
    parser = argparse.ArgumentParser(description='Test PACS server')
    parser.add_argument('-H', '--host', default='localhost', help='PACS server hostname')
    parser.add_argument('-p', '--port', type=int, default=4244, help='PACS server port')
    parser.add_argument('-a', '--aet', default='SCREENING_PACS', help='PACS server AE title')
    parser.add_argument('-m', '--modality', default='MG', help='Modality for test image')
    parser.add_argument('--echo-only', action='store_true', help='Only test C-ECHO')
    parser.add_argument('--store-only', action='store_true', help='Only test C-STORE')

    args = parser.parse_args()

    print("\n" + "#"*60)
    print("DICOM PACS Server Test")
    print("#"*60)
    print(f"\nServer: {args.host}:{args.port}")
    print(f"AE Title: {args.aet}\n")

    results = {}

    # Test C-ECHO
    if not args.store_only:
        results['echo'] = test_echo(args.host, args.port, args.aet)

    # Test C-STORE
    if not args.echo_only:
        results['store'] = test_store(args.host, args.port, args.aet, args.modality)

    # Summary
    print("\n" + "#"*60)
    print("Test Summary")
    print("#"*60)

    if 'echo' in results:
        status = "✓ PASS" if results['echo'] else "✗ FAIL"
        print(f"  C-ECHO:  {status}")

    if 'store' in results:
        status = "✓ PASS" if results['store'] else "✗ FAIL"
        print(f"  C-STORE: {status}")

    print("#"*60 + "\n")

    # Exit with appropriate code
    if all(results.values()):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
