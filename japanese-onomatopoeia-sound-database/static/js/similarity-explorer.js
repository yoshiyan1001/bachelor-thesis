(function () {
  "use strict"; // Strict Mode to catch an error easily

  const currentRole = document.body.dataset.currentRole || "basic";
  const isAdmin = currentRole === "admin";

  let rawGraph = null;
  let currentVersion = null;
  let labelToFile = {};

  // Three.js — initialised once, never torn down
  let renderer = null;
  let scene = null;
  let camera = null;
  let controls = null;
  let threeReady = false;

  // Per-graph scene objects
  // nodeState: Map<string id, { x,y,z, mesh, labelDiv, label }>
  let nodeState = new Map();
  let edgeObjects = [];   // [{ line, sourceId, targetId, similarity }]

  const CANVAS_H = 700; // canvas height

  const searchBox = document.getElementById("graph-search-box");
  const saveGraphBtn = document.getElementById("save-graph-btn");
  const displayToggleBtn = document.getElementById("display-toggle-btn");

  function int(value) { return parseInt(value, 10); }

  function setStatus(message, kind) {
    const element = document.getElementById("update-status");
    element.className = kind || "info";
    element.textContent = message;
    element.style.display = "block"; // element visible on the screen
  }

  // Version / history helpers 
  function syncDisplayBtn() {
    if (!displayToggleBtn || !currentVersion) return;
    const isDisplayed = !!currentVersion.displayed;
    const isApproved = currentVersion.status === "approved";
    displayToggleBtn.textContent = isDisplayed ? " Undisplay" : " Display";
    displayToggleBtn.disabled    = !isApproved;
    displayToggleBtn.title = isApproved
      ? (isDisplayed ? "Hide from researchers" : "Show to researchers")
      : "Only approved graphs can be displayed";
  }
  // approve button feature
  function syncApproveBtn() {
    const approveBtn = document.getElementById("approve-graph-btn");
    if (!approveBtn || !currentVersion) return;
    const isSaved = currentVersion.status === "saved";
    approveBtn.disabled = !isSaved;
    approveBtn.title = isSaved
      ? "Approve this saved graph"
      : "Save the graph first before approving";
  }

    // make the table for the versions
  function renderVersionTable(versions) {
    const tableBody = document.querySelector("#version-table tbody");
    if (!tableBody) return;
    tableBody.innerHTML = "";
    versions.forEach(value => {
      const isActive = currentVersion && int(value.id) === int(currentVersion.id);
      const isDisplayed = !!value.displayed;
      const tr = document.createElement("tr");
      if (isActive) tr.classList.add("active-row");
      tr.innerHTML = `
        <td>${value.id}</td>
        <td>${value.name}</td>
        <td><span class="badge badge-${value.status}">${value.status}</span></td>
        <td>${isDisplayed
          ? '<span class="badge badge-displayed">● displayed</span>'
          : '<span style="color:#aaa;">—</span>'}</td>
        <td style="font-size:12px;color:#666;">${value.created_at || ""}</td>`;
      tr.addEventListener("click", async () => {
        const select = document.getElementById("history-select");
        if (select) select.value = value.id;
        await loadGraph(value.id);
      });
      tableBody.appendChild(tr);
    });
  }

  function syncHistoryDropdown(versions) {
    const select = document.getElementById("history-select");
    if (!select) return;
    select.innerHTML = "";
    versions.forEach(value => {
      const option = document.createElement("option");
      option.value = value.id;
      option.textContent = `#${value.id} ${value.name} [${value.status}]`;
      if (currentVersion && int(value.id) === int(currentVersion.id)) option.selected = true;
      select.appendChild(option);
    });
    select.onchange = () => loadGraph(select.value);
  }

  async function loadHistory() {
    if (!isAdmin) return;
    const response  = await fetch("/api/graph/versions");
    const data = await response.json();
    renderVersionTable(data.versions || []);
    syncHistoryDropdown(data.versions || []);
  }

  // Graph loading
  async function loadGraph(versionId = null) {
    let url = "/api/graph/current";
    if (versionId && isAdmin) url = `/api/graph/version/${versionId}`;

    const [graphRes, pcaRes] = await Promise.all([
      fetch(url),
      fetch("/api/graph/pca_positions"),
    ]);
    const graphData = await graphRes.json();
    const pcaData = await pcaRes.json();

    if (graphData.status === "empty") {
      setStatus("No graph available. Build a draft first.", "error");
      return;
    }

    rawGraph = graphData.graph   || {};
    currentVersion = graphData.version || {};

    // Attach PCA data so renderGraph3D can use it
    rawGraph._pcaPositions = (pcaData.status === "ok") ? pcaData.positions : {};
    rawGraph._pcaAxes = (pcaData.status === "ok") ? pcaData.axes : [];

    const editOverlay = document.getElementById("edit-overlay");
    if (editOverlay) editOverlay.style.display = isAdmin ? "block" : "none";

    renderGraph3D();
    renderAxisLegend(rawGraph._pcaAxes);
    syncDisplayBtn();
    syncApproveBtn();

    if (isAdmin) {
      const response2 = await fetch("/api/graph/versions");
      const data2 = await response2.json();
      renderVersionTable(data2.versions || []);
      syncHistoryDropdown(data2.versions || []);
    }
  }

  // Three.js — init ONCE 
  function initThreeOnce() {
    if (threeReady) return;

    const wrap = document.getElementById("graph-wrap");
    const Width = wrap.clientWidth || wrap.offsetWidth || window.innerWidth || 1200;
    const Height = CANVAS_H;

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(Width, Height);
    renderer.domElement.style.display = "block";

    const labelContainer = document.getElementById("label-container");
    wrap.insertBefore(renderer.domElement, labelContainer);

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f7fa);

    camera = new THREE.PerspectiveCamera(60, Width / Height, 0.1, 5000);
    camera.position.set(0, 0, 350);

    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const dir = new THREE.DirectionalLight(0xffffff, 0.6);
    dir.position.set(200, 300, 400);
    scene.add(dir);

    // Draw the 3 principal-component axes so the space is legible
    _drawAxes(200);

    const OrbitControls = THREE.OrbitControls;
    if (!OrbitControls) { console.error("OrbitControls not found on THREE namespace"); return; }
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.minDistance = 30;
    controls.maxDistance = 3000;

    window.addEventListener("resize", () => {
      const newWidth = wrap.clientWidth || wrap.offsetWidth || window.innerWidth;
      renderer.setSize(newWidth, Height);
      camera.aspect = newWidth / Height;
      camera.updateProjectionMatrix();
    });

    setupInteraction();

    // Single persistent render loop
    (function loop() {
      requestAnimationFrame(loop);
      updateLabelPositions();
      controls.update();
      renderer.render(scene, camera);
    })();

    threeReady = true;
  }

  // Draw PC1/PC2/PC3 axes with colour-coded labels
  function _drawAxes(len) {
    const axes = [
      { dir: [1,0,0], color: 0xe74c3c, name: "PC1" },
      { dir: [0,1,0], color: 0x2ecc71, name: "PC2" },
      { dir: [0,0,1], color: 0x3498db, name: "PC3" },
    ];
    const labelContainer = document.getElementById("label-container");
    axes.forEach(axis => {
      const material = new THREE.LineBasicMaterial({ color: axis.color, opacity: 0.4, transparent: true });
      const points = [new THREE.Vector3(0,0,0), new THREE.Vector3(...axis.dir).multiplyScalar(len)];
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      scene.add(new THREE.Line(geometry, material));

      // Axis label
      if (labelContainer) {
        const div = document.createElement("div");
        div.textContent   = axis.name;
        div.dataset.axisX = axis.dir[0] * len;
        div.dataset.axisY = axis.dir[1] * len;
        div.dataset.axisZ = axis.dir[2] * len;
        div.style.cssText = `position:absolute;pointer-events:none;font-size:11px;`
                          + `font-weight:700;color:#${axis.color.toString(16).padStart(6,"0")};`
                          + `opacity:0.7;white-space:nowrap;`;
        div.classList.add("axis-label");
        labelContainer.appendChild(div);
      }
    });
  }

  // Clear old per-graph scene objects
  function clearSceneObjects() {
    edgeObjects.forEach(object => scene.remove(object.line));
    nodeState.forEach(state => {
      if (state.mesh)     scene.remove(state.mesh);
      if (state.labelDiv) state.labelDiv.remove();
    });
    edgeObjects = [];
    nodeState   = new Map();
    // Remove old node labels but keep axis labels
    const labelContainer = document.getElementById("label-container");
    if (labelContainer) {
      Array.from(labelContainer.querySelectorAll(".node-label")).forEach(el => el.remove());
    }
  }

  // Build scene objects from PCA positions
  function buildSceneObjects(nodes, edges) {
    const labelContainer = document.getElementById("label-container");
    const geometry = new THREE.SphereGeometry(6, 20, 14);

    nodes.forEach(node => {
      const state = nodeState.get(node.id);
      if (!state) return;
      const material  = new THREE.MeshPhongMaterial({ color: 0xff8c00 });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(state.x, state.y, state.z);
      mesh.userData = { id: node.id, label: node.label };
      scene.add(mesh);
      state.mesh = mesh;

      const div = document.createElement("div");
      div.className = "node-label";
      div.textContent = node.label;
      div.style.cssText = "position:absolute;pointer-events:none;font-size:13px;"
                        + "font-weight:600;color:#222;"
                        + "text-shadow:0 0 4px #fff,0 0 4px #fff;white-space:nowrap;";
      if (labelContainer) labelContainer.appendChild(div);
      state.labelDiv = div;
    });

    edges.forEach(edge => {
      const sourceNode = nodeState.get(edge.sourceId);
      const targetNode = nodeState.get(edge.targetId);
      const p0 = (sourceNode && isFinite(sourceNode.x)) ? new THREE.Vector3(sourceNode.x, sourceNode.y, sourceNode.z) : new THREE.Vector3();
      const p1 = (targetNode && isFinite(targetNode.x)) ? new THREE.Vector3(targetNode.x, targetNode.y, targetNode.z) : new THREE.Vector3();

      // Colour by PCA distance — same metric as the visual edge length.
      // normDist 0 (shortest = most similar) -> orange
      // normDist 1 (longest  = most dissimilar) -> blue
      // This guarantees colour and length always agree.
      const transition = edge.normDist ?? 0;
      const color = new THREE.Color().setHSL(0.6 - (1 - transition) * 0.6, 0.8, 0.5); // orange→blue
      const material = new THREE.LineBasicMaterial({ color: color, transparent: true, opacity: 0.55 });
      const geom = new THREE.BufferGeometry().setFromPoints([p0, p1]);
      const line = new THREE.Line(geom, material);
      scene.add(line);
      edgeObjects.push({ line, sourceId: edge.sourceId, targetId: edge.targetId,
                         similarity: edge.similarity, normSim: edge.normSim,
                         pcaDist: edge.pcaDist, normDist: edge.normDist });
    });
  }

  // Per-frame: project node + axis labels to screen 
  function updateLabelPositions() {
    if (!renderer || !camera || !nodeState.size) return;
    const Width = renderer.domElement.width  / renderer.getPixelRatio();
    const Height = renderer.domElement.height / renderer.getPixelRatio();

    nodeState.forEach(state => {
      if (!state.labelDiv) return;
      const pos = new THREE.Vector3(state.x, state.y, state.z).project(camera);
      // Place the label exactly at the projected node center, then use
      // transform to nudge it just above — stays tight at any zoom level.
      state.labelDiv.style.left = ((pos.x *  0.5 + 0.5) * Width) + "px";
      state.labelDiv.style.top  = ((pos.y * -0.5 + 0.5) * Height) + "px";
      state.labelDiv.style.transform = "translate(-50%, -220%)";
      state.labelDiv.style.display = pos.z < 1 ? "block" : "none";
    });

    // Axis labels
    const lc = document.getElementById("label-container"); // label container
    if (lc) {
      lc.querySelectorAll(".axis-label").forEach(div => {
        const pos = new THREE.Vector3(
          parseFloat(div.dataset.axisX),
          parseFloat(div.dataset.axisY),
          parseFloat(div.dataset.axisZ),
        ).project(camera);
        div.style.left    = ((pos.x *  0.5 + 0.5) * Width + 4) + "px";
        div.style.top     = ((pos.y * -0.5 + 0.5) * Height - 4) + "px";
        div.style.display = pos.z < 1 ? "block" : "none";
      });
    }
  }

  // Highlight helpers
  function highlightNode(targetId) {
    const neighbors = new Set();
    edgeObjects.forEach(edge => {
      if (edge.sourceId === targetId) neighbors.add(edge.targetId);
      if (edge.targetId === targetId) neighbors.add(edge.sourceId);
    });
    nodeState.forEach((state, id) => {
      if (!state.mesh) return;
      const hit = id === targetId, nbr = neighbors.has(id);
      state.mesh.material.color.set(hit || nbr ? 0xff8c00 : 0xcccccc);
      state.mesh.material.emissive.set(hit ? 0xff4400 : 0x000000);
      if (state.labelDiv) state.labelDiv.style.opacity = (hit || nbr) ? "1" : "0.3"; 
    });
    edgeObjects.forEach(edge => {
      const active = edge.sourceId === targetId || edge.targetId === targetId;
      edge.line.material.opacity = active ? 0.95 : 0.1;
    });
  }

  function resetHighlight() {
    nodeState.forEach(state => {
      if (!state.mesh) return;

      state.mesh.material.color.set(0xff8c00);
      state.mesh.material.emissive.set(0x000000);

      if (state.labelDiv) state.labelDiv.style.opacity = "1";
    });
    edgeObjects.forEach(edge => { edge.line.material.opacity = 0.5; });
  }

  // Raycasting attached once to the persistent canvas
  function setupInteraction() {
    const canvas = renderer.domElement;
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let hoverId = null;

    function getMeshes() {
      const out = [];
      nodeState.forEach(state => { if (state.mesh) out.push(state.mesh); });
      return out;
    }

    canvas.addEventListener("mousemove", event => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width)  * 2 - 1;
      mouse.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(getMeshes());
      const newId = hits.length ? hits[0].object.userData.id : null;
      if (newId !== hoverId) {
        hoverId = newId;
        if (hoverId) highlightNode(hoverId);
        else resetHighlight();
      }
    });

    canvas.addEventListener("click", event => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width)  * 2 - 1;
      mouse.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(getMeshes());
      if (!hits.length) return;
      const { label } = hits[0].object.userData;
      const filename = labelToFile[label] || `${label}.mp3`;
      new Audio(`/sounds/${filename}`).play().catch(() => {});
    });
  }

  // Main graph renderer
  function renderGraph3D() {
    if (!rawGraph) return;
    initThreeOnce();

    const pcaPos = rawGraph._pcaPositions || {};  // { "1": {x,y,z,label}, ... }

    const nodes = (rawGraph.nodes || []).map(node => ({
      id: String(node.item_id),
      label: node.label,
    }));

    // Normalise similarities for edge tooltip only (not for colour)
    const rawEdges = rawGraph.edges || [];
    const simValues = rawEdges.map(e => e.similarity ?? 0);
    const simMin = simValues.length ? Math.min(...simValues) : 0;
    const simMax = simValues.length ? Math.max(...simValues) : 1;
    const simRange = simMax - simMin || 1;

    const edges = rawEdges.map(edge => ({
      sourceId: String(edge.source_item_id),
      targetId: String(edge.target_item_id),
      similarity: edge.similarity ?? 0,
      normSim: ((edge.similarity ?? 0) - simMin) / simRange,
    }));

    // Build nodeState from PCA positions
    clearSceneObjects();

    nodes.forEach(node => {
      const pca = pcaPos[node.id] || pcaPos[int(node.id)];
      if (pca && isFinite(pca.x) && isFinite(pca.y) && isFinite(pca.z)) {
        nodeState.set(node.id, { id: node.id, label: node.label,
                               x: pca.x, y: pca.y, z: pca.z,
                               mesh: null, labelDiv: null });
      } else {
        const hash = node.id.split("").reduce((a, c) => a + c.charCodeAt(0), 0); // fallback coordinate
        nodeState.set(node.id, { id: node.id, label: node.label,
                               x: Math.cos(hash) * 20, y: Math.sin(hash) * 20, z: 0,
                               mesh: null, labelDiv: null });
      }
    });

    // Compute PCA distances and normalise for consistent colour+length
    // Colour is derived from PCA distance (same metric as visual length) so
    // orange always means short/similar and blue always means long/dissimilar.
    // Cosine similarity is kept separately for tooltips only.
    edges.forEach(edge => {
      const source = nodeState.get(edge.sourceId);
      const target = nodeState.get(edge.targetId);
      if (source && target) {
        const dx = target.x - source.x, dy = target.y - source.y, dz = target.z - source.z;
        edge.pcaDist = Math.sqrt(dx*dx + dy*dy + dz*dz);
      } else {
        edge.pcaDist = 0;
      }
    });
    const distValues = edges.map(edge => edge.pcaDist);
    const distMin = distValues.length ? Math.min(...distValues) : 0;
    const distMax = distValues.length ? Math.max(...distValues) : 1;
    const distRange = distMax - distMin || 1;
    // normDist: 0 = shortest (most similar) -> 1 = longest (most dissimilar)
    edges.forEach(edge => {
      edge.normDist = (edge.pcaDist - distMin) / distRange;
    });

    buildSceneObjects(nodes, edges);

    // Reset camera
    camera.position.set(0, 0, 350);
    controls.target.set(0, 0, 0);
    controls.update();

    // Search
    if (searchBox) {
      searchBox.onkeydown = event => {
        if (event.key !== "Enter") return;
        const term = searchBox.value.trim().toLowerCase();
        if (!term) return;
        let found = null;
        nodeState.forEach((s, id) => {
          if (!found && s.label.toLowerCase().includes(term)) found = id;
        });
        if (found) {
          highlightNode(found);
          const state = nodeState.get(found);
          controls.target.set(state.x, state.y, state.z);
          camera.position.set(state.x, state.y, state.z + 150);
          setTimeout(resetHighlight, 2000);
        }
      };
    }
  }

  // Axis legend
  const AXIS_COLORS = { PC1: "#e74c3c", PC2: "#2ecc71", PC3: "#3498db" };
  const AXIS_EXPLANATIONS = {
    PC1: "The axis that separates sounds the most — nodes far apart here are the least alike.",
    PC2: "The second most important axis — captures variation not explained by PC1.",
    PC3: "The third axis — adds depth to the space and reveals subtler groupings.",
  };

  function renderAxisLegend(axes) {
    const container = document.getElementById("axis-legend-rows");
    if (!container) return;
    if (!axes || !axes.length) {
      container.innerHTML = "<em style='color:#aaa;'>No axis data available. We may need to feed more data.</em>";
      return;
    }
    container.innerHTML = axes.map(a => `
      <div class="axis-row">
        <div class="axis-row-header">
          <span class="axis-tag" style="color:${AXIS_COLORS[a.name] || '#666'}">${a.name}</span>
          <span class="axis-var">(${a.variance_ratio}% variance)</span>
          <span class="axis-desc">${a.description}</span>
        </div>
        <span class="axis-explain">${AXIS_EXPLANATIONS[a.name] || ""}</span>
      </div>`).join("");
  }

  // Save positions
  async function saveCurrentPositions() {
    if (!nodeState.size || !currentVersion) return false;
    const positions = {};
    nodeState.forEach((s, id) => {
      positions[id] = { x: Math.round(s.x), y: Math.round(s.y) };
    });
    const response  = await fetch("/api/graph/save_positions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_id: currentVersion.id, positions }),
    });
    const data = await response.json();
    return data.status === "ok";
  }

  async function saveGraph() {
    if (!currentVersion) { setStatus("No graph is loaded to save.", "error"); return; }
    setStatus("Saving…", "info");
    const ok = await saveCurrentPositions();
    if (!ok) { setStatus("Save failed. Please try again.", "error"); return; }
    // Update local state so approve button enables immediately
    currentVersion.status = "saved";
    setStatus("Graph saved. You can now approve it.", "success");
    syncApproveBtn();
    await loadHistory();
  }

  // Admin actions
  async function buildDraft() {
    const name = (document.getElementById("graph-name").value || "draft").trim();
    setStatus("Building draft…", "info");
    const res  = await fetch("/api/graph/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });

    const data = await res.json();
    if (data.status !== "ok") { setStatus(`Build failed: ${data.message}`, "error"); return; }
    setStatus(`Draft built — ${data.nodes_count} nodes, ${data.edges_count} edges.`, "success");
    await loadGraph(data.version_id);
  }

  async function approveDraft() {
    if (!currentVersion) return;
    const response = await fetch("/api/graph/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_id: currentVersion.id }),
    });
    const data = await response.json();
    if (data.status !== "ok") { setStatus(`Approve failed: ${data.message}`, "error"); return; }
    currentVersion.status = "approved";
    setStatus("Graph approved. You can now display it.", "success");
    syncApproveBtn();
    syncDisplayBtn();
    await loadHistory();
  }

  async function toggleDisplay() {
    if (!currentVersion) return;
    const nowDisplayed = !!currentVersion.displayed;
    const response = await fetch("/api/graph/display", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_id: currentVersion.id, displayed: !nowDisplayed }),
    });
    const data = await response.json();
    if (data.status !== "ok") { setStatus(`Display toggle failed: ${data.message}`, "error"); return; }

    currentVersion.displayed = data.displayed ? 1 : 0;
    setStatus(data.displayed ? "Graph is now displayed to researchers." : "Graph is now hidden.", "success");
    syncDisplayBtn();

    await loadHistory();
  }

  async function deleteVersion() {
    if (!currentVersion || !confirm("Delete this graph version?")) return;

    const response = await fetch("/api/graph/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_id: currentVersion.id }),
    });

    const data = await response.json();
    if (data.status !== "ok") { setStatus(`Delete failed: ${data.message}`, "error"); return; }

    setStatus("Version deleted.", "success");
    currentVersion = null; rawGraph = null; nodeState = new Map();

    await loadGraph();
  }

  function loadLabelMap() {
    fetch("/api/label_to_file")
      .then( response => response.json())
      .then(data => { if (!data.error) labelToFile = data; });
  }

  // Boot 
  document.addEventListener("DOMContentLoaded", async () => {
    loadLabelMap();
    await loadGraph();

    if (isAdmin) {
      await loadHistory();
      document.getElementById("build-graph-btn").onclick = buildDraft;
      saveGraphBtn.onclick = saveGraph;
      document.getElementById("approve-graph-btn").onclick = approveDraft;
      displayToggleBtn.onclick = toggleDisplay;
      document.getElementById("delete-graph-btn").onclick = deleteVersion;
    }
  });
})();
