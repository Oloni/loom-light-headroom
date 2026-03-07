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
# Load data
# ---------------------------------------------------------------------------
@st.cache_data
def load_substations():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    df = pd.read_csv(os.path.join(base_dir, "data", "substations.csv"))
    # Approximate peak and median demand (not in the map data, but needed by the model)
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

selected_name = st.sidebar.selectbox(
    "Select substation",
    substation_names,
    index=0,
)

capacity_mw = st.sidebar.number_input(
    "Proposed solar capacity (MW)",
    min_value=0.5,
    max_value=50.0,
    value=8.0,
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
# Main content — only show after button press
# ---------------------------------------------------------------------------
if not run_button and "result" not in st.session_state:
    # Landing state
    st.markdown(
        """
        ## Connection Screening Tool

        Select a substation and proposed solar capacity from the sidebar, then press **Run screening**
        to generate a connection viability assessment.

        This tool compares published generation headroom figures against actual measured
        transformer flows to give a more realistic picture of available capacity for solar connections.
        """
    )
    st.stop()

# Run analysis
if run_button:
    with st.spinner("Running screening analysis..."):
        result = screen_connection(sub_row.to_dict(), capacity_mw)
        st.session_state["result"] = result

result = st.session_state["result"]
hc = result["headroom_comparison"]
monthly = result["monthly_summary"]
hourly = result["hourly_by_season"]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(f"## Connection Screening Report")
st.markdown(f"**{result['substation']}** — {result['proposed_capacity_mw']:.0f} MW {result['technology']}")

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Key metrics
# ---------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Reverse flow hours", f"{result['hours_reverse_flow']:,} hrs/yr",
          f"{result['hours_reverse_pct']:.1f}% of the year")
c2.metric("Estimated curtailment", f"{result['curtailment_pct']:.1f}%",
          f"{result['curtailed_mwh']:,.0f} of {result['total_generation_mwh']:,.0f} MWh")
c3.metric("Published gen headroom", f"{hc['published_gen_headroom_mw']:.1f} MW",
          "NGED network opportunity map")
c4.metric("Summer midday demand", f"{hc['summer_midday_demand_mw']:.1f} MW",
          "Local load absorbing generation")

# ---------------------------------------------------------------------------
# Headroom comparison bars
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Charts — 2x2 grid
# ---------------------------------------------------------------------------
st.markdown("### Seasonal profiles and monthly breakdown")

col_left, col_right = st.columns(2)

hours_labels = [f"{h}:00" for h in range(24)]

# Summer profile
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
        xaxis=dict(gridcolor="#f0f0f0"), yaxis=dict(gridcolor="#f0f0f0", rangemode="tozero"),
    )
    st.plotly_chart(fig_summer, use_container_width=True)

# Winter profile
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
        xaxis=dict(gridcolor="#f0f0f0"), yaxis=dict(gridcolor="#f0f0f0", rangemode="tozero"),
    )
    st.plotly_chart(fig_winter, use_container_width=True)

col_left2, col_right2 = st.columns(2)

months = [m["month"] for m in monthly]

# Monthly generation + curtailment
with col_left2:
    delivered = [m["generation_mwh"] - m["curtailed_mwh"] for m in monthly]
    curtailed_vals = [m["curtailed_mwh"] for m in monthly]

    fig_monthly = go.Figure()
    fig_monthly.add_trace(go.Bar(
        x=months, y=delivered, name="Delivered",
        marker_color="#27ae60",
    ))
    fig_monthly.add_trace(go.Bar(
        x=months, y=curtailed_vals, name="Curtailed",
        marker_color="#c0392b",
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

# Monthly reverse flow hours
with col_right2:
    reverse_hours = [m["hours_reverse"] for m in monthly]

    fig_reverse = go.Figure()
    fig_reverse.add_trace(go.Bar(
        x=months, y=reverse_hours,
        marker_color="#e74c3c",
        showlegend=False,
    ))
    fig_reverse.update_layout(
        title="Monthly reverse flow hours",
        yaxis_title="Hours", height=320,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#f0f0f0"), yaxis=dict(gridcolor="#f0f0f0", rangemode="tozero"),
    )
    st.plotly_chart(fig_reverse, use_container_width=True)

# ---------------------------------------------------------------------------
# Methodology
# ---------------------------------------------------------------------------
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
