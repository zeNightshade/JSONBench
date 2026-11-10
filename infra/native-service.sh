#!/bin/bash
# Installed root-owned as /usr/local/sbin/jsonbench-native-service.
set -euo pipefail
backend=${1:?backend required}
[[ ${2:-} == start ]] || exit 2
case "$backend" in
 mongodb) service=mongod; other=couchbase-server; thp=always; defrag=defer+madvise ;;
 couchbase) service=couchbase-server; other=mongod; thp=never; defrag=never ;;
 *) exit 2 ;;
esac
if systemctl is-active --quiet "$other"; then
 echo "Other database is active" >&2; exit 1
fi
echo "$thp" > /sys/kernel/mm/transparent_hugepage/enabled
echo "$defrag" > /sys/kernel/mm/transparent_hugepage/defrag
if [[ $backend == mongodb ]]; then
 echo 0 > /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_none
fi
sysctl -q -w vm.overcommit_memory=1 vm.swappiness=1
systemctl start "$service"
# Database processes may become ready after systemd marks the unit started.
for attempt in $(seq 1 120); do
 if [[ $backend == mongodb ]]; then
  if mongosh --quiet --eval 'quit(db.adminCommand({ping:1}).ok === 1 ? 0 : 1)' >/dev/null 2>&1; then exit 0; fi
 else
  # Initialized clusters require auth: HTTP401 confirms the HTTP service is up.
  # The matrix performs authenticated SDK/version checks before loading data.
  code=$(curl --max-time 5 --silent --output /dev/null --write-out "%{http_code}" http://127.0.0.1:8091/pools || true)
  if [[ $code == 200 || $code == 401 ]]; then
   if curl --max-time 5 --silent --output /dev/null http://127.0.0.1:8093/admin/ping; then exit 0; fi
  fi
 fi
 sleep 2
done
echo "Database readiness timed out" >&2
exit 1
