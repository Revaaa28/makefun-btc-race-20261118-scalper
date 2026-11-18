# makefun-btc-race-20261118-scalper

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/Revaaa28/makefun-btc-race-20261118-scalper/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/Revaaa28/makefun-btc-race-20261118-scalper/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A mean-reversion scalper for the make.fun 24h cbBTC/USDC bars-replay race (agent-fun/bars-replay/v1), long only on 1-minute bars. It buys the deep deviations this tape actually reverts: when the close sits at least 150 bps below the trailing 240-bar high, the fall has stabilised (a bounce bar — the falling-knife filter) and Wilder RSI(14) is at or under 40, it buys the washout and sells the snap back with a +100 bps target, a -70 bps hard stop, or a 420-bar time stop. Fast z-score scalping was measured on the dev window and rejected — the average bounce after a -2σ stretch is ~10 bps, under the ~26 bps round-trip cost — so the scalping runs on the four-hour clock instead of the one-minute one. On the kit's dev window (a -2.80% downtrend day) it nets +$14.07 over 2 round trips with a 0.60% max drawdown; the full design notes, the rejected variants, and the half-window results are in the docstring of main.py.

## Run it

```sh
python3 main.py   # speaks agent-fun/bars-replay/v1 on stdin/stdout; the harness drives it bar by bar
# Grade it on the kit's dev window from the unpacked kit directory:
node cli/makefun.mjs grade-local --kit . --bot <this repository> --driver docker
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=revaaa28&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>
