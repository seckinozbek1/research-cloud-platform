from collections import OrderedDict
from pathlib import Path
import json
import math
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
from torch.func import functional_call
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

WORLD_SIZE = 2
EPOCHS = 100
BATCH_SIZE = 512
LR = 1e-2


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
        - pd.offsets.Day(29)
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

    # Standardize the target for the minimal manual-SGD
    # sharding demonstration. Raw waste values make the
    # unscaled MSE gradients unnecessarily large and can
    # cause numerical divergence.
    y_mean = float(y.mean())
    y_std = float(y.std())

    y = (
        (y - y_mean)
        / max(y_std, 1e-8)
    ).astype("float32")

    return x, y


def flatten_model(model):
    metadata = []
    flat_parts = []

    for name, param in model.named_parameters():
        metadata.append(
            (
                name,
                tuple(param.shape),
                param.numel(),
            )
        )

        flat_parts.append(
            param.detach().reshape(-1)
        )

    return (
        torch.cat(flat_parts),
        metadata,
    )


def unflatten_params(
    flat,
    metadata,
):
    params = OrderedDict()

    offset = 0

    for name, shape, numel in metadata:
        params[name] = (
            flat[
                offset:
                offset + numel
            ]
            .view(shape)
        )

        offset += numel

    return params


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

    # Template provides architecture only.
    model = WasteMLP(
        len(FEATURES)
    )

    full_initial, metadata = (
        flatten_model(model)
    )

    total_params = (
        full_initial.numel()
    )

    shard_size = math.ceil(
        total_params / world_size
    )

    padded_total = (
        shard_size * world_size
    )

    padded = torch.zeros(
        padded_total,
        dtype=full_initial.dtype,
    )

    padded[:total_params] = (
        full_initial
    )

    start = rank * shard_size
    end = start + shard_size

    # ------------------------------------------------------
    # Persistent state:
    # each rank owns ONLY this shard.
    # ------------------------------------------------------

    local_shard = (
        padded[start:end]
        .clone()
    )

    actual_start = start

    actual_end = min(
        end,
        total_params,
    )

    actual_owned = max(
        0,
        actual_end - actual_start,
    )

    del full_initial
    del padded

    loss_fn = nn.MSELoss()

    dist.barrier()

    wall_start = time.perf_counter()

    for epoch in range(EPOCHS):

        sampler.set_epoch(epoch)

        epoch_loss = 0.0

        for xb, yb in loader:

            # --------------------------------------------------
            # FSDP-style materialization:
            # gather parameter shards only when needed.
            # --------------------------------------------------

            gathered = [
                torch.empty_like(
                    local_shard
                )
                for _ in range(
                    world_size
                )
            ]

            dist.all_gather(
                gathered,
                local_shard,
            )

            full_flat = (
                torch.cat(gathered)
                [:total_params]
                .detach()
                .requires_grad_(True)
            )

            params = unflatten_params(
                full_flat,
                metadata,
            )

            pred = functional_call(
                model,
                params,
                (xb,),
            )

            loss = loss_fn(
                pred,
                yb,
            )

            loss.backward()

            # Every rank processed different data.
            # Average full gradient across ranks.
            full_grad = (
                full_flat.grad.detach()
            )

            dist.all_reduce(
                full_grad,
                op=dist.ReduceOp.SUM,
            )

            full_grad /= world_size

            # --------------------------------------------------
            # Each rank updates ONLY its own parameter shard.
            # --------------------------------------------------

            local_grad = torch.zeros(
                shard_size,
                dtype=full_grad.dtype,
            )

            if actual_owned > 0:
                local_grad[
                    :actual_owned
                ] = full_grad[
                    actual_start:
                    actual_end
                ]

            local_shard -= (
                LR * local_grad
            )

            epoch_loss += (
                loss.item()
                * xb.shape[0]
            )

            # Full parameters were transient.
            del full_flat
            del full_grad
            del params
            del gathered

        if (
            rank == 0
            and (
                epoch == 0
                or (epoch + 1) % 25 == 0
                or epoch + 1 == EPOCHS
            )
        ):
            print(
                f"epoch={epoch + 1:03d} "
                f"local_mse="
                f"{epoch_loss / len(dataset):,.2f}"
            )

    dist.barrier()

    wall_seconds = (
        time.perf_counter()
        - wall_start
    )

    ownership = torch.tensor(
        [
            actual_owned,
            total_params,
            shard_size,
        ],
        dtype=torch.long,
    )

    gathered_ownership = [
        torch.zeros_like(
            ownership
        )
        for _ in range(
            world_size
        )
    ]

    dist.all_gather(
        gathered_ownership,
        ownership,
    )

    if rank == 0:
        rows = []

        for worker_rank, info in enumerate(
            gathered_ownership
        ):
            owned = int(
                info[0].item()
            )

            total = int(
                info[1].item()
            )

            persistent = int(
                info[2].item()
            )

            rows.append(
                {
                    "rank":
                        worker_rank,

                    "actual_owned_parameters":
                        owned,

                    "persistent_shard_elements":
                        persistent,

                    "total_model_parameters":
                        total,

                    "persistent_parameter_share":
                        persistent / total,
                }
            )

        print()
        print(
            "=== FULL PARAMETER SHARDING ==="
        )

        print(
            pd.DataFrame(rows)
            .to_string(index=False)
        )

        print()
        print(
            "Important:"
        )

        print(
            "Full model parameters exist only "
            "transiently during all_gather."
        )

        print(
            "Between steps each rank persistently "
            "stores only its local shard."
        )

        print()
        print(
            "Wall seconds:",
            f"{wall_seconds:.4f}"
        )

        metrics = {
            "mode":
                "fsdp_style_parameter_sharding",

            "world_size":
                world_size,

            "epochs":
                EPOCHS,

            "total_model_parameters":
                total_params,

            "shard_size":
                shard_size,

            "wall_seconds":
                wall_seconds,

            "workers":
                rows,
        }

        out = (
            ARTIFACT_DIR
            / "parameter-sharding-2cpu_metrics.json"
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
        "parameter-sharded workers..."
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
