POC seven
=========

```mermaid
---
config:
  theme: redux-color
---
sequenceDiagram
  actor Mammographer as Mammographer
  participant Manage as Manage Breast Screening (Azure)
  participant Gateway as Gateway VM (Hospital Network)
  participant Modality as Modality
  participant PACS as Hospital PACS
  Mammographer ->> Manage: Collect appointment information
  Manage ->> Gateway: Send participant details
  Gateway ->> Gateway: Create worklist entry
  Modality ->> Gateway: Retrieve worklist 
  Mammographer ->> Modality: Take images
  Modality ->> Gateway: Store images
  Modality ->> PACS: Store images
  Gateway ->> Gateway: Create thumbnail, extract metadata
  Gateway ->> Manage: Return image metadata and thumbnails
  Manage ->> Mammographer: Screening complete
```
