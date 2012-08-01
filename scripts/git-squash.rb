#!/usr/bin/env ruby
 
# Add an alias like this to your ~/.gitconfig file:
#
# [alias]
#   squash = !/home/$USER/scripts/git-squash.rb
 
branch = nil
origin = nil
 
`git status`.each do |line|
  if line =~ /On branch ([\w\-_]+)/
    branch = $1
  elsif line =~ /Your branch is ahead of '(.+)' by/
    origin = $1
  end
end
 
raise "hell" if branch == "squash-#{branch}" || branch.nil? || origin.nil?
 
def run(cmd)
  puts cmd
  system cmd
end
 
run "git branch -D squash-#{branch}"
run "git checkout -b squash-#{branch} #{origin}"
run "git merge --squash #{branch}"
