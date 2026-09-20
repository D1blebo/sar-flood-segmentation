#!/bin/bash
# One-time download of the Sen1Floods11 hand-labeled subset needed for this project.
# Source: public GCS bucket gs://sen1floods11/v1.1/ (no credentials required).
set -euo pipefail

DEST="$(dirname "$0")/../data/sen1floods11"
BASE="https://storage.googleapis.com/sen1floods11/v1.1"

mkdir -p "$DEST/splits"
for f in flood_train_data.csv flood_valid_data.csv flood_test_data.csv flood_bolivia_data.csv; do
  [ -s "$DEST/splits/$f" ] || curl -sL --retry 3 "$BASE/splits/flood_handlabeled/$f" -o "$DEST/splits/$f"
done

for layer in S1Hand LabelHand JRCWaterHand S1OtsuLabelHand; do
  mkdir -p "$DEST/$layer"
done

cat "$DEST"/splits/*.csv | cut -d, -f1 | sed 's/_S1Hand\.tif$//' > "$DEST/_chip_ids.txt"
n=$(wc -l < "$DEST/_chip_ids.txt")
echo "Total chips: $n"

# Build a curl config listing only files that don't already exist (non-empty).
CFG="$DEST/_curl_jobs.cfg"
: > "$CFG"
count=0
while IFS= read -r chip; do
  for layer in S1Hand LabelHand JRCWaterHand S1OtsuLabelHand; do
    out="$DEST/$layer/${chip}_${layer}.tif"
    if [ ! -s "$out" ]; then
      {
        echo "url = \"$BASE/data/flood_events/HandLabeled/$layer/${chip}_${layer}.tif\""
        echo "output = \"$out\""
      } >> "$CFG"
      count=$((count+1))
    fi
  done
done < "$DEST/_chip_ids.txt"

echo "Files to fetch: $count"
if [ "$count" -gt 0 ]; then
  curl -sL --retry 2 --max-time 30 --parallel --parallel-max 16 -K "$CFG"
fi
echo "Download pass done."
