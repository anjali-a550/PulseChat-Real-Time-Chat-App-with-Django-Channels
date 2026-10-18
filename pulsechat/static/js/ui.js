/* Small UI helpers shared by every page: avatars and the mobile sidebar. */
(function () {
  "use strict";

  function hue(name) {
    let h = 0;
    for (const ch of name) h = (h * 31 + ch.codePointAt(0)) % 360;
    return h;
  }

  function paintAvatar(el) {
    const name = el.dataset.name || "?";
    el.textContent = name.slice(0, 1).toUpperCase();
    el.style.setProperty("--avatar-hue", hue(name));
  }

  window.PulseUI = { paintAvatar };
  document.querySelectorAll(".avatar[data-name]").forEach(paintAvatar);

  const sidebar = document.getElementById("sidebar");
  const openBtn = document.getElementById("open-sidebar");
  const closeBtn = document.getElementById("close-sidebar");
  if (sidebar && openBtn) openBtn.addEventListener("click", () => sidebar.classList.add("open"));
  if (sidebar && closeBtn) closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));
})();
