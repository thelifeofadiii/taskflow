(() => {
  const $ = (id) => document.getElementById(id);
  let tasks = [];
  let filter = "all";

  async function api(path, options = {}) {
    const res = await fetch("/api" + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("Please log in.");
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || "Request failed.");
    return body;
  }

  let toastTimer;
  function toast(message) {
    const el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.hidden = true), 3500);
  }

  const todayStr = () =>
    new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

  const formatDate = (d) =>
    new Date(d + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });

  function visibleTasks() {
    const term = $("searchInput").value.trim().toLowerCase();
    return tasks
      .filter((t) => t.name.toLowerCase().includes(term))
      .filter((t) => filter === "all" || (filter === "done" ? t.completed : !t.completed))
      .sort((a, b) => {
        if (a.completed !== b.completed) return a.completed ? 1 : -1;
        if (a.deadline !== b.deadline) {
          if (!a.deadline) return 1;
          if (!b.deadline) return -1;
          return a.deadline < b.deadline ? -1 : 1;
        }
        return b.id - a.id;
      });
  }

  function updateStats() {
    const done = tasks.filter((t) => t.completed).length;
    const left = tasks.length - done;
    const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
    $("totalTasks").textContent = tasks.length;
    $("completedTasks").textContent = done;
    $("pendingTasks").textContent = left;
    $("barFill").style.width = pct + "%";
    $("bar").setAttribute("aria-valuenow", pct);
    $("summary").textContent = !tasks.length
      ? "Add your first task to get started."
      : left === 0
      ? "Everything is done. Nice work."
      : left + (left === 1 ? " task left" : " tasks left") + " (" + pct + "% done).";
  }

  function render() {
    const list = $("taskList");
    list.replaceChildren();
    const items = visibleTasks();
    const empty = $("emptyMessage");
    empty.hidden = items.length > 0;
    if (!items.length) {
      empty.textContent = tasks.length
        ? "No tasks match this view."
        : "No tasks yet. Type one above and press Add task.";
    }

    const today = todayStr();
    items.forEach((task) => {
      const li = document.createElement("li");
      li.className = "task-item" + (task.completed ? " completed" : "");

      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = task.completed;
      check.setAttribute("aria-label", "Mark " + task.name + " as done");
      check.addEventListener("change", async () => {
        try {
          const updated = await api("/tasks/" + task.id, {
            method: "PATCH",
            body: JSON.stringify({ completed: check.checked }),
          });
          Object.assign(task, updated);
        } catch (e) {
          toast(e.message);
        }
        render();
      });

      const body = document.createElement("div");
      body.className = "task-body";
      const name = document.createElement("div");
      name.className = "task-name";
      name.textContent = task.name;

      const meta = document.createElement("div");
      meta.className = "task-meta";
      const chip = document.createElement("span");
      chip.className = "chip p-" + task.priority.toLowerCase();
      chip.textContent = task.priority;
      meta.append(chip);
      if (task.deadline) {
        const due = document.createElement("span");
        const overdue = !task.completed && task.deadline < today;
        due.className = overdue ? "due overdue" : "due";
        due.textContent = (overdue ? "Overdue: " : "Due ") + formatDate(task.deadline);
        meta.append(due);
      }
      body.append(name, meta);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn danger";
      del.textContent = "Delete";
      del.addEventListener("click", async () => {
        try {
          await api("/tasks/" + task.id, { method: "DELETE" });
          tasks = tasks.filter((t) => t.id !== task.id);
          render();
        } catch (e) {
          toast(e.message);
        }
      });

      li.append(check, body, del);
      list.append(li);
    });
    updateStats();
  }

  $("taskForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("taskInput").value.trim();
    if (!name) return;
    try {
      const created = await api("/tasks", {
        method: "POST",
        body: JSON.stringify({
          name,
          priority: $("priority").value,
          deadline: $("deadline").value,
        }),
      });
      tasks.unshift(created);
      $("taskForm").reset();
      $("priority").value = "Medium";
      $("taskInput").focus();
      render();
    } catch (e) {
      toast(e.message);
    }
  });

  $("tabs").addEventListener("click", (event) => {
    const tab = event.target.closest(".tab");
    if (!tab) return;
    filter = tab.dataset.filter;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    render();
  });

  $("searchInput").addEventListener("input", render);

  $("logoutBtn").addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });

  (async function init() {
    try {
      const me = await api("/me");
      $("userName").textContent = me.name;
      const h = new Date().getHours();
      const part = h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
      $("greeting").textContent = "Good " + part + ", " + me.name.split(" ")[0];
      tasks = await api("/tasks");
      render();
    } catch (e) {
      if (e.message !== "Please log in.") toast(e.message);
    }
  })();
})();
