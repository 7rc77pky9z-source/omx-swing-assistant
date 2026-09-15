import json
from pathlib import Path
from statistics import mean


# ============================================================
# OMX SWING SCANNER v1.3 - BACKTEST
#
# TESTAR DEN BEFINTLIGA MODELLEN.
# INGA ÄNDRINGAR AV SCOREMODELLEN.
#
# Score:
#   Trend              35
#   RSI                15
#   Relative strength  25
#   Momentum           10
#   Pullback            10
#
# Max: 95 poäng
#
# Signaler:
#   >= 85  KÖP
#   70-84 BEVAKA
#   <70   AVVAKTA
#
# Trade:
#   Entry = nästa dags öppning
#   Stop  = -8 %
#   Target = +10 % eller +15 %
#   Max holding = 20 handelsdagar
# ============================================================


DATA_FILE = Path("data/backtest_data.json")
RESULT_FILE = Path("data/backtest_results.json")


STOCK_TICKERS = [
    "ABB.ST",
    "ALFA.ST",
    "ASSA-B.ST",
    "ATCO-A.ST",
    "AZN.ST",
    "BOL.ST",
    "ELUX-B.ST",
    "ERIC-B.ST",
    "EVO.ST",
    "HEXA-B.ST",
    "HM-B.ST",
    "INVE-B.ST",
    "KINV-B.ST",
    "NDA-SE.ST",
    "SAND.ST",
    "SCA-B.ST",
    "SEB-A.ST",
    "SHB-A.ST",
    "SINCH.ST",
    "SKF-B.ST",
    "SWED-A.ST",
    "TEL2-B.ST",
    "TELIA.ST",
    "VOLV-B.ST",
]

BENCHMARK = "^OMXS30"

STOP_PCT = 0.08
TARGET_10 = 0.10
TARGET_15 = 0.15
MAX_HOLDING_DAYS = 20


# ------------------------------------------------------------
# Hjälpfunktioner
# ------------------------------------------------------------

def sma(values, n):
    if len(values) < n:
        return None

    return sum(values[-n:]) / n


def rsi_v13(values):
    """
    Exakt samma RSI-logik som v1.3.
    """

    n = 14

    if len(values) <= n:
        return None

    gains = 0
    losses = 0

    for i in range(len(values) - n, len(values)):
        d = values[i] - values[i - 1]

        if d > 0:
            gains += d
        else:
            losses -= d

    if losses == 0:
        return 100

    return 100 - 100 / (1 + gains / losses)


def relative_strength(stock_prices, benchmark_prices):
    """
    Samma princip som nuvarande v1.3:
    aktiens utveckling minus OMXS30:s utveckling
    över 127 datapunkter.
    """

    n = 127

    if len(stock_prices) < n or len(benchmark_prices) < n:
        return None

    stock_start = stock_prices[-n]
    benchmark_start = benchmark_prices[-n]

    if stock_start == 0 or benchmark_start == 0:
        return None

    stock_return = stock_prices[-1] / stock_start - 1
    benchmark_return = benchmark_prices[-1] / benchmark_start - 1

    return stock_return - benchmark_return


def pullback_v13(prices, n=20):
    """
    Exakt samma pullback-logik som v1.3.
    """

    if len(prices) < n:
        return None

    high = max(prices[-n:])

    if high == 0:
        return None

    return (1 - prices[-1] / high) * 100


def calculate_score(stock_prices, benchmark_prices):
    """
    Exakt befintlig v1.3-modell.
    """

    if len(stock_prices) < 200:
        return None

    ma50 = sma(stock_prices, 50)
    ma200 = sma(stock_prices, 200)
    current = stock_prices[-1]

    if ma50 is None or ma200 is None:
        return None

    # -------------------------
    # Trend 35
    # -------------------------

    trend = 0

    if current > ma200:
        trend += 25

    if ma50 > ma200:
        trend += 10

    # -------------------------
    # RSI 15
    # -------------------------

    r = rsi_v13(stock_prices)

    rsi_points = 0

    if r is not None:

        if r < 35:
            rsi_points = 15

        elif r < 45:
            rsi_points = 8

    # -------------------------
    # Relative strength 25
    # -------------------------

    rs = relative_strength(
        stock_prices,
        benchmark_prices
    )

    rs_points = 0

    if rs is not None:

        rs_percent = rs * 100

        if rs_percent >= 10:
            rs_points = 25

        elif rs_percent >= 5:
            rs_points = 15

        elif rs_percent >= 0:
            rs_points = 8

    # -------------------------
    # Momentum 10
    # -------------------------

    momentum = 0

    if current > ma50:
        momentum = 10

    # -------------------------
    # Pullback 10
    # -------------------------

    pb = pullback_v13(stock_prices)

    pullback_points = 0

    if pb is not None:

        if pb >= 5 and pb <= 15:
            pullback_points = 10

        elif pb >= 3:
            pullback_points = 6

    # -------------------------
    # Total
    # -------------------------

    score = min(
        100,
        trend
        + rsi_points
        + rs_points
        + momentum
        + pullback_points
    )

    if score >= 85:
        signal = "KÖP"

    elif score >= 70:
        signal = "BEVAKA"

    else:
        signal = "AVVAKTA"

    return {
        "score": score,
        "signal": signal,
        "trend": trend,
        "rsi_points": rsi_points,
        "relative_strength_points": rs_points,
        "momentum": momentum,
        "pullback_points": pullback_points,
        "rsi": r,
        "relative_strength": rs,
        "pullback": pb,
        "ma50": ma50,
        "ma200": ma200,
    }


# ------------------------------------------------------------
# Ladda data
# ------------------------------------------------------------

if not DATA_FILE.exists():
    raise FileNotFoundError(
        f"Hittar inte {DATA_FILE}"
    )


with DATA_FILE.open("r", encoding="utf-8") as f:
    raw = json.load(f)


stocks = raw["stocks"]


print()
print("========================================")
print("OMX SWING SCANNER v1.3 BACKTEST")
print("========================================")
print()


# ------------------------------------------------------------
# Förbered data
# ------------------------------------------------------------

prepared = {}

for ticker in STOCK_TICKERS + [BENCHMARK]:

    if ticker not in stocks:
        print("SAKNAS:", ticker)
        continue

    rows = stocks[ticker]

    by_date = {}

    for row in rows:
        by_date[row["date"]] = row

    prepared[ticker] = by_date


# ------------------------------------------------------------
# Gemensamma datum
# ------------------------------------------------------------

all_dates = None

for ticker in prepared:

    dates = set(prepared[ticker].keys())

    if all_dates is None:
        all_dates = dates
    else:
        all_dates &= dates


dates = sorted(all_dates)

print("Gemensamma handelsdagar:", len(dates))
print(
    "Period:",
    dates[0],
    "->",
    dates[-1]
)
print()


# ------------------------------------------------------------
# Skapa historiska prislistor
# ------------------------------------------------------------

price_history = {}

for ticker in prepared:

    price_history[ticker] = {
        "open": [],
        "high": [],
        "low": [],
        "close": [],
    }

    for date in dates:

        row = prepared[ticker][date]

        price_history[ticker]["open"].append(row["open"])
        price_history[ticker]["high"].append(row["high"])
        price_history[ticker]["low"].append(row["low"])
        price_history[ticker]["close"].append(row["close"])


# ------------------------------------------------------------
# Backtestfunktion
# ------------------------------------------------------------

def run_strategy(min_score):

    trades = []

    # En öppen position per aktie.
    open_positions = {}

    # Vi börjar när minst 200 dagar finns.
    start_index = 200

    for i in range(start_index, len(dates) - 1):

        date = dates[i]
        next_date = dates[i + 1]

        benchmark_prices = (
            price_history[BENCHMARK]["close"][:i + 1]
        )

        for ticker in STOCK_TICKERS:

            if ticker not in price_history:
                continue

            # ------------------------------------------------
            # Hantera befintlig position
            # ------------------------------------------------

            if ticker in open_positions:

                position = open_positions[ticker]

                entry_price = position["entry_price"]
                entry_index = position["entry_index"]

                low = price_history[ticker]["low"][i]
                high = price_history[ticker]["high"][i]
                close = price_history[ticker]["close"][i]

                stop_price = entry_price * (1 - STOP_PCT)
                target_price = (
                    entry_price
                    * (1 + position["target_pct"])
                )

                days_held = i - entry_index

                exit_reason = None
                exit_price = None

                # Om både stop och target träffas samma dag
                # använder vi den konservativa tolkningen:
                # STOP träffas först.
                if low <= stop_price:

                    exit_reason = "STOP -8%"
                    exit_price = stop_price

                elif high >= target_price:

                    exit_reason = (
                        f"TARGET +{int(position['target_pct'] * 100)}%"
                    )
                    exit_price = target_price

                elif days_held >= MAX_HOLDING_DAYS:

                    exit_reason = "MAX 20 DAGAR"
                    exit_price = close

                if exit_reason:

                    result_pct = (
                        exit_price / entry_price - 1
                    ) * 100

                    trades.append({
                        "ticker": ticker,
                        "signal_date": position["signal_date"],
                        "entry_date": position["entry_date"],
                        "exit_date": date,
                        "score": position["score"],
                        "signal": position["signal"],
                        "entry_price": round(entry_price, 4),
                        "exit_price": round(exit_price, 4),
                        "target_pct": position["target_pct"] * 100,
                        "result_pct": round(result_pct, 4),
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                    })

                    del open_positions[ticker]

                    continue

            # ------------------------------------------------
            # Ny signal
            # ------------------------------------------------

            # Kan inte öppna ny position om en redan finns.
            if ticker in open_positions:
                continue

            stock_prices = (
                price_history[ticker]["close"][:i + 1]
            )

            result = calculate_score(
                stock_prices,
                benchmark_prices
            )

            if result is None:
                continue

            if result["score"] < min_score:
                continue

            # Signal beräknas vid dagens stängning.
            # Entry sker nästa dags öppning.
            entry_price = (
                price_history[ticker]["open"][i + 1]
            )

            open_positions[ticker] = {
                "signal_date": date,
                "entry_date": next_date,
                "entry_index": i + 1,
                "entry_price": entry_price,
                "score": result["score"],
                "signal": result["signal"],
                "target_pct": TARGET_10,
            }

    return trades


# ------------------------------------------------------------
# Kör fyra separata resultat:
#
# KÖP +10
# KÖP +15
# BEVAKA/KÖP +10
# BEVAKA/KÖP +15
# ------------------------------------------------------------

def summarize(trades):

    if not trades:

        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "stops": 0,
            "targets": 0,
            "max_holding": 0,
            "hit_rate": 0,
            "average_result": 0,
            "total_result": 0,
            "average_win": 0,
            "average_loss": 0,
            "average_days": 0,
        }

    wins = [
        t for t in trades
        if t["result_pct"] > 0
    ]

    losses = [
        t for t in trades
        if t["result_pct"] <= 0
    ]

    stops = [
        t for t in trades
        if t["exit_reason"] == "STOP -8%"
    ]

    targets = [
        t for t in trades
        if t["exit_reason"].startswith("TARGET")
    ]

    max_holding = [
        t for t in trades
        if t["exit_reason"] == "MAX 20 DAGAR"
    ]

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "stops": len(stops),
        "targets": len(targets),
        "max_holding": len(max_holding),
        "hit_rate": round(
            len(wins) / len(trades) * 100,
            2
        ),
        "average_result": round(
            mean(t["result_pct"] for t in trades),
            3
        ),
        "total_result": round(
            sum(t["result_pct"] for t in trades),
            3
        ),
        "average_win": round(
            mean(t["result_pct"] for t in wins),
            3
        ) if wins else 0,
        "average_loss": round(
            mean(t["result_pct"] for t in losses),
            3
        ) if losses else 0,
        "average_days": round(
            mean(t["days_held"] for t in trades),
            2
        ),
    }


# ------------------------------------------------------------
# Kör tester
# ------------------------------------------------------------

print("Kör BEVAKA/KÖP...")
trades_70 = run_strategy(70)

print("Kör endast KÖP...")
trades_85 = run_strategy(85)


# Vi kör även +15%-target separat.
#
# Ändra target i varje trade från +10 till +15
# och kör om exitlogiken genom en separat enkel simulering.


def rerun_with_target(min_score, target_pct):

    trades = []

    open_positions = {}

    for i in range(200, len(dates) - 1):

        date = dates[i]
        next_date = dates[i + 1]

        benchmark_prices = (
            price_history[BENCHMARK]["close"][:i + 1]
        )

        for ticker in STOCK_TICKERS:

            if ticker not in price_history:
                continue

            if ticker in open_positions:

                position = open_positions[ticker]

                entry_price = position["entry_price"]

                low = price_history[ticker]["low"][i]
                high = price_history[ticker]["high"][i]
                close = price_history[ticker]["close"][i]

                stop_price = entry_price * (
                    1 - STOP_PCT
                )

                target_price = entry_price * (
                    1 + target_pct
                )

                days_held = (
                    i - position["entry_index"]
                )

                exit_reason = None
                exit_price = None

                if low <= stop_price:

                    exit_reason = "STOP -8%"
                    exit_price = stop_price

                elif high >= target_price:

                    exit_reason = (
                        f"TARGET +{int(target_pct * 100)}%"
                    )
                    exit_price = target_price

                elif days_held >= MAX_HOLDING_DAYS:

                    exit_reason = "MAX 20 DAGAR"
                    exit_price = close

                if exit_reason:

                    result_pct = (
                        exit_price / entry_price - 1
                    ) * 100

                    trades.append({
                        "ticker": ticker,
                        "signal_date": position["signal_date"],
                        "entry_date": position["entry_date"],
                        "exit_date": date,
                        "score": position["score"],
                        "signal": position["signal"],
                        "entry_price": round(entry_price, 4),
                        "exit_price": round(exit_price, 4),
                        "target_pct": target_pct * 100,
                        "result_pct": round(result_pct, 4),
                        "days_held": days_held,
                        "exit_reason": exit_reason,
                    })

                    del open_positions[ticker]

                    continue

            if ticker in open_positions:
                continue

            stock_prices = (
                price_history[ticker]["close"][:i + 1]
            )

            result = calculate_score(
                stock_prices,
                benchmark_prices
            )

            if result is None:
                continue

            if result["score"] < min_score:
                continue

            entry_price = (
                price_history[ticker]["open"][i + 1]
            )

            open_positions[ticker] = {
                "signal_date": date,
                "entry_date": next_date,
                "entry_index": i + 1,
                "entry_price": entry_price,
                "score": result["score"],
                "signal": result["signal"],
            }

    return trades


trades_70_15 = rerun_with_target(70, TARGET_15)
trades_85_15 = rerun_with_target(85, TARGET_15)


# ------------------------------------------------------------
# Resultat
# ------------------------------------------------------------

results = {
    "model": "OMX Swing Scanner v1.3",
    "data_period": {
        "from": dates[0],
        "to": dates[-1],
        "trading_days": len(dates),
    },
    "settings": {
        "stop_loss": -8,
        "target_10": 10,
        "target_15": 15,
        "max_holding_days": MAX_HOLDING_DAYS,
        "entry": "next_day_open",
    },
    "scenarios": {
        "BEVAKA_KOP_target_10": {
            "summary": summarize(trades_70),
            "trades": trades_70,
        },
        "KOP_target_10": {
            "summary": summarize(trades_85),
            "trades": trades_85,
        },
        "BEVAKA_KOP_target_15": {
            "summary": summarize(trades_70_15),
            "trades": trades_70_15,
        },
        "KOP_target_15": {
            "summary": summarize(trades_85_15),
            "trades": trades_85_15,
        },
    },
}


RESULT_FILE.write_text(
    json.dumps(
        results,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# ------------------------------------------------------------
# Visa sammanfattning i Actions-loggen
# ------------------------------------------------------------

print()
print("========================================")
print("RESULTAT")
print("========================================")


for name, scenario in results["scenarios"].items():

    s = scenario["summary"]

    print()
    print(name)
    print("------------------------------")
    print("Trades:", s["trades"])
    print("Vinnare:", s["wins"])
    print("Förlorare:", s["losses"])
    print("Stop:", s["stops"])
    print("Target:", s["targets"])
    print("Max tid:", s["max_holding"])
    print("Träffprocent:", s["hit_rate"], "%")
    print("Snitt/trade:", s["average_result"], "%")
    print("Summa:", s["total_result"], "%")
    print("Snitt vinst:", s["average_win"], "%")
    print("Snitt förlust:", s["average_loss"], "%")
    print("Snitt dagar:", s["average_days"])


print()
print("========================================")
print("Backtest klart.")
print("Resultat sparat i:", RESULT_FILE)
print("========================================")
