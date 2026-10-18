/*
 * PulseChat client: one WebSocket per open room.
 * Handles: live messages, typing indicator, presence, history paging,
 * and automatic reconnect with exponential backoff.
 */
(function () {
  "use strict";

  const slug = JSON.parse(document.getElementById("room-slug").textContent);
  const me = JSON.parse(document.getElementById("me").textContent);
  const history = JSON.parse(document.getElementById("history-data").textContent);

  const list = document.getElementById("message-list");
  const scroller = document.getElementById("messages");
  const emptyState = document.getElementById("empty-state");
  const input = document.getElementById("input");
  const form = document.getElementById("composer");
  const typingEl = document.getElementById("typing");
  const statusEl = document.getElementById("conn-status");
  const onlineEl = document.getElementById("online-count");
  const loadMoreBtn = document.getElementById("load-more");

  let socket = null;
  let retry = 0;
  let oldestId = history.length ? history[0].id : null;
  const typers = new Map(); // username -> timeout id
  const seen = new Set();   // message ids already rendered

  // ---------- rendering ----------
  const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
  const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" });

  function buildMessage(msg, prev) {
    const when = new Date(msg.created_at);
    const grouped = prev && prev.author === msg.author && when - new Date(prev.created_at) < 5 * 60 * 1000;
    const row = document.createElement("article");
    row.className = "msg" + (msg.author === me ? " mine" : "") + (grouped ? " grouped" : "");
    row.dataset.id = msg.id;
    row.dataset.author = msg.author;
    row.dataset.created = msg.created_at;

    if (!grouped) {
      const avatar = document.createElement("span");
      avatar.className = "avatar";
      avatar.dataset.name = msg.author;
      window.PulseUI.paintAvatar(avatar);
      row.appendChild(avatar);
    }
    const body = document.createElement("div");
    body.className = "msg-body";
    if (!grouped) {
      const head = document.createElement("div");
      head.className = "msg-head";
      const name = document.createElement("strong");
      name.textContent = msg.author;
      const time = document.createElement("time");
      time.dateTime = msg.created_at;
      const today = new Date().toDateString() === when.toDateString();
      time.textContent = (today ? "" : dayFmt.format(when) + " · ") + timeFmt.format(when);
      head.append(name, time);
      body.appendChild(head);
    }
    const text = document.createElement("p");
    text.textContent = msg.content; // textContent = no HTML injection
    body.appendChild(text);
    if (msg.flagged) {
      const flag = document.createElement("span");
      flag.className = "flag";
      flag.textContent = "Moderated";
      flag.title = "Some words were masked by the moderation filter";
      body.appendChild(flag);
    }
    row.appendChild(body);
    return row;
  }

  function lastMessageData() {
    const el = list.lastElementChild;
    return el ? { author: el.dataset.author, created_at: el.dataset.created } : null;
  }

  function appendMessage(msg) {
    if (seen.has(msg.id)) return;
    seen.add(msg.id);
    const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
    list.appendChild(buildMessage(msg, lastMessageData()));
    emptyState.hidden = true;
    if (nearBottom || msg.author === me) scrollToBottom();
  }

  function prependMessages(msgs) {
    const before = scroller.scrollHeight;
    const frag = document.createDocumentFragment();
    let prev = null;
    msgs.forEach((m) => {
      if (seen.has(m.id)) return;
      seen.add(m.id);
      frag.appendChild(buildMessage(m, prev));
      prev = m;
    });
    // the first old message may now group with what was at the top
    const firstNew = list.firstElementChild;
    list.prepend(frag);
    if (firstNew && prev && firstNew.dataset.author === prev.author) {
      const rebuilt = buildMessage(
        { id: +firstNew.dataset.id, author: firstNew.dataset.author, created_at: firstNew.dataset.created,
          content: firstNew.querySelector("p").textContent, flagged: !!firstNew.querySelector(".flag") },
        prev
      );
      firstNew.replaceWith(rebuilt);
    }
    scroller.scrollTop = scroller.scrollHeight - before;
  }

  function scrollToBottom() {
    scroller.scrollTop = scroller.scrollHeight;
  }

  function renderTyping() {
    const names = [...typers.keys()];
    if (!names.length) typingEl.textContent = "";
    else if (names.length === 1) typingEl.textContent = `${names[0]} is typing…`;
    else if (names.length === 2) typingEl.textContent = `${names[0]} and ${names[1]} are typing…`;
    else typingEl.textContent = "Several people are typing…";
  }

  function renderPresence(online) {
    const others = online.filter((u) => u !== me).length;
    onlineEl.textContent = others === 0 ? "Only you here right now" : `${online.length} online`;
    document.querySelectorAll(".people a[data-user]").forEach((a) => {
      a.classList.toggle("online", online.includes(a.dataset.user));
    });
  }

  function setStatus(state, label) {
    statusEl.dataset.state = state;
    statusEl.textContent = label;
    input.disabled = state !== "open";
  }

  function toast(text) {
    const el = document.createElement("div");
    el.className = "alert floating";
    el.textContent = text;
    document.querySelector(".chat").appendChild(el);
    setTimeout(() => el.remove(), 3500);
  }

  // ---------- socket ----------
  function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${location.host}/ws/chat/${slug}/`);
    setStatus("connecting", retry ? "Reconnecting" : "Connecting");

    socket.addEventListener("open", () => {
      retry = 0;
      setStatus("open", "Live");
      socket.send(JSON.stringify({ type: "read" }));
    });

    socket.addEventListener("message", (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "message":
          appendMessage(data);
          if (typers.has(data.author)) { clearTimeout(typers.get(data.author)); typers.delete(data.author); renderTyping(); }
          if (document.visibilityState === "visible") send({ type: "read" });
          break;
        case "typing":
          if (typers.has(data.user)) clearTimeout(typers.get(data.user));
          if (data.is_typing) typers.set(data.user, setTimeout(() => { typers.delete(data.user); renderTyping(); }, 4000));
          else typers.delete(data.user);
          renderTyping();
          break;
        case "presence":
          renderPresence(data.online);
          break;
        case "error":
          toast(data.message);
          break;
      }
    });

    socket.addEventListener("close", (event) => {
      if ([4401, 4403, 4404].includes(event.code)) {
        setStatus("closed", "No access");
        return;
      }
      const delay = Math.min(1000 * 2 ** retry, 15000);
      retry += 1;
      setStatus("closed", "Offline");
      setTimeout(connect, delay);
    });
  }

  function send(obj) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(obj));
      return true;
    }
    return false;
  }

  // ---------- composer ----------
  let typingSent = false;
  let typingTimer = null;

  function stopTyping() {
    if (typingSent) send({ type: "typing", is_typing: false });
    typingSent = false;
    clearTimeout(typingTimer);
  }

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
    if (!input.value.trim()) return stopTyping();
    if (!typingSent) { send({ type: "typing", is_typing: true }); typingSent = true; }
    clearTimeout(typingTimer);
    typingTimer = setTimeout(stopTyping, 2500);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const content = input.value.trim();
    if (!content) return;
    if (send({ type: "message", content })) {
      input.value = "";
      input.style.height = "auto";
      stopTyping();
    } else {
      toast("You're offline. The message wasn't sent.");
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") send({ type: "read" });
  });

  // ---------- history paging ----------
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener("click", async () => {
      loadMoreBtn.disabled = true;
      try {
        const res = await fetch(`/api/rooms/${slug}/messages/?before=${oldestId}`, { credentials: "same-origin" });
        const data = await res.json();
        if (data.messages.length) {
          oldestId = data.messages[0].id;
          prependMessages(data.messages);
        }
        if (!data.has_more) loadMoreBtn.remove();
      } catch (err) {
        toast("Couldn't load older messages.");
      } finally {
        loadMoreBtn.disabled = false;
      }
    });
  }

  // ---------- start ----------
  let prev = null;
  history.forEach((m) => { seen.add(m.id); list.appendChild(buildMessage(m, prev)); prev = m; });
  emptyState.hidden = history.length > 0;
  scrollToBottom();
  connect();
})();
