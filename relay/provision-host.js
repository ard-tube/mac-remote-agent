"use strict";

async function main() {
  const [name, ...extra] = process.argv.slice(2);
  const baseUrl = process.env.MRA_RELAY_URL;
  const adminKey = process.env.MRA_RELAY_ADMIN_KEY;
  if (!name || extra.length || !baseUrl || !adminKey) {
    throw new Error(
      'Usage: set MRA_RELAY_URL and MRA_RELAY_ADMIN_KEY, then run node provision-host.js "Office Mac".',
    );
  }
  const url = new URL(baseUrl);
  const isLoopback = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && isLoopback)) {
    throw new Error("Relay provisioning requires HTTPS; plain HTTP is allowed only for a loopback development server.");
  }

  const response = await fetch(new URL("/v1/hosts", url), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${adminKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(`Relay provisioning failed (${response.status}): ${body.error || "Unknown error"}`);
  }
  console.log("Save these one-time credentials in the matching host and phone apps:");
  console.log(JSON.stringify({ relayUrl: url.origin, ...body }, null, 2));
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
