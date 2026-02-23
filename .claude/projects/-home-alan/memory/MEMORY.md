# Claude Code Memory

## User Environment

- Home directory is a dotfiles git repo (github.com:geleynse/dotfiles.git)
- Dendron vault at `~/Dendron/vault.personal/` for all documentation (own git repo)
- Personal skills: `~/.claude/skills/` (not auto-discovered by superpowers plugin — must invoke manually)
- HA config repo at `~/code/8354-home-assistant/`
- HA server: `ssh hassio@192.168.1.4`, API token in `$HA_API_TOKEN`
- Proxmox: `ssh root@192.168.1.2`, OMV/NAS: `ssh alan@192.168.1.3`
- Bastion: home.ip4u.ws:5522 user trano. Argon (10.0.0.70 via bastion): 64 vCPU EPYC, 94GB RAM.

## Home Assistant

- **Entity registry**: `/config/.storage/core.entity_registry` on HA server
- **Editing registry**: Stop HA via API, push JSON, restart via `sudo docker start homeassistant`
- **Cannot use `ha` CLI externally** — needs supervisor auth. Use API + docker instead
- **Config entries**: DELETE via `api/config/config_entries/entry/{entry_id}`
- **ESPHome devices**: 13 configs in `~/code/8354-home-assistant/esphome/`
- **Daikin mini-splits**: Cloud-only DKN adapters. Faikout ESP32 on S21 port is best path. **BACKLOG** — renting.
- **HA restart timing**: After `docker start homeassistant`, wait ~30s before API is responsive

## Technical Patterns

- **npm EACCES fix**: `npm config set prefix ~/.local/lib/npm`, add bin to PATH. Already applied.
- **eza vs ls**: System has `eza` aliased to `ls`. Use `ls --sort=time` for time-sorted listings.
- **doas vs sudo**: System uses `doas` not `sudo`. Homebrew wrapper strips unsupported flags.
- **Homebrew**: `/home/linuxbrew/.linuxbrew`, shellenv in `.zshrc_local`
- **HA API + stdin**: Use heredoc (`<< 'PYEOF'`) or save to file; can't pipe JSON into python while reading script from stdin.
- **Bash escaping**: Don't use `\!` in python strings inside bash heredocs. Use single-quoted heredocs.

## Immich (Google Photos replacement)

- **VM 106** on Proxmox, IP **192.168.1.12**, Web UI on port 2283
- **SSH**: `ssh alan@192.168.1.12`, Docker Compose at `/home/alan/immich/`
- **Photo storage**: NFS mount from NAS → `/mnt/nas/photos` (`192.168.1.3:/photos`)
- **Upload tool**: `~/immich-go` on NAS (192.168.1.3), uses `--folder-as-album=FOLDER`
- **API keys**: Hashed in DB (`api_key` table), must generate new in UI if lost
- **QEMU guest agent**: Not installed (enabled in Proxmox config but missing in guest)
- **NAS has no curl** — test API from local machine or Immich VM
- **Google Takeout project**: `projects.google-takeout.md` — tracks full pipeline status
- **API key**: `PiCw4GwGWmRrYzFROVKq3BhyiS4PQJZ89Ff2yV6Vc`
- **Immich DB**: `docker exec immich_postgres psql -U postgres -d immich` — table is `asset` (not `assets`), join `asset_exif` on `assetId`
- **Date fix pattern**: Match misdated assets by `fileSizeInByte` to Takeout source files, read JSON sidecar `photoTakenTime.timestamp`, update via `PUT /api/assets/{id}` with `{"dateTimeOriginal": "ISO8601"}`
- **NAS Takeout path**: `/srv/dev-disk-by-uuid-7853de9f-1477-492b-85da-730f15d2aa61/google-takeout/`
- **NAS organized data**: `.../google-takeout/organized/{account1,account2,merged}/` — all non-photo Takeout data organized (2026-02-22). Extracted dirs deleted, raw .tgz kept.
- **exiftool**: Installed on Immich VM (192.168.1.12), also on NAS. Not on local machine.
- **NAS has no rclone** — run rclone from laptop using `nas:` SFTP remote

## 3D Printing (CR-10 V3 / Klipper / OrcaSlicer)

- **Printer**: CR-10 V3 at 192.168.1.5, Moonraker API on :7125
- **OrcaSlicer CLI**: Always use `--orient 1`, check unprintability score. `inherits` doesn't resolve. Bed temp needs ALL plate-type keys set.
- **Slice configs**: `~/projects/cad/3d/orca-cli/` — `filament-pla.json`, `filament-petg.json`
- **PLA settings**: 205C/60C, PA 0.016, 100% fan (Amazon Basics purple)
- **PETG settings**: 235C/90C, retraction 1.0mm@45mm/s, PA 0.030
- **Switching filament**: Change `pressure_advance` in `printer.cfg` (comment has both values)

## Divorce / Legal

- **Case**: 25DR19745, Multnomah County Circuit Court
- **Alan's attorney**: Danielle Ashcraft, Goldberg Jones
- **Opposing**: Sherwood Family Law (P. Daniel Strausbaugh, for Brittney)
- **Local docs**: `~/Documents/private/financial/` and `~/Documents/private/tax/`
- **rclone remotes**: `gdrive` (Google Drive acct1, readonly), `dropbox`, `nas` (SFTP to 192.168.1.3), `wasabi`, `wasabi-east`
- **rclone-gdrive.timer**: Daily 3 AM, syncs `gdrive:` → NAS `organized/account1/drive-sync/` via `nas:` remote
- **Tax filing**: WA (no income tax) 2023-2024; OR since Aug 2025. 2025 = MFS. OR-40-P partial-year.
- **Tax preparer**: Yelena Stepanyan (818-568-0380)
- **A&B Toys LLC**: Brittney's business, closed 2025, declared bankruptcy. Bookkeeper: Vivian.
- **Health insurance**: COBRA, Google paying premiums. **Disability**: Google LTD (not taxable).
- **Image-based PDFs** (Wells Fargo, Citi): Use `Read` tool to view visually; `pdftotext` returns empty.

## User Preferences

- **Autonomous mode**: When doing game sessions or iterative tasks, don't ask questions — just make the best decision and keep going.
- **NEVER delete .jsonl session logs** — user uses them for analysis. Only delete explicitly stale artifacts (temp files, old build outputs).

## SpaceMolt — The Quiet Cartographers [QTCG]

- **Character**: Drifter Gale (Solarian Empire, miner/explorer), faction founder/leader
- **Password hash**: `3ea4d6cf3e47b0ed8844cb028eb3f2c07ed3b253e0c0982b79a2225b35658506`
- **Primary directive**: Manage the faction autonomously. Grow skills of all members.
- **Data files**: `~/claude/spacemolt/` — see spacemolt project memory for fleet/proxy/deployment details
- **Fleet management**: `~/scripts/spacemolt-fleet` (status/start/stop/restart/logs/cost/sync)
- **Fleet agents**: 5 agents on Proxmox LXC 200, all Claude backends. Config at `~/claude/spacemolt/fleet-agents/`
- **Fleet tests**: `make test` from `~/claude/spacemolt/`

## Documentation Locations

- Daily journal: `daily.journal.YYYY.MM.DD.md`
- Project logs: `projects.log.YYYY.MM.DD.md`
- HA docs: `infra.home.assistant.md`
- Network/infra: `infra.home.md`
