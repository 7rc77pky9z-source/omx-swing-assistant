import json
from pathlib import Path
from datetime import datetime, timezone

import yfinance as yf


# ============================================================
# OMX SWING SCANNER - BACKTEST DATA
# Hämtar 5 års dagsdata för de 24 aktierna + OMXS30.
#
# OBS:
# Denna fil ändrar INTE data/stocks.json.
# Den skapar endast:
#     data/backtest_data.json
# ============================================================


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
    "^OMXS30",
]


result = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "source": "Yahoo Finance via yfinance",
    "period": "5y",
    "interval": "1d",
    "stocks": {}
}


for ticker in TICKERS:

    print("Hämtar", ticker)

    try:

        # Yahoo Finance använder ^OMX för OMX Stockholm 30.
        yahoo_ticker = "^OMX" if ticker == "^OMXS30" else ticker

        df = yf.download(
            yahoo_ticker,
            period="5y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
            actions=False,
        )

        if df.empty:
            print("  INGEN DATA")
            continue

        # yfinance kan returnera MultiIndex-kolumner även
        # när endast en ticker hämtas.
        def get_column(name):
            column = df[name]

            if hasattr(column, "columns"):
                column = column.iloc[:, 0]

            return column

        open_prices = get_column("Open")
        high_prices = get_column("High")
        low_prices = get_column("Low")
        close_prices = get_column("Close")

        rows = []

        for date in df.index:

            try:
                o = float(open_prices.loc[date])
                h = float(high_prices.loc[date])
                l = float(low_prices.loc[date])
                c = float(close_prices.loc[date])
            except Exception:
                continue

            # Hoppa över rader med saknade värden.
            if not all(
                value == value
                for value in [o, h, l, c]
            ):
                continue

            rows.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(o, 6),
                "high": round(h, 6),
                "low": round(l, 6),
                "close": round(c, 6),
            })

        if len(rows) >= 200:

            result["stocks"][ticker] = rows

            print(
                "  OK",
                len(rows),
                "dagar",
                rows[0]["date"],
                "->",
                rows[-1]["date"]
            )

        else:

            print(
                "  FÖR FÅ DAGAR",
                len(rows)
            )

    except Exception as e:

        print(
            "  FEL",
            e
        )


# ============================================================
# Spara separat backtest-data
# ============================================================

Path("data").mkdir(exist_ok=True)

output_file = Path("data/backtest_data.json")

output_file.write_text(
    json.dumps(
        result,
        ensure_ascii=False,
        separators=(",", ":")
    ),
    encoding="utf-8"
)


print()
print("========================================")
print("BACKTEST-DATA KLAR")
print("========================================")
print("Instrument:", len(result["stocks"]))
print("Fil:", output_file)
print("========================================")
