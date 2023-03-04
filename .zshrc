#
# .zshrc is sourced in interactive shells.
# It should contain commands to set up aliases,
# functions, options, key bindings, etc.
#

#Load any local options
#This has to be done first to make sure I get any options that change the zsh to use
if [[ -f $HOME/.zshrc_local ]]
then
	source $HOME/.zshrc_local
fi

#Configuration options
#AUTO_TITLE_SCREENS="NO"
PROMPT_COLOR=${PROMPT_COLOR:-cyan} # Set the prompt color; defaults to cyan
USE_CONDITIONAL_PROMPT="YES"
PROMPT_SUCCESS_COLOR=${PROMPT_SUCCESS_COLOR:-green}
PROMPT_FAILURE_COLOR=${PROMPT_FAILURE_COLOR:-red}
PROMPT_BRANCH_COLOR=${PROMPT_BRANCH_COLOR:-yellow}

#Set up any extras on the path
if [[ -d /opt/local/bin ]] then PATH="/opt/local/bin:$PATH" fi
if [[ -d $HOME/opt/bin ]] then PATH="$PATH:$HOME/opt/bin" fi
if [[ -d $HOME/bin ]] then PATH="$PATH:$HOME/bin" fi
export PATH

#allow tab completion in the middle of a word
setopt COMPLETE_IN_WORD

## history
## for sharing history between zsh processes
setopt EXTENDED_HISTORY			# store time in history
setopt HIST_IGNORE_DUPS			# only have 1 history entry for duplicate commands
setopt HIST_VERIFY				# Make those history commands nice
HISTFILESIZE=10000000000
HISTSIZE=10000000000
SAVEHIST=10000000000
HISTFILE=~/.history

# History configuration adapted from https://gist.github.com/muzso/f784e98fb187fe5e38117f9e2bd8c0e6

# The following function sets up history management in a way that each shell's
# history is saved into separate files and they are archived into monthly files.
# This prevents accidental loss of history entries.
# Uses zsh-specific features, but can be adapted to other shells (eg. bash)
# as well. The reading of a file into the internal history list of a shell
# cannot be done without an if-else based on the shell's type or the
# availability of specific shell builtins), thus I didn't bother to keep this
# fully bash-compatible.
# It is not guaranteed that history entries are ordered by date&time
# (neither in monthly archives, nor in the shells' internal history list),
# but a best effort is made to preserve the correct order.
# Note that history entries can be multi-line thus re-ordering a history file
# is expensive and complex (and I don't do it here).
# Useful history related shell options to set:
#   setopt extendedhistory histignoredups incappendhistorytime
setopt INC_APPEND_HISTORY
() {
  local hist_dir_path="$HOME/zsh-history"
  if ! mkdir -p "$hist_dir_path"; then
    echo "Failed to create directory at \"$hist_dir_path\"\! Shell history will not be saved." >&2
    return
  fi

  if [ ! -r "$hist_dir_path" -o ! -w "$hist_dir_path" -o ! -x "$hist_dir_path" ]; then
    echo "Insufficient permissions for \"$hist_dir_path\"\! Shell history will neither be loaded nor saved." >&2
    return
  fi

  local temp_hist_prefix="zsh_history."

  # Each shell instance uses a separate file to record it's history.
  # This also means that shell instances won't be able to load the history of
  # other running instances.
  # I.e. you won't be able to recall commands in a (running) shell instance that
  # were executed in another (running) shell instance.
  # If you'd like to have a shared history file between running instances, you
  # can remove the PID variable ($$) from the end of the filename.
  HISTFILE="$hist_dir_path/${temp_hist_prefix}$(date "+%F_%H-%M-%S").$$"
  export HISTFILE

  # Uncomment the following if you want history files created via sudo root
  # sessions to be owned by the original user. Otherwise these root history
  # files will only be merged into the monthly archive, when you next switch
  # to root via sudo.
  # Note that this might not be a good idea in a multiuser environment.
  # In theory the two environment variables (SUDO_UID and SUDO_GID) could pose
  # some risk if sudo itself is vulnerable or misconfigured (i.e. if any of
  # these variables can be set from outside of sudo).
  if [ "$(id -u)" -eq 0 ]; then
    touch "$HISTFILE"
    [ -n "$SUDO_UID" ] && expr "$SUDO_UID" : '^[0-9]\+$' > /dev/null 2>&1 && chown "$SUDO_UID" "$HISTFILE"
    [ -n "$SUDO_GID" ] && expr "$SUDO_GID" : '^[0-9]\+$' > /dev/null 2>&1 && chgrp "$SUDO_GID" "$HISTFILE"
  fi

  local hist_archive_prefix="zsh_history_archive"
  local current_month_hist_archive="$hist_dir_path/${hist_archive_prefix}$(date "+%Y-%m").log"

  # Prevent parallel execution of the following block using
  # "$hist_dir_path/lockfile" as a lockfile.
  (
    flock -en 9 || return

    # For all temporary shell history files ...
    for h in "$hist_dir_path/$temp_hist_prefix"*(N); do
      # Make sure that the current history file is never touched.
      [ "$h" = "$HISTFILE" ] && continue
      # Get the section after the last dot from the filename.
      h_pid="${h##*.}"
      # Skip the file if the found string is not empty and a process with
      # a PID from the string exists.
      [ -n "$h_pid" ] && kill -0 "$h_pid" 2> /dev/null && continue
      # Concatenate the contents of the file to the current month's history
      # archive and delete the file.
      [ -r "$h" ] && cat "$h" >> "$current_month_hist_archive" && rm "$h"
    done
  ) 9> "$hist_dir_path/lockfile"

  # Load all history archives (in order) into the internal history list.
  for h in "$hist_dir_path/$hist_archive_prefix"*(Nn); do [ -r "$h" ] && fc -R "$h"; done

  # Load all temporary history files (in order) into the internal history list.
  for h in "$hist_dir_path/$temp_hist_prefix"*(Nn); do [ -r "$h" ] && fc -R "$h"; done
}

#Watch for logins
#watch=all
watch=notme
WATCHFMT="%W %t %n has %a %l from %M"

get_git_branch()
{
	git symbolic-ref HEAD 2>/dev/null | cut -d'/' -f3 || {echo "$@"; exit;}
}

#Set prompt
set_prompt()
{
	autoload colors
	colors
	if [[ $USE_CONDITIONAL_PROMPT == "YES" ]]; then
		PS1="%{%(?.$fg[$PROMPT_SUCCESS_COLOR].$fg[$PROMPT_FAILURE_COLOR])%}%B%n@%m%# %b%{${fg[default]}%}" # exit code conditional colored prompt
	else
		PS1="%{${fg[$PROMPT_COLOR]}%}%B%n@%m%# %b%{${fg[default]}%}" # basic colored prompt
	fi

	PS2="%{${fg[$PROMPT_COLOR]}%}%B(%_)%b %{${fg[default]}%}"
	RPROMPT="%{${fg[$PROMPT_COLOR]}%}%B(%{${fg[$PROMPT_BRANCH_COLOR]}%}$(get_git_branch)%{${fg[$PROMPT_COLOR]}%}) %(7~,.../,)%6~%b%{${fg[default]}%}"
}

autoload add-zsh-hook
add-zsh-hook precmd set_prompt

if [[ $AUTO_TITLE_SCREENS != "NO" && $EMACS != "t" ]]
then
	precmd ()
	{
		# if you are at a zsh prompt, make your screen title your current directory
		#local TITLE=${PWD:t}
		local TITLE=${(S)PWD/src\/appgroup\/*\/*\//.../}
		TITLE=${(S)TITLE/*\/geleynse-git-*\/*\//.../}
		TITLE=${(S)TITLE/*\/geleynse-git-*\//.../}
		# 'screen' sets STY as well, so for users who override the TERM
		# environment variable, checking STY is nice
		setopt UNSET # Avoid errors from undefined STY for users with 'NOUNSET'
		if [[ $TERM == "screen" || -n $STY ]]; then
			echo -ne "\ek$TITLE\e\\"
		fi
		if [[ $TERM == "xterm" ]]; then
			echo -ne "\e]0;$TITLE\a"
		fi
		setopt LOCAL_OPTIONS # restore value of UNSET
	}

	preexec ()
	{
		# if you are running a command, make your screen title the command you're
		# running
		local CMDS
		local CMD
		set -A CMDS $(echo $1)
		#Use first word from command line, but treat "sudo" specially
		if [[ $CMDS[1] == "sudo" ]]; then
			CMD="sudo $CMDS[2]"
		else
			CMD=$CMDS[1]
		fi
		setopt UNSET # Avoid errors from undefined STY for users with 'NOUNSET'
		if [[ $TERM == "screen" || -n "$STY" ]]; then
		  echo -ne "\ek$CMD\e\\"
		fi
		if [[ $TERM == "xterm" ]]; then
		  echo -ne "\e]0;$CMD\a"
		fi
		setopt LOCAL_OPTIONS # restore value of UNSET

    local TIME=`date +"[%H:%M:%S] "`
    local zero='%([BSUbfksu]|([FK]|){*})'
    local PROMPTLEN=${#${(S%%)PROMPT//$~zero/}}
    echo "\033[1A\033[$(($(echo -n $1 | wc -m)+$PROMPTLEN))C $fg[yellow]${TIME}$reset_color"
	}
fi

DIRSTACKSIZE=20   # number of directories in your pushd/popd stack

export EDITOR="vim"
export VISUAL=$EDITOR # some programs use this instead of EDITOR

#Set up jk to work as the mode switch in vim mode
bindkey -M viins 'jk' vi-cmd-mode

if [[ $EMACS == "t" ]]; then
	export PAGER=cat			# otherwise funkiness in M-x shell
else
	export PAGER=less			# less is more :)
	export LESS="-er"			# set up less to be a little nicer and display color in git logs correctly
fi

source ~/.zsh_modules/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
ZSH_HIGHLIGHT_HIGHLIGHTERS=(main brackets)

source ~/.aliases

#pushes current command on command stack and gives blank line, after that line
#runs command stack is popped
bindkey "^T" push-line-or-edit

#Other useful bindings
bindkey "^R" history-incremental-search-backward
bindkey "^E" end-of-line
bindkey "^B" beginning-of-line

######################### zsh options ################################
setopt ALWAYS_TO_END			# Push that cursor on completions.
setopt AUTO_NAME_DIRS			# change directories  to variable names
setopt AUTO_PUSHD				# push directories on every cd
setopt NO_BEEP					# self explanatory

######################### completion #################################
# these are some (mostly) sane defaults, if you want your own settings, I
# recommend using compinstall to choose them.  See 'man zshcompsys' for more
# info about this stuff.

# The following lines were added by compinstall

zstyle ':completion:*' completer _expand _complete _approximate
zstyle ':completion:*' list-colors ${(s.:.)LS_COLORS}
zstyle ':completion:*' list-prompt '%SAt %p: Hit TAB for more, or the character to insert%s'
zstyle ':completion:*' matcher-list '' 'm:{a-z}={A-Z}' 'r:|[._-]=** r:|=**' 'l:|=* r:|=*'
zstyle ':completion:*' menu select=long
zstyle ':completion:*' select-prompt '%SScrolling active: current selection at %p%s'
zstyle ':completion:*' use-compctl true
zstyle :compinstall filename '/home/alan/.zshrc'

autoload -Uz compinit
compinit
# End of lines added by compinstall

#Custom functions

#Extract most types of archive
extract () {
	if [ -f $1 ] ; then
		case $1 in
			*.tar.bz2)	tar xvjf $1 && cd $(echo $1 | sed 's/.tar.bz2//')	  ;;
			*.tar.gz)	tar xvzf $1 && cd $(echo $1 | sed 's/.tar.gz//')	 ;;
			*.bz2)		bunzip2 $1 && cd $(echo $1 | sed 's/.bz2//')	 ;;
			*.rar)		unrar x $1 && cd $(echo $1 | sed 's/.rar//')	 ;;
			*.gz)		gunzip $1 && cd $(echo $1 | sed 's/.gz//')    ;;
			*.tar)		tar xvf $1 && cd $(echo $1 | sed 's/.tar//')	 ;;
			*.tbz2)		tar xvjf $1 && cd $(echo $1 | sed 's/.tbz2//')    ;;
			*.tgz)		tar xvzf $1 && cd $(echo $1 | sed 's/.tgz//')	  ;;
			*.zip)		unzip $1 && cd $(echo $1 | sed 's/.zip//')    ;;
			*.Z)		uncompress $1 && cd $(echo $1 | sed 's/.Z//')	  ;;
			*.7z)		7z x $1 && cd $(echo $1 | sed 's/.7z//')	 ;;
			*)			echo "don't know how to extract '$1'..." ;;
		esac
	else
		echo "cannot extract '$1', I don't understand that filetype"
	fi
}

#cd up directories with u, uu, uuu, etc.
u () {
	set -A ud
	ud[1+${1-1}]=
	cd ${(j:../:)ud}
}

#Begin special key setup

# create a zkbd compatible hash;
# to add other keys to this hash, see: man 5 terminfo
typeset -A key

key[Home]=${terminfo[khome]}
key[End]=${terminfo[kend]}
key[Insert]=${terminfo[kich1]}
key[Delete]=${terminfo[kdch1]}
key[Up]=${terminfo[kcuu1]}
key[Down]=${terminfo[kcud1]}
key[Left]=${terminfo[kcub1]}
key[Right]=${terminfo[kcuf1]}
key[PageUp]=${terminfo[kpp]}
key[PageDown]=${terminfo[knp]}

for k in ${(k)key} ; do
    # $terminfo[] entries are weird in ncurses application mode...
    [[ ${key[$k]} == $'\eO'* ]] && key[$k]=${key[$k]/O/[}
done
unset k

# setup key accordingly
[[ -n "${key[Home]}"    ]]  && bindkey  "${key[Home]}"    beginning-of-line
[[ -n "${key[End]}"     ]]  && bindkey  "${key[End]}"     end-of-line
[[ -n "${key[Insert]}"  ]]  && bindkey  "${key[Insert]}"  overwrite-mode
[[ -n "${key[Delete]}"  ]]  && bindkey  "${key[Delete]}"  delete-char
[[ -n "${key[Up]}"      ]]  && bindkey  "${key[Up]}"      up-line-or-history
[[ -n "${key[Down]}"    ]]  && bindkey  "${key[Down]}"    down-line-or-history
[[ -n "${key[Left]}"    ]]  && bindkey  "${key[Left]}"    backward-char
[[ -n "${key[Right]}"   ]]  && bindkey  "${key[Right]}"   forward-char
#End special key setup

