from pathlib import Path
import argparse
import json
import math
import os
import time

import numpy as np
import pandas as pd
import torch
import torch.distributed as dist
from torch import nn
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

OUTPUT_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "distributed_ml"
)

TEST_DAYS = 30

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


def regression_metrics(y_true, y_pred):
    error = y_true - y_pred

    mae = np.mean(np.abs(error))
    rmse = np.sqrt(np.mean(error ** 2))

    ss_res = np.sum(error ** 2)
    ss_tot = np.sum(
        (y_true - np.mean(y_true)) ** 2
    )

    r2 = 1.0 - ss_res / ss_tot

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "r2": float(r2),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--device",
        choices=["cpu", "cuda"],
        default="cpu",
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=200,
    )

    parser.add_argument(
        "--global-batch-size",
        type=int,
        default=512,
    )

    parser.add_argument(
        "--lr",
        type=float,
        default=0.01,
    )

    args = parser.parse_args()

    torch.manual_seed(42)
    np.random.seed(42)

    world_size = int(
        os.environ.get("WORLD_SIZE", "1")
    )

    rank = int(
        os.environ.get("RANK", "0")
    )

    distributed = world_size > 1

    # ----------------------------------------------------------
    # Distributed runtime
    # ----------------------------------------------------------

    if distributed:
        if args.device == "cuda":
            available = torch.cuda.device_count()

            if available < world_size:
                raise RuntimeError(
                    f"Requested {world_size} CUDA DDP processes "
                    f"but only {available} GPU(s) are available."
                )

            local_rank = int(
                os.environ["LOCAL_RANK"]
            )

            torch.cuda.set_device(local_rank)

            device = torch.device(
                f"cuda:{local_rank}"
            )

            backend = "nccl"

        else:
            device = torch.device("cpu")
            backend = "gloo"

        dist.init_process_group(
            backend=backend,
        )

    else:
        device = torch.device(args.device)

    # ----------------------------------------------------------
    # Data
    # ----------------------------------------------------------

    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["collection_date"],
    )

    cutoff = (
        df["collection_date"].max()
        - pd.to_timedelta(
            TEST_DAYS - 1,
            unit="D",
        )
    )

    train = df[
        df["collection_date"] < cutoff
    ].copy()

    test = df[
        df["collection_date"] >= cutoff
    ].copy()

    x_train = train[FEATURES].to_numpy(
        dtype=np.float32
    )

    y_train = train[TARGET].to_numpy(
        dtype=np.float32
    )

    x_test = test[FEATURES].to_numpy(
        dtype=np.float32
    )

    y_test = test[TARGET].to_numpy(
        dtype=np.float32
    )

    # Train-only standardization.
    x_mean = x_train.mean(
        axis=0,
        keepdims=True,
    )

    x_std = x_train.std(
        axis=0,
        keepdims=True,
    )

    x_std[x_std < 1e-8] = 1.0

    y_mean = float(
        y_train.mean()
    )

    y_std = float(
        y_train.std()
    )

    if y_std < 1e-8:
        y_std = 1.0

    x_train = (
        x_train - x_mean
    ) / x_std

    x_test = (
        x_test - x_mean
    ) / x_std

    y_train_scaled = (
        y_train - y_mean
    ) / y_std

    train_dataset = TensorDataset(
        torch.from_numpy(x_train),
        torch.from_numpy(
            y_train_scaled
        ).unsqueeze(1),
    )

    # Global batch stays approximately constant.
    local_batch_size = max(
        1,
        args.global_batch_size // world_size,
    )

    sampler = None

    if distributed:
        sampler = DistributedSampler(
            train_dataset,
            num_replicas=world_size,
            rank=rank,
            shuffle=True,
            seed=42,
        )

    loader = DataLoader(
        train_dataset,
        batch_size=local_batch_size,
        shuffle=(sampler is None),
        sampler=sampler,
        num_workers=0,
        drop_last=False,
    )

    # ----------------------------------------------------------
    # Model
    # ----------------------------------------------------------

    model = nn.Linear(
        len(FEATURES),
        1,
    ).to(device)

    if distributed:
        if device.type == "cuda":
            model = DDP(
                model,
                device_ids=[device.index],
            )
        else:
            model = DDP(model)

    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=args.lr,
    )

    loss_fn = nn.MSELoss()

    if distributed:
        dist.barrier()

    if device.type == "cuda":
        torch.cuda.synchronize()

    start = time.perf_counter()

    # ----------------------------------------------------------
    # Training
    # ----------------------------------------------------------

    for epoch in range(args.epochs):

        if sampler is not None:
            sampler.set_epoch(epoch)

        model.train()

        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)

            optimizer.zero_grad(
                set_to_none=True
            )

            pred = model(xb)

            loss = loss_fn(
                pred,
                yb,
            )

            loss.backward()

            # With DDP, gradient synchronization occurs here
            # during backward via all-reduce hooks.

            optimizer.step()

    if distributed:
        dist.barrier()

    if device.type == "cuda":
        torch.cuda.synchronize()

    elapsed = (
        time.perf_counter() - start
    )

    # ----------------------------------------------------------
    # Evaluation
    # ----------------------------------------------------------

    if rank == 0:

        model.eval()

        x_test_tensor = (
            torch.from_numpy(x_test)
            .to(device)
        )

        with torch.no_grad():
            pred_scaled = (
                model(x_test_tensor)
                .squeeze(1)
                .cpu()
                .numpy()
            )

        prediction = (
            pred_scaled * y_std
            + y_mean
        )

        metrics = regression_metrics(
            y_test,
            prediction,
        )

        training_examples = (
            len(train)
            * args.epochs
        )

        throughput = (
            training_examples
            / elapsed
        )

        mode = (
            f"ddp-{world_size}-{args.device}"
            if distributed
            else f"single-{args.device}"
        )

        result = {
            "mode": mode,
            "world_size": world_size,
            "device": args.device,
            "epochs": args.epochs,
            "global_batch_size": (
                args.global_batch_size
            ),
            "train_rows": len(train),
            "test_rows": len(test),
            "wall_seconds": elapsed,
            "training_rows_per_second": throughput,
            **metrics,
        }

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            OUTPUT_DIR
            / f"{mode}_metrics.json"
        )

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                result,
                f,
                indent=2,
            )

        print()
        print(
            "Mode                 :",
            mode,
        )

        print(
            "World size           :",
            world_size,
        )

        print(
            "Train rows           :",
            f"{len(train):,}",
        )

        print(
            "Test rows            :",
            f"{len(test):,}",
        )

        print(
            "Epochs               :",
            args.epochs,
        )

        print(
            "Wall seconds         :",
            f"{elapsed:.4f}",
        )

        print(
            "Training throughput  :",
            f"{throughput:,.0f} rows/s",
        )

        print(
            "MAE                  :",
            f"{metrics['mae']:.2f}",
        )

        print(
            "RMSE                 :",
            f"{metrics['rmse']:.2f}",
        )

        print(
            "R²                   :",
            f"{metrics['r2']:.4f}",
        )

        print(
            "Metrics output       :",
            output_path,
        )

    if distributed:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
