This guide explains how to run the scraper using a ready-to-use Docker image from Docker Hub. No build step is required.

Docker Hub image:
- Repository: [benamoroussema/tiktok-scraper](https://hub.docker.com/r/benamoroussema/tiktok-scraper)
- Tag: `v1`

 1) Install Docker Desktop

- Windows: follow the official guide to install Docker Desktop
  - https://docs.docker.com/desktop/setup/install/windows-install/
- Start Docker Desktop and ensure it shows “Running”.
- If you use WSL, enable WSL integration:
  - Docker Desktop > Settings > Resources > WSL Integration > enable your distro.


2) Create a local output folder

Create a folder to store the CSV output.

- PowerShell (Windows):
```powershell
mkdir data -Force
```

- WSL/macOS/Linux:
```bash
mkdir -p ./data
```



3) Pull the image

`docker run` will auto-pull if needed, but you can pull explicitly:

```bash
docker pull benamoroussema/tiktok-scraper:v1
```

4) Run the scraper

Mount your local `data` folder into the container at `/data`, and set `--output` to `/data/your-file.csv`.

- PowerShell (Windows; run from your project/output folder):
```powershell
docker run --rm -v "${PWD}\data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
```

- WSL/macOS/Linux (run from your project/output folder):
```bash
docker run --rm -v "$(pwd)/data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
```

5) Where is the output file created?

- Inside the container, the scraper writes to the path you pass to `--output` (e.g., `/data/test.csv`).
- On your machine, that file appears in the local folder you mounted to `/data` with `-v`.

- WSL, running from your project folder:
  - Command:
    ```bash
    docker run --rm -v "$(pwd)/data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
    ```
  - Resulting file on your machine (Windows path via WSL):
    - `./data/test.csv` (for example, `/mnt/c/Users/MSI/Desktop/test technique/data/test.csv`)
  - Verify:
    ```bash
    ls -lh "./data/test.csv"
    ```

If you forget the `-v` mount, the file is created inside the container and will be lost when the container exits.



## 7) Using a proxy (optional)

If your network region limits data, run with a proxy:
- PowerShell:
```powershell
docker run --rm -e HTTPS_PROXY="http://user:pass@host:port" -v "${PWD}\data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
```

- WSL/macOS/Linux:
```bash
docker run --rm -e HTTPS_PROXY="http://user:pass@host:port" -v "$(pwd)/data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
```

10) About the Dockerfile

You don’t need to build locally to run the prebuilt image. If you prefer to build from source, the Dockerfile is committed in the repository (not included in this README).