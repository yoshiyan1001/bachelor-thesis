(function () {
  // It displays a loading/progress indicato
  function showProgress() {
    document.getElementById("progress").style.display = "block";
    document.getElementById("augmentBtn").disabled = true;
  }

  function updateSelectedFileName() {
    const input = document.getElementById("audioFile");
    const name = document.getElementById("audioFileName");
    if (!input || !name) return;
    name.textContent = input.files && input.files[0] ? input.files[0].name : "No file chosen";
  }
  // It hides the progress indicator and re-enables the augment button once processing is finished or fails.
  function hideProgress() {
    document.getElementById("progress").style.display = "none";
    document.getElementById("augmentBtn").disabled = false;
  }

  function showError(message) {
    const errorDiv = document.getElementById("error");
    errorDiv.textContent = message;
    errorDiv.style.display = "block";
  }
  // It hides the error message div, usually right before a new attempt is made so old errors don't linger on screen.
  function hideError() {
    document.getElementById("error").style.display = "none";
  }
  // It hides the entire results section to clear the screen before a new audio processing request begins.
  function hideResults() {
    document.getElementById("results").style.display = "none";
  }
  // It takes the successful JSON response (result) from the server and dynamically builds HTML to display the audio files.
  function showResults(result) {
    const resultsDiv = document.getElementById("results");
    const originalDiv = document.getElementById("originalFile");
    const augmentedDiv = document.getElementById("augmentedFiles");

    // It injects an HTML block containing the name, an <audio> player, and a download link for the original uploaded file.
    originalDiv.innerHTML = `
      <div class="audio-item">
        <div class="audio-info">
          <strong>Original File:</strong> ${result.original_file}
        </div>
        <div class="audio-controls">
          <audio controls src="${result.original_download_url}"></audio>
          <a href="${result.original_download_url}" download="${result.original_file}" class="btn" style="text-decoration: none; padding: 8px 16px; font-size: 14px;">💾 Download</a>
        </div>
      </div>
    `;

    // It loops through the augmented_files array provided by the server. For every augmented version, it creates a new HTML div with a description, filename, an <audio> player, and a download link, appending each one to the screen.
    augmentedDiv.innerHTML = "";
    result.augmented_files.forEach(({ filename, description, download_url }) => {
      const audioItem = document.createElement("div");
      audioItem.className = "audio-item";
      audioItem.innerHTML = `
        <div class="audio-info">
          <strong>${description}</strong><br>
          <small>${filename}</small>
        </div>
        <div class="audio-controls">
          <audio controls src="${download_url}"></audio>
          <a href="${download_url}" download="${filename}" class="btn" style="text-decoration: none; padding: 8px 16px; font-size: 14px;">💾 Download</a>
        </div>
      `;
      augmentedDiv.appendChild(audioItem);
    });

    resultsDiv.style.display = "block";
  }

  // This is the main engine of the script, triggered when the user clicks the "Augment" button.
  async function handleAugment() {
    const fileInput = document.getElementById("audioFile");
    const file = fileInput.files[0];

    // It first checks if a file is uploaded.
    if (!file) {
      showError("Please select an audio file first.");
      return;
    }

    const checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');
    const augmentations = Array.from(checkboxes).map((cb) => cb.value);
    if (augmentations.length === 0) {
      showError("Please select at least one augmentation type.");
      return;
    }

    showProgress();
    hideError();
    hideResults();

    const formData = new FormData();
    formData.append("file", file);
    augmentations.forEach((aug) => formData.append("augmentations", aug));

    // It uses the fetch API to send a POST request to /augment_audio on our server.
    try {
      const response = await fetch("/augment_audio", { method: "POST", body: formData });
      const result = await response.json();
      if (result.status === "success") {
        showResults(result);
      } else {
        showError(result.error || "Augmentation failed");
      }
    } catch (error) {
      showError("Network error: " + error.message);
    } finally {
      hideProgress();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("audioFile");
    if (input) input.addEventListener("change", updateSelectedFileName);
    document.getElementById("augmentBtn").addEventListener("click", handleAugment);
  });
})();
