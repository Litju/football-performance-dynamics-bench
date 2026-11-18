"""Render Paper A methodological schematics from frozen public authorities (requires Matplotlib).

Every count drawn here is read from a tracked authority: the prospective protocol v2, the
experiment plan v2, the frozen final-fit checkpoint manifest and the public aggregate findings.
No source data, checkpoint, prediction or private artifact is read.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/paper-a"
TASK = ROOT / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
PROTOCOL = json.loads((TASK / "prospective_skillcorner_protocol_v2.json").read_text())
PLAN = json.loads((TASK / "empirical_experiment_plan_v2.json").read_text())
CHECKPOINTS = json.loads((TASK / "res593_checkpoint_manifest_v1.json").read_text())["checkpoints"]
FINDINGS = json.loads((ROOT / "docs/res440/findings.json").read_text())

SPLIT = PROTOCOL["scientific_state"]["split"]
ROLES = SPLIT["roles"]
REGIMES = PLAN["factorial"]["information_regimes"]
REPRESENTATIONS = PLAN["factorial"]["target_representations"]
SEEDS = PLAN["seeds"]["stochastic_seed_ids"]
FINAL_FITS = PLAN["seeds"]["final_fit_count"]
LOMO_FITS = PLAN["seeds"]["lomo_fit_count"]
PLANNED_FITS = PLAN["seeds"]["total_learned_fits"]
LOMO_FOLDS = SPLIT["lomo"]["fold_count"]
EVAL_MATCHES = ROLES["evaluation"]

assert len(CHECKPOINTS) == FINAL_FITS == len(REGIMES) * len(REPRESENTATIONS) * len(SEEDS)
assert FINAL_FITS + LOMO_FITS == PLANNED_FITS == FINAL_FITS * (LOMO_FOLDS + 1)
assert {tuple(c["train_match_ids"]) for c in CHECKPOINTS} == {tuple(ROLES["training"])}
assert {tuple(c["validation_match_ids"]) for c in CHECKPOINTS} == {tuple(ROLES["validation"])}
assert {c["fit_role"] for c in CHECKPOINTS} == {"final_train"}
assert FINDINGS["records"] == FINAL_FITS * len(EVAL_MATCHES)
assert FINDINGS["independent_units"] == len(EVAL_MATCHES)
assert [d["match"] for d in FINDINGS["denominators"]] == EVAL_MATCHES

INK = "#1a1a1a"
MUTED = "#6b6b6b"
DONE = "#d9e8f5"  # completed or recovered evidence
CONTRACT = "#ffffff"  # frozen contract or design
LIMITED = "#f6e3c9"  # partial, invalidated or scoped negative
DEFERRED = "#efefef"  # deferred, unavailable or not qualified
HISTORY = "#0072B2"
FUTURE = "#D55E00"
TARGET = "#7a7a7a"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.dpi": 300,
        "svg.hashsalt": "fpdbench-paper-a",
    }
)
# Fixed metadata keeps re-rendered files byte-identical.
METADATA = {
    "svg": {"Creator": "FPD Bench Paper A schematics", "Date": None},
    "pdf": {"Creator": "FPD Bench Paper A schematics", "CreationDate": None},
    "png": {"Creator": "FPD Bench Paper A schematics"},
}


def save(fig, name):
    OUT.mkdir(exist_ok=True)
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(
            OUT / f"{name}.{suffix}",
            bbox_inches="tight",
            metadata=METADATA[suffix],
        )
    svg = OUT / f"{name}.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)


def canvas(width, height):
    fig = plt.figure(figsize=(width, height))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100 * height / width)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, fill=CONTRACT, dashed=False, bold_first=True, size=8.2):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.25,rounding_size=0.8",
            fc=fill,
            ec=MUTED if dashed else INK,
            lw=0.9,
            ls=(0, (3, 2)) if dashed else "-",
        )
    )
    lines = text.split("\n")
    first, rest = lines[0], "\n".join(lines[1:])
    cy = y + h / 2 + 0.55 * (len(lines) - 2)
    if rest:
        ax.text(
            x + w / 2,
            cy + 0.15,
            first,
            ha="center",
            va="bottom",
            fontsize=size,
            weight="bold" if bold_first else "normal",
            color=INK,
        )
        ax.text(x + w / 2, cy - 0.25, rest, ha="center", va="top", fontsize=size - 0.8, color=INK)
    else:
        ax.text(
            x + w / 2,
            cy,
            first,
            ha="center",
            va="center",
            fontsize=size,
            weight="bold" if bold_first else "normal",
            color=INK,
        )


def arrow(ax, start, end, label=None, dashed=False, rad=0.0, label_xy=None, color=INK):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=9,
            lw=0.9,
            color=MUTED if dashed else color,
            ls=(0, (3, 2)) if dashed else "-",
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=1,
            shrinkB=1,
        )
    )
    if label:
        lx, ly = label_xy or ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        ax.text(lx, ly, label, fontsize=7, color=MUTED, ha="center", va="center", style="italic")


def legend(ax, x, y, entries):
    for i, (fill, dashed, label) in enumerate(entries):
        ax.add_patch(
            Rectangle(
                (x + i * 22, y),
                2.2,
                1.4,
                fc=fill,
                ec=MUTED if dashed else INK,
                lw=0.8,
                ls=(0, (3, 2)) if dashed else "-",
            )
        )
        ax.text(x + i * 22 + 3, y + 0.7, label, fontsize=7.5, va="center")


# Figure A: benchmark genealogy -------------------------------------------------------------
fig, ax = canvas(13, 7.4)
for x, title in (
    (1, "1  Historical reconstruction"),
    (36, "2  Scientific contracts"),
    (68, "3  Prospective SkillCorner program"),
):
    ax.text(x, 54.5, title, fontsize=10.5, weight="bold", va="center")
ax.text(1, 52.2, "recovered research objects and their status", fontsize=7.5, color=MUTED)
ax.text(36, 52.2, "public, executable methodology (unchanged)", fontsize=7.5, color=MUTED)
ax.text(
    68, 52.2, "frozen design, completed demonstration, deferred work", fontsize=7.5, color=MUTED
)

box(ax, 1, 44, 29, 5.6, "Whole-session performance state\npartial study; non-executable", LIMITED)
box(
    ax,
    1,
    36.5,
    29,
    5.6,
    "Signed tangential acceleration\ninvalidated synthetic formulation",
    LIMITED,
)
box(
    ax,
    1,
    29,
    29,
    5.6,
    "Multimodal sensor-state pilot\nsynthetic; scoped negative, no target selected",
    LIMITED,
)
box(
    ax,
    1,
    20.5,
    29,
    5.6,
    "Conditional absolute XY\none identity across measurement repair",
    DONE,
)
box(
    ax,
    1,
    11.5,
    29,
    5.6,
    "Origin-relative displacement\nnew identity: target and reference frame change",
    DONE,
)
box(
    ax,
    1,
    3,
    29,
    5.6,
    "Future response forecasting\nresearch intent; no recovered benchmark",
    DEFERRED,
    dashed=True,
)
ax.text(31, 46.8, "workload family", fontsize=6.8, color=MUTED, rotation=90, va="center")
arrow(ax, (12, 36.4), (12, 34.8), None)
ax.text(13, 35.6, "research-task lineage", fontsize=7, color=MUTED, style="italic", va="center")
arrow(ax, (12, 28.9), (12, 26.3), None, dashed=True)
ax.text(
    13,
    27.6,
    "source/question switch; no model or data edge",
    fontsize=7,
    color=MUTED,
    style="italic",
    va="center",
)
arrow(ax, (12, 20.4), (12, 17.3), None)
ax.text(
    13,
    18.85,
    "target change ⇒ new benchmark identity",
    fontsize=7,
    color=MUTED,
    style="italic",
    va="center",
)

contracts = (
    "Information boundary\nhistory H; realized future ball B and opponents O",
    "Targets and transforms\nabsolute XY; displacement p − o; inverse",
    "Evaluators\nSRE, calibration, ADE/FDE/XY RMSE, truth masks",
    "Match-level protocols\nmatch roles, LOMO, match-first aggregation",
    "Scientific locks and manifests\nhash-bound state, experiment and result",
    "Capability-bounded reproducibility\noperation-specific public/unavailable labels",
)
for i, text in enumerate(contracts):
    box(ax, 36, 44 - i * 8.2, 27, 5.6, text, CONTRACT)
arrow(ax, (30.2, 23.3), (35.8, 23.3), None)
arrow(ax, (30.2, 14.3), (35.8, 19.0), None)
ax.text(33, 25.0, "recovered", fontsize=7, color=MUTED, style="italic", ha="center")

prospective = (
    ("Protocol v1.1.0 → v2.0.0\nadditive nullable-ball successor; frozen", CONTRACT, False),
    (
        f"Research-only admission: {len(SPLIT['population_match_ids'])} matches\n"
        f"frozen {len(ROLES['training'])}/{len(ROLES['validation'])}/{len(EVAL_MATCHES)} "
        "training/validation/evaluation roles",
        DONE,
        False,
    ),
    ("Deterministic baselines\norigin persistence; constant velocity (1 s)", DONE, False),
    (
        f"{FINAL_FITS} final-fit DeepSets checkpoints\n"
        f"{len(REGIMES)} regimes × {len(REPRESENTATIONS)} targets × {len(SEEDS)} seeds; frozen",
        DONE,
        False,
    ),
    (
        f"Descriptive {len(EVAL_MATCHES)}-match evaluation\n"
        f"{FINDINGS['records']} match/seed records; research-only NOT_QUALIFIED",
        DONE,
        False,
    ),
)
for i, (text, fill, dashed) in enumerate(prospective):
    box(ax, 68, 44 - i * 8.2, 31, 5.6, text, fill, dashed)
for i in range(len(prospective) - 1):
    arrow(ax, (83.5, 43.7 - i * 8.2), (83.5, 44 - (i + 1) * 8.2 + 5.9))
box(
    ax,
    68,
    1.5,
    31,
    7.4,
    "Deferred or not qualified\n"
    f"{LOMO_FITS}-fit training LOMO ({LOMO_FOLDS} folds), not executed\n"
    f"original {PLANNED_FITS}-fit plan incomplete\n"
    "protected population qualification: NOT_QUALIFIED",
    DEFERRED,
    dashed=True,
)
arrow(ax, (63.3, 23.3), (67.7, 23.3), None)
ax.text(65.5, 25.0, "applied\nunchanged", fontsize=7, color=MUTED, style="italic", ha="center")
legend(
    ax,
    1,
    -2.2,
    (
        (DONE, False, "completed or recovered evidence"),
        (CONTRACT, False, "frozen contract or design"),
        (LIMITED, False, "partial, invalidated or negative"),
        (DEFERRED, True, "deferred, unavailable, not qualified"),
    ),
)
ax.set_ylim(-3.5, 56.5)
save(fig, "genealogy")


# Figure B: information boundary -------------------------------------------------------------
time_grid = PROTOCOL["scientific_state"]["time_grid"]
fig, axes = plt.subplots(3, 1, figsize=(11.5, 6.6), sharex=True, layout="constrained")
entities = ("Target team", "Opponent team", "Ball")
future_visible = {
    "history_only": set(),
    "future_ball": {"Ball"},
    "future_opponent_plus_ball": {"Ball", "Opponent team"},
}
titles = {
    "history_only": "history_only — ex-ante forecast: only information available at the origin",
    "future_ball": "future_ball — conditional prediction given the realized future ball trajectory",
    "future_opponent_plus_ball": (
        "future_opponent_plus_ball — conditional on realized future ball and opponent trajectories"
    ),
}
for ax, regime in zip(axes, REGIMES, strict=True):
    conditional = bool(future_visible[regime])
    ax.axvspan(0, 3, color="#fbeee6" if conditional else "#f4f4f4", zorder=0)
    for row, entity in enumerate(entities):
        y = 2 - row
        ax.barh(y, 5, left=-5, height=0.55, color=HISTORY, edgecolor=INK, lw=0.5)
        if entity == "Target team":
            ax.barh(
                y, 3, left=0, height=0.55, color="white", edgecolor=TARGET, hatch="////", lw=0.8
            )
            ax.text(
                1.5,
                y,
                "prediction target (withheld)",
                ha="center",
                va="center",
                fontsize=7.5,
                bbox={"fc": "white", "ec": "none", "pad": 1.2},
            )
        elif entity in future_visible[regime]:
            ax.barh(y, 3, left=0, height=0.55, color=FUTURE, edgecolor=INK, lw=0.5)
            ax.text(
                1.5,
                y,
                "realized future input",
                ha="center",
                va="center",
                fontsize=7.5,
                color="white",
            )
        else:
            ax.barh(y, 3, left=0, height=0.55, color="white", edgecolor="#bdbdbd", lw=0.6, ls="--")
            ax.text(1.5, y, "not available", ha="center", va="center", fontsize=7.5, color=MUTED)
    ax.axvline(0, color=INK, lw=1.1, ls="--")
    ax.set_yticks([2, 1, 0], entities)
    ax.set_ylim(-0.6, 2.6)
    ax.set_title(titles[regime], loc="left", fontsize=9, weight="bold")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.text(
        3.08,
        1,
        "CONDITIONAL\nnot an operational\nforecast" if conditional else "EX-ANTE\nforecast",
        fontsize=7.5,
        va="center",
        color=FUTURE if conditional else HISTORY,
        weight="bold",
    )
axes[-1].set_xlim(-5.2, 3.9)
axes[-1].set_xticks([-5, -4, -3, -2, -1, 0, 1, 2, 3])
axes[-1].set_xlabel(
    f"Time relative to forecast origin t (s); {time_grid['history_intervals']} history intervals "
    f"+ origin, {time_grid['future_intervals']} future steps at "
    f"{time_grid['sample_interval_seconds']} s"
)
fig.legend(
    handles=[
        Patch(fc=HISTORY, ec=INK, label="observed history through t (input)"),
        Patch(fc=FUTURE, ec=INK, label="realized future context (ex-post input)"),
        Patch(fc="white", ec=TARGET, hatch="////", label="target-team future (never an input)"),
    ],
    loc="outside lower center",
    ncol=3,
    frameon=False,
    fontsize=8,
)
save(fig, "information-boundary")


# Figure C: evaluation design ----------------------------------------------------------------
fig, ax = canvas(13, 6.6)
ax.text(1, 48.5, "Match roles (frozen hash ordering)", fontsize=10, weight="bold")
ax.text(36, 48.5, "Fit and select (no evaluation access)", fontsize=10, weight="bold")
ax.text(70, 48.5, "Evaluate and aggregate", fontsize=10, weight="bold")


def match_grid(x, y, n, fill, label, cols=4):
    for k in range(n):
        ax.add_patch(
            Rectangle(
                (x + (k % cols) * 2.6, y - (k // cols) * 2.6), 2.1, 2.1, fc=fill, ec=INK, lw=0.6
            )
        )
    ax.text(
        x + cols * 2.6 + 0.8,
        y + 1.0 - (max(n - 1, 0) // cols) * 1.3,
        label,
        fontsize=8,
        va="center",
    )


match_grid(2, 41, len(ROLES["training"]), "#cfe2f3", f"training\n{len(ROLES['training'])} matches")
match_grid(
    2, 28, len(ROLES["validation"]), "#fde9c9", f"validation\n{len(ROLES['validation'])} matches"
)
match_grid(2, 18, len(EVAL_MATCHES), "#d9ead3", f"evaluation\n{len(EVAL_MATCHES)} matches")
ax.text(
    1,
    10.5,
    "All windows and both directed scenes of a\nmatch inherit exactly one role. Evaluation\n"
    "matches never enter fitting or selection.",
    fontsize=7.5,
    color=MUTED,
    va="top",
)

box(
    ax,
    36,
    36,
    29,
    8,
    f"{FINAL_FITS} final fits on the {len(ROLES['training'])} training matches\n"
    f"{len(REGIMES)} regimes × {len(REPRESENTATIONS)} targets = "
    f"{len(REGIMES) * len(REPRESENTATIONS)} configurations\n"
    f"× seeds {', '.join(str(s) for s in SEEDS)}",
    DONE,
)
box(
    ax,
    36,
    24.5,
    29,
    8,
    f"Checkpoint selection on {len(ROLES['validation'])} validation matches\n"
    "minimum equal-match validation ADE; checks every\n100 steps, at most 5,000 steps",
    DONE,
)
box(
    ax,
    36,
    13,
    29,
    8,
    f"{FINAL_FITS} frozen checkpoints\nSHA-256-bound manifest; no reselection,\nno new fits",
    DONE,
)
arrow(ax, (50.5, 35.8), (50.5, 32.8))
arrow(ax, (50.5, 24.3), (50.5, 21.3))
arrow(ax, (20, 40), (35.7, 40))
arrow(ax, (20, 29), (35.7, 29))
box(
    ax,
    36,
    0,
    29,
    8.0,
    f"Deferred: training LOMO, {LOMO_FOLDS} folds × {FINAL_FITS} = {LOMO_FITS} fits\n"
    f"not executed; original plan {FINAL_FITS} + {LOMO_FITS} = {PLANNED_FITS} fits\n"
    "is therefore incomplete",
    DEFERRED,
    dashed=True,
)

box(
    ax,
    70,
    37,
    29,
    7,
    f"{FINAL_FITS} checkpoints × {len(EVAL_MATCHES)} matches\n"
    f"= {FINDINGS['records']} match/seed records "
    f"({FINDINGS['windows']:,} overlapping windows)",
    DONE,
)
# Evaluation matches and frozen checkpoints meet only at scoring; route below the fit column.
ax.plot([20, 20, 67.5, 67.5], [19, 11.3, 11.3, 40], color=INK, lw=0.9)
ax.plot([65.3, 67.5], [17, 17], color=INK, lw=0.9)
arrow(ax, (67.5, 40), (69.8, 40))
ax.text(
    43.5,
    10.2,
    "evaluation matches reach only the frozen checkpoints",
    fontsize=7,
    color=MUTED,
    style="italic",
    ha="center",
    va="top",
)
steps = (
    "directed scene: mask-aware ADE\nfinal-step FDE / XY RMSE",
    "window: equal mean over scoreable scenes",
    "match: equal mean over windows (per seed)",
    f"match: mean of {len(SEEDS)} seeds",
    f"configuration: equal mean of {len(EVAL_MATCHES)} matches",
)
for i, text in enumerate(steps):
    y = 32 - i * 4.4
    ax.add_patch(
        FancyBboxPatch(
            (72, y),
            25,
            3.0,
            boxstyle="round,pad=0.15,rounding_size=0.5",
            fc="white",
            ec=INK,
            lw=0.7,
        )
    )
    ax.text(84.5, y + 1.5, text, fontsize=7.4, ha="center", va="center")
    if i:
        arrow(ax, (84.5, y + 4.4), (84.5, y + 3.05))
arrow(ax, (84.5, 36.9), (84.5, 35.05))
box(
    ax,
    70,
    2.5,
    29,
    7.4,
    "C1/C2 paired within match after seed averaging\n"
    f"independent units n = {FINDINGS['independent_units']} matches; seeds and\n"
    "windows are not independent replicates",
    CONTRACT,
)
ax.set_ylim(-0.5, 51)
save(fig, "evaluation-design")
