#!/usr/bin/env bash
# One-shot deploy of Companion V3 batch B to the Azure POC — run ON the AVD box.
#
#   PAT=<github_fine_grained_PAT>  FALKOR_PW='<falkordb_password>'  bash deploy_batch_b.sh
#
# Does the non-interactive parts automatically (build backend image, update the
# container app, upload both graph migrations to the FalkorDB file share) and then
# prints the ONE in-container step (az containerapp exec) that needs a TTY.
#
# Requires on the box: az logged in, internet to github.com. PAT needs Contents:Read.
set -uo pipefail

# ---- config (from deploy/AZURE_DEPLOYMENT_BRIEF.md + azure-deployment memory) ----
RG="rg-codeit-product-advisor-poc-01"
ACR="crcodeitproductadvisorpoc01"
ACR_SERVER="crcodeitproductadvisorpoc01.azurecr.io"
BACKEND_APP="ca-backend-poc-01"
FALKOR_APP="ca-falkordb-poc-01"
STORAGE_ACCT="stcodeitpocfalkordb01"
SHARE="falkordb-data"
REPO="piotrzwolinski/synapseos"
BRANCH="${BRANCH:-backup/local-wip-2026-07-28}"
BACKEND_URL="https://ca-backend-poc-01.ambitiousstone-0cca5b82.westeurope.azurecontainerapps.io"
VERSION="${VERSION:-vb$(date +%Y%m%d%H%M)}"   # unique tag -> forces a new revision

: "${PAT:?set PAT to a GitHub fine-grained token with Contents:Read}"
: "${FALKOR_PW:?set FALKOR_PW to the FalkorDB password}"

say() { printf '\n\033[1;36m==== %s ====\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mFAILED at: %s\033[0m\n' "$*"; exit 1; }

say "0/5  Plan: build backend:$VERSION from $BRANCH, update $BACKEND_APP, upload + run graph migrations A+B"

say "1/5  Build backend image ($VERSION) from git via az acr build"
az acr build --registry "$ACR" --image "product-advisor-backend:$VERSION" \
  --file Dockerfile.dist --timeout 1800 \
  "https://${PAT}@github.com/${REPO}.git#${BRANCH}:backend" || die "az acr build"

say "2/5  Point the backend container app at $VERSION"
az containerapp update -n "$BACKEND_APP" -g "$RG" \
  --image "${ACR_SERVER}/product-advisor-backend:$VERSION" -o none || die "containerapp update backend"

say "3/5  Download both graph migrations from git (raw + PAT)"
for f in fix_companion_v3.sh fix_companion_v3b.sh; do
  curl -fsSL -H "Authorization: token ${PAT}" \
    "https://raw.githubusercontent.com/${REPO}/${BRANCH}/deploy/${f}" -o "/tmp/${f}" \
    || die "download ${f} (is the branch pushed? is the PAT valid?)"
  echo "  got /tmp/${f} ($(wc -c </tmp/${f}) bytes)"
done

say "4/5  Upload both migrations to the FalkorDB file share"
STORAGE_KEY=$(az storage account keys list --account-name "$STORAGE_ACCT" -g "$RG" --query "[0].value" -o tsv) \
  || die "get storage key"
for f in fix_companion_v3.sh fix_companion_v3b.sh; do
  az storage file upload --account-name "$STORAGE_ACCT" --account-key "$STORAGE_KEY" \
    --share-name "$SHARE" --source "/tmp/${f}" --path "${f}" -o none || die "upload ${f}"
  echo "  uploaded ${f}"
done

say "5/5  Run the migrations inside the FalkorDB container"
# az containerapp exec usually needs an interactive TTY, so this may not run from a
# script. We try it; if it does not work, run the printed block manually (one paste).
EXEC_CMD="sh /var/lib/falkordb/data/fix_companion_v3.sh '${FALKOR_PW}'; sh /var/lib/falkordb/data/fix_companion_v3b.sh '${FALKOR_PW}'; redis-cli -a '${FALKOR_PW}' --no-auth-warning GRAPH.QUERY synapse SAVE; redis-cli -a '${FALKOR_PW}' --no-auth-warning GRAPH.QUERY synapse 'MATCH (n) RETURN count(n)'"
az containerapp exec -n "$FALKOR_APP" -g "$RG" --command "/bin/sh -c \"$EXEC_CMD\"" 2>/dev/null && MIG_OK=1 || MIG_OK=0

if [ "$MIG_OK" != "1" ]; then
  cat <<EOF

[manual step] az containerapp exec could not run non-interactively.
Exec into the FalkorDB container and paste the block below (one paste):
  az containerapp exec -n $FALKOR_APP -g $RG --command "/bin/sh"
  # then inside the container:
  sh /var/lib/falkordb/data/fix_companion_v3.sh '$FALKOR_PW'
  sh /var/lib/falkordb/data/fix_companion_v3b.sh '$FALKOR_PW'
  redis-cli -a '$FALKOR_PW' --no-auth-warning GRAPH.QUERY synapse SAVE
  redis-cli -a '$FALKOR_PW' --no-auth-warning GRAPH.QUERY synapse "MATCH (n) RETURN count(n)"
EOF
fi

say "Verify backend health"
curl -s --max-time 20 "$BACKEND_URL/health"; echo
echo
echo "Done. Backend image = $VERSION. If step 5 printed a manual block, run it, then test a query (GDB left-hinge + flange, GDMI rooftop)."
