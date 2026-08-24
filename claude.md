# General instructions

## The poll site is served by nginx from /var/www/pollsite/polls on con1.
This repo is checked out on con1 itself as well as on a WSL workstation, so
that path is *local* when you are running on con1 and *remote* (the `con1`
ssh alias) when you are not. Check `hostname` if you are unsure: con1 is
vmi2124707.contaboserver.net.

## When asked to check recency of deployment: Examine each .png file in this directory, then check that there is a .png file with the same name in /var/www/pollsite/polls, and that the date of the deployed file is later than the local one. If any deployed file is older, copy the corresponding newer local file up to the polls directory — with `cp -p` when this machine is con1, with `scp` to con1 otherwise. The directory is owned by agold either way, so no sudo is needed.

## When asked to check for new polls, see if there has been any update on the original source from which the polling data was download.
