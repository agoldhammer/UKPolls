"""Visualize UK general election voting-intention polls as PNG charts.

Reads data/uk_polls_national.csv (one row per poll, party shares in percent)
and renders individual polls as faint dots with a rolling-average trend line
per party, in each party's conventional color.

Usage: uv run main.py [--csv PATH]
"""

import argparse

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

# Party colors chosen from a validated CVD-safe categorical palette (see
# node scripts/validate_palette.js), not pure brand hex -- Reform's teal and
# Labour's red in particular were shifted to clear colorblind separation from
# the Lib Dem/SNP and Green slots respectively. Order = label order by recent
# support. Others is a neutral catch-all, exempt from the palette check.
PARTIES = {
    "Ref": "#1baf7a",
    "Lab": "#e34948",
    "Con": "#2a78d6",
    "LD": "#eb6834",
    "Grn": "#008300",
    "SNP": "#eda100",
    "PC": "#4a3aa7",
    "RB": "#e87ba4",
    "Others": "#75797E",
}

ELECTION = "2024-07-04"

INK = "#33302e"
MUTED = "#77716c"
SURFACE = "#fcfcfb"
ROLLING_WINDOW = "14D"


def load_polls(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    return df.sort_values("date").set_index("date")


def spread_labels(positions: list[float], min_gap: float, lo: float, hi: float) -> list[float]:
    """Nudge label y-positions apart until no pair is closer than min_gap."""
    order = sorted(range(len(positions)), key=lambda i: positions[i])
    ys = [positions[i] for i in order]
    for _ in range(100):
        moved = False
        for a in range(len(ys) - 1):
            overlap = min_gap - (ys[a + 1] - ys[a])
            if overlap > 0:
                ys[a] -= overlap / 2
                ys[a + 1] += overlap / 2
                moved = True
        ys[0] = max(ys[0], lo)
        ys[-1] = min(ys[-1], hi)
        if not moved:
            break
    out = positions[:]
    for rank, i in enumerate(order):
        out[i] = ys[rank]
    return out


def latest_averages(df: pd.DataFrame) -> dict[str, float]:
    """Latest rolling-average share per party, from the most recent polls."""
    return {
        party: float(df[party].dropna().rolling(ROLLING_WINDOW).mean().iloc[-1])
        for party in PARTIES
        if df[party].notna().any()
    }


def dodge(values: list[float], gap: float = 0.5, step: float = 0.16) -> list[float]:
    """Vertical offsets that spread out dots whose x-values nearly coincide."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    offsets = [0.0] * len(values)
    cluster = [order[0]]
    for i in order[1:] + [None]:
        if i is not None and values[i] - values[cluster[-1]] < gap:
            cluster.append(i)
            continue
        for k, idx in enumerate(cluster):
            offsets[idx] = (k - (len(cluster) - 1) / 2) * step
        cluster = [i] if i is not None else []
    return offsets


def plot(df: pd.DataFrame, out_path: str, title: str, subtitle_prefix: str = "") -> None:
    fig, ax = plt.subplots(figsize=(14, 8), dpi=200)
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    label_targets = {}
    for party, color in PARTIES.items():
        series = df[party].dropna() if party in df.columns else pd.Series(dtype=float)
        if series.empty:
            continue
        ax.scatter(series.index, series.values, s=5, color=color, alpha=0.15, linewidths=0)
        smoothed = series.rolling(ROLLING_WINDOW).mean()
        ax.plot(smoothed.index, smoothed.values, color=color, linewidth=2, solid_capstyle="round")
        label_targets[party] = float(smoothed.iloc[-1])

    election_ts = pd.Timestamp(ELECTION)
    if df.index.min() < election_ts < df.index.max():
        ax.axvline(election_ts, color=MUTED, linewidth=0.8, linestyle=(0, (4, 4)), alpha=0.6)
        ax.annotate(
            "GE 2024", (election_ts, 0.995), xycoords=("data", "axes fraction"),
            xytext=(0, -2), textcoords="offset points",
            ha="center", va="top", fontsize=8.5, color=MUTED,
        )

    parties = list(label_targets)
    ymax = df[[p for p in PARTIES if p in df.columns]].max().max() + 2
    labeled_ys = spread_labels(
        [label_targets[p] for p in parties], ymax * 0.04, ymax * 0.01, ymax * 0.99
    )
    x_end = df.index.max()
    for party, y_label in zip(parties, labeled_ys):
        ax.annotate(
            "", (x_end, label_targets[party]),
            xytext=(14, 0), textcoords="offset points",
            arrowprops=dict(arrowstyle="-", color=PARTIES[party], linewidth=2,
                            shrinkA=0, shrinkB=3),
            annotation_clip=False,
        )
        ax.annotate(
            f"{party}  {label_targets[party]:.0f}", (x_end, y_label),
            xytext=(18, 0), textcoords="offset points",
            va="center", fontsize=10, color=INK,
            annotation_clip=False,
        )

    ax.set_ylim(0, ymax)
    ax.set_xlim(df.index.min(), x_end)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    if (df.index.max() - df.index.min()).days > 365:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="y", color="#e6e3e0", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#d5d1cd")
    ax.tick_params(colors=MUTED, labelsize=10, length=0)

    n_polls = len(df)
    ax.set_title(title, fontsize=16, color=INK, loc="left", pad=28, fontweight="bold")
    ax.text(
        0, 1.025,
        f"{subtitle_prefix}{n_polls} polls, {df.index.min():%b %Y} – {df.index.max():%b %Y} · "
        f"dots: individual polls · lines: {ROLLING_WINDOW} rolling average",
        transform=ax.transAxes, fontsize=10.5, color=MUTED,
    )
    fig.text(
        0.99, 0.01,
        "Source: data/uk_polls_national.csv (Wikipedia, national polls, GB/UK)",
        ha="right", fontsize=8.5, color=MUTED,
    )

    fig.subplots_adjust(left=0.045, right=0.9, top=0.895, bottom=0.07)
    fig.savefig(out_path, facecolor=SURFACE)
    print(f"Wrote {out_path}")


def plot_pollsters(df: pd.DataFrame, out_path: str) -> None:
    cutoff = df.index.max() - pd.Timedelta(days=90)
    latest = df[df.index >= cutoff].reset_index().groupby("pollster").last()
    latest = latest.sort_values("Ref")

    avg = latest_averages(df)

    def short(name: str) -> str:
        return name if len(name) <= 24 else name[:23] + "…"

    rows = [(f"{short(pollster)}  ({row['date']:%d %b})", row) for pollster, row in latest.iterrows()]
    rows.append((f"{ROLLING_WINDOW} average", pd.Series(avg)))

    fig, ax = plt.subplots(figsize=(14, 0.62 * len(rows) + 2.6), dpi=200)
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    xmax = 0.0
    for y, (label, values) in enumerate(rows):
        present = [p for p in PARTIES if p in values and pd.notna(values[p])]
        vals = [float(values[p]) for p in present]
        offsets = dodge(vals)
        for party, v, dy in zip(present, vals, offsets):
            ax.scatter(v, y + dy, s=90, color=PARTIES[party], zorder=3,
                       edgecolor=SURFACE, linewidth=1.5)
        xmax = max(xmax, max(vals))

    ax.axhline(len(rows) - 1.5, color="#d5d1cd", linewidth=0.8)

    handles = [
        plt.Line2D([], [], marker="o", linestyle="", markersize=9,
                   markerfacecolor=color, markeredgecolor=SURFACE, label=party)
        for party, color in PARTIES.items()
    ]
    ax.legend(
        handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0),
        ncol=len(PARTIES), frameon=False, fontsize=9.5, labelcolor=INK,
        handletextpad=0.1, columnspacing=0.9, borderaxespad=0.2,
    )

    ax.set_xlim(0, xmax + 2)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_yticks(range(len(rows)), [label for label, _ in rows], fontsize=10)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="x", color="#e6e3e0", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#d5d1cd")
    ax.tick_params(colors=MUTED, length=0)
    for tick in ax.get_yticklabels():
        tick.set_color(INK)
    ax.get_yticklabels()[-1].set_fontweight("bold")

    fig.text(
        0.03, 0.955, "Current polls by pollster",
        fontsize=16, color=INK, fontweight="bold", va="top",
    )
    fig.text(
        0.03, 0.905,
        f"Latest poll from each pollster in the past 90 days (as of {df.index.max():%d %b %Y}), "
        f"sorted by Reform share · average = {ROLLING_WINDOW} rolling average across all pollsters",
        fontsize=10, color=MUTED, va="top",
    )
    fig.text(
        0.99, 0.02,
        "Source: data/uk_polls_national.csv (Wikipedia, national polls, GB/UK)",
        ha="right", fontsize=8.5, color=MUTED,
    )

    fig.subplots_adjust(left=0.21, right=0.97, top=0.79, bottom=0.10)
    fig.savefig(out_path, facecolor=SURFACE)
    print(f"Wrote {out_path}")


def plot_pollster_trends(df: pd.DataFrame, out_path: str) -> None:
    counts = df.groupby("pollster").size()
    pollsters = counts[counts >= 15].sort_values(ascending=False).index

    ncols = 4
    nrows = -(-len(pollsters) // ncols)
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(14, 3.4 * nrows + 1.9), dpi=200,
        sharex=True, sharey=True,
    )
    fig.set_facecolor(SURFACE)

    ymax = 0.0
    for ax, pollster in zip(axes.flat, pollsters):
        ax.set_facecolor(SURFACE)
        sub = df[df["pollster"] == pollster]
        for party, color in PARTIES.items():
            series = sub[party].dropna() if party in sub.columns else pd.Series(dtype=float)
            if series.empty:
                continue
            ax.scatter(series.index, series.values, s=4, color=color,
                       alpha=0.3, linewidths=0)
            # Pollsters poll at very different rates, so use a wider window
            # than the overall trend charts.
            smoothed = series.rolling("28D").mean()
            ax.plot(smoothed.index, smoothed.values, color=color,
                    linewidth=1.6, solid_capstyle="round")
            ymax = max(ymax, series.max())
        ax.set_title(f"{pollster}  ·  {len(sub)} polls", fontsize=10.5,
                     color=INK, loc="left", pad=6)
        ax.grid(axis="y", color="#e6e3e0", linewidth=0.6)
        ax.set_axisbelow(True)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color("#d5d1cd")
        ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    for ax in axes.flat[len(pollsters):]:
        ax.set_visible(False)
    axes.flat[0].set_ylim(0, ymax + 2)

    handles = [
        plt.Line2D([], [], marker="o", linestyle="", markersize=8,
                   markerfacecolor=color, markeredgecolor=SURFACE, label=party)
        for party, color in PARTIES.items()
    ]
    fig.legend(
        handles=handles, loc="upper right", bbox_to_anchor=(0.99, 1.0),
        ncol=len(PARTIES), frameon=False, fontsize=9, labelcolor=INK,
        handletextpad=0.1, columnspacing=0.8,
    )

    fig.text(
        0.03, 0.975, "Party support in trend by pollster",
        fontsize=16, color=INK, fontweight="bold", va="top",
    )
    fig.text(
        0.03, 0.935,
        "Since the 2024 general election · pollsters with at least 15 polls · "
        "dots: individual polls · lines: 28-day rolling average",
        fontsize=10, color=MUTED, va="top",
    )
    fig.text(
        0.99, 0.01,
        "Source: data/uk_polls_national.csv (Wikipedia, national polls, GB/UK)",
        ha="right", fontsize=8.5, color=MUTED,
    )

    fig.subplots_adjust(left=0.045, right=0.985, top=0.86, bottom=0.06,
                        hspace=0.28, wspace=0.08)
    fig.savefig(out_path, facecolor=SURFACE)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/uk_polls_national.csv")
    parser.add_argument("--out", default="uk_polls_national.png")
    parser.add_argument("--out-recent", default="uk_polls_recent.png")
    parser.add_argument("--out-pollsters", default="uk_polls_pollsters.png")
    parser.add_argument("--out-pollster-trends", default="uk_polls_pollster_trends.png")
    args = parser.parse_args()
    df = load_polls(args.csv)
    plot(df, args.out, "Westminster voting intention since the 2024 general election")
    recent_cutoff = df.index.max() - pd.Timedelta(days=182)
    plot(
        df[df.index >= recent_cutoff],
        args.out_recent,
        "Westminster voting intention, last 6 months",
    )
    plot_pollsters(df, args.out_pollsters)
    plot_pollster_trends(df, args.out_pollster_trends)


if __name__ == "__main__":
    main()
