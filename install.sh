#!/usr/bin/env bash
set -euo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$HOME/.dotfiles-backup-$(date +%Y%m%d-%H%M%S)"

backup_and_link() {
  local src="$1"
  local dst="$2"

  if [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]; then
    echo "  ok  $dst"
    return
  fi

  if [[ -e "$dst" || -L "$dst" ]]; then
    mkdir -p "$BACKUP_DIR"
    mv "$dst" "$BACKUP_DIR/"
    echo "  bak $(basename "$dst") → $BACKUP_DIR/"
  fi

  ln -s "$src" "$dst"
  echo "  ln  $dst → $src"
}

echo "=== Linking home/ files ==="
for src in "$DOTFILES/home/"* "$DOTFILES/home/".*; do
  [[ -e "$src" ]] || continue
  name="$(basename "$src")"
  [[ "$name" == "." || "$name" == ".." ]] && continue
  backup_and_link "$src" "$HOME/$name"
done

echo "=== Linking .config subdirs ==="
mkdir -p "$HOME/.config"
for src in "$DOTFILES/config/"/*/; do
  [[ -e "$src" ]] || continue
  name="$(basename "$src")"
  backup_and_link "$src" "$HOME/.config/$name"
done

echo "=== Linking .vim ==="
backup_and_link "$DOTFILES/vim" "$HOME/.vim"

echo "=== Linking .zsh_modules ==="
backup_and_link "$DOTFILES/zsh" "$HOME/.zsh_modules"

echo "=== Linking scripts/ and bin/ ==="
backup_and_link "$DOTFILES/scripts" "$HOME/scripts"
backup_and_link "$DOTFILES/bin"     "$HOME/bin"

echo "=== Initializing submodules ==="
git -C "$DOTFILES" submodule update --init --recursive

echo ""
echo "Done."
[[ -d "$BACKUP_DIR" ]] && echo "Backups saved to: $BACKUP_DIR"
