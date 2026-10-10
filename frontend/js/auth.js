(() => {
  const form = document.getElementById("authForm");
  const errorBox = document.getElementById("formError");
  const button = form.querySelector("button[type=submit]");
  const mode = form.dataset.mode;

  const showError = (message) => {
    errorBox.textContent = message;
    errorBox.hidden = !message;
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    const data = Object.fromEntries(new FormData(form));

    if (mode === "register") {
      if (data.password.length < 6) return showError("Password must be at least 6 characters.");
      if (data.password !== data.confirm) return showError("Passwords do not match.");
    }
    if (!data.email || !data.password) return showError("Enter your email and password.");

    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Please wait...";

    try {
      const res = await fetch("/api/" + mode, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || "Something went wrong. Try again.");
      window.location.href = "/";
    } catch (err) {
      showError(err instanceof TypeError ? "Can't reach the server. Is app.py running?" : err.message);
      button.disabled = false;
      button.textContent = label;
    }
  });
})();
