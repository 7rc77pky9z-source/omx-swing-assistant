import json
import math
from pathlib import Path

import pandas as pd


DATA_FILE = Path("data/backtest_data.json")
OUTPUT_FILE = Path("data/ranked_backtest_results.json")

STOP_LOSS = 0.08
TARGETS = [0.10, 0.15]
MAX_HOLD_DAYS = 20

MIN_SCORE = 70

# Exakt samma tickers som i nuvarande scanner
TICKERS = [
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


def clean_number(value):
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except Exception:
        return None


def prepare_dataframe(raw):
    df = pd.DataFrame(raw)

    if df.empty:
        return df

    # Försök hitta datumkolumn
    date_column = None

    for col in ["Date", "date", "Datetime", "datetime"]:
        if col in df.columns:
            date_column = col
            break

    if date_column is None:
        # Om datum ligger som indexliknande fält
        if "index" in df.columns:
            date_column = "index"
        else:
            raise ValueError("Hittar ingen datumkolumn.")

    df["Date"] = pd.to_datetime(df[date_column])
    df = df.sort_values("Date").reset_index(drop=True)

    # Normalisera kolumnnamn
    rename = {}

    for col in df.columns:
        low = str(col).lower()

        if low == "open":
            rename[col] = "Open"
        elif low == "high":
            rename[col] = "High"
        elif low == "low":
            rename[col] = "Low"
        elif low == "close":
            rename[col] = "Close"

    df = df.rename(columns=rename)

    required = ["Open", "High", "Low", "Close"]

    for col in required:
        if col not in df.columns:
            raise ValueError(f"Saknar kolumnen {col}.")

    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    return df


def calculate_rsi(close, period=14):
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_score(stock_df, benchmark_df, index):
    """
    Exakt v1.3-logik:

    Trend 35
      price > MA200 = +25
      MA50 > MA200 = +10

    RSI 15
      RSI < 35 = +15
      RSI < 45 = +8

    Relative strength 25
      >= +10% = +25
      >= +5%  = +15
      >= 0%   = +8

    Momentum 10
      price > MA50 = +10

    Pullback 10
      5-15% = +10
      >=3%  = +6

    Max 95
    """

    if index < 200:
        return None

    row = stock_df.iloc[index]

    close = row["Close"]

    if pd.isna(close):
        return None

    ma50 = stock_df["Close"].rolling(50).mean().iloc[index]
    ma200 = stock_df["Close"].rolling(200).mean().iloc[index]

    rsi_series = calculate_rsi(stock_df["Close"])
    rsi = rsi_series.iloc[index]

    if pd.isna(ma50) or pd.isna(ma200) or pd.isna(rsi):
        return None

    score = 0

    # -------------------------
    # Trend 35
    # -------------------------

    if close > ma200:
        score += 25

    if ma50 > ma200:
        score += 10

    # -------------------------
    # RSI 15
    # -------------------------

    if rsi < 35:
        score += 15
    elif rsi < 45:
        score += 8

    # -------------------------
    # Relative strength 25
    # -------------------------

    rs_score = 0
    relative_strength = None

    stock_date = stock_df.iloc[index]["Date"]

    # Cirka 6 månader / 127 handelsdagar
    lookback = 127

    if index >= lookback:
        old_stock = stock_df["Close"].iloc[index - lookback]

        # Hitta benchmark på samma datum
        benchmark_matches = benchmark_df[
            benchmark_df["Date"] <= stock_date
        ]

        if not benchmark_matches.empty:
            benchmark_index = benchmark_matches.index[-1]

            # Hitta benchmarkvärdet cirka 127 handelsdagar bakåt
            benchmark_position = benchmark_df.index.get_loc(
                benchmark_index
            )

            if benchmark_position >= lookback:
                old_benchmark = benchmark_df["Close"].iloc[
                    benchmark_position - lookback
                ]

                current_benchmark = benchmark_df["Close"].iloc[
                    benchmark_position
                ]

                if (
                    old_stock
                    and old_benchmark
                    and old_stock > 0
                    and old_benchmark > 0
                ):
                    stock_return = close / old_stock - 1
                    benchmark_return = (
                        current_benchmark / old_benchmark - 1
                    )

                    relative_strength = (
                        stock_return - benchmark_return
                    ) * 100

                    if relative_strength >= 10:
                        rs_score = 25
                    elif relative_strength >= 5:
                        rs_score = 15
                    elif relative_strength >= 0:
                        rs_score = 8

    score += rs_score

    # -------------------------
    # Momentum 10
    # -------------------------

    if close > ma50:
        score += 10

    # -------------------------
    # Pullback 10
    # -------------------------

    high_20 = stock_df["Close"].rolling(20).max().iloc[index]

    pullback = 0

    if high_20 and high_20 > 0:
        pullback = (high_20 - close) / high_20 * 100

    # Viktigt:
    # Detta är samma logik som v1.3,
    # inklusive att >15% också får +6.
    if pullback >= 5 and pullback <= 15:
        score += 10
    elif pullback >= 3:
        score += 6

    return {
        "score": score,
        "rsi": rsi,
        "relative_strength": relative_strength,
        "pullback": pullback,
        "ma50": ma50,
        "ma200": ma200,
    }


def simulate_trade(stock_df, signal_index, target):
    """
    Signal vid dagens stängning.
    Köp nästa handelsdags öppning.

    Stop:
      -8 %

    Target:
      +10 eller +15 %

    Max holding:
      20 handelsdagar

    Om både stop och target träffas samma dag:
      STOP först (konservativt).
    """

    entry_index = signal_index + 1

    if entry_index >= len(stock_df):
        return None

    entry_price = stock_df.iloc[entry_index]["Open"]

    if pd.isna(entry_price) or entry_price <= 0:
        return None

    stop_price = entry_price * (1 - STOP_LOSS)
    target_price = entry_price * (1 + target)

    last_index = min(
        entry_index + MAX_HOLD_DAYS,
        len(stock_df) - 1,
    )

    for i in range(entry_index, last_index + 1):

        row = stock_df.iloc[i]

        low = row["Low"]
        high = row["High"]

        # Stop först om båda nås samma dag
        if low <= stop_price:
            result = -STOP_LOSS * 100

            return {
                "entry_index": entry_index,
                "exit_index": i,
                "entry_price": entry_price,
                "exit_price": stop_price,
                "return_pct": result,
                "exit_reason": "STOP",
                "holding_days": i - entry_index + 1,
            }

        if high >= target_price:
            result = target * 100

            return {
                "entry_index": entry_index,
                "exit_index": i,
                "entry_price": entry_price,
                "exit_price": target_price,
                "return_pct": result,
                "exit_reason": "TARGET",
                "holding_days": i - entry_index + 1,
            }

    # Om varken stop eller target nås:
    # stäng på close efter max 20 dagar
    exit_price = stock_df.iloc[last_index]["Close"]

    result = (exit_price / entry_price - 1) * 100

    return {
        "entry_index": entry_index,
        "exit_index": last_index,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "return_pct": result,
        "exit_reason": "MAX_HOLD",
        "holding_days": last_index - entry_index + 1,
    }


def load_data():
    print(f"Läser {DATA_FILE}...")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return raw


def normalize_data(raw):
    """
    Hanterar den normala strukturen:

    {
      "ABB.ST": [...],
      "VOLV-B.ST": [...],
      "^OMXS30": [...]
    }

    samt om data ligger under exempelvis:
    {
      "stocks": {...}
    }
    """

    if isinstance(raw, dict):

        if "stocks" in raw and isinstance(raw["stocks"], dict):
            raw = raw["stocks"]

        elif "data" in raw and isinstance(raw["data"], dict):
            raw = raw["data"]

    if not isinstance(raw, dict):
        raise ValueError("Okänd struktur i backtest_data.json.")

    result = {}

    for ticker in TICKERS + [BENCHMARK]:

        if ticker not in raw:
            print(f"VARNING: {ticker} saknas i data.")
            continue

        try:
            result[ticker] = prepare_dataframe(raw[ticker])
        except Exception as e:
            print(f"Fel vid läsning av {ticker}: {e}")

    return result


def build_daily_candidates(data):
    benchmark_df = data.get(BENCHMARK)

    if benchmark_df is None or benchmark_df.empty:
        raise ValueError("Benchmark ^OMXS30 saknas.")

    candidates_by_date = {}

    for ticker in TICKERS:

        stock_df = data.get(ticker)

        if stock_df is None or stock_df.empty:
            continue

        for index in range(len(stock_df)):

            date = stock_df.iloc[index]["Date"]

            score_data = calculate_score(
                stock_df,
                benchmark_df,
                index,
            )

            if score_data is None:
                continue

            score = score_data["score"]

            if score < MIN_SCORE:
                continue

            candidate = {
                "ticker": ticker,
                "signal_index": index,
                "date": str(date.date()),
                **score_data,
            }

            candidates_by_date.setdefault(
                str(date.date()),
                []
            ).append(candidate)

    # Rangordning:
    #
    # 1. Högst score
    # 2. Högst relativ styrka
    # 3. Störst pullback
    # 4. Ticker som tie-breaker
    #
    # Detta gör rankningen helt deterministisk.

    for date in candidates_by_date:

        candidates_by_date[date].sort(
            key=lambda x: (
                -x["score"],
                -(x["relative_strength"]
                  if x["relative_strength"] is not None
                  else -999),
                -x["pullback"],
                x["ticker"],
            )
        )

    return candidates_by_date


def run_ranked_backtest(
    candidates_by_date,
    data,
    number_of_positions,
    target,
):
    """
    Varje handelsdag väljs de N högst rankade kandidaterna.

    Viktigt:
    En aktie kan inte ha en ny position om den redan har
    en öppen position.
    """

    all_candidates = []

    for date, candidates in candidates_by_date.items():

        for candidate in candidates:
            all_candidates.append(candidate)

    all_candidates.sort(
        key=lambda x: x["date"]
    )

    open_positions = {}
    trades = []

    for candidate in all_candidates:

        ticker = candidate["ticker"]

        stock_df = data.get(ticker)

        if stock_df is None:
            continue

        signal_index = candidate["signal_index"]

        # Rensa avslutade positioner
        if ticker in open_positions:
            existing = open_positions[ticker]

            if signal_index > existing["exit_index"]:
                del open_positions[ticker]
            else:
                continue

        # Antal positioner som redan öppnats från samma signal-dag
        date = candidate["date"]

        same_day_candidates = [
            x
            for x in candidates_by_date.get(date, [])
        ]

        # Top N för just den dagen
        ranked_today = same_day_candidates[:number_of_positions]

        tickers_today = {
            x["ticker"]
            for x in ranked_today
        }

        if ticker not in tickers_today:
            continue

        trade = simulate_trade(
            stock_df,
            signal_index,
            target,
        )

        if trade is None:
            continue

        trade_record = {
            "date": candidate["date"],
            "ticker": ticker,
            "score": candidate["score"],
            "rsi": candidate["rsi"],
            "relative_strength": candidate["relative_strength"],
            "pullback": candidate["pullback"],
            "target_pct": target * 100,
            **trade,
        }

        trades.append(trade_record)

        open_positions[ticker] = {
            "exit_index": trade["exit_index"]
        }

    return trades


def summarize(trades):

    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "hit_rate_pct": 0,
            "stops": 0,
            "targets": 0,
            "max_holding": 0,
            "average_result_pct": 0,
            "total_result_pct": 0,
            "average_win_pct": 0,
            "average_loss_pct": 0,
            "average_days": 0,
        }

    results = [
        float(t["return_pct"])
        for t in trades
    ]

    wins = [
        r for r in results
        if r > 0
    ]

    losses = [
        r for r in results
        if r <= 0
    ]

    stops = sum(
        1
        for t in trades
        if t["exit_reason"] == "STOP"
    )

    targets = sum(
        1
        for t in trades
        if t["exit_reason"] == "TARGET"
    )

    max_hold = sum(
        1
        for t in trades
        if t["exit_reason"] == "MAX_HOLD"
    )

    days = [
        t["holding_days"]
        for t in trades
    ]

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "hit_rate_pct": (
            len(wins) / len(trades) * 100
        ),
        "stops": stops,
        "targets": targets,
        "max_holding": max_hold,
        "average_result_pct": (
            sum(results) / len(results)
        ),
        "total_result_pct": sum(results),
        "average_win_pct": (
            sum(wins) / len(wins)
            if wins else 0
        ),
        "average_loss_pct": (
            sum(losses) / len(losses)
            if losses else 0
        ),
        "average_days": (
            sum(days) / len(days)
        ),
    }


def main():

    print("")
    print("======================================")
    print(" OMX RANKED BACKTEST")
    print(" v1.3 score – TOP 1 / TOP 2")
    print("======================================")
    print("")

    raw = load_data()
    data = normalize_data(raw)

    print("")
    print("Bygger dagliga kandidater...")
    candidates_by_date = build_daily_candidates(data)

    number_of_candidate_days = len(
        candidates_by_date
    )

    print(
        f"Antal dagar med minst en "
        f"BEVAKA/KÖP-kandidat: "
        f"{number_of_candidate_days}"
    )

    results = {
        "settings": {
            "model": "v1.3",
            "min_score": MIN_SCORE,
            "stop_loss_pct": STOP_LOSS * 100,
            "max_hold_days": MAX_HOLD_DAYS,
            "entry": "next_day_open",
            "same_day_stop_first": True,
            "ranking": [
                "score_desc",
                "relative_strength_desc",
                "pullback_desc",
                "ticker_asc",
            ],
            "note": (
                "Top 1/Top 2 simulation. "
                "No commissions or slippage. "
                "Current 24-stock universe."
            ),
        },
        "scenarios": {},
        "daily_rankings": {},
    }

    # Spara även ranking dag för dag.
    # Det gör att vi senare kan se exakt vilka aktier
    # som valdes.

    for date, candidates in candidates_by_date.items():

        results["daily_rankings"][date] = [
            {
                "rank": rank + 1,
                "ticker": candidate["ticker"],
                "score": candidate["score"],
                "rsi": round(
                    candidate["rsi"], 2
                ),
                "relative_strength": (
                    round(
                        candidate["relative_strength"],
                        2,
                    )
                    if candidate["relative_strength"]
                    is not None
                    else None
                ),
                "pullback": round(
                    candidate["pullback"],
                    2,
                ),
            }
            for rank, candidate
            in enumerate(candidates)
        ]

    for number_of_positions in [1, 2]:

        for target in TARGETS:

            key = (
                f"top{number_of_positions}"
                f"_target{int(target * 100)}"
            )

            print("")
            print(
                f"Kör scenario: {key}"
            )

            trades = run_ranked_backtest(
                candidates_by_date,
                data,
                number_of_positions,
                target,
            )

            summary = summarize(trades)

            results["scenarios"][key] = {
                "settings": {
                    "positions": number_of_positions,
                    "target_pct": target * 100,
                },
                "summary": summary,
                "trades": trades,
            }

            print(
                f"  Trades: "
                f"{summary['trades']}"
            )

            print(
                f"  Träffprocent: "
                f"{summary['hit_rate_pct']:.2f}%"
            )

            print(
                f"  Snitt: "
                f"{summary['average_result_pct']:.3f}%"
            )

            print(
                f"  Total: "
                f"{summary['total_result_pct']:.3f}%"
            )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            results,
            f,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    print("")
    print("======================================")
    print("KLART")
    print(f"Resultat sparat i:")
    print(f"{OUTPUT_FILE}")
    print("======================================")
    print("")


if __name__ == "__main__":
    main()
