// Devkit.app: a menu bar app that runs the devkit server (bundled Python, /usr/bin/python3) as its child process.
// Running the server from a signed app makes macOS attribute screen recording and other privacy prompts to "Devkit"
// instead of python3, and lets the app register itself as a login item.
import AppKit
import CoreGraphics
import ServiceManagement

enum Const {
    static let python = "/usr/bin/python3"
    static let pollInterval: TimeInterval = 3
    static let restartDelays: [TimeInterval] = [1, 2, 5, 10, 30]
    static let stableRunSeconds: TimeInterval = 60   // a run this long resets the restart backoff
    static let defaultPort = 7420
}

/// Localized UI strings (English and German).
enum L {
    static let german = Locale.preferredLanguages.first?.hasPrefix("de") ?? false
    static func s(_ en: String, _ de: String) -> String { german ? de : en }
    static let starting = s("Starting…", "Startet…")
    static let stopped = s("Server stopped", "Server gestoppt")
    static let idle = s("Idle", "Bereit")
    static func waiting(_ n: Int) -> String { s("\(n) waiting", "\(n) wartend") }
    static let open = s("Open Devkit", "Devkit öffnen")
    static let copyAddress = s("Copy Address", "Adresse kopieren")
    static let copyToken = s("Copy Owner Token", "Besitzer-Token kopieren")
    static let loginItem = s("Start at Login", "Bei Anmeldung starten")
    static let screen = s("Allow Screen Viewing…", "Bildschirmansicht erlauben…")
    static let screenOK = s("Screen Viewing Allowed", "Bildschirmansicht erlaubt")
    static let restart = s("Restart Server", "Server neu starten")
    static let log = s("Show Server Log", "Server-Log anzeigen")
    static let data = s("Show Data Folder", "Datenordner anzeigen")
    static let quit = s("Quit Devkit", "Devkit beenden")
    static let loginFailed = s("Could not change the login item", "Anmeldeobjekt konnte nicht geändert werden")
}

final class ServerProcess {
    let resources: URL
    let dataDir: URL
    private var process: Process?
    private var startedAt = Date()
    private var failures = 0
    private var stopping = false
    var onExit: (() -> Void)?

    init(resources: URL, dataDir: URL) {
        self.resources = resources
        self.dataDir = dataDir
    }

    var logURL: URL { dataDir.appendingPathComponent("logs/server.log") }
    var isRunning: Bool { process?.isRunning ?? false }

    func start() {
        stopping = false
        let fm = FileManager.default
        try? fm.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !fm.fileExists(atPath: logURL.path) { fm.createFile(atPath: logURL.path, contents: nil) }
        guard let log = try? FileHandle(forWritingTo: logURL) else { NSLog("devkit: cannot open log at \(logURL.path)"); return }
        log.seekToEndOfFile()

        let p = Process()
        p.executableURL = URL(fileURLWithPath: Const.python)
        p.arguments = [resources.appendingPathComponent("devkit/bin/devkit-server").path]
        var env = ProcessInfo.processInfo.environment
        env["DEVKIT_DATA"] = dataDir.path
        env["PYTHONDONTWRITEBYTECODE"] = "1"   // the app bundle is signed and must stay unmodified
        env["DEVKIT_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)  // server exits if the app dies
        p.environment = env
        p.standardOutput = log
        p.standardError = log
        p.terminationHandler = { [weak self] _ in DispatchQueue.main.async { self?.exited() } }
        do {
            try p.run()
            process = p
            startedAt = Date()
        } catch {
            NSLog("devkit: failed to start server: \(error)")
            exited()
        }
    }

    func stop() {
        stopping = true
        process?.terminate()
    }

    func restart() {
        guard let p = process, p.isRunning else { failures = 0; start(); return }
        stopping = true
        p.terminationHandler = { [weak self] _ in DispatchQueue.main.async { self?.failures = 0; self?.start() } }
        p.terminate()
    }

    private func exited() {
        onExit?()
        if stopping { return }
        if Date().timeIntervalSince(startedAt) > Const.stableRunSeconds { failures = 0 }
        let delay = Const.restartDelays[min(failures, Const.restartDelays.count - 1)]
        failures += 1
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self, !self.stopping, !self.isRunning else { return }
            self.start()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var statusItem: NSStatusItem!
    private var server: ServerProcess!
    private var timer: Timer?
    private let statusLine = NSMenuItem(title: L.starting, action: nil, keyEquivalent: "")
    private let detailLine = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    private let loginItem = NSMenuItem(title: L.loginItem, action: #selector(toggleLogin), keyEquivalent: "")
    private let screenItem = NSMenuItem(title: L.screen, action: #selector(requestScreen), keyEquivalent: "")
    private var lastPing: [String: Any]?
    private var signalSources: [DispatchSourceSignal] = []

    private var dataDir: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Devkit")
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        setIcon(running: false)
        statusItem.menu = buildMenu()

        server = ServerProcess(resources: Bundle.main.resourceURL!, dataDir: dataDir)
        server.onExit = { [weak self] in self?.render(nil) }
        server.start()

        // Quit cleanly on SIGTERM/SIGINT (kill, logout) so the server child is stopped too.
        for sig in [SIGTERM, SIGINT] {
            signal(sig, SIG_IGN)
            let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
            src.setEventHandler { NSApp.terminate(nil) }
            src.resume()
            signalSources.append(src)
        }

        timer = Timer.scheduledTimer(withTimeInterval: Const.pollInterval, repeats: true) { [weak self] _ in self?.poll() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in self?.poll() }
    }

    func applicationWillTerminate(_ notification: Notification) {
        server.stop()
    }

    // MARK: menu

    private func buildMenu() -> NSMenu {
        let m = NSMenu()
        m.delegate = self
        statusLine.isEnabled = false
        detailLine.isEnabled = false
        m.addItem(statusLine)
        m.addItem(detailLine)
        m.addItem(.separator())
        m.addItem(item(L.open, #selector(openUI), "o"))
        m.addItem(item(L.copyAddress, #selector(copyAddress), ""))
        m.addItem(item(L.copyToken, #selector(copyToken), ""))
        m.addItem(.separator())
        loginItem.target = self
        m.addItem(loginItem)
        screenItem.target = self
        m.addItem(screenItem)
        m.addItem(.separator())
        m.addItem(item(L.restart, #selector(restartServer), "r"))
        m.addItem(item(L.log, #selector(showLog), "l"))
        m.addItem(item(L.data, #selector(showData), ""))
        m.addItem(.separator())
        m.addItem(item(L.quit, #selector(NSApplication.terminate(_:)), "q", target: NSApp))
        return m
    }

    private func item(_ title: String, _ action: Selector, _ key: String, target: AnyObject? = nil) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
        i.target = target ?? self
        return i
    }

    func menuWillOpen(_ menu: NSMenu) {
        loginItem.state = SMAppService.mainApp.status == .enabled ? .on : .off
        let allowed = CGPreflightScreenCaptureAccess()
        screenItem.title = allowed ? L.screenOK : L.screen
        screenItem.state = allowed ? .on : .off
        poll()
    }

    // MARK: status

    private func config() -> [String: Any]? {
        guard let data = try? Data(contentsOf: dataDir.appendingPathComponent("config.json")) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private var port: Int { (config()?["port"] as? Int) ?? Const.defaultPort }

    private func poll() {
        guard let token = config()?["token"] as? String,
              let url = URL(string: "http://127.0.0.1:\(port)/api/ping") else { render(nil); return }
        var req = URLRequest(url: url, timeoutInterval: 2)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("Devkit menu bar", forHTTPHeaderField: "X-Devkit-Client")
        URLSession.shared.dataTask(with: req) { [weak self] data, _, _ in
            let ping = data.flatMap { (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any] }
            DispatchQueue.main.async { self?.render(ping) }
        }.resume()
    }

    private func render(_ ping: [String: Any]?) {
        lastPing = ping
        guard let ping else {
            statusLine.title = server?.isRunning == true ? L.starting : L.stopped
            detailLine.isHidden = true
            setIcon(running: false)
            return
        }
        let queue = ping["queue_len"] as? Int ?? 0
        if let job = ping["running"] as? [String: Any] {
            let kind = (job["kind"] as? String ?? "").capitalized
            let project = job["project"] as? String ?? ""
            statusLine.title = "\(kind) \(project)"
            detailLine.title = queue > 1 ? L.waiting(queue - 1) : (ping["name"] as? String ?? "")
            setIcon(running: true)
        } else {
            statusLine.title = L.idle
            detailLine.title = queue > 0 ? L.waiting(queue) : (ping["name"] as? String ?? "")
            setIcon(running: false)
        }
        detailLine.isHidden = detailLine.title.isEmpty
    }

    /// Menu bar glyph: the devkit box; its status light fills while a job runs.
    private func setIcon(running: Bool) {
        let size = NSSize(width: 20, height: 16)
        let img = NSImage(size: size, flipped: false) { _ in
            NSColor.black.setStroke()
            NSColor.black.setFill()
            let box = NSBezierPath(roundedRect: NSRect(x: 1.5, y: 4.5, width: 17, height: 8), xRadius: 2, yRadius: 2)
            box.lineWidth = 1.5
            box.stroke()
            NSBezierPath(roundedRect: NSRect(x: 4, y: 1, width: 12, height: 1.4), xRadius: 0.7, yRadius: 0.7).fill()
            let light = NSBezierPath(ovalIn: NSRect(x: 4, y: 7, width: 3, height: 3))
            if running { light.fill() } else { light.lineWidth = 1; light.stroke() }
            NSBezierPath(roundedRect: NSRect(x: 9, y: 8, width: 6.5, height: 1.2), xRadius: 0.6, yRadius: 0.6).fill()
            return true
        }
        img.isTemplate = true
        statusItem.button?.image = img
        statusItem.button?.toolTip = "Devkit"
    }

    // MARK: actions

    private var address: String {
        let host = ProcessInfo.processInfo.hostName
        return "http://\(host):\(port)"
    }

    @objc private func openUI() {
        if let url = URL(string: "http://127.0.0.1:\(port)/") { NSWorkspace.shared.open(url) }
    }

    @objc private func copyAddress() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(address, forType: .string)
    }

    @objc private func copyToken() {
        guard let token = config()?["token"] as? String else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(token, forType: .string)
    }

    @objc private func toggleLogin() {
        do {
            if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() } else { try SMAppService.mainApp.register() }
        } catch {
            let alert = NSAlert()
            alert.messageText = L.loginFailed
            alert.informativeText = error.localizedDescription
            alert.runModal()
        }
    }

    @objc private func requestScreen() {
        if !CGRequestScreenCaptureAccess() {
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    @objc private func restartServer() { server.restart() }
    @objc private func showLog() { NSWorkspace.shared.open(server.logURL) }
    @objc private func showData() { NSWorkspace.shared.activateFileViewerSelecting([dataDir]) }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
