(function () {

  // It takes the list of matches returned by the server and builds the results list on the screen.
  function showMatches(matches) {
    const resultsDiv = document.getElementById("results");
    resultsDiv.innerHTML = "";

    const ul = document.createElement("ul");
    matches.forEach((match) => {
      const li = document.createElement("li");
      li.textContent = match;
      ul.appendChild(li);
    });
    resultsDiv.appendChild(ul);
  }

  // This function wires up the primary "Search" button.
  function bindSearch() {
    document.getElementById("searchBtn").addEventListener("click", () => {
      // It checks if the user has actually uploaded an audio file to the audioFile input.
      const fileInput = document.getElementById("audioFile");
      if (fileInput.files.length === 0) {
        alert("Please upload an audio file.");
        return;
      }

      const formData = new FormData();
      formData.append("audio", fileInput.files[0]);

      fetch("/phonetic_search", { method: "POST", body: formData }) // formData contains the audio file the user just uploaded.
        .then((response) => response.json()) // translate it into a readable JSON object.
        .then((matches) => { // it contains an array of strings, specifically labels.
          showMatches(matches);
        })
        .catch((err) => {
          console.error(err);
          alert("Search failed.");
        });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindSearch();
  });
})();
