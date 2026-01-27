# How RotiBot Works: Complete Architecture Documentation

> A comprehensive guide to RotiBot's CI/CD pipeline, Kubernetes deployment, and system architecture

---

## Table of Contents

1. [Overview](#overview)
2. [CI/CD Pipeline](#cicd-pipeline)
3. [Kubernetes Architecture](#kubernetes-architecture)
4. [Communication Flow](#communication-flow)
5. [Security & Secrets Management](#security--secrets-management)
6. [Resource Allocation](#resource-allocation)
7. [Deployment Timeline](#deployment-timeline)
8. [Key Components](#key-components)
9. [Troubleshooting](#troubleshooting)

---

## Overview

RotiBot is a Discord bot deployed on Google Kubernetes Engine (GKE) with automated CI/CD via GitHub Actions. The system consists of two main components:

- **RotiBot Pod**: Discord bot application (Python/discord.py)
- **Lavalink Pod**: Music streaming server for audio playback

### Technology Stack

- **Language**: Python 3.12
- **Framework**: discord.py with lavalink.py
- **Container Registry**: Google Artifact Registry
- **Orchestration**: Google Kubernetes Engine (GKE)
- **CI/CD**: GitHub Actions
- **Audio**: Lavalink with YouTube plugin
- **Database**: MongoDB

---

## CI/CD Pipeline

### Pipeline Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GITHUB REPOSITORY                                 │
│                                                                             │
│  ┌──────────────┐                                                           │
│  │  Developer   │                                                           │
│  │  pushes to   │                                                           │
│  │    main      │                                                           │
│  └──────┬───────┘                                                           │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    .github/workflows/deploy.yml                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │ Trigger
         ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         GITHUB ACTIONS RUNNER                              │
│                                                                            │
│  Step 1: Authenticate to GCP                                               │
│  ┌────────────────────────────────────────────────────────┐                │
│  │ google-github-actions/auth@v2                          │                │
│  │ Uses: GKE_SA_KEY secret                                │                │
│  └────────────────────────────────────────────────────────┘                │
│         │                                                                  │
│         ▼                                                                  │
│  Step 2: Build Docker Image                                                │
│  ┌────────────────────────────────────────────────────────┐                │
│  │ docker build -t us-central1-docker.pkg.dev/            │                │
│  │   PROJECT_ID/rotibot/rotibot:COMMIT_SHA                │                │
│  └────────────────────────────────────────────────────────┘                │
│         │                                                                  │
│         ▼                                                                  │
│  Step 3: Push to Artifact Registry                                         │
│  ┌────────────────────────────────────────────────────────┐                │
│  │ docker push us-central1-docker.pkg.dev/...             │                │
│  └────────────────────────────────────────────────────────┘                │
│         │                                                                  │
│         ▼                                                                  │
│  Step 4: Create Kubernetes Secrets                                         │
│  ┌────────────────────────────────────────────────────────┐                │
│  │ kubectl create secret generic rotibot-secrets          │                │
│  │   --from-literal=TOKEN=***                             │                │
│  │   --from-literal=MUSIC_PASS=***                        │                │
│  │   --from-literal=YOUTUBE_REFRESH_TOKEN=***             │                │
│  │   ... (all environment variables)                      │                │
│  └────────────────────────────────────────────────────────┘                │
│         │                                                                  │
│         ▼                                                                  │
│  Step 5: Deploy to GKE                                                     │
│  ┌────────────────────────────────────────────────────────┐                │
│  │ kubectl apply -f kubernetes/lavalink-deployment.yaml   │                │
│  │ kubectl apply -f kubernetes/deployment.yaml            │                │
│  └────────────────────────────────────────────────────────┘                │
└────────────────────────────────────────────────────────────────────────────┘
         │
         │ Deploys to
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GOOGLE KUBERNETES ENGINE                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Steps Explained

1. **Authentication**: Uses service account key to authenticate with GCP
2. **Image Build**: Constructs Docker image with Python dependencies
3. **Registry Push**: Uploads image to Artifact Registry with commit SHA tag
4. **Secrets Update**: Creates/updates Kubernetes secrets from GitHub secrets
5. **Deployment**: Applies Kubernetes manifests, triggering rolling update

---

## Kubernetes Architecture

### Cluster Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    GKE CLUSTER (roti-cluster)                                │
│                    Zone: us-central1-a                                       │
│                    Node Pool: standard-pool (e2-standard-2)                  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐      │
│  │                        NAMESPACE: default                          │      │
│  │                                                                    │      │
│  │  ┌──────────────────────────────────────────────────────────────┐  │      │
│  │  │              ConfigMap: lavalink-config                      │  │      │
│  │  │  - application.yml (Lavalink configuration)                  │  │      │
│  │  └──────────────────────────────────────────────────────────────┘  │      │
│  │                                                                    │      │
│  │  ┌──────────────────────────────────────────────────────────────┐  │      │
│  │  │              Secret: rotibot-secrets                         │  │      │
│  │  │  - TOKEN                                                     │  │      │
│  │  │  - MUSIC_PASS                                                │  │      │
│  │  │  - YOUTUBE_REFRESH_TOKEN                                     │  │      │
│  │  │  - DATABASE                                                  │  │      │
│  │  │  - APPLICATION_ID                                            │  │      │
│  │  │  - ... (all bot environment variables)                       │  │      │
│  │  └──────────────────────────────────────────────────────────────┘  │      │
│  │                                                                  |──      │
│  │  ┌───────────────────────────────┐  ┌──────────────────────────┐ │        │
│  │  │  Deployment: lavalink         │  │  Deployment: rotibot     │ │        │
│  │  │  Replicas: 1                  │  │  Replicas: 1             │ │        │
│  │  │                               │  │                          │ │        │
│  │  │  ┌─────────────────────────┐  │  │  ┌────────────────────┐  │ │        │
│  │  │  │  Pod: lavalink-xxx      │  │  │  │  Pod: rotibot-xxx  │  │ │        │
│  │  │  │                         │  │  │  │                    │  │ │        │
│  │  │  │  Container: lavalink    │  │  │  │  InitContainer:    │  │ │        │
│  │  │  │  Image: fredboat/       │  │  │  │  wait-for-lavalink │  │ │        │
│  │  │  │    lavalink:latest      │  │  │  │  (busybox)         │  │ │        │
│  │  │  │                         │  │  │  │         │          │  │ │        │
│  │  │  │  Port: 2333             │  │  │  │         ▼          │  │ │        │
│  │  │  │                         │  │  │  │  Container:        │  │ │        │
│  │  │  │  Env:                   │  │  │  │    rotibot         │  │ │        │
│  │  │  │  - MUSIC_PASS ◄─────────┼─ ┼──┼──┤  Image: us-central1│  │ │        │
│  │  │  │  - YOUTUBE_REFRESH_TOKEN│  │  │  │   -docker.pkg.dev/ │  │ │        │
│  │  │  │    (from Secret)        │  │  │  │   PROJECT_ID/      │  │ │        │
│  │  │  │                         │  │  │  │   rotibot:latest   │  │ │        │
│  │  │  │  VolumeMounts:          │  │  │  │                    │  │ │        │
│  │  │  │  - application.yml ◄────┼─ ┼──┼──┤  Env:              │  │ │        │
│  │  │  │    (from ConfigMap)     │  │  │  │  - LAVALINK_HOST=  │  │ │        │
│  │  │  │                         │  │  │  │    lavalink        │  │ │        │
│  │  │  │  Resources:             │  │  │  │  - LAVALINK_PORT=  │  │ │        │
│  │  │  │  - CPU: 100m            │  │  │  │    2333            │  │ │        │
│  │  │  │  - Memory: 256Mi        │  │  │  │  - TOKEN, etc...   │  │ │        │
│  │  │  │                         │  │  │  │    (from Secret)   │  │ │        │
│  │  │  └─────────────────────────┘  │  │  │                    │  │ │        │
│  │  └───────────┬───────────────────┘  │  │  Resources:        │  │ │        │
│  │              │                      │  │  - CPU: 100m       │  │ │        │
│  │              ▼                      │  │  - Memory: 128Mi   │  │ │        │
│  │  ┌───────────────────────────┐      │  └────────────────────┘  │ │        │
│  │  │  Service: lavalink        │      └──────────────────────────┘ │        │
│  │  │  Type: ClusterIP          │                                   │        │
│  │  │  Port: 2333               │◄──────────────────────────────────┘        │
│  │  │                           │  (RotiBot connects to                      │
│  │  │  Selector:                │   lavalink:2333 internally)                │
│  │  │    app: lavalink          │                                            │
│  │  └───────────────────────────┘                                            │
│  └───────────────────────────────────────────────────────────────────────────┘  
└──────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

**Separate Pods for Lavalink and RotiBot**
- Independent lifecycle management
- Easier scaling and updates
- Better resource isolation
- Lavalink can restart without affecting bot connection to Discord

**InitContainer Pattern**
- Ensures Lavalink is ready before RotiBot starts
- Prevents connection errors on startup
- Uses busybox with netcat to poll Lavalink port

**Service Discovery**
- Kubernetes DNS resolves `lavalink` to the ClusterIP service
- No hardcoded IPs needed
- Automatic load balancing (if scaled)

---

## Communication Flow

### Discord → RotiBot → Lavalink → YouTube

```
┌──────────────┐                 ┌──────────────┐                 ┌──────────────┐
│   Discord    │                 │   RotiBot    │                 │  Lavalink    │
│   Server     │                 │     Pod      │                 │     Pod      │
└──────┬───────┘                 └──────┬───────┘                 └──────┬───────┘
       │                                │                                │
       │  1. User: /play song           │                                │
       ├───────────────────────────────►│                                │
       │                                │                                │
       │                                │  2. GET /v4/loadtracks?        │
       │                                │     identifier=ytsearch:song   │
       │                                ├───────────────────────────────►│
       │                                │                                │
       │                                │  3. Return track info          │
       │                                │◄───────────────────────────────┤
       │                                │                                │
       │                                │  4. Join voice channel         │
       │◄───────────────────────────────┤    (Discord WebSocket)         │
       │                                │                                │
       │  5. Voice connection           │                                │
       │    established                 │                                │
       ├───────────────────────────────►│                                │
       │                                │                                │
       │                                │  6. PATCH /v4/sessions/        │
       │                                │     .../players/GUILD_ID       │
       │                                │     (voice server info)        │
       │                                ├───────────────────────────────►│
       │                                │                                │
       │                                │  7. PATCH with track data      │
       │                                ├───────────────────────────────►│
       │                                │                                │
       │                                │                                │  8. YouTube
       │                                │                                │     API calls
       │                                │                                ├──────────►
       │                                │                                │
       │                                │  9. Stream audio data          │
       │                                │◄───────────────────────────────┤
       │                                │                                │
       │  10. Audio playback            │                                │
       │     in voice channel           │                                │
       │◄───────────────────────────────┤                                │
       │                                │                                │
```

### Protocol Details

1. **Discord Gateway**: WebSocket connection for bot commands
2. **Discord Voice**: UDP connection for audio streaming
3. **Lavalink REST API**: HTTP/REST for track management
4. **Lavalink WebSocket**: Real-time player updates
5. **YouTube Data API**: Search and metadata retrieval
6. **YouTube OAuth2**: Authentication for premium features

---

## Security & Secrets Management

### Secrets Flow

```
┌────────────────────┐
│  GitHub Secrets    │  (Stored in GitHub Repository Settings)
│                    │
│  - GKE_SA_KEY      │  ← Service Account JSON for GKE access
│  - GCP_PROJECT_ID  │  ← Google Cloud Project ID
│  - TOKEN           │  ← Discord Bot Token
│  - MUSIC_PASS      │  ← Lavalink Password
│  - YOUTUBE_REFRESH │  ← YouTube OAuth Token
│  - DATABASE        │  ← MongoDB Connection String
│  - etc...          │
└─────────┬──────────┘
          │
          │ GitHub Actions reads secrets
          │
          ▼
┌────────────────────┐
│  GitHub Actions    │
│  Workflow          │
│                    │
│  1. Authenticate   │
│  2. Build Image    │
│  3. Push Image     │
│  4. Create K8s     │──────┐
│     Secrets        │      │
└────────────────────┘      │
                            │
                            ▼
                ┌───────────────────────┐
                │  Kubernetes Secrets   │  (In GKE Cluster)
                │                       │
                │  rotibot-secrets:     │
                │  - TOKEN              │
                │  - MUSIC_PASS         │
                │  - YOUTUBE_REFRESH    │
                │  - DATABASE           │
                │  - etc...             │
                └───────┬───────────────┘
                        │
                        │ Injected as environment variables
                        │
          ┌─────────────┴─────────────┐
          │                           │
          ▼                           ▼
┌──────────────────┐        ┌──────────────────┐
│  Lavalink Pod    │        │  RotiBot Pod     │
│                  │        │                  │
│  Env:            │        │  Env:            │
│  - MUSIC_PASS    │        │  - TOKEN         │
│  - YOUTUBE_      │        │  - DATABASE      │
│    REFRESH_TOKEN │        │  - MUSIC_PASS    │
└──────────────────┘        └──────────────────┘
```

### Security Best Practices

✅ **Secrets never committed to Git**  
✅ **Service account with minimal permissions**  
✅ **Secrets encrypted in Kubernetes etcd**  
✅ **Secrets injected as environment variables (not mounted files)**  
✅ **Artifact Registry authentication via workload identity**  
✅ **No hardcoded credentials in code**

---

## Resource Allocation

### Node Capacity

```
┌─────────────────────────────────────────────────────────────┐
│  GKE Node (e2-standard-2)                                   │
│  Total Resources: 2 vCPUs, ~8GB RAM                         │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  System Pods (kube-proxy, CNI, etc.)                   │ │
│  │  CPU: ~0.7 cores | Memory: ~1GB                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Lavalink Pod                                          │ │
│  │  Request: 100m CPU, 256Mi RAM                          │ │
│  │  Limit: 500m CPU, 512Mi RAM                            │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  RotiBot Pod                                           │ │
│  │  Request: 100m CPU, 128Mi RAM                          │ │
│  │  Limit: 250m CPU, 256Mi RAM                            │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  Available: ~1.0 core CPU, ~6GB RAM                         │
└─────────────────────────────────────────────────────────────┘
```

### Resource Explanation

- **Requests**: Guaranteed resources reserved for the pod
- **Limits**: Maximum resources the pod can use
- **System Overhead**: ~30-40% of node resources for Kubernetes system components

### Why These Numbers?

- **Lavalink**: Needs more resources for audio processing and YouTube API calls
- **RotiBot**: Lightweight, mostly I/O bound (Discord API, database)
- **Headroom**: Extra capacity for spikes and future scaling

---

## Deployment Timeline

### Typical Deployment Flow

```
Time  Event
─────────────────────────────────────────────────────────────
0:00  Developer pushes to main branch
      │
0:05  GitHub Actions triggered
      │
0:10  ├─ Authenticate to GCP
      │
0:15  ├─ Build Docker image (RotiBot)
      │
0:45  ├─ Push to Artifact Registry
      │
1:00  ├─ Update Kubernetes secrets
      │
1:05  ├─ Apply Lavalink deployment
      │  └─ Lavalink pod starts
      │     └─ Downloads plugins (~30s)
      │        └─ Connects to YouTube
      │
1:40  ├─ Apply RotiBot deployment
      │  └─ InitContainer waits for Lavalink
      │     └─ RotiBot container starts
      │        └─ Connects to Discord
      │           └─ Connects to Lavalink
      │
2:00  ✓ Deployment complete
      └─ Bot is online and ready!
```

### Rolling Update Strategy

- **maxSurge**: 1 (can have 1 extra pod during update)
- **maxUnavailable**: 0 (always keep at least 1 pod running)
- **Result**: Zero-downtime deployments for the bot

---

## Key Components

### 1. RotiBot Application

**Purpose**: Discord bot handling commands and user interactions

**Key Features**:
- Command handling (slash commands)
- Music playback management
- Database operations (MongoDB)
- Statistics tracking
- Custom utilities and cogs

**Dependencies**:
- discord.py
- lavalink.py
- pymongo
- aiohttp

### 2. Lavalink Server

**Purpose**: Audio streaming and music playback

**Key Features**:
- YouTube music streaming
- Multiple source support (SoundCloud, Bandcamp, etc.)
- Audio filters and effects
- Queue management
- Low latency audio delivery

**Plugins**:
- YouTube plugin (with OAuth support)
- LavaSrc (additional sources)

### 3. GitHub Actions Workflow

**Purpose**: Automated CI/CD pipeline

**Triggers**:
- Push to `main` branch
- Manual workflow dispatch

**Outputs**:
- Docker image in Artifact Registry
- Updated Kubernetes deployments
- Deployed bot ready to use

### 4. Kubernetes Resources

**ConfigMap**: `lavalink-config`
- Stores Lavalink configuration
- Mounted as volume in Lavalink pod

**Secret**: `rotibot-secrets`
- Stores sensitive credentials
- Injected as environment variables

**Service**: `lavalink`
- ClusterIP type
- Internal DNS name for pod-to-pod communication
- Port 2333

**Deployments**: `lavalink`, `rotibot`
- Single replica each
- Rolling update strategy
- Resource limits enforced

---

## Troubleshooting

### Common Issues and Solutions

#### Bot Not Responding to Commands

**Symptoms**: Discord commands timeout or show "Application did not respond"

**Checks**:
```bash
# Check if bot pod is running
kubectl get pods

# Check bot logs
kubectl logs -f deployment/rotibot

# Check Discord gateway connection
kubectl logs deployment/rotibot | grep "Shard ID"
```

**Common Causes**:
- Bot token expired or invalid
- Pod crash-looping
- Network connectivity issues

#### Music Not Playing

**Symptoms**: Bot joins voice channel but no audio

**Checks**:
```bash
# Check Lavalink pod status
kubectl get pods | grep lavalink

# Check Lavalink logs
kubectl logs -f deployment/lavalink

# Verify Lavalink connection
kubectl logs deployment/rotibot | grep "Lavalink"
```

**Common Causes**:
- Lavalink not ready when bot starts
- YouTube OAuth token expired
- Network issues between pods
- Discord voice connection failed
- Youtube Cypto Challenge is failing (most common)

#### Deployment Fails

**Symptoms**: GitHub Actions workflow fails

**Checks**:
```bash
# Check workflow logs in GitHub Actions tab
# Common failure points:
# 1. Authentication - check GKE_SA_KEY secret
# 2. Image build - check Dockerfile syntax
# 3. Registry push - check permissions
# 4. kubectl apply - check manifest syntax
```

**Common Causes**:
- Invalid service account key
- Insufficient permissions
- Syntax errors in Kubernetes manifests
- Resource quota exceeded

#### Pod Stuck in Pending

**Symptoms**: Pod shows "Pending" status

**Checks**:
```bash
# Describe the pod to see events
kubectl describe pod <pod-name>

# Common reasons:
# - Insufficient CPU/memory
# - Node not ready
# - Image pull errors
```

**Solution**:
```bash
# Scale up node pool or adjust resource requests
gcloud container clusters resize roti-cluster \
  --num-nodes=2 \
  --zone=us-central1-a
```

---

## Useful Commands

### Development

```bash
# Test Docker build locally
docker build -t rotibot:test .

# Run locally with env file
docker run --env-file .env rotibot:test

# Check Python dependencies
pip freeze > requirements.txt
```

### Deployment

```bash
# Manual deploy (if not using GitHub Actions)
kubectl apply -f k8s/lavalink-deployment.yaml
kubectl apply -f k8s/deployment.yaml

# Force new deployment
kubectl rollout restart deployment/rotibot
kubectl rollout restart deployment/lavalink

# Check rollout status
kubectl rollout status deployment/rotibot
```

### Monitoring

```bash
# Get all resources
kubectl get all

# Watch pods
kubectl get pods -w

# Stream logs
kubectl logs -f deployment/rotibot
kubectl logs -f deployment/lavalink

# Get resource usage
kubectl top pods
kubectl top nodes
```

### Debugging

```bash
# Get pod shell
kubectl exec -it deployment/rotibot -- /bin/bash

# Check environment variables
kubectl exec deployment/rotibot -- env

# Test Lavalink connectivity from RotiBot pod
kubectl exec deployment/rotibot -- nc -zv lavalink 2333

# Get full pod description
kubectl describe pod <pod-name>
```

## Credits

- **Lavalink**: [lavalink-devs/Lavalink](https://github.com/lavalink-devs/Lavalink)
- **lavalink.py**: [devoxin/Lavalink.py](https://github.com/devoxin/Lavalink.py)
- **discord.py**: [Rapptz/discord.py](https://github.com/Rapptz/discord.py)
- **YouTube Plugin**: [lavalink-devs/youtube-source](https://github.com/lavalink-devs/youtube-source)

---

**Last Updated**: January 20, 2026  
**Version**: 1.0.0
**Maintainer**: @soupa.
