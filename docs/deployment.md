# Deployment (Docker Compose on a tailnet host)

The app runs as two containers, `backend` (FastAPI) and `frontend` (Next.js), defined in
`docker-compose.yml` at the repo root. The host is reached over **Tailscale only**: no
public SSH, and no host names or addresses in this repo (see the operator's local runbook).

## Database

- **Default: MongoDB Atlas.** Set `MONGODB_URI` to the Atlas connection string.
  **Atlas means stored mail content leaves your own machines.** The privacy modes only
  control what is sent to AI providers, not what is stored.
- **Alternative: a MongoDB container on the host.** Set `MONGODB_URI=mongodb://mongo:27017`
  and add `--profile local-mongo` to every `docker compose` command. Data lives in the
  `mongo-data` volume.

## First deploy

1. Check the ports are free on the shared host: `ss -ltn | grep -E ':(3000|8000) '`.
   Pick other ports if they're taken.
2. Copy `.env.example` to `.env` next to `docker-compose.yml` and fill it in:
   `MONGODB_URI`, the ports, and the public URLs as the browser will see them
   (`PUBLIC_API_BASE`, `FRONTEND_ORIGIN`, i.e. the tailnet host name plus port).
3. Start it:
   - with images from GHCR (built by `.github/workflows/images.yml` on every push to
     `main`): `docker compose pull && docker compose up -d`
   - or build on the host: `docker compose up -d --build`
4. Before relying on it, check CORS from the UI origin:
   `curl -si -X OPTIONS <api>/api/v1/tasks/ -H 'Origin: <FRONTEND_ORIGIN>' -H 'Access-Control-Request-Method: GET'`
   must answer with `access-control-allow-origin: <FRONTEND_ORIGIN>`.

`PUBLIC_API_BASE` is baked into the frontend bundle at build time. For GHCR images, set
the repository variable `PUBLIC_API_BASE` (Settings → Variables) so CI builds the right
URL in. Building on the host uses the value from `.env`.

## Updating

Run the same command again: `docker compose pull && docker compose up -d` (or
`docker compose up -d --build`). It is idempotent: unchanged images keep their
containers running untouched, and only services whose image changed are recreated.
