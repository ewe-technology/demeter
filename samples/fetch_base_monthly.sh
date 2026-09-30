#!/bin/bash
# Base USDC/WETH 0.05% minute data, month by month (keeps memory bounded), into $OUT.
# usage: fetch_base_monthly.sh <first month YYYY-MM> <last day YYYY-MM-DD> <out dir>
set -o pipefail
cd "$(dirname "$0")"
export ETH_RPC=${ETH_RPC:-https://base.gateway.tenderly.co} STEP=${STEP:-1000} THREADS=${THREADS:-8}
POOL=0xd0b53d9277642d899df5c87a3966a349a798f224
m=$1; last=$2; out=$3
while [[ "$m-01" < "$last" || "$m-01" == "$last" ]]; do
  s="$m-01"
  e=$(python3 -c "import datetime as d,calendar as c;y,mo=map(int,'$m'.split('-'));x=d.date(y,mo,c.monthrange(y,mo)[1]);print(min(x,d.date.fromisoformat('$last')))")
  if [ -f "$out/ethereum-$POOL-$e.minute.csv" ]; then echo "skip $s..$e"; else
    echo "$(date +%T) fetch $s..$e"
    ../.venv-lab/bin/python fetch_uni_minute.py $POOL "$s" "$e" "$out" | tail -1 || echo "FAILED $s..$e"
  fi
  m=$(python3 -c "y,mo=map(int,'$m'.split('-'));mo+=1;y+=mo>12;mo=mo-12 if mo>12 else mo;print(f'{y}-{mo:02d}')")
done
echo "all months done"
