"""Audit whether short forcing gaps hide difficult geomagnetic storms."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from multi_storm_transfer_lab import (
    PopulationData,
    Storm,
    evaluate_model,
    fit_response_model,
    load_population,
    response_valid,
    select_storms,
)


GAP_POLICIES_HOURS = (0, 1, 3, 6, 24)


def interpolate_short_gaps(
    values: torch.Tensor, valid: torch.Tensor, maximum_gap_hours: int
) -> tuple[torch.Tensor, torch.Tensor, list[dict]]:
    if maximum_gap_hours < 0:
        raise ValueError("maximum_gap_hours must be nonnegative")
    result = values.clone()
    result_valid = valid.clone()
    filled = []
    mask = valid.detach().cpu().numpy().astype(bool)
    padded = np.concatenate(([True], mask, [True]))
    starts = np.flatnonzero(padded[:-1] & ~padded[1:])
    stops = np.flatnonzero(~padded[:-1] & padded[1:])
    for start, stop in zip(starts, stops):
        length = int(stop - start)
        if (
            length == 0
            or length > maximum_gap_hours
            or start == 0
            or stop >= len(values)
            or not valid[start - 1]
            or not valid[stop]
        ):
            continue
        left, right = float(values[start - 1]), float(values[stop])
        fractions = torch.arange(1, length + 1, dtype=values.dtype, device=values.device) / (length + 1)
        result[start:stop] = left + fractions * (right - left)
        result_valid[start:stop] = True
        filled.append({"start_index": int(start), "hours": length})
    return result, result_valid, filled


def fill_required_forcing(data: PopulationData, maximum_gap_hours: int) -> tuple[PopulationData, dict]:
    electric_valid = torch.isfinite(data.electric_field) & (data.electric_field < 900)
    pressure_valid = torch.isfinite(data.pressure) & (data.pressure < 90)
    electric, _, electric_gaps = interpolate_short_gaps(
        data.electric_field, electric_valid, maximum_gap_hours
    )
    pressure, _, pressure_gaps = interpolate_short_gaps(
        data.pressure, pressure_valid, maximum_gap_hours
    )
    filled = replace(data, electric_field=electric, pressure=pressure)
    return filled, {
        "maximum_gap_hours": maximum_gap_hours,
        "electric_gaps_filled": len(electric_gaps),
        "electric_hours_filled": sum(gap["hours"] for gap in electric_gaps),
        "pressure_gaps_filled": len(pressure_gaps),
        "pressure_hours_filled": sum(gap["hours"] for gap in pressure_gaps),
        "valid_required_input_rows": int(response_valid(filled).sum()),
    }


def event_subset(evaluation: dict, timestamps: set[str]) -> dict:
    rows = [row for row in evaluation["events"] if row["timestamp_utc"] in timestamps]
    return {
        "events": len(rows),
        "mean_event_rmse_nt": sum(row["rollout_rmse_nt"] for row in rows) / len(rows),
        "mean_persistence_rmse_nt": sum(row["persistence_rmse_nt"] for row in rows) / len(rows),
        "mean_tail_72h_rmse_nt": sum(row["tail_72h_rmse_nt"] for row in rows) / len(rows),
    }


def main(
    manifest_path: Path = Path("data/omni_population/manifest.json"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    original = load_population(manifest_path)
    strict_storms = [
        storm
        for storm in select_storms(original)
        if storm.complete_forcing_window and storm.timestamp.year >= 2019
    ]
    common_timestamps = {storm.timestamp.isoformat() for storm in strict_storms}
    policies = []
    for maximum_gap in GAP_POLICIES_HOURS:
        data, fill_summary = fill_required_forcing(original, maximum_gap)
        storms = [
            storm
            for storm in select_storms(data)
            if storm.complete_forcing_window and storm.timestamp.year >= 2019
        ]
        model = fit_response_model(data, (2010, 2018), None)
        evaluation = evaluate_model(data, storms, model)
        new_events = [
            row for row in evaluation["events"] if row["timestamp_utc"] not in common_timestamps
        ]
        policies.append(
            {
                **fill_summary,
                "eligible_test_storms": len(storms),
                "deepest_eligible_test_storm_nt": min(storm.minimum_dst_nt for storm in storms),
                "all_eligible_test": evaluation,
                "common_strict_test": event_subset(evaluation, common_timestamps),
                "newly_admitted_events": new_events,
                "newly_admitted_mean_rmse_nt": (
                    sum(row["rollout_rmse_nt"] for row in new_events) / len(new_events)
                    if new_events
                    else None
                ),
            }
        )

    report = {
        "experiment": "short forcing-gap robustness for chronological storm transfer",
        "gap_policies_hours": list(GAP_POLICIES_HOURS),
        "interpolation": "linear, interior gaps only, applied separately to electric field and pressure",
        "training_years": [2010, 2018],
        "test_years": [2019, 2025],
        "strict_common_test_storms": len(strict_storms),
        "policies": policies,
        "interpretation_boundary": (
            "interpolation sensitivity tests observation completeness; it does not validate the missing values"
        ),
    }
    (output_dir / "storm_forcing_gap_robustness.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    hours = [policy["maximum_gap_hours"] for policy in policies]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
    axes[0].plot(hours, [policy["eligible_test_storms"] for policy in policies], marker="o", color="#1565c0")
    axes[0].set(xlabel="maximum interpolated gap (hours)", ylabel="eligible test storms", title="Short gaps censor later storms")
    axes[0].grid(alpha=0.2)

    axes[1].plot(
        hours,
        [policy["common_strict_test"]["mean_event_rmse_nt"] for policy in policies],
        marker="o",
        color="#00897b",
        label="common strict 11 storms",
    )
    axes[1].plot(
        hours,
        [policy["all_eligible_test"]["mean_event_rmse_nt"] for policy in policies],
        marker="o",
        color="#d84315",
        label="all admitted storms",
    )
    axes[1].plot(
        hours,
        [policy["newly_admitted_mean_rmse_nt"] for policy in policies],
        marker="o",
        color="#7e57c2",
        label="newly admitted only",
    )
    axes[1].set(xlabel="maximum interpolated gap (hours)", ylabel="mean event RMSE (nT)", title="Performance on fixed and expanding cohorts")
    axes[1].legend(frameon=False)
    axes[1].grid(alpha=0.2)
    fig.savefig(output_dir / "storm_forcing_gap_robustness.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
