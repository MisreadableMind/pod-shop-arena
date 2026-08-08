#!/bin/sh
# Boot: schema, then optionally the staged demo, then serve.
set -e

echo "→ applying schema"
python -m adapters.bootstrap

if [ "${PODARENA_SEED_DEMO}" = "true" ]; then
  echo "→ seeding the demo records"
  # Idempotent: existing records are left alone, so a redeploy does not wipe
  # anything and does not stack duplicate snapshots.
  python -m demo.seed || echo "  seeding failed; the app will still start"
fi

echo "→ serving on ${PORT:-8000}"
exec uvicorn api.app:app --host 0.0.0.0 --port "${PORT:-8000}" --forwarded-allow-ips '*'
