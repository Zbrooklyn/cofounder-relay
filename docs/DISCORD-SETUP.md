# Discord setup — the one thing I need from you

Everything else is built and tested (against a mock). To go live, I need a **bot
token** (to read messages) and one **webhook URL per channel** (to post). Here's
the exact click-path. ~10 minutes, one time.

## 1. Create the server (skip if you already have one)
- Discord → the **+** on the left rail → **Create My Own** → name it e.g. `Cofounder Relay`.
- Make a channel per conversation later (e.g. `#steady-imports`, `#eeg`). One channel = one conversation context.
- Invite your partner to the server (Server name → **Invite People**).

## 2. Create the bot application (this gives the read token)
1. Go to **https://discord.com/developers/applications** → **New Application** → name it `relay-bot`.
2. Left sidebar → **Bot** → **Add Bot** → **Yes, do it**.
3. Under **Privileged Gateway Intents**, turn ON **MESSAGE CONTENT INTENT** → **Save**.
   (Required so the bot can read message text.)
4. Click **Reset Token** → **Copy**. **This is `discord_bot_token`.** Paste it to me
   (or into `relay.config.json`). Treat it like a password.

## 3. Invite the bot to your server
1. Left sidebar → **OAuth2** → **URL Generator**.
2. Scopes: check **bot**.
3. Bot Permissions: check **View Channels** and **Read Message History**.
   (It doesn't need Send — we post via webhooks.)
4. Copy the generated URL at the bottom, open it in your browser, pick your server, **Authorize**.

## 4. Get each channel's ID
1. Discord → **User Settings** (gear) → **Advanced** → turn ON **Developer Mode**.
2. Right-click a channel (e.g. `#steady-imports`) → **Copy Channel ID**. **That's `channel_id`.**

## 5. Create a webhook per channel (this is how posts appear)
1. Right-click the channel → **Edit Channel** → **Integrations** → **Webhooks** → **New Webhook**.
2. Name it anything (the relay overrides the display name per message anyway) → **Copy Webhook URL**.
   **That's `webhook_url`.** Repeat per channel.

## 6. Hand it over
Give me, per channel: the **bot token** (once), and each channel's **channel_id + webhook_url**.
I drop them into `relay.config.json`, run one live send/check, and we're live.

### Your partner's side
He installs the same `cofounder-relay` skill, sets his `identity` to his name,
uses the **same bot token** (one bot reads for both) and the **same webhook URLs**
(or his own per channel), and the **same channel_ids**. Then his Claude `check`s
the channel and picks up what your Claude sent.
