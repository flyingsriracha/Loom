# Loom Demo Scenarios and Background

## Purpose
This file logs the two guided engineering demos used in the Loom marketing prototype and the factual background used to ground them.

The UI timing, animation, and presentation are simulated for storytelling.
The engineering content, module names, command names, layer names, and standards references are grounded in Loom's local knowledge sources plus public standards pages.

## Shared Knowledge Foundation Background
Loom's demo grounding comes from these local sources:

- `tools/ASAMKnowledgeDB/fused_knowledge.db`
- `tools/autosar-fusion/autosar_fused.db`
- The restored Loom FalkorDB / Graphiti knowledge graph

Key graph context currently reflected in the demo:

- `39,411` mapped nodes
- `384,763` vector nodes
- `744` temporal state edges
- `26` communities

Important grounding rule used for the demo:

- No ASAM or AUTOSAR claims were written from memory alone. Commands, module names, layer names, and workflow statements were cross-checked against local fused data and public standards pages.

## Demo 1: ETAS ETK / XCP / A2L Workflow
### Scenario
An embedded calibration engineer is bringing up an ETAS ETK workflow for an AUTOSAR ECU and asks Loom how to configure XCP DAQ and what needs to exist in the A2L so INCA can interpret measured/calibrated values correctly.

### What the Demo Shows
- AMS restores prior ETK session context.
- Loom queries the Knowledge Foundation for ASAM XCP and A2L guidance.
- Loom returns a verified DAQ command sequence.
- Loom answers a follow-up question about A2L structure.
- Loom finishes with concrete engineering next steps.

### Grounded Standards / Data Used
Public standards pages:

- `ASAM MCD-1 XCP v1.5.0`
- `ASAM MCD-2 MC v1.7.1`

Official standards facts used in the demo:

- XCP is a bus-independent master/slave protocol for ECU measurement, calibration, stimulation, and programming.
- XCP uses memory-oriented access and relies on A2L descriptions standardized by ASAM MCD-2 MC.
- A2L contains variable memory locations, data types, record layouts, conversion methods, and units needed by measurement/calibration tools.

Local Loom data used in the demo:

- `xcp_commands`
- `domain_glossary`
- `protocol_parameters`

Real XCP command names shown in the demo:

- `SET_DAQ_PTR`
- `WRITE_DAQ`
- `SET_DAQ_LIST_MODE`
- `GET_DAQ_CLOCK`
- `START_STOP_DAQ_LIST`

Real ASAM glossary concepts used in the narrative:

- `XCP`
- `DAQ`
- `A2L`
- `COMPU-METHOD`
- `MAX_CTO`

ETK-specific operational background used in the script:

- ETK / FETK interfaces are used for direct ECU access during measurement and calibration.
- ETK workflows are designed for low-overhead acquisition of ECU variables while keeping development-tool connectivity practical for INCA-style workflows.

### Engineering Storyline
The demo intentionally models a realistic question sequence:

1. Which XCP DAQ commands are needed first?
2. What must exist in the A2L so the tool interprets signals correctly?
3. What should the engineer do next before bench validation or code changes?

## Demo 2: AUTOSAR Classic Communication Workflow
### Scenario
An AUTOSAR Classic engineer is implementing CAN communication in a body ECU and asks Loom how the compliant communication path should be structured for periodic COM signals and UDS diagnostics, especially when bus-off recovery is part of the requirement.

### What the Demo Shows
- Loom restores the ECU communication context.
- Loom queries the Knowledge Foundation for relevant Classic Platform modules.
- Loom returns the communication stack path for both COM and diagnostic traffic.
- Loom explains where `CanSM` and `ComM` fit.
- Loom ends with ARXML / BSW integration next steps.

### Grounded Standards / Data Used
Public AUTOSAR and reference material used:

- `AUTOSAR Classic Platform`
- AUTOSAR Classic workflow example material
- PDU Router behavior reference material

Local Loom data used in the demo:

- `autosar_cp_modules`
- `autosar_cp_layers`

Real AUTOSAR modules and layers used in the script:

- `Com` — Communication Services
- `PduR` — static PDU routing between upper and lower layers
- `CanIf` — ECU Abstraction / CAN hardware abstraction interface
- `CanTp` — transport for segmented diagnostic communication over CAN
- `Dcm` — diagnostic communication manager
- `CanSM` — CAN state manager for bus-off and network state handling
- `ComM` — communication mode manager
- `SoAd`, `TcpIp`, `EthIf` — optional Ethernet / DoIP extension context

### Realistic Stack Paths Used in the Demo
Periodic signal path:

- `SWC -> RTE -> Com -> PduR -> CanIf -> CanDrv -> CAN bus`

Diagnostic path:

- `Dcm -> PduR -> CanTp -> CanIf -> CanDrv -> CAN bus`

Communication mode / recovery path:

- `ComM <-> CanSM <-> CanIf / CanDrv`

Optional Ethernet extension path shown as background context:

- `Dcm -> PduR -> SoAd -> TcpIp -> EthIf`

### Engineering Storyline
The demo is designed to reflect real BSW bring-up concerns:

1. Which modules define the compliant path?
2. What is the difference between COM signal traffic and DCM/CanTp diagnostic traffic?
3. Where do mode management and bus-off recovery fit?
4. What needs to be configured next in ARXML and BSW integration work?

## Notes For Future Demo Iterations
Potential improvements that would stay grounded:

- Show a generated A2L scaffold preview after the XCP / ETK demo.
- Add explicit ARXML artifacts and PDU identifiers to the AUTOSAR demo.
- Add a query-to-path highlight on the Knowledge Foundation graph for the exact modules returned by the AUTOSAR demo.
