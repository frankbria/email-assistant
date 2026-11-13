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

1. Check the ports are free on the shared host: `ss -ltn | grep -E ':(3200|8000) '`.
   Pick other ports if they're taken.
2. Copy `.env.example` to `.env` next to `docker-compose.yml` and fill it in:
   `MONGODB_URI`, the ports, `BIND_ADDRESS` (the host's Tailscale IP, from
   `tailscale ip -4`), and the public URLs as the browser will see them
   (`PUBLIC_API_BASE`, `FRONTEND_ORIGIN`, i.e. the tailnet host name plus port).
   Ports bind only to `BIND_ADDRESS` (default `127.0.0.1`). Never use `0.0.0.0`:
   Docker's published ports bypass UFW, which would expose the API publicly.
3. Create the config directory the backend writes the owner's `permissions.yaml` to
   (mounted at `/app/config`; the container runs as `nobody`, uid 65534):
   `mkdir -p config && sudo chown 65534 config`. The app writes the file on its first
   pass and keeps it in sync with the settings screen. Edit it on the host to change a
   verb's level; a level above a verb's ceiling is rejected (the settings screen says why)
   and the previous settings stay. If the directory isn't writable the settings still
   apply; only the file is missing, and the settings screen says so.
4. Start it:
   - with images from GHCR (built by `.github/workflows/images.yml` on every push to
     `main`). **Recommended:** set `IMAGE_TAG=<commit sha>` in `.env` so both services
     run the same immutable build, then `docker compose pull && docker compose up -d`.
     Leaving `IMAGE_TAG` unset uses `:latest`. That's convenient, but the two `:latest`
     tags move one after the other, so a pull during a publish can briefly mix commits.
   - or build on the host: `docker compose up -d --build`
5. Before relying on it, check CORS from the UI origin:
   `curl -si -X OPTIONS <api>/api/v1/jobs -H 'Origin: <FRONTEND_ORIGIN>' -H 'Access-Control-Request-Method: GET'`
   must answer with `access-control-allow-origin: <FRONTEND_ORIGIN>`.

6. Pin the sign-in keys (below).

`PUBLIC_API_BASE` is baked into the frontend bundle at build time. For GHCR images, set
the repository variable `PUBLIC_API_BASE` (Settings → Variables) so CI builds the right
URL in. Building on the host uses the value from `.env`.

## Pin the sign-in keys

The API checks every sign-in token against the frontend's public keys (its JWKS). Unpinned,
it fetches them from `http://frontend:3200/api/auth/jwks` over plain HTTP on the Compose
network, so a process that could answer as `frontend` there could serve its own key and
sign in as anyone. Pinned, the API trusts only the keys in `BETTER_AUTH_JWKS` and never
fetches. A malformed value stops the backend at startup.

Once the frontend is up (its first JWKS request creates its key pair), pin the current keys
and recreate the backend:

```bash
jwks=$(curl -fsS http://<BIND_ADDRESS>:<FRONTEND_PORT>/api/auth/jwks) &&
  printf "BETTER_AUTH_JWKS='%s'\n" "$jwks" >> .env &&
  docker compose up -d --force-recreate backend
```

If `curl` fails, nothing is written and nothing restarts. Delete the empty
`BETTER_AUTH_JWKS=` line the template left, so `.env` holds one value. The JWKS holds only
public keys, so it is safe in `.env`.

**Rotation.** The frontend changes its key only if its `jwks` collection is reset or key
rotation is turned on. Sign-in then fails with 401 ("Invalid or expired sign-in token")
until you pin again. To rotate without that gap, put both the old and the new key in the
`keys` array, recreate the backend, and drop the old key once tokens signed with it have
expired (they are short-lived, minutes).

## Updating

Set the new `IMAGE_TAG` (or keep `:latest`) and run the same command again:
`docker compose pull && docker compose up -d` (or `docker compose up -d --build`). It is idempotent: unchanged images keep their
containers running untouched, and only services whose image changed are recreated.
