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

## keep background processes at full speed
#setopt NOBGNICE
## restart running processes on exit
#setopt HUP

## history
## for sharing history between zsh processes
#setopt SHARE_HISTORY			# share history between shell instances
setopt EXTENDED_HISTORY			# store time in history
setopt HIST_IGNORE_DUPS			# only have 1 history entry for duplicate commands
setopt HIST_VERIFY				# Make those history commands nice
HISTSIZE=15000					# spots for duplicates/uniques
SAVEHIST=15000					# unique events guarenteed, but since we are ignoring dups it is the same
HISTFILE=~/.history


## automatically decide when to page a list of completions
#LISTMAX=0

## disable mail checking
#MAILCHECK=0

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
	}
fi

DIRSTACKSIZE=20   # number of directories in your pushd/popd stack

export EDITOR="vim"
export VISUAL=$EDITOR # some programs use this instead of EDITOR

#Use emacs mode since zsh only has a vi mode, not a vim mode and it takes way more work to get it working nicely
#bindkey -e

if [[ $EMACS == "t" ]]; then
	export PAGER=cat			# otherwise funkiness in M-x shell
else
	export PAGER=less			# less is more :)
	export LESS="-er"			# set up less to be a little nicer and display color in git logs correctly
fi

#Set caps lock to be ESC for vim
#xmodmap ~/.capslocktoesc

source ~/.aliases

#AWESOME...
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

autoload -U compinit
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
