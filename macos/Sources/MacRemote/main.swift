import AppKit
import CSQLite
import Foundation
import SwiftUI

private struct AgentTask: Identifiable {
    let id: String
    let provider: String
    let prompt: String
    let status: String
    let createdAt: String
}

@MainActor
private final class AppModel: ObservableObject {
    @Published var isAgentRunning = false
    @Published var botToken = ""
    @Published var antigravityPath = ""
    @Published var claudePath = ""
    @Published var workingDirectory = FileManager.default.homeDirectoryForCurrentUser.path
    @Published var relayURL = ""
    @Published var relayHostID = ""
    @Published var relayHostToken = ""
    @Published var pairingPin = ""
    @Published var tasks: [AgentTask] = []
    @Published var errorMessage: String?
    @Published var notice: String?

    private let fileManager = FileManager.default
    private let dataDirectory: URL
    private let databaseURL: URL
    private let configURL: URL
    private let logURL: URL
    private let csrfToken = UUID().uuidString
    private var agentProcess: Process?
    private var logHandle: FileHandle?
    private var terminationObserver: NSObjectProtocol?
    private var refreshTask: Task<Void, Never>?
    private var isRefreshing = false
    private var isShuttingDown = false

    init() {
        let support = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        dataDirectory = support.appendingPathComponent("MacRemote", isDirectory: true)
        databaseURL = dataDirectory.appendingPathComponent("pending_tasks.sqlite3")
        configURL = dataDirectory.appendingPathComponent("config.json")
        logURL = dataDirectory.appendingPathComponent("agent.log")
        terminationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.stopAgent()
            }
        }
        loadSettings()
        startAgentIfConfigured()
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(2))
                guard !Task.isCancelled else { break }
                self?.refresh()
            }
        }
    }

    deinit {
        refreshTask?.cancel()
        if let terminationObserver {
            NotificationCenter.default.removeObserver(terminationObserver)
        }
        agentProcess?.terminate()
        try? logHandle?.close()
    }

    func refresh() {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        isAgentRunning = agentProcess?.isRunning ?? false

        do {
            tasks = try TaskStore(databaseURL: databaseURL).list()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveSettings() {
        do {
            try fileManager.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
            var settings = readConfigDictionary()
            settings["bot_token"] = botToken.trimmingCharacters(in: .whitespacesAndNewlines)
            settings["antigravity_bin"] = antigravityPath.trimmingCharacters(in: .whitespacesAndNewlines)
            settings["claude_bin"] = claudePath.trimmingCharacters(in: .whitespacesAndNewlines)
            settings["working_directory"] = workingDirectory.trimmingCharacters(in: .whitespacesAndNewlines)
            settings["relay_url"] = relayURL.trimmingCharacters(in: .whitespacesAndNewlines)
            settings["relay_host_id"] = relayHostID.trimmingCharacters(in: .whitespacesAndNewlines)
            settings["relay_host_token"] = relayHostToken.trimmingCharacters(in: .whitespacesAndNewlines)
            if (settings["pairing_pin"] as? String ?? "").isEmpty {
                settings["pairing_pin"] = String(format: "%04d", Int.random(in: 1000...9999))
            }
            if settings["allowed_user_ids"] == nil {
                settings["allowed_user_ids"] = [Int]()
            }
            if settings["google_drive_path"] == nil {
                settings["google_drive_path"] = NSString(string: "~/Google Drive/My Drive").expandingTildeInPath
            }
            if settings["keep_awake"] == nil {
                settings["keep_awake"] = true
            }
            let data = try JSONSerialization.data(withJSONObject: settings, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: configURL, options: .atomic)
            try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: configURL.path)
            pairingPin = settings["pairing_pin"] as? String ?? ""
            notice = "Settings saved securely on this Mac."
            restartAgent()
        } catch {
            errorMessage = "Could not save settings: \(error.localizedDescription)"
        }
    }

    func approve(_ task: AgentTask) {
        updateTask(task, to: "approved")
    }

    func reject(_ task: AgentTask) {
        updateTask(task, to: "rejected")
    }

    func openActivityLog() {
        do {
            try fileManager.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
            if !fileManager.fileExists(atPath: logURL.path) {
                fileManager.createFile(atPath: logURL.path, contents: nil)
            }
            NSWorkspace.shared.open(logURL)
        } catch {
            errorMessage = "Could not open the activity log: \(error.localizedDescription)"
        }
    }

    func startAgentIfConfigured() {
        guard !botToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !(agentProcess?.isRunning ?? false) else {
            return
        }
        do {
            try fileManager.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
            if !fileManager.fileExists(atPath: logURL.path) {
                fileManager.createFile(atPath: logURL.path, contents: nil)
            }
            let handle = try FileHandle(forWritingTo: logURL)
            try handle.seekToEnd()

            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["python3", agentScriptURL().path]
            process.environment = ProcessInfo.processInfo.environment.merging(
                ["MRA_DATA_DIR": dataDirectory.path],
                uniquingKeysWith: { _, new in new }
            )
            process.standardOutput = handle
            process.standardError = handle
            process.terminationHandler = { [weak self] _ in
                Task { @MainActor in
                    self?.isAgentRunning = false
                }
            }
            try process.run()
            agentProcess = process
            logHandle = handle
            isAgentRunning = true
            notice = "MacRemote is starting. Telegram connection details are in the activity log."
        } catch {
            errorMessage = "Could not start the host agent: \(error.localizedDescription)"
        }
    }

    func stopAgent() {
        isShuttingDown = true
        guard let process = agentProcess, process.isRunning else { return }
        process.terminate()
        process.waitUntilExit()
        agentProcess = nil
        isAgentRunning = false
    }

    private func loadSettings() {
        let settings = readConfigDictionary()
        botToken = settings["bot_token"] as? String ?? ""
        antigravityPath = settings["antigravity_bin"] as? String ?? ""
        claudePath = settings["claude_bin"] as? String ?? ""
        workingDirectory = settings["working_directory"] as? String
            ?? fileManager.homeDirectoryForCurrentUser.path
        relayURL = settings["relay_url"] as? String ?? ""
        relayHostID = settings["relay_host_id"] as? String ?? ""
        relayHostToken = settings["relay_host_token"] as? String ?? ""
        pairingPin = settings["pairing_pin"] as? String ?? ""
    }

    private func readConfigDictionary() -> [String: Any] {
        if let data = try? Data(contentsOf: configURL),
           let dictionary = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            return dictionary
        }
        if let path = ProcessInfo.processInfo.environment["MRA_AGENT_PATH"],
           let data = try? Data(contentsOf: URL(fileURLWithPath: path).deletingLastPathComponent().appendingPathComponent("config.json")),
           let dictionary = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            return dictionary
        }
        return [:]
    }

    private func agentScriptURL() -> URL {
        if let path = ProcessInfo.processInfo.environment["MRA_AGENT_PATH"] {
            return URL(fileURLWithPath: path)
        }
        if let resource = Bundle.main.resourceURL?.appendingPathComponent("agent.py"),
           fileManager.fileExists(atPath: resource.path) {
            return resource
        }
        return URL(fileURLWithPath: fileManager.currentDirectoryPath).appendingPathComponent("agent.py")
    }

    private func updateTask(_ task: AgentTask, to status: String) {
        do {
            let changed = try TaskStore(databaseURL: databaseURL).setStatus(task.id, to: status)
            guard changed else {
                errorMessage = "That task was already handled. The list has been refreshed."
                refresh()
                return
            }
            notice = status == "approved" ? "Task approved. It will run on this Mac." : "Task rejected."
            refresh()
        } catch {
            errorMessage = "Could not update task: \(error.localizedDescription)"
        }
    }

    private func restartAgent() {
        guard let process = agentProcess, process.isRunning else {
            startAgentIfConfigured()
            return
        }
        process.terminationHandler = { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                self.agentProcess = nil
                self.isAgentRunning = false
                guard !self.isShuttingDown else { return }
                self.startAgentIfConfigured()
            }
        }
        process.terminate()
    }
}

private struct TaskStore {
    let databaseURL: URL

    func list() throws -> [AgentTask] {
        var database: OpaquePointer?
        guard sqlite3_open_v2(databaseURL.path, &database, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
            if let database { sqlite3_close(database) }
            return []
        }
        defer { sqlite3_close(database) }

        let sql = """
            SELECT id, provider, prompt, status, created_at
            FROM agent_tasks
            WHERE status IN ('pending', 'approved', 'running', 'completed', 'rejected')
            ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 WHEN 'running' THEN 2 ELSE 3 END,
                     created_at DESC
            LIMIT 40
            """
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else {
            throw databaseError(database)
        }
        defer { sqlite3_finalize(statement) }

        var results: [AgentTask] = []
        while sqlite3_step(statement) == SQLITE_ROW {
            results.append(
                AgentTask(
                    id: text(statement, at: 0),
                    provider: text(statement, at: 1),
                    prompt: text(statement, at: 2),
                    status: text(statement, at: 3),
                    createdAt: text(statement, at: 4)
                )
            )
        }
        return results
    }

    func setStatus(_ id: String, to status: String) throws -> Bool {
        var database: OpaquePointer?
        guard sqlite3_open_v2(databaseURL.path, &database, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK else {
            if let database { sqlite3_close(database) }
            throw NSError(domain: "MacRemote.Database", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "The agent task database is not available yet."
            ])
        }
        defer { sqlite3_close(database) }

        var statement: OpaquePointer?
        let sql = "UPDATE agent_tasks SET status = ? WHERE id = ? AND status = 'pending'"
        guard sqlite3_prepare_v2(database, sql, -1, &statement, nil) == SQLITE_OK else {
            throw databaseError(database)
        }
        defer { sqlite3_finalize(statement) }
        sqlite3_bind_text(statement, 1, status, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(statement, 2, id, -1, SQLITE_TRANSIENT)
        guard sqlite3_step(statement) == SQLITE_DONE else {
            throw databaseError(database)
        }
        return sqlite3_changes(database) == 1
    }

    private func text(_ statement: OpaquePointer?, at index: Int32) -> String {
        guard let value = sqlite3_column_text(statement, index) else { return "" }
        return String(cString: value)
    }

    private func databaseError(_ database: OpaquePointer?) -> NSError {
        let detail = database.flatMap { sqlite3_errmsg($0) }.map(String.init(cString:)) ?? "Unknown database error."
        return NSError(domain: "MacRemote.Database", code: 2, userInfo: [
            NSLocalizedDescriptionKey: detail
        ])
    }
}

private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

@main
private struct MacRemoteApp: App {
    @StateObject private var model = AppModel()

    init() {
        NSApplication.shared.setActivationPolicy(.accessory)
    }

    var body: some Scene {
        MenuBarExtra {
            HostDashboard(model: model)
                .frame(width: 440, height: 640)
        } label: {
            Label("MacRemote", systemImage: model.isAgentRunning ? "dot.radiowaves.left.and.right" : "desktopcomputer")
        }
        .menuBarExtraStyle(.window)
    }
}

private struct HostDashboard: View {
    @ObservedObject var model: AppModel

    private var pendingTasks: [AgentTask] {
        model.tasks.filter { $0.status == "pending" }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let message = model.errorMessage {
                        messageBox(message, color: .red)
                    }
                    if let message = model.notice {
                        messageBox(message, color: .green)
                    }
                    settings
                    approvalQueue
                    activityLog
                }
                .padding(18)
            }
            footer
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .onAppear(perform: model.refresh)
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "macbook.and.iphone")
                .font(.system(size: 24, weight: .medium))
                .foregroundStyle(Color.accentColor)
            VStack(alignment: .leading, spacing: 3) {
                Text("MacRemote").font(.system(size: 19, weight: .semibold))
                HStack(spacing: 6) {
                    Circle()
                        .fill(model.isAgentRunning ? Color.green : Color.orange)
                        .frame(width: 7, height: 7)
                    Text(model.isAgentRunning ? "Host agent running" : "Setup required")
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button(action: model.refresh) {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.borderless)
            .help("Refresh task list")
        }
        .padding(18)
        .background(.bar)
    }

    private var settings: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionTitle("Connection", subtitle: "Use Telegram, or configure a paired relay for the Android app.")
            VStack(alignment: .leading, spacing: 10) {
                SecureField("Telegram bot token", text: $model.botToken)
                    .textFieldStyle(.roundedBorder)
                TextField("Antigravity CLI path (optional)", text: $model.antigravityPath)
                    .textFieldStyle(.roundedBorder)
                TextField("Claude Code CLI path (optional)", text: $model.claudePath)
                    .textFieldStyle(.roundedBorder)
                TextField("Working folder for approved tasks", text: $model.workingDirectory)
                    .textFieldStyle(.roundedBorder)
                TextField("Relay HTTPS URL (optional)", text: $model.relayURL)
                    .textFieldStyle(.roundedBorder)
                TextField("Relay host ID (optional)", text: $model.relayHostID)
                    .textFieldStyle(.roundedBorder)
                SecureField("Relay host token (optional)", text: $model.relayHostToken)
                    .textFieldStyle(.roundedBorder)
                HStack {
                    if !model.pairingPin.isEmpty {
                        Label("Pairing PIN: \(model.pairingPin)", systemImage: "lock.shield")
                            .font(.system(size: 12, weight: .medium, design: .monospaced))
                            .textSelection(.enabled)
                    } else {
                        Text("Pairing PIN is created when settings are saved.")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                    Button("Save & connect", action: model.saveSettings)
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                }
            }
            .padding(14)
            .background(.quaternary.opacity(0.55), in: RoundedRectangle(cornerRadius: 12))
        }
    }

    private var approvalQueue: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionTitle(
                "Approval queue",
                subtitle: pendingTasks.isEmpty ? "No tasks are waiting for approval." : "\(pendingTasks.count) task\(pendingTasks.count == 1 ? "" : "s") need your review."
            )
            if model.tasks.isEmpty {
                emptyState
            } else {
                ForEach(model.tasks) { task in
                    taskCard(task)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.shield")
                .font(.system(size: 27))
                .foregroundStyle(.secondary)
            Text(model.isAgentRunning ? "You're all caught up" : "Connect Telegram to receive tasks")
                .font(.system(size: 13, weight: .medium))
            Text(model.isAgentRunning
                 ? "Antigravity and Claude Code requests will appear here before they run."
                 : "Save your bot token above to start the host agent.")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(20)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
    }

    private func taskCard(_ task: AgentTask) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(task.provider == "claude" ? "Claude Code" : "Antigravity", systemImage: "sparkles")
                    .font(.system(size: 12, weight: .semibold))
                Spacer()
                Text(task.status.capitalized)
                    .font(.system(size: 10, weight: .medium))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(statusColor(task.status).opacity(0.15), in: Capsule())
                    .foregroundStyle(statusColor(task.status))
            }
            Text(task.prompt)
                .font(.system(size: 12))
                .textSelection(.enabled)
                .lineLimit(5)
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack {
                Text(task.createdAt)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
                Spacer()
                if task.status == "pending" {
                    Button("Reject") { model.reject(task) }
                        .controlSize(.small)
                    Button("Approve") { model.approve(task) }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                }
            }
        }
        .padding(13)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
    }

    private var activityLog: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle("Task safety", subtitle: "Remote shell commands are disabled.")
            Text("Approving starts the selected CLI with the submitted prompt. Review prompts before approval; any file edits or other actions are performed by the CLI under your macOS account.")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("Open host activity log", action: model.openActivityLog)
                .buttonStyle(.link)
                .font(.system(size: 11))
        }
    }

    private var footer: some View {
        HStack {
            Text("Local approval • This Mac only")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            Spacer()
            Button("Quit MacRemote") {
                NSApplication.shared.terminate(nil)
            }
            .buttonStyle(.borderless)
            .font(.system(size: 11))
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
        .background(.bar)
    }

    private func sectionTitle(_ title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.system(size: 14, weight: .semibold))
            Text(subtitle).font(.system(size: 11)).foregroundStyle(.secondary)
        }
    }

    private func messageBox(_ message: String, color: Color) -> some View {
        Text(message)
            .font(.system(size: 11))
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            .foregroundStyle(color)
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "pending": .orange
        case "approved", "completed": .green
        case "running": .blue
        default: .secondary
        }
    }
}
