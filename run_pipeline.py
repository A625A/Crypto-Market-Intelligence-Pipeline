"""Run the project data pipeline from raw CSV to final features."""

from argparse import ArgumentParser
from pathlib import Path

from src.extractors import load_raw_data
from src.features import build_features
from src.transformers import clean_data

PROCESSED_DATA_DIR = Path("data/processed")
FINAL_DATA_DIR = Path("data/final")


def run_pipeline(
    input_filename: str,
    processed_filename: str = "processed.csv",
    final_filename: str = "features.csv",
) -> tuple[Path, Path]:
    """Load raw data, clean it, build features, and save pipeline outputs."""
    raw_df = load_raw_data(input_filename)
    cleaned_df = clean_data(raw_df)
    feature_df = build_features(cleaned_df)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    processed_path = PROCESSED_DATA_DIR / processed_filename
    final_path = FINAL_DATA_DIR / final_filename

    cleaned_df.to_csv(processed_path, index=False)
    feature_df.to_csv(final_path, index=False)

    return processed_path, final_path


def parse_args() -> ArgumentParser:
    """Build the CLI argument parser."""
    parser = ArgumentParser(description="Run the crypto data science pipeline.")
    parser.add_argument(
        "input_filename",
        help="CSV filename inside data/raw/.",
    )
    parser.add_argument(
        "--processed-filename",
        default="processed.csv",
        help="Output filename inside data/processed/.",
    )
    parser.add_argument(
        "--final-filename",
        default="features.csv",
        help="Output filename inside data/final/.",
    )
    return parser


if __name__ == "__main__":
    args = parse_args().parse_args()
    processed_output, final_output = run_pipeline(
        input_filename=args.input_filename,
        processed_filename=args.processed_filename,
        final_filename=args.final_filename,
    )
    print(f"Saved processed data to {processed_output}")
    print(f"Saved final features to {final_output}")
