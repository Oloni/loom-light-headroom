"""
Loom Light — Connection Screening Tool
Streamlit app for probabilistic hosting capacity analysis.
"""
import streamlit as st
import pandas as pd
import numpy as np
import os
import plotly.graph_objects as go
from analysis import screen_connection

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Connection Screening — Loom Light",
    page_icon="⚡",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def check_password():
    """Gate access with a shared password stored in Streamlit secrets."""

    if "authenticated" in st.session_state and st.session_state["authenticated"]:
        return True

    st.markdown(
        """
        <div style="text-align: center; margin-top: 4rem; margin-bottom: 2rem;">
            <span style="font-family: 'Palatino Linotype', Palatino, serif;
                         font-size: 1.3rem; letter-spacing: 0.25em; text-transform: uppercase;">
                LOOM LIGHT
            </span>
            <div style="font-size: 0.85rem; color: #6b6560; margin-top: 0.4rem;">
                Connection Screening Tool — Early Access
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_l, col_m, col_r = st.columns([1, 1.5, 1])
    with col_m:
        name = st.text_input("Your name")
        email = st.text_input("Email address")
        password = st.text_input("Access code", type="password",
                                 help="Enter the access code from your invitation email.")
        submit = st.button("Sign in", type="primary", use_container_width=True)

    if submit:
        correct = st.secrets.get("access_code", "")
        if password == correct and correct != "":
            st.session_state["authenticated"] = True
            st.session_state["user_name"] = name
            st.session_state["user_email"] = email
            st.rerun()
        else:
            st.error("Incorrect access code. Please check your invitation email.")

    return False


if not check_password():
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
@st.cache_data
def load_substations():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    df = pd.read_csv(os.path.join(base_dir, "data", "substations.csv"))
    df["peak_demand_mw"] = df["winter_evening_p50_mw"] * 1.2
    df["median_demand_mw"] = (df["summer_midday_p50_mw"] + df["winter_evening_p50_mw"]) / 2
    return df


substations = load_substations()

# ---------------------------------------------------------------------------
# Sidebar — inputs
# ---------------------------------------------------------------------------
st.sidebar.markdown(
    """
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <span style="font-family: 'Palatino Linotype', Palatino, serif;
                     font-size: 1.1rem; letter-spacing: 0.2em; text-transform: uppercase;">
            LOOM LIGHT
        </span>
        <div style="font-size: 0.78rem; color: #6b6560; margin-top: 0.25rem;">
            Connection Screening Tool
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Fuzzy search substation selector
search_query = st.sidebar.text_input(
    "Search substation",
    placeholder="Type to search (e.g. Calverton, Leicester...)",
)

# Filter substations based on search
if search_query:
    query_lower = search_query.lower().strip()
    filtered = substations[
        substations["name"].str.lower().str.contains(query_lower, na=False)
    ]
else:
    filtered = substations

substation_names = sorted(filtered["name"].tolist())

if len(substation_names) == 0:
    st.sidebar.warning("No substations match your search.")
    st.stop()

# Default to Quorn — high ratio (0.90), 11.6 MW headroom, 10.4 MW summer demand
# Great demo: a 12 MW solar farm looks risky on paper but screening shows it works
default_sub = "Quorn"
default_idx = 0
if default_sub in substation_names:
    default_idx = substation_names.index(default_sub)

selected_name = st.sidebar.selectbox(
    "Select substation",
    substation_names,
    index=default_idx,
)

capacity_mw = st.sidebar.number_input(
    "Proposed solar capacity (MW)",
    min_value=0.5,
    max_value=50.0,
    value=12.0,
    step=0.5,
)

run_button = st.sidebar.button("Run screening", type="primary", use_container_width=True)

# Show selected substation summary in sidebar
sub_row = substations[substations["name"] == selected_name].iloc[0]
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Published gen headroom:** {sub_row['published_gen_headroom_mw']:.1f} MW")
st.sidebar.markdown(f"**Summer midday demand:** {sub_row['summer_midday_p50_mw']:.1f} MW")
st.sidebar.markdown(f"**Winter evening demand:** {sub_row['winter_evening_p50_mw']:.1f} MW")

st.sidebar.markdown(
    """
    <div style="margin-top: 2rem; font-size: 0.75rem; color: #9a948d; line-height: 1.5;">
        Data: NGED Open Data Portal<br>
        East Midlands 11kV primaries<br>
        185 substations
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Auto-run on first load with default substation
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    result = screen_connection(sub_row.to_dict(), capacity_mw)
    st.session_state["result"] = result
    st.session_state["result_name"] = selected_name
    st.session_state["result_capacity"] = capacity_mw

if run_button:
    with st.spinner("Running screening analysis..."):
        result = screen_connection(sub_row.to_dict(), capacity_mw)
        st.session_state["result"] = result
        st.session_state["result_name"] = selected_name
        st.session_state["result_capacity"] = capacity_mw

result = st.session_state["result"]
hc = result["headroom_comparison"]
monthly = result["monthly_summary"]
hourly = result["hourly_by_season"]

# ---------------------------------------------------------------------------
# Tabs: Report | Map
# ---------------------------------------------------------------------------
tab_report, tab_map = st.tabs(["📊 Screening Report", "🗺️ Substation Map"])

# ============================= REPORT TAB ================================
with tab_report:

    # Header
    st.markdown(f"## Connection Screening Report")
    st.markdown(
        f"**{result['substation']}** — {result['proposed_capacity_mw']:.0f} MW {result['technology']}"
    )

    # --- Headroom gap callout ---
    gap_mw = hc["summer_midday_demand_mw"] - hc["published_gen_headroom_mw"]
    if gap_mw > 0:
        gap_direction = "more"
        gap_color = "#27ae60"
    else:
        gap_direction = "less"
        gap_color = "#e67e22"
        gap_mw = abs(gap_mw)

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #0a0f1a 0%, #1a2a3a 100%);
                    border-radius: 10px; padding: 18px 24px; margin-bottom: 20px; color: white;">
            <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.1em;
                        color: rgba(255,255,255,0.6); margin-bottom: 6px;">
                What the published figure misses
            </div>
            <div style="font-size: 17px; line-height: 1.5;">
                NGED publishes <b>{hc['published_gen_headroom_mw']:.1f} MW</b> of generation headroom.
                But actual summer midday demand is <b>{hc['summer_midday_demand_mw']:.1f} MW</b> —
                <span style="color: {gap_color}; font-weight: 700;">{gap_mw:.1f} MW {gap_direction}</span>
                than the published figure suggests is available.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Verdict
    if result["curtailment_pct"] < 1:
        verdict_color = "#27ae60"
        verdict_label = "LOW RISK"
    elif result["curtailment_pct"] < 5:
        verdict_color = "#e67e22"
        verdict_label = "MODERATE"
    else:
        verdict_color = "#c0392b"
        verdict_label = "HIGH CURTAILMENT RISK"

    st.markdown(
        f"""
        <div style="background: white; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px;
                    border-left: 5px solid {verdict_color}; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
            <div style="font-size: 13px; font-weight: 700; color: {verdict_color};
                        letter-spacing: 0.5px;">{verdict_label}</div>
            <div style="font-size: 15px; margin-top: 8px; line-height: 1.5; color: #333;">
                {hc['verdict']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Key metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reverse flow hours", f"{result['hours_reverse_flow']:,} hrs/yr",
              f"{result['hours_reverse_pct']:.1f}% of the year")
    c2.metric("Estimated curtailment", f"{result['curtailment_pct']:.1f}%",
              f"{result['curtailed_mwh']:,.0f} of {result['total_generation_mwh']:,.0f} MWh")
    c3.metric("Published gen headroom", f"{hc['published_gen_headroom_mw']:.1f} MW",
              "NGED network opportunity map")
    c4.metric("Summer midday demand", f"{hc['summer_midday_demand_mw']:.1f} MW",
              "Local load absorbing generation")

    # Headroom comparison bars
    st.markdown("### Headroom comparison")

    bar_labels = ["Published gen headroom", "Summer midday demand",
                  "Your proposed connection", "Winter evening demand"]
    bar_values = [hc["published_gen_headroom_mw"], hc["summer_midday_demand_mw"],
                  result["proposed_capacity_mw"], hc["winter_evening_demand_mw"]]
    bar_colors = ["#c0392b", "#3498db", "#2c3e50", "#7f8c8d"]

    fig_bars = go.Figure()
    fig_bars.add_trace(go.Bar(
        y=bar_labels[::-1],
        x=bar_values[::-1],
        orientation="h",
        marker_color=bar_colors[::-1],
        text=[f"{v:.1f} MW" for v in bar_values[::-1]],
        textposition="auto",
        textfont=dict(color="white", size=13),
    ))
    fig_bars.update_layout(
        height=220,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="MW",
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#f0f0f0"),
        yaxis=dict(tickfont=dict(size=13)),
    )
    st.plotly_chart(fig_bars, use_container_width=True)

    # Charts — 2x2 grid
    st.markdown("### Seasonal profiles and monthly breakdown")

    col_left, col_right = st.columns(2)
    hours_labels = [f"{h}:00" for h in range(24)]

    with col_left:
        season_key = "Summer (Jun–Aug)"
        fig_summer = go.Figure()
        fig_summer.add_trace(go.Scatter(
            x=hours_labels, y=hourly[season_key]["demand"],
            name="Demand", fill="tozeroy",
            line=dict(color="#3498db"), fillcolor="rgba(52,152,219,0.1)",
        ))
        fig_summer.add_trace(go.Scatter(
            x=hours_labels, y=hourly[season_key]["generation"],
            name="Solar generation", fill="tozeroy",
            line=dict(color="#f39c12"), fillcolor="rgba(243,156,18,0.1)",
        ))
        fig_summer.update_layout(
            title="Summer daily profile — demand vs generation",
            yaxis_title="MW", height=320,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0.5, xanchor="center"),
            plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#f0f0f0"),
            yaxis=dict(gridcolor="#f0f0f0", rangemode="tozero"),
        )
        st.plotly_chart(fig_summer, use_container_width=True)

    with col_right:
        season_key = "Winter (Dec–Feb)"
        fig_winter = go.Figure()
        fig_winter.add_trace(go.Scatter(
            x=hours_labels, y=hourly[season_key]["demand"],
            name="Demand", fill="tozeroy",
            line=dict(color="#3498db"), fillcolor="rgba(52,152,219,0.1)",
        ))
        fig_winter.add_trace(go.Scatter(
            x=hours_labels, y=hourly[season_key]["generation"],
            name="Solar generation", fill="tozeroy",
            line=dict(color="#f39c12"), fillcolor="rgba(243,156,18,0.1)",
        ))
        fig_winter.update_layout(
            title="Winter daily profile — demand vs generation",
            yaxis_title="MW", height=320,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0.5, xanchor="center"),
            plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#f0f0f0"),
            yaxis=dict(gridcolor="#f0f0f0", rangemode="tozero"),
        )
        st.plotly_chart(fig_winter, use_container_width=True)

    col_left2, col_right2 = st.columns(2)
    months = [m["month"] for m in monthly]

    with col_left2:
        delivered = [m["generation_mwh"] - m["curtailed_mwh"] for m in monthly]
        curtailed_vals = [m["curtailed_mwh"] for m in monthly]
        fig_monthly = go.Figure()
        fig_monthly.add_trace(go.Bar(
            x=months, y=delivered, name="Delivered", marker_color="#27ae60",
        ))
        fig_monthly.add_trace(go.Bar(
            x=months, y=curtailed_vals, name="Curtailed", marker_color="#c0392b",
        ))
        fig_monthly.update_layout(
            title="Monthly generation and curtailment",
            yaxis_title="MWh", barmode="stack", height=320,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0.5, xanchor="center"),
            plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#f0f0f0"), yaxis=dict(gridcolor="#f0f0f0"),
        )
        st.plotly_chart(fig_monthly, use_container_width=True)

    with col_right2:
        reverse_hours = [m["hours_reverse"] for m in monthly]
        fig_reverse = go.Figure()
        fig_reverse.add_trace(go.Bar(
            x=months, y=reverse_hours, marker_color="#e74c3c", showlegend=False,
        ))
        fig_reverse.update_layout(
            title="Monthly reverse flow hours",
            yaxis_title="Hours", height=320,
            margin=dict(l=10, r=10, t=40, b=10),
            plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="#f0f0f0"),
            yaxis=dict(gridcolor="#f0f0f0", rangemode="tozero"),
        )
        st.plotly_chart(fig_reverse, use_container_width=True)

    # Methodology
    with st.expander("Methodology"):
        st.markdown(
            """
            Demand profiles are derived from NGED's half-hourly transformer flow data for
            East Midlands primary substations. Solar generation is modelled using a standard
            UK irradiance profile scaled to the proposed connection capacity.

            Reverse flow occurs when solar output exceeds local demand. Curtailment is
            estimated as the energy that would need to be curtailed when net export exceeds
            the published generation headroom.

            **This is an indicative screening tool** — a formal connection application requires
            detailed network studies by the DNO including fault level, protection coordination,
            voltage rise, and harmonic assessments.

            **Data:** NGED Open Data Portal (public)
            """
        )


# ============================= MAP TAB ===================================
with tab_map:
    st.markdown("## East Midlands — Generation Headroom vs Measured Demand")
    st.markdown(
        "Each dot is an 11kV primary substation. Colour shows how summer midday demand "
        "compares to published generation headroom. Click a substation to see details."
    )

    # Categorise substations for the map
    map_df = substations.copy()
    map_df["gap"] = map_df["summer_midday_p50_mw"] - map_df["published_gen_headroom_mw"]
    map_df["ratio"] = map_df["summer_midday_p50_mw"] / map_df["published_gen_headroom_mw"]

    # Colour logic matching the original Folium map
    def get_color(row):
        if row["published_gen_headroom_mw"] < 5 and row["summer_midday_p50_mw"] > 5:
            return "#c0392b"  # Misleading
        elif row["summer_midday_p50_mw"] > row["published_gen_headroom_mw"]:
            return "#e67e22"  # Conservative
        elif row["ratio"] >= 0.7:
            return "#f39c12"  # Tight
        else:
            return "#3498db"  # Normal

    def get_category(row):
        if row["published_gen_headroom_mw"] < 5 and row["summer_midday_p50_mw"] > 5:
            return "Misleading headroom"
        elif row["summer_midday_p50_mw"] > row["published_gen_headroom_mw"]:
            return "Conservative headroom"
        elif row["ratio"] >= 0.7:
            return "Tight — demand close to headroom"
        else:
            return "Headroom looks reasonable"

    map_df["color"] = map_df.apply(get_color, axis=1)
    map_df["map_category"] = map_df.apply(get_category, axis=1)
    map_df["size"] = map_df["summer_midday_p50_mw"].clip(lower=1) * 1.5

    # Highlight selected substation
    selected_lat = sub_row["latitude"]
    selected_lon = sub_row["longitude"]

    # Build Plotly scattermapbox
    fig_map = go.Figure()

    # All substations
    for cat, color in [
        ("Headroom looks reasonable", "#3498db"),
        ("Tight — demand close to headroom", "#f39c12"),
        ("Conservative headroom", "#e67e22"),
        ("Misleading headroom", "#c0392b"),
    ]:
        cat_df = map_df[map_df["map_category"] == cat]
        if len(cat_df) == 0:
            continue
        fig_map.add_trace(go.Scattermapbox(
            lat=cat_df["latitude"],
            lon=cat_df["longitude"],
            mode="markers",
            marker=dict(
                size=cat_df["size"],
                color=color,
                opacity=0.75,
            ),
            text=cat_df.apply(
                lambda r: (
                    f"<b>{r['name']}</b><br>"
                    f"Published headroom: {r['published_gen_headroom_mw']:.1f} MW<br>"
                    f"Summer midday demand: {r['summer_midday_p50_mw']:.1f} MW<br>"
                    f"Winter evening demand: {r['winter_evening_p50_mw']:.1f} MW<br>"
                    f"Demand/headroom ratio: {r['ratio']:.1f}x"
                ),
                axis=1,
            ),
            hoverinfo="text",
            name=cat,
        ))

    # Selected substation marker
    fig_map.add_trace(go.Scattermapbox(
        lat=[selected_lat],
        lon=[selected_lon],
        mode="markers",
        marker=dict(size=18, color="#c45d2c", symbol="circle",
                    opacity=1.0),
        text=[f"<b>SELECTED: {selected_name}</b>"],
        hoverinfo="text",
        name="Selected",
        showlegend=False,
    ))

    fig_map.update_layout(
        mapbox=dict(
            style="carto-positron",
            center=dict(lat=52.73, lon=-1.14),
            zoom=7.5,
        ),
        height=600,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            yanchor="top", y=0.98, xanchor="left", x=0.02,
            bgcolor="rgba(255,255,255,0.9)",
            font=dict(size=12),
        ),
    )
    st.plotly_chart(fig_map, use_container_width=True)

    st.caption("Dot size proportional to summer midday demand. Orange highlight = selected substation.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    f"""
    <div style="text-align: center; font-size: 12px; color: #999;">
        Loom Light · Data: NGED Open Data Portal · Generated {pd.Timestamp.now().strftime('%d %B %Y')}
    </div>
    """,
    unsafe_allow_html=True,
)
