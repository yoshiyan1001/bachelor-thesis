(function () {
  const uploadedFiles = { file1: null, file2: null }; // We compare two audio files.

  // It updfates the interface when a user selects an audio file.
  function updateFileInfo(fileId, file) {
    const infoDiv = document.getElementById(fileId + "Info");
    const nameSpan = document.getElementById(fileId + "Name");
    if (nameSpan) {
      nameSpan.textContent = file ? file.name : "No file chosen";
    }
    if (file) {
      infoDiv.innerHTML = `
        <div style="background: #d4edda; color: #155724; padding: 10px; border-radius: 4px; margin-top: 10px;">
          ✅ ${file.name} (${(file.size / 1024).toFixed(1)} KB)
        </div>
      `;
    } else {
      infoDiv.innerHTML = "";
    }
  }

  // It displays a loading indicator while the server is working. 
  // It also disables the "Compare" and "Extract" buttons so the user cannot spam the server with multiple clicks.
  function showProgress() {
    document.getElementById("progress").style.display = "block";
    document.getElementById("compareBtn").disabled = true;
    document.getElementById("extractBtn").disabled = true;
  }

  // It hides the loading indicator and re-enables the action buttons once the server request finishes or fails.
  function hideProgress() {
    document.getElementById("progress").style.display = "none";
    document.getElementById("compareBtn").disabled = false;
    document.getElementById("extractBtn").disabled = false;
  }

  function showError(message) {
    const errorDiv = document.getElementById("error");
    errorDiv.textContent = message;
    errorDiv.style.display = "block";
  }

  function hideError() {
    document.getElementById("error").style.display = "none";
  }

  function hideResults() {
    document.getElementById("results").style.display = "none";
  }

  // It creates a visual "card" used when comparing two files.
  function createFeatureCard(feature) {
    const card = document.createElement("div");
    card.className = "feature-card";

    const similarityPercent = (feature.similarity * 100).toFixed(1);
    const barWidth = feature.similarity * 100;
    const contributionPercent = feature.contribution ? (feature.contribution * 100).toFixed(1) : "N/A";
    const weightPercent = feature.weight ? (feature.weight * 100).toFixed(1) : "N/A";

    let content = `
      <div class="feature-name">${feature.name.replace(/_/g, " ").toUpperCase()}</div>
      <div class="similarity-score">Similarity: ${similarityPercent}%</div>
      <div class="similarity-bar">
        <div class="similarity-fill" style="width: ${barWidth}%"></div>
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; font-size: 12px;">
        <div style="background: #e8f5e8; padding: 5px; border-radius: 4px; text-align: center;">
          <strong>Contribution:</strong><br>${contributionPercent}%
        </div>
        <div style="background: #e3f2fd; padding: 5px; border-radius: 4px; text-align: center;">
          <strong>Weight:</strong><br>${weightPercent}%
        </div>
      </div>
    `;

    if (feature.type === "scalar") {
      content += `
        <div class="feature-values">
          <div class="value-item">File 1: ${feature.value1.toFixed(4)}</div>
          <div class="value-item">File 2: ${feature.value2.toFixed(4)}</div>
        </div>
      `;
    } else {
      content += `<div style="color: #6c757d; font-size: 14px;">Array size: ${feature.size}</div>`;
    }

    card.innerHTML = content;
    return card;
  }

  // It creates a simpler card used when extracting data from a single file.
  function createSingleFeatureCard(feature) {
    const card = document.createElement("div");
    card.className = "feature-card";

    if (feature.type === "scalar") {
      card.innerHTML = `
        <div class="feature-name">${feature.name.replace(/_/g, " ").toUpperCase()}</div>
        <div style="font-size: 18px; color: #495057;">${feature.value.toFixed(4)}</div>
      `;
    } else {
      const previewValues = feature.values.join(", ");
      card.innerHTML = `
        <div class="feature-name">${feature.name.replace(/_/g, " ").toUpperCase()}</div>
        <div style="color: #6c757d; font-size: 14px;">Array size: ${feature.size}</div>
        <div style="color: #6c757d; font-size: 12px; margin-top: 5px;">Preview: [${previewValues}...]</div>
      `;
    }

    return card;
  }

  // It handles the layout for a two-file comparison.
  function showComparisonResults(result) {
    const resultsDiv = document.getElementById("results");
    const overallScoreDiv = document.getElementById("overallScore");
    const scalarFeaturesDiv = document.getElementById("scalarFeatures");
    const arrayFeaturesDiv = document.getElementById("arrayFeatures");

    const overall = result.comparison.overall;
    overallScoreDiv.innerHTML = `
      <h3>🎯 Overall Similarity Score</h3>
      <div class="score-display">${(overall.similarity * 100).toFixed(1)}%</div>
      <p>Based on ${overall.feature_count} audio features</p>
    `;

    if (result.comparison.feature_ranking) {
      const importanceDiv = document.createElement("div");
      importanceDiv.className = "feature-importance";
      importanceDiv.innerHTML = `
        <h4>🔍 Feature Importance Analysis</h4>
        <p><strong>What makes these sounds similar:</strong></p>
        <div id="importanceChart"></div>
      `;
      overallScoreDiv.appendChild(importanceDiv);

      if (overall.top_features) {
        const topFeaturesDiv = document.createElement("div");
        topFeaturesDiv.className = "top-features";
        topFeaturesDiv.innerHTML = `
          <h4>🏆 Top Contributing Features</h4>
          <p>These features contribute most to the similarity:</p>
          <div>
            ${overall.top_features.map((f) => `<span class="feature-tag">${f.replace(/_/g, " ").toUpperCase()}</span>`).join("")}
          </div>
        `;
        overallScoreDiv.appendChild(topFeaturesDiv);
      }

      const importanceChart = document.getElementById("importanceChart");
      // Before drawing anything, it looks through the entire list of features and finds the single highest contribution value.
      const maxContribution = Math.max(...result.comparison.feature_ranking.map((f) => f.contribution));
      // It takes the list of ranked features from the server and loops through them one by one to build a row for each.
      result.comparison.feature_ranking.forEach((feature) => {
        const contributionPercent = (feature.contribution * 100).toFixed(1);
        // It divides the current feature's score by the maximum score to find its relative width. The #1 feature will always result in 100 here, filling the bar completely.
        const barWidth = (feature.contribution / maxContribution) * 100;

        const chartItem = document.createElement("div");
        chartItem.className = "importance-chart";
        chartItem.innerHTML = `
          <div style="min-width: 120px; font-size: 14px;">${feature.name.replace(/_/g, " ").toUpperCase()}</div>
          <div class="importance-bar">
            <div class="importance-fill" style="width: ${barWidth}%"></div>
          </div>
          <div style="min-width: 80px; text-align: right; font-size: 14px; color: #495057;">
            ${contributionPercent}%
          </div>
        `;
        importanceChart.appendChild(chartItem);
      });
    }

    const scalarFeatures = [];
    const arrayFeatures = [];
    for (const [featureName, featureData] of Object.entries(result.comparison)) { // Ita takes a dictionary and converts it into a list of pairs so you can loop through it.
      // The server also sent back the "overall" score and the "feature_ranking" list. 
      // Because this loop is only meant to sort the actual audio features, the continue command tells the loop to immediately skip these two items and move on to the next one.
      if (featureName === "overall" || featureName === "feature_ranking") continue;

      if (featureData.type === "scalar") {
        scalarFeatures.push({ name: featureName, ...featureData }); // it tosses it into the scalarFeatures bucket.
      } else {
        arrayFeatures.push({ name: featureName, ...featureData }); // it tosses it into the arrayFeatures bucket.
      }
    }

    // It loops through those sorted lists, generates cards using createFeatureCard, and appends them to the screen.
    scalarFeaturesDiv.innerHTML = "<h3>📊 Scalar Features (Brightness, Frequency, etc.)</h3>";
    scalarFeatures.forEach((feature) => scalarFeaturesDiv.appendChild(createFeatureCard(feature)));

    arrayFeaturesDiv.innerHTML = "<h3>🎵 Array Features (MFCC, Chroma, etc.)</h3>";
    arrayFeatures.forEach((feature) => arrayFeaturesDiv.appendChild(createFeatureCard(feature)));

    resultsDiv.style.display = "block";
  }

  // It handles the layout for a single-file extraction.
  function showSingleFileFeatures(result) {
    const resultsDiv = document.getElementById("results");
    const overallScoreDiv = document.getElementById("overallScore");
    const scalarFeaturesDiv = document.getElementById("scalarFeatures");
    const arrayFeaturesDiv = document.getElementById("arrayFeatures");

    overallScoreDiv.innerHTML = `
      <h3>📊 Single File Feature Analysis</h3>
      <div style="font-size: 24px; color: #155724;">${result.filename}</div>
      <p>Extracted ${Object.keys(result.features).length} audio features</p>
    `;

    const scalarFeatures = [];
    const arrayFeatures = [];
    for (const [featureName, featureValue] of Object.entries(result.features)) {
      // It checks this is a list of items.
      if (Array.isArray(featureValue)) {
        arrayFeatures.push({ // it creates a new object and tosses it into the arrayFeatures bucket.
          name: featureName,
          type: "array",
          size: featureValue.length,
          values: featureValue.slice(0, 10), // Audio features like MFCCs can contain thousands of numbers. It simply cuts out the first 10 numbers
        });
      } else {
        scalarFeatures.push({ name: featureName, type: "scalar", value: featureValue });
      }
    }

    scalarFeaturesDiv.innerHTML = "<h3>📊 Scalar Features</h3>";
    scalarFeatures.forEach((feature) => scalarFeaturesDiv.appendChild(createSingleFeatureCard(feature)));

    arrayFeaturesDiv.innerHTML = "<h3>🎵 Array Features</h3>";
    arrayFeatures.forEach((feature) => arrayFeaturesDiv.appendChild(createSingleFeatureCard(feature)));

    resultsDiv.style.display = "block";
  }

  // It handles the comparison feature.
  async function handleCompare() {
    if (!uploadedFiles.file1 || !uploadedFiles.file2) {
      showError("Please upload both audio files first.");
      return;
    }

    showProgress();
    hideError();
    hideResults();

    const formData = new FormData();
    formData.append("file1", uploadedFiles.file1);
    formData.append("file2", uploadedFiles.file2);

    try {
      // It sends the packaged FormData to your server's "/compare_audio" URL using a POST request. 
      // The await keyword tells JavaScript to pause and wait for the server to reply.
      const response = await fetch("/compare_audio", { method: "POST", body: formData });
      const result = await response.json();
      if (result.status === "success") {
        showComparisonResults(result);
      } else {
        showError(result.error || "Comparison failed");
      }
    } catch (error) {
      showError("Network error: " + error.message);
    } finally {
      hideProgress();
    }
  }

  // This is a case when single file is uploaded.
  async function handleExtract() {
    const file = uploadedFiles.file1 || uploadedFiles.file2;
    if (!file) {
      showError("Please upload an audio file first.");
      return;
    }

    showProgress();
    hideError();
    hideResults();

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("/extract_features_single", { method: "POST", body: formData });
      const result = await response.json();
      if (result.status === "success") {
        showSingleFileFeatures(result);
      } else {
        showError(result.error || "Feature extraction failed");
      }
    } catch (error) {
      showError("Network error: " + error.message);
    } finally {
      hideProgress();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("file1").addEventListener("change", (e) => {
      uploadedFiles.file1 = e.target.files[0];
      updateFileInfo("file1", e.target.files[0]);
    });

    document.getElementById("file2").addEventListener("change", (e) => {
      uploadedFiles.file2 = e.target.files[0];
      updateFileInfo("file2", e.target.files[0]);
    });

    document.getElementById("compareBtn").addEventListener("click", handleCompare);
    document.getElementById("extractBtn").addEventListener("click", handleExtract);
  });
})();
