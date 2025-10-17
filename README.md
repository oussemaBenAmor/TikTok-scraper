Ce guide explique comment utiliser le scraper à partir d’une image Docker disponible sur Docker Hub. **Aucune étape de build n’est nécessaire**.

**Image Docker Hub :**

* Repository : [benamoroussema/tiktok-scraper](https://hub.docker.com/r/benamoroussema/tiktok-scraper)
* Tag : `v1`

---

 1) Installer Docker Desktop

* **Windows :** suivez le guide officiel pour installer Docker Desktop :

  * [https://docs.docker.com/desktop/setup/install/windows-install/](https://docs.docker.com/desktop/setup/install/windows-install/)
* Démarrez Docker Desktop et assurez-vous qu’il affiche “Running”.
* Si vous utilisez WSL, activez l’intégration WSL :

  * Docker Desktop > Paramètres > Ressources > Intégration WSL > activez votre distribution.

---

2) Créer un dossier local pour la sortie

Créez un dossier pour stocker le CSV généré.

* **PowerShell (Windows) :**

```powershell
mkdir data -Force
```

* **WSL/macOS/Linux :**

```bash
mkdir -p ./data
```

---

 3) Récupérer l’image

`docker run` téléchargera automatiquement l’image si nécessaire, mais vous pouvez la récupérer explicitement :

```bash
docker pull benamoroussema/tiktok-scraper:v1
```

---

4) Exécuter le scraper

Montez votre dossier local `data` dans le conteneur à `/data` et utilisez `--output` pour définir le chemin de sortie dans le conteneur.

* **PowerShell (Windows ; depuis le dossier projet/output) :**

```powershell
docker run --rm -v "${PWD}\data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
```

* **WSL/macOS/Linux (depuis le dossier projet/output) :**

```bash
docker run --rm -v "$(pwd)/data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
```

---

5) Où est créé le fichier de sortie ?

* À l’intérieur du conteneur, le scraper écrit dans le chemin passé à `--output` (ex : `/data/test.csv`).

* Sur votre machine, le fichier apparaît dans le dossier local que vous avez monté sur `/data` avec `-v`.

* **WSL, depuis le dossier projet :**

  * Commande :

    ```bash
    docker run --rm -v "$(pwd)/data:/data" benamoroussema/tiktok-scraper:v1 --username hugodecrypte --limit 5 --output /data/test.csv
    ```
  * Fichier généré sur votre machine (chemin Windows via WSL) :

    * `./data/test.csv` (ex : `/mnt/c/Users/MSI/Desktop/test technique/data/test.csv`)
  * Vérification :

    ```bash
    ls -lh "./data/test.csv"
    ```

**Remarque :** si vous oubliez le `-v` pour monter le dossier, le fichier sera créé uniquement dans le conteneur et sera perdu à sa fermeture.

---

6) À propos du Dockerfile

Vous n’avez pas besoin de build localement pour utiliser l’image préconstruite.
Si vous préférez build à partir du code source, le Dockerfile est inclus dans le repository (non décrit dans ce README).
