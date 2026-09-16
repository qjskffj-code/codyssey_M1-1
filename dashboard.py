"""주요 6개국 외식 물가 탐색 대시보드.

실행: streamlit run dashboard.py

URL 쿼리로 처음 화면의 조건을 지정할 수 있다 (시나리오 재현용).
  예) http://localhost:8501/?countries=KOR,GBR,DEU&category=energy&metric=yoy&start=2021-01&end=2024-12&event=ukraine
"""

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

DATA_PATH = "data/cpi_monthly.csv"
COUNTRY_NAMES = {"KOR": "한국", "USA": "미국", "JPN": "일본", "GBR": "영국", "DEU": "독일", "FRA": "프랑스"}
COLORS = {"KOR": "#2a78d6", "USA": "#eb6834", "JPN": "#1baf7a", "GBR": "#eda100", "DEU": "#e87ba4", "FRA": "#008300"}
CATEGORY_NAMES = {
    "restaurants_hotels": "음식 및 숙박 (외식)",
    "food": "식료품",
    "energy": "에너지",
    "all_items": "전체 CPI",
}
METRICS = {
    "index": "지수 (2015년=100)",
    "yoy": "전년동월대비 상승률(%)",
    "ma3": "상승률 3개월 이동평균(%)",
}
EVENTS = {
    "covid": ("코로나19", pd.Timestamp("2020-03-01")),
    "ukraine": ("러-우 전쟁", pd.Timestamp("2022-02-01")),
    "israel": ("이-하 전쟁", pd.Timestamp("2023-10-01")),
}
DEFAULT_START, DEFAULT_END = "2015-01", "2024-12"

st.set_page_config(page_title="외식 물가 대시보드", page_icon="🍽️", layout="wide")


@st.cache_data
def load_data() -> pd.DataFrame:
    """월별 지수에 전년동월대비 상승률과 3개월 이동평균을 붙인 long format 표를 만든다."""
    raw = pd.read_csv(DATA_PATH, parse_dates=["date"])
    # 빠진 달(미국 2025-10)이 있어도 12개월 전과 정확히 비교되도록 날짜 기준 표로 만든다
    wide = raw.pivot_table(index="date", columns=["country", "category"], values="index").asfreq("MS")
    yoy = wide.pct_change(12) * 100
    ma3 = yoy.rolling(3).mean()

    parts = []
    for country, category in wide.columns:
        parts.append(pd.DataFrame({
            "date": wide.index,
            "country": country,
            "category": category,
            "index": wide[(country, category)].to_numpy(),
            "yoy": yoy[(country, category)].to_numpy(),
            "ma3": ma3[(country, category)].to_numpy(),
        }))
    return pd.concat(parts, ignore_index=True).dropna(subset=["index"])


def query_value(key: str, default: str, allowed) -> str:
    value = st.query_params.get(key)
    return value if value in allowed else default


def query_list(key: str, default: list[str], allowed) -> list[str]:
    value = st.query_params.get(key)
    items = [v for v in value.split(",") if v in allowed] if value else []
    return items or default


def query_month(key: str, default: str) -> date:
    try:
        return pd.Timestamp(st.query_params.get(key, default)).date()
    except ValueError:
        return pd.Timestamp(default).date()


def change_pct(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    if start not in series.index or end not in series.index:
        return None
    return (series[end] / series[start] - 1) * 100


data = load_data()
latest_month = data["date"].max().date()

# ---------------------------------------------------------------- 조건 설정
with st.sidebar:
    st.header("조건 설정")
    countries = st.multiselect(
        "나라",
        options=list(COUNTRY_NAMES),
        default=query_list("countries", list(COUNTRY_NAMES), COUNTRY_NAMES),
        format_func=COUNTRY_NAMES.get,
    )
    category = st.selectbox(
        "항목",
        options=list(CATEGORY_NAMES),
        index=list(CATEGORY_NAMES).index(query_value("category", "restaurants_hotels", CATEGORY_NAMES)),
        format_func=CATEGORY_NAMES.get,
    )
    metric = st.radio(
        "지표",
        options=list(METRICS),
        index=list(METRICS).index(query_value("metric", "yoy", METRICS)),
        format_func=METRICS.get,
    )
    start_date, end_date = st.slider(
        "기간",
        min_value=date(2015, 1, 1),
        max_value=latest_month,
        value=(query_month("start", DEFAULT_START), min(query_month("end", DEFAULT_END), latest_month)),
        format="YYYY-MM",
    )
    rebase = st.checkbox(
        "시작 월을 100으로 맞추기",
        value=st.query_params.get("rebase") == "1",
        disabled=metric != "index",
        help="지표가 '지수'일 때만 사용한다. 선택한 기간 동안 얼마나 올랐는지 나라별로 같은 출발점에서 비교할 수 있다.",
    )
    show_events = st.checkbox("사건 시점 표시", value=True)
    event_key = st.selectbox(
        "전후 12개월을 비교할 사건",
        options=list(EVENTS),
        index=list(EVENTS).index(query_value("event", "ukraine", EVENTS)),
        format_func=lambda key: f"{EVENTS[key][0]} ({EVENTS[key][1]:%Y.%m})",
    )

start = pd.Timestamp(start_date).to_period("M").to_timestamp()
end = pd.Timestamp(end_date).to_period("M").to_timestamp()

# ---------------------------------------------------------------- 제목
st.title("🍽️ 주요 6개국 외식 물가 대시보드")
st.caption(
    f"OECD 소비자물가지수 · 월별 · {CATEGORY_NAMES[category]} · {start:%Y-%m} ~ {end:%Y-%m} · "
    "음식 및 숙박(CP11)은 외식과 숙박을 합친 지수입니다."
)

if not countries:
    st.warning("왼쪽에서 나라를 하나 이상 선택하세요.")
    st.stop()

view = data[
    data["country"].isin(countries) & (data["category"] == category) & data["date"].between(start, end)
].copy()
if metric == "index" and rebase:
    view["index"] = view["index"] / view.groupby("country")["index"].transform("first") * 100
view["나라"] = view["country"].map(COUNTRY_NAMES)

last_month = view.groupby("country")["date"].max()
missing = [COUNTRY_NAMES[c] for c in countries if c not in last_month.index]
cut_short = [f"{COUNTRY_NAMES[c]}({d:%Y-%m}까지)" for c, d in last_month.items() if d < end]
if missing:
    st.info(f"선택한 조건에 데이터가 없는 나라: {', '.join(missing)}")
if cut_short:
    st.info(f"선택한 기간 끝까지 데이터가 없는 나라: {', '.join(cut_short)}")

# ---------------------------------------------------------------- 핵심 수치
st.subheader("기간 누적 상승률")
metric_columns = st.columns(len(countries))
for column, country in zip(metric_columns, countries):
    series = view.loc[view["country"] == country]
    if len(series) < 2:
        column.metric(COUNTRY_NAMES[country], "데이터 없음")
        continue
    total = (series["index"].iloc[-1] / series["index"].iloc[0] - 1) * 100
    column.metric(
        COUNTRY_NAMES[country],
        f"{total:+.1f}%",
        help=f"{series['date'].iloc[0]:%Y-%m} → {series['date'].iloc[-1]:%Y-%m} 지수 변화율",
    )
    column.caption(f"평균 상승률 {series['yoy'].mean():.2f}%")

# ---------------------------------------------------------------- 추이 그래프
metric_label = METRICS[metric] + (" · 시작 월=100" if metric == "index" and rebase else "")
st.subheader(f"{CATEGORY_NAMES[category]} 추이")
domain = [COUNTRY_NAMES[c] for c in countries]
plot_data = view.dropna(subset=[metric])
x_axis = alt.X("date:T", title=None, axis=alt.Axis(format="%Y-%m", labelColor="#898781", grid=False))
y_axis = alt.Y(f"{metric}:Q", title=metric_label, scale=alt.Scale(zero=False))
color = alt.Color("나라:N", scale=alt.Scale(domain=domain, range=[COLORS[c] for c in countries]),
                  legend=alt.Legend(orient="top", title=None))
tooltip = [
    alt.Tooltip("나라:N"),
    alt.Tooltip("date:T", title="월", format="%Y-%m"),
    alt.Tooltip("index:Q", title="지수", format=".2f"),
    alt.Tooltip("yoy:Q", title="전년동월대비(%)", format=".2f"),
]
hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False)
base = alt.Chart(plot_data).encode(x=x_axis)
layers = [
    base.mark_line(strokeWidth=2).encode(y=y_axis, color=color),
    base.mark_point(size=80, opacity=0).encode(y=y_axis, color=color, tooltip=tooltip).add_params(hover),
    base.mark_rule(color="#c3c2b7").encode(opacity=alt.condition(hover, alt.value(1), alt.value(0))),
]
if metric != "index":
    layers.append(alt.Chart(pd.DataFrame({"zero": [0]})).mark_rule(color="#898781").encode(y="zero:Q"))
if show_events:
    events = pd.DataFrame([{"사건": name, "date": when} for name, when in EVENTS.values()])
    events = events[events["date"].between(start, end)]
    layers.append(alt.Chart(events).mark_rule(strokeDash=[4, 4], color="#898781").encode(x="date:T"))
    layers.append(alt.Chart(events).mark_text(align="left", dx=4, color="#52514e").encode(
        x="date:T", y=alt.value(8), text="사건:N"))
st.altair_chart(alt.layer(*layers).properties(height=420), width="stretch")

# ---------------------------------------------------------------- 사건 전후 비교 + 요약 표
left, right = st.columns([1, 1])

with left:
    event_name, event_date = EVENTS[event_key]
    st.subheader(f"{event_name} 전후 12개월")
    st.caption("사건이 일어난 달을 기준으로 직전 12개월과 직후 12개월 상승률을 비교합니다. 기간 슬라이더와 관계없이 계산합니다.")
    indexed = data[data["category"] == category].set_index(["country", "date"])["index"]
    rows = []
    for country in countries:
        series = indexed.loc[country] if country in indexed.index.get_level_values(0) else pd.Series(dtype=float)
        before = change_pct(series, event_date - pd.DateOffset(months=12), event_date)
        after = change_pct(series, event_date, event_date + pd.DateOffset(months=12))
        if before is None or after is None:
            continue
        rows.append({"나라": COUNTRY_NAMES[country], "구간": "직전 12개월", "상승률": before})
        rows.append({"나라": COUNTRY_NAMES[country], "구간": "직후 12개월", "상승률": after})
    if rows:
        periods = ["직전 12개월", "직후 12개월"]
        bars = alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("나라:N", sort=domain, title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("구간:N", sort=periods),
            y=alt.Y("상승률:Q", title="상승률(%)"),
            color=alt.Color("구간:N", scale=alt.Scale(domain=periods, range=["#c3c2b7", "#2a78d6"]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=[alt.Tooltip("나라:N"), alt.Tooltip("구간:N"), alt.Tooltip("상승률:Q", format=".2f")],
        )
        st.altair_chart(bars.properties(height=340), width="stretch")
    else:
        st.info("이 사건의 전후 12개월 데이터가 있는 나라가 없습니다.")

with right:
    st.subheader("기간 요약")
    st.caption("선택한 나라·항목·기간 기준입니다.")
    summary = []
    for country in countries:
        series = view.loc[view["country"] == country].dropna(subset=["yoy"])
        if series.empty:
            continue
        peak = series.loc[series["yoy"].idxmax()]
        summary.append({
            "나라": COUNTRY_NAMES[country],
            "평균(%)": round(series["yoy"].mean(), 2),
            "최고(%)": round(peak["yoy"], 2),
            "최고 월": f"{peak['date']:%Y-%m}",
            "최저(%)": round(series["yoy"].min(), 2),
            "마지막 월": f"{series['date'].iloc[-1]:%Y-%m}",
        })
    st.caption("평균·최고·최저는 전년동월대비 상승률입니다.")
    st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")

with st.expander("데이터 설명과 주의사항"):
    st.markdown(
        """
- **출처:** OECD Data Explorer, Consumer price indices (COICOP 1999 / 일본은 COICOP 2018), 수집일 2026-09-15
- **음식 및 숙박(CP11)** 은 외식과 숙박을 합친 지수입니다. 순수 외식 물가와 다를 수 있습니다.
- 미국의 음식 및 숙박·에너지 지수는 2024-12까지만 제공됩니다. 미국 전체 CPI·식료품은 2025-10 값이 없습니다.
- 지수는 2015년=100인 상대 값이라 나라 간 가격 수준(어느 나라가 더 비싼가)은 비교할 수 없습니다.
- 사건 전후 비교는 시점이 겹친다는 것만 보여주며, 사건이 원인이라는 뜻은 아닙니다.
        """
    )
