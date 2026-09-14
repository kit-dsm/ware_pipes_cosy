from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd


class DataLoader(ABC):
    """Small loader contract owned by the benchmark project.

    ``ware_ops_algos`` intentionally stopped shipping data loaders.  Keeping the
    contract here prevents benchmark I/O from being coupled to that package's
    internal layout.
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.cache_path: Path | None = None

    @abstractmethod
    def load(self, *args, **kwargs) -> Any:
        pass

    def _load_text(self, filename: str | Path, encoding: str = "utf-8") -> list[str]:
        path = Path(filename)
        if not path.is_absolute():
            path = self.data_dir / path
        with path.open("r", encoding=encoding) as file:
            return [line.strip() for line in file if line.strip()]

    def _load_csv(self, filename: str | Path, sep: str = ",", **kwargs) -> pd.DataFrame:
        path = Path(filename)
        if not path.is_absolute():
            path = self.data_dir / path
        return pd.read_csv(path, sep=sep, **kwargs)
