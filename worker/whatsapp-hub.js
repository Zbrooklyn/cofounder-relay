/**
 * cofounder-relay — WhatsApp hub (Cloudflare Worker).
 *
 * WhatsApp's official API only PUSHES inbound to a webhook (no polling like Discord),
 * so this always-on hub sits between the relay and WhatsApp. It is the source of truth:
 * every message (a Claude's outbound AND a human's inbound WhatsApp reply) is stored per
 * room; each side's relay polls GET /messages. The relay never talks to WhatsApp directly
 * — this Worker absorbs every provider detail, so the Python side stays provider-agnostic.
 *
 * Provider is chosen by the PROVIDER env var ("twilio" | "meta"); both are implemented
 * here, so switching is a config change, not a rewrite.
 *
 * Routes:
 *   GET  /webhook        Meta verification handshake (echoes hub.challenge)
 *   POST /webhook        inbound from WhatsApp (Twilio form-enc OR Meta JSON) -> store
 *   GET  /messages       relay poll: ?room=&since=&limit=  -> {messages:[...]} oldest-first
 *   POST /send           relay send: {room,text,identity} -> store + fan out to WhatsApp
 *
 * Bindings:
 *   KV  MESSAGES         per-room message log + counter
 * Env (Worker secrets/vars):
 *   PROVIDER             "twilio" | "meta"
 *   HUB_TOKEN            shared secret; relay sends Authorization: Bearer <HUB_TOKEN>
 *   ROOMS                JSON: {"<room>":{"participants":[{"number":"+1...","identity":"Edward"},...]}}
 *   -- Meta:   META_TOKEN, META_PHONE_ID, META_VERIFY_TOKEN
 *   -- Twilio: TW_SID, TW_TOKEN, TW_FROM   (e.g. "whatsapp:+14155238886")
 *
 * Normalized message shape (matches the Discord/Mock transports):
 *   { id, author, identity, text, ts, is_bot }
 */

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

function rooms(env) {
  try { return JSON.parse(env.ROOMS || "{}"); } catch { return {}; }
}

// Which room does an inbound WhatsApp number belong to, and who is it? (E.164, tolerant of "whatsapp:" prefix)
function identify(env, fromNumber) {
  const norm = (n) => (n || "").replace(/^whatsapp:/, "").replace(/[^\d+]/g, "");
  const target = norm(fromNumber);
  const all = rooms(env);
  for (const [room, cfg] of Object.entries(all)) {
    for (const p of cfg.participants || []) {
      if (norm(p.number) === target) return { room, identity: p.identity, number: target };
    }
  }
  return null;
}

async function readLog(env, room) {
  const raw = await env.MESSAGES.get(`room:${room}`);
  return raw ? JSON.parse(raw) : { seq: 1000, messages: [] };
}

async function appendMessage(env, room, { author, identity, text, is_bot }) {
  const log = await readLog(env, room);
  log.seq += 1;
  const msg = {
    id: String(log.seq),
    author,
    identity,
    text,
    ts: new Date().toISOString(),
    is_bot: !!is_bot,
  };
  log.messages.push(msg);
  if (log.messages.length > 500) log.messages = log.messages.slice(-500); // cap
  await env.MESSAGES.put(`room:${room}`, JSON.stringify(log));
  return msg;
}

// --- provider send: deliver `text` to one WhatsApp number ------------------
async function sendToNumber(env, toNumber, text) {
  const provider = (env.PROVIDER || "meta").toLowerCase();
  if (provider === "twilio") {
    const to = toNumber.startsWith("whatsapp:") ? toNumber : `whatsapp:${toNumber}`;
    const from = env.TW_FROM.startsWith("whatsapp:") ? env.TW_FROM : `whatsapp:${env.TW_FROM}`;
    const body = new URLSearchParams({ To: to, From: from, Body: text });
    const r = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${env.TW_SID}/Messages.json`, {
      method: "POST",
      headers: {
        "Authorization": "Basic " + btoa(`${env.TW_SID}:${env.TW_TOKEN}`),
        "content-type": "application/x-www-form-urlencoded",
      },
      body,
    });
    return r.ok;
  }
  // meta (WhatsApp Cloud API)
  const to = toNumber.replace(/^whatsapp:/, "").replace(/[^\d]/g, "");
  const r = await fetch(`https://graph.facebook.com/v21.0/${env.META_PHONE_ID}/messages`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${env.META_TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ messaging_product: "whatsapp", to, type: "text", text: { body: text } }),
  });
  return r.ok;
}

// Fan a message out to every participant in a room EXCEPT the given identity (the sender).
async function fanOut(env, room, text, exceptIdentity) {
  const cfg = rooms(env)[room];
  if (!cfg) return;
  await Promise.all(
    (cfg.participants || [])
      .filter((p) => p.identity !== exceptIdentity)
      .map((p) => sendToNumber(env, p.number, text).catch(() => false))
  );
}

// --- inbound parsers -------------------------------------------------------
async function parseInbound(env, request) {
  const provider = (env.PROVIDER || "meta").toLowerCase();
  if (provider === "twilio") {
    const form = await request.formData();
    return [{ from: form.get("From"), text: form.get("Body") || "" }];
  }
  // meta: entry[].changes[].value.messages[]
  const body = await request.json().catch(() => ({}));
  const out = [];
  for (const entry of body.entry || []) {
    for (const change of entry.changes || []) {
      for (const m of change.value?.messages || []) {
        out.push({ from: m.from, text: m.text?.body || "" });
      }
    }
  }
  return out;
}

function authed(request, env) {
  const h = request.headers.get("Authorization") || "";
  return env.HUB_TOKEN && h === `Bearer ${env.HUB_TOKEN}`;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Meta webhook verification handshake
    if (path === "/webhook" && request.method === "GET") {
      const mode = url.searchParams.get("hub.mode");
      const token = url.searchParams.get("hub.verify_token");
      const challenge = url.searchParams.get("hub.challenge");
      if (mode === "subscribe" && token === env.META_VERIFY_TOKEN) return new Response(challenge, { status: 200 });
      return new Response("forbidden", { status: 403 });
    }

    // Inbound from WhatsApp (a human typed a reply)
    if (path === "/webhook" && request.method === "POST") {
      const items = await parseInbound(env, request);
      for (const it of items) {
        const who = identify(env, it.from);
        if (!who || !it.text) continue;
        // store as a human (is_bot:false) so the relay can distinguish AI vs human
        await appendMessage(env, who.room, {
          author: `${who.identity} (WhatsApp)`, identity: who.identity, text: it.text, is_bot: false,
        });
        // mirror to the other participants so their phones see it too
        await fanOut(env, who.room, `${who.identity}: ${it.text}`, who.identity);
      }
      // Twilio expects TwiML/200; Meta expects 200
      return new Response("", { status: 200 });
    }

    // Relay poll
    if (path === "/messages" && request.method === "GET") {
      if (!authed(request, env)) return json({ error: "unauthorized" }, 401);
      const room = url.searchParams.get("room");
      const since = url.searchParams.get("since");
      const limit = parseInt(url.searchParams.get("limit") || "50", 10);
      if (!room) return json({ error: "room required" }, 400);
      const log = await readLog(env, room);
      let msgs = log.messages;
      if (since) msgs = msgs.filter((m) => parseInt(m.id, 10) > parseInt(since, 10));
      return json({ messages: msgs.slice(0, limit) });
    }

    // Relay send: store + push to the humans' WhatsApp
    if (path === "/send" && request.method === "POST") {
      if (!authed(request, env)) return json({ error: "unauthorized" }, 401);
      const { room, text, identity } = await request.json().catch(() => ({}));
      if (!room || !text) return json({ error: "room and text required" }, 400);
      const msg = await appendMessage(env, room, {
        author: `${identity}'s Claude`, identity, text, is_bot: true,
      });
      await fanOut(env, room, `${identity}'s Claude: ${text}`, identity);
      return json({ id: msg.id });
    }

    return new Response("cofounder-relay whatsapp hub", { status: 200 });
  },
};
