# -*- coding: utf-8 -*-
"""
A전략 시장판단 대시보드
- KODEX 인버스 30분봉 120이평 위치 (아래 = 지수 상승추세 = 좋음)
- 나스닥선물 60분봉 120이평 위치 (위 = 좋음)
- 나스닥선물 20분봉 정배열 (20>60>120)
- SOX(필라델피아 반도체) 흐름
데이터: yfinance (인터넷에서 직접 수집 → 클라우드에 올리면 내 PC 꺼도 작동)
"""
import datetime as dt
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="A전략 시장판단", layout="wide", page_icon="📊")

# ---------------------------------------------------------------------------
# 데이터 유틸
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)  # 5분 캐시 (야후 요청 과다 방지)
def fetch(ticker: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(ticker, interval=interval, period=period,
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    # yfinance가 종종 멀티인덱스 컬럼을 주므로 평탄화
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)  # Open High Low Close Volume
    return df

def add_ma(df: pd.DataFrame, spans=(20, 60, 120)) -> pd.DataFrame:
    # 데이터가 비었거나 Close 컬럼이 없으면 그대로 반환 (KeyError 방지)
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame()
    for s in spans:
        df[f"MA{s}"] = df["Close"].rolling(s).mean()
    return df

def last_session(df: pd.DataFrame) -> pd.DataFrame:
    """가장 최근 거래일(하루)만 잘라서 반환 — MA는 이미 전체로 계산돼 있음"""
    if df.empty:
        return df
    last_day = df.index[-1].date()
    return df[df.index.date == last_day]

def candle_chart(df_full: pd.DataFrame, title: str, baseline="MA120") -> go.Figure:
    df = last_session(df_full)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        increasing_line_color="#f0464b", decreasing_line_color="#4b8ef0",  # 한국식 빨강↑ 파랑↓
        name="price", showlegend=False))
    colors = {"MA20": "#f2c14e", "MA60": "#4caf7d", "MA120": "#9aa4b2"}
    for ma, c in colors.items():
        if ma in df:
            fig.add_trace(go.Scatter(x=df.index, y=df[ma], line=dict(color=c, width=1.6),
                                     name=ma))
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        template="plotly_dark", height=340, margin=dict(l=10, r=10, t=38, b=10),
        xaxis_rangeslider_visible=False, paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10)))
    return fig

def status(df: pd.DataFrame, want_above: bool):
    """종가가 MA120 위/아래인지 판정. want_above=True면 '위'가 좋음(🟢)"""
    if df.empty or df["MA120"].dropna().empty:
        return None, "데이터 없음"
    close = float(df["Close"].iloc[-1]); ma = float(df["MA120"].iloc[-1])
    above = close > ma
    good = (above == want_above)
    pos = "기준선 위" if above else "기준선 아래"
    gap = (close - ma) / ma * 100
    return good, f"{pos} ({gap:+.2f}%)"

def is_aligned(df: pd.DataFrame):
    """정배열 20>60>120 여부"""
    if df.empty or df[["MA20", "MA60", "MA120"]].dropna().empty:
        return None
    r = df.dropna(subset=["MA20", "MA60", "MA120"]).iloc[-1]
    return bool(r["MA20"] > r["MA60"] > r["MA120"])

# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------
st.markdown("### 📊 A전략 시장판단  ·  30분봉 120이평 게이트")
now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
c1, c2 = st.columns([3, 1])
c1.caption("KODEX 인버스 · 나스닥선물 · 필라델피아 반도체(SOX) — 데이터 5분 캐시")
if c2.button("🔄 새로고침"):
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------------------------
# 데이터 수집
# ---------------------------------------------------------------------------
with st.spinner("데이터 불러오는 중..."):
    # 인버스: 국내 ETF (야후 분봉이 불안정하면 아래 period/interval 조정)
    inv30 = add_ma(fetch("114800.KS", "30m", "60d"))
    # 나스닥선물: 60분봉 + 20분봉(정배열용). 야후는 20m 미지원 → 5m 받아 20m 리샘플
    nq60 = add_ma(fetch("NQ=F", "60m", "60d"))
    nq5 = fetch("NQ=F", "5m", "5d")
    nq20 = pd.DataFrame()
    if not nq5.empty:
        nq20 = nq5.resample("20min").agg({"Open": "first", "High": "max",
                                          "Low": "min", "Close": "last"}).dropna()
        nq20 = add_ma(nq20)
    # SOX: 30분봉 (안 되면 일봉 폴백) — 차트용
    sox = add_ma(fetch("^SOX", "30m", "60d"))
    if sox.empty:
        sox = add_ma(fetch("^SOX", "1d", "1y"))
    # SOX 일봉 — 장전 판정용 (120일선 위/아래 + 전일대비 방향)
    sox_d = add_ma(fetch("^SOX", "1d", "2y"))

# ---------------------------------------------------------------------------
# 신호등 판정
# ---------------------------------------------------------------------------
inv_good, inv_txt = status(inv30, want_above=False)   # 인버스는 '아래'가 좋음
nq_good, nq_txt = status(nq60, want_above=True)        # 나스닥은 '위'가 좋음
nq20_aligned = is_aligned(nq20)

# SOX 장전 판정 (실시간 아님 = 간밤 마감 기준)
sox_good, sox_txt = status(sox_d, want_above=True)     # SOX 120일선 위면 반도체 우호
sox_dir = None
if not sox_d.empty and len(sox_d) >= 2:
    c = float(sox_d["Close"].iloc[-1]); p = float(sox_d["Close"].iloc[-2])
    sox_dir = (c - p) / p * 100

gate_ok = all(x is True for x in [inv_good, nq_good, nq20_aligned])

def light(good):
    return "🟢" if good is True else ("🔴" if good is False else "⚪")

# 장전 참고 (SOX) — 오늘 반도체가 우호적인가. 장중 게이트와 별개
st.markdown("#### 🌙 장전 참고 — 필라델피아 반도체(SOX)")
s1, s2 = st.columns([1, 3])
if sox_dir is not None:
    dir_txt = f"간밤 {'상승' if sox_dir >= 0 else '하락'} ({sox_dir:+.2f}%)"
else:
    dir_txt = "방향 데이터 없음"
s1.metric(f"SOX 120일선 {light(sox_good)}", sox_txt, dir_txt)
if sox_good is True and (sox_dir or 0) >= 0:
    s2.info("간밤 SOX 우호적 — 오늘 반도체 대형주 갭업·강세 가능성. 관심 켜기.")
elif sox_good is False or (sox_dir is not None and sox_dir < 0):
    s2.warning("간밤 SOX 약함 — 반도체 갭다운/약세 주의. 무리한 진입 자제.")
else:
    s2.caption("SOX는 미국 마감(한국 새벽) 후 값이 고정됩니다. 장중엔 안 변해요 — 장전 판단용.")

st.markdown("#### ☀️ 장중 게이트 — A급 (진입 여부 결정)")
g1, g2, g3, g4 = st.columns(4)
g1.metric("① 인버스 30분", f"{light(inv_good)}", inv_txt)
g2.metric("② 나스닥선물 60분", f"{light(nq_good)}", nq_txt)
g3.metric("③ 나스닥 20분 정배열",
          light(nq20_aligned),
          "정배열 O" if nq20_aligned else ("정배열 X" if nq20_aligned is False else "데이터 없음"))
verdict = "🟢 A급 — 진입 가능" if gate_ok else "🔴 관망 / 금지"
g4.metric("종합 판정", verdict)

if gate_ok:
    st.success("세 조건 모두 충족 — A급. (종목 조건: 기준선 위 + 10분 정배열 + 수급 별도 확인)")
else:
    st.warning("하나 이상 불충족 — 관망. 인버스가 기준선 위면 매매금지.")

st.divider()

# ---------------------------------------------------------------------------
# 차트 (당일)
# ---------------------------------------------------------------------------
col_a, col_b = st.columns(2)
with col_a:
    if not inv30.empty:
        st.plotly_chart(candle_chart(inv30, "KODEX 인버스 · 30분봉"), use_container_width=True)
    else:
        st.info("인버스 분봉 데이터를 못 불러왔습니다. (야후 국내 ETF 분봉 제한 — MTS로 보조 확인)")
with col_b:
    if not nq60.empty:
        st.plotly_chart(candle_chart(nq60, "나스닥선물(NQ) · 60분봉"), use_container_width=True)

col_c, col_d = st.columns(2)
with col_c:
    if not sox.empty:
        st.plotly_chart(candle_chart(sox, "필라델피아 반도체(SOX)"), use_container_width=True)
with col_d:
    if not nq20.empty:
        st.plotly_chart(candle_chart(nq20, "나스닥선물(NQ) · 20분봉 (정배열 확인)"),
                        use_container_width=True)

st.caption(f"업데이트: {now}  ·  빨강=상승 파랑=하락(한국식)  ·  노랑=20 초록=60 회색=120이평")
