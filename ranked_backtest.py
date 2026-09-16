import json
from pathlib import Path
import pandas as pd


# ============================================================
# OMX SWING SCANNER V1.3
# FINAL BACKTEST
#
# Modell: V1.3 - oförändrad
# Max 2 samtidiga positioner
# Entry: nästa handelsdags öppning
# Stop: -8 %
# Target: +10 % / +15 %
# Max innehav: 20 handelsdagar
#
# Ingen courtage eller slippage
# ============================================================


DATA_FILE = Path("data/backtest_data.json")
OUTPUT_FILE = Path("data/final_backtest_results.json")

START_CAPITAL = 100_000.0
MAX_POSITIONS = 2

STOP_LOSS_PCT = 8.0
MAX_HOLD_DAYS = 20

TARGETS = {
    "target_10": 10.0,
    "target_15": 15.0,
}


# ------------------------------------------------------------
# V1.3 MODEL
# ------------------------------------------------------------

def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_score(df, benchmark):

    if len(df) < 200:
        return None

    close = df["Close"]

    price = close.iloc[-1]

    ma50 = close.rolling(50).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1]

    rsi_series = calculate_rsi(close)
    rsi = rsi_series.iloc[-1]

    # --------------------------------------------------------
    # Trend: 35 points
    # --------------------------------------------------------

    trend_score = 0

    if price > ma200:
        trend_score += 25

    if ma50 > ma200:
        trend_score += 10

    # --------------------------------------------------------
    # RSI: 15 points
    # --------------------------------------------------------

    rsi_score = 0

    if rsi < 35:
        rsi_score = 15
    elif rsi < 45:
        rsi_score = 8

    # --------------------------------------------------------
    # Relative strength: 25 points
    # --------------------------------------------------------

    relative_strength_score = 0

    try:
        current_stock = close.iloc[-1]

        lookback = min(127, len(df) - 1)

        old_stock = close.iloc[-1 - lookback]

        # Match benchmark by date
        current_date = df.index[-1]

        benchmark_close = benchmark["Close"]

        if current_date in benchmark_close.index:

            benchmark_current = benchmark_close.loc[current_date]

            old_date = df.index[-1 - lookback]

            if old_date in benchmark_close.index:

                benchmark_old = benchmark_close.loc[old_date]

                stock_return = (
                    current_stock / old_stock - 1
                ) * 100

                benchmark_return = (
                    benchmark_current / benchmark_old - 1
                ) * 100

                relative_strength = (
                    stock_return - benchmark_return
                )

                if relative_strength >= 10:
                    relative_strength_score = 25
                elif relative_strength >= 5:
                    relative_strength_score = 15
                elif relative_strength >= 0:
                    relative_strength_score = 8

            else:
                relative_strength = None

        else:
            relative_strength = None

    except Exception:
        relative_strength = None

    # --------------------------------------------------------
    # Momentum: 10 points
    # --------------------------------------------------------

    momentum_score = 0

    if price > ma50:
        momentum_score = 10

    # --------------------------------------------------------
    # Volatility / Pullback: V1.3 pullback component
    # --------------------------------------------------------

    pullback_score = 0

    high_20 = close.tail(20).max()

    pullback = (
        (high_20 - price) / high_20
    ) * 100

    # EXACT V1.3 LOGIC
    if pullback >= 5 and pullback <= 15:
        pullback_score = 10
    elif pullback >= 3:
        pullback_score = 6

    # --------------------------------------------------------
    # Total
    # --------------------------------------------------------

    total_score = (
        trend_score
        + rsi_score
        + relative_strength_score
        + momentum_score
        + pullback_score
    )

    if total_score >= 85:
        signal = "KÖP"
    elif total_score >= 70:
        signal = "BEVAKA"
    else:
        signal = "AVVAKTA"

    return {
        "score": total_score,
        "signal": signal,
        "price": price,
        "ma50": ma50,
        "ma200": ma200,
        "rsi": rsi,
        "relative_strength": relative_strength,
        "pullback": pullback,
    }


# ------------------------------------------------------------
# LOAD DATA
# ------------------------------------------------------------

print("Läser backtest-data...")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    raw_data = json.load(f)


data = {}

for ticker, values in raw_data.items():

    if not isinstance(values, list):
    continue

    print("TICKER:", ticker)
    print("TYPE:", type(values))
    print("FIRST:", values[0] if isinstance(values, list) and len(values) > 0 else values)

    df = pd.DataFrame(values)
    

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")

    df = df.sort_index()

    for column in ["Open", "High", "Low", "Close"]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=["Open", "High", "Low", "Close"]
    )

    data[ticker] = df


benchmark = data["^OMXS30"]

tickers = [
    ticker
    for ticker in data
    if ticker != "^OMXS30"
]


# ------------------------------------------------------------
# COMMON TRADING DATES
# ------------------------------------------------------------

all_dates = set()

for ticker in tickers:

    all_dates.update(
        data[ticker].index
    )

dates = sorted(all_dates)


# ------------------------------------------------------------
# BACKTEST FUNCTION
# ------------------------------------------------------------

def run_backtest(target_pct):

    print()
    print("=" * 60)
    print(
        f"STARTAR TEST: target +{target_pct:.0f}%"
    )
    print("=" * 60)

    capital = START_CAPITAL

    equity_curve = []

    open_positions = {}

    trades = []

    skipped_signals = []

    previous_equity = capital

    # --------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------

    for date_index, date in enumerate(dates):

        # ----------------------------------------------------
        # 1. EXIT EXISTING POSITIONS
        # ----------------------------------------------------

        positions_to_remove = []

        for ticker, position in list(
            open_positions.items()
        ):

            df = data[ticker]

            if date not in df.index:
                continue

            current_index = df.index.get_loc(date)

            entry_index = position["entry_index"]

            holding_days = (
                current_index - entry_index + 1
            )

            row = df.iloc[current_index]

            entry_price = position["entry_price"]

            stop_price = (
                entry_price
                * (1 - STOP_LOSS_PCT / 100)
            )

            target_price = (
                entry_price
                * (1 + target_pct / 100)
            )

            exit_price = None
            exit_reason = None

            # ------------------------------------------------
            # STOP FIRST
            # ------------------------------------------------

            if row["Low"] <= stop_price:

                exit_price = stop_price
                exit_reason = "STOP"

            elif row["High"] >= target_price:

                exit_price = target_price
                exit_reason = "TARGET"

            # ------------------------------------------------
            # MAX HOLD
            # ------------------------------------------------

            elif holding_days >= MAX_HOLD_DAYS:

                exit_price = row["Close"]
                exit_reason = "MAX_HOLD"

            # ------------------------------------------------
            # CLOSE POSITION
            # ------------------------------------------------

            if exit_price is not None:

                result_pct = (
                    exit_price / entry_price - 1
                ) * 100

                capital_before = capital

                capital *= (
                    1 + result_pct / 100
                )

                trade = {
                    "ticker": ticker,
                    "signal_date": position[
                        "signal_date"
                    ].strftime("%Y-%m-%d"),

                    "entry_date": position[
                        "entry_date"
                    ].strftime("%Y-%m-%d"),

                    "exit_date": date.strftime(
                        "%Y-%m-%d"
                    ),

                    "score": position["score"],

                    "signal": position["signal"],

                    "entry_price": entry_price,

                    "exit_price": exit_price,

                    "result_pct": result_pct,

                    "exit_reason": exit_reason,

                    "holding_days": holding_days,

                    "capital_before": capital_before,

                    "capital_after": capital,
                }

                trades.append(trade)

                positions_to_remove.append(
                    ticker
                )

        for ticker in positions_to_remove:

            del open_positions[ticker]

        # ----------------------------------------------------
        # 2. FIND NEW CANDIDATES
        # ----------------------------------------------------

        candidates = []

        for ticker in tickers:

            # Already holding this stock
            if ticker in open_positions:
                continue

            df = data[ticker]

            if date not in df.index:
                continue

            current_index = df.index.get_loc(date)

            # Need next day for entry
            if current_index >= len(df) - 1:
                continue

            historical_df = df.iloc[
                :current_index + 1
            ]

            result = calculate_score(
                historical_df,
                benchmark
            )

            if result is None:
                continue

            if result["signal"] not in [
                "BEVAKA",
                "KÖP",
            ]:
                continue

            if result["score"] < 70:
                continue

            candidates.append({
                "ticker": ticker,
                **result,
            })

        # ----------------------------------------------------
        # 3. RANK CANDIDATES
        # ----------------------------------------------------

        candidates.sort(
            key=lambda x: (
                -x["score"],

                -(
                    x["relative_strength"]
                    if x["relative_strength"]
                    is not None
                    else -999
                ),

                -x["pullback"],

                x["ticker"],
            )
        )

        # ----------------------------------------------------
        # 4. OPEN POSITIONS UNTIL MAX 2
        # ----------------------------------------------------

        free_slots = (
            MAX_POSITIONS
            - len(open_positions)
        )

        selected = candidates[
            :free_slots
        ]

        for candidate in selected:

            ticker = candidate["ticker"]

            df = data[ticker]

            current_index = df.index.get_loc(
                date
            )

            entry_index = current_index + 1

            entry_date = df.index[
                entry_index
            ]

            entry_price = float(
                df.iloc[entry_index]["Open"]
            )

            open_positions[ticker] = {

                "ticker": ticker,

                "signal_date": date,

                "entry_date": entry_date,

                "entry_index": entry_index,

                "entry_price": entry_price,

                "score": candidate["score"],

                "signal": candidate["signal"],
            }

        # ----------------------------------------------------
        # 5. EQUITY CURVE
        # ----------------------------------------------------

        equity_curve.append({
            "date": date.strftime(
                "%Y-%m-%d"
            ),
            "capital": capital,
            "open_positions": len(
                open_positions
            ),
        })

    # --------------------------------------------------------
    # CLOSE REMAINING POSITIONS AT END
    # --------------------------------------------------------
    #
    # These are NOT included in performance.
    # Same principle as previous tests.
    # --------------------------------------------------------

    open_at_end = []

    for ticker, position in open_positions.items():

        open_at_end.append({
            "ticker": ticker,
            "entry_date": position[
                "entry_date"
            ].strftime("%Y-%m-%d"),
            "entry_price": position[
                "entry_price"
            ],
            "score": position["score"],
        })

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    if trades:

        results = [
            t["result_pct"]
            for t in trades
        ]

        wins = [
            x for x in results
            if x > 0
        ]

        losses = [
            x for x in results
            if x <= 0
        ]

        total_return_pct = (
            capital / START_CAPITAL - 1
        ) * 100

        average_trade = sum(
            results
        ) / len(results)

        hit_rate = (
            len(wins)
            / len(results)
        ) * 100

        average_win = (
            sum(wins) / len(wins)
            if wins else 0
        )

        average_loss = (
            sum(losses) / len(losses)
            if losses else 0
        )

        stop_count = sum(
            1 for t in trades
            if t["exit_reason"] == "STOP"
        )

        target_count = sum(
            1 for t in trades
            if t["exit_reason"] == "TARGET"
        )

        max_hold_count = sum(
            1 for t in trades
            if t["exit_reason"] == "MAX_HOLD"
        )

        average_days = sum(
            t["holding_days"]
            for t in trades
        ) / len(trades)

    else:

        total_return_pct = 0
        average_trade = 0
        hit_rate = 0
        average_win = 0
        average_loss = 0
        stop_count = 0
        target_count = 0
        max_hold_count = 0
        average_days = 0

    # --------------------------------------------------------
    # EQUITY / DRAWDOWN
    # --------------------------------------------------------

    equity_df = pd.DataFrame(
        equity_curve
    )

    equity_df["peak"] = (
        equity_df["capital"]
        .cummax()
    )

    equity_df["drawdown_pct"] = (
        equity_df["capital"]
        / equity_df["peak"]
        - 1
    ) * 100

    max_drawdown = (
        equity_df["drawdown_pct"].min()
    )

    # --------------------------------------------------------
    # YEARLY RESULTS
    # --------------------------------------------------------

    yearly = {}

    for trade in trades:

        year = trade["exit_date"][:4]

        if year not in yearly:
            yearly[year] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "result_sum_pct": 0.0,
            }

        yearly[year]["trades"] += 1

        yearly[year][
            "result_sum_pct"
        ] += trade["result_pct"]

        if trade["result_pct"] > 0:
            yearly[year]["wins"] += 1
        else:
            yearly[year]["losses"] += 1

    # --------------------------------------------------------
    # COMPOUNDED YEARLY RETURN
    # --------------------------------------------------------

    yearly_capital = START_CAPITAL

    yearly_compounded = {}

    for year in sorted(yearly):

        year_trades = [
            t for t in trades
            if t["exit_date"][:4] == year
        ]

        capital_before_year = (
            yearly_capital
        )

        for trade in year_trades:

            yearly_capital *= (
                1
                + trade["result_pct"]
                / 100
            )

        year_return = (
            yearly_capital
            / capital_before_year
            - 1
        ) * 100

        yearly_compounded[year] = {
            "start_capital":
                capital_before_year,

            "end_capital":
                yearly_capital,

            "return_pct":
                year_return,

            "trades":
                len(year_trades),
        }

    # --------------------------------------------------------
    # CAGR
    # --------------------------------------------------------

    first_date = pd.to_datetime(
        equity_curve[0]["date"]
    )

    last_date = pd.to_datetime(
        equity_curve[-1]["date"]
    )

    years = (
        (last_date - first_date).days
        / 365.25
    )

    if years > 0:

        cagr = (
            (
                capital
                / START_CAPITAL
            ) ** (1 / years)
            - 1
        ) * 100

    else:

        cagr = 0

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {

        "settings": {

            "model": "v1.3",

            "starting_capital":
                START_CAPITAL,

            "max_positions":
                MAX_POSITIONS,

            "stop_loss_pct":
                STOP_LOSS_PCT,

            "target_pct":
                target_pct,

            "max_hold_days":
                MAX_HOLD_DAYS,

            "entry":
                "next_day_open",

            "same_day_stop_first":
                True,

            "commission":
                0,

            "slippage":
                0,

            "universe":
                len(tickers),
        },

        "summary": {

            "trades":
                len(trades),

            "wins":
                len(wins)
                if trades else 0,

            "losses":
                len(losses)
                if trades else 0,

            "hit_rate_pct":
                hit_rate,

            "stops":
                stop_count,

            "targets":
                target_count,

            "max_holding":
                max_hold_count,

            "average_result_pct":
                average_trade,

            "total_result_pct":
                total_return_pct,

            "average_win_pct":
                average_win,

            "average_loss_pct":
                average_loss,

            "average_days":
                average_days,

            "max_drawdown_pct":
                max_drawdown,

            "cagr_pct":
                cagr,

            "final_capital":
                capital,

            "open_positions_at_end":
                len(open_at_end),
        },

        "yearly":
            yearly,

        "yearly_compounded":
            yearly_compounded,

        "trades":
            trades,

        "open_positions_at_end":
            open_at_end,

        "equity_curve":
            equity_curve,
    }


# ------------------------------------------------------------
# RUN BOTH TARGETS
# ------------------------------------------------------------

results = {

    "model":
        "OMX Swing Scanner v1.3",

    "description":
        "Final test: maximum 2 simultaneous positions",

    "data_period": {

        "from":
            str(dates[0].date()),

        "to":
            str(dates[-1].date()),

        "trading_days":
            len(dates),
    },

    "scenarios": {

        "target_10":
            run_backtest(10.0),

        "target_15":
            run_backtest(15.0),
    },
}


# ------------------------------------------------------------
# SAVE
# ------------------------------------------------------------

OUTPUT_FILE.parent.mkdir(
    exist_ok=True
)

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        results,
        f,
        indent=2,
        ensure_ascii=False
    )


print()
print("=" * 60)
print("KLART")
print("=" * 60)

for name, scenario in results[
    "scenarios"
].items():

    s = scenario["summary"]

    print()
    print(name)

    print(
        f"Affärer: {s['trades']}"
    )

    print(
        f"Träffsäkerhet: "
        f"{s['hit_rate_pct']:.2f}%"
    )

    print(
        f"Slutkapital: "
        f"{s['final_capital']:.2f} kr"
    )

    print(
        f"Total avkastning: "
        f"{s['total_result_pct']:.2f}%"
    )

    print(
        f"CAGR: "
        f"{s['cagr_pct']:.2f}%"
    )

    print(
        f"Max drawdown: "
        f"{s['max_drawdown_pct']:.2f}%"
    )

    print(
        f"Genomsnitt/affär: "
        f"{s['average_result_pct']:.3f}%"
    )

    print(
        f"Stoppar: "
        f"{s['stops']}"
    )

    print(
        f"Targets: "
        f"{s['targets']}"
    )

    print(
        f"20-dagars exits: "
        f"{s['max_holding']}"
    )

print()
print(
    f"Resultat sparat i: "
    f"{OUTPUT_FILE}"
)
