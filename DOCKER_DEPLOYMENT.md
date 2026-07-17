# Docker Deployment

Run everything through Nginx:

```bash
docker compose up --build
```

Only Nginx publishes a host port. The frontend, backend, MongoDB, and GeoServer are reachable only inside the Compose network.

Default routes:

- Frontend: `http://localhost/`
- Backend API: `http://localhost/api/...`
- Backend health: `http://localhost/health`
- GeoServer: `http://localhost/geoserver/`

Large raster/database data is mounted from host directories, not baked into images:

- Backend rasters/logs/models: `${BACKEND_DATA_DIR:-./backend/data}` mounted at `/app/data`
- MongoDB files: `${MONGO_DATA_DIR:-/home/aman/iirs-data/mongodb}` mounted at `/data/db`

GeoServer is built as a project image (`iirs-geoserver`). The image copies the local `/home/aman/geoserver` install into `/opt/geoserver` at build time and runs that same `start.jar`, so the GeoServer runtime version and `data_dir` stay matched.

GeoServer mounts the backend raster data at `/app/data:ro`. Keep this mount: the backend publishes coverage stores with `file:/app/data/...` paths, so GeoServer needs the same path inside its own container.

The same backend data folder is also mounted into the GeoServer container at `/home/aman/web_world/Web_Project/irr/IIRS/backend/data:ro`. This helps old/local GeoServer coverage-store XML files that reference the original absolute host path continue to resolve inside Docker.

Useful logs:

```bash
docker compose logs -f nginx
docker compose logs -f backend
docker compose logs -f geoserver
docker compose logs -f mongodb
```

Backend app logs are also written under `${BACKEND_DATA_DIR}/logs`.
