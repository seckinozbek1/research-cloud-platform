from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
import ray
import ray.train as train
import torch

from ray.train import ScalingConfig
from ray.train.torch import TorchTrainer
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "waste_operations.csv"
)

ARTIFACT_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "distributed_ml"
)

ARTIFACT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FEATURES = [
    "population_2025",
    "population_density_2025",
    "road_density_km_per_km2",
    "container_capacity_kg",
    "days_since_last_pickup",
    "weekend",
    "temperature_c",
    "rain_mm",
    "previous_waste_kg",
]

TARGET = "waste_kg"

EPOCHS = 50
BATCH_SIZE = 512
LR = 1e-3


class WasteMLP(nn.Module):
    def __init__(self, input_dim):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x)


def load_data():
    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["collection_date"],
    )

    cutoff = (
        df["collection_date"].max()
        - pd.offsets.Day(29)
    )

    train_df = df[
        df["collection_date"] < cutoff
    ].copy()

    scaler = StandardScaler()

    x = scaler.fit_transform(
        train_df[FEATURES]
    ).astype("float32")

    y = (
        train_df[TARGET]
        .to_numpy(dtype="float32")
        .reshape(-1, 1)
    )

    # Numerical stability for this small exercise.
    y = (
        (y - y.mean())
        / max(float(y.std()), 1e-8)
    ).astype("float32")

    return x, y


def train_loop_per_worker(config):

    context = train.get_context()

    rank = context.get_world_rank()
    world_size = context.get_world_size()

    print(
        f"Training rank={rank} "
        f"world_size={world_size}"
    )

    # ------------------------------------------------------
    # Every worker constructs the same Dataset.
    # Ray will shard the DataLoader below.
    # ------------------------------------------------------

    x, y = load_data()

    dataset = TensorDataset(
        torch.from_numpy(x),
        torch.from_numpy(y),
    )

    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
    )

    # ------------------------------------------------------
    # Ray replaces the ordinary loader with a distributed
    # one. With 2 workers, each worker processes a different
    # shard of the training samples.
    # ------------------------------------------------------

    loader = train.torch.prepare_data_loader(
        loader
    )

    model = WasteMLP(
        len(FEATURES)
    )

    # ------------------------------------------------------
    # This is the important Ray/PyTorch bridge.
    #
    # Ray moves the model to the appropriate device and,
    # because world_size > 1, wraps it in PyTorch DDP.
    #
    # We therefore do NOT manually call:
    # dist.init_process_group()
    # DDP(model)
    # ------------------------------------------------------

    model = train.torch.prepare_model(
        model
    )

    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=LR,
    )

    loss_fn = nn.MSELoss()

    start = time.perf_counter()

    final_loss = None

    for epoch in range(EPOCHS):

        # DistributedSampler must receive the epoch so that
        # workers get a new shuffled ordering each epoch.
        if hasattr(
            loader.sampler,
            "set_epoch",
        ):
            loader.sampler.set_epoch(
                epoch
            )

        running_loss = 0.0
        seen = 0

        for xb, yb in loader:

            optimizer.zero_grad(
                set_to_none=True
            )

            pred = model(xb)

            loss = loss_fn(
                pred,
                yb,
            )

            loss.backward()
            optimizer.step()

            running_loss += (
                loss.item()
                * xb.shape[0]
            )

            seen += xb.shape[0]

        final_loss = (
            running_loss
            / max(seen, 1)
        )

        if (
            epoch == 0
            or (epoch + 1) % 10 == 0
            or epoch + 1 == EPOCHS
        ):
            print(
                f"rank={rank} "
                f"epoch={epoch + 1:03d} "
                f"loss={final_loss:.4f}"
            )

    wall = (
        time.perf_counter()
        - start
    )

    # Ray Train records metrics from the distributed run.
    train.report(
        {
            "rank":
                rank,

            "world_size":
                world_size,

            "epochs":
                EPOCHS,

            "final_loss":
                final_loss,

            "wall_seconds":
                wall,
        }
    )


def main():

    # ------------------------------------------------------
    # We ask Ray for:
    #
    # 2 distributed workers
    # CPU only
    # 1 CPU allocated to each worker
    # ------------------------------------------------------

    trainer = TorchTrainer(
        train_loop_per_worker=
            train_loop_per_worker,

        scaling_config=ScalingConfig(
            num_workers=2,
            use_gpu=False,

            resources_per_worker={
                "CPU": 1,
            },
        ),
    )

    start = time.perf_counter()

    result = trainer.fit()

    total_wall = (
        time.perf_counter()
        - start
    )

    print()
    print("=== RAY DISTRIBUTED TRAINING ===")
    print(
        "Total wall seconds:",
        round(total_wall, 4),
    )

    print(
        "Ray result metrics:",
        result.metrics,
    )

    metrics = {
        "mode":
            "ray_torch_ddp",

        "num_workers":
            2,

        "use_gpu":
            False,

        "epochs":
            EPOCHS,

        "total_wall_seconds":
            total_wall,

        "result_metrics":
            result.metrics,
    }

    out = (
        ARTIFACT_DIR
        / "ray-2cpu-training_metrics.json"
    )

    out.write_text(
        json.dumps(
            metrics,
            indent=2,
            default=str,
        )
    )

    print(
        "Metrics saved:",
        out,
    )

    ray.shutdown()


if __name__ == "__main__":
    main()
