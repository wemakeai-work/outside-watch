# outside-watch

Polls the public health endpoints of our products every 15 minutes from GitHub Actions, outside the
platform they run on. A target is down after two failed checks 90 seconds apart; each outage opens one
issue (label `outside-watch`) and sends one mail, recovery closes it and sends one more.

    python3 test_watch.py      # tests, stdlib only
    python3 watch.py --drill   # also checks a target that is meant to fail

Run the workflow by hand with `drill` ticked to prove the alarm path end to end.
