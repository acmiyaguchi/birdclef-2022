from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pytorch_lightning as pl
import torch
from torch.utils.data import DataLoader, Dataset, random_split
from torchvision import transforms


class TileTripletsDataset(Dataset):
    def __init__(self, meta_df: pd.DataFrame, tile_dir: Path, transform=None):
        self.df = meta_df
        self.tile_dir = Path(tile_dir)
        self.transform = transform

    def __len__(self):
        return self.df.shape[0]

    def _load_audio(self, row: pd.Series, col: str, duration=7):
        # build the canonical filename
        offset = int(row[f"{col}_loc"])
        input_path = Path(row[col])
        filename = (
            self.tile_dir / f"{input_path.name.split('.')[0]}_{offset}_{duration}.npy"
        ).as_posix()
        # lets only keep 5 seconds of data
        sr = 32000
        offset = int(np.random.rand() * 2 * sr)
        return np.load(filename)[offset : offset + sr * 5]

    def __getitem__(self, idx: int):
        try:
            row = self.df.iloc[idx]
        except:
            raise KeyError(idx)
        sample = {
            "anchor": self._load_audio(row, "a"),
            "neighbor": self._load_audio(row, "b"),
            "distant": self._load_audio(row, "c"),
        }
        if self.transform:
            sample = self.transform(sample)
        return sample


class ToFloatTensor:
    """
    Converts numpy arrays to float Variables in Pytorch.
    """

    def __call__(self, sample):
        a, n, d = (
            torch.from_numpy(sample["anchor"]).float(),
            torch.from_numpy(sample["neighbor"]).float(),
            torch.from_numpy(sample["distant"]).float(),
        )
        sample = {"anchor": a, "neighbor": n, "distant": d}
        return sample


class TileTripletsDataModule(pl.LightningDataModule):
    def __init__(
        self,
        meta_df: pd.DataFrame,
        data_dir: Path,
        batch_size=4,
        num_workers=8,
        shuffle=True,
    ):
        super().__init__()
        self.meta_df = meta_df
        self.data_dir = data_dir
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.kwargs = dict(
            batch_size=self.batch_size,
            num_workers=self.num_workers,
            pin_memory=True,
        )
        self.shuffle = shuffle

    def setup(self, stage: Optional[str] = None):
        n = self.meta_df.shape[0]
        ratios = [0.9, 0.1]
        lengths = [int(n * p) for p in ratios]
        lengths[0] += n - sum(lengths)

        dataset = TileTripletsDataset(
            self.meta_df,
            self.data_dir,
            transform=transforms.Compose([ToFloatTensor()]),
        )
        self.train, self.val = random_split(dataset, lengths)

    def train_dataloader(self):
        return DataLoader(self.train, shuffle=self.shuffle, **self.kwargs)

    def val_dataloader(self):
        return DataLoader(self.val, **self.kwargs)

    def test_dataloader(self):
        raise NotImplementedError()
