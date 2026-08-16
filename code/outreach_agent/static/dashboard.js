(() => {
  const toast = document.getElementById("toast");
  const notify = (message) => {
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2600);
  };

  const runDemo = async (button) => {
    button.disabled = true;
    button.textContent = "Building workflow…";
    try {
      const response = await fetch("/api/v1/demo", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Demo failed");
      window.location.href = `/?conversation=${data.conversation_id}`;
    } catch (error) {
      notify(error.message);
      button.disabled = false;
      button.textContent = "Run zero-token example";
    }
  };

  ["demo-button", "demo-button-secondary", "welcome-demo-button"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.addEventListener("click", () => runDemo(button));
  });

  const actionGroup = document.querySelector(".approval-actions");
  if (!actionGroup) return;
  actionGroup.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const draftId = actionGroup.dataset.draftId;
    const action = button.dataset.action;
    let path = `/api/v1/approvals/${draftId}/${action}`;
    let body;
    if (action === "approve") {
      body = { edited_body: document.getElementById("draft-body").value, reviewer_note: "Approved in workflow dashboard" };
    } else if (action === "reject") {
      const reason = window.prompt("Why should this draft be rejected?");
      if (!reason) return;
      body = { reason };
    } else {
      body = {};
    }
    button.disabled = true;
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `${action} failed`);
      notify(`${action} completed`);
      window.setTimeout(() => window.location.reload(), 500);
    } catch (error) {
      notify(error.message);
      button.disabled = false;
    }
  });
})();

