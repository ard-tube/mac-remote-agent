"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const { once } = require("node:events");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { createRelayServer } = require("./server");

const adminKey = crypto.randomBytes(32).toString("base64url");

async function withRelay(run) {
  const server = createRelayServer({ databasePath: ":memory:", adminKey });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    server.close();
    await once(server, "close");
  }
}

async function createHost(baseUrl) {
  const response = await fetch(`${baseUrl}/v1/hosts`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${adminKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: "Test Mac" }),
  });
  assert.equal(response.status, 201);
  return response.json();
}

test("provisioned phone can queue a built-in action for its host", async () => {
  await withRelay(async (baseUrl) => {
    const host = await createHost(baseUrl);
    const queued = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${host.phoneToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action: "status" }),
    });
    assert.equal(queued.status, 202);

    const poll = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      headers: { Authorization: `Bearer ${host.hostToken}` },
    });
    const body = await poll.json();
    assert.equal(body.commands.length, 1);
    assert.equal(body.commands[0].action, "status");

    const finished = await fetch(
      `${baseUrl}/v1/hosts/${host.id}/commands/${body.commands[0].id}/result`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${host.hostToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "completed", result: { platform: "macOS" } }),
      },
    );
    assert.equal(finished.status, 200);

    const hostStatus = await fetch(`${baseUrl}/v1/hosts/${host.id}`, {
      headers: { Authorization: `Bearer ${host.phoneToken}` },
    });
    const status = await hostStatus.json();
    assert.equal(status.commands[0].status, "completed");
    assert.deepEqual(status.commands[0].result, { platform: "macOS" });
  });
});

test("rejects unpaired access and arbitrary commands", async () => {
  await withRelay(async (baseUrl) => {
    const host = await createHost(baseUrl);
    const unauthorized = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "status" }),
    });
    assert.equal(unauthorized.status, 401);

    const shell = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${host.phoneToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action: "shell", command: "whoami" }),
    });
    assert.equal(shell.status, 400);
  });
});

test("agent tasks require explicit provider and a bounded prompt", async () => {
  await withRelay(async (baseUrl) => {
    const host = await createHost(baseUrl);
    const valid = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${host.phoneToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action: "agent_task", provider: "claude", prompt: "Review this project" }),
    });
    assert.equal(valid.status, 202);

    const invalid = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${host.phoneToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action: "agent_task", provider: "shell", prompt: "run a command" }),
    });
    assert.equal(invalid.status, 400);
  });
});

test("agent commands remain observable while awaiting host approval", async () => {
  await withRelay(async (baseUrl) => {
    const host = await createHost(baseUrl);
    const queued = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${host.phoneToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action: "agent_task", provider: "antigravity", prompt: "Check the repo" }),
    });
    const command = await queued.json();
    const poll = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      headers: { Authorization: `Bearer ${host.hostToken}` },
    });
    const delivered = (await poll.json()).commands[0];

    const awaitingApproval = await fetch(
      `${baseUrl}/v1/hosts/${host.id}/commands/${delivered.id}/result`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${host.hostToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "awaiting_approval", result: { taskId: "task-1" } }),
      },
    );
    assert.equal(awaitingApproval.status, 200);

    const finalResult = await fetch(
      `${baseUrl}/v1/hosts/${host.id}/commands/${command.id}/result`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${host.hostToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: "completed", result: { text: "Done" } }),
      },
    );
    assert.equal(finalResult.status, 200);
  });
});

test("phone activity feed omits screenshot bytes and loads them on demand", async () => {
  await withRelay(async (baseUrl) => {
    const host = await createHost(baseUrl);
    const queued = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${host.phoneToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action: "screenshot" }),
    });
    const { id } = await queued.json();
    const poll = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands`, {
      headers: { Authorization: `Bearer ${host.hostToken}` },
    });
    await poll.json();
    const finished = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands/${id}/result`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${host.hostToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        status: "completed",
        result: { mediaType: "image/jpeg", imageBase64: "c2NyZWVuc2hvdA==" },
      }),
    });
    assert.equal(finished.status, 200);

    const feed = await fetch(`${baseUrl}/v1/hosts/${host.id}`, {
      headers: { Authorization: `Bearer ${host.phoneToken}` },
    });
    const feedCommand = (await feed.json()).commands[0];
    assert.equal(feedCommand.result.hasScreenshot, true);
    assert.equal("imageBase64" in feedCommand.result, false);

    const detail = await fetch(`${baseUrl}/v1/hosts/${host.id}/commands/${id}`, {
      headers: { Authorization: `Bearer ${host.phoneToken}` },
    });
    assert.equal((await detail.json()).result.imageBase64, "c2NyZWVuc2hvdA==");
  });
});

test("relay database files are private on Unix", async (t) => {
  if (process.platform === "win32") {
    t.skip("Unix file mode checks do not apply on Windows.");
    return;
  }
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "macremote-relay-test-"));
  const databasePath = path.join(directory, "data", "relay.sqlite3");
  const server = createRelayServer({ databasePath, adminKey });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const { port } = server.address();
    await createHost(`http://127.0.0.1:${port}`);
  } finally {
    server.close();
    await once(server, "close");
  }

  try {
    assert.equal(fs.statSync(path.dirname(databasePath)).mode & 0o777, 0o700);
    assert.equal(fs.statSync(databasePath).mode & 0o777, 0o600);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
