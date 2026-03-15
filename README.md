# distrostrap

Install any Linux distribution onto a target disk or partition from a running host system. No live USB required.

distrostrap downloads the necessary bootstrap tools automatically, so you can install Arch from Ubuntu, Fedora from Arch, or any supported combination.

## Supported Distributions

| Distro | Bootstrap Method | Desktop Options |
|--------|-----------------|-----------------|
| **Arch Linux** | pacstrap (auto-downloaded bootstrap tarball) | GNOME, KDE Plasma, Xfce, or server |
| **Ubuntu** | debootstrap (auto-extracted from .deb) | GNOME, GNOME minimal, KDE, Xfce, or server |
| **Fedora** | dnf via OCI container image | GNOME Workstation, KDE, Xfce, or server |

## Requirements

- A running Linux system (any distro)
- Root privileges
- Network connectivity
- Python 3.11+
- Standard tools: `lsblk`, `blkid`, `mount`, `umount`, `mkfs.ext4`, `sgdisk`, `chroot`

## Installation

### Prerequisites (Ubuntu/Debian)

Ubuntu minimal or server installs may not have everything out of the box. Install the required packages first:

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv curl
```

On Arch, Fedora, and most desktop installs these are already present.

### Setup

```bash
git clone https://github.com/soyeb-jim285/distrostrap.git
cd distrostrap
python3 -m venv .venv
.venv/bin/pip install -e .
```

For development (includes pytest, ruff, mypy):

```bash
.venv/bin/pip install -e ".[dev]"
```

## Usage

### Interactive Mode (TUI)

```bash
sudo .venv/bin/distrostrap
```

This launches a step-by-step terminal wizard:

1. **Welcome** — preflight checks (root, tools, boot mode)
2. **Select Distribution** — pick a distro and release version
3. **Select Target** — choose a disk or existing partition
4. **Partition Layout** — review the default partitioning scheme
5. **System Configuration** — set hostname, user, password, timezone, locale
6. **Confirm** — type `YES` to begin
7. **Install** — watch the pipeline execute with live progress

### Headless Mode (YAML Config)

```bash
sudo .venv/bin/distrostrap --config config.yaml --no-tui
```

Example `config.yaml`:

```yaml
distro: arch
distro_variant: ""
target_device: /dev/sdb
hostname: mybox
username: jim
password: changeme
root_password: changeme
timezone: America/New_York
locale: en_US.UTF-8
desktop: ""
```

### Dry Run

Simulate the entire installation without touching any disk:

```bash
sudo .venv/bin/distrostrap --dry-run
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Simulate all operations without making changes |
| `--config PATH` | Path to a YAML config file for headless mode |
| `--no-tui` | Run non-interactively (requires `--config`) |
| `--log-file PATH` | Log file path (default: `/var/log/distrostrap.log`) |

## How It Works

distrostrap runs a 10-stage pipeline:

```
validate → preflight → partition → format → mount →
bootstrap → post_bootstrap → configure → bootloader → host_grub
```

1. **Validate** — check root privileges, verify the target device is safe (not the host root, not mounted)
2. **Preflight** — detect UEFI/BIOS boot mode, check for distro-specific tools
3. **Partition** — create GPT (UEFI) or MBR (BIOS) partitions with `sgdisk`/`sfdisk`
4. **Format** — create filesystems (vfat for ESP, ext4 for root, mkswap)
5. **Mount** — mount target partitions under `/mnt/distrostrap`
6. **Bootstrap** — install the base system using the distro's native tool
7. **Post-bootstrap** — install kernel, firmware, bootloader packages, and optional desktop
8. **Configure** — set up fstab, hostname, locale, timezone, users, networking inside the chroot
9. **Bootloader** — install GRUB in the target system
10. **Host GRUB** — update the host's GRUB config so the new install appears in the boot menu

### Cross-Distro Installation

Each distro plugin can download its own bootstrap tools. For example:

- **Arch from Ubuntu**: downloads the Arch bootstrap tarball, extracts it, and runs `pacstrap` from within
- **Ubuntu from Arch**: downloads the `debootstrap` .deb, extracts it with `ar` + `tar` (no `dpkg` needed)
- **Fedora from anything**: downloads a Fedora OCI container image, extracts the rootfs layers, and runs `dnf` from within

### Target Modes

- **Full disk** (`/dev/sdb`): wipes the entire disk, creates fresh partitions, installs bootloader
- **Existing partition** (`/dev/sdb3`): formats and installs to a single partition, skips partitioning and bootloader (relies on host GRUB to chainload)

## Safety

distrostrap includes several safeguards:

- Refuses to operate on the disk containing the host root filesystem
- Refuses to operate on mounted partitions
- Handles NVMe (`/dev/nvme0n1p2`) and conventional (`/dev/sda1`) device naming correctly
- All destructive operations go through a central `Executor` that supports dry-run mode
- Requires explicit `YES` confirmation before any installation begins

## Development

```bash
# Run tests
.venv/bin/pytest

# Run a single test
.venv/bin/pytest tests/unit/test_safety.py -v

# Lint
.venv/bin/ruff check src/ tests/

# Type check
.venv/bin/mypy src/
```

## Project Structure

```
src/distrostrap/
├── cli.py              # CLI argument parsing, mode routing
├── app.py              # Interactive TUI wizard (stdlib-only, no curses)
├── term.py             # Terminal primitives: menus, tables, spinners, input
├── core/
│   ├── context.py      # InstallContext dataclass (carries all config)
│   ├── pipeline.py     # 10-stage installation pipeline
│   ├── executor.py     # Subprocess runner with dry-run + logging
│   ├── safety.py       # Target validation (host root protection)
│   ├── chroot.py       # Bind-mount management for chroot
│   └── host_info.py    # Boot mode, distro, network detection
├── distros/
│   ├── base.py         # DistroPlugin abstract base class
│   ├── registry.py     # Plugin registration and discovery
│   ├── arch.py         # Arch Linux plugin
│   ├── ubuntu.py       # Ubuntu plugin
│   └── fedora.py       # Fedora plugin
├── partition/
│   ├── detect.py       # Block device enumeration (lsblk)
│   ├── layout.py       # Partition layout specifications
│   ├── create.py       # Partition creation (sgdisk/sfdisk)
│   ├── format.py       # Filesystem creation + UUID capture
│   └── mount.py        # Mount/unmount operations
├── config/
│   ├── fstab.py        # /etc/fstab generation
│   ├── hostname.py     # /etc/hostname + /etc/hosts
│   ├── locale.py       # Locale configuration
│   ├── timezone.py     # Timezone + hwclock
│   ├── users.py        # User creation + sudo setup
│   └── network.py      # NetworkManager/systemd-networkd
└── bootloader/
    ├── grub.py         # GRUB installation in target chroot
    ├── detect.py       # ESP discovery on host
    └── host_grub.py    # Host GRUB update (os-prober + custom entry)
```

## License

MIT
