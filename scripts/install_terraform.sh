#!/usr/bin/env bash
set -Eeuo pipefail

if command -v terraform >/dev/null 2>&1; then
    echo "Terraform already installed:"
    terraform version
    exit 0
fi

echo "Installing prerequisites..."
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    gnupg \
    software-properties-common \
    wget

echo "Installing HashiCorp package signing key..."
tmp_key="$(mktemp)"
trap 'rm -f "$tmp_key"' EXIT

wget -qO- https://apt.releases.hashicorp.com/gpg \
    | gpg --dearmor > "$tmp_key"

sudo install -m 0644 \
    "$tmp_key" \
    /usr/share/keyrings/hashicorp-archive-keyring.gpg

codename="$(
    grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release \
    || lsb_release -cs
)"

echo "Adding HashiCorp APT repository..."
echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${codename} main" \
    | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null

echo "Installing Terraform..."
sudo apt-get update
sudo apt-get install -y terraform

echo
echo "Installed:"
terraform version
