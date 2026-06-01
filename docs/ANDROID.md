# A.E.T.H.E.R. on Android (installable app)

A.E.T.H.E.R. is a **Progressive Web App (PWA)**. You install it from Chrome on your phone; the AI and printer still run on your **home PC** (Ollama + A.E.T.H.E.R. server).

## What you need

1. A Windows PC on your home network running Ollama + A.E.T.H.E.R.
2. Phone on the **same Wi-Fi** (or Tailscale VPN for away-from-home).
3. **Google Chrome** on Android (Samsung Internet works too).

## Step 1: Start server for phone access (on PC)

```powershell
cd aether
.\.venv\Scripts\activate
aether web --lan
```

`--lan` listens on `0.0.0.0` so your phone can connect.

Find your PC IP (PowerShell):

```powershell
ipconfig
```

Look for **IPv4** under Wi-Fi, e.g. `192.168.1.42`.

On the phone browser open: `http://192.168.1.42:8787`

## Step 2: Install like an app

1. Open that URL in **Chrome**.
2. **Settings** (in the app) → **Server URL** → `http://192.168.1.42:8787` → Save → **Test connection**.
3. Install:
   - Chrome may show **Install app** (also under Settings in A.E.T.H.E.R.), or
   - Chrome menu (⋮) → **Install app** / **Add to Home screen**.

You get a home-screen icon that opens full-screen like a native app.

## Step 3: Use on the go (same Wi-Fi)

- **Chat**, **Learn & Build**, **Ender 3** status work from the phone.
- Heavy AI runs on the PC; the phone is the remote control.

## Away from home (optional)

Use **Tailscale** (free) on PC + phone, then set Server URL to your PC’s Tailscale IP, e.g. `http://100.x.x.x:8787`.

Do not expose port 8787 to the public internet without authentication.

## Limitations

- This is **not** a standalone Play Store APK; it requires your PC to be on with `aether web --lan` running.
- A full offline Android-only build would need Ollama on the phone (very limited) or a cloud backend.

## Firewall

If the phone cannot connect, allow Python through Windows Firewall for private networks, or allow inbound TCP **8787**.
