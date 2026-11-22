"""Match the operation order of the pinned OpenClaw speed scorer."""


def call_rate(tokens, milliseconds):
    return tokens / (milliseconds / 1000)


def mean_rate(rates):
    total = 0.0
    for rate in rates:
        total += rate
    return total / len(rates)


def round_rate(rate):
    """Round a nonnegative rate like Math.round without rounding the added half."""
    whole = int(rate)
    return whole + (rate - whole >= 0.5)


def recording_required(mean, displayed, valid, cutoff, plan):
    if displayed is not None and displayed >= cutoff:
        return True
    if not valid or mean is None or 'prior_verified_mean_tps' not in plan:
        return False
    prior = plan['prior_verified_mean_tps']
    return prior is None or mean > prior
