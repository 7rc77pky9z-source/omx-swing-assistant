import json
from pathlib import Path
from datetime import datetime, timezone
import yfinance as yf

TICKERS=["ABB.ST","ALFA.ST","ASSA-B.ST","ATCO-A.ST","AZN.ST","BOL.ST","ELUX-B.ST","ERIC-B.ST","EVO.ST","HEXA-B.ST","HM-B.ST","INVE-B.ST","KINV-B.ST","NDA-SE.ST","SAND.ST","SCA-B.ST","SEB-A.ST","SHB-A.ST","SINCH.ST","SKF-B.ST","SWED-A.ST","TEL2-B.ST","TELIA.ST","VOLV-B.ST","^OMXS30"]
result={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"source":"Yahoo Finance via yfinance","stocks":{}}

for ticker in TICKERS:
    print("Hämtar",ticker)
    try:
        df=yf.download(ticker,period="1y",interval="1d",auto_adjust=False,progress=False,threads=False)
        if df.empty: print("  INGEN DATA"); continue
        close=df["Close"]
        if hasattr(close,"columns"): close=close.iloc[:,0]
        rows=[{"date":d.strftime("%Y-%m-%d"),"close":round(float(v),6)} for d,v in close.dropna().items()]
        if len(rows)>=200:
            result["stocks"][ticker]=rows
            print("  OK",len(rows),"dagar")
        else: print("  FÖR FÅ DAGAR",len(rows))
    except Exception as e: print("  FEL",e)

Path("data").mkdir(exist_ok=True)
Path("data/stocks.json").write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
print("Klart:",len(result["stocks"]),"instrument")
