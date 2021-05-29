set nocompatible

scriptencoding=utf-8
set encoding=utf-8

call pathogen#infect()

set history=500
set showcmd
set showmatch
set ignorecase
set smartcase
set hlsearch
set incsearch
set autowrite
set autoread
set hidden
if has('mouse')
    set mouse=a
endif
set ttymouse=xterm "fix hang in screen/tmux
set autoindent
set smartindent
set wrap
set title
set nobackup
set noswapfile
set scrolloff=3 "Scroll 3 lines before edge of screen
set bs=2 "Fix backspace

let mapleader=","
let maplocalleader="\\"

syntax enable

colorscheme geleynse

inoremap jk <ESC>

"Adjust settings to avoid annoying timeouts after <Esc>-O and others
set timeout timeoutlen=1000 ttimeoutlen=100

"Tab settings
set ts=2 sts=2 sw=2
set expandtab

"Show special characters
set list
set listchars=tab:▸\ ,eol:¬

"report results for all commands
set report=1

"map del to be the same as backspace
map <C-V>127 <C-H>

"use F2 to temporarily disable automatic stuff for pasting
set pastetoggle=<F2>

"set ,ss to clean up whitespace at end of lines
nmap <silent> <leader>ss :%s/\(\S\)\(\s\+\)$/\1/<CR>

"set ,sS to clean up whitespace from empty lines
nmap <silent> <leader>sS :%s/^\s\+$//<CR>

"set w!! to automatically save the file in sudo
cmap w!! w !sudo tee % >/dev/null

"set ,/ to clear search highlighting
nmap <silent> <leader>/ :nohlsearch<CR>

"set cp{motion} to change paste motion e.g. cpw = replace next word with paste buffer
nmap <silent> cp :set opfunc=ChangePaste<CR>g@
function! ChangePaste(type, ...)
    silent exe "normal! `[v`]\"_c"
    silent exe "normal! p"
endfunction

"left/right arrow keys change indent
nnoremap <Left> <<
nnoremap <Right> >>
vnoremap <Left> <gv
vnoremap <Right> >gv

"text bubbling
nnoremap <C-j> :m+<CR>==
nnoremap <C-k> :m-2<CR>==
inoremap <C-j> <Esc>:m+<CR>==gi
inoremap <C-k> <Esc>:m-2<CR>==gi
vnoremap <C-j> :m'>+<CR>gv=gv
vnoremap <C-k> :m-2<CR>gv=gv

"up/down arrow keys also bubble text
nnoremap <Down> :m+<CR>==
nnoremap <Up> :m-2<CR>==
inoremap <Down> <Esc>:m+<CR>==gi
inoremap <Up> <Esc>:m-2<CR>==gi
vnoremap <Down> :m'>+<CR>gv=gv
vnoremap <Up> :m-2<CR>gv=gv

"use ack instead of grep
set grepprg=ack\ -a

filetype plugin on
filetype indent on

set wildmenu
set wildmode=list:longest,full

set ruler
if exists("&relativenumber")
	set relativenumber
else
	set number
endif
set magic

"Persistent undo
try
	if MySys() == "windows"
	  set undodir=C:\Windows\Temp
	else
	  set undodir=~/.vim/undodir
	endif

	set undofile
	set undolevels=1000
	set undoreload=10000
catch
endtry

"function to switch between relative and absolute line numbers
function! g:ToggleNuMode()
	if(&rnu == 1)
		set nu
	else
		set rnu
	endif
endfunc

"set <C-l> to switch line numbering mode
nnoremap <C-L> :call g:ToggleNuMode()<cr>

"When editing a file, make screen display the name of the file you are editing
function! SetTitle()
	if $TERM =~ "^screen"
		let l:title = 'vi: ' . expand('%:t')

		if (l:title != 'vi: __Tag_List__')
			let l:truncTitle = strpart(l:title, 0, 15)
			silent exe '!echo -e -n "\033k' . l:truncTitle . '\033\\"'
		endif
	endif
endfunction

" Run it every time we change buffers
autocmd BufEnter,BufFilePost * call SetTitle()

"Always show the status line
set laststatus=2

let g:airline_theme = 'powerlineish'

if filereadable($HOME."/.vimrc_local")
	source $HOME/.vimrc_local
endif

"Make F3 display the highlight name for the character under the cursor to make color schemes easier to write
:map <F3> :echo "hi<" . synIDattr(synID(line("."),col("."),1),"name") . '> trans<' . synIDattr(synID(line("."),col("."),0),"name") . "> lo<" . synIDattr(synIDtrans(synID(line("."),col("."),1)),"name") . ">"<CR>

"Make F5 display gundo
nnoremap <F5> :GundoToggle<CR>

