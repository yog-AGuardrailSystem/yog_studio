"""Small-sample statistics for the benchmark. With ~20 test rules a bare percentage overstates what we know,
so every proportion is reported with a Wilson 95% confidence interval."""
import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials, as fractions (0..1). (0, 1) when n == 0."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def proportion(k: int, n: int) -> dict:
    """{k, n, pct, ci_low, ci_high} with percentages rounded to 0.1."""
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None,
            "ci_low": round(100 * lo, 1), "ci_high": round(100 * hi, 1)}


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100); None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, min(len(s) - 1, math.ceil(q / 100 * len(s)) - 1))]


def fmt(p: dict) -> str:
    """'62.5% (k=5/8, 95% CI 30.6 to 86.3)'"""
    if not p["n"]:
        return "n/a (no items)"
    return f"{p['pct']}% ({p['k']}/{p['n']}, 95% CI {p['ci_low']} to {p['ci_high']})"
