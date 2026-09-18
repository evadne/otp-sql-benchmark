#!/usr/bin/env bash
# Install the same server package as the retained Docker baseline, on Debian 13.
set -euo pipefail
test "$(id -u)" -eq 0
. /etc/os-release
test "$ID" = debian && test "$VERSION_ID" = 13
package_version=16.15-1.pgdg13+2
install -d -m 0755 /usr/share/postgresql-common/pgdg
curl --fail --silent --show-error \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
cat > /etc/apt/sources.list.d/otp-sql-benchmark-pgdg.sources <<'SOURCES'
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: trixie-pgdg
Architectures: amd64
Components: main
Signed-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
SOURCES
apt-get update
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends postgresql-common

# Prevent installation from creating an unrelated default cluster, then restore
# the policy. The benchmark manages its own isolated disposable cluster.
cluster_config=/etc/postgresql-common/createcluster.conf
config_backup=$(mktemp)
cp -p "$cluster_config" "$config_backup"
trap 'cp -p "$config_backup" "$cluster_config"; rm -f "$config_backup"' EXIT
sed -i '/^[[:space:]]*create_main_cluster[[:space:]]*=/d' "$cluster_config"
printf '\ncreate_main_cluster = false\n' >> "$cluster_config"
apt-get install -y --no-install-recommends \
  "postgresql-16=$package_version" "postgresql-client-16=$package_version"
/usr/lib/postgresql/16/bin/postgres --version
pg_lsclusters
