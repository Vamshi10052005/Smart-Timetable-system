const API_URL = "http://127.0.0.1:5000";

let availableLecturers = [];
let availableSubjects = [];
let availableSections = [];
let definedTimeSlots = [];
let definedAssignments = [];

let editingAssignmentId = null;
let currentSectionId = null;
let currentActiveCell = null;
let currentTimetableData = null;
// cache of last generated timetable for all sections (not only saved ones)
let localTimetables = null;

let fixedSlots = []; // loaded from backend
let editingSectionId = null; // for section edit

// ---------------------------------------------------------------
// INIT
// ---------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  loadInitialData();

  const modal = document.getElementById("fix-slot-modal");
  const closeBtn = document.querySelector(".close-btn");

  if (closeBtn) {
    closeBtn.onclick = () => {
      modal.style.display = "none";
      currentActiveCell = null;
    };
  }

  window.onclick = (e) => {
    if (e.target === modal) {
      modal.style.display = "none";
      currentActiveCell = null;
    }
  };

  // ✅ BOTH buttons use regenerateTimetable (which also saves to DB)
  document
    .getElementById("generateBtn")
    ?.addEventListener("click", regenerateTimetable);

  document
    .getElementById("regenerateBtn")
    ?.addEventListener("click", regenerateTimetable);

  document.getElementById("loadBtn")?.addEventListener("click", loadTimetable);

  // ✅ Download PDF button
  document.getElementById("pdfBtn")?.addEventListener("click", downloadPDF);

  // Simple clash
  document
    .getElementById("clashBtn")
    ?.addEventListener("click", checkAllClashes);

  // Detailed clash (if you added this earlier)
  document
    .getElementById("detailedClashBtn")
    ?.addEventListener("click", detailedClashAnalysis);

  // Fixed slot save
  document
    .getElementById("save-fixed-slot")
    ?.addEventListener("click", saveFixedSlot);

  // Optional: remove fixed slot button (if you added it)
  document
    .getElementById("remove-fixed-slot")
    ?.addEventListener("click", removeFixedSlot);

  // Clear data buttons
  document
    .getElementById("clear-lecturers-btn")
    ?.addEventListener("click", () => clearAllData("lecturers"));

  document
    .getElementById("clear-subjects-btn")
    ?.addEventListener("click", () => clearAllData("subjects"));

  // Forms
  document
    .getElementById("slot-form")
    ?.addEventListener("submit", handleAddSlot);

  document
    .getElementById("section-form")
    ?.addEventListener("submit", handleAddSection);

  document
    .getElementById("assignment-form")
    ?.addEventListener("submit", handleAddAssignment);
});

// ---------------------------------------------------------------
// Load Initial Data
// ---------------------------------------------------------------
async function loadInitialData() {
  try {
    const res = await fetch(`${API_URL}/api/data`);
    const data = await res.json();

    availableLecturers = data.lecturers || [];
    availableSubjects = data.subjects || [];
    availableSections = data.sections || [];
    definedTimeSlots = data.time_slots || [];
    definedAssignments = data.assignments || [];

    await loadFixedSlotsFromServer();

    renderList(
      "slot-list",
      definedTimeSlots.map((t) => ({
        id: t.id,
        text: `${t.name} (${t.start}-${t.end}) ${t.is_break ? "[BREAK]" : ""}`,
        data: t,
      })),
      "timeslots"
    );

    renderList(
      "section-list",
      availableSections.map((s) => ({
        id: s.id,
        text: s.display_name,
        data: s,
      })),
      "sections"
    );

    renderList(
      "assignment-list",
      definedAssignments.map((a) => ({
        id: a.id,
        text: `${a.section}: ${a.subject} → ${a.lecturer} (${a.weekly_count}x/week)`,
        data: a,
      })),
      "assignments"
    );

    populateSelect(
      "assign-section",
      availableSections,
      "id",
      "display_name",
      "-- Select Section --"
    );
    populateSelect(
      "assign-subject",
      availableSubjects,
      "id",
      "name",
      "-- Select Subject --"
    );
    populateSelect(
      "assign-lecturer",
      availableLecturers,
      "id",
      "name",
      "-- Select Lecturer --"
    );

    populateSectionTabs(availableSections);

    populateSelect(
      "subject-select",
      availableSubjects,
      "id",
      "name",
      "-- Select Subject --"
    );
    populateSelect(
      "lecturer-select",
      availableLecturers,
      "id",
      "name",
      "-- Select Lecturer --"
    );
  } catch (err) {
    alert("Backend not running.");
    console.error(err);
  }
}

// ---------------------------------------------------------------
// Upload Combined CSV (Lecturer + Subject)
// ---------------------------------------------------------------
async function uploadCombinedFile() {
  const fileInput = document.getElementById("combinedFile");
  const statusEl = document.getElementById("upload-status");

  if (!fileInput || !fileInput.files.length) {
    alert("Please choose a CSV / Excel file first.");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]); // key must be "file"

  try {
    const res = await fetch(`${API_URL}/upload/combined_list`, {
      method: "POST",
      body: formData,
    });

    const json = await res.json();

    if (!res.ok || json.error) {
      statusEl.textContent = json.error || "Upload failed.";
      statusEl.style.color = "red";
      return;
    }

    statusEl.textContent = json.success || "Upload success.";
    statusEl.style.color = "green";

    await loadInitialData();
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Upload error (check backend).";
    statusEl.style.color = "red";
  }
}

// ---------------------------------------------------------------
// Load fixed slots from server
// ---------------------------------------------------------------
async function loadFixedSlotsFromServer() {
  try {
    const r = await fetch(`${API_URL}/api/fixed_slots`);
    const d = await r.json();
    fixedSlots = d.fixed_slots || [];
  } catch (e) {
    console.error("Failed to load fixed slots", e);
    fixedSlots = [];
  }
}

// Sync fixed slots to server
async function syncFixedSlotsToServer() {
  try {
    const res = await fetch(`${API_URL}/api/fixed_slots`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fixed_slots: fixedSlots }),
    });

    const json = await res.json();

    if (!res.ok || json.error) {
      alert("Fixed slot error: " + (json.error || "Server error"));
      return false;
    }

    if (json.warning) {
      alert("Warning: " + json.warning);
    }

    return true;
  } catch (e) {
    alert("Could not save fixed slot.");
    return false;
  }
}

// ---------------------------------------------------------------
// Section Tabs
// ---------------------------------------------------------------
function populateSectionTabs(sections) {
  const tabs = document.getElementById("class-tabs-container");
  if (!tabs) return;

  tabs.innerHTML = "";

  if (!sections.length) {
    tabs.innerHTML = `<div class="tab-info">Add sections to see tabs</div>`;
    return;
  }

  sections.forEach((section, idx) => {
    const tab = document.createElement("div");
    tab.className = "tab";
    tab.dataset.sectionId = section.id;
    tab.innerText = section.display_name;

    tab.addEventListener("click", async () => {
      document
        .querySelectorAll(".tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      currentSectionId = section.id;

      createGrid(section.id);
      await loadTimetableForCurrentSection();
    });

    if (idx === 0) {
      tab.classList.add("active");
      currentSectionId = section.id;
    }

    tabs.appendChild(tab);
  });

  if (currentSectionId) {
    createGrid(currentSectionId);
    setTimeout(loadTimetableForCurrentSection, 300);
  }
}

// ---------------------------------------------------------------
// Create Grid
// ---------------------------------------------------------------
function createGrid(sectionId) {
  const grid = document.getElementById("timetable-grid");
  grid.innerHTML = "";
  grid.className = "grid-container";

  const days = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ];
  const slots = definedTimeSlots;

  grid.style.gridTemplateColumns = `140px repeat(${slots.length}, 1fr)`;

  // Header
  const corner = document.createElement("div");
  corner.className = "grid-cell grid-header time-header";
  corner.textContent = "Time / Day";
  grid.appendChild(corner);

  slots.forEach((slot) => {
    const col = document.createElement("div");
    col.className = "grid-cell grid-header day-header";
    col.innerHTML = `${to12(slot.start)}<br>${to12(slot.end)}`;
    grid.appendChild(col);
  });

  // Rows
  days.forEach((day) => {
    const d = document.createElement("div");
    d.className = "grid-cell grid-header time-slot-header";
    d.innerHTML = `<strong>${day}</strong>`;
    grid.appendChild(d);

    slots.forEach((slot) => {
      const cell = document.createElement("div");
      cell.className = "grid-cell";
      cell.dataset.day = day;
      cell.dataset.timeslotid = slot.id;
      cell.dataset.sectionid = sectionId;

      if (slot.is_break) {
        cell.classList.add("break");
        cell.innerHTML = "<strong>BREAK</strong>";
      } else {
        const fs = findFixedSlot(sectionId, slot.id, day);
        if (fs) {
          cell.classList.add("fixed");
          if (fs.custom_label) {
            cell.innerHTML = `<strong>${fs.custom_label}</strong>`;
          } else {
            const sub = availableSubjects.find((s) => s.id === fs.subject_id);
            const lec = availableLecturers.find((l) => l.id === fs.lecturer_id);
            cell.innerHTML = `<strong>${sub?.name || ""}</strong><br><small>${
              lec?.name || ""
            }</small>`;
          }
          // ✅ allow editing fixed slot by clicking
          cell.addEventListener("click", () => handleSlotClick(cell));
        } else {
          cell.innerHTML = "Available";
          cell.addEventListener("click", () => handleSlotClick(cell));
        }
      }

      grid.appendChild(cell);
    });
  });
}

function to12(t) {
  try {
    let [h, m] = t.split(":");
    h = parseInt(h);
    let ampm = h >= 12 ? "PM" : "AM";
    let hh = h % 12 || 12;
    return `${hh}:${m} ${ampm}`;
  } catch {
    return t;
  }
}

// ---------------------------------------------------------------
// Slot Click
// ---------------------------------------------------------------
function handleSlotClick(cell) {
  currentActiveCell = cell;

  const modal = document.getElementById("fix-slot-modal");

  const day = cell.dataset.day;
  const sectionId = parseInt(cell.dataset.sectionid);
  const slotId = parseInt(cell.dataset.timeslotid);
  const slot = definedTimeSlots.find((s) => s.id == slotId);

  document.getElementById("modal-title").innerText = `Assign Slot (${day})`;
  document.getElementById(
    "modal-subtitle"
  ).innerText = `${slot.name} (${slot.start}-${slot.end})`;

  const subjectSelect = document.getElementById("subject-select");
  const lecturerSelect = document.getElementById("lecturer-select");
  const customInput = document.getElementById("custom-label-input");
  const removeBtn = document.getElementById("remove-fixed-slot");

  // Reset modal fields
  subjectSelect.value = "";
  lecturerSelect.value = "";
  customInput.value = "";

  const existing = findFixedSlot(sectionId, slotId, day);

  // if fixed → show remove button
  if (existing) {
    removeBtn.style.display = "block";

    if (existing.custom_label) {
      customInput.value = existing.custom_label;
    } else {
      subjectSelect.value = existing.subject_id || "";
      lecturerSelect.value = existing.lecturer_id || "";
    }
  } else {
    removeBtn.style.display = "none";
  }

  modal.style.display = "block";
}

// ---------------------------------------------------------------
// Save Fixed Slot
// ---------------------------------------------------------------
async function saveFixedSlot() {
  const modal = document.getElementById("fix-slot-modal");
  if (!currentActiveCell) {
    modal.style.display = "none";
    return;
  }

  const day = currentActiveCell.dataset.day;
  const sectionId = parseInt(currentActiveCell.dataset.sectionid);
  const slotId = parseInt(currentActiveCell.dataset.timeslotid);

  const subjectId = document.getElementById("subject-select").value;
  const lecturerId = document.getElementById("lecturer-select").value;
  const customLabel = document
    .getElementById("custom-label-input")
    .value.trim();

  if (!customLabel && (!subjectId || !lecturerId)) {
    alert("Select subject + lecturer OR enter custom label");
    return;
  }

  // remove existing
  fixedSlots = fixedSlots.filter(
    (fs) =>
      !(
        fs.class_section_id === sectionId &&
        fs.time_slot_id === slotId &&
        fs.day === day
      )
  );

  // add new
  const newSlot = {
    class_section_id: sectionId,
    day,
    time_slot_id: slotId,
  };

  if (customLabel) {
    newSlot.custom_label = customLabel;
  } else {
    newSlot.subject_id = parseInt(subjectId);
    newSlot.lecturer_id = parseInt(lecturerId);
  }

  fixedSlots.push(newSlot);

  const ok = await syncFixedSlotsToServer();
  if (!ok) {
    fixedSlots = fixedSlots.filter(
      (fs) =>
        !(
          fs.class_section_id === sectionId &&
          fs.time_slot_id === slotId &&
          fs.day === day
        )
    );
    return;
  }

  await loadFixedSlotsFromServer();
  createGrid(sectionId);
  await loadTimetableForCurrentSection();

  modal.style.display = "none";
  currentActiveCell = null;
}

document
  .getElementById("remove-fixed-slot")
  ?.addEventListener("click", removeFixedSlot);

async function removeFixedSlot() {
  if (!currentActiveCell) return;

  const sectionId = parseInt(currentActiveCell.dataset.sectionid);
  const slotId = parseInt(currentActiveCell.dataset.timeslotid);
  const day = currentActiveCell.dataset.day;

  // Remove ONLY this slot
  fixedSlots = fixedSlots.filter(
    (fs) =>
      !(
        fs.class_section_id === sectionId &&
        fs.time_slot_id === slotId &&
        fs.day === day
      )
  );

  const ok = await syncFixedSlotsToServer();
  if (!ok) return;

  await loadFixedSlotsFromServer();
  createGrid(sectionId);
  await loadTimetableForCurrentSection();

  document.getElementById("fix-slot-modal").style.display = "none";
  currentActiveCell = null;
}

function findFixedSlot(sectionId, slotId, day) {
  return fixedSlots.find(
    (fs) =>
      fs.class_section_id === sectionId &&
      fs.time_slot_id === slotId &&
      fs.day === day
  );
}

// ---------------------------------------------------------------
// Display generated timetable
// ---------------------------------------------------------------
function displayGeneratedTimetable(data) {
  if (!data) return;

  const section = availableSections.find((s) => s.id == currentSectionId);
  if (!section) return;

  const secName = section.display_name;
  const days = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ];

  definedTimeSlots.forEach((slot) => {
    days.forEach((day) => {
      const cell = document.querySelector(
        `.grid-cell[data-day="${day}"][data-timeslotid="${slot.id}"][data-sectionid="${currentSectionId}"]`
      );

      if (
        !cell ||
        cell.classList.contains("fixed") ||
        cell.classList.contains("break")
      )
        return;

      cell.innerHTML = "Empty";
      cell.classList.remove("generated", "system-assigned");

      let cellVal = null;

      if (
        data[secName] &&
        data[secName][day] &&
        data[secName][day][slot.display_name]
      ) {
        cellVal = data[secName][day][slot.display_name];
      }

      if (!cellVal) return;

      if (Array.isArray(cellVal)) {
        const subject = availableSubjects.find((s) => s.id === cellVal[1]);
        const lect = availableLecturers.find((l) => l.id === cellVal[2]);

        cell.innerHTML = `<strong>${subject?.name || ""}</strong><br><small>${
          lect?.name || ""
        }</small>`;
        cell.classList.add("generated");
      }
    });
  });
}

// ---------------------------------------------------------------
// Generate Timetable
// ---------------------------------------------------------------

async function generateTimetable() {
  try {
    const r = await fetch(`${API_URL}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fixed_slots: fixedSlots }),
    });

    const json = await r.json();
    if (json.error) {
      alert(json.error);
      return;
    }

    // cache full timetable in memory
    localTimetables = json.timetable;
    currentTimetableData = json.timetable;

    displayGeneratedTimetable(json.timetable);

    alert("Generated (preview only). Use 'Regenerate New Version' to save.");
  } catch (err) {
    console.error(err);
    alert("Error generating timetable.");
  }
}

// ---------------------------------------------------------------
// Regenerate ONLY current section
// ---------------------------------------------------------------

async function regenerateTimetable() {
  if (!currentSectionId) {
    alert("Select a section");
    return;
  }

  try {
    const r = await fetch(`${API_URL}/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fixed_slots: fixedSlots,
        section_id: currentSectionId, // tell backend which section to regenerate
      }),
    });

    const json = await r.json();

    if (!r.ok || json.error) {
      alert(json.error || "Error regenerating timetable.");
      return;
    }

    // Find the display name of the current section
    const section = availableSections.find((s) => s.id == currentSectionId);
    if (!section) {
      alert("Section not found in UI.");
      return;
    }
    const secName = section.display_name;

    // Ensure we have an object to store timetables
    if (!currentTimetableData || typeof currentTimetableData !== "object") {
      currentTimetableData = {};
    }

    // Backend may send section_timetable (only this section)
    // or full timetable. Prefer section_timetable if present.
    if (json.section_timetable && json.section_timetable[secName]) {
      currentTimetableData[secName] = json.section_timetable[secName];
    } else if (json.timetable && json.timetable[secName]) {
      currentTimetableData[secName] = json.timetable[secName];
    } else {
      alert("No timetable data returned for this section.");
      return;
    }

    alert("Regenerated timetable for selected section only.");

    // Now redraw grid using the combined data:
    // - this section: new version
    // - other sections: old versions remain untouched
    displayGeneratedTimetable(currentTimetableData);
  } catch (err) {
    console.error(err);
    alert("Error regenerating.");
  }
}

// ---------------------------------------------------------------
// Load saved timetable
// ---------------------------------------------------------------
async function loadTimetable() {
  if (!currentSectionId) {
    alert("Select a section");
    return;
  }

  try {
    const r = await fetch(`${API_URL}/api/timetable/load/${currentSectionId}`);
    const json = await r.json();

    if (json.success) {
      currentTimetableData = json.timetable_data;
      displayGeneratedTimetable(json.timetable_data);
      alert("Loaded");
    } else {
      alert(json.error || "No saved timetable");
    }
  } catch {
    alert("Load error");
  }
}

async function loadTimetableForCurrentSection() {
  if (!currentSectionId) return;

  try {
    const r = await fetch(`${API_URL}/api/timetable/load/${currentSectionId}`);
    const json = await r.json();

    if (r.ok && json.success) {
      // There is a saved timetable in DB for this section
      currentTimetableData = json.timetable_data;
      displayGeneratedTimetable(json.timetable_data);
      return;
    }

    // If no saved timetable but we still have in-memory data,
    // use that to show the timetable for this section.
    if (currentTimetableData) {
      displayGeneratedTimetable(currentTimetableData);
    }
  } catch (e) {
    console.error(e);
    // On error, still try to use in-memory timetable if available
    if (currentTimetableData) {
      displayGeneratedTimetable(currentTimetableData);
    }
  }
}

// ---------------------------------------------------------------
// Clash Check
// ---------------------------------------------------------------
async function checkAllClashes() {
  try {
    const r = await fetch(`${API_URL}/api/check_clashes`);
    const json = await r.json();

    if (json.error) {
      alert(json.error);
      return;
    }

    const clashes = json.clashes;

    if (!clashes.length) {
      alert("No clashes!");
      return;
    }

    let msg = "⚠ CLASHES:\n\n";
    clashes.forEach((c, idx) => {
      msg += `${idx + 1}) ${c.type}\n`;
      msg += `   Day: ${c.day}\n`;
      msg += `   Time: ${c.time}\n`;
      msg += `   Sections: ${c.sections.join(" & ")}\n\n`;
    });

    alert(msg);
  } catch (err) {
    alert("Error checking clashes");
  }
}

// ---------------------------------------------------------------
// Detailed Clash Analysis (back-to-back lecturer classes)
// ---------------------------------------------------------------
async function detailedClashAnalysis() {
  try {
    const r = await fetch(`${API_URL}/api/clash_analysis`);
    const json = await r.json();

    if (json.error) {
      alert("Error: " + json.error);
      return;
    }

    const violations = json.gap_violations || [];

    if (!violations.length) {
      alert("No continuous-class (back-to-back) problems found.");
      return;
    }

    let msg = "⚠ DETAILED CLASH ANALYSIS (GAP VIOLATIONS)\n\n";
    msg += `Total issues: ${violations.length}\n\n`;

    violations.forEach((v, idx) => {
      msg += `${idx + 1}) Lecturer ${v.lecturer_id}`;
      if (v.lecturer_name) msg += ` (${v.lecturer_name})`;
      msg += `\n   Day: ${v.day}\n`;
      msg += `   1st: ${v.first_time} in ${v.first_section}\n`;
      msg += `   2nd: ${v.second_time} in ${v.second_section}\n\n`;
    });

    alert(msg);
  } catch (err) {
    console.error(err);
    alert("Error running detailed clash analysis.");
  }
}

// ---------------------------------------------------------------
// PDF
// ---------------------------------------------------------------
function downloadPDF() {
  if (!currentSectionId) {
    alert("Select a section");
    return;
  }
  window.open(`${API_URL}/api/timetable/pdf/${currentSectionId}`, "_blank");
}

// ---------------------------------------------------------------
// Time Slot: Add / Edit / Delete
// ---------------------------------------------------------------
async function handleAddSlot(e) {
  e.preventDefault();

  let name = document.getElementById("slot-name").value;
  let start = document.getElementById("slot-start").value;
  let end = document.getElementById("slot-end").value;
  let is_break = document.getElementById("slot-is-break").checked;
  let editId = document.getElementById("slot-edit-id").value;

  try {
    if (editId) {
      // UPDATE existing slot
      const res = await fetch(`${API_URL}/api/timeslots/${editId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          start_time: start,
          end_time: end,
          is_break,
        }),
      });

      const json = await res.json();
      if (!res.ok || json.error) {
        alert(json.error || "Error updating time slot");
        return;
      }

      alert("Time Slot Updated");
    } else {
      // ADD new slot
      await postData(
        "/api/timeslots",
        {
          name,
          start_time: start,
          end_time: end,
          is_break,
        },
        "Slot Added"
      );
    }

    resetSlotForm();
    loadInitialData();
  } catch {}
}

function startEditTimeSlot(slot) {
  document.getElementById("slot-name").value = slot.name;
  document.getElementById("slot-start").value = slot.start;
  document.getElementById("slot-end").value = slot.end;
  document.getElementById("slot-is-break").checked = !!slot.is_break;

  document.getElementById("slot-edit-id").value = slot.id;

  const submitBtn = document.getElementById("slot-submit-btn");
  const cancelBtn = document.getElementById("slot-cancel-btn");
  if (submitBtn) submitBtn.textContent = "Update Time Slot";
  if (cancelBtn) cancelBtn.style.display = "inline-block";
}

function resetSlotForm() {
  document.getElementById("slot-name").value = "";
  document.getElementById("slot-start").value = "";
  document.getElementById("slot-end").value = "";
  document.getElementById("slot-is-break").checked = false;
  document.getElementById("slot-edit-id").value = "";

  const submitBtn = document.getElementById("slot-submit-btn");
  const cancelBtn = document.getElementById("slot-cancel-btn");
  if (submitBtn) submitBtn.textContent = "Add Time Slot";
  if (cancelBtn) cancelBtn.style.display = "none";
}

async function deleteTimeSlot(slotId) {
  if (!confirm("Delete this time slot?")) return;

  try {
    const res = await fetch(`${API_URL}/api/timeslots/${slotId}`, {
      method: "DELETE",
    });
    const json = await res.json();
    if (!res.ok || json.error) {
      alert(json.error || "Could not delete time slot");
      return;
    }
    resetSlotForm();
    await loadInitialData();
  } catch (e) {
    alert("Error deleting time slot");
  }
}

// ---------------------------------------------------------------
// Section: Add / Edit / Delete
// ---------------------------------------------------------------
async function handleAddSection(e) {
  e.preventDefault();

  try {
    let year = document.getElementById("section-year").value;
    let section = document.getElementById("section-name").value;
    let dept = document.getElementById("section-dept").value;
    let adviser = document.getElementById("section-adviser").value;

    if (editingSectionId) {
      // UPDATE section
      const res = await fetch(`${API_URL}/api/sections/${editingSectionId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          year,
          section_name: section,
          department: dept,
          class_adviser: adviser,
        }),
      });

      const json = await res.json();
      if (!res.ok || json.error) {
        alert(json.error || "Error updating section");
        return;
      }

      alert("Section Updated");
    } else {
      // ADD section
      await postData(
        "/api/sections",
        {
          year,
          section_name: section,
          department: dept,
          class_adviser: adviser,
        },
        "Section Added"
      );
    }

    resetSectionForm();
    loadInitialData();
  } catch {}
}

function startEditSection(sec) {
  editingSectionId = sec.id;

  document.getElementById("section-year").value = sec.year;
  document.getElementById("section-name").value = sec.section_name;
  document.getElementById("section-dept").value = sec.department;
  document.getElementById("section-adviser").value = sec.class_adviser || "";

  const btn = document.querySelector('#section-form button[type="submit"]');
  if (btn) btn.textContent = "Update Section";
}

function resetSectionForm() {
  editingSectionId = null;
  document.getElementById("section-year").value = "";
  document.getElementById("section-name").value = "";
  document.getElementById("section-dept").value = "CSE";
  document.getElementById("section-adviser").value = "";

  const btn = document.querySelector('#section-form button[type="submit"]');
  if (btn) btn.textContent = "Add Section";
}

async function deleteSection(id) {
  if (!confirm("Delete this section?")) return;

  try {
    const res = await fetch(`${API_URL}/api/sections/${id}`, {
      method: "DELETE",
    });
    const json = await res.json();

    if (!res.ok || json.error) {
      alert("Error deleting section");
      console.error(json.error || "Unknown error");
      return;
    }

    alert("Section deleted");
    loadInitialData(); // refresh lists & tabs
  } catch (e) {
    alert("Error deleting section");
    console.error(e);
  }
}

function startEditAssignment(a) {
  editingAssignmentId = a.id;

  // set dropdowns
  document.getElementById("assign-section").value = a.class_section_id;
  document.getElementById("assign-subject").value = a.subject_id;
  document.getElementById("assign-lecturer").value = a.lecturer_id;

  // set counts
  document.getElementById("assign-weekly-count").value = a.weekly_count;
  document.getElementById("assign-max-per-day").value = a.max_per_day;

  const btn = document.querySelector('#assignment-form button[type="submit"]');
  if (btn) btn.textContent = "Update Assignment";
}

function resetAssignmentForm() {
  editingAssignmentId = null;
  document.getElementById("assign-section").value = "";
  document.getElementById("assign-subject").value = "";
  document.getElementById("assign-lecturer").value = "";
  document.getElementById("assign-weekly-count").value = 3;
  document.getElementById("assign-max-per-day").value = 1;

  const btn = document.querySelector('#assignment-form button[type="submit"]');
  if (btn) btn.textContent = "Create Assignment";
}

async function deleteAssignment(id) {
  if (!confirm("Delete this assignment?")) return;

  try {
    const res = await fetch(`${API_URL}/api/assignments/${id}`, {
      method: "DELETE",
    });
    const json = await res.json();
    if (!res.ok || json.error) {
      alert(json.error || "Could not delete assignment");
      return;
    }

    if (editingAssignmentId === id) {
      resetAssignmentForm();
    }

    loadInitialData();
  } catch (err) {
    alert("Error deleting assignment");
  }
}

// ---------------------------------------------------------------
// Assignments
// ---------------------------------------------------------------
async function handleAddAssignment(e) {
  e.preventDefault();

  const sectionId = document.getElementById("assign-section").value;
  const subjectId = document.getElementById("assign-subject").value;
  const lecturerId = document.getElementById("assign-lecturer").value;
  const weeklyCount = document.getElementById("assign-weekly-count").value;
  const maxPerDay = document.getElementById("assign-max-per-day").value;

  if (!sectionId || !subjectId || !lecturerId) {
    alert("Please select section, subject and lecturer.");
    return;
  }

  const payload = {
    class_section_id: sectionId,
    subject_id: subjectId,
    lecturer_id: lecturerId,
    lectures_per_week: weeklyCount,
    max_per_day: maxPerDay,
  };

  try {
    if (editingAssignmentId) {
      // UPDATE existing assignment
      const res = await fetch(
        `${API_URL}/api/assignments/${editingAssignmentId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const json = await res.json();
      if (!res.ok || json.error) {
        alert(json.error || "Error updating assignment");
        return;
      }

      alert("Assignment Updated");
    } else {
      // CREATE new assignment
      await postData("/api/assignments", payload, "Assignment Created");
    }

    resetAssignmentForm();
    loadInitialData();
  } catch (err) {
    alert("Error saving assignment");
  }
}

// ---------------------------------------------------------------
// Clear all lecturers/subjects
// ---------------------------------------------------------------
async function clearAllData(type) {
  if (!confirm("Are you sure?")) return;

  await fetch(`${API_URL}/api/${type}/clear`, { method: "DELETE" });
  loadInitialData();
}

// ---------------------------------------------------------------
// Render list with edit/delete buttons
// ---------------------------------------------------------------
function renderList(id, items, type) {
  const list = document.getElementById(id);
  list.innerHTML = "";

  items.forEach((item) => {
    const li = document.createElement("li");

    const textSpan = document.createElement("span");
    textSpan.textContent = item.text;
    li.appendChild(textSpan);

    if (type === "timeslots") {
      const editBtn = document.createElement("button");
      editBtn.className = "edit-btn";
      editBtn.textContent = "✏";
      editBtn.title = "Edit slot";
      editBtn.addEventListener("click", () => {
        if (item.data) startEditTimeSlot(item.data);
      });

      const delBtn = document.createElement("button");
      delBtn.className = "delete-btn";
      delBtn.textContent = "✕";
      delBtn.title = "Delete slot";
      delBtn.addEventListener("click", () => {
        deleteTimeSlot(item.id);
      });

      li.appendChild(editBtn);
      li.appendChild(delBtn);
    } else if (type === "sections") {
      const editBtn = document.createElement("button");
      editBtn.className = "edit-btn";
      editBtn.textContent = "✏";
      editBtn.title = "Edit section";
      editBtn.addEventListener("click", () => {
        if (item.data) startEditSection(item.data);
      });

      const delBtn = document.createElement("button");
      delBtn.className = "delete-btn";
      delBtn.textContent = "✕";
      delBtn.title = "Delete section";
      delBtn.addEventListener("click", () => {
        deleteSection(item.id);
      });

      li.appendChild(editBtn);
      li.appendChild(delBtn);
    } else if (type === "assignments") {
      // NEW: edit/delete for assignments
      const editBtn = document.createElement("button");
      editBtn.className = "edit-btn";
      editBtn.textContent = "✏";
      editBtn.title = "Edit assignment";
      editBtn.addEventListener("click", () => {
        if (item.data) startEditAssignment(item.data);
      });

      const delBtn = document.createElement("button");
      delBtn.className = "delete-btn";
      delBtn.textContent = "✕";
      delBtn.title = "Delete assignment";
      delBtn.addEventListener("click", () => {
        deleteAssignment(item.id);
      });

      li.appendChild(editBtn);
      li.appendChild(delBtn);
    }

    list.appendChild(li);
  });
}

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------
function populateSelect(id, items, vKey, tKey, placeholder) {
  const el = document.getElementById(id);
  el.innerHTML = `<option value="">${placeholder}</option>`;

  items.forEach((i) => {
    el.innerHTML += `<option value="${i[vKey]}">${i[tKey]}</option>`;
  });
}

async function postData(url, data, successMsg) {
  const res = await fetch(API_URL + url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  const json = await res.json();
  if (!res.ok) throw new Error(json.error);

  if (successMsg) alert(successMsg);
  return json;
}
