// Shoir-IE Excel add-in task pane.
// This bridge intentionally uses a configurable API host. It does not claim
// a backend endpoint is available until the Shoir-IE deployment exposes one.

Office.onReady(() => {
  const save = document.getElementById("saveHost");
  const send = document.getElementById("sendSelection");
  const copy = document.getElementById("copySelection");
  const status = document.getElementById("status");
  const hostInput = document.getElementById("host");

  hostInput.value = localStorage.getItem("shoirIeHost") || "";
  save.onclick = () => {
    localStorage.setItem("shoirIeHost", hostInput.value.trim().replace(/\/$/, ""));
    status.textContent = "Shoir-IE host saved for this Excel profile.";
  };

  async function selectedRangePayload() {
    return await Excel.run(async context => {
      const range = context.workbook.getSelectedRange();
      range.load(["address", "values", "rowCount", "columnCount"]);
      await context.sync();
      return {
        address: range.address,
        values: range.values,
        rows: range.rowCount,
        columns: range.columnCount
      };
    });
  }

  send.onclick = async () => {
    try {
      const host = hostInput.value.trim().replace(/\/$/, "");
      if (!host) throw new Error("Enter the URL of a deployed Shoir-IE API gateway first.");
      const payload = await selectedRangePayload();
      const response = await fetch(host + "/api/workbook/import", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error("Shoir-IE API returned HTTP " + response.status);
      status.textContent = "Selected Excel range sent to Shoir-IE.";
    } catch (error) {
      status.textContent = "Bridge not connected: " + error.message;
    }
  };

  copy.onclick = async () => {
    try {
      const payload = await selectedRangePayload();
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      status.textContent = "Selected range copied as Shoir-IE JSON.";
    } catch (error) {
      status.textContent = "Could not read the selected range: " + error.message;
    }
  };
});
