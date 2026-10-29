"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { DatabaseSync } = require("node:sqlite");

const MAX_BODY_BYTES = 5 * 1024 * 1024;
const MAX_PROMPT_CHARS = 4000;
const MAX_LEASE_SECONDS = 60;
const ACTIONS = new Set(["status", "screenshot", "lock", "open_folder", "agent_task"]);
const ID_PATTERN = /^[A-Za-z0-9_-]{16,64}$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function hashToken(token) {
  return crypto.createHash("sha256").update(token, "utf8").digest();
}

function safeEqual(left, right) {
  const leftHash = hashToken(left);
  const rightHash = hashToken(right);
  return crypto.timingSafeEqual(leftHash, rightHash);
}

function bearerToken(request) {
  const match = /^Bearer ([A-Za-z0-9_-]{40,128})$/.exec(request.headers.authorization || "");
  if (!match) {
    throw new HttpError(401, "A valid bearer token is required.");
  }
  return match[1];
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new HttpError(413, "Request body is too large."));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(new HttpError(400, "Request body must be valid JSON."));
      }
    });
    request.on("error", reject);
  });
}

function sendJson(response, status, value) {
  const body = Buffer.from(JSON.stringify(value));
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Length": body.length,
    "Content-Type": "application/json; charset=utf-8",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  });
  response.end(body);
}

function phoneCommand(row, includeScreenshot) {
  let result = row.result_json ? JSON.parse(row.result_json) : null;
  const screenshot = row.screenshot_base64;
  const hasScreenshot = Boolean(screenshot) || row.has_screenshot === 1;
  if (hasScreenshot) {
    if (!result || typeof result !== "object" || Array.isArray(result)) result = {};
    if (includeScreenshot && screenshot) {
      result.imageBase64 = screenshot;
    } else {
      result.hasScreenshot = true;
    }
  }
  return {
    id: row.id,
    action: row.action,
    status: row.status,
    createdAt: row.created_at,
    finishedAt: row.finished_at,
    result,
  };
}

function createRelayServer({ databasePath, adminKey, now = Date.now, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)) }) {
  if (!adminKey || Buffer.byteLength(adminKey, "utf8") < 32) {
    throw new Error("MRA_RELAY_ADMIN_KEY must be configured with at least 32 bytes.");
  }
  if (databasePath !== ":memory:") {
    const dataDirectory = path.dirname(databasePath);
    fs.mkdirSync(dataDirectory, { recursive: true, mode: 0o700 });
    fs.chmodSync(dataDirectory, 0o700);
  }

  const database = new DatabaseSync(databasePath);
  database.exec(`
    PRAGMA foreign_keys = ON;
    PRAGMA journal_mode = WAL;
    PRAGMA busy_timeout = 5000;
    CREATE TABLE IF NOT EXISTS hosts (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      host_token_hash BLOB NOT NULL,
      phone_token_hash BLOB NOT NULL,
      created_at TEXT NOT NULL,
      last_seen_at TEXT
    );
    CREATE TABLE IF NOT EXISTS commands (
      id TEXT PRIMARY KEY,
      host_id TEXT NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
      action TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      status TEXT NOT NULL CHECK (status IN ('queued', 'leased', 'awaiting_approval', 'completed', 'failed', 'cancelled')),
      lease_until INTEGER,
      created_at TEXT NOT NULL,
      finished_at TEXT,
      result_json TEXT,
      screenshot_base64 TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_commands_host_status ON commands(host_id, status, created_at);
  `);
  const commandColumns = database.prepare("PRAGMA table_info(commands)").all();
  if (!commandColumns.some((column) => column.name === "screenshot_base64")) {
    database.exec("ALTER TABLE commands ADD COLUMN screenshot_base64 TEXT");
  }
  function secureDatabaseFiles() {
    if (databasePath === ":memory:") return;
    for (const suffix of ["", "-wal", "-shm"]) {
      try {
        fs.chmodSync(`${databasePath}${suffix}`, 0o600);
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
    }
  }
  const legacyScreenshotIds = database.prepare(
    "SELECT id FROM commands WHERE screenshot_base64 IS NULL AND result_json LIKE '%\"imageBase64\"%'"
  );
  const getLegacyResult = database.prepare("SELECT result_json FROM commands WHERE id = ?");
  const migrateLegacyScreenshot = database.prepare(
    "UPDATE commands SET result_json = ?, screenshot_base64 = ? WHERE id = ?"
  );
  for (const { id } of legacyScreenshotIds.all()) {
    const result = JSON.parse(getLegacyResult.get(id).result_json);
    if (result && typeof result === "object" && !Array.isArray(result) && typeof result.imageBase64 === "string") {
      const { imageBase64, ...summary } = result;
      migrateLegacyScreenshot.run(JSON.stringify(summary), imageBase64, id);
    }
  }
  secureDatabaseFiles();

  const findHost = database.prepare("SELECT * FROM hosts WHERE id = ?");
  const updateLastSeen = database.prepare("UPDATE hosts SET last_seen_at = ? WHERE id = ?");
  const getPhoneCommands = database.prepare(
    "SELECT id, action, status, created_at, finished_at, result_json, " +
    "screenshot_base64 IS NOT NULL AS has_screenshot " +
    "FROM commands WHERE host_id = ? " +
    "ORDER BY created_at DESC LIMIT 50"
  );
  const getPhoneCommand = database.prepare(
    "SELECT id, action, status, created_at, finished_at, result_json, screenshot_base64 " +
    "FROM commands WHERE host_id = ? AND id = ?"
  );
  const leaseCommands = database.prepare(
    "SELECT id, action, payload_json, created_at FROM commands " +
    "WHERE host_id = ? AND (status = 'queued' OR (status = 'leased' AND lease_until < ?)) " +
    "ORDER BY created_at LIMIT 10"
  );

  function authorize(request, host, tokenField) {
    const token = bearerToken(request);
    if (!host || !crypto.timingSafeEqual(
      hashToken(token),
      Buffer.from(host[tokenField]),
    )) {
      throw new HttpError(401, "Invalid access token.");
    }
  }

  function verifyAdmin(request) {
    const token = bearerToken(request);
    if (!safeEqual(token, adminKey)) {
      throw new HttpError(401, "Invalid provisioning key.");
    }
  }

  function provisionHost(request, response, body) {
    verifyAdmin(request);
    const name = typeof body.name === "string" ? body.name.trim() : "";
    if (!name || name.length > 80) {
      throw new HttpError(400, "Host name must be between 1 and 80 characters.");
    }
    const id = crypto.randomBytes(18).toString("base64url");
    const hostToken = crypto.randomBytes(32).toString("base64url");
    const phoneToken = crypto.randomBytes(32).toString("base64url");
    const createdAt = new Date(now()).toISOString();
    database.prepare(
      "INSERT INTO hosts (id, name, host_token_hash, phone_token_hash, created_at) VALUES (?, ?, ?, ?, ?)"
    ).run(id, name, hashToken(hostToken), hashToken(phoneToken), createdAt);
    secureDatabaseFiles();
    sendJson(response, 201, { id, name, hostToken, phoneToken, createdAt });
  }

  async function createCommand(request, response, host) {
    authorize(request, host, "phone_token_hash");
    const body = await readJson(request);
    if (!body || !ACTIONS.has(body.action)) {
      throw new HttpError(400, "Unknown command action.");
    }
    let payload = {};
    if (body.action === "agent_task") {
      const { provider, prompt } = body;
      if (!["antigravity", "claude"].includes(provider) || typeof prompt !== "string") {
        throw new HttpError(400, "Agent tasks require provider and prompt fields.");
      }
      const cleanPrompt = prompt.trim();
      if (!cleanPrompt || cleanPrompt.length > MAX_PROMPT_CHARS) {
        throw new HttpError(400, "Task prompt must be between 1 and 4,000 characters.");
      }
      payload = { provider, prompt: cleanPrompt };
    } else if (body.action === "open_folder") {
      if (typeof body.path !== "string" || !body.path.trim() || body.path.length > 1024) {
        throw new HttpError(400, "Folder path must be between 1 and 1,024 characters.");
      }
      payload = { path: body.path.trim() };
    } else if (body.action === "lock" || body.action === "screenshot" || body.action === "status") {
      if (Object.keys(body).some((key) => key !== "action")) {
        throw new HttpError(400, "This action does not accept additional fields.");
      }
    }

    const id = crypto.randomUUID();
    const createdAt = new Date(now()).toISOString();
    database.prepare(
      "INSERT INTO commands (id, host_id, action, payload_json, status, created_at) VALUES (?, ?, ?, ?, 'queued', ?)"
    ).run(id, host.id, body.action, JSON.stringify(payload), createdAt);
    secureDatabaseFiles();
    sendJson(response, 202, { id, status: "queued", createdAt });
  }

  async function pollCommands(request, response, host) {
    authorize(request, host, "host_token_hash");
    const url = new URL(request.url, "http://relay.local");
    const requestedWait = Number(url.searchParams.get("wait") || 0);
    const waitMs = Number.isFinite(requestedWait) ? Math.min(Math.max(requestedWait, 0), 25) * 1000 : 0;
    const deadline = now() + waitMs;
    let commands = [];
    do {
      const timestamp = now();
      updateLastSeen.run(new Date(timestamp).toISOString(), host.id);
      secureDatabaseFiles();
      database.exec("BEGIN IMMEDIATE");
      try {
        commands = leaseCommands.all(host.id, timestamp).map((row) => {
          database.prepare(
            "UPDATE commands SET status = 'leased', lease_until = ? WHERE id = ? AND host_id = ?"
          ).run(timestamp + MAX_LEASE_SECONDS * 1000, row.id, host.id);
          return {
            id: row.id,
            action: row.action,
            payload: JSON.parse(row.payload_json),
            createdAt: row.created_at,
          };
        });
        database.exec("COMMIT");
        secureDatabaseFiles();
      } catch (error) {
        database.exec("ROLLBACK");
        throw error;
      }
      if (commands.length || now() >= deadline) break;
      await sleep(Math.min(500, deadline - now()));
    } while (now() < deadline);
    sendJson(response, 200, { commands });
  }

  async function finishCommand(request, response, host, commandId) {
    authorize(request, host, "host_token_hash");
    if (!UUID_PATTERN.test(commandId)) throw new HttpError(404, "Command not found.");
    const body = await readJson(request);
    if (!body || !["awaiting_approval", "completed", "failed"].includes(body.status)) {
      throw new HttpError(400, "Command result status is invalid.");
    }
    if (body.result === undefined || body.result === null) {
      throw new HttpError(400, "A command result is required.");
    }
    const fullResultJson = JSON.stringify(body.result);
    if (Buffer.byteLength(fullResultJson, "utf8") > MAX_BODY_BYTES) {
      throw new HttpError(413, "Command result is too large.");
    }
    let result = body.result;
    let screenshotBase64 = null;
    if (result && typeof result === "object" && !Array.isArray(result) && typeof result.imageBase64 === "string") {
      screenshotBase64 = result.imageBase64;
      result = { ...result };
      delete result.imageBase64;
    }
    const resultJson = JSON.stringify(result);
    const finishedAt = new Date(now()).toISOString();
    const update = body.status === "awaiting_approval"
      ? database.prepare(
        "UPDATE commands SET status = ?, lease_until = NULL, result_json = ?, screenshot_base64 = ? " +
        "WHERE id = ? AND host_id = ? AND status = 'leased'"
      ).run(body.status, resultJson, screenshotBase64, commandId, host.id)
      : database.prepare(
        "UPDATE commands SET status = ?, lease_until = NULL, finished_at = ?, result_json = ?, screenshot_base64 = ? " +
        "WHERE id = ? AND host_id = ? AND status IN ('leased', 'awaiting_approval')"
      ).run(body.status, finishedAt, resultJson, screenshotBase64, commandId, host.id);
    if (update.changes !== 1) {
      throw new HttpError(409, "Command is not leased or has already finished.");
    }
    secureDatabaseFiles();
    sendJson(response, 200, { id: commandId, status: body.status, finishedAt });
  }

  async function route(request, response) {
    try {
      const url = new URL(request.url, "http://relay.local");
      if (request.method === "GET" && url.pathname === "/health") {
        return sendJson(response, 200, { status: "ok" });
      }
      if (request.method === "POST" && url.pathname === "/v1/hosts") {
        return provisionHost(request, response, await readJson(request));
      }

      const commandMatch = /^\/v1\/hosts\/([A-Za-z0-9_-]{16,64})\/commands(?:\/([0-9a-f-]{36})\/result)?$/.exec(url.pathname);
      const commandDetailMatch = /^\/v1\/hosts\/([A-Za-z0-9_-]{16,64})\/commands\/([0-9a-f-]{36})$/.exec(url.pathname);
      const hostMatch = /^\/v1\/hosts\/([A-Za-z0-9_-]{16,64})$/.exec(url.pathname);
      if (!commandMatch && !commandDetailMatch && !hostMatch) throw new HttpError(404, "Route not found.");
      const hostId = (commandMatch || commandDetailMatch || hostMatch)[1];
      const host = findHost.get(hostId);
      if (!host) throw new HttpError(404, "Host not found.");

      if (commandDetailMatch && request.method === "GET") {
        authorize(request, host, "phone_token_hash");
        const commandId = commandDetailMatch[2];
        if (!UUID_PATTERN.test(commandId)) throw new HttpError(404, "Command not found.");
        const command = getPhoneCommand.get(host.id, commandId);
        if (!command) throw new HttpError(404, "Command not found.");
        return sendJson(response, 200, phoneCommand(command, true));
      }
      if (commandMatch && commandMatch[2] && request.method === "POST") {
        return await finishCommand(request, response, host, commandMatch[2]);
      }
      if (commandMatch && !commandMatch[2] && request.method === "POST") {
        return await createCommand(request, response, host);
      }
      if (commandMatch && !commandMatch[2] && request.method === "GET") {
        return await pollCommands(request, response, host);
      }
      if (hostMatch && request.method === "GET") {
        authorize(request, host, "phone_token_hash");
        return sendJson(response, 200, {
          id: host.id,
          name: host.name,
          createdAt: host.created_at,
          lastSeenAt: host.last_seen_at,
          commands: getPhoneCommands.all(host.id).map((row) => phoneCommand(row, false)),
        });
      }
      throw new HttpError(405, "Method not allowed.");
    } catch (error) {
      const status = error instanceof HttpError ? error.status : 500;
      if (status === 500) console.error("Relay request failed:", error);
      if (!response.headersSent) {
        sendJson(response, status, { error: status === 500 ? "Internal server error." : error.message });
      } else {
        response.destroy();
      }
    }
  }

  const server = http.createServer((request, response) => {
    response.setTimeout(30_000);
    void route(request, response);
  });
  server.on("close", () => database.close());
  return server;
}

if (require.main === module) {
  const dataDirectory = path.resolve(process.env.MRA_RELAY_DATA_DIR || path.join(__dirname, "data"));
  const server = createRelayServer({
    databasePath: path.join(dataDirectory, "relay.sqlite3"),
    adminKey: process.env.MRA_RELAY_ADMIN_KEY,
  });
  const host = process.env.MRA_RELAY_BIND || "127.0.0.1";
  const port = Number(process.env.MRA_RELAY_PORT || 8787);
  server.listen(port, host, () => {
    console.log(`MacRemote relay listening on http://${host}:${port}`);
    console.log("Place an HTTPS reverse proxy in front before allowing remote clients.");
  });
  const shutdown = () => server.close(() => process.exit(0));
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

module.exports = { createRelayServer };
