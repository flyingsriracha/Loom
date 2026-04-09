const carouselTrack = document.getElementById("carouselTrack");
const slideButtons = Array.from(document.querySelectorAll("[data-slide]"));
const dotButtons = Array.from(document.querySelectorAll(".carousel-dot"));
const prevButton = document.getElementById("carouselPrev");
const nextButton = document.getElementById("carouselNext");
const slideCount = 3;
let activeSlide = 0;

function setActiveControls(index) {
  slideButtons.forEach((button) => {
    const isActive = Number(button.dataset.slide) === index;
    button.classList.toggle("is-active", isActive);
    if (button.matches("[role='tab']")) {
      button.setAttribute("aria-selected", String(isActive));
    }
  });

  dotButtons.forEach((button) => {
    const isActive = Number(button.dataset.slide) === index;
    button.classList.toggle("is-active", isActive);
  });
}

function goToSlide(index) {
  activeSlide = (index + slideCount) % slideCount;
  carouselTrack.style.transform = `translateX(-${activeSlide * 100}%)`;
  setActiveControls(activeSlide);
  if (activeSlide === 0) {
    restartIdeDemo();
  }
  if (activeSlide === 1) {
    restartAutosarDemo();
  }
  if (activeSlide === 3) {
    restartIntelligenceDemo();
  }
}

slideButtons.forEach((button) => {
  button.addEventListener("click", () => goToSlide(Number(button.dataset.slide)));
});

prevButton.addEventListener("click", () => goToSlide(activeSlide - 1));
nextButton.addEventListener("click", () => goToSlide(activeSlide + 1));

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    goToSlide(activeSlide - 1);
  }
  if (event.key === "ArrowRight") {
    goToSlide(activeSlide + 1);
  }
});

// New IDE Demo v3 - ETAS ETK / XCP / A2L workflow
const chatMessages = document.getElementById("chatMessages");
const chatStatus = document.getElementById("chatStatus");
const thinkingChip = document.getElementById("thinkingChip");
const workflowItems = Array.from(document.querySelectorAll("#workflowList .workflow-item"));
const ideProgressFill = document.getElementById("ideProgressFill");
const ideResults = document.getElementById("ideResults");
const resultQuery = document.getElementById("resultQuery");
const resultSources = document.getElementById("resultSources");
const resultCount = document.getElementById("resultCount");
const resultTableBody = document.getElementById("resultTableBody");
const a2lList = document.getElementById("a2lList");
const nextSteps = document.getElementById("nextSteps");
const resultMemory = document.getElementById("resultMemory");
const ideReplayBtn = document.getElementById("ideReplayBtn");
let ideTimers = [];

const xcpCommands = [
  { cmd: "SET_DAQ_PTR", hex: "0xE2", desc: "Point to the DAQ list and ODT entry before populating measurements" },
  { cmd: "WRITE_DAQ", hex: "0xE1", desc: "Write each measurement or characteristic entry into the ODT" },
  { cmd: "SET_DAQ_LIST_MODE", hex: "0xE0", desc: "Configure event channel, prescaler, priority, and acquisition mode" },
  { cmd: "GET_DAQ_CLOCK", hex: "0xDC", desc: "Read slave clock to align DAQ timestamps in the calibration tool" },
  { cmd: "START_STOP_DAQ_LIST", hex: "0xDE", desc: "Arm or stop the configured DAQ list on the ECU" }
];

const a2lBlocks = [
  "MEASUREMENT entries for each ETK-visible signal and memory address",
  "COMPU_METHOD and UNIT so INCA displays physical values instead of raw bytes",
  "RECORD_LAYOUT for the binary layout used by the ECU memory image",
  "IF_DATA XCP to describe transport-specific access details for the XCP stack",
  "CHARACTERISTIC blocks for calibratable constants, curves, or maps"
];

const nextStepItems = [
  "Verify ETK debug interface connection (DAP/JTAG/proprietary) and confirm XCP-over-Ethernet link to INCA.",
  "Generate or update the A2L with MEASUREMENT, CHARACTERISTIC, COMPU_METHOD, and RECORD_LAYOUT entries before opening INCA.",
  "Build the DAQ list in order: SET_DAQ_PTR, WRITE_DAQ, SET_DAQ_LIST_MODE, then START_STOP_DAQ_LIST.",
  "Validate scaling, units, and memory addresses against the ECU build before the first calibration session.",
  "Run CMM impact analysis before merging any AUTOSAR module changes that touch the exposed signals."
];

const sourceRefs = [
  "ASAM MCD-1 XCP v1.5",
  "ASAM MCD-2 MC v1.7.1",
  "ETAS ETK / INCA workflow",
  "FalkorDB verified nodes"
];

function scrollResultsPanel() {
  if (!ideResults) return;
  requestAnimationFrame(() => {
    ideResults.scrollTo({ top: ideResults.scrollHeight, behavior: "smooth" });
  });
}

function setWorkflowState(activeIndex) {
  workflowItems.forEach((item, index) => {
    item.classList.remove("is-active", "is-done");
    if (index < activeIndex) item.classList.add("is-done");
    if (index === activeIndex) item.classList.add("is-active");
  });

  const visibleSteps = activeIndex < 0 ? 0 : Math.min(activeIndex + 1, workflowItems.length);
  if (ideProgressFill) {
    ideProgressFill.style.width = `${(visibleSteps / Math.max(workflowItems.length, 1)) * 100}%`;
  }
}

function setThinkingState(label, done = false) {
  if (!thinkingChip) return;
  thinkingChip.textContent = label;
  thinkingChip.classList.toggle("is-done", done);
}

function appendChatMessage(type, label, html, extraClass = "") {
  if (!chatMessages) return;
  const msg = document.createElement("div");
  msg.className = `chat-msg ${type}-msg ${extraClass}`.trim();
  msg.innerHTML = `<span class="msg-label">${label}</span><p>${html}</p>`;
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function fillSourcePills(items) {
  if (!resultSources) return;
  resultSources.innerHTML = items.map((item) => `<span class="source-pill">${item}</span>`).join("");
}

function fillList(target, items) {
  if (!target) return;
  target.innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function restartIdeDemo() {
  ideTimers.forEach((timer) => clearTimeout(timer));
  ideTimers = [];

  if (chatMessages) {
    chatMessages.innerHTML = `
      <div class="chat-msg user-msg">
        <span class="msg-label">Engineer</span>
        <p>I am bringing up an ETAS ETK workflow for an AUTOSAR ECU. Which XCP DAQ commands do I need first, and what should I put in the A2L so INCA can read the signals correctly?</p>
      </div>`;
  }

  if (chatStatus) chatStatus.textContent = "Thinking";
  if (resultQuery) resultQuery.textContent = "Waiting for agent...";
  if (resultSources) resultSources.innerHTML = "";
  if (resultCount) resultCount.textContent = "0 hits";
  if (resultTableBody) resultTableBody.innerHTML = "";
  if (resultMemory) resultMemory.textContent = "Waiting for AMS restore...";
  fillList(a2lList, []);
  fillList(nextSteps, []);
  setWorkflowState(-1);
  setThinkingState("WAITING");
  if (ideResults) ideResults.scrollTop = 0;

  let elapsed = 0;
  const stages = [
    {
      delay: 2400,
      run: () => {
        if (chatStatus) chatStatus.textContent = "Restoring memory";
        setWorkflowState(0);
        setThinkingState("RESTORING");
        appendChatMessage("loom", "Loom", "Recovering your last ETK session, INCA workspace assumptions, and DAQ timing limits.", "thinking-msg");
      }
    },
    {
      delay: 4400,
      run: () => {
        if (resultMemory) {
          resultMemory.innerHTML = "<strong>Session 12 restored:</strong> ETK bring-up, debug interface connected, injector timing measurements, 100 ms DAQ budget, low ECU overhead constraint.";
        }
        if (chatStatus) chatStatus.textContent = "Querying graph";
        setWorkflowState(1);
        setThinkingState("QUERYING GRAPH");
        if (resultQuery) {
          resultQuery.textContent = "MATCH (s:Standard)-[:DEFINES]->(c:Command) WHERE s.title IN ['ASAM MCD-1 XCP','ASAM MCD-2 MC'] RETURN c.command, c.hex_code, c.description LIMIT 5";
        }
        if (resultCount) resultCount.textContent = "27 node hits";
        scrollResultsPanel();
      }
    },
    {
      delay: 4400,
      run: () => {
        if (chatStatus) chatStatus.textContent = "Verifying A2L";
        setWorkflowState(2);
        setThinkingState("VERIFYING A2L");
        fillSourcePills(sourceRefs);
        appendChatMessage("loom", "Loom", "Knowledge Foundation is pulling ASAM MCD-1 XCP for the DAQ sequence and ASAM MCD-2 MC for the A2L structure. ETAS ETK notes are being used to keep the workflow compatible with INCA and low-overhead acquisition.", "thinking-msg");
        scrollResultsPanel();
      }
    },
    {
      delay: 4400,
      run: () => {
        if (resultTableBody) {
          resultTableBody.innerHTML = xcpCommands.map((item) => `<tr><td>${item.cmd}</td><td>${item.hex}</td><td>${item.desc}</td></tr>`).join("");
        }
        if (resultCount) resultCount.textContent = "5 verified commands";
        if (chatStatus) chatStatus.textContent = "Returning result";
        setWorkflowState(3);
        setThinkingState("RETURNING RESULT");
        appendChatMessage("loom", "Loom", "Based on <strong>ASAM MCD-1 XCP v1.5</strong>, start with <strong>SET_DAQ_PTR</strong>, populate entries with <strong>WRITE_DAQ</strong>, set acquisition behavior with <strong>SET_DAQ_LIST_MODE</strong>, read timing with <strong>GET_DAQ_CLOCK</strong>, then arm the list with <strong>START_STOP_DAQ_LIST</strong>. That gives you the minimum verified DAQ sequence for ETK bring-up.");
        scrollResultsPanel();
      }
    },
    {
      delay: 4400,
      run: () => {
        if (chatStatus) chatStatus.textContent = "Checking A2L";
        appendChatMessage("user", "Engineer", "Good. What A2L blocks do I need so INCA can interpret the signals and calibration values correctly?");
        setThinkingState("CHECKING A2L");
      }
    },
    {
      delay: 4400,
      run: () => {
        fillList(a2lList, a2lBlocks);
        appendChatMessage("loom", "Loom", "For the A2L, use <strong>MEASUREMENT</strong> and <strong>CHARACTERISTIC</strong> to expose the ECU variables, then add <strong>COMPU_METHOD</strong>, <strong>UNIT</strong>, and <strong>RECORD_LAYOUT</strong> so INCA can interpret raw memory correctly. Add <strong>IF_DATA XCP</strong> for transport-specific access metadata. This follows <strong>ASAM MCD-2 MC v1.7.1</strong>, which defines data types, dimensions, record layouts, and memory locations in the A2L.");
        if (chatStatus) chatStatus.textContent = "Planning next step";
        setWorkflowState(4);
        setThinkingState("PLANNING NEXT STEP");
        scrollResultsPanel();
      }
    },
    {
      delay: 4400,
      run: () => {
        fillList(nextSteps, nextStepItems);
        if (chatStatus) chatStatus.textContent = "Guidance Ready";
        setWorkflowState(5);
        setThinkingState("READY", true);
        appendChatMessage("loom", "Loom", "Next, I would generate the first A2L scaffold, map the injector timing measurements to verified addresses, and run a CMM impact check before you modify any AUTOSAR communication or diagnostic modules.");
        scrollResultsPanel();
      }
    }
  ];

  stages.forEach((stage) => {
    elapsed += stage.delay;
    ideTimers.push(setTimeout(stage.run, elapsed));
  });
}

if (ideReplayBtn) {
  ideReplayBtn.addEventListener("click", restartIdeDemo);
}

// AUTOSAR Classic demo
const autosarChatMessages = document.getElementById("autosarChatMessages");
const autosarChatStatus = document.getElementById("autosarChatStatus");
const autosarThinkingChip = document.getElementById("autosarThinkingChip");
const autosarWorkflowItems = Array.from(document.querySelectorAll("#autosarWorkflowList .workflow-item"));
const autosarProgressFill = document.getElementById("autosarProgressFill");
const autosarIdeResults = document.getElementById("autosarIdeResults");
const autosarResultQuery = document.getElementById("autosarResultQuery");
const autosarResultSources = document.getElementById("autosarResultSources");
const autosarResultCount = document.getElementById("autosarResultCount");
const autosarResultTableBody = document.getElementById("autosarResultTableBody");
const autosarPaths = document.getElementById("autosarPaths");
const autosarNextSteps = document.getElementById("autosarNextSteps");
const autosarMemory = document.getElementById("autosarMemory");
const autosarReplayBtn = document.getElementById("autosarReplayBtn");
let autosarTimers = [];

const autosarModules = [
  { module: "Com", layer: "Services", role: "Packs signals into I-PDUs and monitors timeout/deadline behavior" },
  { module: "PduR", layer: "Services", role: "Routes PDUs statically between upper and lower communication layers" },
  { module: "CanIf", layer: "ECUAbstraction", role: "Standardized CAN interface between upper layers and CAN driver" },
  { module: "CanTp", layer: "Services", role: "Segments and reassembles diagnostic transport payloads over CAN" },
  { module: "Dcm", layer: "Services", role: "Implements diagnostic communication and uses CanTp via PduR" },
  { module: "CanSM / ComM", layer: "Services", role: "Handles bus-off recovery and communication mode coordination" }
];

const autosarPathItems = [
  "Signal path: SWC -> RTE -> Com -> PduR -> CanIf -> CanDrv -> CAN bus",
  "Diagnostic path: Dcm -> PduR -> CanTp -> CanIf -> CanDrv -> CAN bus",
  "Mode control path: ComM <-> CanSM <-> CanIf / CanDrv for bus-off and communication state handling",
  "Optional Ethernet diagnostic path: Dcm -> PduR -> SoAd -> TcpIp -> EthIf for DoIP-style extensions"
];

const autosarNextStepItems = [
  "Set up CanDrv controller timing, baud rate, hardware objects, and CAN IDs from the network matrix.",
  "Bind CanIf Tx/Rx PDUs to the correct upper layers and hardware handles.",
  "Create static PduR routing paths for both Com signal PDUs and Dcm diagnostic PDUs.",
  "Configure CanTp only for segmented diagnostic payloads larger than one CAN frame.",
  "Verify CanSM bus-off recovery and ComM communication modes before integration testing on target hardware."
];

const autosarSourceRefs = [
  "AUTOSAR Classic Platform",
  "AUTOSAR workflow example",
  "autosar_fused.db verified modules",
  "PduR routing notes"
];

function scrollAutosarResultsPanel() {
  if (!autosarIdeResults) return;
  requestAnimationFrame(() => {
    autosarIdeResults.scrollTo({ top: autosarIdeResults.scrollHeight, behavior: "smooth" });
  });
}

function setAutosarWorkflowState(activeIndex) {
  autosarWorkflowItems.forEach((item, index) => {
    item.classList.remove("is-active", "is-done");
    if (index < activeIndex) item.classList.add("is-done");
    if (index === activeIndex) item.classList.add("is-active");
  });
  const visibleSteps = activeIndex < 0 ? 0 : Math.min(activeIndex + 1, autosarWorkflowItems.length);
  if (autosarProgressFill) {
    autosarProgressFill.style.width = `${(visibleSteps / Math.max(autosarWorkflowItems.length, 1)) * 100}%`;
  }
}

function setAutosarThinkingState(label, done = false) {
  if (!autosarThinkingChip) return;
  autosarThinkingChip.textContent = label;
  autosarThinkingChip.classList.toggle("is-done", done);
}

function appendAutosarChatMessage(type, label, html, extraClass = "") {
  if (!autosarChatMessages) return;
  const msg = document.createElement("div");
  msg.className = `chat-msg ${type}-msg ${extraClass}`.trim();
  msg.innerHTML = `<span class="msg-label">${label}</span><p>${html}</p>`;
  autosarChatMessages.appendChild(msg);
  autosarChatMessages.scrollTop = autosarChatMessages.scrollHeight;
}

function fillAutosarPills(items) {
  if (!autosarResultSources) return;
  autosarResultSources.innerHTML = items.map((item) => `<span class="source-pill">${item}</span>`).join("");
}

function fillAutosarList(target, items) {
  if (!target) return;
  target.innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function restartAutosarDemo() {
  autosarTimers.forEach((timer) => clearTimeout(timer));
  autosarTimers = [];

  if (autosarChatMessages) {
    autosarChatMessages.innerHTML = `
      <div class="chat-msg user-msg">
        <span class="msg-label">Engineer</span>
        <p>I need AUTOSAR-compliant CAN communication for a body ECU. Which modules define the path for periodic COM signals and UDS diagnostics, and where do CanSM and ComM fit when bus-off recovery is required?</p>
      </div>`;
  }

  if (autosarChatStatus) autosarChatStatus.textContent = "Thinking";
  if (autosarResultQuery) autosarResultQuery.textContent = "Waiting for AUTOSAR module lookup...";
  if (autosarResultSources) autosarResultSources.innerHTML = "";
  if (autosarResultCount) autosarResultCount.textContent = "0 hits";
  if (autosarResultTableBody) autosarResultTableBody.innerHTML = "";
  if (autosarMemory) autosarMemory.textContent = "Waiting for AUTOSAR project context...";
  fillAutosarList(autosarPaths, []);
  fillAutosarList(autosarNextSteps, []);
  setAutosarWorkflowState(-1);
  setAutosarThinkingState("WAITING");
  if (autosarIdeResults) autosarIdeResults.scrollTop = 0;

  let elapsed = 0;
  const stages = [
    {
      delay: 2400,
      run: () => {
        if (autosarChatStatus) autosarChatStatus.textContent = "Restoring context";
        setAutosarWorkflowState(0);
        setAutosarThinkingState("RESTORING");
        appendAutosarChatMessage("loom", "Loom", "Recovering your Classic Platform ECU context: body controller, 500 kbps CAN, periodic status signals, UDS diagnostics, and mandatory bus-off recovery.", "thinking-msg");
      }
    },
    {
      delay: 4400,
      run: () => {
        if (autosarMemory) {
          autosarMemory.innerHTML = "<strong>Project context restored:</strong> body ECU, CAN 500 kbps, periodic COM signals every 20 ms, Dcm over CanTp, bus-off recovery required before bench testing.";
        }
        if (autosarChatStatus) autosarChatStatus.textContent = "Querying modules";
        setAutosarWorkflowState(1);
        setAutosarThinkingState("QUERYING GRAPH");
        if (autosarResultQuery) {
          autosarResultQuery.textContent = "MATCH (m:Module)-[:BELONGS_TO]->(l:Layer) WHERE m.name IN ['Com','PduR','CanIf','CanTp','Dcm','CanSM','ComM'] RETURN m.name, l.layer, m.description";
        }
        if (autosarResultCount) autosarResultCount.textContent = "7 verified modules";
        scrollAutosarResultsPanel();
      }
    },
    {
      delay: 4400,
      run: () => {
        if (autosarChatStatus) autosarChatStatus.textContent = "Validating routes";
        setAutosarWorkflowState(2);
        setAutosarThinkingState("VALIDATING STACK");
        fillAutosarPills(autosarSourceRefs);
        appendAutosarChatMessage("loom", "Loom", "Knowledge Foundation confirms the Classic Platform layering: <strong>Com</strong> handles signal packing and deadlines, <strong>PduR</strong> provides static routing, <strong>CanIf</strong> abstracts the CAN driver, <strong>CanTp</strong> carries segmented diagnostic traffic, and <strong>Dcm</strong> is the diagnostic upper layer using CanTp through PduR.", "thinking-msg");
        scrollAutosarResultsPanel();
      }
    },
    {
      delay: 4400,
      run: () => {
        if (autosarResultTableBody) {
          autosarResultTableBody.innerHTML = autosarModules.map((item) => `<tr><td>${item.module}</td><td>${item.layer}</td><td>${item.role}</td></tr>`).join("");
        }
        if (autosarResultCount) autosarResultCount.textContent = "6 core modules";
        fillAutosarList(autosarPaths, autosarPathItems);
        if (autosarChatStatus) autosarChatStatus.textContent = "Returning stack";
        setAutosarWorkflowState(3);
        setAutosarThinkingState("RETURNING RESULT");
        appendAutosarChatMessage("loom", "Loom", "For normal signal communication, use <strong>SWC -> RTE -> Com -> PduR -> CanIf -> CanDrv</strong>. For diagnostics, use <strong>Dcm -> PduR -> CanTp -> CanIf -> CanDrv</strong>. <strong>CanSM</strong> handles bus-off recovery and reports communication state upward to <strong>ComM</strong>.");
        scrollAutosarResultsPanel();
      }
    },
    {
      delay: 4400,
      run: () => {
        if (autosarChatStatus) autosarChatStatus.textContent = "Comparing COM vs DCM";
        appendAutosarChatMessage("user", "Engineer", "I also need periodic status signals and diagnostics in the same ECU. What is the practical difference between the COM path and the DCM path?", "");
        setAutosarThinkingState("CHECKING PATHS");
      }
    },
    {
      delay: 4400,
      run: () => {
        fillAutosarList(autosarNextSteps, autosarNextStepItems);
        appendAutosarChatMessage("loom", "Loom", "Use <strong>Com</strong> for scheduled application signals and deadline monitoring. Use <strong>Dcm + CanTp</strong> for diagnostic services when payloads exceed one CAN frame. Keep the routing tables in <strong>PduR</strong> static, bind IDs in <strong>CanIf</strong>, and verify mode transitions through <strong>CanSM</strong> and <strong>ComM</strong> before code generation and bench validation.");
        if (autosarChatStatus) autosarChatStatus.textContent = "Guidance Ready";
        setAutosarWorkflowState(4);
        setAutosarThinkingState("READY", true);
        scrollAutosarResultsPanel();
      }
    }
  ];

  stages.forEach((stage) => {
    elapsed += stage.delay;
    autosarTimers.push(setTimeout(stage.run, elapsed));
  });
}

if (autosarReplayBtn) {
  autosarReplayBtn.addEventListener("click", restartAutosarDemo);
}

// Slide 4: code tracking + memory demo
const intelligenceReplayBtn = document.getElementById("intelligenceReplayBtn");
const intelligenceThinkingChip = document.getElementById("intelligenceThinkingChip");
const intelligenceWorkflowState = document.getElementById("intelligenceWorkflowState");
const intelligenceProgressFill = document.getElementById("intelligenceProgressFill");
const intelligenceWorkflowItems = Array.from(document.querySelectorAll("#intelligenceWorkflowList .workflow-item"));
const intelligenceStatusTitle = document.getElementById("intelligenceStatusTitle");
const intelligenceStatusBody = document.getElementById("intelligenceStatusBody");
const intelligenceActionPills = Array.from(document.querySelectorAll("#intelligenceActionPills .source-pill"));
const traceImpactItems = Array.from(document.querySelectorAll("#traceImpactList .trace-impact-item"));
const mergeDecisionCard = document.getElementById("mergeDecisionCard");
const intelligenceOutcomeText = document.getElementById("intelligenceOutcomeText");
const intelligenceRiskPill = document.getElementById("intelligenceRiskPill");
let intelligenceTimers = [];

function setIntelligenceWorkflowState(activeIndex) {
  intelligenceWorkflowItems.forEach((item, index) => {
    item.classList.remove("is-active", "is-done");
    if (index < activeIndex) item.classList.add("is-done");
    if (index === activeIndex) item.classList.add("is-active");
  });
  const visibleSteps = activeIndex < 0 ? 0 : Math.min(activeIndex + 1, intelligenceWorkflowItems.length);
  if (intelligenceProgressFill) {
    intelligenceProgressFill.style.width = `${(visibleSteps / Math.max(intelligenceWorkflowItems.length, 1)) * 100}%`;
  }
}

function setIntelligenceActionStep(stepIndex) {
  intelligenceActionPills.forEach((pill, index) => {
    pill.classList.toggle("is-active", index === stepIndex);
  });
}

function setIntelligenceThinkingState(label, done = false) {
  if (intelligenceThinkingChip) {
    intelligenceThinkingChip.textContent = label;
    intelligenceThinkingChip.classList.toggle("is-done", done);
  }
  if (intelligenceWorkflowState) {
    intelligenceWorkflowState.textContent = label;
    intelligenceWorkflowState.classList.toggle("is-done", done);
  }
}

function setTraceImpactState(activeIndex) {
  traceImpactItems.forEach((item, index) => {
    item.classList.remove("is-active", "is-done");
    if (index < activeIndex) item.classList.add("is-done");
    if (index === activeIndex) item.classList.add("is-active");
  });
}

function setMergeDecision(state, message) {
  if (mergeDecisionCard) {
    mergeDecisionCard.classList.toggle("is-warning", state !== "safe");
    mergeDecisionCard.classList.toggle("is-safe", state === "safe");
  }
  if (intelligenceOutcomeText) intelligenceOutcomeText.textContent = message;
  if (intelligenceRiskPill) intelligenceRiskPill.textContent = state === "safe" ? "READY TO VALIDATE" : "RISK OPEN";
}

function restartIntelligenceDemo() {
  intelligenceTimers.forEach((timer) => clearTimeout(timer));
  intelligenceTimers = [];
  setIntelligenceWorkflowState(-1);
  setIntelligenceActionStep(-1);
  setTraceImpactState(-1);
  setIntelligenceThinkingState("WAITING");
  setMergeDecision("warning", "Waiting for trace + memory evidence.");
  if (intelligenceStatusTitle) intelligenceStatusTitle.textContent = "Start with a changed symbol, not a guess";
  if (intelligenceStatusBody) intelligenceStatusBody.textContent = "Loom turns a diff into concrete impact paths, then restores the engineering memory that should still constrain the fix.";
  setMemoryNode("objective");

  let elapsed = 0;
  const stages = [
    {
      delay: 2200,
      run: () => {
        setIntelligenceWorkflowState(0);
        setIntelligenceActionStep(0);
        setIntelligenceThinkingState("DETECT CHANGES");
        if (intelligenceStatusTitle) intelligenceStatusTitle.textContent = "Map the edited function from git diff";
        if (intelligenceStatusBody) intelligenceStatusBody.textContent = "CMM maps the exact symbol changed in CanIf_Transmit() so the engineer starts from code reality instead of prompt memory.";
        setMemoryNode("objective");
      }
    },
    {
      delay: 2600,
      run: () => {
        setIntelligenceWorkflowState(1);
        setIntelligenceActionStep(1);
        setIntelligenceThinkingState("TRACE CALL PATH");
        if (intelligenceStatusTitle) intelligenceStatusTitle.textContent = "Expose caller and downstream impact";
        if (intelligenceStatusBody) intelligenceStatusBody.textContent = "trace_call_path reveals COM and DCM traffic routes plus CanSM/ComM recovery checks that could regress if this merges blindly.";
        setTraceImpactState(0);
        setMemoryNode("session-b");
      }
    },
    {
      delay: 2600,
      run: () => {
        setIntelligenceWorkflowState(2);
        setIntelligenceActionStep(2);
        setIntelligenceThinkingState("RECALL");
        if (intelligenceStatusTitle) intelligenceStatusTitle.textContent = "Recover prior engineering intent";
        if (intelligenceStatusBody) intelligenceStatusBody.textContent = "AMS System recalls bench notes, guard rules, and module constraints from prior sessions before generating a recommendation.";
        setTraceImpactState(1);
        setMemoryNode("decision");
      }
    },
    {
      delay: 2600,
      run: () => {
        setIntelligenceWorkflowState(3);
        setIntelligenceActionStep(3);
        setIntelligenceThinkingState("REFLECT");
        if (intelligenceStatusTitle) intelligenceStatusTitle.textContent = "Combine code evidence with memory evidence";
        if (intelligenceStatusBody) intelligenceStatusBody.textContent = "Loom reflects on both data streams and flags remaining uncertainty at the bus recovery layer before allowing a merge recommendation.";
        setTraceImpactState(2);
        setMemoryNode("constraint");
      }
    },
    {
      delay: 2600,
      run: () => {
        setIntelligenceWorkflowState(4);
        setIntelligenceActionStep(4);
        setIntelligenceThinkingState("READY", true);
        setMergeDecision("safe", "Run CanSM + ComM regression checks, then merge if bus-off recovery stays intact.");
        if (intelligenceStatusTitle) intelligenceStatusTitle.textContent = "Safe next step, not just fast next step";
        if (intelligenceStatusBody) intelligenceStatusBody.textContent = "Final recommendation is grounded: trace paths checked, memory guardrails restored, and validation target explicitly named for the engineer.";
      }
    }
  ];

  stages.forEach((stage) => {
    elapsed += stage.delay;
    intelligenceTimers.push(setTimeout(stage.run, elapsed));
  });
}

if (intelligenceReplayBtn) {
  intelligenceReplayBtn.addEventListener("click", restartIntelligenceDemo);
}

const canvas = document.getElementById("falkorCanvas");
const ctx = canvas.getContext("2d");
const graphNodeName = document.getElementById("graphNodeName");
const graphNodeSummary = document.getElementById("graphNodeSummary");
const graphNodeType = document.getElementById("graphNodeType");
const graphNodeConfidence = document.getElementById("graphNodeConfidence");
const graphNodeLinks = document.getElementById("graphNodeLinks");
const graphProvenance = document.getElementById("graphProvenance");

const graphCenters = {
  Hub: { x: 0.5, y: 0.46 },
  Standard: { x: 0.18, y: 0.22 },
  Module: { x: 0.78, y: 0.28 },
  Artifact: { x: 0.48, y: 0.78 },
  Source: { x: 0.18, y: 0.78 },
  TextChunk: { x: 0.82, y: 0.76 },
  Concept: { x: 0.36, y: 0.18 },
  Parameter: { x: 0.62, y: 0.58 }
};

const graphPalette = {
  Hub: "#9333ea",
  Standard: "#06b6d4",
  Module: "#fbbf24",
  Artifact: "#fb7185",
  Source: "#14b8a6",
  TextChunk: "#a78bfa",
  Concept: "#34d399",
  Parameter: "#f59e0b"
};

const seedNodes = [
  { label: "loom_knowledge", type: "Hub", summary: "FalkorDB-backed knowledge graph joining AUTOSAR, ASAM, provenance, and retrieved engineering context.", source: ["falkordb", "graphiti", "loom_knowledge"], confidence: "1.00", links: 38 },
  { label: "AUTOSAR_CP_R24-11", type: "Standard", summary: "Classic Platform architecture separating application, RTE, and BSW layers.", source: ["autosar.org", "Classic Platform", "R24-11"], confidence: "0.97", links: 24 },
  { label: "ASAM_MCD-1_XCP", type: "Standard", summary: "Bus-independent measurement and calibration protocol for ECU access and DAQ acquisition.", source: ["asam.net", "MCD-1 XCP v1.5", "official datasheet"], confidence: "0.99", links: 21 },
  { label: "ASAM_MCD-2_MC", type: "Standard", summary: "A2L / ASAP2 description format for ECU memory layout, data types, and conversion methods.", source: ["asam.net", "MCD-2 MC v1.7.1", "A2L"], confidence: "0.99", links: 19 },
  { label: "Com", type: "Module", summary: "AUTOSAR COM packs signals into I-PDUs and monitors reception / transmission deadlines.", source: ["autosar_fused.db", "Com SWS", "confidence 0.9"], confidence: "0.90", links: 17 },
  { label: "PduR", type: "Module", summary: "Static PDU routing between upper and lower communication layers for signal and diagnostic traffic.", source: ["autosar_fused.db", "PduR SWS", "confidence 0.9"], confidence: "0.90", links: 18 },
  { label: "CanIf", type: "Module", summary: "Standardized CAN interface between upper layers and the CAN driver.", source: ["autosar_fused.db", "CanIf SRS", "confidence 0.9"], confidence: "0.90", links: 15 },
  { label: "CanTp", type: "Module", summary: "Segments and reassembles diagnostic payloads over CAN transport.", source: ["autosar_fused.db", "CanTp SWS", "confidence 0.9"], confidence: "0.90", links: 13 },
  { label: "Dcm", type: "Module", summary: "Diagnostic Communication Manager acting as upper layer for transport protocol reception and services.", source: ["autosar_fused.db", "Dcm SWS", "confidence 0.9"], confidence: "0.90", links: 14 },
  { label: "CanSM", type: "Module", summary: "CAN State Manager handling bus-off recovery and communication state changes.", source: ["autosar_fused.db", "CanSM SWS", "confidence 0.9"], confidence: "0.90", links: 11 },
  { label: "ComM", type: "Module", summary: "Communication Manager coordinating communication modes across channels and users.", source: ["autosar_fused.db", "ComM SWS", "confidence 0.90"], confidence: "0.90", links: 11 },
  { label: "CanDrv", type: "Module", summary: "Low-level CAN driver controlling hardware timing, mailboxes, and controller state.", source: ["AUTOSAR CAN Driver", "MCAL", "confidence 0.9"], confidence: "0.90", links: 9 },
  { label: "SoAd", type: "Module", summary: "Socket Adaptor providing PDU-based communication over TCP/IP sockets.", source: ["autosar_fused.db", "SoAd SWS", "confidence 0.9"], confidence: "0.90", links: 8 },
  { label: "TcpIp", type: "Module", summary: "TCP/IP stack submodules for socket-based communication and network services.", source: ["autosar_fused.db", "TcpIp SWS", "confidence 0.9"], confidence: "0.90", links: 8 },
  { label: "EthIf", type: "Module", summary: "Ethernet Interface abstracting Ethernet hardware and link state changes.", source: ["autosar_fused.db", "EthIf SRS", "confidence 0.95"], confidence: "0.95", links: 7 },
  { label: "A2L", type: "Artifact", summary: "ASAP2 text description of ECU variables, memory locations, units, and conversion methods.", source: ["domain_glossary", "A2L", "ASAM MCD-2 MC"], confidence: "0.99", links: 16 },
  { label: "ARXML", type: "Artifact", summary: "AUTOSAR XML configuration exchanged between tools for BSW and system descriptions.", source: ["AUTOSAR methodology", "workflow example", "tool exchange"], confidence: "0.94", links: 15 },
  { label: "I-PDU", type: "Artifact", summary: "Interaction Layer PDU carrying packed AUTOSAR signal data through the communication stack.", source: ["Com SWS", "PduR route", "confidence 0.9"], confidence: "0.90", links: 13 },
  { label: "ETAS_ETK", type: "Artifact", summary: "Development ECU interface used for measurement and calibration workflows with low ECU overhead.", source: ["ETAS product docs", "ETK/FETK", "measurement workflow"], confidence: "0.86", links: 9 },
  { label: "DAQ_List", type: "Artifact", summary: "Configured DAQ acquisition list describing which ECU signals stream back to the tool.", source: ["domain_glossary", "DAQ", "XCP commands"], confidence: "0.95", links: 12 },
  { label: "UDS_Request", type: "Artifact", summary: "Diagnostic request transported by Dcm and CanTp through routed PDUs.", source: ["Dcm", "CanTp", "diagnostic flow"], confidence: "0.88", links: 10 },
  { label: "DAQ", type: "Concept", summary: "XCP feature for high-speed measurement data streaming from ECU to tool.", source: ["domain_glossary", "DAQ", "ASAM"], confidence: "0.99", links: 12 },
  { label: "COMPU_METHOD", type: "Concept", summary: "Conversion method that maps raw ECU values to physical units in A2L / ODX descriptions.", source: ["domain_glossary", "COMPU-METHOD", "ASAM"], confidence: "0.97", links: 10 },
  { label: "BusOffRecovery", type: "Concept", summary: "Recovery behavior triggered after CAN bus-off events and handled by CanSM / ComM coordination.", source: ["CanSM SRS", "ComM indication", "confidence 0.9"], confidence: "0.90", links: 9 },
  { label: "DeadlineMonitoring", type: "Concept", summary: "COM monitoring of reception timeouts and transmission deadlines for periodic communication.", source: ["Com EXP", "timeouts", "deadline monitoring"], confidence: "0.90", links: 8 },
  { label: "SET_DAQ_PTR", type: "Parameter", summary: "XCP command used before writing entries into the DAQ list.", source: ["xcp_commands", "0xE2", "ASAM fused db"], confidence: "0.99", links: 8 },
  { label: "WRITE_DAQ", type: "Parameter", summary: "XCP command used to write each DAQ measurement entry.", source: ["xcp_commands", "0xE1", "ASAM fused db"], confidence: "0.99", links: 8 },
  { label: "SET_DAQ_LIST_MODE", type: "Parameter", summary: "XCP command used to configure DAQ list mode, event channel, and acquisition behavior.", source: ["xcp_commands", "0xE0", "ASAM fused db"], confidence: "0.99", links: 8 },
  { label: "START_STOP_DAQ_LIST", type: "Parameter", summary: "XCP command used to arm or stop a configured DAQ list.", source: ["xcp_commands", "0xDE", "ASAM fused db"], confidence: "0.99", links: 8 },
  { label: "GET_DAQ_CLOCK", type: "Parameter", summary: "XCP command used to read the slave DAQ clock for synchronization.", source: ["xcp_commands", "0xDC", "ASAM fused db"], confidence: "0.99", links: 8 },
  { label: "MAX_CTO", type: "Parameter", summary: "Maximum XCP Command Transfer Object size used by the tool and ECU stack.", source: ["protocol_parameters", "MAX_CTO", "confidence 0.83"], confidence: "0.83", links: 7 },
  { label: "P2", type: "Parameter", summary: "Diagnostic timing parameter used for UDS response timing.", source: ["protocol_parameters", "UDS-on-CAN", "P2"], confidence: "0.67", links: 6 },
  { label: "S3", type: "Parameter", summary: "Diagnostic server timing parameter used in UDS session handling.", source: ["protocol_parameters", "UDS-on-CAN", "S3"], confidence: "0.67", links: 6 },
  { label: "AUTOSAR_CP_WorkflowExample.zip", type: "Source", summary: "Official AUTOSAR workflow example for Classic Platform tool-chain neutral setup.", source: ["autosar.org", "workflow example", "official"], confidence: "0.95", links: 10 },
  { label: "KNOWLEDGE_ASAM.md", type: "Source", summary: "ASAM fused knowledge source providing XCP / ODX / MDF extracted concepts.", source: ["ASAMKnowledgeDB", "mistral_azrouter", "fused"], confidence: "0.90", links: 11 },
  { label: "fusion_log", type: "Source", summary: "Migration and fusion provenance for imported automotive knowledge artifacts.", source: ["autosar-fusion", "ASAMKnowledgeDB", "audit trail"], confidence: "1.00", links: 12 },
  { label: "AUTOSAR_SWS_PDURouter.pdf", type: "Source", summary: "Specification source for static routing and gateway behavior in the PDU Router.", source: ["AUTOSAR SWS", "PduR", "spec pdf"], confidence: "0.92", links: 9 },
  { label: "TextChunk_XCP_102", type: "TextChunk", summary: "Chunk referencing XCP protocol notes for DAQ list setup.", source: ["chunk_102", "XCP", "vector store"], confidence: "0.88", links: 5 },
  { label: "TextChunk_A2L_044", type: "TextChunk", summary: "Chunk describing A2L record layout and conversion metadata.", source: ["chunk_044", "A2L", "vector store"], confidence: "0.88", links: 5 },
  { label: "TextChunk_PDUR_118", type: "TextChunk", summary: "Chunk describing PDU Router static routing and gateway buffering.", source: ["chunk_118", "PduR", "vector store"], confidence: "0.88", links: 5 },
  { label: "TextChunk_COM_071", type: "TextChunk", summary: "Chunk describing AUTOSAR COM signal packing and deadline monitoring.", source: ["chunk_071", "Com", "vector store"], confidence: "0.88", links: 5 },
  { label: "TextChunk_CANTP_019", type: "TextChunk", summary: "Chunk describing CAN transport segmentation for diagnostic payloads.", source: ["chunk_019", "CanTp", "vector store"], confidence: "0.88", links: 5 },
  { label: "TextChunk_CANSM_033", type: "TextChunk", summary: "Chunk describing CanSM bus-off recovery and mode handling.", source: ["chunk_033", "CanSM", "vector store"], confidence: "0.88", links: 5 }
];

const graphNodes = [];
const graphEdges = [];
const graphNodeCount = seedNodes.length;
const graphRadiusMap = {
  Hub: 11,
  Standard: 8,
  Module: 7,
  Artifact: 7,
  Concept: 6,
  Parameter: 6,
  Source: 5.5,
  TextChunk: 5
};
const edgeSet = new Set();

for (let i = 0; i < graphNodeCount; i += 1) {
  const base = seedNodes[i];
  graphNodes.push({
    ...base,
    orbitX: (Math.random() - 0.5) * 240,
    orbitY: (Math.random() - 0.5) * 180,
    x: 0,
    y: 0,
    vx: (Math.random() - 0.5) * 0.26,
    vy: (Math.random() - 0.5) * 0.26,
    radius: graphRadiusMap[base.type] || 5
  });
}

const labelIndex = new Map(graphNodes.map((node, index) => [node.label, index]));

function pushGraphEdge(fromIndex, toIndex) {
  if (fromIndex == null || toIndex == null || fromIndex === toIndex) return;
  const a = Math.min(fromIndex, toIndex);
  const b = Math.max(fromIndex, toIndex);
  const key = `${a}-${b}`;
  if (edgeSet.has(key)) return;
  edgeSet.add(key);
  graphEdges.push([a, b]);
}

function connectLabels(fromLabel, toLabel) {
  pushGraphEdge(labelIndex.get(fromLabel), labelIndex.get(toLabel));
}

graphNodes.forEach((node) => {
  if (node.label !== "loom_knowledge") {
    connectLabels("loom_knowledge", node.label);
  }
});

[
  ["AUTOSAR_CP_R24-11", "Com"],
  ["AUTOSAR_CP_R24-11", "PduR"],
  ["AUTOSAR_CP_R24-11", "CanIf"],
  ["AUTOSAR_CP_R24-11", "CanTp"],
  ["AUTOSAR_CP_R24-11", "Dcm"],
  ["AUTOSAR_CP_R24-11", "CanSM"],
  ["AUTOSAR_CP_R24-11", "ComM"],
  ["AUTOSAR_CP_R24-11", "ARXML"],
  ["ASAM_MCD-1_XCP", "DAQ"],
  ["ASAM_MCD-1_XCP", "SET_DAQ_PTR"],
  ["ASAM_MCD-1_XCP", "WRITE_DAQ"],
  ["ASAM_MCD-1_XCP", "SET_DAQ_LIST_MODE"],
  ["ASAM_MCD-1_XCP", "START_STOP_DAQ_LIST"],
  ["ASAM_MCD-1_XCP", "GET_DAQ_CLOCK"],
  ["ASAM_MCD-1_XCP", "MAX_CTO"],
  ["ASAM_MCD-2_MC", "A2L"],
  ["ASAM_MCD-2_MC", "COMPU_METHOD"],
  ["ASAM_MCD-2_MC", "ETAS_ETK"],
  ["Com", "PduR"],
  ["Com", "I-PDU"],
  ["Com", "DeadlineMonitoring"],
  ["PduR", "CanIf"],
  ["PduR", "CanTp"],
  ["PduR", "Dcm"],
  ["CanIf", "CanDrv"],
  ["CanTp", "CanIf"],
  ["Dcm", "CanTp"],
  ["Dcm", "UDS_Request"],
  ["Dcm", "P2"],
  ["Dcm", "S3"],
  ["CanSM", "ComM"],
  ["CanSM", "BusOffRecovery"],
  ["CanSM", "CanIf"],
  ["ComM", "BusOffRecovery"],
  ["A2L", "COMPU_METHOD"],
  ["A2L", "ETAS_ETK"],
  ["DAQ", "DAQ_List"],
  ["DAQ_List", "SET_DAQ_PTR"],
  ["DAQ_List", "WRITE_DAQ"],
  ["DAQ_List", "SET_DAQ_LIST_MODE"],
  ["DAQ_List", "START_STOP_DAQ_LIST"],
  ["DAQ_List", "GET_DAQ_CLOCK"],
  ["AUTOSAR_CP_WorkflowExample.zip", "AUTOSAR_CP_R24-11"],
  ["AUTOSAR_SWS_PDURouter.pdf", "PduR"],
  ["KNOWLEDGE_ASAM.md", "ASAM_MCD-1_XCP"],
  ["KNOWLEDGE_ASAM.md", "ASAM_MCD-2_MC"],
  ["fusion_log", "loom_knowledge"],
  ["TextChunk_XCP_102", "ASAM_MCD-1_XCP"],
  ["TextChunk_XCP_102", "DAQ"],
  ["TextChunk_A2L_044", "A2L"],
  ["TextChunk_A2L_044", "COMPU_METHOD"],
  ["TextChunk_PDUR_118", "PduR"],
  ["TextChunk_COM_071", "Com"],
  ["TextChunk_CANTP_019", "CanTp"],
  ["TextChunk_CANSM_033", "CanSM"],
  ["SoAd", "TcpIp"],
  ["TcpIp", "EthIf"],
  ["Dcm", "SoAd"]
].forEach(([a, b]) => connectLabels(a, b));

graphNodes.forEach((source, i) => {
  graphNodes.forEach((target, j) => {
    if (j <= i) return;
    if (source.type === target.type && Math.random() > 0.92) {
      pushGraphEdge(i, j);
    }
  });
});

let hoveredGraphNode = null;
let selectedGraphNode = graphNodes.find((node) => node.label === "PduR") || graphNodes[0];

function resizeCanvas() {
  const parent = canvas.parentElement;
  const rect = parent.getBoundingClientRect();
  canvas.width = Math.max(320, Math.floor(rect.width));
  canvas.height = Math.max(620, Math.floor(rect.height));
}

function updateInspector(node) {
  if (!node) return;
  graphNodeName.textContent = node.label;
  graphNodeSummary.textContent = node.summary;
  graphNodeType.textContent = node.type;
  graphNodeConfidence.textContent = node.confidence;
  graphNodeLinks.textContent = String(node.links);
  graphProvenance.innerHTML = "";
  node.source.forEach((item) => {
    const chip = document.createElement("span");
    chip.className = "provenance-pill";
    chip.textContent = item;
    graphProvenance.appendChild(chip);
  });
}

function nearestGraphNode(x, y) {
  let closest = null;
  let bestDistance = Infinity;
  for (const node of graphNodes) {
    const dx = node.x - x;
    const dy = node.y - y;
    const distance = Math.sqrt(dx * dx + dy * dy);
    if (distance < bestDistance && distance < node.radius + 10) {
      bestDistance = distance;
      closest = node;
    }
  }
  return closest;
}

canvas.addEventListener("mousemove", (event) => {
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  hoveredGraphNode = nearestGraphNode(x, y);
  canvas.style.cursor = hoveredGraphNode ? "pointer" : "default";
  if (hoveredGraphNode) {
    updateInspector(hoveredGraphNode);
  } else {
    updateInspector(selectedGraphNode);
  }
});

canvas.addEventListener("mouseleave", () => {
  hoveredGraphNode = null;
  updateInspector(selectedGraphNode);
  canvas.style.cursor = "default";
});

canvas.addEventListener("click", () => {
  if (hoveredGraphNode) {
    selectedGraphNode = hoveredGraphNode;
    updateInspector(selectedGraphNode);
  }
});

function animateGraph() {
  if (!canvas.width || !canvas.height) {
    resizeCanvas();
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "rgba(15, 23, 42, 1)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  graphNodes.forEach((node) => {
    const center = graphCenters[node.type];
    const targetX = center.x * canvas.width + node.orbitX;
    const targetY = center.y * canvas.height + node.orbitY;

    if (node.x === 0 && node.y === 0) {
      node.x = targetX;
      node.y = targetY;
    }

    node.vx += (targetX - node.x) * 0.0018;
    node.vy += (targetY - node.y) * 0.0018;
    node.vx *= 0.985;
    node.vy *= 0.985;
    node.x += node.vx;
    node.y += node.vy;
  });

  ctx.lineWidth = 1.15;
  graphEdges.forEach(([fromIndex, toIndex]) => {
    const from = graphNodes[fromIndex];
    const to = graphNodes[toIndex];
    const selectedEdge = selectedGraphNode && (selectedGraphNode === from || selectedGraphNode === to);
    ctx.strokeStyle = selectedEdge ? "rgba(96, 165, 250, 0.62)" : "rgba(148, 163, 184, 0.22)";
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
  });

  graphNodes.forEach((node) => {
    const isSelected = node === selectedGraphNode;
    const isHovered = node === hoveredGraphNode;
    const radius = isSelected ? node.radius + 2.5 : isHovered ? node.radius + 1.5 : node.radius;

    ctx.beginPath();
    ctx.fillStyle = graphPalette[node.type];
    ctx.shadowBlur = isSelected ? 18 : 10;
    ctx.shadowColor = graphPalette[node.type];
    ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    if (isSelected || isHovered || ["Hub", "Standard", "Module", "Artifact", "Concept", "Parameter"].includes(node.type)) {
      const labelX = node.x + 10;
      const labelY = node.y - 10;
      ctx.font = "12px JetBrains Mono";
      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(15, 23, 42, 0.92)";
      ctx.strokeText(node.label, labelX, labelY);
      ctx.fillStyle = "rgba(248, 250, 252, 0.98)";
      ctx.fillText(node.label, labelX, labelY);
    }
  });

  requestAnimationFrame(animateGraph);
}

const memoryDetailTitle = document.getElementById("memoryDetailTitle");
const memoryDetailBody = document.getElementById("memoryDetailBody");
const memoryDetailMeta = document.getElementById("memoryDetailMeta");
const memoryNodes = Array.from(document.querySelectorAll(".memory-node"));

const memoryMap = {
  objective: {
    title: "Current Task",
    body: "Open the exact communication path affected by the changed symbol and restore the design rules that should still govern the fix.",
    meta: ["current task", "active context", "highest priority"]
  },
  "session-a": {
    title: "Mental Models",
    body: "Reusable summaries the agent checks first, like 'this ECU uses AUTOSAR Classic communication services and bus-off recovery must stay enabled.'",
    meta: ["memory bank", "high priority", "summary layer"]
  },
  "session-b": {
    title: "Observed Patterns",
    body: "Consolidated patterns learned from past work, such as COM and DCM sharing lower CAN layers but following different upper routing paths.",
    meta: ["synthesized", "pattern", "cross-session"]
  },
  steering: {
    title: "Raw Facts",
    body: "Exact facts the system can recall later: module names, stack paths, timing values, and the guardrails captured during implementation.",
    meta: ["facts", "retrieved", "source backed"]
  },
  decision: {
    title: "Experience Facts",
    body: "What happened in prior work: the last bench run hit bus-off during wakeup, and the engineer decided not to change CAN IDs until recovery was revalidated.",
    meta: ["history", "bench result", "team memory"]
  },
  constraint: {
    title: "Guard Rule",
    body: "A rule the next session should still obey: do not merge the transport-layer change until CanSM and ComM behavior are checked against the changed CanIf path.",
    meta: ["guardrail", "must remember", "merge blocker"]
  }
};

function setMemoryNode(key) {
  const details = memoryMap[key];
  if (!details) return;
  memoryNodes.forEach((node) => {
    node.classList.toggle("is-selected", node.dataset.memoryKey === key);
  });
  memoryDetailTitle.textContent = details.title;
  memoryDetailBody.textContent = details.body;
  memoryDetailMeta.innerHTML = "";
  details.meta.forEach((item) => {
    const pill = document.createElement("span");
    pill.className = "memory-pill provenance-pill";
    pill.textContent = item;
    memoryDetailMeta.appendChild(pill);
  });
}

memoryNodes.forEach((node) => {
  node.addEventListener("click", () => setMemoryNode(node.dataset.memoryKey));
});

let countersAnimated = false;
const metricsSection = document.getElementById("impact");

function animateCounter(counter) {
  const target = Number(counter.dataset.target);
  const duration = 1100;
  const start = performance.now();

  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    counter.textContent = String(Math.round(target * eased));
    if (progress < 1) {
      requestAnimationFrame(tick);
    } else {
      counter.textContent = String(target);
    }
  }

  requestAnimationFrame(tick);
}

function animateCountersOnce() {
  if (countersAnimated) return;
  countersAnimated = true;
  document.querySelectorAll(".counter").forEach(animateCounter);
}

if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          animateCountersOnce();
        }
      });
    },
    { threshold: 0.35 }
  );
  observer.observe(metricsSection);
} else {
  setTimeout(animateCountersOnce, 900);
}

window.addEventListener("resize", resizeCanvas);
resizeCanvas();
updateInspector(selectedGraphNode);
setMemoryNode("objective");
goToSlide(0);
animateGraph();

// Problem Carousel
const problemTrack = document.getElementById("problemTrack");
const problemNav = document.getElementById("problemNav");
const problemPrev = document.getElementById("problemPrev");
const problemNext = document.getElementById("problemNext");
const problemDots = problemNav ? Array.from(problemNav.querySelectorAll(".problem-nav-dot")) : [];
const problemCards = problemTrack ? Array.from(problemTrack.querySelectorAll(".problem-card")) : [];

function getCardWidth() {
  if (!problemCards.length) return 340;
  return problemCards[0].offsetWidth + 20;
}

function updateProblemDots() {
  if (!problemTrack || problemCards.length === 0) return;
  const scrollLeft = problemTrack.scrollLeft;
  const trackWidth = problemTrack.scrollWidth - problemTrack.clientWidth;
  const scrollPercent = trackWidth > 0 ? scrollLeft / trackWidth : 0;
  const activeIndex = Math.min(
    Math.round(scrollPercent * (problemCards.length - 1)),
    problemCards.length - 1
  );
  problemDots.forEach((dot, index) => {
    dot.classList.toggle("is-active", index === activeIndex);
  });
}

if (problemTrack) {
  problemTrack.addEventListener("scroll", updateProblemDots);
}

problemDots.forEach((dot) => {
  dot.addEventListener("click", () => {
    const index = parseInt(dot.dataset.index, 10);
    const cardWidth = getCardWidth();
    problemTrack.scrollTo({ left: index * cardWidth, behavior: "smooth" });
  });
});

// Arrow navigation
if (problemPrev) {
  problemPrev.addEventListener("click", () => {
    const cardWidth = getCardWidth();
    problemTrack.scrollBy({ left: -cardWidth, behavior: "smooth" });
  });
}

if (problemNext) {
  problemNext.addEventListener("click", () => {
    const cardWidth = getCardWidth();
    problemTrack.scrollBy({ left: cardWidth, behavior: "smooth" });
  });
}

// Mouse drag scrolling
if (problemTrack) {
  let isDown = false;
  let startX;
  let scrollLeft;

  problemTrack.addEventListener("mousedown", (e) => {
    isDown = true;
    problemTrack.classList.add("is-dragging");
    startX = e.pageX - problemTrack.offsetLeft;
    scrollLeft = problemTrack.scrollLeft;
  });

  problemTrack.addEventListener("mouseleave", () => {
    isDown = false;
    problemTrack.classList.remove("is-dragging");
  });

  problemTrack.addEventListener("mouseup", () => {
    isDown = false;
    problemTrack.classList.remove("is-dragging");
  });

  problemTrack.addEventListener("mousemove", (e) => {
    if (!isDown) return;
    e.preventDefault();
    const x = e.pageX - problemTrack.offsetLeft;
    const walk = (x - startX) * 1.5;
    problemTrack.scrollLeft = scrollLeft - walk;
  });
}
