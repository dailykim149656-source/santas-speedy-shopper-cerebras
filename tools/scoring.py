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
