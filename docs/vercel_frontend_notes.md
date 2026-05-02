# Vercel Frontend Notes

The VPO Corp frontend lives in:

```text
web/
```

It is a Next.js app. The browser never receives the Render API key. Instead:

```text
Browser -> Vercel API route -> Render API -> Google Cloud Storage -> XLSX
```

## Local Development

```powershell
cd C:\royalties_pipeline\web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:3000
```

## Local Environment

Create `web/.env.local`:

```text
VPO_API_URL=https://vpo-corp-api.onrender.com
VPO_API_KEY=<render-api-key>
VPO_WEB_PASSWORD=<web-login-password>
```

`web/.env.local` is ignored by Git.

## Vercel Environment Variables

Set these in Vercel:

```text
VPO_API_URL=https://vpo-corp-api.onrender.com
VPO_API_KEY=<render-api-key>
VPO_WEB_PASSWORD=<web-login-password>
```

## Vercel Project Settings

When importing the GitHub repo:

```text
Framework Preset: Next.js
Root Directory: web
Build Command: npm run build
Output Directory: .next
Install Command: npm install
```

