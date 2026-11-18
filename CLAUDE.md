# outside-watch — brain

> Shared infrastructure, unnumbered (master brain rule 31), umbrella-owned. Tracker row **#20346**.
> **This repo is PUBLIC** (BJS 18-11-2026 "Outside watch: public repo"): never put an address, key, project id,
> platform-internal hostname or anything from the master brain here. Those live in the repo's SECRETS (masked) - never variables: a public repo's run logs are public and print variables.

## What it is
A GitHub Actions schedule (`*/15`) that polls our public health URLs (`TARGETS` in `watch.py`) from outside Scaleway.
Why: every other watcher is a Scaleway Job; on 01-11 a Scaleway Jobs outage (85 min) silenced the stars' crons, their
watchdogs and `watch-uptime` together (#20346). Public because Actions minutes are free there; a private repo would
spend the 3,000 shared minutes that CI and the daily batch need.

## How it alarms
- Down = two failures 90 s apart. One open issue per down target is the state: one mail per outage, one on recovery.
- Mail: Scaleway TEM to `secrets.ALARM_TO` from `secrets.ALARM_FROM` (project `secrets.SCW_PROJECT_ID`), key `secrets.SCW_TEM_KEY` (IAM app `outside-watch`,
  TEM send only, created by `Z:\tools\outside-watch-setup.py key`; copy in 1Password via day-sync secrets-up).
- Second channel: a run that opens an outage or cannot mail FAILS, so GitHub mails the account (independent of TEM).
- Keep-alive: on the 1st of the month the workflow re-enables itself (a public schedule stops after 60 days without
  activity; that the API call resets the timer is NOT-CHECKED - if the schedule ever stops, push any commit).

## Change it
Add a target to `TARGETS` (public https only - a test refuses `scw.cloud`), `python test_watch.py`, release the
repo (`release-all.py <tag> outside-watch`). Prove the alarm: Actions -> watch -> Run workflow -> drill.
