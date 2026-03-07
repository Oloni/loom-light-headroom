"""
Connection screening analysis engine.
Ported from connection_screen.py by Deepanshu and Leonie.
"""
import numpy as np
import pandas as pd


def uk_solar_profile():
    """Return 12x24 array of capacity factors [month][hour], 0-indexed month (0=Jan)."""
    monthly_peak = [0.08, 0.15, 0.30, 0.45, 0.55, 0.60, 0.58, 0.50, 0.38, 0.22, 0.10, 0.06]
    day_lengths = [8, 9.5, 11.5, 13.5, 15, 16, 15.5, 14, 12.5, 10.5, 9, 7.5]
    profile = np.zeros((12, 24))
    for m in range(12):
        half_day = day_lengths[m] / 2
        sunrise = 12 - half_day
        sunset = 12 + half_day
        for h in range(24):
            if sunrise <= h <= sunset:
                fraction_of_day = (h - sunrise) / (sunset - sunrise)
                profile[m, h] = monthly_peak[m] * np.sin(np.pi * fraction_of_day)
    return profile


def annual_solar_generation_mw(capacity_mw):
    """Return 8760-length array of hourly generation in MW."""
    profile = uk_solar_profile()
    generation = np.zeros(8760)
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    hour_idx = 0
    for m in range(12):
        for d in range(days_in_month[m]):
            for h in range(24):
                generation[hour_idx] = capacity_mw * profile[m, h]
                hour_idx += 1
    return generation


def synthesise_demand_profile(summer_midday_mw, winter_evening_mw, peak_mw, median_mw):
    """Create a synthetic 8760-hour demand profile from summary statistics."""
    demand = np.zeros(8760)
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    seasonal = {
        0: 1.25, 1: 1.20, 2: 1.05, 3: 0.90, 4: 0.80, 5: 0.75,
        6: 0.72, 7: 0.75, 8: 0.85, 9: 1.00, 10: 1.15, 11: 1.25
    }

    weekday_shape = np.array([
        0.45, 0.40, 0.38, 0.36, 0.37, 0.42,
        0.55, 0.72, 0.88, 0.95, 0.92, 0.90,
        0.88, 0.90, 0.88, 0.85, 0.90, 1.00,
        0.95, 0.85, 0.75, 0.65, 0.55, 0.50
    ])

    weekend_shape = np.array([
        0.40, 0.35, 0.32, 0.30, 0.30, 0.32,
        0.38, 0.45, 0.55, 0.62, 0.65, 0.65,
        0.63, 0.62, 0.60, 0.58, 0.62, 0.70,
        0.68, 0.62, 0.55, 0.50, 0.45, 0.42
    ])

    summer_months = [5, 6, 7]
    winter_months = [0, 1, 10, 11]

    raw_summer_midday = np.mean([seasonal[m] * weekday_shape[h]
                                  for m in summer_months for h in range(10, 15)])
    raw_winter_evening = np.mean([seasonal[m] * weekday_shape[h]
                                   for m in winter_months for h in range(16, 20)])

    base_from_summer = summer_midday_mw / raw_summer_midday if raw_summer_midday > 0 else median_mw
    base_from_winter = winter_evening_mw / raw_winter_evening if raw_winter_evening > 0 else median_mw
    base_level = (base_from_summer + base_from_winter) / 2

    rng = np.random.RandomState(42)

    hour_idx = 0
    day_of_year = 0
    for m in range(12):
        for d in range(days_in_month[m]):
            dow = day_of_year % 7
            is_weekend = dow >= 5
            shape = weekend_shape if is_weekend else weekday_shape
            for h in range(24):
                base = base_level * seasonal[m] * shape[h]
                noise = rng.normal(0, base * 0.10)
                demand[hour_idx] = max(0.05 * base_level, base + noise)
                hour_idx += 1
            day_of_year += 1

    return demand


def _verdict(published_gen_headroom, summer_midday, proposed_mw):
    """Generate a plain-English verdict."""
    gh = published_gen_headroom
    sd = summer_midday
    if proposed_mw <= gh:
        return (f"Within published headroom ({gh:.1f} MW). "
                f"Likely straightforward connection.")
    elif proposed_mw <= sd:
        return (f"Exceeds published headroom ({gh:.1f} MW) but within summer midday demand "
                f"({sd:.1f} MW). Generation would be locally absorbed during peak output hours. "
                f"Published headroom may be overly conservative for solar.")
    else:
        return (f"Exceeds both published headroom ({gh:.1f} MW) and typical summer demand "
                f"({sd:.1f} MW). Expect material reverse flow and possible curtailment.")


def screen_connection(substation_row, proposed_capacity_mw, technology='solar'):
    """
    Run connection screening for a proposed generation connection.
    substation_row: dict-like with keys:
        summer_midday_p50_mw, winter_evening_p50_mw, peak_demand_mw,
        median_demand_mw, published_gen_headroom_mw, name
    """
    s = substation_row
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    solar_gen = annual_solar_generation_mw(proposed_capacity_mw)
    demand = synthesise_demand_profile(
        s['summer_midday_p50_mw'],
        s['winter_evening_p50_mw'],
        s['peak_demand_mw'],
        s['median_demand_mw']
    )

    net_flow = demand - solar_gen
    export_limit_mw = s['published_gen_headroom_mw']

    hours_reverse = int(np.sum(net_flow < 0))
    export = np.maximum(-net_flow, 0)
    curtailed = np.maximum(export - export_limit_mw, 0)

    total_gen_mwh = float(np.sum(solar_gen))
    curtailed_mwh = float(np.sum(curtailed))
    curtailment_pct = (curtailed_mwh / total_gen_mwh * 100) if total_gen_mwh > 0 else 0
    capacity_factor = total_gen_mwh / (proposed_capacity_mw * 8760) * 100 if proposed_capacity_mw > 0 else 0

    # Monthly summary
    monthly = []
    idx = 0
    for m in range(12):
        hours = days_in_month[m] * 24
        sl = slice(idx, idx + hours)
        monthly.append({
            'month': month_names[m],
            'avg_demand_mw': float(np.mean(demand[sl])),
            'avg_generation_mw': float(np.mean(solar_gen[sl])),
            'avg_net_flow_mw': float(np.mean(net_flow[sl])),
            'hours_reverse': int(np.sum(net_flow[sl] < 0)),
            'curtailed_mwh': float(np.sum(curtailed[sl])),
            'generation_mwh': float(np.sum(solar_gen[sl])),
        })
        idx += hours

    # Seasonal hourly averages
    seasons = {
        'Summer (Jun–Aug)': [5, 6, 7],
        'Winter (Dec–Feb)': [11, 0, 1],
        'Spring (Mar–May)': [2, 3, 4],
        'Autumn (Sep–Nov)': [8, 9, 10],
    }

    hourly_by_season = {}
    for season_name, months in seasons.items():
        demand_by_hour = np.zeros(24)
        gen_by_hour = np.zeros(24)
        counts = np.zeros(24)
        idx = 0
        for m_idx in range(12):
            for d in range(days_in_month[m_idx]):
                for h in range(24):
                    if m_idx in months:
                        demand_by_hour[h] += demand[idx]
                        gen_by_hour[h] += solar_gen[idx]
                        counts[h] += 1
                    idx += 1
        counts = np.maximum(counts, 1)
        hourly_by_season[season_name] = {
            'demand': (demand_by_hour / counts).tolist(),
            'generation': (gen_by_hour / counts).tolist(),
            'net': ((demand_by_hour - gen_by_hour) / counts).tolist(),
        }

    gh = s['published_gen_headroom_mw']
    sd = s['summer_midday_p50_mw']

    headroom_comp = {
        'published_gen_headroom_mw': gh,
        'proposed_capacity_mw': proposed_capacity_mw,
        'summer_midday_demand_mw': sd,
        'winter_evening_demand_mw': s['winter_evening_p50_mw'],
        'effective_summer_headroom_mw': sd,
        'headroom_ratio': sd / gh if gh > 0 else None,
        'verdict': _verdict(gh, sd, proposed_capacity_mw),
    }

    return {
        'substation': s['name'],
        'proposed_capacity_mw': proposed_capacity_mw,
        'technology': technology,
        'hours_reverse_flow': hours_reverse,
        'hours_reverse_pct': hours_reverse / 8760 * 100,
        'curtailment_pct': curtailment_pct,
        'curtailed_mwh': curtailed_mwh,
        'total_generation_mwh': total_gen_mwh,
        'capacity_factor_pct': capacity_factor,
        'net_revenue_impact_pct': 100 - curtailment_pct,
        'headroom_comparison': headroom_comp,
        'monthly_summary': monthly,
        'hourly_by_season': hourly_by_season,
    }
