
let levelChart;
let timelineChart;
let currentFileId = null;

async function uploadFile() {
  const input = document.getElementById("fileInput");
  const status = document.getElementById("uploadStatus");
  const file = input.files[0];

  if (!file) {
    alert("Selecione um arquivo .log ou .txt.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  status.textContent = "Analisando arquivo...";

  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Não foi possível analisar o arquivo.");
    }

    currentFileId = data.file_id;

    status.textContent =
      `${data.filename} — ${data.total_events} eventos encontrados.`;

    renderTopGroups(data.top_groups || []);
    await refreshAll();
  } catch (error) {
    status.textContent = `Falha na análise: ${error.message}`;
  }
}

async function refreshAll() {
  await Promise.all([
    loadStats(),
    loadFiles(),
    loadEvents()
  ]);
}

async function loadStats() {
  const url = currentFileId
    ? `/api/stats?file_id=${currentFileId}`
    : "/api/stats";

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error("Não foi possível carregar as estatísticas.");
  }

  const data = await response.json();

  const levels = {
    CRITICAL: 0,
    ERROR: 0,
    WARNING: 0,
    INFO: 0
  };

  data.by_level.forEach(event => {
    levels[event.level] = event.count;
  });

  document.getElementById("kpiCritical").textContent = levels.CRITICAL;
  document.getElementById("kpiError").textContent = levels.ERROR;
  document.getElementById("kpiWarning").textContent = levels.WARNING;
  document.getElementById("kpiInfo").textContent = data.total_events;

  if (levelChart) levelChart.destroy();

  levelChart = new Chart(document.getElementById("levelChart"), {
    type: "doughnut",
    data: {
      labels: ["Críticos", "Erros", "Avisos", "Informações"],
      datasets: [{
        data: [
          levels.CRITICAL,
          levels.ERROR,
          levels.WARNING,
          levels.INFO
        ],
        backgroundColor: [
          "#f85149",
          "#ff7b72",
          "#d29922",
          "#58a6ff"
        ],
        borderColor: "#141920",
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: "#c9d1d9",
            padding: 16
          }
        }
      }
    }
  });

  if (timelineChart) timelineChart.destroy();

  timelineChart = new Chart(document.getElementById("timelineChart"), {
    type: "line",
    data: {
      labels: data.timeline.map(event => event.hour),
      datasets: [{
        label: "Eventos por hora",
        data: data.timeline.map(event => event.count),
        borderColor: "#58a6ff",
        backgroundColor: "rgba(88, 166, 255, 0.08)",
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.2,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: "#c9d1d9"
          }
        }
      },
      scales: {
        x: {
          ticks: { color: "#8b949e" },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: { color: "#8b949e", precision: 0 },
          grid: { color: "#2a3038" }
        }
      }
    }
  });
}

async function loadFiles() {
  const response = await fetch("/api/files");

  if (!response.ok) {
    throw new Error("Não foi possível carregar os arquivos.");
  }

  const files = await response.json();
  const tbody = document.querySelector("#filesTable tbody");

  tbody.replaceChildren();

  for (const file of files) {
    const row = document.createElement("tr");

    const values = [
      file.id,
      file.filename,
      new Date(file.uploaded_at).toLocaleString("pt-BR"),
      file.error_count,
      file.warning_count,
      file.critical_count
    ];

    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value ?? "";
      row.appendChild(cell);
    }

    const actionCell = document.createElement("td");
    const button = document.createElement("button");

    button.type = "button";
    button.textContent = "Excluir";
    button.className = "secondary-button";
    button.addEventListener("click", () => deleteFile(file.id));

    actionCell.appendChild(button);
    row.appendChild(actionCell);
    tbody.appendChild(row);
  }
}

async function deleteFile(id) {
  if (!confirm("Deseja excluir este arquivo e seus eventos?")) {
    return;
  }

  try {
    const response = await fetch(`/api/files/${id}`, {
      method: "DELETE"
    });

    if (!response.ok) {
      throw new Error("Não foi possível excluir o arquivo.");
    }

    if (currentFileId === id) {
      currentFileId = null;
      document.getElementById("topGroups").replaceChildren();
      document.getElementById("uploadStatus").textContent = "";
    }

    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

function renderTopGroups(groups) {
  const container = document.getElementById("topGroups");
  container.replaceChildren();

  if (!groups.length) {
    const message = document.createElement("p");
    message.className = "section-description";
    message.textContent = "Nenhum evento recorrente encontrado.";
    container.appendChild(message);
    return;
  }

  for (const group of groups) {
    const item = document.createElement("div");
    item.className = `group-item ${group.level}`;

    const count = document.createElement("span");
    count.className = "count";
    count.textContent = `${group.count} ocorrências`;

    const message = document.createElement("span");
    message.className = "msg";
    message.textContent = group.sample_message;

    const level = document.createElement("span");
    level.className = `lvl ${group.level}`;
    level.textContent = group.level;

    item.append(count, message, level);
    container.appendChild(item);
  }
}

async function loadEvents() {
  const level = document.getElementById("filterLevel").value;
  const search = document.getElementById("filterSearch").value;

  const params = new URLSearchParams({ level, search });

  if (currentFileId !== null) {
    params.set("file_id", currentFileId);
  }

  const response = await fetch(`/api/events?${params}`);

  if (!response.ok) {
    throw new Error("Não foi possível carregar os eventos.");
  }

  const events = await response.json();
  const tbody = document.querySelector("#eventsTable tbody");

  tbody.replaceChildren();

  if (!events.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");

    cell.colSpan = 3;
    cell.textContent = "Nenhum evento encontrado.";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  for (const event of events) {
    const row = document.createElement("tr");

    const timestamp = document.createElement("td");
    timestamp.textContent = (event.timestamp || "")
      .replace("T", " ")
      .slice(0, 19);

    const levelCell = document.createElement("td");
    levelCell.className = `lvl ${event.level}`;
    levelCell.textContent = event.level;

    const message = document.createElement("td");
    message.textContent = (event.message || "").slice(0, 180);

    row.append(timestamp, levelCell, message);
    tbody.appendChild(row);
  }
}

function exportCSV() {
  const level = document.getElementById("filterLevel").value;
  const search = document.getElementById("filterSearch").value;
  const params = new URLSearchParams({ level, search });

  if (currentFileId !== null) {
    params.set("file_id", currentFileId);
  }

  window.location.href = `/api/export?${params}`;
}

refreshAll().catch(error => {
  console.error("Falha ao carregar o painel:", error);
});
