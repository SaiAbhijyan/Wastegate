Off-by-one: range stops one window early.
<<<REPLACE windows/__init__.py
    return [xs[i:i + k] for i in range(len(xs) - k)]
<<<WITH
    return [xs[i:i + k] for i in range(len(xs) - k + 1)]
<<<END
