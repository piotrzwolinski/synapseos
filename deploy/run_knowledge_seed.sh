#!/bin/sh
# Auto-generated. Loads knowledge.cypher into FalkorDB graph 'synapse'.
# Usage: sh run_knowledge_seed.sh <password>
# Reads each statement as a SINGLE redis-cli arg ("$line") -> no shell re-parsing.
PASS="$1"
if [ -z "$PASS" ]; then echo "Usage: sh run_knowledge_seed.sh <password>"; exit 1; fi
DIR="$(dirname "$0")"
OK=0; FAIL=0; N=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  N=$((N+1))
  if redis-cli -a "$PASS" --no-auth-warning GRAPH.QUERY synapse "$line" > /dev/null 2>&1; then
    OK=$((OK+1))
  else
    FAIL=$((FAIL+1)); echo "FAIL[$N]: $line" | cut -c1-160
  fi
done < "$DIR/knowledge.cypher"
echo "Done: $OK ok, $FAIL failed, $N total"
