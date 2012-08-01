" Vim color scheme
"
" Name:         custom.vim
" Maintainer:   Alan Geleynse

set background=dark
hi clear
if exists("syntax_on")
   syntax reset
endif

set t_Co=256

let g:colors_name = "custom"

highlight SpecialKey     term=bold cterm=bold ctermfg=4
"highlight NonText        term=bold cterm=bold ctermfg=4
highlight NonText        term=bold cterm=bold ctermfg=8
highlight Directory      term=bold cterm=bold ctermfg=6
highlight ErrorMsg       term=standout cterm=bold ctermfg=7 ctermbg=1
highlight IncSearch      term=reverse cterm=reverse
highlight Search         term=reverse ctermfg=0 ctermbg=3
highlight MoreMsg        term=bold cterm=bold ctermfg=2
highlight ModeMsg        term=bold cterm=bold
highlight LineNr         term=underline cterm=bold ctermfg=3
highlight Question       term=standout cterm=bold ctermfg=2
highlight StatusLine     term=bold,reverse cterm=bold,reverse
highlight StatusLineNC   term=reverse cterm=reverse
highlight VertSplit      term=reverse cterm=reverse
highlight Title          term=bold cterm=bold ctermfg=5
highlight Visual         term=reverse cterm=reverse
highlight WarningMsg     term=standout cterm=bold ctermfg=1
highlight WildMenu       term=standout ctermfg=0 ctermbg=3
highlight Folded         term=standout cterm=bold ctermfg=6 ctermbg=0
highlight FoldColumn     term=standout cterm=bold ctermfg=6 ctermbg=0
highlight DiffAdd        term=bold ctermbg=4
highlight DiffChange     term=bold ctermbg=5
highlight DiffDelete     term=bold cterm=bold ctermfg=4 ctermbg=6
highlight DiffText       term=reverse cterm=bold ctermbg=1
highlight SignColumn     term=standout cterm=bold ctermfg=6 ctermbg=0
highlight SpellBad       term=reverse ctermbg=1
highlight SpellCap       term=reverse ctermbg=4
highlight SpellRare      term=reverse ctermbg=5
highlight SpellLocal     term=underline ctermbg=6
highlight Pmenu          ctermbg=5
highlight PmenuSel       ctermbg=0
highlight PmenuSbar      ctermbg=7
highlight PmenuThumb     cterm=reverse
highlight TabLine        term=underline cterm=bold,underline ctermfg=7 ctermbg=0
highlight TabLineSel     term=bold cterm=bold
highlight TabLineFill    term=reverse cterm=reverse
highlight CursorColumn   term=reverse ctermbg=0
highlight CursorLine     term=underline cterm=underline
highlight ColorColumn    term=reverse ctermbg=1
highlight MatchParen     term=reverse ctermbg=6
"highlight Comment        term=bold cterm=bold ctermfg=6
"highlight Comment        term=bold ctermfg=246
highlight Comment        term=bold ctermfg=6
"highlight Constant       term=underline cterm=bold ctermfg=5
highlight Constant       term=underline cterm=none ctermfg=10
highlight Constant       term=underline cterm=none ctermfg=10
highlight Special        term=bold cterm=bold ctermfg=1
highlight Identifier     term=underline cterm=bold ctermfg=6
"highlight Statement      term=bold cterm=bold ctermfg=3
highlight Statement      term=bold ctermfg=11
highlight PreProc        term=underline cterm=bold ctermfg=4
"highlight Type           term=underline cterm=bold ctermfg=2
highlight Type           term=underline ctermfg=2
highlight Underlined     term=underline cterm=bold,underline ctermfg=4
highlight Ignore         ctermfg=0
highlight Error          term=reverse cterm=bold ctermfg=7 ctermbg=1
highlight Todo           term=standout ctermfg=0 ctermbg=3

"MiniBufExplorer
highlight MBENormal cterm=bold ctermfg=6

"Javascript
highlight javaScriptBraces cterm=bold ctermfg=6
highlight javaScriptNull   cterm=bold ctermfg=5
"highlight javaScriptParens cterm=bold ctermfg=208
highlight javaScriptParens cterm=bold ctermfg=10
highlight javaScriptValue  cterm=bold ctermfg=5
highlight javaScriptStringS  cterm=none ctermfg=2
highlight javaScriptStringD  cterm=none ctermfg=2
highlight javaScriptBoolean  cterm=none ctermfg=2

"HTML
"highlight link htmlTag Type
"highlight link htmlEndTag htmlTag
"highlight link htmlTagName htmlTag
