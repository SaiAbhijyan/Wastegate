def sliding_windows(xs, k):
    """All contiguous windows of length k, in order."""
    return [xs[i:i + k] for i in range(len(xs) - k)]
