import os
from pathlib import Path
from typing import Optional

import librosa
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

    def _load_audio(self, row: pd.Series, col: str, duration=5):
        offset = row[f"{col}_loc"]
        filename = (self.tile_dir / row[col]).as_posix()
        # -1 is when the audio file is shorter than our 5 second window
        if offset > 0:
            # we know we have enough room to read near the ends, so we can shift
            # it by some amount
            # this is not exactly even, but it's good enough for me right now
            offset = max(offset + (np.random.rand() - 0.5) * duration, 0)
            y, sr = librosa.load(filename, offset=offset, duration=duration, sr=32000)
        else:
            y, sr = librosa.load(filename, sr=32000)

        # ensure these are audio samples
        length = sr * duration
        return np.resize(np.moveaxis(y, -1, 0), length)

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
        self, meta_df: pd.DataFrame, data_dir: Path, batch_size=4, num_workers=8
    ):
        super().__init__()
        self.meta_df = meta_df
        self.data_dir = data_dir
        self.batch_size = batch_size
        self.num_workers = num_workers

    def setup(self, stage: Optional[str] = None):
        n = self.meta_df.shape[0]
        ratios = [0.8, 0.1, 0.1]
        lengths = [int(n * p) for p in ratios]
        lengths[0] += n - sum(lengths)

        dataset = TileTripletsDataset(
            self.meta_df,
            self.data_dir,
            transform=transforms.Compose([ToFloatTensor()]),
        )
        self.train, self.val, self.test = random_split(dataset, lengths)

    def train_dataloader(self):
        return DataLoader(
            self.train, batch_size=self.batch_size, num_workers=self.num_workers
        )

    def val_dataloader(self):
        return DataLoader(
            self.val, batch_size=self.batch_size, num_workers=self.num_workers
        )

    def test_dataloader(self):
        return DataLoader(
            self.test, batch_size=self.batch_size, num_workers=self.num_workers
        )