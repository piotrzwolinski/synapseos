# SynapseOS — Azure Deployment Runbook (clean redeploy to POC)

Battle-tested end-to-end procedure, including every gotcha hit on 2026-08-25.
Follow top to bottom. Times: backend build ~10-15 min (Cython), rest minutes.

---

## 0. Environment & access reality

- Deploy is driven from an **AVD Linux box** running **PowerShell** (`PS /home/cl>`), with
  only `az` logged in. **No repo checkout, no working Docker daemon** on that box.
- `az account show` there defaults to subscription **`sub-sandbox-dev-01`**
  (tenant `23bf2ff5-...`). **The POC ACR/RG live in THAT subscription and resolve fine.**
  **Do NOT** `az account set` to the old `fb01fd65-...` id from stale docs — it breaks access.
- Because there's no source on the box, images are built by **`az acr build` pulling
  straight from the private GitHub repo** (needs a PAT). No Docker needed — ACR builds remotely.

## 1. Resource names

| Thing | Value |
|---|---|
| Resource Group | `rg-codeit-product-advisor-poc-01` |
| ACR (registry name) | `crcodeitproductadvisorpoc01` |
| ACR login server | `crcodeitproductadvisorpoc01.azurecr.io` |
| Container Apps Env | `cae-codeit-product-advisor-poc-01` |
| Backend app | `ca-backend-poc-01` (port 8000) |
| Frontend app | `ca-frontend-poc-01` (port 3000) |
| FalkorDB app | `ca-falkordb-poc-01` (port 6379, internal) |
| Storage acct / share | `stcodeitpocfalkordb01` / `falkordb-data` (binding `falkordbstorage`) |
| Backend URL | `https://ca-backend-poc-01.ambitiousstone-0cca5b82.westeurope.azurecontainerapps.io` |
| Frontend URL | `https://ca-frontend-poc-01.ambitiousstone-0cca5b82.westeurope.azurecontainerapps.io` |
| Repo | `https://github.com/piotrzwolinski/synapseos.git` (private) |

## 2. GitHub PAT (one-time, for az acr build + downloading seed on AVD)

Fine-grained token: **Repository access → Only `synapseos`**, **Permissions → Contents: Read-only**
(Metadata: Read is auto-added). Test on AVD:
```powershell
$PAT = "WKLEJ_TOKEN"
Invoke-RestMethod -Uri "https://api.github.com/repos/piotrzwolinski/synapseos" -Headers @{ Authorization = "Bearer $PAT"; "User-Agent"="avd" }
# expect: full_name=piotrzwolinski/synapseos, private=True
```

## 3. Build & deploy images (backend + frontend)

**Prereq in repo:** `backend/requirements-build.txt` must pin **`Cython==3.2.4`**.
Unpinned `Cython>=3.0` makes the ACR agent pull a 3.1.x that crashes cythonize with
`generate_sequence_as_array_code ... expected str instance, NoneType found`.

```powershell
$RG     = "rg-codeit-product-advisor-poc-01"
$ACR    = "crcodeitproductadvisorpoc01"
$BE_URL = "https://ca-backend-poc-01.ambitiousstone-0cca5b82.westeurope.azurecontainerapps.io"
$BE_TAG = "v4"    # BUMP every deploy — same tag = no new revision
$FE_TAG = "v4a"
$PAT = "WKLEJ_TOKEN"
$BRANCH = "backup/local-wip-2026-07-28"
$GIT = "https://$PAT@github.com/piotrzwolinski/synapseos.git#$BRANCH"

# Backend (Cython dist). Context = :backend subfolder, Dockerfile.dist. ~10-15 min.
az acr build --registry $ACR --image "product-advisor-backend:$BE_TAG" `
    --file Dockerfile.dist --timeout 1800 "${GIT}:backend"

# Frontend. NEXT_PUBLIC_API_URL is BUILD-time (baked in), not runtime.
az acr build --registry $ACR --image "product-advisor-frontend:$FE_TAG" `
    --file Dockerfile --build-arg "NEXT_PUBLIC_API_URL=$BE_URL" --timeout 900 "${GIT}:frontend"

# Roll the apps to the new images
az containerapp update --name ca-backend-poc-01  -g $RG --image "$ACR.azurecr.io/product-advisor-backend:$BE_TAG"
az containerapp update --name ca-frontend-poc-01 -g $RG --image "$ACR.azurecr.io/product-advisor-frontend:$FE_TAG"

Invoke-RestMethod -Uri "$BE_URL/health" -TimeoutSec 30   # -> status: healthy
```
Secrets (GEMINI_API_KEY, FALKORDB_PASSWORD, AUTH_USERS_JSON…) are already set on the apps;
`--image` updates do NOT clear them.

## 4. FalkorDB persistence — MUST verify, it was silently broken

**Root cause (2026-08-25):** the `falkordb/falkordb:latest` image **ignores `REDIS_ARGS`**
(`cat /proc/1/cmdline` → bare `redis-server *:6379`). Redis writes RDB to its default dir
**`/var/lib/falkordb/data`**. The Azure Files share was mounted at **`/data`**, but **`/data`
is just a dir holding a symlink `data -> /var/lib/falkordb/data`** — the mount at `/data` never
covered the real data dir, so **every container restart wiped the whole graph** (knowledge +
all user sessions/feedback).

**Fix — mount the share at the real data dir:**
```powershell
$RG = "rg-codeit-product-advisor-poc-01"
az containerapp show -n ca-falkordb-poc-01 -g $RG -o yaml > fk.yaml
(Get-Content fk.yaml) -replace 'mountPath:\s*/data\b','mountPath: /var/lib/falkordb/data' | Set-Content fk.yaml
az containerapp update -n ca-falkordb-poc-01 -g $RG --yaml fk.yaml
```
Verify inside the container:
```powershell
az containerapp exec --name ca-falkordb-poc-01 -g $RG --command "/bin/sh"
```
```sh
redis-cli -p 6379 -a FalkorPoc2024! --no-auth-warning CONFIG GET dir   # -> /var/lib/falkordb/data
ls -la /var/lib/falkordb/data/                                          # share files show here
```
Note: after this YAML round-trip, `requirepass` becomes active (`NOAUTH` without `-a`); the
app already uses `FalkorPoc2024!`, so it matches. **Always use the full `/var/lib/falkordb/data/...`
path — `/data/...` is the wrong, near-empty dir.**

## 5. Seed the knowledge graph (Layers 1-3, NO Layer-4/feedback)

**Generate locally** (needs local FalkorDB up on :6379, graph `synapse`):
```bash
backend/venv/bin/python scripts/export_knowledge_seed.py
# -> deploy/knowledge.cypher (974 nodes + 2654 rels) + deploy/run_knowledge_seed.sh
# excludes: Session, ActiveProject, ConversationTurn, TagUnit, ExpertReview, UserComment
# merge key: id > name > code   (commit both files)
```
**Deliver to the share, from AVD:**
```powershell
$RG="rg-codeit-product-advisor-poc-01"; $PAT="WKLEJ_TOKEN"
$H=@{ Authorization="Bearer $PAT"; Accept="application/vnd.github.raw"; "User-Agent"="avd" }
$base="https://api.github.com/repos/piotrzwolinski/synapseos/contents/deploy"; $ref="backup/local-wip-2026-07-28"
Invoke-WebRequest -Uri "$base/knowledge.cypher?ref=$ref"      -Headers $H -OutFile knowledge.cypher
Invoke-WebRequest -Uri "$base/run_knowledge_seed.sh?ref=$ref" -Headers $H -OutFile run_knowledge_seed.sh
$KEY = az storage account keys list --account-name stcodeitpocfalkordb01 -g $RG --query "[0].value" -o tsv
az storage file upload --account-name stcodeitpocfalkordb01 --account-key $KEY --share-name falkordb-data --source knowledge.cypher      --path knowledge.cypher
az storage file upload --account-name stcodeitpocfalkordb01 --account-key $KEY --share-name falkordb-data --source run_knowledge_seed.sh --path run_knowledge_seed.sh
```
If a running container was started **before** the upload, the SMB mount may not list the new
files — force a fresh revision so it remounts:
```powershell
az containerapp update -n ca-falkordb-poc-01 -g $RG --set-env-vars "REMOUNT_NONCE=1"
```
**Run the seed inside the container (one command at a time — the exec TTY garbles pasted blocks):**
```sh
sh /var/lib/falkordb/data/run_knowledge_seed.sh FalkorPoc2024!            # -> Done: 3628 ok, 0 failed
redis-cli -p 6379 -a FalkorPoc2024! --no-auth-warning GRAPH.QUERY synapse "MATCH (n) RETURN count(n)"   # -> 974
```

## 6. Create vector indexes (else the app crashes: "Invalid arguments for procedure 'db.idx.vector.queryNodes'")

The seed ships node embeddings but NOT indexes. Create them (dimension 3072, cosine):
```sh
redis-cli -p 6379 -a FalkorPoc2024! --no-auth-warning GRAPH.QUERY synapse "CREATE VECTOR INDEX FOR (c:Concept) ON (c.embedding) OPTIONS {dimension: 3072, similarityFunction: 'cosine'}"
redis-cli -p 6379 -a FalkorPoc2024! --no-auth-warning GRAPH.QUERY synapse "CREATE VECTOR INDEX FOR (k:Keyword) ON (k.embedding) OPTIONS {dimension: 3072, similarityFunction: 'cosine'}"
redis-cli -p 6379 -a FalkorPoc2024! --no-auth-warning SAVE
```
> Known caveat: the exporter writes embeddings as plain float arrays, not `vecf32(...)`.
> The index is created and the app no longer crashes, but semantic similar-case search may
> return empty. If that enrichment matters, re-export embeddings wrapped in `vecf32()`.

## 7. Persist + restart-test (prove it survives)

```sh
redis-cli -p 6379 -a FalkorPoc2024! --no-auth-warning SAVE
ls -la /var/lib/falkordb/data/dump.rdb        # ~2.7 MB with full graph
```
```powershell
az containerapp update -n ca-falkordb-poc-01 -g $RG --set-env-vars "PERSIST_TEST=1"   # new pod
# re-exec, then:
```
```sh
redis-cli -p 6379 -a FalkorPoc2024! --no-auth-warning GRAPH.QUERY synapse "MATCH (n) RETURN count(n)"   # still 974
```

## 8. End-to-end smoke test

Frontend URL → login (`mh` / `MHFind@r2026`) → switch to **Graph Reasoning** (violet button)
→ e.g. "I need a GDB housing, size 600×600, Galvanized FZ, airflow 2500 m³/h." → expect a real
product answer. If "No response received", pull backend logs:
```powershell
az containerapp logs show -n ca-backend-poc-01 -g rg-codeit-product-advisor-poc-01 --type console --tail 100
```

## Gotcha cheat-sheet

- `az acr build` from private git needs a PAT in the URL; no Docker required.
- **Pin `Cython==3.2.4`** or the ACR build crashes.
- **Bump image tags** every deploy or no new revision fires.
- **`REDIS_ARGS` is ignored** by the falkordb image — don't rely on it for dir/save/password.
- **`/data` is a symlink dir; real data dir is `/var/lib/falkordb/data`** — mount the share there.
- Use the **full `/var/lib/falkordb/data/...` path** for seed files.
- Run in-container commands **one at a time** (the exec TTY interleaves pasted lines).
- Create the **vector indexes** after seeding or the reasoning stream crashes.
- Stay on the AVD box's default subscription — don't switch to the stale `fb01fd65-...` id.
