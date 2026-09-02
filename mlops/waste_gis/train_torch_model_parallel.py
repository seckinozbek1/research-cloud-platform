from pathlib import Path
import time

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
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
TEST_DAYS = 30

BATCH_SIZE = 512
EPOCHS = 200
LR = 1e-3

CPU = torch.device("cpu")
GPU = torch.device("cuda:0")


class SplitWasteModel(nn.Module):
    """
    Functional model-parallel example.

    Stage 1 lives on CPU.
    Stage 2 lives on GPU.

    Every forward pass therefore performs a real
    CPU -> GPU activation transfer.
    """

    def __init__(self, input_dim):
        super().__init__()

        self.stage_cpu = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
        ).to(CPU)

        self.stage_gpu = nn.Sequential(
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        ).to(GPU)

    def forward(self, x):
        # Model part 1 executes on CPU.
        x = x.to(CPU)
        x = self.stage_cpu(x)

        # Activation crosses device boundary.
        x = x.to(
            GPU,
            non_blocking=True,
        )

        # Model part 2 executes on GPU.
        return self.stage_gpu(x)


def main():

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA GPU is required for this application."
        )

    torch.manual_seed(42)
    np.random.seed(42)

    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["collection_date"],
    )

    cutoff = (
        df["collection_date"].max()
        - pd.Timedelta(
            days=TEST_DAYS - 1
        )
    )

    train = df[
        df["collection_date"] < cutoff
    ].copy()

    test = df[
        df["collection_date"] >= cutoff
    ].copy()

    scaler = StandardScaler()

    x_train = scaler.fit_transform(
        train[FEATURES]
    ).astype("float32")

    x_test = scaler.transform(
        test[FEATURES]
    ).astype("float32")

    y_train = (
        train[TARGET]
        .to_numpy(
            dtype="float32"
        )
        .reshape(-1, 1)
    )

    y_test = (
        test[TARGET]
        .to_numpy(
            dtype="float32"
        )
        .reshape(-1, 1)
    )

    dataset = TensorDataset(
        torch.from_numpy(x_train),
        torch.from_numpy(y_train),
    )

    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
    )

    model = SplitWasteModel(
        input_dim=len(FEATURES)
    )

    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=LR,
    )

    loss_fn = nn.MSELoss()

    print("=== MODEL PLACEMENT ===")
    print(
        "stage_cpu:",
        next(
            model.stage_cpu.parameters()
        ).device,
    )
    print(
        "stage_gpu:",
        next(
            model.stage_gpu.parameters()
        ).device,
    )

    print()
    print("=== TRAINING ===")

    torch.cuda.synchronize()
    start = time.perf_counter()

    for epoch in range(
        1,
        EPOCHS + 1,
    ):

        model.train()

        epoch_loss = 0.0

        for xb, yb in loader:

            optimizer.zero_grad(
                set_to_none=True
            )

            # Input starts on CPU.
            pred = model(xb)

            # Target must be where prediction lives.
            yb = yb.to(
                GPU,
                non_blocking=True,
            )

            loss = loss_fn(
                pred,
                yb,
            )

            loss.backward()
            optimizer.step()

            epoch_loss += (
                loss.item()
                * xb.shape[0]
            )

        if (
            epoch == 1
            or epoch % 25 == 0
            or epoch == EPOCHS
        ):
            print(
                f"epoch={epoch:03d} "
                f"mse="
                f"{epoch_loss / len(dataset):,.2f}"
            )

    torch.cuda.synchronize()

    wall_seconds = (
        time.perf_counter()
        - start
    )

    # ------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------

    model.eval()

    with torch.no_grad():

        x_test_tensor = (
            torch.from_numpy(
                x_test
            )
        )

        pred = (
            model(
                x_test_tensor
            )
            .cpu()
            .numpy()
            .ravel()
        )

    truth = y_test.ravel()

    mae = mean_absolute_error(
        truth,
        pred,
    )

    rmse = np.sqrt(
        mean_squared_error(
            truth,
            pred,
        )
    )

    r2 = r2_score(
        truth,
        pred,
    )

    print()
    print("=== RESULT ===")
    print(
        f"train rows      : {len(train):,}"
    )
    print(
        f"test rows       : {len(test):,}"
    )
    print(
        f"wall seconds    : {wall_seconds:.4f}"
    )
    print(
        f"MAE             : {mae:,.2f}"
    )
    print(
        f"RMSE            : {rmse:,.2f}"
    )
    print(
        f"R2              : {r2:.4f}"
    )

    metrics = {
        "mode":
            "cpu_gpu_model_parallel",

        "train_rows":
            int(len(train)),

        "test_rows":
            int(len(test)),

        "epochs":
            EPOCHS,

        "batch_size":
            BATCH_SIZE,

        "wall_seconds":
            wall_seconds,

        "mae":
            mae,

        "rmse":
            rmse,

        "r2":
            r2,

        "stage_1_device":
            "cpu",

        "stage_2_device":
            "cuda:0",
    }

    out = (
        ARTIFACT_DIR
        / "model-parallel-cpu-gpu_metrics.json"
    )

    pd.Series(
        metrics
    ).to_json(
        out,
        indent=2,
    )

    print()
    print(
        "Metrics saved:",
        out,
    )


if __name__ == "__main__":
    main()
