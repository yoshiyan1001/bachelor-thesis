// Updates the visual text of a file upload button.
function bindCustomFilePicker(inputId) {
  const input = document.getElementById(inputId);
  const fileName = document.getElementById(`${inputId}Name`);

  if (!input || !fileName) return;
  input.addEventListener("change", () => {
    fileName.textContent = (input.files && input.files[0])
      ? input.files[0].name
      : "No file chosen";
  });
}

function setupAnnotation() {
  let annotateWavesurfer = null;
  const annotateAudioFile = document.getElementById("annotateAudioFile");
  const annotationControls = document.getElementById("annotationControls");
  const playPauseBtn = document.getElementById("playPauseBtn");
  const saveAnnotationBtn = document.getElementById("saveAnnotationBtn");

  if (!annotateAudioFile) return; // not rendered for non-admins

  annotateAudioFile.addEventListener("change", () => {
    const file = annotateAudioFile.files && annotateAudioFile.files[0];
    if (!file) {
      annotationControls.style.display = "none";
      if (annotateWavesurfer) {
        annotateWavesurfer.destroy();
        annotateWavesurfer = null;
      }
      return;
    }
    loadAnnotateWaveform(URL.createObjectURL(file));
  });

  function loadAnnotateWaveform(fileUrl) {
    if (annotateWavesurfer) annotateWavesurfer.destroy();
    annotateWavesurfer = WaveSurfer.create({
      container: "#waveform",
      waveColor: "#ddd",
      progressColor: "#4a90e2",
      height: 128,
    });
    annotateWavesurfer.load(fileUrl);
    annotateWavesurfer.on("ready", () => {
      annotationControls.style.display = "block";
      playPauseBtn.textContent = "Play";
    });
  }

  playPauseBtn.addEventListener("click", () => {
    if (!annotateWavesurfer) return;
    annotateWavesurfer.playPause();
    playPauseBtn.textContent = annotateWavesurfer.isPlaying() ? "Pause" : "Play";
  });

  saveAnnotationBtn.addEventListener("click", () => {
    const file = annotateAudioFile.files && annotateAudioFile.files[0];
    if (!file) { alert("Please choose a file first."); return; }

    const label = (document.getElementById("annotationLabel")?.value || "").trim();
    if (!label) { alert("Label is required."); return; }

    const description = (document.getElementById("annotationDescription")?.value || "").trim();
    const category = document.getElementById("categorySelect")?.value || "";

    submitAnnotation(file, label, description, category);
  });

  // Submits to /save_annotation. On 409 (duplicate label) shows an inline
  // confirmation banner offering to add the audio as a new variant instead.
  function submitAnnotation(file, label, description, category) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("label", label);
    formData.append("description", description);
    formData.append("category", category);

    fetch("/save_annotation", { method: "POST", body: formData })
      .then(async r => {
        const data = await r.json();

        if (r.status === 409) {
          // Label already exists — show inline confirmation instead of alert
          showVariantConfirmation(file, label);
          return;
        }

        if (data.status === "ok") {
          resetAnnotationForm();
          showAnnotationSuccess(data.message || "Annotation submitted!");
        } else {
          showAnnotationError(data.error || "Unknown error");
        }
      })
      .catch(err => {
        console.error("Annotation save failed:", err);
        showAnnotationError("Network error — please try again.");
      });
  }

  // Shows an inline banner asking whether to add the audio as a new variant.
  function showVariantConfirmation(file, label) {
    // Remove any existing banner first
    const existing = document.getElementById("variant-confirm-banner");
    if (existing) existing.remove();

    const banner = document.createElement("div");
    banner.id = "variant-confirm-banner";
    banner.style.cssText = [
      "margin-top:12px", "padding:14px 16px", "border-radius:6px",
      "background:#fff3cd", "border:1px solid #ffc107", "color:#856404",
      "font-size:14px", "line-height:1.5",
    ].join(";");

    banner.innerHTML = `
      <strong>"${label}"</strong> already exists in the database.<br>
      Will you add this audio as a <strong>new variant</strong> of "${label}"?
      <span style="font-size:12px; color:#6c757d; display:block; margin-top:4px;">
      </span>
      <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
        <button id="variant-confirm-yes"
          style="padding:6px 14px; background:#28a745; color:white; border:none; border-radius:4px; cursor:pointer; font-size:13px;">
          ✔ Yes, add as variant
        </button>
        <button id="variant-confirm-no"
          style="padding:6px 14px; background:#6c757d; color:white; border:none; border-radius:4px; cursor:pointer; font-size:13px;">
          ✗ Cancel
        </button>
      </div>
    `;

    // Insert after the annotation controls
    const controls = document.getElementById("annotationControls");
    controls.parentNode.insertBefore(banner, controls.nextSibling);

    document.getElementById("variant-confirm-yes").onclick = () => {
      banner.remove();
      addVariantToExisting(file, label);
    };
    document.getElementById("variant-confirm-no").onclick = () => {
      banner.remove();
    };
  }

  // Calls /add_variant_to_existing with the same file and label.
  function addVariantToExisting(file, label) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("label", label);

    fetch("/add_variant_to_existing", { method: "POST", body: formData })
      .then(r => r.json())
      .then(data => {
        if (data.status === "ok" || (data.error && data.error.toLowerCase().includes("already exists"))) {
          resetAnnotationForm();
          showAnnotationSuccess(data.status === "ok"
            ? (data.message || `Variant added to "${label}".`)
            : "Success!");
        } else {
          showAnnotationError(data.error || "Unknown error");
        }
      })
      .catch(err => {
        console.error("add_variant_to_existing failed:", err);
        showAnnotationError("Network error — please try again.");
      });
  }

  function showAnnotationSuccess(message) {
    showAnnotationBanner(message, "#d4edda", "#155724", "#c3e6cb");
  }

  function showAnnotationError(message) {
    showAnnotationBanner(message, "#f8d7da", "#721c24", "#f5c6cb");
  }

  function showAnnotationBanner(message, bg, color, border) {
    const existing = document.getElementById("annotation-status-banner");
    if (existing) existing.remove();
    const el = document.createElement("div");
    el.id = "annotation-status-banner";
    el.style.cssText = `margin-top:10px;padding:10px 14px;border-radius:5px;background:${bg};color:${color};border:1px solid ${border};font-size:13px;`;
    el.textContent = message;
    const controls = document.getElementById("annotationControls");
    controls.parentNode.insertBefore(el, controls.nextSibling);
    setTimeout(() => el.remove(), 6000);
  }

  function resetAnnotationForm() {
    const labelEl = document.getElementById("annotationLabel");
    const descEl  = document.getElementById("annotationDescription");
    const nameEl  = document.getElementById("annotateAudioFileName");
    if (labelEl) labelEl.value = "";
    if (descEl)  descEl.value  = "";
    if (nameEl)  nameEl.textContent = "No file chosen";
    annotateAudioFile.value = "";
    annotationControls.style.display = "none";
    if (annotateWavesurfer) { annotateWavesurfer.destroy(); annotateWavesurfer = null; }
    // Remove any leftover banners — but not the status banner, which is shown after reset
    ["variant-confirm-banner"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });
  }
}

function setupPrediction() {
  const predictForm = document.getElementById("predictForm");
  const predictionResult = document.getElementById("predictionResult");
  const playBtn = document.getElementById("playPredictedBtn");
  if (!predictForm) return;

  let predictWavesurfer = null;

  predictForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const file = document.getElementById("audioFile").files[0];
    if (!file) { alert("Please choose a file."); return; }

    predictionResult.textContent = "Predicting...";
    playBtn.style.display = "none";

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/predict", { method: "POST", body: formData });
      const result = await res.json();
      predictionResult.textContent = result.predicted_label
        ? "Predicted onomatopoeia: " + result.predicted_label
        : "Error: " + (result.error || "Unknown error");
    } catch (err) {
      console.error("Prediction failed:", err);
      predictionResult.textContent = "Prediction failed.";
    }

    // Draw waveform for the uploaded file
    if (predictWavesurfer) predictWavesurfer.destroy();
    predictWavesurfer = WaveSurfer.create({
      container: "#predictWaveform",
      waveColor: "#eee",
      progressColor: "#f76c6c",
      height: 128,
    });
    predictWavesurfer.load(URL.createObjectURL(file));
    playBtn.style.display = "inline-block";
    playBtn.onclick = () => predictWavesurfer.playPause();
  });
}

function setupPhoneticSearch() {
  const form = document.getElementById("phoneticSearchForm");
  const results = document.getElementById("phoneticSearchResults");
  if (!form) return;

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const file = document.getElementById("phoneticAudioFile").files[0];
    if (!file) { alert("Please choose a file."); return; }

    results.innerHTML = "Searching...";

    try {
      const formData = new FormData();
      formData.append("audio", file);
      const res = await fetch("/phonetic_search", { method: "POST", body: formData });
      if (!res.ok) throw new Error("Search request failed");

      const matches = await res.json();

      results.innerHTML = "";
      if (!matches.length) { results.innerHTML = "<p>No similar sounds found.</p>"; return; }

      matches.forEach(match => {
        const row = document.createElement("div");
        row.className = "phonetic-result";

        const label = document.createElement("span");
        label.className = "label";
        label.textContent = match;

        row.appendChild(label);
        results.appendChild(row);
      });
    } catch (err) {
      console.error("Phonetic search failed:", err);
      results.innerHTML = "Search failed. Please try again.";
    }
  });
}

// Category dropdown
async function setupCategoryDropdown() {
  const select = document.getElementById("categorySelect");
  if (!select) return;
  try {
    const res = await fetch("/api/onomatopoeia/filters");
    const data = await res.json();
    select.innerHTML = "";
    (data.categories || []).forEach(c => {
      const opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      select.appendChild(opt);
    });
  } catch {
    select.innerHTML = "<option disabled>Error loading categories</option>";
  }
}

// Model training
function setupTraining() {
  const btn = document.getElementById("trainButton");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const output = document.getElementById("trainOutput");
    output.textContent = "Training model...";
    try {
      const res = await fetch("/train_model", { method: "POST" });
      const result = await res.json();
      output.textContent = result.status === "ok"
        ? result.output
        : "Error: " + (result.error || "Unknown error");
    } catch (err) {
      console.error("Training failed:", err);
      output.textContent = "Training failed.";
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindCustomFilePicker("annotateAudioFile");
  bindCustomFilePicker("audioFile");
  bindCustomFilePicker("phoneticAudioFile");

  setupAnnotation();
  setupPrediction();
  setupPhoneticSearch();
  setupCategoryDropdown();
  setupTraining();
});
