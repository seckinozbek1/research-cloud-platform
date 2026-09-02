from pathlib import Path
import json
import os
import socket
import time

import numpy as np
import pandas as pd
import torch
import torch.distributed as dist
import torch.multiprocessing as mp
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.distributed.optim import ZeroRedundancyOptimizer
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, TensorDataset
from torch.utils.data.distributed import DistributedSampler


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

EPOCHS = 100
BATCH_SIZE = 512
LR = 1e-3
WORLD_SIZE = 2


class WasteMLP(nn.Module):
    def __init__(self, input_dim):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        return self.net(x)


def free_port():
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def prepare_data():

    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["collection_date"],
    )

    cutoff = (
        df["collection_date"].max()
        - pd.Timedelta(days=29)
    )

    train = df[
        df["collection_date"] < cutoff
    ].copy()

    scaler = StandardScaler()

    x = scaler.fit_transform(
        train[FEATURES]
    ).astype("float32")

    y = (
        train[TARGET]
        .to_numpy(dtype="float32")
        .reshape(-1, 1)
    )

    return x, y


def worker(
    rank,
    world_size,
    port,
    x,
    y,
):

    os.environ["MASTER_ADDR"] = "127.0.0.1"
    os.environ["MASTER_PORT"] = str(port)

    dist.init_process_group(
        backend="gloo",
        rank=rank,
        world_size=world_size,
    )

    torch.manual_seed(42)

    dataset = TensorDataset(
        torch.from_numpy(x),
        torch.from_numpy(y),
    )

    sampler = DistributedSampler(
        dataset,
        num_replicas=world_size,
        rank=rank,
        shuffle=True,
    )

    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        sampler=sampler,
    )

    model = WasteMLP(
        len(FEATURES)
    )

    model = DDP(model)

    # ------------------------------------------------------
    # ZeRO-style optimizer-state sharding.
    #
    # DDP still replicates model parameters, but optimizer
    # state is partitioned across workers instead of being
    # fully duplicated on every rank.
    # ------------------------------------------------------

    optimizer = ZeroRedundancyOptimizer(
        model.parameters(),
        optimizer_class=torch.optim.Adam,
        lr=LR,
    )

    loss_fn = nn.MSELoss()

    dist.barrier()

    start = time.perf_counter()

    for epoch in range(EPOCHS):

        sampler.set_epoch(epoch)

        model.train()

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

    dist.barrier()

    wall = (
        time.perf_counter()
        - start
    )

    # ------------------------------------------------------
    # Inspect optimizer ownership.
    # ------------------------------------------------------

    local_param_count = sum(
        p.numel()
        for group in optimizer.optim.param_groups
        for p in group["params"]
    )

    total_model_params = sum(
        p.numel()
        for p in model.module.parameters()
    )

    ownership = torch.tensor(
        [
            local_param_count,
            total_model_params,
        ],
        dtype=torch.long,
    )

    gathered = [
        torch.zeros_like(ownership)
        for _ in range(world_size)
    ]

    dist.all_gather(
        gathered,
        ownership,
    )

    if rank == 0:

        rows = []

        for worker_rank, tensor in enumerate(
            gathered
        ):
            local_params = int(
                tensor[0].item()
            )

            total_params = int(
                tensor[1].item()
            )

            rows.append(
                {
                    "rank":
                        worker_rank,

                    "optimizer_owned_parameters":
                        local_params,

                    "total_model_parameters":
                        total_params,

                    "optimizer_parameter_share":
                        (
                            local_params
                            / total_params
                        ),
                }
            )

        print(
            "\n=== PARAMETER / OPTIMIZER OWNERSHIP ==="
        )

        print(
            pd.DataFrame(rows)
            .to_string(index=False)
        )

        print()
        print(
            "Wall seconds:",
            f"{wall:.4f}",
        )

        metrics = {
            "mode":
                "zero_optimizer_sharding",

            "world_size":
                world_size,

            "epochs":
                EPOCHS,

            "wall_seconds":
                wall,

            "total_model_parameters":
                total_model_params,

            "workers":
                rows,
        }

        out = (
            ARTIFACT_DIR
            / "zero-2cpu-sharding_metrics.json"
        )

        out.write_text(
            json.dumps(
                metrics,
                indent=2,
            )
        )

        print(
            "Metrics saved:",
            out,
        )

    dist.destroy_process_group()


def main():

    x, y = prepare_data()

    port = free_port()

    print(
        "Launching",
        WORLD_SIZE,
        "distributed CPU workers..."
    )

    mp.spawn(
        worker,
        args=(
            WORLD_SIZE,
            port,
            x,
            y,
        ),
        nprocs=WORLD_SIZE,
        join=True,
    )


if __name__ == "__main__":
    main()
