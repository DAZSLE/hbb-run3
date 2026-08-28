import argparse
import numpy as np
import uproot
import matplotlib.pyplot as plt


def read_asymptotic_limits(path):
    with uproot.open(path) as f:
        t = f["limit"]
        q = t["quantileExpected"].array(library="np")
        lim = t["limit"].array(library="np")

    out = {}
    for qi, li in zip(q, lim):
        if abs(qi + 1) < 1e-3:
            out["obs"] = li
        elif abs(qi - 0.025) < 1e-3:
            out["m2"] = li
        elif abs(qi - 0.160) < 1e-3:
            out["m1"] = li
        elif abs(qi - 0.500) < 1e-3:
            out["med"] = li
        elif abs(qi - 0.840) < 1e-3:
            out["p1"] = li
        elif abs(qi - 0.975) < 1e-3:
            out["p2"] = li

    return out


def read_multidimfit_scan(path, poi, cl=0.95):
    """
    Reads a 1D MultiDimFit scan and extracts the confidence interval.

    For 1D:
      68% CL: 2*deltaNLL = 1.00
      95% CL: 2*deltaNLL = 3.84

    Combine stores deltaNLL, so threshold is:
      deltaNLL = 0.5 for 68%
      deltaNLL = 1.92 for 95%
    """
    if cl == 0.68:
        threshold = 0.5
    elif cl == 0.95:
        threshold = 1.92
    else:
        raise ValueError("Only cl=0.68 or cl=0.95 implemented")

    with uproot.open(path) as f:
        t = f["limit"]
        x = t[poi].array(library="np")
        dnll = t["deltaNLL"].array(library="np")

    y = 2.0 * dnll

    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    # Remove duplicate x values, keeping the smallest NLL value
    xu = []
    yu = []
    for val in np.unique(x):
        m = x == val
        xu.append(val)
        yu.append(np.min(y[m]))
    x = np.asarray(xu)
    y = np.asarray(yu)

    ymin_idx = np.argmin(y)
    best = x[ymin_idx]

    target = 2.0 * threshold

    left_x = x[: ymin_idx + 1]
    left_y = y[: ymin_idx + 1]
    right_x = x[ymin_idx:]
    right_y = y[ymin_idx:]

    lo = find_crossing(left_x, left_y, target, side="left")
    hi = find_crossing(right_x, right_y, target, side="right")

    return {
        "obs": best,
        "med": best,
        "m1": lo,
        "p1": hi,
        "m2": lo,
        "p2": hi,
    }


def find_crossing(x, y, target, side):
    vals = y - target

    crossings = []
    for i in range(len(x) - 1):
        if vals[i] == 0:
            crossings.append(x[i])
        elif vals[i] * vals[i + 1] < 0:
            x0, x1 = x[i], x[i + 1]
            y0, y1 = vals[i], vals[i + 1]
            xc = x0 - y0 * (x1 - x0) / (y1 - y0)
            crossings.append(xc)

    if not crossings:
        return np.nan

    if side == "left":
        return crossings[-1]
    else:
        return crossings[0]


def make_plot(results, args, cms_label="CMS Private Work"):
    n = len(results)
    y = np.arange(n)[::-1]

    fig, ax = plt.subplots(figsize=(9, 0.9 * n + 2.0))

    for i, res in enumerate(results):
        yi = y[i]

        m2 = res.get("m2", np.nan)
        m1 = res.get("m1", np.nan)
        med = res.get("med", np.nan)
        p1 = res.get("p1", np.nan)
        p2 = res.get("p2", np.nan)
        obs = res.get("obs", np.nan)

        ax.barh(
            yi,
            p2 - m2,
            left=m2,
            height=0.75,
            color="lightskyblue",
            edgecolor="none",
            label="95% expected" if i == 0 else None,
        )

        ax.barh(
            yi,
            p1 - m1,
            left=m1,
            height=0.75,
            color="khaki",
            edgecolor="none",
            label="68% expected" if i == 0 else None,
        )

        ax.vlines(
            med,
            yi - 0.38,
            yi + 0.38,
            colors="black",
            linestyles="dashed",
            label="Median expected" if i == 0 else None,
        )

        if not args.blind and np.isfinite(obs):
            ax.plot(
                obs,
                yi,
                "ko",
                label="Observed" if i == 0 else None,
            )

        txt = f"Exp. {med:.3g}"
        if not args.blind and np.isfinite(obs):
            txt += f"\nObs. {obs:.3g}"

        xmin, xmax = ax.get_xlim()
        ax.text(
            xmin,
            yi,
            txt,
            ha="right",
            va="center",
            fontsize=12,
        )

    ax.axvline(1.0, color="red", linewidth=1.2)

    ax.set_yticks(y)
    ax.set_yticklabels(args.labels, fontsize=13, fontweight="bold")
    ax.set_xlabel(args.xlabel, fontsize=15)

    ax.legend(loc="upper right", frameon=False, fontsize=12)

    ax.text(
        0.0,
        1.03,
        cms_label,
        transform=ax.transAxes,
        fontsize=16,
        fontweight="bold",
        ha="left",
        va="bottom",
    )

    ax.tick_params(axis="both", which="both", direction="in", top=True, right=True)
    ax.set_ylim(-0.6, n - 0.4)

    fig.tight_layout()
    fig.savefig(args.output)
    print(f"Saved {args.output}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="ROOT files from AsymptoticLimits or MultiDimFit",
    )

    parser.add_argument(
        "--labels",
        nargs="+",
        required=True,
        help="Labels matching the input files (ex: Hcc, VHcc)",
    )

    parser.add_argument(
        "--types",
        nargs="+",
        required=True,
        choices=["asymptotic", "multidimfit"],
        help="Type for each input file",
    )

    parser.add_argument(
        "--poi",
        default="rH_cc",
        help="POI name for MultiDimFit scans",
    )

    parser.add_argument(
        "--output",
        default="limit_summary.pdf",
    )

    parser.add_argument(
        "--xlabel",
        default=r"95% CL upper limit / interval on $\mu_{H\to c\bar{c}}$",
    )

    parser.add_argument(
        "--blind",
        action="store_true",
        help="Do not draw observed values",
    )

    args = parser.parse_args()

    if not (len(args.inputs) == len(args.labels) == len(args.types)):
        raise ValueError("--inputs, --labels, and --types must have the same length")

    results = []
    for path, typ in zip(args.inputs, args.types):
        if typ == "asymptotic":
            results.append(read_asymptotic_limits(path))
        else:
            results.append(read_multidimfit_scan(path, args.poi, cl=0.95))

    make_plot(results, args)


if __name__ == "__main__":
    main()