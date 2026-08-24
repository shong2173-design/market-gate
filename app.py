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

base3 = bool(sox_good and inv_good and nq_good)   # A급: SOX+인버스+나스닥60
sgrade = bool(base3 and nq20_aligned)             # S급: +나스닥20
gate_ok = base3   # 진입 가능 = A급 이상

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

if sgrade:
    vcol = "#4b8ef0"; vtxt = "🔵 S급 — 최상급 진입"
elif base3:
    vcol = "#4caf7d"; vtxt = "🟢 A급 — 진입 가능"
else:
    vcol = "#f0464b"; vtxt = "🔴 관망 / 금지"

sox_sub = sox_txt.split("(")[0].strip() if sox_txt else "—"
inv_sub = inv_txt.split("(")[0].strip() if inv_txt else "—"
nq_sub = nq_txt.split("(")[0].strip() if nq_txt else "—"
nq20_sub = "정배열 O" if nq20_aligned else ("정배열 X" if nq20_aligned is False else "—")

st.markdown(f"""
<div style="background:{vcol}22;border:1px solid {vcol};border-radius:12px;padding:10px 14px;margin-bottom:10px;text-align:center">
  <span style="font-size:19px;font-weight:800;color:{vcol}">{vtxt}</span>
</div>
<div style="display:flex;gap:6px;margin-bottom:6px">
  {chip("SOX", sox_good, sox_sub)}
  {chip("인버스30", inv_good, inv_sub)}
  {chip("나스닥60", nq_good, nq_sub)}
  {chip("나스닥20", nq20_aligned, nq20_sub)}
</div>
<div style="font-size:10.5px;color:#5d6b7d;text-align:center;margin-bottom:14px">
  A급 = SOX·인버스·나스닥60 모두 🟢 (진입 가능) · S급 = 나스닥20까지 🟢 (최상급)
</div>
""", unsafe_allow_html=True)

# ===== 오늘 판정을 구글시트에 기록 =====
import requests as _rq
def _save_today():
    url = st.secrets.get("SHEET_WEBHOOK", "")
    if not url:
        return False, "SHEET_WEBHOOK 미설정 (Streamlit Secrets 확인)"
    grade_txt = "🔵 S급" if sgrade else ("🟢 A급" if base3 else "🔴 관망")
    _today = dt.datetime.now().strftime("%m-%d")
    payload = {
        "날짜": _today,
        "판정": grade_txt,
        "SOX": "🟢" if sox_good else "🔴",
        "인버스": "🟢" if inv_good else "🔴",
        "나닥60": "🟢" if nq_good else "🔴",
        "나닥20": "🟢" if nq20_aligned else "🔴",
        "삼성등락": "",   # 그날 종가 확정 후 별도 기입(장중엔 미정)
    }
    try:
        r = _rq.post(url, json=payload, timeout=10)
        ok = '"ok":true' in r.text.replace(" ", "")
        return ok, (r.text[:120] if not ok else "")
    except Exception as e:
        return False, str(e)

bc1, bc2 = st.columns([1, 2])
if bc1.button("📌 오늘 판정 기록", use_container_width=True):
    ok, err = _save_today()
    if ok:
        bc2.success(f"{dt.datetime.now():%m-%d} 판정 시트에 저장됨")
    else:
        bc2.error(f"저장 실패: {err}")


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
verdict = ("🔵 S급 — 최상급" if sgrade else ("🟢 A급 — 진입 가능" if base3 else "🔴 관망 / 금지"))
g4.metric("종합 판정", verdict)

if sgrade:
    st.success("S급 — SOX·인버스·나스닥60·나스닥20 모두 충족. (종목 조건: 기준선 위 + 10분 정배열 + 수급 별도 확인)")
elif base3:
    st.success("A급 — SOX·인버스·나스닥60 충족(나스닥20 미충족). 진입 가능하나 최상급은 아님.")
else:
    st.warning("관망 — SOX·인버스·나스닥60 중 하나 이상 불충족. 인버스가 기준선 위면 매매금지.")

st.divider()

st.caption(f"업데이트: {now}")

# ---------------------------------------------------------------------------
# 날짜별 A급/관망 히스토리 (한 달 복기)
# ---------------------------------------------------------------------------
st.divider()
st.markdown("#### 🗓️ 날짜별 게이트 히스토리 (최대 60일 · 날짜 선택)")

@st.cache_data(ttl=1800)
def build_history():
    # 지표별 과거 봉 (MA는 전체로 계산). 야후 30/60분봉은 최대 60일 제공.
    h_inv = add_ma(fetch("114800.KS", "30m", "60d"))
    h_nq60 = add_ma(fetch("NQ=F", "60m", "60d"))
    h_sox = add_ma(fetch("^SOX", "30m", "60d"))
    # 나스닥20분봉용 5분봉 — 야후가 60일 다 안 주면(보통 최근 수일) 과거는 자동으로 빈 값
    h_nq5 = fetch("NQ=F", "5m", "60d")
    h_nq20 = pd.DataFrame()
    if not h_nq5.empty:
        h_nq20 = h_nq5.resample("20min").agg({"Open": "first", "High": "max",
                                              "Low": "min", "Close": "last"}).dropna()
        h_nq20 = add_ma(h_nq20)
    # 삼성전자 일봉 등락률
    sam = fetch("005930.KS", "1d", "4mo")
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
    dates = sorted(set(inv_by) | set(nq60_by), reverse=True)   # 전체 (표시 일수는 밖에서 자름)
    rows = []
    for d in dates:
        iv = inv_by.get(d); nq = nq60_by.get(d); n2 = nq20_by.get(d); sx = sox_by.get(d)
        inv_ok = (iv is not None and not pd.isna(iv.get("MA120")) and iv["Close"] < iv["MA120"])
        nq_ok = (nq is not None and not pd.isna(nq.get("MA120")) and nq["Close"] > nq["MA120"])
        n2_ok = (n2 is not None and not pd.isna(n2.get("MA120"))
                 and n2["MA20"] > n2["MA60"] > n2["MA120"])
        sox_ok = (sx is not None and not pd.isna(sx.get("MA120")) and sx["Close"] > sx["MA120"])
        base3 = bool(sox_ok and inv_ok and nq_ok)      # A급: SOX+인버스+나스닥60
        sgrade = bool(base3 and n2_ok)                  # S급: +나스닥20 정배열
        if sgrade:
            grade = "🔵 S급"
        elif base3:
            grade = "🟢 A급"
        else:
            grade = "🔴 관망"
        chg = sam_chg.get(d)
        rows.append({
            "_date": d,   # 실제 날짜 객체 (필터용, 표시 안 함)
            "날짜": d.strftime("%m-%d"),
            "판정": grade,
            "SOX": G if sox_ok else R,
            "인버스": G if inv_ok else R,
            "나스닥60": G if nq_ok else R,
            "나스닥20": G if n2_ok else R,
            "삼성 등락": (f"{chg:+.2f}%" if chg is not None and not pd.isna(chg) else "—"),
        })
    return pd.DataFrame(rows)

try:
    hist = build_history()
    if hist.empty:
        st.info("히스토리 데이터를 못 불러왔습니다.")
    else:
        # ----- 날짜 선택기: 데이터 범위 안에서 시작~끝 고르기 -----
        all_dates = sorted(hist["_date"].tolist())
        dmin, dmax = all_dates[0], all_dates[-1]
        import datetime as _dt
        default_start = max(dmin, dmax - _dt.timedelta(days=31))  # 기본 최근 1개월
        c1, c2 = st.columns(2)
        start_d = c1.date_input("시작 날짜", value=default_start,
                                min_value=dmin, max_value=dmax, key="hist_start")
        end_d = c2.date_input("끝 날짜", value=dmax,
                              min_value=dmin, max_value=dmax, key="hist_end")
        if start_d > end_d:
            start_d, end_d = end_d, start_d  # 거꾸로 고르면 자동 교정

        # 선택 구간만 필터 (최신이 위로)
        view = hist[(hist["_date"] >= start_d) & (hist["_date"] <= end_d)]
        view = view.sort_values("_date", ascending=False)

        s_days = (view["판정"] == "🔵 S급").sum()
        a_days = (view["판정"] == "🟢 A급").sum()
        up_on = 0; entry_days = 0
        for _, r in view[view["판정"].isin(["🔵 S급", "🟢 A급"])].iterrows():
            entry_days += 1
            v = r["삼성 등락"]
            if v != "—" and v.startswith("+"):
                up_on += 1
        msg = f"{start_d:%m/%d}~{end_d:%m/%d} · {len(view)}거래일 중 **S급 {s_days} · A급 {a_days}**"
        if entry_days:
            msg += f" · 진입급 날 삼성 상승 {up_on}/{entry_days} ({up_on/entry_days*100:.0f}%)"
        st.caption(msg)

        # 스크롤 없이 다 보이는 컴팩트 HTML 표
        head = "<tr><th>날짜</th><th>판정</th><th>SOX</th><th>인버스</th><th>나닥60</th><th>나닥20</th><th>삼성</th></tr>"
        body = ""
        for _, r in view.iterrows():
            chg = r["삼성 등락"]
            chg_color = "#f0464b" if chg.startswith("+") else ("#4b8ef0" if chg.startswith("-") else "#5d6b7d")
            pj = r["판정"]
            pj_bg = "#4b8ef022" if "S급" in pj else ("#4caf7d22" if "A급" in pj else "transparent")
            body += (f"<tr style='background:{pj_bg}'>"
                     f"<td class='dt'>{r['날짜']}</td>"
                     f"<td class='pj'>{pj}</td>"
                     f"<td>{r['SOX']}</td><td>{r['인버스']}</td>"
                     f"<td>{r['나스닥60']}</td><td>{r['나스닥20']}</td>"
                     f"<td style='color:{chg_color};font-family:monospace'>{chg}</td></tr>")
        st.markdown(f"""
<style>
  .histtbl{{width:100%;border-collapse:collapse;font-size:12px}}
  .histtbl th{{color:#8b98a9;font-weight:700;padding:3px 4px;border-bottom:1px solid #28313d;text-align:center;font-size:10.5px}}
  .histtbl td{{padding:2px 4px;text-align:center;border-bottom:1px solid #1c2330;line-height:1.35}}
  .histtbl td.dt{{font-family:monospace;color:#111827;font-weight:800;font-size:12.5px}}
  .histtbl td.pj{{font-size:10.5px;font-weight:700;white-space:nowrap}}
</style>
<table class="histtbl">{head}{body}</table>
""", unsafe_allow_html=True)
        st.caption("🔵S급=4개 전부 · 🟢A급=SOX+인버스+나닥60 · 🔴관망 / 인버스🟢=기준선 아래·나닥·SOX🟢=위·나닥20🟢=정배열 · ※장 마감 무렵 근사치")
except Exception as e:
    st.warning(f"히스토리 계산 중 문제: {e}")
