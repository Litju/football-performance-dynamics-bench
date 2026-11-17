"""Render publication figures from RES440 public aggregates (requires Matplotlib)."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OUT = Path(__file__).resolve().parents[1] / "docs/res440"
DATA = json.loads((OUT / "findings.json").read_text())
REGIMES = ("history_only", "future_ball", "future_opponent_plus_ball")
REPS = ("absolute_xy", "origin_relative_displacement")
COLORS = ("#0072B2", "#D55E00")
MARKERS = ("o", "s", "^", "D")
MATCHES = [d["match"] for d in DATA["denominators"]]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.dpi": 300,
    }
)


def save(fig, name):
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(
            OUT / f"{name}.{suffix}", bbox_inches="tight", metadata={"Creator": "FPD Bench RES-440"}
        )
    svg = OUT / f"{name}.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)


fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout="constrained")
for ax, metric, title in zip(
    axes, ("ade_m", "fde_m", "xy_rmse_m"), ("ADE", "FDE at 3 s", "XY coordinate RMSE"), strict=True
):
    ax.axvspan(0.5, 2.45, color="#eeeeee", zorder=0)
    for j, rep in enumerate(REPS):
        x = [i + (j - 0.5) * 0.14 for i in range(3)]
        values = [
            next(
                r[metric]
                for r in DATA["summary"]
                if r["regime"] == regime and r["representation"] == rep
            )
            for regime in REGIMES
        ]
        ax.plot(x, values, color=COLORS[j], lw=2, marker="_", ms=16)
        for k, match in enumerate(MATCHES):
            y = [
                next(
                    r[metric]
                    for r in DATA["match_means"]
                    if r["match"] == match and r["regime"] == regime and r["representation"] == rep
                )
                for regime in REGIMES
            ]
            ax.scatter(
                x,
                y,
                marker=MARKERS[k],
                s=24,
                facecolors="none",
                edgecolors=COLORS[j],
                alpha=0.8,
                zorder=3,
            )
    ax.set(
        xticks=range(3),
        xticklabels=["History\nonly", "Future\nball", "Future opponents\n+ ball"],
        ylabel="Error (m; lower is better)",
        title=title,
        ylim=(0, None),
    )
    ax.grid(axis="y", alpha=0.2)
fig.legend(
    handles=[
        Line2D([], [], color=c, lw=2, label=label)
        for c, label in zip(COLORS, ("Absolute XY", "Origin-relative displacement"), strict=True)
    ],
    loc="outside upper center",
    ncol=2,
    frameon=False,
)
fig.supxlabel(
    "Open points: four seed-averaged matches; lines: equal-match means.\n"
    "Shading: realized-future conditional prediction.",
    fontsize=9,
)
save(fig, "errors")

fig, ax = plt.subplots(figsize=(8, 4.3), layout="constrained")
labels = []
for i, row in enumerate(DATA["contrasts"]):
    color = COLORS[REPS.index(row["representation"])]
    labels.append(
        row["contrast"] + " / " + ("XY" if row["representation"] == REPS[0] else "Displacement")
    )
    ax.plot([row["min_m"], row["max_m"]], [i, i], color=color, alpha=0.4, lw=3)
    for k, match in enumerate(MATCHES):
        ax.scatter(row[match], i + (k - 1.5) * 0.07, color=color, marker=MARKERS[k], s=45, zorder=3)
    ax.scatter(row["mean_m"], i, color="black", marker="|", s=220, zorder=4)
ax.set(
    yticks=range(4),
    yticklabels=labels,
    xlabel="Paired ADE reduction (m; positive = lower error with added context)",
    xlim=(0, 0.33),
    title="All four matches have positive C1 and C2 differences",
)
ax.invert_yaxis()
ax.grid(axis="x", alpha=0.2)
fig.legend(
    handles=[
        Line2D([], [], color="black", marker=m, ls="", label=match)
        for m, match in zip(MARKERS, MATCHES, strict=True)
    ]
    + [Line2D([], [], color="black", marker="|", ls="", ms=12, label="Equal-match mean")],
    loc="outside lower center",
    ncol=3,
    frameon=False,
    fontsize=9,
)
save(fig, "contrasts")

fig, axes = plt.subplots(1, 2, figsize=(9, 4), layout="constrained", sharey=True)
for ax, rep, title in zip(axes, REPS, ("Absolute XY", "Origin-relative displacement"), strict=True):
    for regime, color, marker, label in zip(
        REGIMES,
        ("#222222", "#0072B2", "#D55E00"),
        ("o", "s", "^"),
        ("History only", "Future ball", "Future opponents + ball"),
        strict=True,
    ):
        values = [
            next(
                r["ade_m"]
                for r in DATA["strata"]
                if r["stratum"] == s and r["regime"] == regime and r["representation"] == rep
            )
            for s in ("early", "middle", "late")
        ]
        ax.plot(range(3), values, color=color, marker=marker, label=label)
    ax.set(
        title=title,
        xticks=range(3),
        xticklabels=["0.2–1.0", "1.2–2.0", "2.2–3.0"],
        xlabel="Forecast interval (s)",
        ylim=(0, None),
    )
    ax.grid(axis="y", alpha=0.2)
axes[0].set_ylabel("ADE (m; four-match mean)")
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="outside upper center", ncol=3, frameon=False)
save(fig, "horizon")
