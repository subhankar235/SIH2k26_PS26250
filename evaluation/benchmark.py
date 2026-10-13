"""Quick, dependency-light synthetic baseline benchmark."""

from ml.models.forecast import moving_average


def run_benchmark() -> dict[str, float]:
    """Compare the trailing-mean baseline with a fixed synthetic series."""
    actual = [100.0, 105.0, 103.0, 110.0]
    prediction = moving_average(actual[:-1], window=3)
    return {"mae_mw": abs(actual[-1] - prediction), "prediction_mw": prediction}


if __name__ == "__main__":
    print(run_benchmark())
