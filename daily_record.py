# -*- coding: utf-8 -*-
"""
매일 자동 실행용 — 게이트 판정을 계산해서 구글시트에 저장한다.
Streamlit 없이 혼자 돈다. GitHub Actions가 매일 이 파일을 실행.
웹훅 URL은 환경변수 SHEET_WEBHOOK 에서 읽음 (코드에 노출 안 함).
"""
import os
import datetime as dt
import pandas as pd
import yfinance as yf
import requests


def fetch(ticker, interval, period):
    df = yf.download(ticker, interval=interval, period=period,
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)
    return df


def add_ma(df, spans=(20, 60, 120)):
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame()
    for s in spans:
        df[f"MA{s}"] = df["Close"].rolling(s).mean()
    return df


def above_ma120(df, want_above):
    """종가가 MA120 위/아래 판정. want_above=True면 '위'가 좋음."""
    if df.empty or df["MA120"].dropna().empty:
        return None
    close = float(df["Close"].iloc[-1])
    ma = float(df["MA120"].iloc[-1])
    return (close > ma) == want_above


def is_aligned(df):
    if df.empty or df[["MA20", "MA60", "MA120"]].dropna().empty:
        return None
    r = df.dropna(subset=["MA20", "MA60", "MA120"]).iloc[-1]
    return bool(r["MA20"] > r["MA60"] > r["MA120"])


def main():
    url = os.environ.get("SHEET_WEBHOOK", "")
    if not url:
        print("❌ SHEET_WEBHOOK 환경변수 없음"); return

    # 데이터 수집 (대시보드와 동일)
    inv30 = add_ma(fetch("114800.KS", "30m", "60d"))
    nq60 = add_ma(fetch("NQ=F", "60m", "60d"))
    nq5 = fetch("NQ=F", "5m", "5d")
    nq20 = pd.DataFrame()
    if not nq5.empty:
        nq20 = nq5.resample("20min").agg({"Open": "first", "High": "max",
                                          "Low": "min", "Close": "last"}).dropna()
        nq20 = add_ma(nq20)
    sox = add_ma(fetch("^SOX", "30m", "60d"))
    if sox.empty:
        sox = add_ma(fetch("^SOX", "1d", "1y"))

    # 삼성 그날 등락 (일봉 마지막 봉)
    sam = fetch("005930.KS", "1d", "5d")
    sam_chg = ""
    if not sam.empty and len(sam) >= 2:
        c = float(sam["Close"].iloc[-1]); p = float(sam["Close"].iloc[-2])
        sam_chg = round((c - p) / p, 4)   # 소수로 저장 (0.0387 = +3.87%). 시트 서식=퍼센트

    # 판정
    inv_ok = above_ma120(inv30, want_above=False)   # 인버스는 아래가 좋음
    nq_ok = above_ma120(nq60, want_above=True)
    sox_ok = above_ma120(sox, want_above=True)
    n20_ok = is_aligned(nq20)

    base3 = bool(sox_ok and inv_ok and nq_ok)
    sgrade = bool(base3 and n20_ok)
    grade = "🔵 S급" if sgrade else ("🟢 A급" if base3 else "🔴 관망")

    def g(x):
        return "🟢" if x else "🔴"

    payload = {
        "날짜": dt.datetime.now().strftime("%m-%d"),
        "판정": grade,
        "SOX": g(sox_ok),
        "인버스": g(inv_ok),
        "나닥60": g(nq_ok),
        "나닥20": g(n20_ok),
        "삼성등락": sam_chg,
    }
    print("전송:", payload)
    r = requests.post(url, json=payload, timeout=15)
    print("응답:", r.status_code, r.text[:200])
    if '"ok":true' in r.text.replace(" ", ""):
        print("✅ 시트 저장 완료")
    else:
        print("⚠️ 저장 실패 — 응답 확인")


if __name__ == "__main__":
    main()
