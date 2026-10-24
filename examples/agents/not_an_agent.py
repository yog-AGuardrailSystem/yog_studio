"""A plain utility script. Detector must say `unknown` (and the UI offers manual selection)."""


def fibonacci(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return c * 9 / 5 + 32


async def slow_double(x: int) -> int:
    return x * 2


if __name__ == "__main__":
    print(fibonacci(10))
