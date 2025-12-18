# DICOM Networking Integration - Work in Progress

## Current Status

**Started**: 2025-12-17
**Status**: Incomplete - Basic structure in place, response building not working yet

## What Was Completed

1. ✅ **Added obd-dicom dependency** (v1.6.0)
   - `github.com/t2care/obd-dicom@v1.6.0` added to go.mod
   - Upgraded golang.org/x/text to v0.28.0

2. ✅ **Created networking wrapper**
   - File: `internal/dicom/network_worklist.go`
   - Implements WorklistSCP struct
   - Sets up association handlers
   - Implements C-FIND query extraction
   - Basic structure for response building

3. ✅ **Updated worklist-server main.go**
   - Removed TODO comments
   - Integrated WorklistSCP
   - Proper goroutine management for server startup

## What's Not Working Yet

### 1. DICOM Object Construction

**Problem**: obd-dicom doesn't expose a simple API for building DICOM responses programmatically.

**Current code** (line 163-182 in network_worklist.go):
```go
func (s *WorklistSCP) convertWorklistResponseToDicom(response *WorklistResponse) (*media.DcmObj, error) {
    // TODO: Need to figure out how to create DcmObj from scratch
    dcmObj := &media.DcmObj{}
    s.logger.Warn("DICOM object creation not fully implemented - returning empty object")
    return dcmObj, nil
}
```

**Needed**:
- How to create a new DcmObj with tags
- How to add patient demographics (Name, ID, Birth Date, Sex)
- How to add scheduled procedure step sequence
- How to add study information

### 2. SCP Type Visibility

**Problem**: obd-dicom's `scp` type is unexported (lowercase), making it hard to wrap cleanly.

**Current workaround**: Using `interface{}` which breaks type safety and method calls.

## Research Findings

### obd-dicom Library Analysis

**Package Structure**:
- `github.com/t2care/obd-dicom/network` - SCP/SCU implementations
- `github.com/t2care/obd-dicom/network/dicomstatus` - Status codes
- `github.com/t2care/obd-dicom/media` - DICOM object handling
- `github.com/t2care/obd-dicom/dictionary/tags` - Tag definitions

**SCP API** (from `/network/scp.go`):
```go
type scp struct {  // Note: unexported
    Port int
    onCFindRequest func(request *AAssociationRQ, data *media.DcmObj) ([]*media.DcmObj, uint16)
    onCStoreRequest func(request *AAssociationRQ, data *media.DcmObj) uint16
    // ...
}

func NewSCP(port int) *scp
func (s *scp) OnCFindRequest(handler ...)
func (s *scp) Start() error
```

**Example Usage** (from `/cmd/obd-dicom/main.go`):
```go
scp.OnCFindRequest(func(request *network.AAssociationRQ, query *media.DcmObj) ([]*media.DcmObj, uint16) {
    results := make([]*media.DcmObj, 0)
    for i := 0; i < 10; i++ {
        results = append(results, utils.GenerateCFindRequest())
    }
    return results, dicomstatus.Success
})
```

**Key Finding**: The example uses `utils.GenerateCFindRequest()` to create responses. Need to find this utility function or similar.

### Missing MPPS Support

**Finding**: obd-dicom does NOT appear to support N-CREATE or N-SET operations (MPPS).

**Evidence**:
- No `OnNCreateRequest` or `OnNSetRequest` methods in scp.go
- Only C-FIND, C-STORE, C-MOVE, and C-ECHO are supported

**Implication**: May need to use grailbio/go-netdicom for MPPS support (archived but has MPPS examples).

## Next Steps (In Priority Order)

### Option A: Complete obd-dicom Integration (Recommended First)

1. **Find DICOM object creation pattern**
   - Search obd-dicom codebase for worklist response examples
   - Look at `utils.GenerateCFindRequest()` implementation
   - Study how to create DcmObj with tags programmatically

2. **Fix type issues**
   - Either use the scp type directly (accept it's unexported)
   - Or simplify the wrapper to just call NewSCP directly in main.go

3. **Implement convertWorklistResponseToDicom()**
   - Map WorklistResponse fields to DICOM tags
   - Create proper ScheduledProcedureStepSequence
   - Test with modality emulator

4. **Test C-FIND** with modality emulator
   - Verify associations work
   - Verify query extraction
   - Verify responses are returned

### Option B: Add MPPS Support

Two approaches:

**B1. Check if obd-dicom has MPPS** (unlikely but check first)
- Search for N-CREATE/N-SET support
- Check if it's in a different package

**B2. Use grailbio/go-netdicom for MPPS only**
- Keep obd-dicom for C-FIND/C-STORE
- Add grailbio/go-netdicom dependency
- Run MPPS on different port or different service
- Note: grailbio/go-netdicom is archived but functional

### Option C: Implement PACS SCP with C-STORE

After worklist is working:

1. Create `internal/dicom/network_pacs.go`
2. Implement C-STORE handler using obd-dicom
3. Implement C-ECHO handler
4. Update pacs-server/main.go

## Files Modified (Uncommitted)

```
M  go.mod                                    # Added obd-dicom
M  go.sum                                    # Added obd-dicom
M  cmd/worklist-server/main.go               # Integrated WorklistSCP
A  internal/dicom/network_worklist.go        # New file (incomplete)
M  deployments/Dockerfile.worklist           # DB initialization
M  deployments/Dockerfile.pacs               # DB initialization
A  deployments/docker-entrypoint-worklist.sh # New file
A  deployments/docker-entrypoint-pacs.sh     # New file
A  .env.development                          # New file
```

## Key Code Locations

- **Business logic (complete)**: `internal/dicom/worklist.go`, `internal/dicom/mpps.go`
- **Storage layer (complete)**: `internal/storage/worklist.go`
- **Networking (incomplete)**: `internal/dicom/network_worklist.go`
- **DICOM tags needed**: See comments in `cmd/worklist-server/main.go` lines 195-213

## Resources

- **obd-dicom GitHub**: https://github.com/t2care/obd-dicom
- **obd-dicom pkg.go.dev**: https://pkg.go.dev/github.com/t2care/obd-dicom
- **grailbio/go-netdicom** (archived): https://github.com/grailbio/go-netdicom
- **Local installation**: `/Users/grahampengelly/Repos/go/pkg/mod/github.com/t2care/obd-dicom@v1.6.0/`

## Questions to Answer

1. How does obd-dicom create DICOM worklist responses programmatically?
2. Is there a helper for building ScheduledProcedureStepSequence?
3. Can we use the library without wrapping the scp type?
4. Does obd-dicom support MPPS at all?
5. Should we use grailbio/go-netdicom instead (despite being archived)?

## Recommendation for Next Session

Start with **Option A, Step 1**: Research how to build DICOM worklist responses in obd-dicom. Look at:
- `/cmd/obd-dicom/main.go` - example usage
- `/utils/` directory - helper functions
- `/samples/` directory - test DICOM files
- Search for "GenerateCFindRequest" implementation

Once we know how to build responses, the rest should fall into place quickly.
