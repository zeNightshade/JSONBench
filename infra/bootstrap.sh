#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/jsonbench-bootstrap.log) 2>&1
# New instance only: identify the dedicated 250 GiB EBS disk by exact size.
for attempt in $(seq 1 30); do
  mapfile -t disks < <(lsblk -dnbo NAME,SIZE,TYPE | awk '$2 == 268435456000 && $3 == "disk" {print "/dev/"$1}')
  [ "${#disks[@]}" -eq 1 ] && break
  sleep 2
done
[ "${#disks[@]}" -eq 1 ]
DATA_DEVICE="${disks[0]}"
if ! blkid "$DATA_DEVICE"; then
  # Refuse devices with partitions; never repurpose existing data.
  [ "$(lsblk -nr "$DATA_DEVICE" | wc -l)" -eq 1 ]
  mkfs.xfs "$DATA_DEVICE"
fi
mkdir -p /data
DATA_UUID=$(blkid -s UUID -o value "$DATA_DEVICE")
printf 'UUID=%s /data xfs defaults,nofail 0 2\n' "$DATA_UUID" >> /etc/fstab
mount /data
chown ec2-user:ec2-user /data
mkdir -p /data/docker
mkdir -p /etc/docker
printf '{"data-root":"/data/docker"}\n' > /etc/docker/daemon.json
# Do not perform a general OS upgrade: preserve the selected RHEL minor release.
dnf install -y dnf-plugins-core git python3.11 python3.11-pip tmux sysstat
dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker ec2-user
sudo -u ec2-user python3.11 -m pip install --user uv
printf 'Bootstrap complete\n'
