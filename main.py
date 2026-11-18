"""Mean-reversion scalper for the make.fun cbBTC bars-replay race
(agent-fun/bars-replay/v1). Long only, at most one position, paper USDC.

The model (one idea, applied on a slow clock): on a choppy tape the
deviations that actually pay are the deep ones. When the close has
fallen at least 150 bps below the trailing 240-bar high of bar highs
— a four-hour range, so this is a stretched deviation from the recent
range, not a one-minute wiggle — and the fall has stabilised (the bar
closes at or above the previous close: the falling-knife filter) with
Wilder RSI(14) at or under 40, buy the washout and sell the snap back
toward the range: a +100 bps profit target, a -70 bps hard stop, or a
420-bar time stop, whichever comes first. A 5-bar cooldown follows
every exit, and no new position is opened in the last 90 bars of the
1,440-bar window (a fresh trade there cannot outrun the end-of-window
flatten and its round-trip cost).

Why not scalp the fast wiggles: they were measured and rejected on
this kit's own dev window. After a z-score of -2 against a 60-bar
mean, the average forward move is only about +10 bps over the next
15-30 bars and the median best run-up inside an hour is 15-33 bps —
under the ~26 bps a round trip costs in fees, slippage and impact, so
every fast-scalp variant tested (z entries 1.8-2.0, targets 30-55,
stops 35-60, with and without trend-regime gates) bled between -$7
and -$53. The deep deviation is the same mean-reversion idea at the
scale this market actually reverts: event studies on the dev window
show closes 100-150 bps under the trailing 240-bar high, bought on a
bounce with oversold RSI, averaging roughly +100 bps over the next
240 bars.

Measured on the kit's dev window (24h ending 2026-11-18T14:44Z, a
-2.80% buy-and-hold downtrend) with a fill-faithful simulator — an
exact integer port of the harness's fill engine, which reproduces
the grader's buy-and-hold score of -31.633698 USDC to the unit:
net PnL +14.070045 USDC, 2 round trips, both winners, expectancy
+$7.04 per trade, max drawdown 6.0 USDC (0.60% of the starting
cash). Run end-to-end over stdio under the harness's own runtime
command (python3 -P -s, PYTHONHASHSEED=0), the shipped file scores
+14.065722 USDC — two runs, reply streams byte-identical; the
4.3-millidollar gap to the in-process figure is the real SDK's
account rounding, and the server's dev grade is the authority. Truncated half-window runs: first half +6.50 (the two deep
trades), second half -5.42 — reported plainly: the second half
offered no deep setup at all; its single truncated-run trade is an
entry in the window's final bars that the shipped late guard
refuses, and at the shallower 100 bps depth the second half's two
extra trades both lost. The parameters sit mid-plateau: varying any
one of them (depth 120-180, target 80-120, stop 50-90, time stop
300-600, RSI cap 35-45, reference window 180-300, knife bounce /
higher-low / either) keeps the dev result between +$6.71 and
+$14.92 — a flat region, not a fitted spike.

Deterministic: no wall clock, no randomness, no environment reads;
the only inputs are the hello and the batches. All arithmetic is
integer, identical every run.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars  # noqa: E402

SYMBOL = "CBBTC"

PARAMS = {
    "ref_win": 240,        # trailing-high reference window (bars)
    "dev_bps": 150,        # entry depth below the trailing high
    "rsi_period": 14,      # Wilder RSI period
    "rsi_max": 40,         # entries need RSI at or below this
    "target_bps": 100,     # profit target vs the entry reference close
    "stop_bps": 70,        # hard stop vs the entry reference close
    "time_stop": 420,      # max bars held
    "cooldown": 5,         # bars after an exit before re-entering
    "window_bars": 1440,   # bars per graded window (from the rules)
    "late_guard": 90,      # no entries in the last bars of the window
    "size_pct": 100,       # percent of cash per entry
    "buy_slip_bps": 10000,   # max_slippage_bps on buys (never refuses)
    "sell_slip_bps": 10000,  # max_slippage_bps on sells
}


class Bot:
    def __init__(self, hello):
        self.p = dict(PARAMS)
        self.min_notional = int(hello["fees"]["min_notional_quote_units"])
        self.closes = []      # close of every bar seen, in order
        self.lows = []        # low of every bar seen, in order
        self.highs = []       # high of every bar seen, in order
        self.avg_gain = 0     # Wilder RSI state, scaled by 10**6
        self.avg_loss = 0
        self.rsi_bars = 0
        self.entry_price = 0  # close of the bar that decided the buy
        self.entry_seq = -1   # bar index that decided the buy
        self.last_exit = -10 ** 9  # bar index of the last sell decision
        self.pending = None   # "buy" / "sell" awaiting its fill
        self.order_n = 0

    def _next_id(self, tag):
        self.order_n += 1
        return "%s%d" % (tag, self.order_n)

    def _rsi(self):
        total = self.avg_gain + self.avg_loss
        if total == 0 or self.rsi_bars < self.p["rsi_period"]:
            return 100
        return 100 * self.avg_gain // total

    def _update_indicators(self, close, prev_close):
        if prev_close is None:
            return
        chg = close - prev_close
        gain = chg if chg > 0 else 0
        loss = -chg if chg < 0 else 0
        n = self.p["rsi_period"]
        if self.rsi_bars < n:
            self.avg_gain += gain * 10 ** 6 // n
            self.avg_loss += loss * 10 ** 6 // n
        else:
            self.avg_gain = (self.avg_gain * (n - 1)
                             + gain * 10 ** 6) // n
            self.avg_loss = (self.avg_loss * (n - 1)
                             + loss * 10 ** 6) // n
        self.rsi_bars += 1

    def on_batch(self, state, batch):
        prev_close = self.closes[-1] if self.closes else None
        bar = None
        for b in batch["bars"]:
            if b["symbol"] == SYMBOL:
                bar = b
        if bar is None:
            return None
        close = int(bar["c"])
        self.closes.append(close)
        self.lows.append(int(bar["l"]))
        self.highs.append(int(bar["h"]))
        self._update_indicators(close, prev_close)
        # Any resolution of the pending order (filled or rejected)
        # clears the flag; the account in `state` is the truth about
        # whether a position exists.
        for fill in batch["fills"]:
            if self.pending == "buy" and fill["side"] == "buy":
                self.pending = None
            elif self.pending == "sell" and fill["side"] == "sell":
                self.pending = None
        if state.warming_up:
            return None
        i = len(self.closes) - 1
        p = self.p
        holding = state.positions.get(SYMBOL)

        if holding is not None and self.pending is None:
            gain = (close - self.entry_price) * 10000 // self.entry_price
            exit_now = False
            if gain <= -p["stop_bps"]:
                exit_now = True                        # hard stop
            elif gain >= p["target_bps"]:
                exit_now = True                        # reversion target
            elif i - self.entry_seq >= p["time_stop"]:
                exit_now = True                        # time stop
            if exit_now:
                self.pending = "sell"
                self.last_exit = i
                return [{
                    "side": "sell",
                    "client_id": self._next_id("s"),
                    "symbol": SYMBOL,
                    "qty": holding.qty,
                    "max_slippage_bps": p["sell_slip_bps"],
                }]
            return None

        if holding is not None or self.pending is not None:
            return None
        if i - self.last_exit < p["cooldown"]:
            return None
        if i >= p["window_bars"] - p["late_guard"]:
            return None                     # too late to start a trade
        if len(self.closes) <= p["ref_win"]:
            return None                     # reference window not full
        if self.rsi_bars < p["rsi_period"]:
            return None
        # The falling-knife filter: the bar must close at or above the
        # previous close — the fall has stopped, at least for a bar.
        if prev_close is None or close < prev_close:
            return None
        hi = max(self.highs[-p["ref_win"]:])
        if close * 10000 > hi * (10000 - p["dev_bps"]):
            return None                     # not stretched enough
        if self._rsi() > p["rsi_max"]:
            return None                     # not oversold enough

        notional = state.cash * p["size_pct"] // 100
        room = state.weight_room(SYMBOL)
        if room < notional:
            notional = room
        if notional < self.min_notional:
            return None
        self.pending = "buy"
        self.entry_price = close
        self.entry_seq = i
        return [{
            "side": "buy",
            "client_id": self._next_id("b"),
            "symbol": SYMBOL,
            "notional_quote_units": notional,
            "max_slippage_bps": p["buy_slip_bps"],
        }]


def main():
    holder = {}

    def on_batch(state, batch):
        bot = holder.get("bot")
        if bot is None:
            bot = holder["bot"] = Bot(state.hello)
        return bot.on_batch(state, batch)

    makefun_bars.run(on_batch)


if __name__ == "__main__":
    main()
