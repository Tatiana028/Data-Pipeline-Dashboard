import os
from datetime import date, timedelta

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")


@st.cache_data(ttl=60)
def get_json(path: str, params: dict | None = None):
    """GET к нашему API; ответ кешируется на 60 секунд."""
    response = httpx.get(f"{API_URL}{path}", params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch(path: str, params: dict | None = None): 
    try:
        return get_json(path, params)
    except httpx.HTTPError:
        st.error("API is unavailable. Start it with `uvicorn src.api.main:app`.")
        st.stop()


def overview_page():
    st.title("Weather now")
    latest = fetch("/weather/latest")
    if not latest:
        st.info("No data yet — the ETL hasn't run.")
        return

    columns = st.columns(3)
    for i, row in enumerate(latest):
        with columns[i % 3]:
            st.metric(
                label=row["city_name"],
                value=f"{row['temperature_2m']:.1f} °C",
                delta=f"feels like {row['apparent_temperature']:.1f} °C",
                delta_color="off",
            )
            st.caption(
                f"Wind {row['wind_speed_10m']:.0f} km/h · "
                f"Rain {row['precipitation']:.1f} mm · "
                f"Updated {row['ts'][11:16]} UTC"
            )


def trends_page():
    st.title("Trends")
    cities = fetch("/cities")
    if not cities:
        st.info("No data yet — the ETL hasn't run.")
        return
    names = {c["name"]: c["id"] for c in cities}

    left, right = st.columns([2, 1])
    selected = left.multiselect("Cities", list(names), default=list(names)[:3])
    today = date.today()
    period = right.date_input("Period", value=(today - timedelta(days=6), today))
    if not selected or len(period) != 2:
        st.info("Pick at least one city and both dates.")
        return
    date_from, date_to = period

    hourly, daily = [], []
    for name in selected:
        params = {"city_id": names[name], "date_from": str(date_from), "date_to": str(date_to)}
        for row in fetch("/weather/hourly", {**params, "limit": 5000}):
            hourly.append({**row, "city": name})
        for row in fetch("/weather/daily", params):
            daily.append({**row, "city": name})
    if not hourly:
        st.info("No data for this period.")
        return

    hourly_df = pd.DataFrame(hourly)
    hourly_df["ts"] = pd.to_datetime(hourly_df["ts"])
    st.subheader("Hourly temperature")
    st.plotly_chart(
        px.line(hourly_df, x="ts", y="temperature_2m", color="city",
                labels={"ts": "Time (UTC)", "temperature_2m": "°C", "city": "City"}),
    )

    daily_df = pd.DataFrame(daily)
    temp_df = daily_df.melt(id_vars=["date", "city"], value_vars=["temp_min", "temp_max"],
                            var_name="kind", value_name="temp")
    st.subheader("Daily min / max temperature")
    st.plotly_chart(
        px.line(temp_df, x="date", y="temp", color="city", line_dash="kind", markers=True,
                labels={"date": "Date", "temp": "°C", "city": "City", "kind": ""}),
    )

    st.subheader("Daily precipitation")
    st.plotly_chart(
        px.bar(daily_df, x="date", y="precipitation_sum", color="city", barmode="group",
               labels={"date": "Date", "precipitation_sum": "mm", "city": "City"}),
    )


STATUS_COLORS = {
    "success": "background-color: #d4edda",
    "partial": "background-color: #fff3cd",
    "failed": "background-color: #f8d7da",
    "running": "background-color: #d1ecf1",
}
FRESHNESS_LIMIT_MIN = 90  # ETL ходит раз в час; дольше 90 минут без успеха — повод насторожиться


def pipeline_page():
    st.title("Pipeline health")
    runs = fetch("/etl/runs", {"limit": 50})
    if not runs:
        st.info("No ETL runs yet.")
        return

    df = pd.DataFrame(runs)
    df["started_at"] = pd.to_datetime(df["started_at"])
    df["finished_at"] = pd.to_datetime(df["finished_at"])
    df["duration_s"] = (df["finished_at"] - df["started_at"]).dt.total_seconds().round(1)

    # Свежесть: сколько минут прошло с последнего запуска, где загрузился хотя бы один город
    ok_runs = df[df["status"].isin(["success", "partial"])]
    now = pd.Timestamp.now(tz="UTC")
    last = df.iloc[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Last run", last["status"], f"{last['started_at']:%Y-%m-%d %H:%M} UTC",
                delta_color="off")
    col3.metric("Success rate (last 50)", f"{(df['status'] == 'success').mean():.0%}")
    if ok_runs.empty:
        col2.metric("Data freshness", "—")
        st.error("No successful runs yet.")
    else:
        minutes = int((now - ok_runs["finished_at"].iloc[0]).total_seconds() // 60)
        col2.metric("Data freshness", f"{minutes} min ago")
        if minutes > FRESHNESS_LIMIT_MIN:
            st.warning(f"No successful ETL run for over {FRESHNESS_LIMIT_MIN} minutes.")

    st.subheader("Recent runs")
    table = df[["id", "started_at", "duration_s", "status", "cities_ok", "cities_failed",
                "rows_upserted", "error"]]
    st.dataframe(
        table.style.map(lambda s: STATUS_COLORS.get(s, ""), subset=["status"]),
        hide_index=True,
    )


st.set_page_config(page_title="Weather Pipeline", page_icon="🌦️", layout="wide")
navigation = st.navigation(
    [
        st.Page(overview_page, title="Overview", icon="🌍"),
        st.Page(trends_page, title="Trends", icon="📈"),
        st.Page(pipeline_page, title="Pipeline health", icon="🛠️"),
    ]
)
navigation.run()
