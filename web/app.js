"use strict";
/* Devkit web UI. Plain JS, no build step. Pages: overview, projects, jobs, devices, mac, activity, settings. */

const POLL_MS = 2000, DEVICE_POLL_MS = 15000, SYSTEM_POLL_MS = 60000, SCREEN_FRAME_MS = 200;
const LOG_TAIL = 2000, JOB_LIMIT = 150, FEED_LIMIT = 60;
const TEMPLATES = ["Time Profiler", "Game Performance", "Game Memory", "Allocations", "Leaks", "Metal System Trace", "App Launch",
  "Animation Hitches", "Power Profiler", "Network", "System Trace", "CPU Profiler", "SwiftUI"];

/* ---------------------------------------------------------------- text */
const T = {
  en: {
    connectTitle: "Connect to Devkit", connectText: "Paste the access token from devkit/config.json on the Mac. It is kept in this browser only.",
    token: "Access token", connect: "Connect", badToken: "That token was rejected.", unreachable: "The Mac isn't answering. Check that devkit-server is running.",
    nav: { overview: "Overview", projects: "Projects", jobs: "Jobs", devices: "Devices", mac: "This Mac", hosts: "Hosts", activity: "Activity", settings: "Settings" },
    hostsText: "Devkit machines connected to this one. Jobs can run on any of them; agents reach all of them through this address.",
    connectHost: "Connect a host", connectHostText: "On the other devkit, open Settings → Access tokens, create an Operator token named after this machine, and paste it here with that machine's address.",
    hostUrl: "Address", hostToken: "Its access token", connectBtn: "Connect", removeHost: "Disconnect", confirmRemoveHost: "Disconnect {n}? Its jobs keep running there.",
    online: "Online", offline: "Offline", thisHost: "this host", autoHost: "Automatic (shortest queue)", runOn: "Run on", onHost: "on {h}", host: "Host",
    idleHost: "Idle", manage: "Manage", openUi: "Open its web UI", platformName: { macos: "macOS", windows: "Windows", linux: "Linux" },
    tokens: "Access tokens", tokensText: "Give every person, agent and connected host its own token, so you can see who did what and revoke one without touching the others.",
    newToken: "Create token", tokenName: "Who or what uses it", tokenNameHint: "Shown in Activity, e.g. \"build agent (Windows)\" or \"studio-win\".",
    role: "Access", roles: { viewer: "Viewer: can look, can't change anything", operator: "Operator: can run and cancel jobs", admin: "Admin: can also manage tokens and hosts" },
    roleShort: { viewer: "Viewer", operator: "Operator", admin: "Admin" }, created: "Created", lastUsed: "Last used", revoke: "Revoke",
    confirmRevoke: "Revoke {n}? Anything using it loses access immediately.", tokenOnce: "Copy this token now. It is shown only once.",
    copy: "Copy", copied: "Copied", done: "Done", ownerToken: "From config.json on the Mac", you: "you",
    st: { running: "Running", queued: "Waiting", succeeded: "Succeeded", failed: "Failed", cancelled: "Cancelled" },
    k: { build: "Build", test: "Test", deploy: "Install", launch: "Launch", profile: "Profile", screenshot: "Screenshot", archive: "Archive",
         release: "Release", notarize: "Notarize", crashlogs: "Crash logs", unity: "Unity build", shell: "Shell", echo: "Echo" },
    tg: { ios: "iPhone / iPad", "ios-sim": "Simulator", macos: "Mac" },
    nowRunning: "Running now", nothingWaiting: "Nothing is waiting.", waitingN: "{n} waiting", idleTitle: "Nothing is running", idleText: "The Mac is free. Start something:", upNext: "Up next",
    recent: "Recent results", agents: "Connected", noAgents: "Nobody else is connected.", vitals: "Mac right now", feed: "What happened",
    noFeed: "Nothing has happened yet.", openJob: "Open job", stepOf: "step {a} of {b}", elapsed: "elapsed", took: "took", ago: "ago",
    cpu: "CPU", memory: "Memory", disk: "Free disk", load: "Load", thermal: "Thermal", battery: "Power", uptime: "Up for",
    thermalOk: "Normal", thermalHot: "Throttling", onAc: "Plugged in", onBattery: "On battery",
    projects: "Projects", projectsText: "Save a game or app once, then build, install and profile it with one click.", newProject: "New project",
    noProjects: "No projects yet. Add your game's repository, Xcode project and scheme once.", editProject: "Edit", deleteProject: "Delete",
    lastRun: "Last run", never: "Never run", confirmDelete: "Delete project {n}? Its jobs and files stay.",
    a: { build: ["Build", "Compile for a device, simulator or Mac."], install: ["Install & run", "Build, install and start it with your arguments."],
         launch: ["Launch", "Start the installed app and stream its output."], profile: ["Profile", "Record an Instruments trace while it runs."],
         test: ["Test", "Run the test suite."], screenshot: ["Screenshot", "Grab the device's screen."],
         archive: ["Archive", "Signed release archive, optionally exported."], release: ["Release", "TestFlight upload or notarized Mac build."],
         unity: ["Unity build", "Batch-build the Unity project."], shell: ["Run command", "Any shell command in the checkout."] },
    run: "Start", runTitle: "{a}: {p}", jobsOf: "Jobs for this project", allJobs: "All jobs", customJob: "Custom job",
    jobsText: "Everything the Mac has done, newest first.", search: "Search", anyProject: "All projects", anyState: "Any state", anyKind: "Any kind",
    noJobs: "No jobs match.", colWhat: "Job", colWhere: "Where", colWho: "Started by", colWhen: "When", colTook: "Duration",
    cancel: "Cancel job", rerun: "Run again", steps: "Steps", noSteps: "Waiting to start.", log: "Output", follow: "Follow",
    findInLog: "Find in output", whyFailed: "Why it failed:", files: "Files", noFiles: "No files yet.", download: "Download", openSummary: "Hottest functions", idleProfile: "No CPU samples with a call stack: the app was idle while recording.", cores: "{n} cores ({p} performance, {e} efficiency)",
    profiling: "Recording {t}", recorded: "{a} of {b} s recorded", macDuring: "Mac CPU during this job", watchScreen: "Watch the Mac's screen",
    requestedBy: "Started by", commit: "Commit", branch: "Branch or commit", target: "Platform", device: "Device", scheme: "Scheme",
    template: "Instruments template", duration: "Seconds", launchArgs: "Launch arguments", exportAs: "Export as", noExport: "Don't export",
    configuration: "Configuration", defaultCfg: "Default", command: "Command", anyDevice: "Any (generic build)",
    devices: "Devices", devicesText: "Phones and simulators the Mac can reach.", physical: "Connected devices", sims: "Simulators",
    noDevices: "No phones are connected. Plug one in or pair it over the network in Xcode.", apps: "Installed apps", loadApps: "Show installed apps",
    loading: "Loading…", crashLogs: "Get crash logs", shot: "Screenshot", booted: "Booted", shutdown: "Off", showAll: "Show all {n}",
    macTitle: "This Mac", macText: "Hardware, tools, settings and what the machine is doing.", hardware: "Hardware", tools: "Developer tools",
    settings: "Settings that matter", screen: "Screen", screenText: "View only, about 5 frames per second.", play: "Watch", pause: "Pause",
    display: "Display", screenOff: "Press Watch to see the Mac's screen.", topProcs: "Busiest processes", proc: "Process",
    activity: "Activity", activityText: "Who is connected and everything they did.", everyone: "Everyone who connected",
    active: "active", lastSeen: "last seen", via: "via", requests: "{n} requests",
    settingsTitle: "Settings", language: "Language", theme: "Theme", themeAuto: "Match system", themeLight: "Light", themeDark: "Dark",
    forget: "Forget access token", agentsSetup: "Connect an agent", agentsSetupText: "Agents use the MCP endpoint with the same access token.",
    api: "HTTP API", saved: "Saved", queued: "Queued {k}", cancelled: "Cancelled", save: "Save", close: "Close", create: "Create project",
    pName: "Name", pRepo: "Repository URL", pRef: "Default branch", pXcode: "Xcode project or workspace", pBundle: "Bundle ID",
    pTeam: "Team ID", pTarget: "Default platform", pDevice: "Default device", pUnityTarget: "Unity build target", pUnityMethod: "Unity build method",
    pNotes: "Notes", pRefHint: "Jobs check out this branch unless you pick another.", pXcodeHint: "Path inside the repository, e.g. ios/Game.xcodeproj",
    kind: "Kind", params: "Extra parameters (JSON)", badJson: "Extra parameters must be a JSON object.", projectName: "Project",
    c: { signing: "Signing certificate", profiles: "Provisioning profiles", devid: "Developer ID (Mac releases)", asc: "App Store Connect key",
         notary: "Notarization profile", devmode: "Developer mode", sleep: "Sleep", capture: "Screen recording permission",
         firewall: "Firewall", filevault: "FileVault", ssh: "Remote Login (SSH)", tailscale: "Tailscale" },
    h: { signing: "Sign in to Xcode → Settings → Accounts so device builds can be signed.",
         profiles: "None yet. Xcode creates them on the first signed device build after you sign in.",
         devid: "Needed to notarize Mac builds. Requires a paid Apple Developer team.",
         asc: "Add asc_api_key to config.json for TestFlight uploads.", notary: "Run xcrun notarytool store-credentials, then set notary_profile in config.json.",
         sleep: "Sleeps after {n} min when idle. Devkit keeps it awake while a job runs (display too for launch and profiling). Closing the lid on battery still sleeps.",
         capture: "Grant Screen Recording to python3 in System Settings → Privacy & Security to see the screen here.",
         ssh: "Debug channel only." },
    yes: "Yes", no: "No", on: "On", off: "Off", none: "None", never: "Never", minutes: "{n} min", installed: "installed",
  },
  de: {
    connectTitle: "Mit Devkit verbinden", connectText: "Zugangstoken aus devkit/config.json auf dem Mac einfügen. Er bleibt nur in diesem Browser.",
    token: "Zugangstoken", connect: "Verbinden", badToken: "Dieser Token wurde abgelehnt.", unreachable: "Der Mac antwortet nicht. Läuft devkit-server?",
    nav: { overview: "Übersicht", projects: "Projekte", jobs: "Jobs", devices: "Geräte", mac: "Dieser Mac", hosts: "Hosts", activity: "Aktivität", settings: "Einstellungen" },
    hostsText: "Mit diesem verbundene Devkit-Rechner. Jobs können auf jedem laufen; Agents erreichen alle über diese Adresse.",
    connectHost: "Host verbinden", connectHostText: "Auf dem anderen Devkit Einstellungen → Zugangstokens öffnen, einen Operator-Token mit dem Namen dieses Rechners erstellen und hier mit dessen Adresse einfügen.",
    hostUrl: "Adresse", hostToken: "Sein Zugangstoken", connectBtn: "Verbinden", removeHost: "Trennen", confirmRemoveHost: "{n} trennen? Seine Jobs laufen dort weiter.",
    online: "Online", offline: "Offline", thisHost: "dieser Host", autoHost: "Automatisch (kürzeste Warteschlange)", runOn: "Ausführen auf", onHost: "auf {h}", host: "Host",
    idleHost: "Frei", manage: "Verwalten", openUi: "Weboberfläche öffnen", platformName: { macos: "macOS", windows: "Windows", linux: "Linux" },
    tokens: "Zugangstokens", tokensText: "Jede Person, jeder Agent und jeder verbundene Host bekommt einen eigenen Token: So sieht man, wer was getan hat, und kann einzelne widerrufen.",
    newToken: "Token erstellen", tokenName: "Wer oder was ihn nutzt", tokenNameHint: "Erscheint in der Aktivität, z. B. „Build-Agent (Windows)“ oder „studio-win“.",
    role: "Zugriff", roles: { viewer: "Betrachter: darf ansehen, nichts ändern", operator: "Operator: darf Jobs starten und abbrechen", admin: "Admin: darf zusätzlich Tokens und Hosts verwalten" },
    roleShort: { viewer: "Betrachter", operator: "Operator", admin: "Admin" }, created: "Erstellt", lastUsed: "Zuletzt genutzt", revoke: "Widerrufen",
    confirmRevoke: "{n} widerrufen? Alles, was ihn nutzt, verliert sofort den Zugriff.", tokenOnce: "Diesen Token jetzt kopieren. Er wird nur einmal angezeigt.",
    copy: "Kopieren", copied: "Kopiert", done: "Fertig", ownerToken: "Aus config.json auf dem Mac", you: "du",
    st: { running: "Läuft", queued: "Wartet", succeeded: "Erfolgreich", failed: "Fehlgeschlagen", cancelled: "Abgebrochen" },
    k: { build: "Build", test: "Test", deploy: "Installieren", launch: "Starten", profile: "Profilieren", screenshot: "Bildschirmfoto", archive: "Archivieren",
         release: "Veröffentlichen", notarize: "Notarisieren", crashlogs: "Absturzberichte", unity: "Unity-Build", shell: "Shell", echo: "Echo" },
    tg: { ios: "iPhone / iPad", "ios-sim": "Simulator", macos: "Mac" },
    nowRunning: "Läuft gerade", nothingWaiting: "Nichts wartet.", waitingN: "{n} wartend", idleTitle: "Nichts läuft", idleText: "Der Mac ist frei. Etwas starten:", upNext: "Als Nächstes",
    recent: "Letzte Ergebnisse", agents: "Verbunden", noAgents: "Sonst ist niemand verbunden.", vitals: "Mac gerade", feed: "Was passiert ist",
    noFeed: "Noch ist nichts passiert.", openJob: "Job öffnen", stepOf: "Schritt {a} von {b}", elapsed: "vergangen", took: "Dauer", ago: "her",
    cpu: "CPU", memory: "Speicher", disk: "Freier Speicherplatz", load: "Last", thermal: "Temperatur", battery: "Strom", uptime: "Läuft seit",
    thermalOk: "Normal", thermalHot: "Gedrosselt", onAc: "Am Netzteil", onBattery: "Akku",
    projects: "Projekte", projectsText: "Spiel oder App einmal anlegen, dann mit einem Klick bauen, installieren und profilieren.", newProject: "Neues Projekt",
    noProjects: "Noch keine Projekte. Repository, Xcode-Projekt und Schema einmal eintragen.", editProject: "Bearbeiten", deleteProject: "Löschen",
    lastRun: "Zuletzt", never: "Noch nie ausgeführt", confirmDelete: "Projekt {n} löschen? Jobs und Dateien bleiben erhalten.",
    a: { build: ["Bauen", "Für Gerät, Simulator oder Mac kompilieren."], install: ["Installieren & starten", "Bauen, installieren und mit deinen Argumenten starten."],
         launch: ["Starten", "Installierte App starten und Ausgabe streamen."], profile: ["Profilieren", "Instruments-Aufnahme während sie läuft."],
         test: ["Testen", "Testsuite ausführen."], screenshot: ["Bildschirmfoto", "Bildschirm des Geräts aufnehmen."],
         archive: ["Archivieren", "Signiertes Release-Archiv, optional exportiert."], release: ["Veröffentlichen", "TestFlight-Upload oder notarisierter Mac-Build."],
         unity: ["Unity-Build", "Unity-Projekt im Batch bauen."], shell: ["Befehl ausführen", "Beliebiger Shell-Befehl im Checkout."] },
    run: "Starten", runTitle: "{a}: {p}", jobsOf: "Jobs dieses Projekts", allJobs: "Alle Jobs", customJob: "Eigener Job",
    jobsText: "Alles, was der Mac getan hat, neueste zuerst.", search: "Suchen", anyProject: "Alle Projekte", anyState: "Jeder Status", anyKind: "Jede Art",
    noJobs: "Keine passenden Jobs.", colWhat: "Job", colWhere: "Wo", colWho: "Gestartet von", colWhen: "Wann", colTook: "Dauer",
    cancel: "Job abbrechen", rerun: "Erneut ausführen", steps: "Schritte", noSteps: "Wartet auf Start.", log: "Ausgabe", follow: "Folgen",
    findInLog: "In Ausgabe suchen", whyFailed: "Warum es fehlschlug:", files: "Dateien", noFiles: "Noch keine Dateien.", download: "Herunterladen", openSummary: "Heißeste Funktionen", idleProfile: "Keine CPU-Samples mit Aufrufstapel: Die App war während der Aufnahme untätig.", cores: "{n} Kerne ({p} Leistung, {e} Effizienz)",
    profiling: "Nehme {t} auf", recorded: "{a} von {b} s aufgenommen", macDuring: "Mac-CPU während dieses Jobs", watchScreen: "Bildschirm des Macs ansehen",
    requestedBy: "Gestartet von", commit: "Commit", branch: "Branch oder Commit", target: "Plattform", device: "Gerät", scheme: "Schema",
    template: "Instruments-Vorlage", duration: "Sekunden", launchArgs: "Startargumente", exportAs: "Exportieren als", noExport: "Nicht exportieren",
    configuration: "Konfiguration", defaultCfg: "Standard", command: "Befehl", anyDevice: "Beliebig (generischer Build)",
    devices: "Geräte", devicesText: "Telefone und Simulatoren, die der Mac erreicht.", physical: "Verbundene Geräte", sims: "Simulatoren",
    noDevices: "Kein Telefon verbunden. Per Kabel anschließen oder in Xcode über das Netzwerk koppeln.", apps: "Installierte Apps", loadApps: "Installierte Apps zeigen",
    loading: "Lädt…", crashLogs: "Absturzberichte holen", shot: "Bildschirmfoto", booted: "Gestartet", shutdown: "Aus", showAll: "Alle {n} zeigen",
    macTitle: "Dieser Mac", macText: "Hardware, Werkzeuge, Einstellungen und was der Rechner gerade tut.", hardware: "Hardware", tools: "Entwicklerwerkzeuge",
    settings: "Wichtige Einstellungen", screen: "Bildschirm", screenText: "Nur ansehen, etwa 5 Bilder pro Sekunde.", play: "Ansehen", pause: "Pause",
    display: "Monitor", screenOff: "Auf „Ansehen“ drücken, um den Bildschirm des Macs zu sehen.", topProcs: "Aktivste Prozesse", proc: "Prozess",
    activity: "Aktivität", activityText: "Wer verbunden ist und alles, was passiert ist.", everyone: "Alle, die sich verbunden haben",
    active: "aktiv", lastSeen: "zuletzt", via: "über", requests: "{n} Anfragen",
    settingsTitle: "Einstellungen", language: "Sprache", theme: "Darstellung", themeAuto: "Wie System", themeLight: "Hell", themeDark: "Dunkel",
    forget: "Zugangstoken vergessen", agentsSetup: "Agent verbinden", agentsSetupText: "Agents nutzen den MCP-Endpunkt mit demselben Zugangstoken.",
    api: "HTTP-API", saved: "Gespeichert", queued: "{k} eingereiht", cancelled: "Abgebrochen", save: "Speichern", close: "Schließen", create: "Projekt anlegen",
    pName: "Name", pRepo: "Repository-URL", pRef: "Standard-Branch", pXcode: "Xcode-Projekt oder -Workspace", pBundle: "Bundle-ID",
    pTeam: "Team-ID", pTarget: "Standardplattform", pDevice: "Standardgerät", pUnityTarget: "Unity-Build-Ziel", pUnityMethod: "Unity-Build-Methode",
    pNotes: "Notizen", pRefHint: "Jobs checken diesen Branch aus, außer du wählst einen anderen.", pXcodeHint: "Pfad im Repository, z. B. ios/Game.xcodeproj",
    kind: "Art", params: "Zusätzliche Parameter (JSON)", badJson: "Zusätzliche Parameter müssen ein JSON-Objekt sein.", projectName: "Projekt",
    c: { signing: "Signaturzertifikat", profiles: "Provisioning-Profile", devid: "Developer ID (Mac-Releases)", asc: "App-Store-Connect-Schlüssel",
         notary: "Notarisierungsprofil", devmode: "Entwicklermodus", sleep: "Ruhezustand", capture: "Bildschirmaufnahme-Berechtigung",
         firewall: "Firewall", filevault: "FileVault", ssh: "Entfernte Anmeldung (SSH)", tailscale: "Tailscale" },
    h: { signing: "In Xcode → Einstellungen → Accounts anmelden, damit Geräte-Builds signiert werden können.",
         profiles: "Noch keine. Xcode erstellt sie beim ersten signierten Geräte-Build nach der Anmeldung.",
         devid: "Nötig zum Notarisieren von Mac-Builds. Erfordert ein bezahltes Apple-Developer-Team.",
         asc: "asc_api_key in config.json eintragen für TestFlight-Uploads.", notary: "xcrun notarytool store-credentials ausführen, dann notary_profile in config.json setzen.",
         sleep: "Schläft nach {n} Min. im Leerlauf. Devkit hält ihn wach, solange ein Job läuft (beim Starten und Profilieren auch den Bildschirm). Deckel zu im Akkubetrieb schläft trotzdem.",
         capture: "python3 in Systemeinstellungen → Datenschutz & Sicherheit → Bildschirmaufnahme erlauben, um den Bildschirm hier zu sehen.",
         ssh: "Nur als Debug-Kanal." },
    yes: "Ja", no: "Nein", on: "An", off: "Aus", none: "Keine", never: "Nie", minutes: "{n} Min.", installed: "installiert",
  }
};

/* ---------------------------------------------------------------- utilities */
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } },
};
let lang = store.get("devkit.lang") || (navigator.language.startsWith("de") ? "de" : "en");
let token = store.get("devkit.token") || "";
const $ = (s, root = document) => root.querySelector(s);
const t = (k, vars) => { let s = k.split(".").reduce((o, p) => (o ? o[p] : undefined), T[lang]) ?? k;
  if (vars) Object.entries(vars).forEach(([a, b]) => { s = s.replace("{" + a + "}", b); }); return s; };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const parseTime = s => (s ? new Date(String(s).replace(/([+-]\d\d)(\d\d)$/, "$1:$2")) : null);
const fmtBytes = n => n == null ? "–" : n < 1024 ? n + " B" : n < 1 << 20 ? (n / 1024).toFixed(1) + " KB" : n < 1 << 30 ? (n / 1048576).toFixed(1) + " MB" : (n / 1073741824).toFixed(1) + " GB";
function fmtDur(ms) { const s = Math.max(0, Math.round(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`; }
function fmtAgo(d) { if (!d) return ""; const s = (Date.now() - d) / 1000, f = new Intl.RelativeTimeFormat(lang, { numeric: "auto", style: "short" });
  return s < 45 ? f.format(-Math.max(0, Math.round(s)), "second") : s < 3600 ? f.format(-Math.round(s / 60), "minute") : s < 86400 ? f.format(-Math.round(s / 3600), "hour") : f.format(-Math.round(s / 86400), "day"); }
const fmtClock = d => d.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
function fmtUptime(sec) { const d = Math.floor(sec / 86400), h = Math.floor(sec / 3600) % 24, m = Math.floor(sec / 60) % 60;
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`; }
const kname = k => t("k." + k);
const tname = x => (x ? t("tg." + x) : "");
function toast(msg) { const el = document.createElement("div"); el.className = "toast"; el.setAttribute("role", "status"); el.textContent = msg;
  document.body.appendChild(el); setTimeout(() => el.remove(), 2600); }
function splitArgs(s) { return (String(s || "").match(/"[^"]*"|'[^']*'|\S+/g) || []).map(x => x.replace(/^(["'])(.*)\1$/, "$2")); }
const joinArgs = a => (a || []).map(x => (/\s/.test(x) ? `"${x}"` : x)).join(" ");

const ICON = {
  overview: '<path d="M3 10.5 10 4l7 6.5V17H3z"/><path d="M8 17v-4.5h4V17"/>',
  projects: '<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M3 8h14"/>',
  jobs: '<path d="M4 5h12M4 10h12M4 15h8"/>',
  devices: '<rect x="6" y="2.5" width="8" height="15" rx="2"/><path d="M9 5h2"/>',
  hosts: '<rect x="2.5" y="3" width="15" height="5.5" rx="1.5"/><rect x="2.5" y="11.5" width="15" height="5.5" rx="1.5"/><path d="M5.5 5.75h.01M5.5 14.25h.01"/>',
  mac: '<rect x="2.5" y="3.5" width="15" height="10" rx="1.5"/><path d="M7 17h6M10 13.5V17"/>',
  activity: '<path d="M2.5 10h3.5l2-5 4 10 2-5h3.5"/>',
  settings: '<circle cx="10" cy="10" r="2.5"/><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4"/>',
  build: '<path d="M12.5 3.5a3.5 3.5 0 0 0-3.3 4.6L3.5 13.8l2.7 2.7 5.7-5.7a3.5 3.5 0 0 0 4.6-3.3l-2.2 2.2-2.4-.6-.6-2.4z"/>',
  install: '<path d="M10 3v9M6.5 8.5 10 12l3.5-3.5"/><path d="M4 15.5h12"/>',
  launch: '<path d="M7 5v10l8-5z"/>',
  profile: '<path d="M2.5 15.5h15"/><path d="M4.5 12.5l3-4 3 2.5 4.5-6"/>',
  test: '<path d="M4 10.5l3.5 3.5L16 5.5"/>',
  screenshot: '<rect x="3" y="5" width="14" height="11" rx="2"/><circle cx="10" cy="10.5" r="2.5"/><path d="M7.5 5l1-1.5h3l1 1.5"/>',
  archive: '<rect x="3" y="4" width="14" height="4" rx="1"/><path d="M4.5 8v8h11V8M8 11h4"/>',
  release: '<path d="M10 16V4M5.5 8.5 10 4l4.5 4.5"/>',
  unity: '<path d="M10 2.5 16.5 6v8L10 17.5 3.5 14V6z"/><path d="M10 10v7.5M10 10l6.5-4M10 10 3.5 6"/>',
  shell: '<path d="M4 6l4 4-4 4M10 14h6"/>',
  phone: '<rect x="6" y="2.5" width="8" height="15" rx="2"/><path d="M9 5h2"/>',
  watch: '<rect x="5.5" y="5.5" width="9" height="9" rx="2.5"/><path d="M7.5 5.5V2.5h5v3M7.5 14.5v3h5v-3"/>',
};
const icon = (name, size = 18) => `<svg width="${size}" height="${size}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name] || ""}</svg>`;

/* ---------------------------------------------------------------- api */
class AuthError extends Error {}
async function api(path, opts = {}) {
  let r;
  try { r = await fetch(path, { ...opts, headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", "X-Devkit-UI": "1" } }); }
  catch (e) { throw new Error(t("unreachable")); }
  if (r.status === 401) throw new AuthError(t("badToken"));
  const json = (r.headers.get("Content-Type") || "").includes("json");
  const body = json ? await r.json() : await r.blob();
  if (!r.ok) { const e = new Error(body.error || r.statusText); e.status = r.status; throw e; }
  return body;
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
/* A job reference is "id" for this host or "id@host" for a connected host; remote calls go through /api/hosts/<host>. */
function jref(ref) {
  const [id, host] = String(ref).split("@");
  const remote = host && S.me && host !== S.me.host ? host : null;
  return { id, host: remote, base: remote ? "/api/hosts/" + encodeURIComponent(remote) : "/api" };
}
const jobHash = r => "#/jobs/" + r.id + (r.host && S.me && r.host !== S.me.host ? "@" + encodeURIComponent(r.host) : "");
const canOperate = () => S.me && S.me.role !== "viewer";
const isAdmin = () => S.me && S.me.role === "admin";
const PLATFORM_OF = { ios: "macos", "ios-sim": "macos", macos: "macos" };
function hostOptions(target) {
  const want = PLATFORM_OF[target] || "macos";
  const ok = S.hosts.filter(h => h.online && h.platform === want);
  return ok.length > 1 ? [["auto", t("autoHost")]].concat(ok.map(h => [h.self ? "" : h.name, h.name + (h.self ? " · " + t("thisHost") : "") + (h.queue_len ? " · " + t("waitingN", { n: h.queue_len }) : "")])) : [];
}

/* ---------------------------------------------------------------- state */
const S = { ping: null, jobs: [], clients: [], feed: [], metrics: [], devices: [], sims: [], projects: [], system: null, kinds: {}, down: false,
  me: null, hosts: [], tokens: [] };
const jobById = id => S.jobs.find(j => j.id === id);
const running = () => S.jobs.find(j => j.state === "running");
const deviceName = id => { if (!id) return ""; const d = S.devices.find(x => x.id === id); if (d) return d.model;
  const s = S.sims.find(x => x.id === id); return s ? s.name : id.slice(0, 8); };
const jobTitle = j => `${kname(j.kind)} ${j.project}`;
const jobWhere = j => [tname(j.target), deviceName(j.device)].filter(Boolean).join(", ");
const refLabel = j => (j.commit && j.commit !== "none" ? (/^[0-9a-f]{12,}$/.test(j.commit) ? j.commit.slice(0, 8) : j.commit) : "");
function jobDuration(j) { const a = parseTime(j.started), b = parseTime(j.finished); return a ? (b || new Date()) - a : null; }

async function pollCore() {
  try {
    const [ping, jobs, clients, feed] = await Promise.all([api("/api/ping"), api("/api/jobs?limit=" + JOB_LIMIT), api("/api/clients"), api("/api/activity?limit=" + FEED_LIMIT)]);
    Object.assign(S, { ping, jobs: jobs.jobs, clients: clients.clients, feed: feed.events, down: false });
  } catch (e) {
    if (e instanceof AuthError) return showConnect(e.message);
    S.down = true;
  }
  renderChrome(); page.refresh && page.refresh();
}
async function pollMetrics() { try { S.metrics = (await api("/api/metrics")).history; } catch (e) { /* shown by health dot */ } }
async function pollDevices() {
  try { const [d, s] = await Promise.all([api("/api/devices"), api("/api/simulators")]); S.devices = d.devices; S.sims = s.simulators; }
  catch (e) { /* shown by health dot */ }
}
async function pollSystem() { try { S.system = await api("/api/system"); } catch (e) { /* shown by health dot */ } }
async function pollHosts() { try { S.hosts = (await api("/api/hosts")).hosts; } catch (e) { /* shown by health dot */ } }
async function loadTokens() { try { S.tokens = isAdmin() ? (await api("/api/tokens")).tokens : []; } catch (e) { S.tokens = []; } }
async function loadProjects() { try { S.projects = (await api("/api/projects")).projects; } catch (e) { /* shown by health dot */ } }

/* ---------------------------------------------------------------- chrome */
const NAV = ["overview", "projects", "jobs", "devices", "mac", "hosts", "activity", "settings"];
function renderNav() {
  const cur = route().page;
  const waiting = S.jobs.filter(j => j.state === "queued").length + (running() ? 1 : 0);
  $("#nav-items").innerHTML = NAV.map(p => `<a class="item" href="#/${p === "overview" ? "" : p}" ${cur === p ? 'aria-current="page"' : ""}>
    ${icon(p)}<span class="label">${esc(t("nav." + p))}</span>${p === "jobs" && waiting ? `<span class="count">${waiting}</span>` : ""}</a>`).join("");
}
function renderChrome() {
  renderNav();
  $("#host-dot").className = "dot " + (S.down ? "off" : S.ping ? "on" : "");
  $("#host-name").textContent = S.ping ? S.ping.host.replace(/\.local$/, "") : "";
  $("#host-name").title = $("#host-name").textContent;
  const r = running(), pill = $("#running-pill");
  pill.classList.toggle("hidden", !r);
  if (r) { pill.href = "#/jobs/" + r.id; pill.innerHTML = `<b>${esc(t("nowRunning"))} · ${fmtDur(jobDuration(r))}</b>${esc(jobTitle(r))}`; }
  document.title = r ? `▶ ${jobTitle(r)} · Devkit` : "Devkit";
}

/* ---------------------------------------------------------------- shared fragments */
function markHtml(j, n) {
  const sym = { succeeded: "✓", failed: "✕", cancelled: "–", queued: n ?? "", running: "" }[j.state];
  return `<span class="mark ${esc(j.state)}" role="img" aria-label="${esc(t("st." + j.state))}">${sym}</span>`;
}
function jobRow(j, n) {
  const right = j.state === "running" ? fmtDur(jobDuration(j)) : j.state === "queued" ? "" : fmtAgo(parseTime(j.finished || j.created));
  const sub = j.state === "failed" && j.error ? j.error : [jobWhere(j), refLabel(j), j.requested_by].filter(Boolean).join(" · ");
  return `<li><a class="row" href="#/jobs/${esc(j.id)}">${markHtml(j, n)}<span class="t">${esc(jobTitle(j))}</span><span class="r">${esc(right)}</span><span class="s">${esc(sub)}</span></a></li>`;
}
function stepsOf(j) {
  const steps = j.steps || [];
  return steps.map((s, i) => ({ ...s, cls: s.finished ? (s.exit && j.state === "failed" && i === steps.length - 1 ? "broke" : "") : j.state === "running" ? "now" : "broke" }));
}
function sparkline(values, opts = {}) {
  const w = 300, h = 44, max = opts.max ?? Math.max(1, ...values), n = values.length;
  if (n < 2) return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"></svg>`;
  const x = i => (i / (n - 1)) * w, y = v => h - 2 - (Math.min(v, max) / max) * (h - 4);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${esc(opts.label || "")}">
    <path class="a" d="${d}L${w} ${h}L0 ${h}Z"/><path class="l" d="${d}" vector-effect="non-scaling-stroke"/></svg>`;
}
/* Hover readout for a sparkline: crosshair + value of the nearest sample, written into the sibling .spark-tip. */
function bindSpark(root, series, fmt) {
  root.querySelectorAll("[data-spark]").forEach(box => {
    const svg = $("svg", box), tip = $(".spark-tip", box), vals = series[box.dataset.spark];
    if (!svg || !vals || vals.length < 2) return;
    const restore = tip.textContent;
    svg.onpointermove = e => {
      const r = svg.getBoundingClientRect(), i = Math.round(((e.clientX - r.left) / r.width) * (vals.length - 1));
      const v = vals[Math.max(0, Math.min(vals.length - 1, i))];
      tip.textContent = `${fmt[box.dataset.spark](v.v)} · ${fmtClock(new Date(v.t * 1000))}`;
      let line = $("line.x", svg); if (!line) { line = document.createElementNS("http://www.w3.org/2000/svg", "line"); line.setAttribute("class", "x"); svg.appendChild(line); }
      const px = (Math.max(0, Math.min(vals.length - 1, i)) / (vals.length - 1)) * 300;
      line.setAttribute("x1", px); line.setAttribute("x2", px); line.setAttribute("y1", 0); line.setAttribute("y2", 44); line.setAttribute("vector-effect", "non-scaling-stroke");
    };
    svg.onpointerleave = () => { tip.textContent = restore; const l = $("line.x", svg); if (l) l.remove(); };
  });
}
function vitalsHtml(history, opts = {}) {
  const m = history[history.length - 1];
  if (!m) return `<div class="empty">${esc(t("loading"))}</div>`;
  const cpu = history.map(x => x.cpu_percent), mem = history.map(x => (100 * x.memory_used) / x.memory_total);
  const memPct = (100 * m.memory_used) / m.memory_total;
  const thermal = m.thermal_warning ? `<span class="st-failed">${esc(t("thermalHot"))}</span>` : esc(t("thermalOk"));
  const power = m.battery ? `${m.battery.percent}% <small>${esc(m.battery.ac ? t("onAc") : t("onBattery"))}</small>` : esc(t("onAc"));
  return `<div class="vitals">
    <div class="vital" data-spark="cpu"><div class="lbl">${esc(t("cpu"))}</div><div class="val">${m.cpu_percent.toFixed(0)}<small>%</small></div>${sparkline(cpu, { max: 100, label: t("cpu") })}<div class="spark-tip">${esc(t("load"))} ${m.load.join(" ")}</div></div>
    <div class="vital" data-spark="mem"><div class="lbl">${esc(t("memory"))}</div><div class="val">${fmtBytes(m.memory_used)} <small>/ ${fmtBytes(m.memory_total)}</small></div>${sparkline(mem, { max: 100, label: t("memory") })}<div class="spark-tip">${memPct.toFixed(0)}%</div></div>
    ${`<div class="vital"><div class="lbl">${esc(t("disk"))}</div><div class="val">${fmtBytes(m.disk_free)}</div><div class="spark-tip">/ ${fmtBytes(m.disk_total)}</div></div>`}
    <div class="vital"><div class="lbl">${esc(t("thermal"))}</div><div class="val" style="font-size:17px">${thermal}</div><div class="spark-tip">${esc(t("uptime"))} ${fmtUptime(m.uptime_seconds)}</div></div>
    ${opts.compact ? "" : `<div class="vital"><div class="lbl">${esc(t("battery"))}</div><div class="val" style="font-size:17px">${power}</div></div>`}
  </div>`;
}
function bindVitals(root, history) {
  bindSpark(root, { cpu: history.map(x => ({ v: x.cpu_percent, t: x.time })), mem: history.map(x => ({ v: (100 * x.memory_used) / x.memory_total, t: x.time })) },
    { cpu: v => v.toFixed(0) + "% CPU", mem: v => v.toFixed(0) + "% " + t("memory") });
}
function feedHtml(events) {
  if (!events.length) return `<div class="empty">${esc(t("noFeed"))}</div>`;
  return `<ul class="rows feed">${events.map(e => `<li class="k-${esc(e.kind)}"><time datetime="${new Date(e.time * 1000).toISOString()}">${fmtClock(new Date(e.time * 1000))}</time>
    <span>${e.job ? `<a href="#/jobs/${esc(e.job)}">` : ""}<b>${esc(e.who)}</b> <span>${esc(e.text)}</span>${e.job ? "</a>" : ""}</span></li>`).join("")}</ul>`;
}
function agentsHtml(clients, all) {
  const list = all ? clients : clients.filter(c => c.active);
  if (!list.length) return `<div class="empty">${esc(t("noAgents"))}</div>`;
  return `<ul class="rows agents">${list.map(c => `<li><i class="dot ${c.active ? "on" : ""}"></i><span class="t">${esc(c.label)}</span>
    <span class="r">${c.active ? esc(t("active")) : esc(t("lastSeen")) + " " + fmtAgo(c.last_seen * 1000)}</span>
    <span class="s">${esc(c.ip)} ${esc(t("via"))} ${esc(c.channel.toUpperCase())} · ${esc(c.last_action || "")}${all ? " · " + esc(t("requests", { n: c.requests })) : ""}</span></li>`).join("")}</ul>`;
}

function hostRows(list) {
  return `<ul class="rows">${list.map(h => { const r = h.running;
    const href = r ? "#/jobs/" + r.id + (h.self ? "" : "@" + encodeURIComponent(h.name)) : h.self ? "#/mac" : "#/hosts";
    const sub = h.online ? (r ? `${kname(r.kind)} ${r.project} · ${fmtDur(Date.now() - parseTime(r.started))}` : t("idleHost")) + (h.queue_len > (r ? 1 : 0) ? " · " + t("waitingN", { n: h.queue_len - (r ? 1 : 0) }) : "") : (h.error || t("offline"));
    return `<li><a class="row" href="${href}"><i class="dot ${h.online ? "on" : "off"}"></i><span class="t">${esc(h.name)}${h.self ? ` <span class="faint" style="font-weight:400">· ${esc(t("thisHost"))}</span>` : ""}</span>
      <span class="r">${esc(t("platformName." + h.platform) || h.platform || "")}</span><span class="s">${esc(sub)}</span></a></li>`; }).join("")}</ul>`;
}

/* ---------------------------------------------------------------- screen viewer */
function screenViewer(host, displays) {
  let playing = false, display = Number(store.get("devkit.display") || 1), last = null, frames = 0, since = performance.now();
  const opts = displays && displays.length > 1 ? `<div class="seg" role="group" aria-label="${esc(t("display"))}">${displays.map((d, i) =>
    `<button type="button" data-d="${i + 1}" aria-pressed="${i + 1 === display}" title="${esc(d.name)}">${i + 1}</button>`).join("")}</div>` : "";
  host.innerHTML = `<div class="panel-head"><h2>${esc(t("screen"))} <span class="faint" style="font-weight:400;font-size:13px">${esc(t("screenText"))}</span></h2>
    <div class="actions">${opts}<button type="button" class="btn small" data-play>${esc(t("play"))}</button></div></div>
    <div class="screen"><div class="msg">${esc(t("screenOff"))}</div></div>`;
  const box = $(".screen", host), btn = $("[data-play]", host);
  host.querySelectorAll("[data-d]").forEach(b => b.onclick = () => { display = Number(b.dataset.d); store.set("devkit.display", display);
    host.querySelectorAll("[data-d]").forEach(x => x.setAttribute("aria-pressed", x === b)); });
  btn.onclick = () => { playing = !playing; btn.textContent = playing ? t("pause") : t("play"); if (playing) loop(); };
  async function loop() {
    while (playing && host.isConnected) {
      const t0 = performance.now();
      if (!document.hidden) {
        try {
          const blob = await api("/api/screen?display=" + display);
          const url = URL.createObjectURL(blob);
          let img = $("img", box);
          if (!img) { box.innerHTML = '<img alt=""><span class="fps"></span>'; img = $("img", box); }
          img.src = url; if (last) URL.revokeObjectURL(last); last = url;
          frames++; const dt = (performance.now() - since) / 1000;
          if (dt > 2) { $(".fps", box).textContent = (frames / dt).toFixed(1) + " fps"; frames = 0; since = performance.now(); }
        } catch (e) {
          box.innerHTML = `<div class="msg">${esc(e.status === 503 ? t("h.capture") : e.message)}</div>`;
          playing = false; btn.textContent = t("play"); break;
        }
      }
      await new Promise(r => setTimeout(r, Math.max(0, SCREEN_FRAME_MS - (performance.now() - t0))));
    }
  }
}

/* ---------------------------------------------------------------- pages */
let page = {};
function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  return { page: parts[0] || "overview", arg: parts[1] };
}

const PAGES = {
  overview: {
    render(main) {
      main.innerHTML = `<div class="grid cols-main"><div class="stack"><div id="ov-now"></div>
        <section class="panel"><div class="panel-head"><h2>${esc(t("upNext"))}</h2></div><div id="ov-next"></div></section>
        <section class="panel"><div class="panel-head"><h2>${esc(t("recent"))}</h2><a class="link" href="#/jobs">${esc(t("allJobs"))}</a></div><div id="ov-recent"></div></section></div>
        <div class="stack"><section class="panel"><div class="panel-head"><h2>${esc(t("vitals"))}</h2><a class="link" href="#/mac">${esc(t("nav.mac"))}</a></div><div id="ov-vitals"></div></section>
        <section class="panel" id="ov-hosts-wrap"><div class="panel-head"><h2>${esc(t("nav.hosts"))}</h2><a class="link" href="#/hosts">${esc(t("manage"))}</a></div><div id="ov-hosts"></div></section>
        <section class="panel"><div class="panel-head"><h2>${esc(t("agents"))}</h2><a class="link" href="#/activity">${esc(t("nav.activity"))}</a></div><div id="ov-agents"></div></section>
        <section class="panel"><div class="panel-head"><h2>${esc(t("feed"))}</h2></div><div id="ov-feed"></div></section></div></div>`;
      this.refresh();
    },
    refresh() {
      const r = running(), now = $("#ov-now");
      if (!now) return;
      if (r) {
        const steps = stepsOf(r), cur = steps.findIndex(s => s.cls === "now");
        now.className = "nowcard running";
        now.innerHTML = `<div class="now-top"><div><div class="now-label">${esc(t("nowRunning"))}</div>
            <div class="now-title"><a href="#/jobs/${esc(r.id)}">${esc(jobTitle(r))}</a></div>
            <div class="muted">${esc([jobWhere(r), refLabel(r), r.requested_by].filter(Boolean).join(" · "))}</div></div>
          <div class="clock">${fmtDur(jobDuration(r))}<small>${steps.length ? esc(t("stepOf", { a: (cur < 0 ? steps.length : cur + 1), b: steps.length })) : esc(t("elapsed"))}</small></div></div>
          ${steps.length ? `<div class="now-steps">${steps.map(s => `<span class="chip-step ${s.cls}"><i class="s"></i>${esc(s.label)}</span>`).join("")}</div>` : ""}
          <pre class="now-tail" id="ov-tail"></pre>`;
        api(`/api/jobs/${r.id}/log?tail=8`).then(l => { const el = $("#ov-tail"); if (el) el.innerHTML = colorLog(l.text.trimEnd()); }).catch(() => {});
      } else {
        now.className = "nowcard";
        const quick = S.projects.slice(0, 3).flatMap(p => [["install", p], ["profile", p]]);
        now.innerHTML = `<div class="idle"><div><h2>${esc(t("idleTitle"))}</h2><p class="muted" style="margin:4px 0 0">${esc(t("idleText"))}</p></div>
          <div class="quick">${quick.length ? quick.map(([a, p]) => `<button class="btn" data-quick="${esc(a)}" data-p="${esc(p.name)}">${icon(a, 16)}${esc(t("a." + a)[0])} ${esc(p.name)}</button>`).join("") :
          `<a class="btn primary" href="#/projects">${esc(t("newProject"))}</a>`}</div></div>`;
        now.querySelectorAll("[data-quick]").forEach(b => b.onclick = () => openRun(S.projects.find(p => p.name === b.dataset.p), b.dataset.quick));
      }
      const next = S.jobs.filter(j => j.state === "queued").reverse();
      $("#ov-next").innerHTML = next.length ? `<ul class="rows">${next.map((j, i) => jobRow(j, i + 1)).join("")}</ul>` : `<div class="empty">${esc(t("nothingWaiting"))}</div>`;
      const recent = S.jobs.filter(j => !["queued", "running"].includes(j.state)).slice(0, 8);
      $("#ov-recent").innerHTML = recent.length ? `<ul class="rows">${recent.map(j => jobRow(j)).join("")}</ul>` : `<div class="empty">${esc(t("noJobs"))}</div>`;
      $("#ov-vitals").innerHTML = vitalsHtml(S.metrics.slice(-60), { compact: true }); bindVitals($("#ov-vitals"), S.metrics.slice(-60));
      $("#ov-agents").innerHTML = agentsHtml(S.clients, false);
      $("#ov-hosts-wrap").classList.toggle("hidden", S.hosts.length < 2);
      $("#ov-hosts").innerHTML = hostRows(S.hosts);
      $("#ov-feed").innerHTML = feedHtml(S.feed.slice(0, 12));
    },
  },

  projects: {
    render(main, arg) {
      if (arg) return PAGES.project.render(main, arg);
      main.innerHTML = `<div class="page-head"><div><h1>${esc(t("projects"))}</h1><p>${esc(t("projectsText"))}</p></div>
        <div class="actions"><button class="btn primary" id="new-project">${esc(t("newProject"))}</button></div></div><div id="pj-list"></div>`;
      $("#new-project").onclick = () => openProject();
      this.refresh();
    },
    refresh() {
      const el = $("#pj-list"); if (!el) return PAGES.project.refresh();
      if (!S.projects.length) { el.innerHTML = `<div class="panel empty">${esc(t("noProjects"))}<br><button class="btn primary" id="np2">${esc(t("newProject"))}</button></div>`;
        $("#np2").onclick = () => openProject(); return; }
      el.innerHTML = `<div class="proj-grid">${S.projects.map(p => { const last = S.jobs.find(j => j.project === p.name);
        return `<a class="panel proj" href="#/projects/${encodeURIComponent(p.name)}"><h3>${esc(p.name)}</h3>
          <div class="meta">${esc(p.repo || "")}</div><div class="meta">${esc([p.ref, p.scheme, tname(p.target)].filter(Boolean).join(" · "))}</div>
          <div class="last">${last ? `${markHtml(last)} ${esc(kname(last.kind))} · ${esc(fmtAgo(parseTime(last.finished || last.created)))}` : `<span class="faint">${esc(t("never"))}</span>`}</div></a>`; }).join("")}</div>`;
    },
  },

  project: {
    render(main, name) {
      this.name = name;
      const p = S.projects.find(x => x.name === name);
      if (!p) { main.innerHTML = `<div class="panel empty">${esc(t("loading"))}</div>`; loadProjects().then(() => S.projects.some(x => x.name === name) && this.render(main, name)); return; }
      const acts = ["install", "build", "profile", "launch", "test", "screenshot", "archive", "release", "unity", "shell"];
      main.innerHTML = `<a class="crumb" href="#/projects">← ${esc(t("projects"))}</a>
        <div class="page-head"><div><h1>${esc(p.name)}</h1><p>${esc([p.repo, p.ref].filter(Boolean).join(" · "))}</p></div>
        <div class="actions"><button class="btn" id="pe">${esc(t("editProject"))}</button><button class="btn danger" id="pd">${esc(t("deleteProject"))}</button></div></div>
        <div class="action-grid" style="margin-bottom:22px">${acts.map(a => `<button class="action" data-a="${a}"><b>${icon(a)}${esc(t("a." + a)[0])}</b><span>${esc(t("a." + a)[1])}</span></button>`).join("")}</div>
        <section class="panel"><div class="panel-head"><h2>${esc(t("jobsOf"))}</h2></div><div id="pj-jobs"></div></section>`;
      main.querySelectorAll("[data-a]").forEach(b => b.onclick = () => openRun(p, b.dataset.a));
      $("#pe").onclick = () => openProject(p);
      $("#pd").onclick = async () => { if (!confirm(t("confirmDelete", { n: p.name }))) return;
        await api("/api/projects/" + encodeURIComponent(p.name), { method: "DELETE" }); await loadProjects(); location.hash = "#/projects"; };
      this.refresh();
    },
    refresh() {
      const el = $("#pj-jobs"); if (!el) return;
      const jobs = S.jobs.filter(j => j.project === this.name).slice(0, 25);
      el.innerHTML = jobs.length ? `<ul class="rows">${jobs.map(j => jobRow(j)).join("")}</ul>` : `<div class="empty">${esc(t("never"))}</div>`;
    },
  },

  jobs: {
    f: { q: "", project: "", state: "", kind: "", host: "" }, remote: [],
    render(main, arg) {
      if (arg) return PAGES.job.render(main, arg);
      main.innerHTML = `<div class="page-head"><div><h1>${esc(t("nav.jobs"))}</h1><p>${esc(t("jobsText"))}</p></div>
        <div class="actions"><button class="btn" id="custom">${esc(t("customJob"))}</button></div></div>
        <section class="panel"><div class="filters">
          <input type="search" id="fq" placeholder="${esc(t("search"))}" value="${esc(this.f.q)}" aria-label="${esc(t("search"))}">
          ${S.hosts.length > 1 ? `<select id="fh" aria-label="${esc(t("host"))}">${S.hosts.map(h => `<option value="${h.self ? "" : esc(h.name)}" ${(h.self ? "" : h.name) === this.f.host ? "selected" : ""}>${esc(h.name)}</option>`).join("")}</select>` : ""}
          <select id="fp" aria-label="${esc(t("projectName"))}"></select><select id="fs" aria-label="${esc(t("anyState"))}"></select><select id="fk" aria-label="${esc(t("kind"))}"></select>
        </div><div class="table-wrap" id="jobs-table"></div></section>`;
      $("#custom").onclick = openCustom;
      const bind = (id, key) => { $(id).oninput = e => { this.f[key] = e.target.value; this.refresh(); }; };
      bind("#fq", "q"); bind("#fp", "project"); bind("#fs", "state"); bind("#fk", "kind");
      if ($("#fh")) $("#fh").onchange = e => { this.f.host = e.target.value; this.remote = []; this.refresh(); };
      this.refresh();
    },
    refresh() {
      const el = $("#jobs-table"); if (!el) return PAGES.job.refresh();
      const host = this.f.host;
      if (host) api(`/api/hosts/${encodeURIComponent(host)}/jobs?limit=${JOB_LIMIT}`).then(r => { if (this.f.host === host) { this.remote = r.jobs; this.draw(); } }).catch(e => { el.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; });
      else this.draw();
    },
    draw() {
      const el = $("#jobs-table"); if (!el) return;
      const src = this.f.host ? this.remote : S.jobs, suffix = this.f.host ? "@" + encodeURIComponent(this.f.host) : "";
      const opt = (sel, all, vals, label, cur) => { const s = $(sel); if (s.dataset.n === String(vals.length) && s.options.length) return;
        s.dataset.n = vals.length; s.innerHTML = `<option value="">${esc(all)}</option>` + vals.map(v => `<option value="${esc(v)}">${esc(label(v))}</option>`).join(""); s.value = cur; };
      opt("#fp", t("anyProject"), [...new Set(src.map(j => j.project))].sort(), v => v, this.f.project);
      opt("#fs", t("anyState"), ["running", "queued", "succeeded", "failed", "cancelled"], v => t("st." + v), this.f.state);
      opt("#fk", t("anyKind"), [...new Set(src.map(j => j.kind))].sort(), kname, this.f.kind);
      const q = this.f.q.toLowerCase();
      const jobs = src.filter(j => (!this.f.project || j.project === this.f.project) && (!this.f.state || j.state === this.f.state) && (!this.f.kind || j.kind === this.f.kind)
        && (!q || [j.project, j.kind, j.commit, j.requested_by, j.id, jobWhere(j)].join(" ").toLowerCase().includes(q)));
      el.innerHTML = jobs.length ? `<table class="data"><thead><tr><th></th><th>${esc(t("colWhat"))}</th><th>${esc(t("colWhere"))}</th><th>${esc(t("commit"))}</th>
        <th>${esc(t("colWho"))}</th><th>${esc(t("colWhen"))}</th><th class="num">${esc(t("colTook"))}</th></tr></thead><tbody>${jobs.map(j => {
          const d = jobDuration(j);
          return `<tr class="click" data-id="${esc(j.id) + suffix}" tabindex="0"><td>${markHtml(j)}</td><td>${esc(jobTitle(j))}</td><td>${esc(jobWhere(j))}</td>
            <td class="mono">${esc(refLabel(j))}</td><td>${esc(j.requested_by || "")}</td><td>${esc(fmtAgo(parseTime(j.started || j.created)))}</td>
            <td class="num mono">${d == null ? "" : fmtDur(d)}</td></tr>`; }).join("")}</tbody></table>` : `<div class="empty">${esc(t("noJobs"))}</div>`;
      el.querySelectorAll("tr[data-id]").forEach(tr => { tr.onclick = () => { location.hash = "#/jobs/" + tr.dataset.id; };
        tr.onkeydown = e => { if (e.key === "Enter") tr.onclick(); }; });
    },
  },

  job: {
    render(main, id) {
      Object.assign(this, { id, follow: true, find: "", lastText: null, summaryFor: null, shotFor: null });
      main.innerHTML = `<a class="crumb" href="#/jobs">← ${esc(t("nav.jobs"))}</a><div id="jd-head" class="page-head"></div>
        <div class="grid cols-main"><div class="stack">
          <div id="jd-live"></div>
          <section class="panel"><div class="log-tools"><b style="color:var(--ink)">${esc(t("log"))}</b><span style="display:flex;gap:12px;align-items:center">
            <input type="search" id="jd-find" placeholder="${esc(t("findInLog"))}" aria-label="${esc(t("findInLog"))}">
            <label><input type="checkbox" id="jd-follow" checked> ${esc(t("follow"))}</label></span></div><pre class="log" id="jd-log" tabindex="0"></pre></section>
          <section class="panel hidden" id="jd-screen"></section>
        </div><div class="stack">
          <section class="panel"><div class="panel-head"><h2>${esc(t("steps"))}</h2></div><ol class="timeline" id="jd-steps"></ol></section>
          <section class="panel hidden" id="jd-summary"></section>
          <section class="panel"><div class="panel-head"><h2>${esc(t("files"))}</h2></div><div id="jd-files"></div></section>
        </div></div>`;
      const log = $("#jd-log");
      $("#jd-follow").onchange = e => { this.follow = e.target.checked; if (this.follow) log.scrollTop = log.scrollHeight; };
      log.onscroll = () => { const end = log.scrollTop + log.clientHeight >= log.scrollHeight - 8; if (end !== this.follow) { this.follow = end; $("#jd-follow").checked = end; } };
      $("#jd-find").oninput = e => { this.find = e.target.value; this.lastText = null; this.refresh(); };
      this.refresh();
    },
    async refresh() {
      const id = this.id; if (!$("#jd-head")) return;
      let s, l, a;
      const J = jref(id);
      try { [s, l, a] = await Promise.all([api(`${J.base}/jobs/${J.id}`), api(`${J.base}/jobs/${J.id}/log?tail=${LOG_TAIL}`), api(`${J.base}/jobs/${J.id}/artifacts`)]); }
      catch (e) { if (e instanceof AuthError) return showConnect(e.message); $("#jd-head").innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
      if (route().arg !== id || !$("#jd-head")) return;
      const d = jobDuration(s);
      $("#jd-head").innerHTML = `<div><h1>${esc(jobTitle(s))}</h1><p>${esc([J.host ? t("onHost", { h: J.host }) : "", jobWhere(s), s.commit !== "none" ? (s.resolved ? `${s.commit} @ ${s.resolved.slice(0, 8)}` : s.commit) : "",
          s.requested_by ? t("requestedBy") + " " + s.requested_by : "", parseTime(s.started || s.created).toLocaleString(lang)].filter(Boolean).join(" · "))}</p></div>
        <div style="text-align:right"><div class="status-big st-${esc(s.state)}" style="justify-content:flex-end">${markHtml(s)} ${esc(t("st." + s.state))}${d != null ? ` · <span class="mono" style="font-size:15px">${fmtDur(d)}</span>` : ""}</div>
        <div class="actions" style="margin-top:10px;justify-content:flex-end">${["queued", "running"].includes(s.state) ? `<button class="btn danger" id="jd-cancel">${esc(t("cancel"))}</button>` : `<button class="btn" id="jd-rerun">${esc(t("rerun"))}</button>`}</div></div>`;
      $("#jd-head").insertAdjacentHTML("beforeend", s.state === "failed" && s.error ? `<div class="callout" role="alert"><b>${esc(t("whyFailed"))}</b> ${esc(s.error)}</div>` : "");
      const c = $("#jd-cancel"), rr = $("#jd-rerun");
      if (c) c.onclick = async () => { await post(`${J.base}/jobs/${J.id}/cancel`); toast(t("cancelled")); pollCore(); };
      if (rr) rr.onclick = () => rerun(s, J.host);
      if (!canOperate()) [c, rr].forEach(b => b && b.remove());
      const steps = stepsOf(s);
      $("#jd-steps").innerHTML = steps.length ? steps.map(x => `<li class="${x.cls}"><i class="s"></i><span class="n" title="${esc(x.label)}">${esc(x.label)}</span>
        <span class="d">${x.finished ? fmtDur((x.finished - x.started) * 1000) : s.state === "running" ? fmtDur(Date.now() - x.started * 1000) : ""}</span></li>`).join("")
        : `<li><span></span><span class="faint">${esc(t("noSteps"))}</span></li>`;
      this.renderLive(s, steps);
      const log = $("#jd-log");
      if (l.text !== this.lastText) { log.innerHTML = colorLog(l.text, this.find); this.lastText = l.text; if (this.follow) log.scrollTop = log.scrollHeight; }
      $("#jd-files").innerHTML = a.files.length ? `<ul class="files">${a.files.map(f => `<li><span class="name" title="${esc(f.path)}">${esc(f.path)}</span>
        <span style="display:flex;gap:10px;align-items:center"><span class="size">${fmtBytes(f.bytes)}</span><button class="btn small" data-file="${esc(f.path)}">${esc(t("download"))}</button></span></li>`).join("")}</ul>${a.files.some(f => /\.png$/i.test(f.path)) ? '<div class="pad" id="jd-shot"></div>' : ""}`
        : `<div class="empty">${esc(t("noFiles"))}</div>`;
      $("#jd-files").querySelectorAll("[data-file]").forEach(b => b.onclick = () => download(id, b.dataset.file));
      const png = a.files.find(f => /\.png$/i.test(f.path));
      if (png) { const url = await artifactUrl(id, png.path); const box = $("#jd-shot"); if (box) box.innerHTML = `<img class="shot" alt="${esc(png.path)}" src="${url}">`; }
      if (a.files.some(f => f.path === "profile-summary.json") && this.summaryFor !== id) { this.summaryFor = id; this.renderSummary(id); }
    },
    renderLive(s, steps) {
      const box = $("#jd-live"); if (!box) return;
      const rec = steps.find(x => x.label === "xctrace record");
      const want = Number((s.params || {}).duration) || 30;
      const parts = [];
      if (s.kind === "profile" && rec) {
        const secs = rec.finished ? want : Math.min(want, (Date.now() / 1000 - rec.started));
        parts.push(`<div class="pad"><div style="display:flex;justify-content:space-between;margin-bottom:8px"><b>${esc(t("profiling", { t: (s.params || {}).template || "Time Profiler" }))}</b>
          <span class="mono">${esc(t("recorded", { a: Math.floor(secs), b: want }))}</span></div><div class="progress"><i style="width:${(100 * secs) / want}%"></i></div></div>`);
      }
      const start = parseTime(s.started), end = parseTime(s.finished) || new Date();
      const hist = start ? S.metrics.filter(m => m.time * 1000 >= start - 3000 && m.time * 1000 <= +end + 3000) : [];
      if (hist.length > 2) parts.push(`<div class="pad" data-spark="cpu" style="padding-top:${parts.length ? 0 : 16}px"><div class="faint" style="font-size:13px">${esc(t("macDuring"))}</div>
        ${sparkline(hist.map(m => m.cpu_percent), { max: 100, label: t("macDuring") })}<div class="spark-tip">${hist[hist.length - 1].cpu_percent.toFixed(0)}% CPU</div></div>`);
      const watchable = !jref(this.id).host && s.state === "running" && ["launch", "profile", "deploy", "screenshot"].includes(s.kind) && s.target !== "ios";
      box.className = parts.length || watchable ? "panel" : "hidden";
      box.innerHTML = parts.join("") + (watchable && $("#jd-screen").classList.contains("hidden") ? `<div class="pad"><button class="btn" id="jd-watch">${esc(t("watchScreen"))}</button></div>` : "");
      bindSpark(box, { cpu: hist.map(m => ({ v: m.cpu_percent, t: m.time })) }, { cpu: v => v.toFixed(0) + "% CPU" });
      const w = $("#jd-watch");
      if (w) w.onclick = () => { const sc = $("#jd-screen"); sc.classList.remove("hidden"); screenViewer(sc, S.system?.info?.displays); $("[data-play]", sc).click(); w.remove(); };
    },
    async renderSummary(id) {
      try {
        const res = await api(fileUrl(id, "profile-summary.json"));
        const sum = res instanceof Blob ? JSON.parse(await res.text()) : res;
        const box = $("#jd-summary"); if (!box) return;
        box.classList.remove("hidden");
        if (!sum.top.length) { box.innerHTML = `<div class="panel-head"><h2>${esc(t("openSummary"))}</h2></div><div class="empty">${esc(t("idleProfile"))}</div>`; return; }
        const max = sum.top[0].percent || 1;
        box.innerHTML = `<div class="panel-head"><h2>${esc(t("openSummary"))}</h2><span class="faint" style="font-size:13px">${esc(sum.template)} · ${sum.seconds}s</span></div>
          <ul class="bars">${sum.top.slice(0, 15).map(f => `<li title="${esc(f.function)} (${esc(f.binary)}) ${f.ms} ms"><span class="fn">${esc(f.function)}<small>${esc(f.binary)}</small></span>
          <span class="pc">${f.percent.toFixed(1)}%</span><span class="bar"><i style="width:${(100 * f.percent) / max}%"></i></span></li>`).join("")}</ul>`;
      } catch (e) { /* summary is optional */ }
    },
  },

  devices: {
    render(main) {
      main.innerHTML = `<div class="page-head"><div><h1>${esc(t("devices"))}</h1><p>${esc(t("devicesText"))}</p></div></div>
        <h2 style="font-size:17px;margin:0 0 12px">${esc(t("physical"))}</h2><div id="dv-phys" class="dev-grid" style="margin-bottom:28px"></div>
        <section class="panel"><div class="panel-head"><h2>${esc(t("sims"))}</h2></div><div class="table-wrap" id="dv-sims"></div></section>`;
      this.apps = {}; this.showAll = false;
      this.refresh();
    },
    refresh() {
      const el = $("#dv-phys"); if (!el) return;
      el.innerHTML = S.devices.length ? S.devices.map(d => { const watch = /watch/i.test(d.model), apps = this.apps[d.id];
        return `<div class="panel dev"><div class="dev-top">${icon(watch ? "watch" : "phone", 30)}<b>${esc(d.model)}</b><span>${esc(d.name)} · iOS ${esc(d.os)}</span></div>
          ${watch ? "" : `<div class="actions"><button class="btn small" data-shot="${esc(d.id)}">${icon("screenshot", 16)}${esc(t("shot"))}</button>
            <button class="btn small" data-crash="${esc(d.id)}">${esc(t("crashLogs"))}</button>
            ${apps ? "" : `<button class="btn small" data-apps="${esc(d.id)}">${esc(t("loadApps"))}</button>`}</div>
          ${apps ? (apps === "loading" ? `<div class="faint">${esc(t("loading"))}</div>` : typeof apps === "string" ? `<div class="err">${esc(apps)}</div>` :
            `<ul class="apps" aria-label="${esc(t("apps"))}">${apps.map(x => `<li><span class="an">${esc(x.name || x.bundle_id)}<small>${esc(x.bundle_id)} ${esc(x.version || "")}</small></span>
              <span class="actions"><button class="btn small" data-launch="${esc(d.id)}" data-b="${esc(x.bundle_id)}">${esc(t("k.launch"))}</button>
              <button class="btn small" data-prof="${esc(d.id)}" data-b="${esc(x.bundle_id)}">${esc(t("k.profile"))}</button></span></li>`).join("")}</ul>`) : ""}`}</div>`; }).join("")
        : `<div class="panel empty" style="grid-column:1/-1">${esc(t("noDevices"))}</div>`;
      el.querySelectorAll("[data-shot]").forEach(b => b.onclick = () => queueQuick({ kind: "screenshot", target: "ios", device: b.dataset.shot }));
      el.querySelectorAll("[data-crash]").forEach(b => b.onclick = () => queueQuick({ kind: "crashlogs", target: "ios", device: b.dataset.crash }));
      el.querySelectorAll("[data-apps]").forEach(b => b.onclick = async () => { const id = b.dataset.apps; this.apps[id] = "loading"; this.refresh();
        try { this.apps[id] = (await api(`/api/devices/${encodeURIComponent(id)}/apps`)).apps; } catch (e) { this.apps[id] = e.message; } this.refresh(); });
      el.querySelectorAll("[data-launch]").forEach(b => b.onclick = () => openRun({ name: "devices", bundle_id: b.dataset.b, target: "ios", device: b.dataset.launch }, "launch"));
      el.querySelectorAll("[data-prof]").forEach(b => b.onclick = () => openRun({ name: "devices", bundle_id: b.dataset.b, target: "ios", device: b.dataset.prof }, "profile"));
      const sims = [...S.sims].sort((x, y) => (y.state === "Booted") - (x.state === "Booted") || x.runtime.localeCompare(y.runtime) || x.name.localeCompare(y.name));
      const shown = this.showAll ? sims : sims.filter(s => s.state === "Booted" || /^iOS/.test(s.runtime)).slice(0, 12);
      $("#dv-sims").innerHTML = `<table class="data"><tbody>${shown.map(s => `<tr><td>${esc(s.name)}</td><td class="muted">${esc(s.runtime.replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/-/g, " "))}</td>
        <td>${s.state === "Booted" ? `<span class="st-succeeded">● ${esc(t("booted"))}</span>` : `<span class="faint">${esc(t("shutdown"))}</span>`}</td>
        <td class="num">${s.state === "Booted" ? `<button class="btn small" data-sshot="${esc(s.id)}">${esc(t("shot"))}</button>` : ""}</td></tr>`).join("")}</tbody></table>
        ${!this.showAll && sims.length > shown.length ? `<div class="pad"><button class="link" id="dv-all">${esc(t("showAll", { n: sims.length }))}</button></div>` : ""}`;
      $("#dv-sims").querySelectorAll("[data-sshot]").forEach(b => b.onclick = () => queueQuick({ kind: "screenshot", target: "ios-sim", device: b.dataset.sshot }));
      const all = $("#dv-all"); if (all) all.onclick = () => { this.showAll = true; this.refresh(); };
    },
  },

  mac: {
    render(main) {
      main.innerHTML = `<div class="page-head"><div><h1>${esc(t("macTitle"))}</h1><p>${esc(t("macText"))}</p></div></div>
        <div class="stack"><section class="panel" id="mac-vitals"></section>
        <div class="grid cols-2"><section class="panel" id="mac-screen"></section><section class="panel"><div class="panel-head"><h2>${esc(t("topProcs"))}</h2></div><div class="table-wrap" id="mac-top"></div></section></div>
        <div class="grid cols-2"><section class="panel"><div class="panel-head"><h2>${esc(t("settings"))}</h2></div><div id="mac-checks"></div></section>
        <div class="stack"><section class="panel"><div class="panel-head"><h2>${esc(t("hardware"))}</h2></div><div class="pad" id="mac-hw"></div></section>
        <section class="panel"><div class="panel-head"><h2>${esc(t("tools"))}</h2></div><div class="pad" id="mac-tools"></div></section></div></div></div>`;
      screenViewer($("#mac-screen"), S.system?.info?.displays);
      if (!S.system) pollSystem().then(() => { this.renderStatic(); const sc = $("#mac-screen"); if (sc && !$("img", sc)) screenViewer(sc, S.system?.info?.displays); });
      this.renderStatic(); this.refresh();
    },
    renderStatic() {
      const sys = S.system; if (!sys || !$("#mac-hw")) return;
      const i = sys.info, s = sys.settings;
      $("#mac-hw").innerHTML = `<dl class="facts"><dt>Model</dt><dd>${esc(i.model)} (${esc(i.model_id)})</dd><dt>Chip</dt><dd>${esc(i.chip)}${i.cores ? `, ${esc(t("cores", { n: i.cores.total, p: i.cores.performance, e: i.cores.efficiency }))}` : ""}</dd>
        <dt>${esc(t("memory"))}</dt><dd>${esc(i.memory)}</dd><dt>macOS</dt><dd>${esc(i.macos)} (${esc(i.macos_build)})</dd>
        <dt>Name</dt><dd>${esc(i.computer_name)} · ${esc(i.hostname)}</dd><dt>IP</dt><dd class="mono">${esc(Object.entries(i.ip).map(([k, v]) => `${v} (${k})`).join(", "))}</dd>
        ${i.displays.map((d, n) => `<dt>${esc(t("display"))} ${n + 1}</dt><dd>${esc(d.name)} · ${esc(d.resolution)}</dd>`).join("")}</dl>`;
      $("#mac-tools").innerHTML = `<dl class="facts"><dt>Xcode</dt><dd>${esc(i.xcode_version)}<br><span class="faint mono">${esc(i.xcode_selected)}</span></dd>
        ${i.xcodes.length > 1 ? `<dt></dt><dd>${esc(i.xcodes.map(x => `${x.version} (${x.path})`).join(", "))}</dd>` : ""}
        <dt>Simulators</dt><dd>${esc(i.simulator_runtimes.join(", "))}</dd>
        <dt>Unity</dt><dd>${i.unity.length ? i.unity.map(u => `${esc(u.version)} <span class="faint">(${esc(u.modules.map(m => m.replace(/Support|Player|Standalone/g, "")).join(", "))})</span>`).join("<br>") : esc(t("none"))}</dd></dl>`;
      const sl = s.sleep_minutes, sig = s.signing;
      const rows = [
        ["signing", sig.identities.length && sig.provisioning_profiles ? "ok" : "warn", String(sig.identities.length), (sig.identities.length && sig.provisioning_profiles ? "" : t("h.signing") + " ") + sig.identities.join(", ")],
        ["profiles", sig.provisioning_profiles ? "ok" : "warn", String(sig.provisioning_profiles), sig.provisioning_profiles ? "" : t("h.profiles")],
        ["devid", sig.developer_id ? "ok" : "info", sig.developer_id ? t("yes") : t("no"), sig.developer_id ? "" : t("h.devid")],
        ["asc", s.devkit.asc_api_key ? "ok" : "info", s.devkit.asc_api_key ? t("yes") : t("no"), s.devkit.asc_api_key ? "" : t("h.asc")],
        ["notary", s.devkit.notary_profile ? "ok" : "info", s.devkit.notary_profile ? t("yes") : t("no"), s.devkit.notary_profile ? "" : t("h.notary")],
        ["devmode", s.developer_mode ? "ok" : "warn", s.developer_mode ? t("on") : t("off"), ""],
        ["sleep", "ok", sl ? t("minutes", { n: sl }) : t("never"), sl ? t("h.sleep", { n: sl }) : ""],
        ["capture", s.screen_capture ? "ok" : "warn", s.screen_capture ? t("yes") : t("no"), s.screen_capture ? "" : t("h.capture")],
        ["firewall", "info", s.firewall, ""], ["filevault", "info", s.filevault, ""],
        ["ssh", "info", s.remote_login ? t("on") : t("off"), t("h.ssh")], ["tailscale", "info", s.tailscale ? t("on") : t("off"), ""],
      ];
      $("#mac-checks").innerHTML = `<ul class="checks">${rows.map(([k, lvl, v, h]) => `<li class="${lvl}"><span class="ic">${lvl === "ok" ? "✓" : lvl === "warn" ? "!" : "i"}</span>
        <span class="t">${esc(t("c." + k))}</span><span class="v">${esc(v)}</span>${h ? `<span class="h">${esc(h)}</span>` : ""}</li>`).join("")}</ul>`;
    },
    refresh() {
      const v = $("#mac-vitals"); if (!v) return;
      v.innerHTML = vitalsHtml(S.metrics); bindVitals(v, S.metrics);
      const m = S.metrics[S.metrics.length - 1];
      $("#mac-top").innerHTML = m ? `<table class="data"><thead><tr><th>${esc(t("proc"))}</th><th class="num">CPU</th><th class="num">${esc(t("memory"))}</th></tr></thead>
        <tbody>${m.top.map(p => `<tr><td>${esc(p.name)} <span class="faint mono">${p.pid}</span></td><td class="num">${p.cpu.toFixed(1)}%</td><td class="num">${fmtBytes(p.memory)}</td></tr>`).join("")}</tbody></table>` : "";
    },
  },

  hosts: {
    render(main) {
      main.innerHTML = `<div class="page-head"><div><h1>${esc(t("nav.hosts"))}</h1><p>${esc(t("hostsText"))}</p></div>
        <div class="actions">${isAdmin() ? `<button class="btn primary" id="add-host">${esc(t("connectHost"))}</button>` : ""}</div></div><div id="hosts-grid" class="dev-grid"></div>`;
      const add = $("#add-host"); if (add) add.onclick = openConnectHost;
      this.refresh();
    },
    refresh() {
      const el = $("#hosts-grid"); if (!el) return;
      el.innerHTML = S.hosts.map(h => { const r = h.running;
        return `<div class="panel dev"><div class="dev-top">${icon(h.platform === "macos" ? "mac" : "hosts", 30)}<b>${esc(h.name)}</b>
            <span><i class="dot ${h.online ? "on" : "off"}"></i> ${esc(h.online ? t("online") : t("offline"))} · ${esc(t("platformName." + h.platform) || "?")}${h.self ? " · " + esc(t("thisHost")) : ""}</span></div>
          ${h.online ? `<dl class="facts">${h.chip ? `<dt>Chip</dt><dd>${esc(h.chip)}</dd>` : ""}${h.xcode ? `<dt>Xcode</dt><dd>${esc(h.xcode.replace(/ Build version.*/, ""))}</dd>` : ""}
            <dt>${esc(t("nav.jobs"))}</dt><dd>${r ? `<a href="#/jobs/${esc(r.id)}${h.self ? "" : "@" + encodeURIComponent(h.name)}">${esc(kname(r.kind) + " " + r.project)}</a> · ` : esc(t("idleHost")) + " · "}${esc((h.queue_len || 0) - (r ? 1 : 0) > 0 ? t("waitingN", { n: (h.queue_len || 0) - (r ? 1 : 0) }) : t("nothingWaiting"))}</dd></dl>`
            : `<div class="err" style="font-size:14px">${esc(h.error || "")}</div>`}
          <div class="actions">${h.self ? `<a class="btn small" href="#/mac">${esc(t("nav.mac"))}</a>` : `<a class="btn small" href="#/jobs" data-hostjobs="${esc(h.name)}">${esc(t("nav.jobs"))}</a>
            ${h.url ? `<a class="btn small" href="${esc(h.url)}" target="_blank" rel="noopener">${esc(t("openUi"))}</a>` : ""}
            ${isAdmin() ? `<button class="btn small danger" data-rm="${esc(h.name)}">${esc(t("removeHost"))}</button>` : ""}`}</div></div>`; }).join("");
      el.querySelectorAll("[data-hostjobs]").forEach(a => a.onclick = () => { PAGES.jobs.f.host = a.dataset.hostjobs; PAGES.jobs.remote = []; });
      el.querySelectorAll("[data-rm]").forEach(b => b.onclick = async () => { if (!confirm(t("confirmRemoveHost", { n: b.dataset.rm }))) return;
        await api("/api/hosts/" + encodeURIComponent(b.dataset.rm), { method: "DELETE" }); await pollHosts(); this.refresh(); });
    },
  },

  activity: {
    render(main) {
      main.innerHTML = `<div class="page-head"><div><h1>${esc(t("activity"))}</h1><p>${esc(t("activityText"))}</p></div></div>
        <div class="grid cols-main"><section class="panel"><div class="panel-head"><h2>${esc(t("feed"))}</h2></div><div id="act-feed"></div></section>
        <section class="panel"><div class="panel-head"><h2>${esc(t("everyone"))}</h2></div><div id="act-agents"></div></section></div>`;
      this.refresh();
    },
    refresh() { const f = $("#act-feed"); if (!f) return; f.innerHTML = feedHtml(S.feed); $("#act-agents").innerHTML = agentsHtml(S.clients, true); },
  },

  settings: {
    render(main) {
      const origin = location.origin;
      const theme = store.get("devkit.theme") || "auto";
      main.innerHTML = `<div class="page-head"><div><h1>${esc(t("settingsTitle"))}</h1></div></div>
        <div class="grid cols-2" style="align-items:start"><section class="panel"><div class="pad stack">
          <div class="field"><label for="s-lang">${esc(t("language"))}</label><select id="s-lang"><option value="en">English</option><option value="de">Deutsch</option></select></div>
          <div class="field"><label for="s-theme">${esc(t("theme"))}</label><select id="s-theme"><option value="auto">${esc(t("themeAuto"))}</option><option value="light">${esc(t("themeLight"))}</option><option value="dark">${esc(t("themeDark"))}</option></select></div>
          <div><button class="btn danger" id="s-forget">${esc(t("forget"))}</button></div></div></section>
        <section class="panel"><div class="panel-head"><h2>${esc(t("agentsSetup"))}</h2></div><div class="pad stack"><p class="muted" style="margin:0">${esc(t("agentsSetupText"))}</p>
          <pre class="code">${esc(JSON.stringify({ mcpServers: { devkit: { type: "http", url: origin + "/mcp", headers: { Authorization: "Bearer <token>" } } } }, null, 2))}</pre>
          <b>${esc(t("api"))}</b><pre class="code">GET  ${esc(origin)}/api/ping | kinds | projects | devices | simulators | system
GET  ${esc(origin)}/api/jobs?limit=N
POST ${esc(origin)}/api/jobs  {"project","commit","kind","target","device","params"}
GET  ${esc(origin)}/api/jobs/&lt;id&gt; | /log?tail=N | /artifacts
POST ${esc(origin)}/api/jobs/&lt;id&gt;/cancel
GET  ${esc(origin)}/api/hosts | /api/hosts/&lt;name&gt;/&lt;any path above&gt;</pre></div></section></div>
        ${isAdmin() ? `<section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>${esc(t("tokens"))}</h2></div><button class="btn primary small" id="new-token">${esc(t("newToken"))}</button></div>
          <p class="muted pad" style="margin:0;padding-bottom:0">${esc(t("tokensText"))}</p><div class="table-wrap" id="tok-table"></div></section>` : ""}`;
      $("#s-lang").value = lang; $("#s-theme").value = theme;
      $("#s-lang").onchange = e => { lang = e.target.value; store.set("devkit.lang", lang); document.documentElement.lang = lang; render(); };
      $("#s-theme").onchange = e => { store.set("devkit.theme", e.target.value); applyTheme(); };
      $("#s-forget").onclick = () => { token = ""; store.set("devkit.token", null); showConnect(); };
      if (isAdmin()) { $("#new-token").onclick = openNewToken; loadTokens().then(() => this.drawTokens()); }
    },
    drawTokens() {
      const el = $("#tok-table"); if (!el) return;
      el.innerHTML = `<table class="data"><thead><tr><th>${esc(t("tokenName"))}</th><th>${esc(t("role"))}</th><th>${esc(t("created"))}</th><th>${esc(t("lastUsed"))}</th><th></th></tr></thead><tbody>
        ${S.tokens.map(k => `<tr><td>${esc(k.name)}${S.me && k.name === S.me.name ? ` <span class="faint">(${esc(t("you"))})</span>` : ""}</td><td>${esc(t("roleShort." + k.role))}</td>
          <td>${k.builtin ? `<span class="faint">${esc(t("ownerToken"))}</span>` : esc(fmtAgo(k.created * 1000))}${k.created_by ? ` <span class="faint">· ${esc(k.created_by)}</span>` : ""}</td>
          <td>${k.last_used ? esc(fmtAgo(k.last_used * 1000)) : "–"}</td>
          <td class="num">${k.builtin ? "" : `<button class="btn small danger" data-revoke="${esc(k.id)}" data-n="${esc(k.name)}">${esc(t("revoke"))}</button>`}</td></tr>`).join("")}</tbody></table>`;
      el.querySelectorAll("[data-revoke]").forEach(b => b.onclick = async () => { if (!confirm(t("confirmRevoke", { n: b.dataset.n }))) return;
        await api("/api/tokens/" + encodeURIComponent(b.dataset.revoke), { method: "DELETE" }); await loadTokens(); this.drawTokens(); });
    },
  },
};

/* ---------------------------------------------------------------- log rendering */
function colorLog(text, find) {
  const needle = (find || "").toLowerCase();
  return text.split("\n").map(line => {
    let e = esc(line);
    if (needle && line.toLowerCase().includes(needle)) {
      const re = new RegExp(esc(find).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"); e = e.replace(re, m => `<mark>${m}</mark>`);
    }
    if (line.startsWith("$ ")) return `<span class="c">${e}</span>`;
    if (line.startsWith("DEVKIT error") || /\berror[:\]]/i.test(line) || /\*\* \w+ FAILED \*\*/.test(line)) return `<span class="e">${e}</span>`;
    if (/\*\* \w+ SUCCEEDED \*\*/.test(line)) return `<span class="g">${e}</span>`;
    if (/\bwarning:/i.test(line)) return `<span class="w">${e}</span>`;
    if (line.startsWith("DEVKIT")) return `<span class="d">${e}</span>`;
    return e;
  }).join("\n");
}

/* ---------------------------------------------------------------- artifacts */
const fileUrl = (ref, path) => { const J = jref(ref); return `${J.base}/jobs/${J.id}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`; };
const blobCache = {};
async function artifactUrl(id, path) { const k = id + "/" + path; if (!blobCache[k]) blobCache[k] = URL.createObjectURL(await api(fileUrl(id, path))); return blobCache[k]; }
async function download(id, path) {
  const u = URL.createObjectURL(await api(fileUrl(id, path))), a = document.createElement("a");
  a.href = u; a.download = path.split("/").pop(); a.click(); setTimeout(() => URL.revokeObjectURL(u), 1000);
}

/* ---------------------------------------------------------------- dialogs */
const dlg = $("#dlg");
function field(name, label, html, opts = {}) {
  return `<div class="field ${opts.full ? "full" : ""} ${opts.check ? "check" : ""}">${opts.check ? html : `<label for="f-${name}">${esc(label)}</label>${html}`}${opts.hint ? `<div class="hint">${esc(opts.hint)}</div>` : ""}</div>`;
}
const input = (name, value, attrs = "") => `<input id="f-${name}" name="${name}" value="${esc(value ?? "")}" spellcheck="false" ${attrs}>`;
const select = (name, options, value) => `<select id="f-${name}" name="${name}">${options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(value ?? "") ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
function deviceOptions(target, opts = {}) {
  const generic = opts.generic ? [["", t("anyDevice")]] : [];
  if (target === "ios") return generic.concat(S.devices.filter(d => !/watch/i.test(d.model)).map(d => [d.id, `${d.model} · iOS ${d.os}`]));
  if (target === "ios-sim") return S.sims.filter(s => /^iOS/.test(s.runtime)).sort((a, b) => (b.state === "Booted") - (a.state === "Booted"))
    .map(s => [s.id, `${s.name} · ${s.runtime.replace(/^iOS-/, "iOS ").replace(/-/g, ".")}${s.state === "Booted" ? " ●" : ""}`]);
  return [];
}
function openDialog(html, onSubmit, onReady) {
  dlg.innerHTML = `<form method="dialog" novalidate>${html}</form>`;
  const form = $("form", dlg);
  form.onsubmit = async e => { e.preventDefault(); if (!form.reportValidity()) return; const err = $(".dlg-err", dlg); err.textContent = "";
    try { await onSubmit(form); dlg.close(); } catch (x) { err.textContent = x.message; } };
  $("[data-close]", dlg).onclick = () => dlg.close();
  onReady && onReady(form);
  dlg.showModal();
}
const foot = label => `<div class="dlg-foot"><span class="dlg-err err" role="alert"></span><div class="actions"><button type="button" class="btn" data-close>${esc(t("close"))}</button><button class="btn primary">${esc(label)}</button></div></div>`;

/* What each project action asks for and how it maps onto a job. */
const RUN = {
  build:      { kind: "build", targets: ["ios", "ios-sim", "macos"], fields: ["ref", "target", "device", "configuration"], generic: true },
  install:    { kind: "deploy", targets: ["ios", "ios-sim", "macos"], fields: ["ref", "target", "device", "launch_args", "duration"], extra: { launch: true } },
  launch:     { kind: "launch", targets: ["ios", "ios-sim"], fields: ["target", "device", "launch_args", "duration"], noRepo: true },
  profile:    { kind: "profile", targets: ["ios", "ios-sim", "macos"], fields: ["target", "device", "template", "duration", "launch_args"], noRepo: true },
  test:       { kind: "test", targets: ["ios-sim", "macos", "ios"], fields: ["ref", "target", "device"] },
  screenshot: { kind: "screenshot", targets: ["ios", "ios-sim"], fields: ["target", "device"], noRepo: true },
  archive:    { kind: "archive", targets: ["ios", "macos"], fields: ["ref", "target", "export_method"] },
  release:    { kind: "release", targets: ["ios", "macos"], fields: ["ref", "target"] },
  unity:      { kind: "unity", targets: [], fields: ["ref"] },
  shell:      { kind: "shell", targets: [], fields: ["ref", "args"] },
};
function openRun(p, action) {
  const spec = RUN[action], last = JSON.parse(store.get("devkit.run." + p.name + "." + action) || "{}");
  const v = k => last[k] ?? { ref: p.ref || "main", target: p.target || spec.targets[0], device: p.device, duration: action === "profile" ? 30 : 60, template: "Time Profiler" }[k];
  const target0 = spec.targets.includes(v("target")) ? v("target") : spec.targets[0];
  const hostField = () => { const o = hostOptions(target0); return o.length ? field("host", t("runOn"), select("host", o, last.host ?? "auto")) : ""; };
  const fieldsHtml = () => hostField() + spec.fields.map(f => ({
    ref: () => field("ref", t("branch"), input("ref", v("ref"), 'required pattern="[A-Za-z0-9._/\\-]+"')),
    target: () => field("target", t("target"), select("target", spec.targets.map(x => [x, tname(x)]), target0)),
    device: () => field("device", t("device"), select("device", deviceOptions(target0, { generic: spec.generic }), v("device"))),
    configuration: () => field("configuration", t("configuration"), select("configuration", [["", t("defaultCfg")], ["Debug", "Debug"], ["Release", "Release"]], v("configuration"))),
    launch_args: () => field("launch_args", t("launchArgs"), input("launch_args", joinArgs(v("launch_args")), 'placeholder="-mute -autoplay"'), { full: true }),
    duration: () => field("duration", t("duration"), input("duration", v("duration"), 'type="number" min="1" max="3600"')),
    template: () => field("template", t("template"), select("template", TEMPLATES.map(x => [x, x]), v("template"))),
    export_method: () => field("export_method", t("exportAs"), select("export_method", [["", t("noExport")], ["development", "development"], ["release-testing", "release-testing"], ["app-store-connect", "app-store-connect"], ["developer-id", "developer-id"]], v("export_method"))),
    args: () => field("args", t("command"), `<textarea id="f-args" name="args" spellcheck="false" required>${esc(v("args") || "")}</textarea>`, { full: true }),
  }[f]())).join("");
  openDialog(`<div class="dlg-head"><h2>${esc(t("runTitle", { a: t("a." + action)[0], p: p.name }))}</h2><p>${esc(t("a." + action)[1])}</p></div>
    <div class="dlg-body">${fieldsHtml()}</div>${foot(t("run"))}`, async form => {
    const val = k => (form.elements[k] ? form.elements[k].value.trim() : "");
    const target = val("target") || undefined, params = { ...(spec.extra || {}) };
    if (p.xcode) params[p.xcode.endsWith(".xcworkspace") ? "workspace" : "project"] = p.xcode;
    ["scheme", "team_id", "bundle_id"].forEach(k => p[k] && (params[k] = p[k]));
    if (action === "unity") { params.build_target = p.unity_build_target || "iOS"; params.method = p.unity_method || ""; }
    if (val("configuration")) params.configuration = val("configuration");
    if (val("export_method")) params.export_method = val("export_method");
    if (val("template")) params.template = val("template");
    if (val("duration")) params.duration = Number(val("duration"));
    if (form.elements.launch_args) params.launch_args = splitArgs(val("launch_args"));
    const body = { project: p.name, kind: spec.kind, commit: spec.noRepo ? "none" : val("ref"), target, device: val("device") || undefined,
      repo: spec.noRepo ? undefined : p.repo, args: val("args") || undefined, params };
    const remember = {}; [...form.elements].forEach(el => el.name && (remember[el.name] = el.name === "launch_args" ? splitArgs(el.value) : el.value));
    store.set("devkit.run." + p.name + "." + action, JSON.stringify(remember));
    if (val("host")) body.host = val("host");
    const r = await post("/api/jobs", body);
    toast(t("queued", { k: t("a." + action)[0] }) + (r.host && r.host !== S.me.host ? " → " + r.host : "")); await pollCore(); location.hash = jobHash(r);
  }, form => {
    const tg = form.elements.target;
    if (tg && form.elements.host) tg.addEventListener("change", () => { form.elements.host.innerHTML = hostOptions(tg.value).map(([a, b]) => `<option value="${esc(a)}">${esc(b)}</option>`).join(""); });
    if (tg && form.elements.device) tg.onchange = () => { const sel = form.elements.device; sel.innerHTML = deviceOptions(tg.value, { generic: spec.generic }).map(([a, b]) => `<option value="${esc(a)}">${esc(b)}</option>`).join("");
      sel.closest(".field").classList.toggle("hidden", tg.value === "macos"); };
    if (tg && form.elements.device) form.elements.device.closest(".field").classList.toggle("hidden", tg.value === "macos");
  });
}
async function queueQuick(body) {
  const r = await post("/api/jobs", { project: "devices", commit: "none", ...body });
  toast(t("queued", { k: kname(body.kind) })); await pollCore(); location.hash = jobHash(r);
}
async function rerun(s, host) {
  const body = { project: s.project, repo: s.repo || undefined, commit: s.commit, kind: s.kind, target: s.target || undefined,
    device: s.device || undefined, args: s.args || undefined, params: s.params || undefined, host: host || undefined };
  const r = await post("/api/jobs", body); toast(t("queued", { k: kname(s.kind) })); await pollCore(); location.hash = jobHash(r);
}
function openProject(p) {
  const v = k => (p ? p[k] : "") || "";
  openDialog(`<div class="dlg-head"><h2>${esc(p ? p.name : t("newProject"))}</h2></div><div class="dlg-body">
      ${field("name", t("pName"), input("name", v("name"), 'required pattern="[A-Za-z0-9._\\-]+"'))}
      ${field("ref", t("pRef"), input("ref", v("ref") || "main"), { hint: t("pRefHint") })}
      ${field("repo", t("pRepo"), input("repo", v("repo"), 'placeholder="https://github.com/you/game.git"'), { full: true })}
      ${field("xcode", t("pXcode"), input("xcode", v("xcode"), 'placeholder="ios/Game.xcodeproj"'), { hint: t("pXcodeHint") })}
      ${field("scheme", t("scheme"), input("scheme", v("scheme")))}
      ${field("bundle_id", t("pBundle"), input("bundle_id", v("bundle_id"), 'placeholder="com.example.game"'))}
      ${field("team_id", t("pTeam"), input("team_id", v("team_id")))}
      ${field("target", t("pTarget"), select("target", [["ios", tname("ios")], ["ios-sim", tname("ios-sim")], ["macos", tname("macos")]], v("target") || "ios"))}
      ${field("device", t("pDevice"), select("device", [["", "–"]].concat(deviceOptions("ios"), deviceOptions("ios-sim")), v("device")))}
      ${field("unity_build_target", t("pUnityTarget"), select("unity_build_target", [["", "–"], ["iOS", "iOS"], ["OSXUniversal", "macOS"], ["Android", "Android"], ["WebGL", "WebGL"]], v("unity_build_target")))}
      ${field("unity_method", t("pUnityMethod"), input("unity_method", v("unity_method"), 'placeholder="BuildScript.BuildiOS"'))}
      ${field("notes", t("pNotes"), `<textarea id="f-notes" name="notes">${esc(v("notes"))}</textarea>`, { full: true })}
    </div>${foot(p ? t("save") : t("create"))}`, async form => {
    const proj = {}; [...form.elements].forEach(el => el.name && (proj[el.name] = el.value.trim()));
    const r = await post("/api/projects", { project: proj, previous: p ? p.name : undefined });
    await loadProjects(); toast(t("saved")); location.hash = "#/projects/" + encodeURIComponent(r.project.name); render();
  });
}
function openNewToken() {
  openDialog(`<div class="dlg-head"><h2>${esc(t("newToken"))}</h2></div><div class="dlg-body">
      ${field("name", t("tokenName"), input("name", "", 'required maxlength="60"'), { full: true, hint: t("tokenNameHint") })}
      <div class="field full"><label>${esc(t("role"))}</label>${["operator", "viewer", "admin"].map((r, i) => `<label style="display:flex;gap:8px;font-weight:400;margin:6px 0">
        <input type="radio" name="role" value="${r}" ${i === 0 ? "checked" : ""} style="width:auto"> ${esc(t("roles." + r))}</label>`).join("")}</div>
    </div>${foot(t("newToken"))}`, async form => {
    const r = await post("/api/tokens", { name: form.elements.name.value, role: form.elements.role.value });
    await loadTokens(); PAGES.settings.drawTokens();
    setTimeout(() => showSecret(r.name, r.token), 50);
  });
}
function showSecret(name, secret) {
  dlg.innerHTML = `<form method="dialog"><div class="dlg-head"><h2>${esc(name)}</h2><p>${esc(t("tokenOnce"))}</p></div>
    <div class="dlg-body"><pre class="code full" id="secret">${esc(secret)}</pre></div>
    <div class="dlg-foot"><span></span><div class="actions"><button type="button" class="btn" id="copy-secret">${esc(t("copy"))}</button><button class="btn primary">${esc(t("done"))}</button></div></div></form>`;
  $("#copy-secret").onclick = async () => { try { await navigator.clipboard.writeText(secret); $("#copy-secret").textContent = t("copied"); }
    catch (e) { const r = document.createRange(); r.selectNodeContents($("#secret")); getSelection().removeAllRanges(); getSelection().addRange(r); } };
  dlg.showModal();
  /* The previous dialog's close event can arrive after this one opened; only clear the secret on a real close. */
  dlg.addEventListener("close", function clear() { if (dlg.open) return; dlg.innerHTML = ""; dlg.removeEventListener("close", clear); });
}
function openConnectHost() {
  openDialog(`<div class="dlg-head"><h2>${esc(t("connectHost"))}</h2><p>${esc(t("connectHostText"))}</p></div><div class="dlg-body">
      ${field("url", t("hostUrl"), input("url", "", 'required placeholder="http://192.168.1.50:7420"'), { full: true })}
      ${field("token", t("hostToken"), '<input id="f-token" name="token" type="password" autocomplete="off" required>', { full: true })}
    </div>${foot(t("connectBtn"))}`, async form => {
    const r = await post("/api/hosts", { url: form.elements.url.value, token: form.elements.token.value.trim() });
    toast(r.name); await pollHosts(); PAGES.hosts.refresh();
  });
}
function openCustom() {
  const kinds = Object.keys(S.kinds);
  openDialog(`<div class="dlg-head"><h2>${esc(t("customJob"))}</h2></div><div class="dlg-body">
      ${field("kind", t("kind"), select("kind", kinds.map(k => [k, kname(k)]), "shell"))}
      ${S.hosts.length > 1 ? field("host", t("runOn"), select("host", [["", S.me.host + " · " + t("thisHost")]].concat(S.hosts.filter(h => !h.self && h.online).map(h => [h.name, h.name + " · " + h.platform]), [["auto", t("autoHost")]]), "")) : ""}
      ${field("project", t("projectName"), input("project", "", 'required pattern="[A-Za-z0-9._\\-]+"'))}
      ${field("repo", t("pRepo"), input("repo", ""), { full: true })}
      ${field("commit", t("branch"), input("commit", "none", 'required'))}
      ${field("target", t("target"), select("target", [["", "–"], ["ios", tname("ios")], ["ios-sim", tname("ios-sim")], ["macos", tname("macos")]], ""))}
      ${field("device", t("device"), select("device", [["", "–"]].concat(deviceOptions("ios"), deviceOptions("ios-sim")), ""), { full: true })}
      ${field("args", t("command"), `<textarea id="f-args" name="args" spellcheck="false"></textarea>`, { full: true })}
      ${field("params", t("params"), `<textarea id="f-params" name="params" spellcheck="false" placeholder='{"scheme": "Game"}'></textarea>`, { full: true, hint: "" })}
      <p class="full faint" id="kind-doc" style="margin:0;font-size:13px;white-space:pre-wrap"></p>
    </div>${foot(t("run"))}`, async form => {
    const body = {}; ["kind", "project", "repo", "commit", "target", "device", "args"].forEach(k => form.elements[k].value.trim() && (body[k] = form.elements[k].value.trim()));
    if (form.elements.params.value.trim()) { try { body.params = JSON.parse(form.elements.params.value); } catch (e) { throw new Error(t("badJson")); }
      if (typeof body.params !== "object" || Array.isArray(body.params)) throw new Error(t("badJson")); }
    if (form.elements.host && form.elements.host.value) body.host = form.elements.host.value;
    const r = await post("/api/jobs", body); toast(t("queued", { k: kname(body.kind) })); await pollCore(); location.hash = jobHash(r);
  }, form => { const show = () => { $("#kind-doc").textContent = S.kinds[form.elements.kind.value] || ""; }; form.elements.kind.onchange = show; show(); });
}

/* ---------------------------------------------------------------- boot */
function applyTheme() { const th = store.get("devkit.theme") || "auto"; th === "auto" ? document.documentElement.removeAttribute("data-theme") : document.documentElement.setAttribute("data-theme", th); }
function render() {
  const r = route(), main = $("#main");
  page = PAGES[r.page] || PAGES.overview;
  if (r.page === "jobs" && r.arg) page = PAGES.job;
  if (r.page === "projects" && r.arg) page = PAGES.project;
  renderChrome();
  page.render(main, r.arg);
  main.focus({ preventScroll: true });
}
function showConnect(msg) {
  $("#frame").classList.add("hidden"); $("#connect").classList.remove("hidden");
  $("#connect-err").textContent = msg || ""; $("#token-input").focus();
}
$("#connect-form").onsubmit = async e => {
  e.preventDefault(); token = $("#token-input").value.trim();
  try { await api("/api/ping"); store.set("devkit.token", token); start(); } catch (err) { $("#connect-err").textContent = err.message; }
};
let timers = [];
async function start() {
  $("#connect").classList.add("hidden"); $("#frame").classList.remove("hidden");
  document.querySelectorAll("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
  try { S.kinds = (await api("/api/kinds")).kinds; } catch (e) { if (e instanceof AuthError) return showConnect(e.message); }
  try { S.me = await api("/api/me"); } catch (e) { if (e instanceof AuthError) return showConnect(e.message); }
  await Promise.all([pollCore(), pollMetrics(), loadProjects(), pollDevices(), pollHosts()]);
  render(); pollSystem().then(() => { if (route().page === "mac") PAGES.mac.renderStatic(); });
  timers.forEach(clearInterval);
  timers = [setInterval(pollCore, POLL_MS), setInterval(pollHosts, POLL_MS * 2.5), setInterval(() => pollMetrics(), POLL_MS * 2), setInterval(pollDevices, DEVICE_POLL_MS),
    setInterval(() => pollSystem().then(() => route().page === "mac" && PAGES.mac.renderStatic()), SYSTEM_POLL_MS)];
}
window.addEventListener("hashchange", () => { if (!$("#frame").classList.contains("hidden")) render(); });
applyTheme();
document.documentElement.lang = lang;
document.querySelectorAll("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
token ? start() : showConnect();
