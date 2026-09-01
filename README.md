# dotfiles

Symlink-based dotfiles for a fresh Arch machine. `install.sh` links everything
into `$HOME`, backing up anything already there.

```sh
git clone --recurse-submodules https://github.com/geleynse/dotfiles ~/dotfiles
cd ~/dotfiles && ./install.sh
```

## Layout

| Path | Linked to | What |
|---|---|---|
| `home/` | `~/<name>` | `.zshrc`, `.vimrc`, `.aliases`, `.tmux.conf`, `.gitconfig` |
| `config/` | `~/.config/<name>` | `git/ignore`, `restic/excludes` |
| `vim/` | `~/.vim` | pathogen + bundles (git submodules) |
| `zsh/` | `~/.zsh_modules` | zsh-syntax-highlighting (submodule) |
| `bin/` | `~/bin` | small standalone utilities |

`install.sh` is idempotent: a link already pointing at the right place is left
alone, and anything else is moved to `~/.dotfiles-backup-<timestamp>/` first. It
also runs `git submodule update --init --recursive`, so a clone without
`--recurse-submodules` is still fine.

`scripts/` is **not** in this repo. It is a separate private repository checked
out at `~/dotfiles/scripts` (gitignored here) and linked to `~/scripts`; it holds
infrastructure tooling that should not be public.

## Pre-commit secret scan

This repo is **public**. `.githooks/pre-commit` runs `~/scripts/check-secrets`
over staged files and refuses a commit that introduces a new credential — or, in
this repo only, a new private (RFC1918) address, since what leaks here is the
network layout rather than a key.

Enable once per clone:

```sh
git config core.hooksPath .githooks
```

Known findings are excused by `.secrets-baseline`, which holds a hash per finding
and never a value. The single entry today is the NAS address in `bin/backup.sh`;
it is left deliberately, because the obvious fix is an ssh alias and a hostname
that fails to resolve would silently break the nightly restic backup.
