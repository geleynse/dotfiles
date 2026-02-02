# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a personal dotfiles repository (github.com:geleynse/dotfiles.git) that manages the home directory configuration. The repository root is `~` (home directory), with this working directory being `~/claude`.

## Key Configuration Files

- **`.zshrc`** - Main shell config with per-shell history management (saves to `~/zsh-history/`), vim keybindings (`jk` for escape), and custom prompt with git branch display
- **`.vimrc`** - Vim config using Pathogen for plugins, with `jk` for escape, text bubbling (C-j/C-k or arrows), and ripgrep for grep
- **`.aliases`** - Shell aliases; git shortcuts (g, ga, gp, gs, gd, etc.), `ack` redirects to `rg`
- **`.gitconfig`** - Git config with custom aliases including `squash` (uses `~/scripts/git-squash.rb`), `lg` for graph log
- **`.tmux.conf`** - tmux with C-a prefix, vim-style pane navigation (hjkl)

## Customization Pattern

Most configs support local overrides that are not tracked in git:
- `.zshrc` sources `.zshrc_local` if present
- `.vimrc` sources `.vimrc_local` if present
- `.aliases` sources `.aliases_local` if present

## Included Tools

- **`bin/colout/`** - Python tool for colorizing arbitrary command output with regex patterns
- **`scripts/git-squash.rb`** - Ruby script for squashing commits (aliased as `git squash`)

## Vim Plugins (via Pathogen)

Located in `.vim/bundle/`: fugitive, gundo, minibufexpl, supertab, surround, togglemouse, vim-airline, vim-airline-themes

Submodules managed via `.gitmodules`.
