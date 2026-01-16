# AllDebrid Client Optimisé - Spécifications Techniques Complètes

**Version:** 1.0  
**Date:** 16 janvier 2025  
**Auteur:** Spécifications pour développement avec Claude Code

---

## Table des matières

1. [Vue d'ensemble du projet](#1-vue-densemble-du-projet)
2. [Architecture technique](#2-architecture-technique)
3. [Optimisations HDD](#3-optimisations-hdd)
4. [Configuration détaillée](#4-configuration-détaillée)
5. [API qBittorrent émulée](#5-api-qbittorrent-émulée)
6. [Performances attendues](#6-performances-attendues)
7. [Déploiement Docker](#7-déploiement-docker)
8. [Tests et validation](#8-tests-et-validation)
9. [Notes additionnelles](#9-notes-additionnelles)

---

## 1. Vue d'ensemble du projet

### 1.1 Objectif principal

Créer un **client AllDebrid optimisé** pour télécharger des fichiers REMUX 4K (60-100 Go) sur stockage HDD, sans problème de consommation RAM excessive.

### 1.2 Problèmes actuels avec rdt-client

- **OutOfMemoryException** sur fichiers REMUX 4K (> 60 Go)
- Consommation RAM : **2-4 Go** pour un seul téléchargement
- Crashes fréquents avec gros fichiers
- Impossible de télécharger plusieurs REMUX simultanément

### 1.3 Objectifs du nouveau client

- ✅ Consommation RAM : **< 100 Mo** par téléchargement
- ✅ Support stable des fichiers 100+ Go
- ✅ Optimisé pour stockage HDD (écriture séquentielle)
- ✅ Compatibilité totale API qBittorrent (Sonarr/Radarr)
- ✅ Vitesse de téléchargement maximale (fibre 8 Gb/s)

---

## 2. Architecture technique

### 2.1 Stack technologique

| Composant | Technologie | Description |
|-----------|-------------|-------------|
| **Backend API** | FastAPI (Python 3.12) | Framework async natif pour API REST |
| **Téléchargeur** | aria2c | Optimisé pour écriture séquentielle HDD |
| **Client HTTP** | httpx | Requêtes AllDebrid API async |
| **Base de données** | SQLite | État des torrents, historique |
| **Container** | Docker (Alpine Linux) | Image finale < 100 Mo |

### 2.2 Flux de données

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Sonarr/Radarr envoie torrent via API qBittorrent        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ 2. Client envoie torrent à AllDebrid API                    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ 3. AllDebrid télécharge torrent (30s - 2 min)               │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ 4. Client récupère lien DDL HTTPS                           │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ 5. aria2c télécharge avec optimisations HDD                 │
│    - Écriture séquentielle                                  │
│    - Buffer RAM 512 Mo                                       │
│    - 16 connexions max                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ 6. Fichier écrit dans /downloads/complete                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ 7. Sonarr/Radarr détecte et importe le fichier              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Optimisations HDD

### 3.1 Contexte

Le stockage est sur **disques durs (HDD)**, pas sur SSD/NVMe. Les HDD ont des caractéristiques spécifiques qui nécessitent une approche différente.

### 3.2 Caractéristiques HDD

| Métrique | Valeur | Impact |
|----------|--------|--------|
| **Lecture séquentielle** | 150-200 MB/s | ✅ OK pour fibre 8 Gb/s |
| **Random I/O (IOPS)** | 100-150 | ⚠️ Goulot d'étranglement |
| **Latence** | 10-15 ms | Nécessite buffering RAM |

### 3.3 Stratégies d'optimisation

#### 3.3.1 Écriture séquentielle forcée

**Problème :** Avec 64 connexions parallèles (optimal SSD), aria2 crée 64 fichiers temporaires et écrit de manière aléatoire sur le disque. Sur HDD, cela sature les IOPS et réduit drastiquement la vitesse.

**Solution :**
- Réduire à **16 connexions max**
- Forcer l'écriture séquentielle avec des segments larges (**1 Go**)
- Pré-allouer l'espace fichier pour éviter la fragmentation

#### 3.3.2 Buffer RAM intelligent

Utiliser la RAM comme buffer entre la fibre (800 MB/s) et le HDD (150 MB/s) :

```
AllDebrid (800 MB/s) → RAM buffer (512 Mo) → Batch write HDD (150 MB/s)
                          ↓
                   Absorbe les pics de vitesse
```

Configuration :
- **RAM buffer** : 512 Mo par téléchargement
- **Write batch** : 64 Mo
- **Flush interval** : 5 secondes

#### 3.3.3 Téléchargements séquentiels

Pour les **REMUX (> 20 Go)** : télécharger **1 seul fichier à la fois** pour éviter le thrashing HDD.

Pour les **petits fichiers (< 5 Go)** : autoriser **3 téléchargements simultanés**.

---

## 4. Configuration détaillée

### 4.1 Configuration aria2c pour HDD

```python
aria2_config = {
    "max-connection-per-server": 16,     # 16 connexions (vs 64 pour SSD)
    "split": 1,                          # Pas de split multi-segments
    "min-split-size": "1G",              # Segments énormes (force séquentiel)
    "file-allocation": "prealloc",       # Pré-alloue l'espace (évite fragmentation)
    "disk-cache": "128M",                # Cache disque 128 Mo
    "max-concurrent-downloads": 2,       # Max 2 downloads simultanés
    "enable-mmap": "true",               # Memory-mapped I/O
    "max-overall-download-limit": "0",   # Pas de limite (fibre)
    "continue": "true",                  # Reprise automatique
}
```

### 4.2 Variables d'environnement Docker

| Variable | Défaut | Description |
|----------|--------|-------------|
| `ALLDEBRID_API_KEY` | *(requis)* | Clé API AllDebrid |
| `STORAGE_TYPE` | `auto` | auto / hdd / ssd |
| `ARIA2_CONNECTIONS` | `16` | Connexions par serveur |
| `ARIA2_SPLIT` | `1` | Split segments |
| `ARIA2_DISK_CACHE` | `128M` | Cache disque |
| `RAM_BUFFER_PER_DOWNLOAD` | `512M` | Buffer RAM par fichier |
| `MAX_CONCURRENT_DOWNLOADS` | `2` | DL simultanés max |
| `WRITE_BATCH_SIZE` | `64M` | Taille batch écriture |
| `FLUSH_INTERVAL` | `5` | Flush disque (secondes) |
| `ENABLE_MMAP` | `true` | Memory-mapped I/O |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING |
| `ENABLE_DASHBOARD` | `false` | Dashboard web monitoring |
| `AUTO_EXTRACT` | `false` | Décompression auto .rar |

### 4.3 Détection automatique du type de stockage

Le client doit détecter automatiquement si le stockage est HDD ou SSD :

```python
import psutil
import os

def detect_storage_type(path="/downloads"):
    """
    Détecte si le chemin est sur HDD ou SSD
    
    Returns:
        "hdd" ou "ssd"
    """
    # Utiliser psutil pour détecter le type de disque
    # Si rotation speed > 0 → HDD
    # Si rotation speed = 0 → SSD
    # Fallback : vérifier performance I/O
    
    # Exemple de détection
    partitions = psutil.disk_partitions()
    for partition in partitions:
        if path.startswith(partition.mountpoint):
            # Logique de détection ici
            pass
    
    return "hdd"  # ou "ssd"
```

Si `STORAGE_TYPE=auto`, le client détecte automatiquement et applique la config appropriée.

### 4.4 Stratégie de queue intelligente

```python
queue_strategy = {
    "mode": "smart",
    "simultaneous_on_hdd": 1,        # 1 seul REMUX à la fois si HDD
    "simultaneous_small_files": 3,   # 3 petits fichiers OK (< 5 Go)
    "size_threshold": "20G",         # Seuil REMUX
}
```

**Comportement :**
- REMUX 80 Go : téléchargé seul (150 MB/s)
- 3x Films 1080p (8 Go) : simultanés OK (50 MB/s chacun)

---

## 5. API qBittorrent émulée

### 5.1 Endpoints requis

Le client doit émuler l'API qBittorrent pour être compatible avec Sonarr et Radarr.

#### Endpoints essentiels :

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/v2/auth/login` | POST | Authentification (peut être vide) |
| `/api/v2/torrents/add` | POST | Ajouter torrent - Params: `urls`, `category` |
| `/api/v2/torrents/info` | GET | Liste torrents avec état, progression |
| `/api/v2/torrents/delete` | POST | Supprimer torrent - Param: `hashes` |
| `/api/v2/torrents/pause` | POST | Mettre en pause |
| `/api/v2/torrents/resume` | POST | Reprendre |
| `/api/v2/app/version` | GET | Version API (retourner `v4.5.0`) |
| `/api/v2/app/preferences` | GET | Préférences (retourner config basique) |

### 5.2 Format de réponse `/api/v2/torrents/info`

```json
[
  {
    "hash": "abc123def456...",
    "name": "Mission.Impossible.2025.REMUX.mkv",
    "size": 85899345920,
    "progress": 0.45,
    "dlspeed": 157286400,
    "upspeed": 0,
    "eta": 520,
    "state": "downloading",
    "category": "radarr",
    "save_path": "/downloads/complete",
    "completion_on": 0,
    "added_on": 1705363200,
    "completed": 38654705664,
    "downloaded": 38654705664,
    "uploaded": 0,
    "ratio": 0.0
  }
]
```

### 5.3 États des torrents (state)

| État | Description |
|------|-------------|
| `queued` | En attente (AllDebrid traite le torrent) |
| `downloading` | En cours de téléchargement |
| `completed` | Terminé |
| `paused` | En pause |
| `error` | Erreur (torrent invalide, AllDebrid erreur, etc.) |

### 5.4 Calcul du hash

Le hash du torrent doit être **déterministe** et calculé à partir du magnet link ou du fichier .torrent :

```python
import hashlib

def calculate_torrent_hash(magnet_or_file):
    """
    Calcule le hash SHA1 du torrent
    Compatible avec qBittorrent
    """
    if magnet_or_file.startswith("magnet:"):
        # Extraire le hash du magnet link
        # magnet:?xt=urn:btih:HASH
        import re
        match = re.search(r'btih:([a-fA-F0-9]{40})', magnet_or_file)
        if match:
            return match.group(1).lower()
    else:
        # Calculer hash du fichier .torrent
        # (Utiliser bencodepy pour lire le torrent)
        pass
    
    return hashlib.sha1(magnet_or_file.encode()).hexdigest()
```

---

## 6. Performances attendues

### 6.1 Benchmarks cibles (HDD)

| Scénario | Vitesse attendue | Temps | RAM |
|----------|------------------|-------|-----|
| **REMUX 4K (80 Go)** | 140-160 MB/s | ~9-10 min | ~80 Mo |
| **Film 1080p (10 Go)** | 150-180 MB/s | ~1 min | ~60 Mo |
| **Client idle** | - | - | ~30 Mo |
| **5x REMUX simultanés** | ⚠️ Non recommandé | HDD thrashing | - |

**Limite théorique :** ~150-180 MB/s (HDD, pas la fibre)

### 6.2 Comparaison rdt-client vs client optimisé

| Critère | rdt-client actuel | Client optimisé |
|---------|-------------------|-----------------|
| **RAM REMUX 4K** | 2-4 Go (crash ❌) | ~80 Mo ✅ |
| **Stabilité gros fichiers** | OutOfMemory ❌ | Parfait ✅ |
| **Vitesse HDD** | Bonne | Optimisée séquentiel ✅ |
| **Config Sonarr/Radarr** | Simple | Simple (API identique) |
| **Maintenance** | Active | À développer |

### 6.3 Métriques à monitorer

Le client doit exposer des métriques pour monitoring :

```python
metrics = {
    "memory_usage_mb": 78.5,              # RAM actuelle
    "active_downloads": 1,                # Nombre de DL actifs
    "download_speed_mbps": 145.2,         # Vitesse totale
    "storage_type": "hdd",                # Type détecté
    "torrents_queued": 0,                 # En attente
    "torrents_downloading": 1,            # En cours
    "torrents_completed": 42,             # Terminés
    "torrents_errored": 0,                # Erreurs
    "alldebrid_api_calls": 156,           # Appels API
    "alldebrid_api_errors": 0,            # Erreurs API
    "uptime_seconds": 86400,              # Uptime
}
```

---

## 7. Déploiement Docker

### 7.1 docker-compose.yml complet

```yaml
version: '3.8'

services:
  alldebrid-client:
    image: alldebrid-client:latest
    container_name: alldebrid-client
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Paris
      
      # AllDebrid
      - ALLDEBRID_API_KEY=${ALLDEBRID_API_KEY}
      
      # Optimisations HDD (auto-détecté par défaut)
      - STORAGE_TYPE=auto
      - ARIA2_CONNECTIONS=16
      - ARIA2_SPLIT=1
      - ARIA2_DISK_CACHE=128M
      - RAM_BUFFER_PER_DOWNLOAD=512M
      - MAX_CONCURRENT_DOWNLOADS=2
      
      # Écriture optimisée
      - FILE_ALLOCATION=prealloc
      - WRITE_BATCH_SIZE=64M
      - ENABLE_MMAP=true
      
      # Logging
      - LOG_LEVEL=INFO
      
      # Features optionnelles
      - ENABLE_DASHBOARD=false
      - AUTO_EXTRACT=false
      
    volumes:
      - /mnt/MainPool/apps/alldebrid-client:/config
      - /mnt/MainPool/apps/downloads:/downloads
      
    ports:
      - 6500:6500      # API qBittorrent
      - 8080:8080      # Dashboard (si activé)
      
    dns:
      - 1.1.1.1
      - 1.0.0.1
      
    deploy:
      resources:
        limits:
          memory: 2G      # 2 Go (pour les buffers RAM)
        reservations:
          memory: 512M
    
    restart: unless-stopped

networks:
  default:
    name: media-stack
```

### 7.2 Structure du projet

```
alldebrid-client/
├── src/
│   ├── api/              # API qBittorrent émulée (FastAPI)
│   │   ├── __init__.py
│   │   ├── routes.py     # Endpoints API
│   │   ├── models.py     # Modèles de données Pydantic
│   │   └── auth.py       # Authentification (optionnelle)
│   │
│   ├── downloader/       # Wrapper aria2
│   │   ├── __init__.py
│   │   ├── aria2.py      # Contrôle aria2c via RPC
│   │   ├── config.py     # Config HDD/SSD auto-detect
│   │   └── queue.py      # Gestion queue intelligente
│   │
│   ├── alldebrid/        # Client AllDebrid
│   │   ├── __init__.py
│   │   ├── client.py     # API AllDebrid async (httpx)
│   │   └── models.py     # Modèles réponses API
│   │
│   ├── database/         # SQLite
│   │   ├── __init__.py
│   │   ├── models.py     # SQLAlchemy models
│   │   └── crud.py       # CRUD operations
│   │
│   ├── monitoring/       # Monitoring (optionnel)
│   │   ├── __init__.py
│   │   ├── dashboard.py  # Dashboard web
│   │   └── metrics.py    # Métriques Prometheus
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── storage.py    # Détection HDD/SSD
│   │   └── logger.py     # Configuration logging
│   │
│   └── main.py           # Point d'entrée FastAPI
│
├── tests/                # Tests unitaires
│   ├── test_api.py
│   ├── test_alldebrid.py
│   ├── test_downloader.py
│   └── test_integration.py
│
├── docker/
│   └── Dockerfile        # Multi-stage build
│
├── scripts/
│   └── migrate_from_rdt.py  # Migration depuis rdt-client
│
├── docker-compose.yml
├── requirements.txt      # Dépendances Python
├── README.md
├── BENCHMARK.md          # Résultats tests perf
└── API.md                # Documentation API
```

### 7.3 Dockerfile multi-stage

```dockerfile
# Stage 1: Builder
FROM python:3.12-alpine AS builder

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    aria2

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-alpine

# Install runtime dependencies
RUN apk add --no-cache \
    aria2 \
    sqlite \
    unrar

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application
WORKDIR /app
COPY src/ ./src/

# Create directories
RUN mkdir -p /config /downloads

# Expose ports
EXPOSE 6500 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:6500/api/v2/app/version || exit 1

# Run application
CMD ["python", "src/main.py"]
```

### 7.4 requirements.txt

```txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
httpx==0.26.0
sqlalchemy==2.0.25
aiosqlite==0.19.0
pydantic==2.5.3
python-multipart==0.0.6
aria2p==0.11.3
psutil==5.9.7
python-dotenv==1.0.0

# Optionnel - Monitoring
prometheus-client==0.19.0
```

---

## 8. Tests et validation

### 8.1 Tests unitaires requis

- ✅ **API qBittorrent** - Test de tous les endpoints
- ✅ **AllDebrid API** - Upload torrent, récupération liens DDL
- ✅ **aria2 wrapper** - Lancement, monitoring, crash recovery
- ✅ **Gestion mémoire** - Vérification pas de leak RAM
- ✅ **Détection stockage** - HDD vs SSD auto-detect
- ✅ **Queue management** - Priorités, concurrent downloads

### 8.2 Tests d'intégration

1. **Test téléchargement fichier 1 Go** (benchmark baseline)
2. **Test REMUX 4K (80 Go)** - vérifier RAM < 100 Mo
3. **Test 2 REMUX simultanés** - stabilité
4. **Test interruption réseau** - reprise automatique
5. **Test intégration Sonarr** - ajout série, monitoring progression
6. **Test intégration Radarr** - ajout film, vérification import
7. **Test AllDebrid erreur** - gestion erreur API
8. **Test disque plein** - gestion erreur espace disque

### 8.3 Critères de validation

| Critère | Objectif | Statut |
|---------|----------|--------|
| RAM max REMUX 80 Go | < 100 Mo | ⏳ À valider |
| Vitesse téléchargement HDD | > 140 MB/s | ⏳ À valider |
| Stabilité 2 REMUX simultanés | 0 crash | ⏳ À valider |
| Compatibilité API qBittorrent | 100% | ⏳ À valider |
| Temps REMUX 80 Go | < 10 min | ⏳ À valider |
| Détection auto HDD/SSD | 100% précision | ⏳ À valider |

### 8.4 Script de test de performance

```python
#!/usr/bin/env python3
"""
Benchmark script for AllDebrid client
"""
import time
import psutil
import httpx

def benchmark_download(torrent_url, expected_size_gb):
    """
    Benchmark un téléchargement et mesure:
    - Temps total
    - Vitesse moyenne
    - RAM max utilisée
    - Stabilité
    """
    # Ajouter le torrent
    response = httpx.post(
        "http://localhost:6500/api/v2/torrents/add",
        data={"urls": torrent_url}
    )
    
    # Monitoring
    start_time = time.time()
    max_memory = 0
    
    while True:
        # Récupérer état
        info = httpx.get("http://localhost:6500/api/v2/torrents/info").json()
        
        if info[0]["state"] == "completed":
            break
        
        # Mesurer RAM
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        max_memory = max(max_memory, memory_mb)
        
        time.sleep(1)
    
    elapsed = time.time() - start_time
    speed_mbps = (expected_size_gb * 1024) / elapsed
    
    print(f"Temps: {elapsed:.2f}s")
    print(f"Vitesse: {speed_mbps:.2f} MB/s")
    print(f"RAM max: {max_memory:.2f} Mo")

if __name__ == "__main__":
    # Test REMUX 80 Go
    benchmark_download("magnet:?xt=urn:btih:...", 80)
```

---

## 9. Notes additionnelles

### 9.1 Fonctionnalités bonus (optionnelles)

- **Dashboard web** - Interface de monitoring temps réel (port 8080)
- **Métriques Prometheus** - Export pour Grafana
- **Notifications** - Discord/Telegram/Email (webhooks)
- **Auto-extraction .rar** - Décompression automatique avec unrar
- **Support SSD cache** - Téléchargement sur SSD puis move HDD
- **RAM disk optionnel** - Pour utilisateurs avec 64+ Go RAM
- **Rate limiting** - Limiter vitesse selon heure de la journée
- **Post-processing hooks** - Scripts personnalisés après téléchargement

### 9.2 Gestion des erreurs

Le client doit gérer proprement ces cas d'erreur :

1. **AllDebrid API erreur** (503, timeout, quota dépassé)
   - Retry automatique avec backoff exponentiel
   - Log détaillé de l'erreur
   - État torrent → `error`

2. **Disque plein**
   - Pause automatique des téléchargements
   - Notification (si configuré)
   - Log erreur claire

3. **Interruption réseau**
   - aria2 gère la reprise automatique
   - Si échec après 3 tentatives → état `error`

4. **Torrent invalide** (magnet invalide, fichier corrompu)
   - État → `error`
   - Message d'erreur explicite

5. **AllDebrid torrent non disponible**
   - Retry après 30s
   - Si échec après 5 min → état `error`

### 9.3 Logging structuré

Utiliser des logs JSON structurés pour faciliter le debugging :

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": record.created,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        })

# Configuration
logger = logging.getLogger("alldebrid-client")
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
```

### 9.4 Migration depuis rdt-client

Fournir un script de migration :

```python
#!/usr/bin/env python3
"""
Migrer depuis rdt-client vers alldebrid-client
- Copie la DB SQLite
- Convertit le schéma
- Préserve l'historique
"""

import sqlite3
import shutil

def migrate_from_rdt(rdt_db_path, new_db_path):
    # Copier la DB
    shutil.copy(rdt_db_path, new_db_path)
    
    # Convertir le schéma
    conn = sqlite3.connect(new_db_path)
    cursor = conn.cursor()
    
    # Migration SQL
    cursor.execute("""
        -- Adapter le schéma ici
        ALTER TABLE torrents ADD COLUMN storage_type TEXT DEFAULT 'hdd';
    """)
    
    conn.commit()
    conn.close()
```

### 9.5 Documentation à fournir

1. **README.md** - Installation, configuration, troubleshooting
2. **BENCHMARK.md** - Résultats tests de performance
3. **API.md** - Documentation endpoints API
4. **MIGRATION.md** - Guide migration depuis rdt-client
5. **CONTRIBUTING.md** - Guide pour contributeurs

### 9.6 Timeline de développement

| Phase | Tâches | Durée |
|-------|--------|-------|
| **Phase 1** | Core (API qBittorrent, AllDebrid, aria2, Docker) | 48h |
| **Phase 2** | Optimisations (tuning RAM, benchmarks, error handling) | 24h |
| **Phase 3** | Polish (dashboard, docs, tests) | 12h |

**Total estimé :** 3-4 jours de développement

### 9.7 Commandes Docker utiles

```bash
# Build l'image
docker build -t alldebrid-client:latest .

# Run en dev (avec logs)
docker-compose up

# Run en background
docker-compose up -d

# Voir les logs
docker-compose logs -f alldebrid-client

# Restart
docker-compose restart alldebrid-client

# Stats RAM/CPU en temps réel
docker stats alldebrid-client

# Shell dans le container
docker exec -it alldebrid-client sh

# Cleanup
docker-compose down
docker system prune -a
```

### 9.8 Configuration Sonarr/Radarr

**Dans Sonarr/Radarr :**

1. Settings → Download Clients → Add (+)
2. Sélectionner **qBittorrent**
3. Configuration :
   - Name : `AllDebrid Client`
   - Host : `alldebrid-client` (ou IP)
   - Port : `6500`
   - Username : (laisser vide)
   - Password : (laisser vide)
   - Category : `sonarr` ou `radarr`
4. Test → Save

**Remote Path Mappings** (normalement pas nécessaire) :
- Host : `alldebrid-client`
- Remote Path : `/downloads/complete`
- Local Path : `/downloads/complete`

---

## Annexes

### A. Endpoints API complets

```
GET  /api/v2/app/version
GET  /api/v2/app/preferences
POST /api/v2/auth/login
POST /api/v2/torrents/add
GET  /api/v2/torrents/info
POST /api/v2/torrents/delete
POST /api/v2/torrents/pause
POST /api/v2/torrents/resume
POST /api/v2/torrents/recheck
GET  /api/v2/torrents/properties
GET  /api/v2/torrents/trackers
GET  /api/v2/torrents/files
```

### B. AllDebrid API endpoints utilisés

```
POST https://api.alldebrid.com/v4/magnet/upload
GET  https://api.alldebrid.com/v4/magnet/status
GET  https://api.alldebrid.com/v4/link/unlock
GET  https://api.alldebrid.com/v4/user
```

### C. Variables d'environnement complètes

Voir section 4.2 pour la liste complète.

---

## Conclusion

Ce document fournit toutes les spécifications techniques nécessaires pour développer un client AllDebrid optimisé pour HDD, compatible avec Sonarr/Radarr, et résolvant les problèmes de RAM de rdt-client.

**Objectifs principaux :**
- ✅ RAM < 100 Mo par REMUX
- ✅ Vitesse 140-160 MB/s sur HDD
- ✅ Stabilité totale (0 crash)
- ✅ API qBittorrent 100% compatible

**Prêt pour développement avec Claude Code !** 🚀
