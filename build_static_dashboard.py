"""GitHub Pages용 정적 대시보드 생성 스크립트.

실행: python build_static_dashboard.py
결과: docs/index.html (데이터를 포함한 단일 HTML 파일)

서버 없이 브라우저에서만 동작하도록 Vega-Lite로 필터를 구성한다.
Streamlit 대시보드(dashboard.py)와 같은 데이터를 쓰지만, 이쪽은 배포용이다.
"""

import json
from pathlib import Path

import pandas as pd

DATA_PATH = Path("data/cpi_monthly.csv")
OUT_PATH = Path("docs/index.html")
REPO_URL = "https://github.com/qjskffj-code/codyssey_M1-1"

COUNTRY_NAMES = {"KOR": "한국", "USA": "미국", "JPN": "일본", "GBR": "영국", "DEU": "독일", "FRA": "프랑스"}
COLORS = {"KOR": "#2a78d6", "USA": "#eb6834", "JPN": "#1baf7a", "GBR": "#eda100", "DEU": "#e87ba4", "FRA": "#008300"}
CATEGORY_NAMES = {
    "restaurants_hotels": "음식 및 숙박 (외식)",
    "food": "식료품",
    "energy": "에너지",
    "all_items": "전체 CPI",
}
METRIC_LABELS = {"index": "지수 (2015년=100)", "yoy": "전년동월대비 상승률(%)", "ma3": "상승률 3개월 이동평균(%)"}
EVENTS = {"코로나19": "2020-03-01", "러-우 전쟁": "2022-02-01", "이-하 전쟁": "2023-10-01"}
START, ANALYSIS_END = "2015-01-01", "2024-12-01"


def load_tables():
    raw = pd.read_csv(DATA_PATH, parse_dates=["date"])
    # 빠진 달(미국 2025-10)이 있어도 12개월 전과 정확히 비교되도록 날짜 기준 표로 만든다
    wide = raw.pivot_table(index="date", columns=["country", "category"], values="index").asfreq("MS")
    yoy = wide.pct_change(12) * 100
    ma3 = yoy.rolling(3).mean()
    return wide, yoy, ma3


def series_records(wide, yoy, ma3):
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
    data = pd.concat(parts, ignore_index=True)
    data = data[(data["date"] >= START) & data["index"].notna()].copy()
    data["나라"] = data["country"].map(COUNTRY_NAMES)
    data["date"] = data["date"].dt.strftime("%Y-%m-%d")
    data = data.round({"index": 4, "yoy": 3, "ma3": 3})
    data = data.astype(object).where(pd.notna(data), None)
    return data[["date", "나라", "category", "index", "yoy", "ma3"]].to_dict("records")


def event_records(wide):
    """사건 직전 12개월 / 직후 12개월 상승률을 미리 계산한다."""
    rows = []
    for category in CATEGORY_NAMES:
        for event, when in EVENTS.items():
            event_date = pd.Timestamp(when)
            for code, name in COUNTRY_NAMES.items():
                if (code, category) not in wide.columns:
                    continue
                series = wide[(code, category)]
                for label, start, end in (
                    ("직전 12개월", event_date - pd.DateOffset(months=12), event_date),
                    ("직후 12개월", event_date, event_date + pd.DateOffset(months=12)),
                ):
                    if start not in series.index or end not in series.index:
                        continue
                    if pd.isna(series[start]) or pd.isna(series[end]):
                        continue
                    rows.append({
                        "category": category,
                        "사건": event,
                        "나라": name,
                        "구간": label,
                        "상승률": round((series[end] / series[start] - 1) * 100, 2),
                    })
    return rows


def summary_rows(wide, yoy):
    """분석 기간(2015-01 ~ 2024-12) 음식 및 숙박 요약."""
    rows = []
    for code, name in COUNTRY_NAMES.items():
        index_series = wide[(code, "restaurants_hotels")].loc[START:ANALYSIS_END]
        yoy_series = yoy[(code, "restaurants_hotels")].loc[START:ANALYSIS_END]
        peak_month = yoy_series.idxmax()
        rows.append({
            "나라": name,
            "누적 상승률(%)": f"{(index_series.iloc[-1] / index_series.iloc[0] - 1) * 100:+.1f}",
            "평균 상승률(%)": f"{yoy_series.mean():.2f}",
            "최고 상승률(%)": f"{yoy_series.max():.2f}",
            "최고 월": f"{peak_month:%Y-%m}",
        })
    return rows


def build_spec(series, events):
    country_order = list(COUNTRY_NAMES.values())
    event_points = [{"date": when, "사건": name} for name, when in EVENTS.items()]
    period_filter = "year(datum.date) >= y0 && year(datum.date) <= y1"
    series_encoding = {
        "x": {"field": "date", "type": "temporal", "title": None,
              "axis": {"format": "%Y", "grid": False, "tickCount": {"interval": "year", "step": 1}}},
        "y": {"field": "value", "type": "quantitative", "title": "값", "scale": {"zero": False}},
        "color": {"field": "나라", "type": "nominal", "title": None,
                  "scale": {"domain": country_order, "range": [COLORS[c] for c in COUNTRY_NAMES]},
                  "legend": {"orient": "top"}},
    }

    trend = {
        "width": "container",
        "height": 420,
        "title": {"text": "항목별 물가 추이", "anchor": "start", "fontSize": 15, "color": "#0b0b0b",
                  "subtitle": "위의 조작 도구에서 항목·지표·기간을 바꿀 수 있습니다.",
                  "subtitleColor": "#898781", "subtitleFontSize": 12},
        "data": {"name": "series"},
        "transform": [
            {"filter": "datum.category == cat"},
            {"filter": period_filter},
            {"window": [{"op": "first_value", "field": "index", "as": "firstIndex"}],
             "groupby": ["나라"], "sort": [{"field": "date"}], "frame": [None, None]},
            {"calculate": "metric == 'index' && rebase ? datum.index / datum.firstIndex * 100 : datum[metric]",
             "as": "value"},
            {"filter": "isValid(datum.value)"},
        ],
        # 상위 encoding을 두면 사건 표시 레이어에도 y·color가 적용되어 마크가 사라진다.
        # 그래서 선·점 레이어에만 인코딩을 넣는다.
        "layer": [
            {"mark": {"type": "line", "strokeWidth": 2},
             # 범례 클릭으로 나라를 고르는 선택은 이 unit spec 안에 두어야 신호가 중복되지 않는다
             "params": [{"name": "sel", "select": {"type": "point", "fields": ["나라"]}, "bind": "legend"}],
             "encoding": dict(series_encoding,
                              opacity={"condition": {"param": "sel", "value": 1}, "value": 0.12})},
            {"mark": {"type": "point", "size": 70, "opacity": 0},
             "encoding": dict(series_encoding, tooltip=[
                 {"field": "나라", "type": "nominal"},
                 {"field": "date", "type": "temporal", "title": "월", "format": "%Y-%m"},
                 {"field": "index", "type": "quantitative", "title": "지수", "format": ".2f"},
                 {"field": "yoy", "type": "quantitative", "title": "전년동월대비(%)", "format": ".2f"},
             ])},
            {"data": {"values": event_points},
             "transform": [{"filter": period_filter}],
             "mark": {"type": "rule", "strokeDash": [4, 4], "color": "#898781"},
             "encoding": {"x": {"field": "date", "type": "temporal"},
                          "opacity": {"value": {"expr": "showEvents ? 1 : 0"}}}},
            {"data": {"values": event_points},
             "transform": [{"filter": period_filter}],
             "mark": {"type": "text", "align": "left", "dx": 4, "dy": 2, "baseline": "top",
                      "color": "#52514e", "fontSize": 11},
             "encoding": {"x": {"field": "date", "type": "temporal"},
                          "y": {"value": 6},
                          "text": {"field": "사건"},
                          "opacity": {"value": {"expr": "showEvents ? 1 : 0"}}}},
            {"data": {"values": [{"zero": 0}]},
             "mark": {"type": "rule", "color": "#898781"},
             "encoding": {"y": {"field": "zero", "type": "quantitative"},
                          "opacity": {"value": {"expr": "metric == 'index' ? 0 : 1"}}}},
        ],
    }

    before_after = {
        "width": "container",
        "height": 320,
        "title": {"text": "사건 전후 12개월 상승률", "anchor": "start", "fontSize": 15, "color": "#0b0b0b",
                  "subtitle": "사건이 일어난 달 기준입니다. 위의 기간 설정과는 무관하게 계산합니다.",
                  "subtitleColor": "#898781", "subtitleFontSize": 12},
        "data": {"values": events},
        "transform": [{"filter": "datum.category == cat"}, {"filter": "datum.사건 == evt"}],
        "mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
        "encoding": {
            "x": {"field": "나라", "type": "nominal", "sort": country_order, "title": None,
                  "axis": {"labelAngle": 0}},
            "xOffset": {"field": "구간", "type": "nominal", "sort": ["직전 12개월", "직후 12개월"]},
            "y": {"field": "상승률", "type": "quantitative", "title": "상승률(%)"},
            "color": {"field": "구간", "type": "nominal", "title": None,
                      "scale": {"domain": ["직전 12개월", "직후 12개월"], "range": ["#c3c2b7", "#2a78d6"]},
                      "legend": {"orient": "top"}},
            "tooltip": [{"field": "나라"}, {"field": "구간"},
                        {"field": "상승률", "type": "quantitative", "format": ".2f"}],
        },
    }

    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "datasets": {"series": series},
        "background": "#fcfcfb",
        "config": {
            "font": "'Malgun Gothic', 'Apple SD Gothic Neo', system-ui, sans-serif",
            "axis": {"labelColor": "#898781", "titleColor": "#52514e", "domainColor": "#c3c2b7",
                     "gridColor": "#e1e0d9", "tickColor": "#c3c2b7"},
            "legend": {"labelColor": "#52514e", "titleColor": "#52514e"},
            "view": {"stroke": None},
        },
        "params": [
            {"name": "cat", "value": "restaurants_hotels",
             "bind": {"input": "select", "options": list(CATEGORY_NAMES),
                      "labels": list(CATEGORY_NAMES.values()), "name": "항목  "}},
            {"name": "metric", "value": "yoy",
             "bind": {"input": "select", "options": list(METRIC_LABELS),
                      "labels": list(METRIC_LABELS.values()), "name": "지표  "}},
            {"name": "y0", "value": 2015,
             "bind": {"input": "range", "min": 2015, "max": 2026, "step": 1, "name": "시작 연도  "}},
            {"name": "y1", "value": 2024,
             "bind": {"input": "range", "min": 2015, "max": 2026, "step": 1, "name": "끝 연도  "}},
            {"name": "rebase", "value": False,
             "bind": {"input": "checkbox", "name": "시작 월을 100으로 맞추기 (지표가 '지수'일 때)  "}},
            {"name": "showEvents", "value": True,
             "bind": {"input": "checkbox", "name": "사건 시점 표시  "}},
            {"name": "evt", "value": "러-우 전쟁",
             "bind": {"input": "select", "options": list(EVENTS), "name": "전후 12개월을 비교할 사건  "}},
        ],
        "vconcat": [trend, before_after],
        # 두 그래프의 색이 서로 섞이지 않도록 색상 스케일과 범례를 따로 둔다
        "resolve": {"scale": {"color": "independent"}, "legend": {"color": "independent"}},
    }


def build_html(spec, summary):
    header = "".join(f"<th>{key}</th>" for key in summary[0])
    body = "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row.values()) + "</tr>" for row in summary)
    spec_json = json.dumps(spec, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>주요 6개국 외식 물가 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #f9f9f7; color: #0b0b0b;
         font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', system-ui, sans-serif; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 32px 16px 64px; }}
  h1 {{ font-size: 1.9rem; margin: 0 0 8px; }}
  h2 {{ font-size: 1.2rem; margin: 32px 0 8px; }}
  p, li {{ color: #52514e; line-height: 1.6; }}
  .card {{ background: #fcfcfb; border: 1px solid rgba(11,11,11,.08); border-radius: 12px;
           padding: 20px; margin-top: 16px; }}
  .hint {{ font-size: .9rem; color: #898781; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .95rem; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid #e1e0d9; text-align: right;
            font-variant-numeric: tabular-nums; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color: #52514e; font-weight: 600; }}
  a {{ color: #2a78d6; }}
  #chart {{ width: 100%; }}
  /* vega-embed 기본값이 inline-block이라 container 폭을 잡지 못한다 */
  #chart .vega-embed {{ display: block; width: 100%; }}
  #controls {{ margin-bottom: 18px; padding-bottom: 8px; border-bottom: 1px solid #e1e0d9; }}
  .vega-bind {{ display: inline-block; margin: 0 18px 10px 0; font-size: .92rem; color: #52514e; }}
  .vega-bind input[type="range"] {{ vertical-align: middle; }}
  .vega-bind select {{ font-size: .92rem; padding: 2px 4px; }}
  .table-scroll {{ overflow-x: auto; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🍽️ 주요 6개국 외식 물가 대시보드</h1>
  <p>OECD 소비자물가지수로 본 한국·미국·일본·영국·독일·프랑스의 외식 물가입니다.
     항목·지표·기간을 바꿔 가며 살펴볼 수 있습니다.
     분석 리포트는 <a href="{REPO_URL}/blob/main/REPORT.md">REPORT.md</a>,
     코드는 <a href="{REPO_URL}">GitHub 저장소</a>에 있습니다.</p>

  <div class="card">
    <div id="controls"></div>
    <div id="chart"></div>
    <p class="hint">범례의 나라 이름을 클릭하면 그 나라만 강조됩니다. Shift를 누른 채 클릭하면 여러 나라를 고를 수 있고,
       빈 곳을 클릭하면 해제됩니다. 선 위에 마우스를 올리면 그 달의 값이 보입니다.</p>
  </div>

  <h2>분석 기간 요약 (음식 및 숙박, 2015-01 ~ 2024-12)</h2>
  <div class="card table-scroll">
    <table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>
  </div>

  <h2>데이터 설명과 주의사항</h2>
  <div class="card">
    <ul>
      <li>출처: OECD Data Explorer, Consumer price indices (COICOP 1999 / 일본은 COICOP 2018), 수집일 2026-09-15</li>
      <li><b>음식 및 숙박(CP11)</b>은 외식과 숙박을 합친 지수입니다. 순수 외식 물가와 다를 수 있습니다.</li>
      <li>미국의 음식 및 숙박·에너지 지수는 2024-12까지만 제공됩니다.</li>
      <li>지수는 2015년=100인 상대 값이라 나라 간 가격 수준은 비교할 수 없습니다.</li>
      <li>사건 전후 비교는 시점이 겹친다는 것만 보여주며, 사건이 원인이라는 뜻은 아닙니다.</li>
    </ul>
  </div>
</div>
<script>
  // bind 옵션으로 조작 도구(select, slider)를 그래프 위 영역에 배치한다
  vegaEmbed('#chart', {spec_json}, {{
      bind: '#controls',
      actions: {{export: true, source: false, compiled: false, editor: false}}
    }})
    .then(function () {{
      // bind 옵션이 동작하지 않는 버전을 대비한 보완 처리
      var controls = document.querySelector('#controls');
      var bindings = document.querySelector('#chart .vega-bindings');
      if (controls && bindings && !controls.contains(bindings)) {{ controls.appendChild(bindings); }}
    }})
    .catch(console.error);
</script>
</body>
</html>
"""


def main():
    wide, yoy, ma3 = load_tables()
    spec = build_spec(series_records(wide, yoy, ma3), event_records(wide))
    html = build_html(spec, summary_rows(wide, yoy))
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"{OUT_PATH} 생성 ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
