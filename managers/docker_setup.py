"""Shared Docker provisioning for protocol managers.

Installs a *real* Docker Engine (Docker CE) across the common distro families,
then enables and starts the daemon.

Why this is centralized and careful about the source of the package:

* On RHEL-family hosts (Alma/Rocky/CentOS/RHEL/Oracle) the distro `docker`
  package pulls in **podman-docker** — a podman shim that owns /usr/bin/docker.
  Podman enforces fully-qualified image names, so a non-interactive
  `docker build` of a Dockerfile that uses a short base image
  (`FROM python:3.14-slim`) fails with "short-name resolution enforced but
  cannot prompt without a TTY". So on these hosts we add Docker's official
  repository, install `docker-ce`, and remove the podman shim.
* On Debian/Ubuntu we likewise prefer Docker's official repo, falling back to
  the distro `docker.io` (which is real Docker) if the repo step fails.
* openSUSE (zypper) and Arch (pacman) ship a real Docker as `docker`, so we use
  the native package there.
"""

INSTALL_DOCKER_SCRIPT = r"""
set -u

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y || true
    apt-get install -y ca-certificates curl gnupg || true
    install -m 0755 -d /etc/apt/keyrings
    . /etc/os-release
    DISTRO="$ID"
    case "$ID" in
        linuxmint|pop|elementary|zorin|neon) DISTRO="ubuntu" ;;
        kali|parrot|raspbian) DISTRO="debian" ;;
    esac
    if [ ! -s /etc/apt/keyrings/docker.asc ]; then
        curl -fsSL "https://download.docker.com/linux/${DISTRO}/gpg" -o /etc/apt/keyrings/docker.asc \
            && chmod a+r /etc/apt/keyrings/docker.asc
    fi
    CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${DISTRO} ${CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    if apt-get update -y && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
        :
    else
        # Official repo unavailable for this release — fall back to distro docker
        # (docker.io is real Docker on Debian/Ubuntu).
        rm -f /etc/apt/sources.list.d/docker.list
        apt-get update -y || true
        apt-get install -y docker.io || exit 1
    fi

elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
    if command -v dnf >/dev/null 2>&1; then PM=dnf; else PM=yum; fi
    . /etc/os-release
    # Drop the podman-docker shim so it does not own /usr/bin/docker and so the
    # docker-ce-cli install does not hit a file conflict. Keep podman itself.
    $PM remove -y podman-docker >/dev/null 2>&1 || true
    $PM install -y dnf-plugins-core >/dev/null 2>&1 || $PM install -y yum-utils >/dev/null 2>&1 || true
    case "$ID" in
        fedora) REPO="https://download.docker.com/linux/fedora/docker-ce.repo" ;;
        *)      REPO="https://download.docker.com/linux/centos/docker-ce.repo" ;;
    esac
    # config-manager syntax differs across dnf4/dnf5/yum; curl is the reliable fallback.
    dnf config-manager --add-repo "$REPO" 2>/dev/null \
        || yum-config-manager --add-repo "$REPO" 2>/dev/null \
        || curl -fsSL "$REPO" -o /etc/yum.repos.d/docker-ce.repo \
        || exit 1
    $PM makecache -y >/dev/null 2>&1 || true
    $PM install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin || exit 1

elif command -v zypper >/dev/null 2>&1; then
    zypper --non-interactive refresh || true
    zypper --non-interactive install -y docker docker-compose || zypper --non-interactive install docker || exit 1

elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm docker docker-compose || pacman -Sy --noconfirm docker || exit 1

else
    echo "Unsupported package manager" >&2
    exit 1
fi

# Enable and start the daemon (RHEL leaves it stopped after install).
systemctl enable --now docker 2>/dev/null || systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
sleep 3
docker --version
"""


def is_docker_running(ssh):
    """True only if Docker is installed AND its daemon is active.

    A bare `docker --version` passes even when the daemon is stopped (common on
    RHEL right after install), which would let a container build start and fail.
    """
    out, _, code = ssh.run_command("docker --version 2>/dev/null")
    if code != 0 or not out.strip():
        return False
    out2, _, _ = ssh.run_command(
        "systemctl is-active docker 2>/dev/null || service docker status 2>/dev/null")
    return 'active' in out2 or 'running' in out2.lower()


def install_docker(ssh, timeout=600):
    """Install Docker CE and ensure the daemon is running. Returns the log.

    Raises RuntimeError if the install script fails.
    """
    out, err, code = ssh.run_sudo_script(INSTALL_DOCKER_SCRIPT, timeout=timeout)
    if code != 0:
        raise RuntimeError(f"Failed to install Docker: {err or out}")
    return out
