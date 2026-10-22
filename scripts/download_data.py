from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clearsignal_wq.data import DATA_FILES, DataContractError, download_data_file


def main() -> int:
    parser = argparse.ArgumentParser(description="下载并校验固定水质传感器数据")
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("data/raw"),
        help="下载目录（默认：data/raw）",
    )
    args = parser.parse_args()

    try:
        for name, (_, expected_digest) in DATA_FILES.items():
            download_data_file(name, args.destination)
            print(f"{name}: verified SHA-256 {expected_digest}")
    except (DataContractError, OSError) as exc:
        print(f"下载失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
