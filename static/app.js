const CLASS_ABBREVS = new Set([
  "BER", "BRD", "BST", "CLR", "DRU", "ENC", "MAG", "MNK",
  "NEC", "PAL", "RNG", "ROG", "SHD", "SHM", "WAR", "WIZ",
]);

const pickLiveButton = document.querySelector("#pick-live");
const liveName = document.querySelector("#live-name");
const support = document.querySelector("#support");
const selectAll = document.querySelector("#select-all");
const serverFilter = document.querySelector("#server-filter");
const characters = document.querySelector("#characters");
const emptyState = document.querySelector("#emptyState");
const fileBalloon = document.createElement("div");
fileBalloon.className = "file-balloon";
fileBalloon.hidden = true;
fileBalloon.setAttribute("role", "tooltip");
document.body.append(fileBalloon);
document.querySelector(".roster-shell").addEventListener("scroll", hideFileBalloon);
const zipButton = document.querySelector("#download-zip");
const statusLine = document.querySelector("#status");
const logBox = document.querySelector("#log");

let liveFolderName = "";
let groups = [];
let eqclientSource = "";
let eqclientFile = null;
let busy = false;
let useLocalFolder = location.hostname === "127.0.0.1" || location.hostname === "localhost";

function parseCharacterIni(filename) {
  if (!filename.toLowerCase().endsWith(".ini")) return null;
  const stem = filename.slice(0, -4);
  const lowered = stem.toLowerCase();
  let prefix = "";
  let rest = stem;
  if (lowered.startsWith("at_default_")) {
    prefix = stem.slice(0, 11);
    rest = stem.slice(11);
  } else if (lowered.startsWith("ui_")) {
    prefix = stem.slice(0, 3);
    rest = stem.slice(3);
  }
  const parts = rest.split("_");
  let name;
  let server;
  let cls = "";
  let extra = "";
  if (parts.length === 2) {
    [name, server] = parts;
  } else if (parts.length === 3) {
    [name, server, cls] = parts;
    if (!CLASS_ABBREVS.has(cls.toUpperCase())) return null;
  } else if (parts.length === 4 && parts[3].toLowerCase() === "shrd") {
    [name, server, cls, extra] = parts;
    if (!CLASS_ABBREVS.has(cls.toUpperCase())) return null;
  } else {
    return null;
  }
  if (server.toLowerCase() === "characters") return null;
  if (!isToken(name) || !isToken(server) || (cls && !isToken(cls)) || (extra && !isToken(extra))) return null;
  const clsPart = cls ? `_${cls}` : "";
  const extraPart = extra ? `_${extra}` : "";
  return {
    prefix,
    name,
    server,
    cls,
    extra,
    betaFilename: `${prefix}${name}_beta${clsPart}${extraPart}.ini`,
  };
}

function isToken(value) {
  return /^[A-Za-z0-9]+$/.test(value);
}

function setStatus(message) {
  statusLine.replaceChildren(document.createTextNode(message));
  if (message.startsWith("More than one file would be named")) {
    const chip = document.createElement("span");
    chip.className = "error-chip";
    chip.textContent = "This character is listed on more than one server. Uncheck the old one you no longer need.";
    statusLine.append(chip);
  }
}

function log(message) {
  logBox.textContent += (logBox.textContent ? "\n" : "") + message;
}

function clearLog() {
  logBox.textContent = "";
}

function serverBoxes() {
  return [...serverFilter.querySelectorAll("input[data-server]")];
}

function visibleGroups() {
  const boxes = serverBoxes();
  if (boxes.length === 0) return groups;
  const chosen = new Set(
    boxes.filter((box) => box.checked).map((box) => box.dataset.server.toLowerCase())
  );
  return groups.filter((group) => chosen.has(group.server.toLowerCase()));
}

function refreshActions() {
  const visible = visibleGroups();
  const anySelected = groups.some((group) => group.checked);
  pickLiveButton.disabled = busy;
  zipButton.disabled = busy || !liveFolderName || !anySelected;
  selectAll.disabled = busy || visible.length === 0;
  syncServerChecks();
  const checkedCount = visible.filter((group) => group.checked).length;
  selectAll.checked = visible.length > 0 && checkedCount === visible.length;
  selectAll.indeterminate = checkedCount > 0 && checkedCount < visible.length;
}

function hideFileBalloon() {
  fileBalloon.hidden = true;
  fileBalloon.replaceChildren();
}

function placeBalloon(anchor) {
  const rect = anchor.getBoundingClientRect();
  const margin = 8;
  let left = rect.left;
  let top = rect.bottom + 6;
  const width = fileBalloon.offsetWidth;
  const height = fileBalloon.offsetHeight;
  if (left + width > window.innerWidth - margin) left = window.innerWidth - width - margin;
  if (left < margin) left = margin;
  if (top + height > window.innerHeight - margin) top = Math.max(margin, rect.top - height - 6);
  fileBalloon.style.left = `${left}px`;
  fileBalloon.style.top = `${top}px`;
}

function showFileBalloon(anchor, files) {
  const list = document.createElement("ul");
  for (const file of files) {
    const item = document.createElement("li");
    const folder = file.kind === "userdata" ? "userdata/" : "";
    item.textContent = `${folder}${file.name} → ${folder}${file.betaFilename}`;
    list.append(item);
  }
  fileBalloon.replaceChildren(list);
  fileBalloon.hidden = false;
  placeBalloon(anchor);
}

function showPersonaBalloon(anchor) {
  const classes = (anchor.dataset.hiddenClasses || "").split(" ").filter(Boolean);
  if (!classes.length) return;
  const list = document.createElement("div");
  list.className = "persona-balloon";
  for (const cls of classes) {
    const badge = ClassVisuals.createBadge(cls);
    if (badge) list.append(badge);
  }
  fileBalloon.replaceChildren(list);
  fileBalloon.hidden = false;
  placeBalloon(anchor);
}

function fitPersonaRow(top) {
  const personas = top.querySelector(".char-personas");
  if (!personas) return;
  const badges = [...personas.querySelectorAll(".class-badge")];
  const more = personas.querySelector(".persona-more");
  if (!badges.length || !more) return;

  for (const badge of badges) badge.hidden = false;
  more.hidden = true;

  const gap = parseFloat(getComputedStyle(personas).columnGap) || 0;
  const available = personas.clientWidth;
  const widths = badges.map((badge) => badge.getBoundingClientRect().width);
  const total = widths.reduce((sum, width, index) => sum + width + (index ? gap : 0), 0);
  if (total <= available + 0.5) {
    more.hidden = true;
    more.dataset.hiddenClasses = "";
    return;
  }

  function countThatFits(tokenWidth) {
    let used = 0;
    let count = 0;
    for (let index = 0; index < widths.length; index += 1) {
      const hiddenAfter = widths.length - (index + 1);
      const extra = hiddenAfter > 0 ? gap + tokenWidth : 0;
      const next = widths[index] + (count > 0 ? gap : 0);
      if (used + next + extra > available + 0.5) break;
      used += next;
      count += 1;
    }
    return count;
  }

  more.hidden = false;
  let fitCount = 0;
  let tokenWidth = 0;
  for (let pass = 0; pass < 3; pass += 1) {
    const hidden = badges.length - fitCount;
    more.textContent = `+${hidden || badges.length}`;
    tokenWidth = more.getBoundingClientRect().width;
    const nextCount = countThatFits(tokenWidth);
    if (pass > 0 && nextCount === fitCount) break;
    fitCount = nextCount;
  }

  const hiddenCount = badges.length - fitCount;
  badges.forEach((badge, index) => {
    badge.hidden = index >= fitCount;
  });
  if (hiddenCount === 0 || (fitCount === 0 && tokenWidth > available + 0.5)) {
    more.hidden = true;
    more.dataset.hiddenClasses = "";
    return;
  }
  more.hidden = false;
  more.textContent = `+${hiddenCount}`;
  more.dataset.hiddenClasses = badges.slice(fitCount).map((badge) => badge.textContent).join(" ");
}

function fitAllPersonas() {
  for (const top of characters.querySelectorAll(".char-row-top")) fitPersonaRow(top);
}

new ResizeObserver(() => fitAllPersonas()).observe(document.querySelector(".roster-shell"));

const copyTitle = document.querySelector("#copy-title");
const copyTip = document.querySelector("#copy-tip");
copyTitle.addEventListener("mouseenter", () => {
  fileBalloon.replaceChildren(...[...copyTip.children].map((node) => node.cloneNode(true)));
  fileBalloon.hidden = false;
  placeBalloon(copyTitle);
});
copyTitle.addEventListener("mouseleave", hideFileBalloon);

function renderCharacters() {
  const visible = liveFolderName ? visibleGroups() : [];
  if (!liveFolderName || visible.length === 0) {
    characters.replaceChildren();
    const boxes = serverBoxes();
    const anyServer = boxes.some((box) => box.checked);
    emptyState.hidden = false;
    emptyState.textContent = !liveFolderName
      ? "Choose your Live EverQuest folder to list characters."
      : boxes.length === 0 || anyServer
        ? "No character INI files found in this folder."
        : "No servers selected.";
    refreshActions();
    return;
  }
  emptyState.hidden = true;
  characters.replaceChildren();
  for (const group of visible) {
    const row = document.createElement("li");
    if (group.checked) row.className = "selected";
    const label = document.createElement("label");
    label.className = "roster-row";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "roster-check";
    box.checked = group.checked;
    box.addEventListener("change", () => {
      group.checked = box.checked;
      row.classList.toggle("selected", box.checked);
      refreshActions();
    });
    const card = document.createElement("div");
    card.className = "char-card-inner";
    card.append(ClassVisuals.createIcon(group.classes[0] || ""));
    const meta = document.createElement("div");
    meta.className = "char-meta";
    const top = document.createElement("div");
    top.className = "char-row-top";
    const name = document.createElement("span");
    name.className = "char-name has-files";
    name.textContent = group.name;
    name.addEventListener("mouseenter", () => showFileBalloon(name, group.files));
    name.addEventListener("mouseleave", hideFileBalloon);
    top.append(name);
    const personas = document.createElement("span");
    personas.className = "char-personas";
    for (const cls of group.classes) {
      const badge = ClassVisuals.createBadge(cls);
      if (badge) personas.append(badge);
    }
    if (personas.childElementCount) {
      const more = document.createElement("span");
      more.className = "persona-more";
      more.hidden = true;
      more.addEventListener("mouseenter", () => showPersonaBalloon(more));
      more.addEventListener("mouseleave", hideFileBalloon);
      personas.append(more);
      top.append(personas);
    }
    const serverEl = document.createElement("div");
    serverEl.className = "char-server";
    serverEl.textContent = group.server;
    meta.append(top, serverEl);
    card.append(meta);
    label.append(box, card);
    row.append(label);
    characters.append(row);
  }
  refreshActions();
  requestAnimationFrame(() => fitAllPersonas());
}

function isEqclientIni(filename) {
  return filename.toLowerCase() === "eqclient.ini";
}

function rememberCharacterFile(found, kind, filename, source) {
  const parsed = parseCharacterIni(filename);
  if (!parsed || parsed.server.toLowerCase() === "beta") return;
  found.push({
    kind,
    name: filename,
    betaFilename: parsed.betaFilename,
    character: parsed.name,
    server: parsed.server,
    cls: parsed.cls,
    ...source,
  });
}

function characterFilesFromList(fileList) {
  const found = [];
  let eqclient = null;
  for (const file of fileList) {
    const parts = (file.webkitRelativePath || file.name).split(/[/\\]/).filter(Boolean);
    const filename = parts[parts.length - 1] || "";
    if (!filename.toLowerCase().endsWith(".ini")) continue;
    const inUserdata = parts.some((part) => part.toLowerCase() === "userdata");
    if (!inUserdata && isEqclientIni(filename)) {
      if (!eqclient) eqclient = { source: `root/${filename}`, file };
      continue;
    }
    const kind = inUserdata ? "userdata" : "root";
    rememberCharacterFile(found, kind, filename, { file });
  }
  return { found, eqclient };
}

function folderNameFromList(fileList) {
  const path = fileList[0] && fileList[0].webkitRelativePath;
  if (!path) return "EverQuest";
  return path.split(/[/\\]/).filter(Boolean)[0] || "EverQuest";
}

function fillServerFilter() {
  const previous = new Map(
    serverBoxes().map((box) => [box.dataset.server.toLowerCase(), box.checked])
  );
  const servers = [...new Set(groups.map((group) => group.server))];
  servers.sort((a, b) => a.localeCompare(b));
  serverFilter.replaceChildren();
  if (servers.length === 0) return;

  const allLabel = document.createElement("label");
  allLabel.className = "chip";
  const allBox = document.createElement("input");
  allBox.type = "checkbox";
  allBox.id = "servers-all";
  allLabel.append(allBox, document.createTextNode("All servers"));

  const choices = servers.map((server) => {
    const label = document.createElement("label");
    label.className = "chip";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.dataset.server = server;
    const known = previous.get(server.toLowerCase());
    box.checked = known === undefined ? true : known;
    box.addEventListener("change", () => {
      syncServerChecks();
      renderCharacters();
    });
    label.append(box, document.createTextNode(server));
    return label;
  });

  allBox.addEventListener("change", () => {
    for (const label of choices) label.querySelector("input").checked = allBox.checked;
    renderCharacters();
  });
  serverFilter.append(allLabel, ...choices);
  syncServerChecks();
}

function paintChip(box) {
  const chip = box.closest(".chip");
  if (!chip) return;
  chip.classList.toggle("on", box.checked && !box.indeterminate);
  chip.classList.toggle("mixed", box.indeterminate);
}

function syncServerChecks() {
  const allBox = serverFilter.querySelector("#servers-all");
  const boxes = serverBoxes();
  if (!allBox) return;
  const checked = boxes.filter((box) => box.checked).length;
  allBox.checked = boxes.length > 0 && checked === boxes.length;
  allBox.indeterminate = checked > 0 && checked < boxes.length;
  allBox.disabled = busy || boxes.length === 0;
  paintChip(allBox);
  for (const box of boxes) {
    box.disabled = busy || groups.length === 0;
    paintChip(box);
  }
}

function groupCharacters(files) {
  const map = new Map();
  for (const file of files) {
    const key = `${file.character.toLowerCase()}|${file.server.toLowerCase()}`;
    let group = map.get(key);
    if (!group) {
      group = {
        key,
        name: file.character,
        server: file.server,
        classes: [],
        files: [],
        checked: false,
      };
      map.set(key, group);
    }
    group.files.push(file);
    if (file.cls && !group.classes.some((item) => item.toLowerCase() === file.cls.toLowerCase())) {
      group.classes.push(file.cls);
    }
  }
  const list = [...map.values()];
  list.sort((a, b) => a.name.localeCompare(b.name) || a.server.localeCompare(b.server));
  for (const group of list) {
    group.classes.sort((a, b) => a.localeCompare(b));
    group.files.sort((a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name));
  }
  return list;
}

async function buildForm() {
  const form = new FormData();
  let count = 0;
  for (const group of groups) {
    if (!group.checked) continue;
    for (const item of group.files) {
      const file = item.file || await item.handle.getFile();
      const folder = item.kind === "userdata" ? "userdata" : "root";
      form.append("files", file, file.name);
      form.append("paths", `${folder}/${item.name}`);
      count += 1;
    }
  }
  if (eqclientFile && eqclientSource) {
    form.append("files", eqclientFile, eqclientFile.name);
    form.append("paths", eqclientSource);
    count += 1;
  }
  if (count === 0) throw new Error("Select at least one character.");
  return { form, count };
}

async function wakeServer() {
  setStatus("Checking the server. If it has been idle, this can take about a minute.");
  const response = await fetch("/health", { cache: "no-store" });
  if (!response.ok) throw new Error("The server did not respond.");
}

async function requestZip(form) {
  setStatus("Uploading files to rename…");
  const response = await fetch("/rename", { method: "POST", body: form });
  if (!response.ok) {
    let message = `Rename failed (${response.status}).`;
    const text = await response.text();
    try {
      const body = JSON.parse(text);
      if (body.error) message = body.error;
    } catch (_error) {
      /* The response was not JSON. */
    }
    throw new Error(message);
  }
  return response.arrayBuffer();
}

function downloadBlob(buffer) {
  const blob = new Blob([buffer], { type: "application/zip" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = "eq-beta-files.zip";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function withBusy(work, clear) {
  busy = true;
  refreshActions();
  if (clear) clearLog();
  try {
    await work();
  } catch (error) {
    const message = error && error.message ? error.message : "Something went wrong.";
    setStatus(message);
    log(message);
  } finally {
    busy = false;
    refreshActions();
  }
}

function showFoundStatus() {
  const countLabel = groups.length === 1 ? "character" : "characters";
  const clientNote = eqclientSource ? " eqclient.ini is included." : "";
  setStatus(groups.length ? `Found ${groups.length} ${countLabel}.${clientNote}` : "No character INI files found.");
}

function applyFoundFiles(folderLabel, found, client) {
  liveFolderName = folderLabel;
  liveName.textContent = `Selected: ${folderLabel}`;
  if (client && typeof client === "object") {
    eqclientSource = client.source || "";
    eqclientFile = client.file || null;
  } else {
    eqclientSource = client || "";
    eqclientFile = null;
  }
  groups = groupCharacters(found);
  fillServerFilter();
  renderCharacters();
  showFoundStatus();
}

async function readJson(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (_error) {
    return {};
  }
}

async function pickOnThisComputer() {
  setStatus("Select the Live EverQuest folder in the dialog.");
  const response = await fetch("/pick-folder", { method: "POST", cache: "no-store" });
  const body = await readJson(response);
  if (!response.ok) throw new Error(body.error || "Could not read that folder.");
  if (body.cancelled) {
    setStatus("Folder selection was cancelled.");
    return;
  }
  applyFoundFiles(body.folder || body.name, body.files || [], body.eqclient || "");
}

function openHostedFolderPicker() {
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = ".ini";
  input.addEventListener("change", () => {
    const files = [...input.files];
    if (!files.length) return;
    const picked = characterFilesFromList(files);
    withBusy(async () => {
      setStatus("Reading character INI names…");
      applyFoundFiles(folderNameFromList(files), picked.found, picked.eqclient);
    });
  });
  input.click();
}

pickLiveButton.addEventListener("click", () => {
  if (useLocalFolder) {
    withBusy(() => pickOnThisComputer());
    return;
  }
  setStatus("Open your EverQuest folder, paste the search, press Ctrl+A, then Open.");
  openHostedFolderPicker();
});

selectAll.addEventListener("change", () => {
  for (const group of visibleGroups()) group.checked = selectAll.checked;
  renderCharacters();
});

function selectedSources() {
  const paths = [];
  for (const group of groups) {
    if (!group.checked) continue;
    for (const item of group.files) paths.push(item.source);
  }
  if (eqclientSource) paths.push(eqclientSource);
  return paths;
}

zipButton.addEventListener("click", () => {
  withBusy(async () => {
    if (!liveFolderName) throw new Error("Choose the Live folder first.");
    let buffer;
    let count;
    if (useLocalFolder) {
      const paths = selectedSources();
      if (paths.length === 0) throw new Error("Select at least one character.");
      setStatus("Building the zip…");
      const response = await fetch("/rename-local", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths }),
        cache: "no-store",
      });
      if (!response.ok) {
        const body = await readJson(response);
        throw new Error(body.error || `Rename failed (${response.status}).`);
      }
      buffer = await response.arrayBuffer();
      count = paths.length;
    } else {
      const built = await buildForm();
      count = built.count;
      await wakeServer();
      buffer = await requestZip(built.form);
    }
    downloadBlob(buffer);
    const fileWord = count === 1 ? "file" : "files";
    setStatus("Downloaded eq-beta-files.zip. Open it and follow readme.txt.");
    log(`Renamed ${count} ${fileWord}. The zip is in your Downloads folder.`);
  }, true);
});

async function loadMode() {
  try {
    const response = await fetch("/health", { cache: "no-store" });
    const body = await readJson(response);
    if (response.ok) useLocalFolder = Boolean(body.localFolder);
  } catch (_error) {
    /* Keep the address check from page load. */
  }
  if (!useLocalFolder) {
    const privacy = document.querySelector("#privacy");
    if (privacy) {
      privacy.textContent = "Checked character INI files are uploaded so the server can rename them, then discarded. eqclient.ini is included when you select it. They are not saved. The first visit after the site has been idle can take about a minute while it wakes up.";
    }
    const searchHelp = document.querySelector("#hosted-search");
    if (searchHelp) searchHelp.hidden = false;
    const copySearch = document.querySelector("#copy-search");
    const iniSearch = document.querySelector("#ini-search");
    if (copySearch && iniSearch) {
      copySearch.addEventListener("click", async () => {
        const text = iniSearch.textContent;
        try {
          await navigator.clipboard.writeText(text);
        } catch (_error) {
          const range = document.createRange();
          range.selectNodeContents(iniSearch);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
        }
        copySearch.textContent = "Copied";
        setTimeout(() => {
          copySearch.textContent = "Copy";
        }, 1500);
      });
    }
  }
  refreshActions();
}

window.EQCopy = { parseCharacterIni };

const helpButton = document.querySelector("#help-button");
const helpMenu = document.querySelector("#help-menu");

function setHelpOpen(open) {
  helpMenu.hidden = !open;
  helpButton.setAttribute("aria-expanded", open ? "true" : "false");
}

helpButton.addEventListener("click", (event) => {
  event.stopPropagation();
  setHelpOpen(helpMenu.hidden);
});

document.addEventListener("click", (event) => {
  if (helpMenu.hidden || event.target.closest("#help")) return;
  setHelpOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setHelpOpen(false);
});

loadMode();
refreshActions();
