(function () {
  let currentPage = 1;
  const pageSize = 12;

  const body = document.body;
  const adminControls = body.dataset.isAdmin === "true";

  // It reaches out to the server to get a list of available categories and labels.
  async function loadFilters() {
    const response = await fetch("/api/onomatopoeia/filters");
    const data = await response.json();
    if (data.error) {
      alert(data.error);
      return;
    }

    const labelSelect = document.getElementById("labelFilter");
    const categorySelect = document.getElementById("categoryFilter");

    const addOpts = (select, values) => {
      select.innerHTML = '<option value="">(any)</option>';
      values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
    };

    addOpts(labelSelect, data.labels || []);
    addOpts(categorySelect, data.categories || []);
  }

  // This is the main data-fetching engine. It reads what the user typed in the search bar (#q) and what they selected in the filter drop-downs.
  async function loadPage(page = 1) {
    currentPage = page;
    const query = document.getElementById("q").value.trim();
    const label = document.getElementById("labelFilter").value;
    const category = document.getElementById("categoryFilter").value;

    const params = new URLSearchParams({ page: String(currentPage), page_size: String(pageSize) });
    if (query) params.set("q", query);
    if (label) params.set("label", label);
    if (category) params.set("category", category);

    const response = await fetch("/api/onomatopoeia?" + params.toString());
    const data = await response.json();
    if (data.error) {
      alert(data.error);
      return;
    }

    renderGrid(data.items || []);
    renderPagination(data.page, data.page_size, data.total);
  }

  // Tracks the currently playing Audio instance so only one plays at a time.
  let currentAudio = null;
  let currentPlayBtn = null;

  function stopCurrent() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    if (currentPlayBtn) {
      currentPlayBtn.textContent = "▶";
      currentPlayBtn = null;
    }
  }

  // It takes the array of sound items returned by the server and builds a visual grid of cards.
  function renderGrid(items) {
    const grid = document.getElementById("grid");
    grid.innerHTML = "";
    if (!items.length) {
      grid.textContent = "No results";
      return;
    }

    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "card";
      const category = item.category
        ? `<div class="tags"><span class="tag">${item.category}</span></div>`
        : "";

      // If adminControls is true, it appends a "Delete" button to the card.
      card.innerHTML = `
        <h4>${item.label || "(untitled)"}</h4>
        <div>${item.description || ""}</div>
        ${item.sound_url ? `
          <div class="audio-controls">
            <button class="play-btn" data-src="${item.sound_url}" title="Play">▶</button>
          </div>` : ""}
        ${category}
        ${adminControls ? `<button class="delete-btn" data-id="${item.id}">Delete</button>` : ""}
      `;

      // Wire up play/stop buttons
      if (item.sound_url) {
        const playBtn = card.querySelector(".play-btn");
        const stopBtn = card.querySelector(".stop-btn");

        playBtn.addEventListener("click", () => {
          // If this card is already playing, stop it
          if (currentAudio && currentPlayBtn === playBtn) {
            stopCurrent();
            return;
          }
          // Stop whatever was playing before
          stopCurrent();
          const audio = new Audio(item.sound_url);
          currentAudio = audio;
          currentPlayBtn = playBtn;
          playBtn.textContent = "⏸";
          audio.play();
          audio.addEventListener("ended", () => {
            playBtn.textContent = "▶";
            currentAudio = null;
            currentPlayBtn = null;
          });
        });
      }

      grid.appendChild(card);
    });

    if (adminControls) { // If user is admin...
      grid.querySelectorAll(".delete-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-id");
          if (!id || !confirm("Delete this item?")) return;
          const response = await fetch(`/api/items/${id}`, { method: "DELETE" });
          const data = await response.json();
          if (data.status === "ok") {
            loadPage(currentPage);
          } else {
            alert(data.error || "Delete failed");
          }
        });
      });
    }
  }

  // It calculates how many pages exist based on the total number of items and the page size.
  function renderPagination(page, currentPageSize, total) {
    const cont = document.getElementById("pagination");
    cont.innerHTML = "";
    const totalPages = Math.max(1, Math.ceil(total / currentPageSize));

    const prev = document.createElement("button");
    prev.textContent = "Prev";
    prev.disabled = page <= 1;
    prev.onclick = () => loadPage(page - 1);

    const next = document.createElement("button");
    next.textContent = "Next";
    next.disabled = page >= totalPages;
    next.onclick = () => loadPage(page + 1);

    const info = document.createElement("span");
    info.textContent = ` Page ${page} / ${totalPages} — ${total} items `;

    cont.append(prev, info, next);
  }

  function applyFilters() {
    loadPage(1);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    await loadFilters();
    await loadPage(1);
    document.getElementById("applyBtn").addEventListener("click", applyFilters);
    document.getElementById("q").addEventListener("keydown", (e) => {
      if (e.key === "Enter") applyFilters();
    });
  });
})();
