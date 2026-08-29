#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage:"
    echo "  $0 BACKUP_DIRECTORY SOURCE [SOURCE ...]"
    exit 1
fi

BACKUP_ROOT="$1"
shift

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_NAME="research-cloud-critical-state-${TIMESTAMP}.tar.gz"
CHECKSUM_NAME="${ARCHIVE_NAME}.sha256"

mkdir -p "$BACKUP_ROOT"

VALID_SOURCES=()

for source in "$@"; do
    if [ ! -e "$source" ]; then
        echo "ERROR: source does not exist: $source" >&2
        exit 1
    fi

    case "$source" in
        environment/local_secrets.env|*secret*|*.pem|*.key)
            echo "ERROR: refusing to include possible secret material: $source" >&2
            exit 1
            ;;
    esac

    VALID_SOURCES+=("$source")
done

echo "Creating backup:"
printf '  %s\n' "${VALID_SOURCES[@]}"

tar \
    --exclude='.git' \
    --exclude='*.tfstate' \
    --exclude='local_secrets.env' \
    -czf "$BACKUP_ROOT/$ARCHIVE_NAME" \
    "${VALID_SOURCES[@]}"

(
    cd "$BACKUP_ROOT"
    sha256sum "$ARCHIVE_NAME" > "$CHECKSUM_NAME"
)

echo
echo "Backup created:"
echo "  $BACKUP_ROOT/$ARCHIVE_NAME"
echo
echo "Checksum:"
cat "$BACKUP_ROOT/$CHECKSUM_NAME"
