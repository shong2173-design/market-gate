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

# 모바일에서 첫 화면에 요약이 바로 보이도록 상단 여백 축소
st.markdown("""<style>
  .block-container{padding-top:1.2rem !important;padding-bottom:1rem !important}
  [data-testid="stMetricValue"]{font-size:1.4rem}
</style>""", unsafe_allow_html=True)

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
st.markdown("#### 📊 A전략 시장판단 · 30분봉 120이평 게이트")
now = dt.datetime.now().strftime("%m-%d %H:%M")
c1, c2 = st.columns([3, 1])
c1.caption(f"인버스·나스닥선물·SOX · {now} · 5분 캐시")
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

# SOX 장전 판정 (님 차트와 동일하게 30분봉 120이평 기준)
sox_good, sox_txt = status(sox, want_above=True)      # SOX 30분봉 120이평 위면 반도체 우호
sox_dir = None
if not sox_d.empty and len(sox_d) >= 2:
    c = float(sox_d["Close"].iloc[-1]); p = float(sox_d["Close"].iloc[-2])
    sox_dir = (c - p) / p * 100

gate_ok = all(x is True for x in [inv_good, nq_good, nq20_aligned])

def light(good):
    return "🟢" if good is True else ("🔴" if good is False else "⚪")

# ===== 최상단 컴팩트 요약: 5개 신호등 한눈에 (폰 첫 화면) =====
def chip(label, good, sub):
    c = "#4caf7d" if good is True else ("#f0464b" if good is False else "#8b98a9")
    dot = "#3ddc84" if good is True else ("#f0464b" if good is False else "#8b98a9")
    return f"""<div style="flex:1;min-width:0;background:#141a22;border:1px solid #28313d;
      border-top:3px solid {c};border-radius:10px;padding:9px 6px;text-align:center">
      <div style="font-size:11px;color:#8b98a9;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{label}</div>
      <div style="width:16px;height:16px;border-radius:50%;background:{dot};margin:6px auto 4px"></div>
      <div style="font-size:10px;color:#cdd7e2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{sub}</div>
    </div>"""

verdict_ok = gate_ok
vcol = "#4caf7d" if verdict_ok else "#f0464b"
vtxt = "🟢 A급 진입가능" if verdict_ok else "🔴 관망 / 금지"

sox_sub = sox_txt.split("(")[0].strip() if sox_txt else "—"
inv_sub = inv_txt.split("(")[0].strip() if inv_txt else "—"
nq_sub = nq_txt.split("(")[0].strip() if nq_txt else "—"
nq20_sub = "정배열 O" if nq20_aligned else ("정배열 X" if nq20_aligned is False else "—")

st.markdown(f"""
<div style="background:{vcol}22;border:1px solid {vcol};border-radius:12px;padding:10px 14px;margin-bottom:10px;text-align:center">
  <span style="font-size:19px;font-weight:800;color:{vcol}">{vtxt}</span>
</div>
<div style="display:flex;gap:6px;margin-bottom:6px">
  {chip("장전 SOX", sox_good, sox_sub)}
  {chip("①인버스30", inv_good, inv_sub)}
  {chip("②나스닥60", nq_good, nq_sub)}
  {chip("③나스닥20", nq20_aligned, nq20_sub)}
</div>
<div style="font-size:10.5px;color:#5d6b7d;text-align:center;margin-bottom:14px">
  장중 게이트 ①②③ 모두 🟢 = A급 · 장전 SOX는 참고
</div>
""", unsafe_allow_html=True)

# ===== 상세 =====
# 장전 참고 (SOX)
st.markdown("#### 🌙 장전 참고 — 필라델피아 반도체(SOX)")
s1, s2 = st.columns([1, 3])
if sox_dir is not None:
    dir_txt = f"간밤 {'상승' if sox_dir >= 0 else '하락'} ({sox_dir:+.2f}%)"
else:
    dir_txt = "방향 데이터 없음"
s1.metric(f"SOX 30분 120이평 {light(sox_good)}", sox_txt, dir_txt)
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

# ---------------------------------------------------------------------------
# 날짜별 A급/관망 히스토리 (한 달 복기)
# ---------------------------------------------------------------------------
st.divider()
st.markdown("#### 🗓️ 날짜별 게이트 히스토리 (한 달 복기)")

@st.cache_data(ttl=1800)
def build_history():
    # 지표별 과거 봉 (MA는 전체로 계산)
    h_inv = add_ma(fetch("114800.KS", "30m", "40d"))
    h_nq60 = add_ma(fetch("NQ=F", "60m", "40d"))
    h_sox = add_ma(fetch("^SOX", "30m", "40d"))
    h_nq5 = fetch("NQ=F", "5m", "40d")
    h_nq20 = pd.DataFrame()
    if not h_nq5.empty:
        h_nq20 = h_nq5.resample("20min").agg({"Open": "first", "High": "max",
                                              "Low": "min", "Close": "last"}).dropna()
        h_nq20 = add_ma(h_nq20)
    # 삼성전자 일봉 등락률
    sam = fetch("005930.KS", "1d", "3mo")
    sam_chg = {}
    if not sam.empty:
        sam["chg"] = sam["Close"].pct_change() * 100
        for idx, row in sam.iterrows():
            sam_chg[idx.date()] = row["chg"]

    def last_per_date(df):
        if df.empty:
            return {}
        out = {}
        for d, g in df.groupby(df.index.date):
            out[d] = g.iloc[-1]
        return out

    inv_by = last_per_date(h_inv)
    nq60_by = last_per_date(h_nq60)
    nq20_by = last_per_date(h_nq20)
    sox_by = last_per_date(h_sox)

    G, R = "🟢", "🔴"
    dates = sorted(set(inv_by) | set(nq60_by), reverse=True)[:25]
    rows = []
    for d in dates:
        iv = inv_by.get(d); nq = nq60_by.get(d); n2 = nq20_by.get(d); sx = sox_by.get(d)
        inv_ok = (iv is not None and not pd.isna(iv.get("MA120")) and iv["Close"] < iv["MA120"])
        nq_ok = (nq is not None and not pd.isna(nq.get("MA120")) and nq["Close"] > nq["MA120"])
        n2_ok = (n2 is not None and not pd.isna(n2.get("MA120"))
                 and n2["MA20"] > n2["MA60"] > n2["MA120"])
        sox_ok = (sx is not None and not pd.isna(sx.get("MA120")) and sx["Close"] > sx["MA120"])
        agrade = bool(inv_ok and nq_ok and n2_ok)   # A급은 장중 3종 기준 (SOX는 참고)
        chg = sam_chg.get(d)
        rows.append({
            "날짜": d.strftime("%m-%d"),
            "판정": (G + " A급") if agrade else (R + " 관망"),
            "SOX": G if sox_ok else R,
            "인버스": G if inv_ok else R,
            "나스닥60": G if nq_ok else R,
            "나스닥20": G if n2_ok else R,
            "삼성 등락": (f"{chg:+.2f}%" if chg is not None else "—"),
        })
    return pd.DataFrame(rows)

try:
    hist = build_history()
    if hist.empty:
        st.info("히스토리 데이터를 못 불러왔습니다.")
    else:
        a_days = (hist["판정"] == "🟢 A급").sum()
        # A급 날 중 삼성 상승 비율
        up_on_a = 0
        for _, r in hist[hist["판정"] == "🟢 A급"].iterrows():
            v = r["삼성 등락"]
            if v != "—" and v.startswith("+"):
                up_on_a += 1
        msg = f"최근 {len(hist)}거래일 중 **A급 {a_days}일**"
        if a_days:
            msg += f" · 그중 삼성 상승 {up_on_a}일 ({up_on_a/a_days*100:.0f}%)"
        st.caption(msg + " — A급 날 실제로 삼성이 올랐는지 눈으로 검증하세요.")
        st.dataframe(hist, use_container_width=True, hide_index=True, height=420)
        st.caption("🟢=조건 충족 / 🔴=미충족 · 인버스🟢=기준선 아래, 나스닥60🟢=기준선 위, 나스닥20🟢=정배열, SOX🟢=기준선 위(참고)")
        st.caption("※ 각 날짜의 '장 마감 무렵' 상태 기준. 시간대(미국/한국) 차이로 근사치이며, 정밀 복기는 실제 매매기록과 대조하세요.")
except Exception as e:
    st.warning(f"히스토리 계산 중 문제: {e}")
