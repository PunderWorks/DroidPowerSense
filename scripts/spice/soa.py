"""Safe-operating-area check for a simulated MOSFET power waveform.

The SOA chart gives the power a FET survives for a single rectangular pulse of a given length. A
simulated waveform is not rectangular, so for every window length we take the highest average power
over any window of that length and compare it with the chart's limit at that length. For a
rectangular pulse this is exact; for a decaying pulse (inrush, where VDS falls while current flows)
it is a reasonable, slightly conservative estimate. It is not a substitute for a transient thermal
model.
"""
from bisect import bisect_left
from math import exp, log

# CSD18532Q5B (SLPS322E Fig. 4-10, Maximum Safe Operating Area, single pulse, TC = 25 C), read off
# the chart at VDS = 30 V. Chart-reading error is roughly +/-30%. Power = 30 V x current.
#   10 us: ~219 A   100 us: ~42 A   1 ms: ~9.7 A   10 ms: ~4.1 A   DC: ~0.9 A (taken as 1 s)
CSD18532_SOA_30V = ((10e-6, 6570.0), (100e-6, 1254.0), (1e-3, 291.0), (10e-3, 122.0), (1.0, 27.0))

# SMBJ33CA (Diodes DS19002 Fig. 3, Pulse Rating Curve, Tj = 25 C): peak pulse power for the 10/1000
# exponential waveform of Fig. 4, a straight line on log-log axes through ~600 W at 1 ms and ~210 W at
# 10 ms (slope about -0.46 per decade). The average power of that waveform over its width is ~0.72 of
# its peak, so the table holds 0.72 x Ppk. Points beyond 10 ms are extrapolated along the same line
# (the chart stops at 10 ms) and are an estimate, not a rating; steady state is 5 W (PM(AV)).
SMBJ33CA_PULSE = tuple((t, 0.72 * 600.0 * (t / 1e-3) ** -0.46) for t in (10e-6, 100e-6, 1e-3, 10e-3, 100e-3, 1.0))

# The charts are for 25 C. Derate linearly to the temperature assumed before the event (the
# CSD18532Q5B to TJ max 150 C; the SMBJ derating of Fig. 1 also reaches zero at 150 C).
TJ_MAX = 150.0


def derate(case_c, chart_c=25.0, tj_max=TJ_MAX):
    """Factor applied to the 25 C SOA power for a hotter case (linear in temperature headroom)."""
    if case_c >= tj_max:
        return 0.0
    return (tj_max - case_c) / (tj_max - chart_c)


def soa_limit(duration, table=CSD18532_SOA_30V):
    """Allowed power (W) for a pulse of `duration` seconds, log-log interpolated between chart points
    and clamped to the end points."""
    if duration <= table[0][0]:
        return table[0][1]
    if duration >= table[-1][0]:
        return table[-1][1]
    for (t0, p0), (t1, p1) in zip(table, table[1:]):
        if t0 <= duration <= t1:
            frac = (log(duration) - log(t0)) / (log(t1) - log(t0))
            return exp(log(p0) + frac * (log(p1) - log(p0)))
    raise AssertionError("unreachable")


def cumulative_energy(t, p):
    """Running integral of power (trapezoidal), same length as `t`."""
    energy = [0.0]
    for i in range(1, len(t)):
        energy.append(energy[-1] + 0.5 * (p[i] + p[i - 1]) * (t[i] - t[i - 1]))
    return energy


def _energy_at(t, energy, when):
    """Cumulative energy linearly interpolated at `when` (clamped to the trace)."""
    if when <= t[0]:
        return energy[0]
    if when >= t[-1]:
        return energy[-1]
    i = bisect_left(t, when)
    span = t[i] - t[i - 1]
    frac = 0.0 if span == 0 else (when - t[i - 1]) / span
    return energy[i - 1] + frac * (energy[i] - energy[i - 1])


def max_window_power(t, p, window):
    """Highest average power over any `window`-second span of the trace."""
    energy = cumulative_energy(t, p)
    best = 0.0
    for i, end in enumerate(t):
        start = end - window
        if start < t[0]:
            # A window that would start before the trace began: the FET was idle before t[0].
            best = max(best, energy[i] / window)
            continue
        best = max(best, (energy[i] - _energy_at(t, energy, start)) / window)
    return best


WINDOWS = (10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3, 30e-3, 100e-3, 300e-3, 1.0)


def soa_margin(t, p, case_c=60.0, table=CSD18532_SOA_30V, windows=WINDOWS):
    """Worst ratio of (windowed average power) / (derated SOA limit) across window lengths.

    Returns (ratio, window, average_power, limit). A ratio above 1.0 means outside the SOA."""
    factor = derate(case_c)
    worst = (0.0, windows[0], 0.0, soa_limit(windows[0], table) * factor)
    for window in windows:
        avg = max_window_power(t, p, window)
        limit = soa_limit(window, table) * factor
        ratio = avg / limit if limit > 0 else float("inf")
        if ratio > worst[0]:
            worst = (ratio, window, avg, limit)
    return worst


def fmt_window(seconds):
    """Human-readable window length: 10us, 3ms, 1s."""
    if seconds >= 1.0:
        return f"{seconds:g}s"
    if seconds >= 1e-3:
        return f"{seconds * 1e3:g}ms"
    return f"{seconds * 1e6:g}us"
