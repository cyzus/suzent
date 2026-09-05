for (const id of ["connect", "disconnect", "help"])
  document.getElementById(id).textContent = chrome.i18n.getMessage(id);
function update(result) {
  document.getElementById("status").textContent = chrome.i18n.getMessage(
    result?.connected ? "connected" : "disconnected",
  );
}
chrome.runtime.sendMessage({ type: "status" }, update);
for (const id of ["connect", "disconnect"]) {
  document.getElementById(id).onclick = () =>
    chrome.runtime.sendMessage({ type: id }, update);
}
